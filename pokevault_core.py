# ── PokeVault Core — reusable, tkinter-free logic ─────────────────────────
# Agent: PokeVault
# Author: Janice Hung
#
# This module contains ONLY the non-GUI classes and constants extracted
# verbatim from pokevault_ui.py:
#   - PokeVaultAgent          (baseline rule engine, all 8 rules)
#   - EnhancedPokeVaultAgent  (Case-Based Reasoning subclass)
#   - PokeTCGClient           (Pokemon TCG API: set resolution, card
#                               search, card-number parsing, rarity
#                               normalization, price extraction)
#   - CollectionDB            (SQLite persistence)
#   - CONDITIONS              (the 5 allowed condition values)
#
# It deliberately does NOT include:
#   - tkinter / tkinter.ttk / tkinter.messagebox imports
#   - PokeVaultApp (the Tkinter UI class)
#   - launch_app()
#   - any Tkinter widget code
#
# This lets a Flask (or any other non-GUI) app import the agent/API/DB
# logic without pulling in a Tk/Tcl dependency. pokevault_ui.py itself
# has NOT been modified -- it still contains its own copy of this logic
# plus the Tkinter desktop UI, exactly as before.
# ─────────────────────────────────────────────────────────────────────────

import sqlite3
import datetime

import requests


# ─────────────────────────────────────────────────────────────────────────
# ORIGINAL BASELINE AGENT -- DO NOT REMOVE OR RENUMBER ANY RULE.
# This class is preserved exactly as it was in pokevault_ui.py.
# ─────────────────────────────────────────────────────────────────────────
class PokeVaultAgent:
    def __init__(self):
        self.rarity_rank = {
            "Common": 1,
            "Uncommon": 2,
            "Rare": 3,
            "Ultra Rare": 4,
            "Secret Rare": 5
        }

        self.card_database = {
            "199/165": {
                "name": "Charizard ex",
                "set": "Scarlet & Violet 151",
                "rarity": "Secret Rare",
                "estimated_value": 402.89
            },
            "025/165": {
                "name": "Pikachu",
                "set": "Scarlet & Violet 151",
                "rarity": "Common",
                "estimated_value": 2
            },
            "009/165": {
                "name": "Blastoise",
                "set": "Scarlet & Violet 151",
                "rarity": "Ultra Rare",
                "estimated_value": 80
            }
        }

        self.performance_log = []

    def perceive(self, card_input):
        set_number = card_input["set_number"]

        card_info = self.card_database.get(set_number, {
            "name": "Unknown Card",
            "set": "Unknown Set",
            "rarity": "Unknown",
            "estimated_value": 0
        })

        return {
            "set_number": set_number,
            "name": card_info["name"],
            "set": card_info["set"],
            "rarity": card_info["rarity"],
            "condition": card_input["condition"],
            "quantity": card_input["quantity"],
            "estimated_value": card_info["estimated_value"],
            "is_high_value": False,
            "recommendations": [],
            "rules_fired": []
        }

    def decide(self, percept):
        if percept["rarity"] == "Unknown":
            return {
                "card": percept["name"],
                "recommendations": ["Card not found. Please verify the set number."],
                "rules_fired": ["No rules fired because the card was not found."]
            }

        if self.rarity_rank[percept["rarity"]] >= 4 and percept["condition"] == "Near Mint":
            percept["recommendations"].append("Recommend grading")
            percept["rules_fired"].append("Rule 1 fired")

        if percept["estimated_value"] >= 100:
            percept["is_high_value"] = True
            percept["recommendations"].append("Flag as high-value card")
            percept["rules_fired"].append("Rule 2 fired")

        if percept["is_high_value"]:
            percept["recommendations"].append("Use protective storage")
            percept["rules_fired"].append("Rule 3 fired")

        if percept["quantity"] > 3:
            percept["recommendations"].append("Consider selling or trading duplicates")
            percept["rules_fired"].append("Rule 4 fired")

        if percept["condition"] in ["Damaged", "Heavily Played"]:
            percept["recommendations"].append("Do not grade due to poor condition")
            percept["rules_fired"].append("Rule 5 fired")

        if percept["rarity"] == "Common" and percept["quantity"] > 3:
            percept["recommendations"].append("Move duplicates to bulk storage")
            percept["rules_fired"].append("Rule 6 fired")

        if percept["is_high_value"] and percept["condition"] == "Near Mint":
            percept["recommendations"].append("Mark as priority card")
            percept["rules_fired"].append("Rule 7 fired")

        if percept["estimated_value"] >= 300:
            percept["recommendations"].append("Document card for insurance purposes")
            percept["rules_fired"].append("Rule 8 fired")

        return {
            "card": percept["name"],
            "recommendations": percept["recommendations"],
            "rules_fired": percept["rules_fired"]
        }

    def act(self, action):
        self.performance_log.append(action)
        return f"Executed recommendations for {action['card']}"

    def run(self, inputs):
        for raw_input in inputs:
            percept = self.perceive(raw_input)
            action = self.decide(percept)
            result = self.act(action)

            print("\nPercept:")
            print(percept)

            print("\nDecision Process:")
            for rule in action["rules_fired"]:
                print("-", rule)

            print("\nFinal Action:")
            for rec in action["recommendations"]:
                print("-", rec)

            print("\nResult:", result)

    # ── NEW, ADDITIVE-ONLY helper ──────────────────────────────────────
    # This does NOT alter perceive()/decide() above. It builds a percept
    # dict with the exact same shape/keys that perceive() produces, but
    # populated from live Pokemon TCG API data instead of the small
    # built-in card_database. decide() then runs completely unmodified
    # against it, so all 8 rules apply identically to real API cards.
    def build_percept_from_api(self, name, set_name, rarity, condition, quantity, estimated_value):
        return {
            "set_number": None,
            "name": name,
            "set": set_name,
            "rarity": rarity,
            "condition": condition,
            "quantity": quantity,
            "estimated_value": estimated_value,
            "is_high_value": False,
            "recommendations": [],
            "rules_fired": []
        }


# ─────────────────────────────────────────────────────────────────────────
# ORIGINAL CBR ENHANCEMENT -- UNCHANGED.
# ─────────────────────────────────────────────────────────────────────────
class EnhancedPokeVaultAgent(PokeVaultAgent):
    def __init__(self):
        super().__init__()

        self.enhancement_model = [
            {
                "name": "Charizard ex",
                "rarity": "Secret Rare",
                "condition": "Near Mint",
                "past_decision": "Grade and protect"
            },
            {
                "name": "Pikachu",
                "rarity": "Common",
                "condition": "Lightly Played",
                "past_decision": "Bulk storage"
            },
            {
                "name": "Blastoise",
                "rarity": "Ultra Rare",
                "condition": "Damaged",
                "past_decision": "Do not grade"
            }
        ]

    def enhance(self, decision, percept):
        refined_decision = decision

        for case in self.enhancement_model:
            if percept["rarity"] == case["rarity"] and percept["condition"] == case["condition"]:
                refined_decision["recommendations"].append(
                    "CBR support: Similar past case suggests: " + case["past_decision"]
                )
                refined_decision["rules_fired"].append(
                    "CBR applied: Similar past case retrieved and reused"
                )
                break

        return refined_decision

    def decide(self, percept):
        base_decision = super().decide(percept)
        final_decision = self.enhance(base_decision, percept)
        return final_decision


# ─────────────────────────────────────────────────────────────────────────
# NEW: Pokemon TCG API client
#
# Resolves a printed set name (e.g. "Scarlet & Violet 151") to the
# internal API set ID, then searches for a specific card by set ID and
# printed card number (e.g. "199/165" -> number "199"). The user is
# never asked for the API set ID directly -- it is resolved internally.
# ─────────────────────────────────────────────────────────────────────────
class PokeTCGClient:
    BASE_URL = "https://api.pokemontcg.io/v2"

    # Rarity strings returned by the API are much more varied than the
    # 5 buckets used by the original rule engine's rarity_rank dict.
    # This mapping is NEW code that sits outside decide()/rarity_rank --
    # it normalizes API rarities down to the 5 buckets the original
    # expert-system rules already understand, so no rule logic changes.
    RARITY_KEYWORD_MAP = [
        (["secret", "rainbow", "gold", "hyper"], "Secret Rare"),
        (["ultra", "vmax", "vstar", " ex", "amazing", "radiant",
          "prime", "legend", " gx", " v "], "Ultra Rare"),
        (["rare"], "Rare"),
        (["uncommon"], "Uncommon"),
        (["common"], "Common"),
    ]

    def __init__(self, api_key=None, timeout=10):
        self.timeout = timeout
        self.headers = {}
        if api_key:
            self.headers["X-Api-Key"] = api_key

    @classmethod
    def normalize_rarity(cls, api_rarity):
        """Map a raw Pokemon TCG API rarity string onto one of the 5
        buckets used by the original rule engine (Common, Uncommon,
        Rare, Ultra Rare, Secret Rare), or 'Unknown' if unrecognized."""
        if not api_rarity:
            return "Unknown"
        lowered = f" {api_rarity.lower()} "
        for keywords, bucket in cls.RARITY_KEYWORD_MAP:
            for kw in keywords:
                if kw in lowered:
                    return bucket
        return "Unknown"

    def resolve_set_id(self, set_name):
        """Given a printed set name typed by the user, return the
        best-matching (set_id, official_set_name) tuple, or (None, None)
        if nothing could be found."""
        set_name = set_name.strip()
        if not set_name:
            return None, None

        # First try an exact quoted match.
        candidates = self._query_sets(f'name:"{set_name}"')
        if not candidates:
            # Fall back to a wildcard / contains match.
            candidates = self._query_sets(f'name:*{set_name}*')

        if not candidates:
            return None, None

        best = candidates[0]
        return best.get("id"), best.get("name")

    def _query_sets(self, query):
        try:
            resp = requests.get(
                f"{self.BASE_URL}/sets",
                params={"q": query},
                headers=self.headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except (requests.RequestException, ValueError):
            return []

    def search_card(self, set_id, printed_number):
        """Search for a card by API set ID and printed number (the part
        before the slash, e.g. '199' from '199/165'). Tries a couple of
        common number formatting variants since some sets store numbers
        with or without leading zeros."""
        number_variants = self._number_variants(printed_number)

        for number in number_variants:
            data = self._query_cards(f'set.id:{set_id} number:{number}')
            if data:
                return data[0]

        return None

    @staticmethod
    def _number_variants(printed_number):
        raw = printed_number.strip()
        variants = [raw]
        try:
            stripped = str(int(raw))
            if stripped not in variants:
                variants.append(stripped)
        except ValueError:
            pass
        return variants

    def _query_cards(self, query):
        try:
            resp = requests.get(
                f"{self.BASE_URL}/cards",
                params={"q": query},
                headers=self.headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except (requests.RequestException, ValueError):
            return []

    @staticmethod
    def extract_market_price(card_json):
        """Pull a TCGplayer 'market' price out of whichever printing
        variant (normal, holofoil, reverseHolofoil, etc.) is available."""
        tcgplayer = card_json.get("tcgplayer") or {}
        prices = tcgplayer.get("prices") or {}
        preferred_order = [
            "normal", "holofoil", "reverseHolofoil",
            "1stEditionHolofoil", "1stEditionNormal", "unlimitedHolofoil",
        ]
        for variant in preferred_order:
            variant_prices = prices.get(variant)
            if variant_prices and variant_prices.get("market") is not None:
                return float(variant_prices["market"])
        # Fall back to any variant that has a market price.
        for variant_prices in prices.values():
            if variant_prices and variant_prices.get("market") is not None:
                return float(variant_prices["market"])
        return 0.0

    def lookup(self, set_name, printed_number):
        """High-level convenience method used by the UI. Returns a dict
        with the fields the UI needs, or raises ValueError with a
        user-friendly message if the card/set cannot be found."""
        number_part = printed_number.split("/")[0].strip()
        if not number_part:
            raise ValueError("Please enter a printed card number such as 199/165.")

        set_id, official_set_name = self.resolve_set_id(set_name)
        if not set_id:
            raise ValueError(
                f"Could not find a set matching '{set_name}'. "
                "Check the spelling of the set name printed on the card."
            )

        card_json = self.search_card(set_id, number_part)
        if not card_json:
            raise ValueError(
                f"Could not find card number '{printed_number}' in set "
                f"'{official_set_name}'. Check the printed card number."
            )

        images = card_json.get("images") or {}

        return {
            "name": card_json.get("name", "Unknown Card"),
            "set_name": official_set_name,
            "set_id": set_id,
            "card_number": printed_number,
            "rarity_raw": card_json.get("rarity"),
            "rarity": self.normalize_rarity(card_json.get("rarity")),
            "image_url": images.get("large") or images.get("small") or "",
            "market_price": self.extract_market_price(card_json),
        }


# ─────────────────────────────────────────────────────────────────────────
# NEW: SQLite collection persistence
#
# Each (set_id, card_number, condition) combination is stored as its own
# row, so the same physical card in two different conditions occupies
# two separate rows with independent quantities.
# ─────────────────────────────────────────────────────────────────────────
class CollectionDB:
    def __init__(self, db_path="pokevault_collection.db"):
        self.db_path = db_path
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collection (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_name TEXT NOT NULL,
                    set_name TEXT NOT NULL,
                    set_id TEXT NOT NULL,
                    card_number TEXT NOT NULL,
                    rarity TEXT,
                    image_url TEXT,
                    market_price REAL,
                    condition TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT,
                    UNIQUE(set_id, card_number, condition)
                )
            """)
            conn.commit()

    def get_condition_breakdown(self, set_id, card_number):
        """Return {condition: quantity} for every condition on file for
        this card."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT condition, quantity FROM collection "
                "WHERE set_id = ? AND card_number = ?",
                (set_id, card_number),
            ).fetchall()
        return {row["condition"]: row["quantity"] for row in rows}

    def get_quantity_in_condition(self, set_id, card_number, condition):
        breakdown = self.get_condition_breakdown(set_id, card_number)
        return breakdown.get(condition, 0)

    def get_total_quantity(self, set_id, card_number):
        breakdown = self.get_condition_breakdown(set_id, card_number)
        return sum(breakdown.values())

    def add_card(self, card_info, condition, quantity):
        """Insert a new row, or if a row already exists for this exact
        (set_id, card_number, condition), increment its quantity."""
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO collection
                    (card_name, set_name, set_id, card_number, rarity,
                     image_url, market_price, condition, quantity, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(set_id, card_number, condition) DO UPDATE SET
                    quantity = quantity + excluded.quantity,
                    market_price = excluded.market_price,
                    rarity = excluded.rarity,
                    image_url = excluded.image_url,
                    date_added = excluded.date_added
            """, (
                card_info["name"], card_info["set_name"], card_info["set_id"],
                card_info["card_number"], card_info["rarity"],
                card_info["image_url"], card_info["market_price"],
                condition, quantity, now,
            ))
            conn.commit()

    def get_all_cards(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM collection "
                "ORDER BY card_name COLLATE NOCASE, set_name, condition"
            ).fetchall()
        return [dict(row) for row in rows]


CONDITIONS = [
    "Near Mint",
    "Lightly Played",
    "Moderately Played",
    "Heavily Played",
    "Damaged",
]
