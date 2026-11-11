"""Projects the current state of every order from the confirmed ledger entries."""
from __future__ import annotations


def project_orders(entries: list[dict]) -> dict[str, dict]:
    orders: dict[str, dict] = {}
    for e in entries:
        p, t = e["payload"], e["entry_type"]
        if t == "ISSUE":
            orders[p["order_id"]] = {
                **p,
                "status": "WITH_KARIGAR",
                "returned_g": 0.0,
                "scrap_g": 0.0,
                "returned_on": None,
                "settlement": None,
                "issue_seq": e["seq"],
            }
        elif t == "RETURN" and p["order_id"] in orders:
            o = orders[p["order_id"]]
            o["returned_g"] = round(o["returned_g"] + p.get("piece_g", 0.0), 3)
            o["scrap_g"] = round(o["scrap_g"] + p.get("scrap_g", 0.0), 3)
            if p.get("piece_g", 0.0) > 0:
                o["returned_on"] = p["date"]
            o["status"] = "RETURNED"
        elif t == "SETTLEMENT" and p["order_id"] in orders:
            o = orders[p["order_id"]]
            o["settlement"] = p
            o["status"] = "SETTLED"
    for o in orders.values():
        if o["returned_on"]:
            o["loss_g"] = round(o["issued_g"] - o["returned_g"] - o["scrap_g"], 3)
            o["loss_pct"] = round(o["loss_g"] / o["issued_g"] * 100, 2)
    return orders
