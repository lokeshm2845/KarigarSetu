"""Deadline Agent: predicts finish dates from each karigar's track record and warns early."""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import median

from .. import config


def speed_ratio(history_ratios: list[float]) -> float:
    """history_ratios = actual_days / typical_days for this karigar's finished orders."""
    return median(history_ratios) if len(history_ratios) >= 3 else 1.0


def assess(order: dict, today: date, history_ratios: list[float]) -> dict:
    issued_on = date.fromisoformat(order["issued_on"])
    due = date.fromisoformat(order["due_date"])
    base_days = config.CATEGORIES[order["item"]]["base_days"]
    ratio = speed_ratio(history_ratios)
    predicted = issued_on + timedelta(days=math.ceil(base_days * ratio))
    days_left = (due - today).days

    if order.get("returned_on"):
        status = "DONE"
    elif today > due:
        status = "OVERDUE"
    elif predicted > due:
        status = "AT_RISK"
    elif days_left <= config.DEADLINE_WARN_DAYS:
        status = "REMIND"
    else:
        status = "ON_TRACK"

    occasion = order.get("occasion_date")
    msg = {
        "AT_RISK": (f"#{order['order_id']} ({order['item']}) is likely to finish around {predicted.isoformat()}, "
                    f"after the due date {due.isoformat()}"
                    + (f" (customer occasion {occasion})" if occasion else "")
                    + ". Consider splitting or reassigning the work."),
        "OVERDUE": f"#{order['order_id']} is {-days_left} day(s) past its due date {due.isoformat()}.",
        "REMIND": f"Reminder: #{order['order_id']} is due on {due.isoformat()} ({days_left} day(s) left).",
        "ON_TRACK": f"#{order['order_id']} is on track for {due.isoformat()}.",
        "DONE": f"#{order['order_id']} has been returned.",
    }[status]
    return {"order_id": order["order_id"], "status": status, "predicted_finish": predicted.isoformat(),
            "due_date": due.isoformat(), "days_left": days_left, "speed_ratio": round(ratio, 2), "message": msg}
