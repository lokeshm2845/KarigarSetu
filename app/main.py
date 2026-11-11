"""FastAPI server: REST API for the agents + the jeweller dashboard + a WhatsApp chat simulator.

Run:  uvicorn app.main:app --reload   then open http://127.0.0.1:8000
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config
from .agents import refinery
from .seed import build_app_state

WEB = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title="KarigarSetu", version="0.1.0",
              description="Agentic two-party gold job-work ledger (prototype, simulated data).")
STATE = {"ks": build_app_state(config.DEMO_TODAY, config.DB_PATH), "today": config.DEMO_TODAY}


def ks():
    return STATE["ks"]


class Message(BaseModel):
    role: str            # "jeweller" or "karigar"
    sender_id: str       # "J01" or a karigar id such as "K01"
    text: str
    today: date | None = None


class Reply(BaseModel):
    party: str           # "jeweller" or "karigar"
    pending_id: int
    text: str
    today: date | None = None


class Reconcile(BaseModel):
    recovered_pure_g: float


@app.get("/")
def dashboard():
    return FileResponse(WEB / "index.html")


@app.get("/api/summary")
def summary():
    orders = list(ks().orders().values())
    open_orders = [o for o in orders if o["status"] == "WITH_KARIGAR"]
    return {
        "today": STATE["today"].isoformat(),
        "jeweller": ks().jeweller,
        "orders_total": len(orders),
        "orders_open": len(open_orders),
        "gold_with_karigars_g": round(sum(o["issued_g"] for o in open_orders), 3),
        "awaiting_settlement": sum(1 for o in orders if o["status"] == "RETURNED"),
        "open_alerts": sum(1 for a in ks().alerts if a["open"]),
        "ledger": ks().ledger.verify(),
        "simulated": True,
    }


@app.get("/api/karigars")
def karigars():
    return [{**{k: v for k, v in kg.items() if k not in ("speed", "honesty")}, "trust": ks().trust(kg["id"])}
            for kg in ks().karigars.values()]


@app.get("/api/orders")
def orders(status: str | None = None):
    rows = sorted(ks().orders().values(), key=lambda o: o["issued_on"], reverse=True)
    return [o for o in rows if not status or o["status"] == status]


@app.get("/api/alerts")
def alerts(open_only: bool = True):
    return [a for a in reversed(ks().alerts) if a["open"] or not open_only]


@app.get("/api/pending")
def pending():
    return ks().ledger.pending()


@app.get("/api/ledger")
def ledger(limit: int = 50):
    return ks().ledger.entries()[-limit:][::-1]


@app.get("/api/ledger/verify")
def verify():
    return ks().ledger.verify()


@app.get("/api/trust/{karigar_id}")
def trust(karigar_id: str):
    if karigar_id not in ks().karigars:
        raise HTTPException(404, "unknown karigar")
    return ks().trust(karigar_id)


@app.post("/api/message")
def message(m: Message):
    if m.role not in ("jeweller", "karigar"):
        raise HTTPException(400, "role must be jeweller or karigar")
    return ks().handle_message(m.role, m.sender_id, m.text, m.today or STATE["today"])


@app.post("/api/reply")
def reply(r: Reply):
    return ks().handle_reply(r.party, r.pending_id, r.text, r.today or STATE["today"])


@app.post("/api/orders/{order_id}/accept-wastage")
def accept_wastage(order_id: str):
    if order_id not in ks().orders():
        raise HTTPException(404, "unknown order")
    return ks().accept_flag(order_id, STATE["today"])


@app.post("/api/refinery/reconcile")
def reconcile(r: Reconcile):
    done = [o for o in ks().orders().values() if o.get("returned_on")]
    return refinery.reconcile(done, r.recovered_pure_g)


@app.post("/api/demo/reset")
def reset():
    STATE["ks"] = build_app_state(STATE["today"], config.DB_PATH)
    return {"ok": True}
