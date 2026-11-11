"""End-to-end demo of one order, printed as a WhatsApp-style conversation.

Issue by voice -> karigar confirms -> return with excess wastage is flagged ->
extra scrap returned -> settlement drafted -> both approve -> UPI link -> chain verified.
Uses illustrative data only.  Run:  python scripts/run_demo.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.ledger import Ledger  # noqa: E402
from app.orchestrator import KarigarSetu  # noqa: E402
from app.seed import load_dataset  # noqa: E402

data = load_dataset()
ks = KarigarSetu(Ledger(), data["jeweller"], data["karigars"])
NAMES = {data["jeweller"]["id"]: "Jeweller", **{k["id"]: k["name"] for k in data["karigars"]}}


def show(who: str, text: str) -> None:
    print(f"\n[{who}] {text}")


def replies(result: dict) -> None:
    for r in result.get("replies", []):
        print(f"   -> to {NAMES.get(r['to'], r['to'])}: {r['text']}")


print("=" * 78)
print("KarigarSetu demo (illustrative data)")
print("=" * 78)

day = date(2026, 11, 11)
msg = "Ravi ge 42.350 gram 22 carat, haar, 15 December"
show("Jeweller, voice note", msg)
r = ks.handle_message("jeweller", "J01", msg, day)
replies(r)
show("Ravi", "Sari")
replies(ks.handle_reply("karigar", r["pending_id"], "Sari", day))

day = date(2026, 12, 10)
msg = "Ravi returned A001 39.700 g, scrap 0.200 g"
show("Ravi", msg)
r = ks.handle_message("karigar", "K01", msg, day)
replies(r)
show("Jeweller", "OK")
replies(ks.handle_reply("jeweller", r["pending_id"], "OK", day))

day = date(2026, 12, 11)
msg = "Ravi returned A001 scrap 1.100 g"
show("Ravi, after review", msg)
r = ks.handle_message("karigar", "K01", msg, day)
replies(r)
show("Jeweller", "OK")
res = ks.handle_reply("jeweller", r["pending_id"], "OK", day)
replies(res)

pid = res["settlement_pending_id"]
show("Jeweller", "OK")
replies(ks.handle_reply("jeweller", pid, "OK", day))
show("Ravi", "Haan")
replies(ks.handle_reply("karigar", pid, "Haan", day))

print("\n" + "-" * 78)
v = ks.ledger.verify()
print(f"Ledger: {v['length']} entries, hash chain intact = {v['ok']}")
print("Trust profile:", ks.trust("K01")["message"])

# Tamper test: quietly change a locked weight and re-verify.
ks.ledger.conn.execute("DROP TRIGGER chain_no_update")
ks.ledger.conn.execute("UPDATE chain SET payload = replace(payload, '42.35', '40.35') WHERE seq = 1")
v = ks.ledger.verify()
print(f"After someone edits entry #1 directly in the database: intact = {v['ok']}, broken at entry #{v['broken_at']}")
