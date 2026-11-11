"""Wastage Guard Agent: checks every return against the agreed wastage and the karigar's own history."""
from __future__ import annotations

from statistics import mean, pstdev

from .. import config


def check(order: dict, history_excess_pp: list[float] | None = None) -> dict:
    """`history_excess_pp` = this karigar's past (loss% - agreed%) values, oldest first."""
    issued = order["issued_g"]
    loss = round(issued - order["returned_g"] - order["scrap_g"], 3)
    loss_pct = loss / issued * 100
    agreed = order["agreed_wastage_pct"]
    allowance = issued * agreed / 100
    excess_g = round(loss - allowance, 3)
    excess_pp = loss_pct - agreed

    reasons = []
    if loss < 0:
        reasons.append("More gold returned than issued: check the issue weight")
    if excess_pp > config.WASTAGE_TOLERANCE_PP:
        reasons.append(f"Loss {loss_pct:.1f}% vs {agreed:.1f}% agreed (+{excess_g:.2f} g)")
    history = history_excess_pp or []
    if len(history) >= 5 and excess_pp > 0:
        mu, sd = mean(history), max(pstdev(history), 0.1)
        if excess_pp > mu + 3 * sd and not reasons:
            reasons.append(f"Unusual for this karigar: {excess_pp:+.2f} points vs usual {mu:+.2f}")

    return {
        "order_id": order["order_id"],
        "loss_g": loss,
        "loss_pct": round(loss_pct, 2),
        "agreed_pct": agreed,
        "allowance_g": round(allowance, 3),
        "excess_g": excess_g,
        "flag": bool(reasons),
        "reasons": reasons,
        "message": ("Wastage flag: " + "; ".join(reasons) + ". Both parties asked to review.")
        if reasons else (f"Wastage {loss_pct:.1f}% is within tolerance of the agreed {agreed:.1f}% "
                         f"(±{config.WASTAGE_TOLERANCE_PP} points)."),
    }
