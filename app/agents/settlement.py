"""Settlement Agent: drafts the gold and labour settlement on delivery. Both parties must approve it."""
from __future__ import annotations

from urllib.parse import quote

from .. import config


def draft(order: dict, karigar: dict, settled_on: str) -> dict:
    issued = order["issued_g"]
    loss = issued - order["returned_g"] - order["scrap_g"]
    allowance = issued * order["agreed_wastage_pct"] / 100
    balance = round(loss - allowance, 3)            # > 0: karigar holds extra gold
    gold_adjust = round(max(balance, 0) * config.GOLD_RATE_INR_PER_G)
    labour = int(order["labour_inr"])
    net = max(labour - gold_adjust, 0)
    upi = (f"upi://pay?pa={quote(karigar.get('upi_id', 'karigar@upi'))}&pn={quote(karigar['name'])}"
           f"&am={net:.2f}&cu=INR&tn={quote('KarigarSetu ' + order['order_id'])}")
    return {
        "order_id": order["order_id"],
        "karigar_id": order["karigar_id"],
        "loss_g": round(loss, 3),
        "allowance_g": round(allowance, 3),
        "gold_balance_g": balance,
        "gold_adjust_inr": gold_adjust,
        "labour_inr": labour,
        "net_payable_inr": net,
        "gold_rate_inr_per_g": config.GOLD_RATE_INR_PER_G,
        "upi_link": upi,
        "date": settled_on,
    }
