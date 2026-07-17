# ── PokeVault Web — app.py ────────────────────────────────────────────────
# Flask routes ONLY. All agent / Pokemon TCG API / SQLite logic is
# imported directly from pokevault_core.py -- a tkinter-free module
# containing only the non-GUI classes/constants extracted from
# pokevault_ui.py. Nothing from that logic is duplicated or rewritten
# here.
#
#   from pokevault_core import EnhancedPokeVaultAgent, PokeTCGClient, CollectionDB, CONDITIONS
#
# WHY THIS CHANGED FROM IMPORTING pokevault_ui DIRECTLY:
#   pokevault_ui.py is a Tkinter desktop app -- it has
#   "import tkinter as tk" and "from tkinter import ttk, messagebox" at
#   module level. Importing pokevault_ui from a web process therefore
#   required Tk/Tcl to be installed on the server even though no GUI is
#   ever opened. pokevault_core.py contains the same agent/API/DB logic
#   with zero tkinter dependency, so this Flask app (and its Gunicorn/
#   Render deployment) no longer needs Tk installed at all.
#   pokevault_ui.py itself has NOT been modified -- it still works
#   exactly as before as a standalone desktop app.
#
# KNOWN BEHAVIOR INHERITED FROM pokevault_core.py AS-IS (verbatim from
# pokevault_ui.py, not modified here -- listed so it isn't mistaken for
# a bug in app.py):
#   - PokeTCGClient.extract_market_price() returns 0.0 (not None) when
#     TCGplayer has no price data, so this layer cannot fully
#     distinguish "no price data" from "an actual $0 price." The
#     _format_price() helper below treats a 0.0 value as unavailable
#     for display purposes only -- it does not alter the underlying
#     value used by decide().
#   - PokeVaultAgent.decide() does not return a "diagnostics" key in
#     this version, so the Analysis Notes list will be empty.
#     decision.get("diagnostics", []) is used defensively so this does
#     not raise an error.
#   - rarity_rank / normalize_rarity in this version only recognize
#     Common, Uncommon, Rare, Ultra Rare, and Secret Rare. Other rarity
#     strings (e.g. "Double Rare") normalize to "Unknown", which makes
#     decide() report the card as not found.
# ─────────────────────────────────────────────────────────────────────────

import os

import requests
from flask import Flask, request, jsonify, render_template

from pokevault_core import EnhancedPokeVaultAgent, PokeTCGClient, CollectionDB, CONDITIONS

app = Flask(__name__)

# No secrets are hardcoded or exposed to the browser -- both are read
# from environment variables at process start.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
_api_key = os.environ.get("POKEMONTCG_IO_API_KEY")  # optional
_db_path = os.environ.get("DATABASE_PATH", "pokevault_collection.db")

agent = EnhancedPokeVaultAgent()
api_client = PokeTCGClient(api_key=_api_key)
db = CollectionDB(db_path=_db_path)


def _format_price(card_info):
    """Presentation-only helper -- not agent/API logic. Formats the
    market_price value exactly as returned by PokeTCGClient.lookup()."""
    price = card_info.get("market_price")
    if price in (None, 0, 0.0):
        return "Unavailable from TCGplayer."
    return f"${price:.2f} (TCGplayer)"


@app.route("/")
def index():
    return render_template("index.html", conditions=CONDITIONS)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Runs the full expert-system + CBR analysis via the imported
    agent/API classes. Used by BOTH modes. In 'collect' mode it also
    reports current/projected collection counts via CollectionDB, but
    NEVER writes to the database -- saving only happens in
    /api/add_to_collection, a separate explicit user action."""
    data = request.get_json(silent=True) or {}

    mode = data.get("mode", "consult")
    card_name_hint = (data.get("card_name") or "").strip()
    set_name = (data.get("set_name") or "").strip()
    card_number = (data.get("card_number") or "").strip()
    condition = data.get("condition") or "Near Mint"

    if condition not in CONDITIONS:
        return jsonify({"error": f"Invalid condition '{condition}'."}), 400

    if not set_name or not card_number:
        return jsonify({"error": "Please enter both the set name and card number."}), 400

    try:
        quantity = int(data.get("quantity", 1))
        if quantity < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Quantity must be a positive whole number."}), 400

    try:
        card_info = api_client.lookup(set_name, card_number)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except requests.RequestException as exc:
        return jsonify({"error": f"Could not reach the Pokemon TCG API: {exc}"}), 502

    # Card-name field is an optional hint/cross-check only -- the card
    # is always uniquely identified by set + printed number.
    name_note = None
    if card_name_hint:
        hint_lower = card_name_hint.lower()
        found_lower = card_info["name"].lower()
        if hint_lower not in found_lower and found_lower not in hint_lower:
            name_note = (
                f"Note: the card name you entered ('{card_name_hint}') doesn't match "
                f"the card found via the set + card number lookup ('{card_info['name']}'). "
                "Showing the card found by set + number, since that uniquely identifies "
                "a card in the Pokemon TCG API."
            )

    collection_status = None
    quantity_for_rules = quantity

    if mode == "collect":
        # Analysis only -- no database writes happen here.
        owned_in_condition = db.get_quantity_in_condition(
            card_info["set_id"], card_info["card_number"], condition
        )
        total_owned = db.get_total_quantity(card_info["set_id"], card_info["card_number"])
        breakdown = db.get_condition_breakdown(card_info["set_id"], card_info["card_number"])

        projected_in_condition = owned_in_condition + quantity
        projected_total = total_owned + quantity
        quantity_for_rules = projected_total  # recommendations use projected total

        collection_status = {
            "owned_in_condition": owned_in_condition,
            "total_owned": total_owned,
            "breakdown": breakdown,
            "projected_in_condition": projected_in_condition,
            "projected_total": projected_total,
        }

    percept = agent.build_percept_from_api(
        name=card_info["name"],
        set_name=card_info["set_name"],
        rarity=card_info["rarity"],
        condition=condition,
        quantity=quantity_for_rules,
        estimated_value=card_info["market_price"],
    )
    decision = agent.decide(percept)

    rules_fired = [r for r in decision["rules_fired"] if not r.startswith("CBR")]
    cbr_lines = [r for r in decision["rules_fired"] if r.startswith("CBR")]
    recommendations = [r for r in decision["recommendations"] if not r.startswith("CBR support")]
    cbr_recommendations = [r for r in decision["recommendations"] if r.startswith("CBR support")]

    return jsonify({
        "mode": mode,
        "card_info": card_info,
        "price_display": _format_price(card_info),
        "condition": condition,
        "quantity": quantity,
        "rules_fired": rules_fired,
        "recommendations": recommendations,
        "cbr_lines": cbr_lines,
        "cbr_recommendations": cbr_recommendations,
        # decision.get(...) is defensive: this version of
        # pokevault_ui.py's decide() does not produce a "diagnostics"
        # key, so this will simply be an empty list.
        "diagnostics": decision.get("diagnostics", []),
        "collection_status": collection_status,
        "name_note": name_note,
    })


@app.route("/api/add_to_collection", methods=["POST"])
def api_add_to_collection():
    """The ONLY route that writes to the database -- a separate,
    explicit user action distinct from /api/analyze above."""
    data = request.get_json(silent=True) or {}

    card_info = data.get("card_info")
    condition = data.get("condition")
    if not card_info or not condition:
        return jsonify({"error": "Missing card info or condition. Please analyze the card again."}), 400

    if condition not in CONDITIONS:
        return jsonify({"error": f"Invalid condition '{condition}'."}), 400

    required_keys = ["name", "set_name", "set_id", "card_number", "rarity"]
    if any(k not in card_info for k in required_keys):
        return jsonify({"error": "Incomplete card info. Please analyze the card again."}), 400

    try:
        quantity = int(data.get("quantity", 1))
        if quantity < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Quantity must be a positive whole number."}), 400

    db.add_card(card_info, condition, quantity)

    # Log the action through the original agent's act() method so the
    # performance_log / architecture stays consistent with the imported
    # baseline agent's action-logging behavior.
    agent.act({
        "card": card_info["name"],
        "recommendations": data.get("recommendations", []),
        "rules_fired": data.get("rules_fired", []),
    })

    return jsonify({
        "status": "ok",
        "message": f"Added {quantity} x {card_info['name']} ({condition}) to your collection.",
    })


@app.route("/api/collection", methods=["GET"])
def api_collection():
    """Powers the Collection summary panel."""
    cards = db.get_all_cards()
    total_copies = sum(c["quantity"] for c in cards)
    unique_cards = len({(c["set_id"], c["card_number"]) for c in cards})
    return jsonify({
        "cards": cards,
        "total_copies": total_copies,
        "unique_cards": unique_cards,
    })


if __name__ == "__main__":
    # Local development server only. In production, use Gunicorn
    # pointed at this same "app" object, e.g.: gunicorn app:app
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
