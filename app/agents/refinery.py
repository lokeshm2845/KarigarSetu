"""Refinery Reconciliation Agent: matches pure gold recovered from scrap against what the ledger expects."""
from __future__ import annotations


def reconcile(orders: list[dict], recovered_pure_g: float, recovery_rate: float = 0.97) -> dict:
    scrap = [o for o in orders if o.get("scrap_g")]
    expected = sum(o["scrap_g"] * o["karat"] / 24 for o in scrap) * recovery_rate
    gap = recovered_pure_g - expected
    gap_pct = (gap / expected * 100) if expected else 0.0
    ok = abs(gap_pct) <= 2.0
    return {
        "scrap_lots": len(scrap),
        "scrap_g": round(sum(o["scrap_g"] for o in scrap), 3),
        "expected_pure_g": round(expected, 3),
        "recovered_pure_g": round(recovered_pure_g, 3),
        "gap_g": round(gap, 3),
        "gap_pct": round(gap_pct, 2),
        "ok": ok,
        "message": "Refinery recovery matches the ledger." if ok else
        f"Refinery recovery differs from the ledger by {gap:+.3f} g ({gap_pct:+.1f}%). Review the scrap lots.",
    }
