"""Scores the agents on the SIMULATED dataset and writes data/results.json.

These are results on synthetic, seeded data, not field results.
Run:  python scripts/evaluate.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.agents import deadline, intake, wastage_guard  # noqa: E402
from app.seed import load_dataset  # noqa: E402


def main() -> dict:
    data = load_dataset()
    orders = data["orders"]
    names = [k["name"] for k in data["karigars"]]

    # ------------------------------------------------------------ baseline costs
    total_g = sum(o["issued_g"] for o in orders)
    excess = []
    for o in orders:
        loss = o["issued_g"] - o["piece_g"] - o["scrap_g"]
        excess.append(max(0.0, loss - o["issued_g"] * o["agreed_wastage_pct"] / 100))
    gap_g = sum(excess)
    late = [o for o in orders if o["truth_late"]]
    late_occasion = [o for o in late if o["occasion_date"]]
    over_agreed = sum(1 for e in excess if e > 0)

    # -------------------------------------------------------------- wastage guard
    by_return = sorted(orders, key=lambda o: o["returned_on"])
    history: dict[str, list[float]] = {}
    tp = fp = 0
    for o in by_return:
        view = {**o, "returned_g": o["piece_g"]}
        res = wastage_guard.check(view, history.get(o["karigar_id"], []))
        if res["flag"] and o["truth_anomaly"]:
            tp += 1
        elif res["flag"]:
            fp += 1
        history.setdefault(o["karigar_id"], []).append(res["loss_pct"] - o["agreed_wastage_pct"])
    n_anom = sum(o["truth_anomaly"] for o in orders)

    # ------------------------------------------------------------- deadline agent
    warned_early = false_alarms = 0
    for o in orders:
        issued = date.fromisoformat(o["issued_on"])
        due = date.fromisoformat(o["due_date"])
        warn_by = due - timedelta(days=config.DEADLINE_WARN_DAYS)
        flagged = False
        day = issued
        while day <= warn_by:
            ratios = [(date.fromisoformat(h["returned_on"]) - date.fromisoformat(h["issued_on"])).days
                      / config.CATEGORIES[h["item"]]["base_days"]
                      for h in orders if h["karigar_id"] == o["karigar_id"] and h["returned_on"] < day.isoformat()]
            if deadline.assess(o | {"returned_on": None}, day, ratios)["status"] == "AT_RISK":
                flagged = True
                break
            day += timedelta(days=1)
        if flagged and o["truth_late"]:
            warned_early += 1
        elif flagged:
            false_alarms += 1

    # -------------------------------------------------------------- payment wait
    wait_base = mean((date.fromisoformat(o["baseline_paid_on"]) - date.fromisoformat(o["returned_on"])).days for o in orders)
    wait_ks = mean((date.fromisoformat(o["ks_paid_on"]) - date.fromisoformat(o["returned_on"])).days for o in orders)

    # ------------------------------------------------------------- intake agent
    ok = 0
    failures = []
    for v in data["voice_notes"]:
        p = intake.parse(v["text"], names, date.fromisoformat(v["spoken_on"]))
        e = v["expected"]
        good = (not p["missing"] and p["karigar"] == e["karigar"] and p["item"] == e["item"]
                and p["karat"] == e["karat"] and p["due_date"] == e["due_date"]
                and p["weight_g"] is not None and abs(p["weight_g"] - e["weight_g"]) < 0.01)
        ok += good
        if not good:
            failures.append({"id": v["id"], "text": v["text"], "missing": p["missing"], "note": e.get("note")})

    results = {
        "_note": "SIMULATED: results on seeded synthetic data, not field results.",
        "dataset": {"karigars": len(data["karigars"]), "orders": len(orders),
                    "gold_issued_kg": round(total_g / 1000, 2),
                    "period": f"{min(o['issued_on'] for o in orders)} to {max(o['issued_on'] for o in orders)}"},
        "baseline": {
            "unexplained_gold_gap_g": round(gap_g, 1),
            "unexplained_gold_gap_inr": round(gap_g * config.GOLD_RATE_INR_PER_G),
            "late_orders": len(late), "late_pct": round(100 * len(late) / len(orders), 1),
            "late_orders_with_occasion": len(late_occasion),
            "returns_over_agreed_wastage": over_agreed,
            "avg_payment_wait_days": round(wait_base, 1),
        },
        "with_karigarsetu": {
            "wastage_anomalies_caught_at_return": f"{tp} of {n_anom}",
            "wastage_false_flags": fp,
            "late_orders_warned_3plus_days_ahead": f"{warned_early} of {len(late)}",
            "deadline_false_alarms": false_alarms,
            "avg_payment_wait_days": round(wait_ks, 1),
            "voice_notes_parsed_without_followup": f"{ok} of {len(data['voice_notes'])} ({100 * ok / len(data['voice_notes']):.0f}%)",
        },
        "intake_failures": failures,
    }
    out = ROOT / "data" / "results.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return results


if __name__ == "__main__":
    r = main()
    print(json.dumps({k: v for k, v in r.items() if k != "intake_failures"}, indent=2, ensure_ascii=False))
    print(f"\nIntake failures: {len(r['intake_failures'])} (details in data/results.json)")
