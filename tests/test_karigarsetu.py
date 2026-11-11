"""Unit tests. Run with:  python -m unittest discover -s tests   (or: pytest)"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents import consent, deadline, intake, settlement, wastage_guard  # noqa: E402
from app.ledger import Ledger  # noqa: E402
from app.orchestrator import KarigarSetu  # noqa: E402

TODAY = date(2026, 11, 11)
NAMES = ["Ravi", "Imran", "Prakash"]


class LedgerTests(unittest.TestCase):
    def test_entry_locks_only_after_both_parties_approve(self):
        lg = Ledger()
        pid = lg.propose("ISSUE", {"order_id": "A001", "karigar_id": "K01"}, "jeweller", TODAY)
        self.assertEqual(lg.entries(), [])
        self.assertIsNotNone(lg.approve(pid, "karigar", TODAY))
        self.assertEqual(len(lg.entries()), 1)

    def test_tampering_is_detected(self):
        lg = Ledger()
        lg.record_both("ISSUE", {"order_id": "A001", "issued_g": 42.35}, TODAY)
        lg.record_both("ISSUE", {"order_id": "A002", "issued_g": 10.0}, TODAY)
        self.assertTrue(lg.verify()["ok"])
        lg.conn.execute("DROP TRIGGER chain_no_update")
        lg.conn.execute("UPDATE chain SET payload = replace(payload, '42.35', '40.35') WHERE seq = 1")
        self.assertEqual(lg.verify()["broken_at"], 1)

    def test_chain_is_append_only(self):
        lg = Ledger()
        lg.record_both("ISSUE", {"order_id": "A001"}, TODAY)
        with self.assertRaises(Exception):
            lg.conn.execute("DELETE FROM chain")


class IntakeTests(unittest.TestCase):
    def test_kannada_issue(self):
        p = intake.parse("Ravi ge 42.350 gram 22 carat, haar, 15 December", NAMES, TODAY)
        self.assertEqual((p["intent"], p["karigar"], p["weight_g"], p["karat"], p["item"], p["due_date"]),
                         ("ISSUE", "Ravi", 42.35, 22, "haar", "2026-12-15"))

    def test_hindi_tola_and_hallmark(self):
        p = intake.parse("Imran ko 2 tola 916 kangan dena hai, 5 Dec tak", NAMES, TODAY)
        self.assertEqual((p["weight_g"], p["karat"], p["item"]), (23.328, 22, "bangle"))

    def test_return_separates_piece_and_scrap(self):
        p = intake.parse("Ravi returned A001 39.700 g, scrap 0.200 g", NAMES, TODAY)
        self.assertEqual((p["intent"], p["order_ref"], p["piece_g"], p["scrap_g"]), ("RETURN", "A001", 39.7, 0.2))

    def test_missing_fields_trigger_followup(self):
        p = intake.parse("Issue 6.2 g ring to Prakash", NAMES, TODAY)
        self.assertIn("karat", p["missing"])
        self.assertIn("due_date", p["missing"])
        self.assertIn("purity", intake.followup_question(p))


class AgentTests(unittest.TestCase):
    ORDER = {"order_id": "A001", "karigar_id": "K01", "item": "haar", "karat": 22, "issued_g": 42.35,
             "issued_on": "2026-11-11", "due_date": "2026-12-15", "agreed_wastage_pct": 3.0, "labour_inr": 6400}

    def test_wastage_flagged_and_cleared(self):
        flagged = wastage_guard.check({**self.ORDER, "returned_g": 39.7, "scrap_g": 0.2})
        self.assertTrue(flagged["flag"])
        self.assertAlmostEqual(flagged["excess_g"], 1.18, places=2)
        ok = wastage_guard.check({**self.ORDER, "returned_g": 39.7, "scrap_g": 1.3})
        self.assertFalse(ok["flag"])

    def test_settlement_deducts_excess_gold(self):
        d = settlement.draft({**self.ORDER, "returned_g": 39.7, "scrap_g": 1.3}, {"name": "Ravi"}, "2026-12-11")
        self.assertAlmostEqual(d["gold_balance_g"], 0.079, places=3)
        self.assertEqual(d["net_payable_inr"], 6400 - d["gold_adjust_inr"])
        self.assertTrue(d["upi_link"].startswith("upi://pay?"))

    def test_deadline_uses_karigar_history(self):
        slow = deadline.assess(self.ORDER | {"due_date": "2026-11-25"}, TODAY, [1.5, 1.6, 1.4])
        self.assertEqual(slow["status"], "AT_RISK")
        fast = deadline.assess(self.ORDER | {"due_date": "2026-11-25"}, TODAY, [0.9, 1.0, 0.95])
        self.assertEqual(fast["status"], "ON_TRACK")

    def test_consent_understands_local_replies(self):
        for yes in ("Sari", "haan", "OK", "ಸರಿ", "👍"):
            self.assertTrue(consent.interpret(yes), yes)
        for no in ("illa", "nahi", "No"):
            self.assertFalse(consent.interpret(no), no)
        self.assertIsNone(consent.interpret("hmm"))


class FlowTest(unittest.TestCase):
    def test_full_order_flow(self):
        ks = KarigarSetu(Ledger(), {"id": "J01", "name": "Test Jeweller"},
                         [{"id": "K01", "name": "Ravi", "upi_id": "ravi@test"}])
        r = ks.handle_message("jeweller", "J01", "Ravi ge 42.350 gram 22 carat, haar, 15 December", TODAY)
        ks.handle_reply("karigar", r["pending_id"], "Sari", TODAY)
        r = ks.handle_message("karigar", "K01", "Ravi returned A001 39.700 g, scrap 0.200 g", TODAY)
        res = ks.handle_reply("jeweller", r["pending_id"], "OK", TODAY)
        self.assertTrue(res["wastage"]["flag"])
        r = ks.handle_message("karigar", "K01", "Ravi returned A001 scrap 1.100 g", TODAY)
        res = ks.handle_reply("jeweller", r["pending_id"], "OK", TODAY)
        pid = res["settlement_pending_id"]
        self.assertIsNone(ks.handle_reply("jeweller", pid, "OK", TODAY).get("entry"))
        done = ks.handle_reply("karigar", pid, "Haan", TODAY)
        self.assertEqual(done["status"], "LOCKED")
        self.assertEqual(ks.orders()["A001"]["status"], "SETTLED")
        self.assertTrue(ks.ledger.verify()["ok"])


if __name__ == "__main__":
    unittest.main()
