"""Generates the SIMULATED dataset used by the prototype.

Everything here is synthetic: a fictional small-town jeweller, 12 fictional karigars,
~3 months of job-work orders, seeded wastage anomalies, and 120 synthetic voice-note
transcripts. Ground-truth labels are stored so `scripts/evaluate.py` can score the agents.

Run:  python data/generate_dummy_data.py
"""
from __future__ import annotations

import calendar
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import CATEGORIES  # noqa: E402

SEED = 42
START, DAYS = date(2026, 8, 1), 92          # orders issued 1 Aug - 31 Oct 2026
N_ORDERS, N_ANOMALIES, N_VOICE = 186, 15, 120

JEWELLER = {"id": "J01", "name": "Sri Lakshmi Jewellers (fictional)", "town": "Tumakuru", "language": "kn"}

KARIGARS = [
    ("K01", "Ravi", "kn"), ("K02", "Manjunath", "kn"), ("K03", "Suresh", "kn"), ("K04", "Prakash", "kn"),
    ("K05", "Imran", "hi"), ("K06", "Venkatesh", "kn"), ("K07", "Gopal", "hi"), ("K08", "Shankar", "kn"),
    ("K09", "Anil", "hi"), ("K10", "Basavaraj", "kn"), ("K11", "Kiran", "kn"), ("K12", "Mahesh", "hi"),
]

WEIGHT_RANGE = {"chain": (10, 40), "bangle": (12, 45), "ring": (3, 10), "haar": (30, 80),
                "mangalsutra": (12, 35), "jhumka": (6, 18)}
ITEM_MIX = {"chain": 0.24, "bangle": 0.18, "ring": 0.20, "haar": 0.12, "mangalsutra": 0.12, "jhumka": 0.14}
ITEM_WORDS = {
    "kn": {"haar": "haara", "chain": "sara", "bangle": "bale", "ring": "ungura", "jhumka": "jhumki", "mangalsutra": "taali"},
    "hi": {"haar": "haar", "chain": "chain", "bangle": "kangan", "ring": "anguthi", "jhumka": "jhumka", "mangalsutra": "mangalsutra"},
    "en": {"haar": "necklace", "chain": "chain", "bangle": "bangle", "ring": "ring", "jhumka": "earrings", "mangalsutra": "mangalsutra"},
}
MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def build() -> dict:
    rng = random.Random(SEED)

    karigars = []
    for i, (kid, name, lang) in enumerate(KARIGARS):
        slow = kid in ("K07", "K11")
        karigars.append({
            "id": kid, "name": name, "language": lang, "phone": f"+91-90000-000{i + 1:02d}",
            "upi_id": f"{name.lower()}.karigar@exampleupi",
            "speed": round(rng.uniform(1.35, 1.6) if slow else rng.uniform(0.8, 1.15), 2),
            "honesty": round(rng.uniform(0.6, 0.92), 2),
        })

    orders = []
    items, weights = list(ITEM_MIX), list(ITEM_MIX.values())
    for n in range(N_ORDERS):
        k = rng.choice(karigars)
        item = rng.choices(items, weights)[0]
        cat = CATEGORIES[item]
        issued_on = START + timedelta(days=rng.randrange(DAYS))
        issued_g = round(rng.uniform(*WEIGHT_RANGE[item]), 3)
        window = math.ceil(cat["base_days"] * 1.15) + rng.randint(1, 4)
        due = issued_on + timedelta(days=window)
        occasion = (due + timedelta(days=rng.randint(2, 7))).isoformat() if rng.random() < 0.35 else None
        actual_days = max(1, round(cat["base_days"] * k["speed"] * rng.uniform(0.85, 1.3)))
        returned_on = issued_on + timedelta(days=actual_days)

        loss_pct = cat["agreed_wastage_pct"] * k["honesty"] * rng.uniform(0.85, 1.12)
        scrap_g = round(issued_g * rng.uniform(0.003, 0.008), 3)
        orders.append({
            "order_id": f"A{n + 1:03d}", "karigar_id": k["id"], "karigar_name": k["name"],
            "item": item, "karat": rng.choices([22, 18], [0.8, 0.2])[0],
            "issued_g": issued_g, "issued_on": issued_on.isoformat(), "due_date": due.isoformat(),
            "occasion_date": occasion, "agreed_wastage_pct": cat["agreed_wastage_pct"],
            "labour_inr": int(round(issued_g * cat["labour_per_g"], -2)),
            "returned_on": returned_on.isoformat(), "scrap_g": scrap_g,
            "_loss_pct": loss_pct, "truth_anomaly": False, "truth_late": returned_on > due,
        })

    # Seed anomalies: 11 clear (+0.6 to +3.0 points) and 4 subtle (+0.2 to +0.45 points).
    for i, o in enumerate(rng.sample(orders, N_ANOMALIES)):
        o["_loss_pct"] = o["agreed_wastage_pct"] + (rng.uniform(0.6, 3.0) if i < 11 else rng.uniform(0.2, 0.45))
        o["truth_anomaly"] = True

    for o in orders:
        loss_g = o["issued_g"] * o.pop("_loss_pct") / 100
        o["piece_g"] = round(o["issued_g"] - loss_g - o["scrap_g"], 3)
        ret = date.fromisoformat(o["returned_on"])
        # Baseline: settled at month end, then a few days to reconcile the notebook.
        o["baseline_paid_on"] = (month_end(ret) + timedelta(days=rng.randint(3, 12))).isoformat()
        # KarigarSetu: both parties approve the draft, then pay by UPI link.
        o["ks_paid_on"] = (ret + timedelta(days=rng.randint(0, 2) + rng.randint(0, 2))).isoformat()

    voice = build_voice_notes(rng, orders, karigars)
    return {"_note": "SIMULATED DATA. Fictional jeweller and karigars, generated with seed 42.",
            "jeweller": JEWELLER, "karigars": karigars, "orders": orders, "voice_notes": voice}


def build_voice_notes(rng: random.Random, orders: list[dict], karigars: list[dict]) -> list[dict]:
    notes = []
    sample = rng.sample(orders, N_VOICE)
    for i, o in enumerate(sample):
        today = date.fromisoformat(o["issued_on"])
        due = date.fromisoformat(o["due_date"])
        name, w, kt, item = o["karigar_name"], o["issued_g"], o["karat"], o["item"]
        mon = MONTH_NAMES[due.month]
        style = rng.choice(["kn", "kn2", "hi", "hi_tola", "en", "kn_916"])
        noise = rng.random()
        expected = {"karigar": name, "weight_g": w, "karat": kt, "item": item, "due_date": due.isoformat()}

        if style == "kn":
            text = f"{name} ge {w:.3f} gram {kt} carat, {ITEM_WORDS['kn'][item]}, {due.day} {mon}"
        elif style == "kn2":
            text = f"{name}ge {w:.2f}g {kt}k {ITEM_WORDS['kn'][item]} kodi, {due.day} {mon[:3]} olage beku"
            expected["weight_g"] = round(w, 2)
        elif style == "kn_916":
            hm = {22: "916", 18: "750"}[kt]
            text = f"{name} ge {w:.3f} gram {hm} {ITEM_WORDS['kn'][item]}, {due.day} {mon} ge beku"
        elif style == "hi":
            text = f"{name} ko {w:.3f} gram {kt} carat ka {ITEM_WORDS['hi'][item]} dena hai, {due.day} {mon} tak"
        elif style == "hi_tola":
            tola = round(w / 11.6638, 1)
            text = f"{name} ko {tola} tola {kt} carat {ITEM_WORDS['hi'][item]}, {due.day} {mon[:3]} tak"
            expected["weight_g"] = round(tola * 11.6638, 3)
        else:
            text = f"Issue {w:.3f} g {kt}K {ITEM_WORDS['en'][item]} to {name}, due {due.day}/{due.month}"

        # ~12% realistic noise that the rules cannot handle without a follow-up question.
        if noise < 0.03:
            text = text.replace(f"{kt} carat", "").replace(f"{kt}k", "").replace(f"{kt}K", "")
            text = text.replace("916", "").replace("750", "")
            expected["note"] = "karat not mentioned"
        elif noise < 0.06:
            text = text.replace(name, name[:-1] + name[-1] * 2 + "u")
            expected["note"] = "name misheard by speech-to-text"
        elif noise < 0.09:
            text = text.split(",")[0]
            expected["note"] = "due date cut off"
        elif noise < 0.12:
            text = text.replace(f"{w:.3f} gram", "nalavattu eradu gram").replace(f"{w:.3f} g", "nalavattu g")
            expected["note"] = "weight spoken in words"

        notes.append({"id": f"V{i + 1:03d}", "spoken_on": today.isoformat(), "text": text, "expected": expected})
    return notes


if __name__ == "__main__":
    data = build()
    out = ROOT / "data" / "dummy_dataset.json"
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}: {len(data['karigars'])} karigars, {len(data['orders'])} orders, "
          f"{len(data['voice_notes'])} voice notes (SIMULATED).")
