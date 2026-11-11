"""Trust Profile Agent: builds a karigar-owned, verifiable record of work delivered."""
from __future__ import annotations

from datetime import date
from statistics import mean

from .. import config


def build(karigar: dict, orders: list[dict]) -> dict:
    done = [o for o in orders if o.get("returned_on")]
    if not done:
        return {"karigar_id": karigar["id"], "name": karigar["name"], "orders_completed": 0,
                "score": None, "tier": "New", "message": "No completed orders yet."}
    on_time = [date.fromisoformat(o["returned_on"]) <= date.fromisoformat(o["due_date"]) for o in done]
    excess = [o["loss_pct"] - o["agreed_wastage_pct"] for o in done]
    over = sum(1 for e in excess if e > config.WASTAGE_TOLERANCE_PP)
    on_time_rate = sum(on_time) / len(done)
    accuracy = 1 - over / len(done)
    volume = min(len(done) / 20, 1.0)
    score = round(100 * (0.45 * on_time_rate + 0.45 * accuracy + 0.10 * volume))
    tier = "Gold" if score >= 85 else "Silver" if score >= 70 else "Building"
    return {
        "karigar_id": karigar["id"],
        "name": karigar["name"],
        "orders_completed": len(done),
        "gold_handled_g": round(sum(o["issued_g"] for o in done), 3),
        "on_time_rate": round(on_time_rate, 3),
        "avg_wastage_vs_agreed_pp": round(mean(excess), 2),
        "returns_over_agreed": over,
        "score": score,
        "tier": tier,
        "message": (f"{karigar['name']}: {len(done)} order{'s' if len(done) != 1 else ''}, {on_time_rate:.0%} on time, "
                    f"{over} return(s) over agreed wastage. Trust score {score}/100 ({tier})."),
    }
