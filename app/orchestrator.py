"""Orchestrator: routes WhatsApp-style messages through the seven agents and the two-party ledger.

Flow:  message -> Intake -> pending entry -> Consent (other party) -> locked in chain
       ISSUE locked  -> Deadline agent
       RETURN locked -> Wastage Guard -> (flag for review) or Settlement draft -> Consent -> locked
"""
from __future__ import annotations

from datetime import date

from . import config
from .agents import consent, deadline, intake, settlement, trust_profile, wastage_guard
from .ledger import Ledger
from .state import project_orders


class KarigarSetu:
    def __init__(self, ledger: Ledger, jeweller: dict, karigars: list[dict]):
        self.ledger = ledger
        self.jeweller = jeweller
        self.karigars = {k["id"]: k for k in karigars}
        self.alerts: list[dict] = []
        self.accepted_flags: set[str] = set()

    # ------------------------------------------------------------------ helpers
    def orders(self) -> dict[str, dict]:
        return project_orders(self.ledger.entries())

    def karigar_by_name(self, name: str | None) -> dict | None:
        if not name:
            return None
        for k in self.karigars.values():
            if k["name"].lower() == name.lower():
                return k
        return None

    def _next_order_id(self) -> str:
        nums = [int(oid[1:]) for oid in self.orders() if oid[1:].isdigit()]
        pend = [int(p["payload"]["order_id"][1:]) for p in self.ledger.pending()
                if p["entry_type"] == "ISSUE"]
        return f"A{max(nums + pend + [0]) + 1:03d}"

    def _done_orders(self, karigar_id: str, before: str | None = None, exclude: str | None = None) -> list[dict]:
        out = []
        for o in self.orders().values():
            if o["karigar_id"] != karigar_id or not o.get("returned_on") or o["order_id"] == exclude:
                continue
            if before and o["returned_on"] >= before:
                continue
            out.append(o)
        return sorted(out, key=lambda o: o["returned_on"])

    def history_excess(self, karigar_id: str, before: str | None = None, exclude: str | None = None) -> list[float]:
        return [o["loss_pct"] - o["agreed_wastage_pct"] for o in self._done_orders(karigar_id, before, exclude)]

    def history_speed(self, karigar_id: str, before: str | None = None) -> list[float]:
        ratios = []
        for o in self._done_orders(karigar_id, before):
            days = (date.fromisoformat(o["returned_on"]) - date.fromisoformat(o["issued_on"])).days
            ratios.append(days / config.CATEGORIES[o["item"]]["base_days"])
        return ratios

    def _alert(self, kind: str, order_id: str, message: str, on: str, **extra) -> dict:
        a = {"id": len(self.alerts) + 1, "kind": kind, "order_id": order_id, "message": message,
             "date": on, "open": True, **extra}
        self.alerts.append(a)
        return a

    def _party_id(self, party: str, karigar_id: str) -> str:
        return self.jeweller["id"] if party == "jeweller" else karigar_id

    # ----------------------------------------------------------------- messages
    def handle_message(self, role: str, sender_id: str, text: str, today: date) -> dict:
        """role = 'jeweller' or 'karigar'. Returns the parsed message and the replies to send."""
        default_k = self.karigars[sender_id]["name"] if role == "karigar" and sender_id in self.karigars else None
        parsed = intake.parse(text, [k["name"] for k in self.karigars.values()], today, default_k)
        if parsed["missing"] or parsed["intent"] == "UNKNOWN":
            return {"status": "NEED_INFO", "parsed": parsed,
                    "replies": [{"to": sender_id, "text": intake.followup_question(parsed)}]}

        if parsed["intent"] == "ISSUE":
            k = self.karigar_by_name(parsed["karigar"])
            cat = config.CATEGORIES[parsed["item"]]
            payload = {
                "order_id": self._next_order_id(),
                "karigar_id": k["id"], "karigar_name": k["name"],
                "item": parsed["item"], "karat": parsed["karat"],
                "issued_g": parsed["weight_g"], "issued_on": today.isoformat(),
                "due_date": parsed["due_date"], "occasion_date": None,
                "agreed_wastage_pct": cat["agreed_wastage_pct"],
                "labour_inr": int(round(parsed["weight_g"] * cat["labour_per_g"], -2)),
            }
            entry_type = "ISSUE"
        else:  # RETURN
            order = self._find_open_order(parsed)
            if order is None:
                return {"status": "NEED_INFO", "parsed": parsed,
                        "replies": [{"to": sender_id, "text": "Which order is this return for? Please share the order number, e.g. A001."}]}
            payload = {"order_id": order["order_id"], "karigar_id": order["karigar_id"],
                       "piece_g": parsed.get("piece_g", 0.0), "scrap_g": parsed.get("scrap_g", 0.0),
                       "date": today.isoformat()}
            entry_type = "RETURN"

        pid = self.ledger.propose(entry_type, payload, role, today)
        other = "karigar" if role == "jeweller" else "jeweller"
        return {"status": "PENDING_CONFIRMATION", "pending_id": pid, "entry_type": entry_type,
                "payload": payload, "parsed": parsed,
                "replies": [
                    {"to": sender_id, "text": f"Noted. {consent.describe(entry_type, payload)}. Sent to the {other} to confirm."},
                    {"to": self._party_id(other, payload["karigar_id"]),
                     "text": consent.confirmation_request(entry_type, payload, pid)},
                ]}

    def _find_open_order(self, parsed: dict) -> dict | None:
        orders = self.orders()
        if parsed.get("order_ref") and parsed["order_ref"] in orders:
            return orders[parsed["order_ref"]]
        k = self.karigar_by_name(parsed.get("karigar"))
        if not k:
            return None
        candidates = [o for o in orders.values() if o["karigar_id"] == k["id"] and o["status"] != "SETTLED"
                      and (not parsed.get("item") or o["item"] == parsed["item"])]
        return max(candidates, key=lambda o: o["issued_on"]) if candidates else None

    # -------------------------------------------------------------- confirmations
    def handle_reply(self, party: str, pending_id: int, text: str, today: date) -> dict:
        p = self.ledger.get_pending(pending_id)
        if p is None or p["status"] != "PENDING":
            return {"status": "NOT_OPEN", "replies": []}
        k_id = p["payload"]["karigar_id"]
        verdict = consent.interpret(text)
        if verdict is None:
            return {"status": "UNCLEAR", "replies": [{"to": self._party_id(party, k_id),
                                                      "text": "Please reply OK / Sari / Haan to confirm, or No to reject."}]}
        if verdict is False:
            self.ledger.reject(pending_id, party, text)
            msg = f"Entry P{pending_id} was not confirmed by the {party}. Please send the corrected details."
            return {"status": "REJECTED", "replies": [{"to": self.jeweller["id"], "text": msg}, {"to": k_id, "text": msg}]}

        locked = self.ledger.approve(pending_id, party, today)
        if locked is None:
            return {"status": "WAITING_OTHER_PARTY", "replies": []}
        return self._after_lock(locked, today)

    def _after_lock(self, entry: dict, today: date) -> dict:
        p = entry["payload"]
        k_id = p["karigar_id"]
        both = lambda text: [{"to": self.jeweller["id"], "text": text}, {"to": k_id, "text": text}]  # noqa: E731
        replies = both(f"Confirmed by both. Entry #{entry['seq']:04d} locked.")
        result = {"status": "LOCKED", "entry": entry, "replies": replies}

        if entry["entry_type"] == "ISSUE":
            o = self.orders()[p["order_id"]]
            d = deadline.assess(o, today, self.history_speed(k_id))
            result["deadline"] = d
            if d["status"] == "AT_RISK":
                self._alert("DEADLINE", o["order_id"], d["message"], today.isoformat())
                replies.append({"to": self.jeweller["id"], "text": d["message"]})

        elif entry["entry_type"] == "RETURN":
            result.update(self.review_return(p["order_id"], today))
            replies.extend(result.pop("review_replies"))

        elif entry["entry_type"] == "SETTLEMENT":
            for a in self.alerts:
                if a["order_id"] == p["order_id"] and a["kind"] == "WASTAGE":
                    a["open"] = False
            replies.append({"to": self.jeweller["id"],
                            "text": f"Pay ₹{p['net_payable_inr']:,} to {self.karigars[k_id]['name']}: {p['upi_link']}"})
        return result

    def review_return(self, order_id: str, today: date) -> dict:
        o = self.orders()[order_id]
        if not o.get("returned_on"):
            return {"review_replies": [{"to": self.jeweller["id"], "text": "Scrap recorded; waiting for the finished piece."}]}
        check = wastage_guard.check(o, self.history_excess(o["karigar_id"], exclude=order_id))
        out = {"wastage": check}
        if check["flag"] and order_id not in self.accepted_flags:
            self._alert("WASTAGE", order_id, check["message"], today.isoformat(), excess_g=check["excess_g"])
            out["review_replies"] = [{"to": self.jeweller["id"], "text": check["message"]},
                                     {"to": o["karigar_id"], "text": check["message"]}]
            return out
        out.update(self.propose_settlement(order_id, today))
        out["review_replies"] = [{"to": self.jeweller["id"], "text": check["message"]}] + out.pop("replies")
        return out

    def accept_flag(self, order_id: str, today: date) -> dict:
        """Jeweller accepts the excess after review; settlement goes ahead."""
        self.accepted_flags.add(order_id)
        return self.propose_settlement(order_id, today)

    def propose_settlement(self, order_id: str, today: date) -> dict:
        o = self.orders()[order_id]
        draft = settlement.draft(o, self.karigars[o["karigar_id"]], today.isoformat())
        pid = self.ledger.propose("SETTLEMENT", draft, "agent", today)
        text = consent.confirmation_request("SETTLEMENT", draft, pid)
        return {"settlement_pending_id": pid, "settlement": draft,
                "replies": [{"to": self.jeweller["id"], "text": text}, {"to": o["karigar_id"], "text": text}]}

    # -------------------------------------------------------------- daily checks
    def daily_check(self, today: date) -> list[dict]:
        out = []
        for o in self.orders().values():
            if o["status"] != "WITH_KARIGAR":
                continue
            d = deadline.assess(o, today, self.history_speed(o["karigar_id"], before=today.isoformat()))
            if d["status"] in ("AT_RISK", "OVERDUE"):
                already = any(a["order_id"] == o["order_id"] and a["kind"] == "DEADLINE" and a["open"] for a in self.alerts)
                if not already:
                    out.append(self._alert("DEADLINE", o["order_id"], d["message"], today.isoformat()))
        return out

    def trust(self, karigar_id: str) -> dict:
        k = self.karigars[karigar_id]
        return trust_profile.build(k, [o for o in self.orders().values() if o["karigar_id"] == karigar_id])
