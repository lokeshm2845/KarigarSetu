"""Consent Agent: asks the other party to confirm each entry and interprets their reply."""
from __future__ import annotations

import re

YES = {"ok", "okay", "yes", "y", "haan", "han", "ha", "haa", "sari", "sariyagide", "houdu", "hoon", "hu",
       "theek", "thik", "confirm", "confirmed", "correct", "ಸರಿ", "ಹೌದು", "हाँ", "हां", "ठीक", "✅", "👍"}
NO = {"no", "n", "nahi", "nahin", "illa", "alla", "galat", "wrong", "tappu", "reject",
      "ಇಲ್ಲ", "ತಪ್ಪು", "नहीं", "गलत", "❌", "👎"}


def interpret(text: str) -> bool | None:
    """True = approve, False = reject, None = unclear (ask again)."""
    tokens = set(re.findall(r"[\wऀ-ॿಀ-೿]+|[✅❌👍👎]", text.lower()))
    yes, no = bool(tokens & YES), bool(tokens & NO)
    if yes and not no:
        return True
    if no and not yes:
        return False
    return None


def describe(entry_type: str, p: dict) -> str:
    if entry_type == "ISSUE":
        return (f"Issue: {p['karigar_name']} · {p['issued_g']:.3f} g · {p['karat']}K · "
                f"{p['item'].title()} #{p['order_id']} · due {p['due_date']}")
    if entry_type == "RETURN":
        parts = []
        if p.get("piece_g"):
            parts.append(f"piece {p['piece_g']:.3f} g")
        if p.get("scrap_g"):
            parts.append(f"scrap {p['scrap_g']:.3f} g")
        return f"Return for #{p['order_id']}: " + ", ".join(parts)
    if entry_type == "SETTLEMENT":
        return (f"Settlement #{p['order_id']}: gold balance {p['gold_balance_g']:+.3f} g, "
                f"labour ₹{p['labour_inr']:,}, pay ₹{p['net_payable_inr']:,}")
    return f"{entry_type}: {p}"


def confirmation_request(entry_type: str, payload: dict, pending_id: int) -> str:
    return f"Please confirm (ref P{pending_id}). {describe(entry_type, payload)}. Reply OK / Sari / Haan, or No."
