"""Loads the simulated dataset into a fresh ledger, replaying events up to `today`."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .agents import wastage_guard
from .ledger import Ledger
from .orchestrator import KarigarSetu

DATA = Path(__file__).resolve().parents[1] / "data" / "dummy_dataset.json"


def load_dataset() -> dict:
    if not DATA.exists():
        import runpy
        runpy.run_path(str(DATA.parent / "generate_dummy_data.py"), run_name="__main__")
    return json.loads(DATA.read_text(encoding="utf-8"))


def build_app_state(today: date, db_path: str = ":memory:") -> KarigarSetu:
    data = load_dataset()
    ks = KarigarSetu(Ledger(db_path), data["jeweller"], data["karigars"])
    ledger = ks.ledger
    t = today.isoformat()

    events = []
    for o in data["orders"]:
        if o["issued_on"] <= t:
            events.append((o["issued_on"], 0, "ISSUE", o))
        if o["returned_on"] <= t:
            events.append((o["returned_on"], 1, "RETURN", o))
    events.sort(key=lambda e: (e[0], e[1], e[3]["order_id"]))

    from .agents import settlement

    due_settlements: list[tuple[str, dict]] = []

    def flush(until: str) -> None:
        due_settlements.sort(key=lambda s: (s[0], s[1]["order_id"]))
        while due_settlements and due_settlements[0][0] <= until:
            paid_on, draft = due_settlements.pop(0)
            ledger.record_both("SETTLEMENT", draft, paid_on)

    for day, _, kind, o in events:
        flush(day)
        if kind == "ISSUE":
            ledger.record_both("ISSUE", {k: o[k] for k in (
                "order_id", "karigar_id", "karigar_name", "item", "karat", "issued_g", "issued_on",
                "due_date", "occasion_date", "agreed_wastage_pct", "labour_inr")}, day)
        else:
            ledger.record_both("RETURN", {"order_id": o["order_id"], "karigar_id": o["karigar_id"],
                                          "piece_g": o["piece_g"], "scrap_g": o["scrap_g"], "date": day}, day)
            current = ks.orders()[o["order_id"]]
            check = wastage_guard.check(current, ks.history_excess(o["karigar_id"], exclude=o["order_id"]))
            if check["flag"]:
                ks._alert("WASTAGE", o["order_id"], check["message"], day, excess_g=check["excess_g"])
            elif o["ks_paid_on"] <= t:
                draft = settlement.draft(current, ks.karigars[o["karigar_id"]], o["ks_paid_on"])
                due_settlements.append((o["ks_paid_on"], draft))
    flush(t)
    ks.daily_check(today)
    return ks
