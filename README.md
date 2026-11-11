# KarigarSetu

**An AI agent ledger for trusted gold job-work between jewellers and karigars.**

Tech4Bharat · GAVS 2026 · Theme: **Jeweltech** · Problem Statement **2.2**: *Gold given to karigars for job-work is tracked on trust, and disputes follow* (Agentic AI)

> ⚠️ **All data in this repository is simulated.** The jeweller and karigars are fictional, and the numbers come from a seeded synthetic dataset (`data/generate_dummy_data.py`, seed 42). They are not field results.

---

## The problem

Jewellers give gold to karigars (artisan goldsmiths) by weight and get finished pieces back after an agreed wastage. Today this is tracked in notebooks and on slips, wastage is agreed verbally, deadlines are chased by phone, and accounts are only squared up at month end. The result is unexplained gold losses, disputes, missed wedding dates, and karigars waiting weeks to be paid.

## The solution

One **two-party gold ledger** that both sides confirm, kept by **seven AI agents** and used over WhatsApp with voice notes in Kannada, Hindi or English.

| Agent | What it does | Code |
|---|---|---|
| Intake | Turns a voice-note transcript or text ("Ravi ge 42.350 gram 22 carat, haar, 15 December") into a structured entry. Understands tola, hallmark codes (916/750) and local item names. Asks a follow-up when something is missing. Can fall back to a Lyzr agent. | `app/agents/intake.py` |
| Consent | Sends each entry to the other party and understands replies such as "Sari", "Haan", "OK" and "illa". | `app/agents/consent.py` |
| Wastage Guard | Checks every return against the agreed wastage and the karigar's own history, and flags it straight away. | `app/agents/wastage_guard.py` |
| Deadline | Predicts the finish date from the karigar's track record and warns early when a wedding-date order is at risk. | `app/agents/deadline.py` |
| Settlement | Drafts the gold and labour settlement on delivery, plus a UPI payment link. Both parties must approve it. | `app/agents/settlement.py` |
| Refinery Recon | Matches pure gold recovered from workshop scrap against what the ledger expects. | `app/agents/refinery.py` |
| Trust Profile | Builds a verified record for each karigar (on-time rate, wastage accuracy) that the karigar owns. | `app/agents/trust_profile.py` |

**The ledger** (`app/ledger.py`): every entry is a pending proposal until **both** jeweller and karigar approve it. Approved entries are appended to a SHA-256 hash chain, so any later edit breaks the chain and `verify()` reports where. SQLite triggers also block UPDATE/DELETE on the chain.

**People decide.** Agents flag problems and draft settlements; nothing is settled without both approvals, and the AI never assigns blame.

## Architecture

```
WhatsApp / voice / scale photo ─┐
Jeweller web dashboard ─────────┼─> FastAPI (app/main.py)
                                │        │
                                │   Orchestrator (app/orchestrator.py)
                                │        │
        Intake · Consent · Wastage Guard · Deadline · Settlement · Refinery · Trust Profile
                                │        │
                                │   Two-party hash-chained ledger (app/ledger.py, SQLite)
                                └── Optional: Lyzr agent for hard-to-parse messages (app/agents/lyzr_client.py)
```

The prototype uses SQLite and a browser-based WhatsApp simulator. The production plan uses PostgreSQL, the WhatsApp Business Cloud API, and Indian-language speech-to-text (Bhashini / IndicWhisper) in front of the Intake Agent.

## Quick start

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python data/generate_dummy_data.py      # writes data/dummy_dataset.json (simulated)
uvicorn app.main:app --reload           # open http://127.0.0.1:8000
```

The dashboard shows gold currently with karigars, agent alerts, karigar trust profiles and the hash-chained ledger. It also has a **WhatsApp simulator**: send an issue as the jeweller, confirm it as the karigar, and watch it lock.

The demo date defaults to **20 Oct 2026**, so some simulated orders are still open. Change it with `DEMO_TODAY=2026-10-25`.

### Command-line demo of one order

```bash
python scripts/run_demo.py
```

It walks through: a voice-note issue → the karigar confirms → a return with **5.8% loss vs 3.0% agreed is flagged** → extra scrap is returned → a settlement is drafted (gold balance +0.079 g, labour ₹6,400, pay ₹5,815) → both approve and a UPI link is sent → the chain is verified → a direct database edit is detected.

### Evaluate on the simulated dataset

```bash
python scripts/evaluate.py      # writes data/results.json
```

| Measure (SIMULATED) | Notebook today | With KarigarSetu |
|---|---|---|
| Wastage anomalies caught at return (15 seeded) | found only at month end | **14 of 15**, 0 false flags |
| Late orders warned 3+ days ahead | not tracked | **12 of 18** (11 false alarms) |
| Average karigar wait for payment after delivery | 22.1 days | **2.1 days** (modelled) |
| Voice-note transcripts parsed without a follow-up | n/a | **113 of 120 (94%)** |

The simulated dataset has 1 fictional jeweller, 12 karigars and 186 orders (4.19 kg of gold issued, Aug–Oct 2026). Baseline: 3.6 g of gold lost above agreed wastage (≈ ₹26,700 at an assumed ₹7,400/g), and 18 late orders (9.7%), 5 of them tied to a customer occasion. The 7 transcripts the Intake Agent could not parse are the deliberately noisy ones (weight spoken in words, due date cut off, purity missing). For each, it asks a follow-up question instead of guessing.

### Tests

```bash
python -m unittest discover -s tests -v
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/summary` | KPIs and ledger integrity |
| GET | `/api/orders?status=WITH_KARIGAR` | Orders (projected from the ledger) |
| GET | `/api/alerts` | Open wastage and deadline alerts |
| GET | `/api/karigars` | Karigars with trust profiles |
| GET | `/api/ledger`, `/api/ledger/verify` | Hash-chained entries, chain check |
| POST | `/api/message` | `{role, sender_id, text}`: a WhatsApp-style message into the Intake Agent |
| POST | `/api/reply` | `{party, pending_id, text}`: a confirmation reply to the Consent Agent |
| POST | `/api/orders/{id}/accept-wastage` | Jeweller accepts a reviewed flag and drafts the settlement |
| POST | `/api/refinery/reconcile` | `{recovered_pure_g}`: Refinery Recon Agent |

Interactive docs: http://127.0.0.1:8000/docs

## Optional: Lyzr agent

Copy `.env.example` to `.env` and set `LYZR_API_KEY` and `LYZR_AGENT_ID` (then export them, or load them in your shell). When the rule-based Intake Agent leaves fields missing, the message is sent to your Lyzr agent with the extraction prompt in `app/agents/lyzr_client.py`. Without keys, everything runs offline.

## Repository layout

```
app/
  agents/          seven agents + optional Lyzr client
  ledger.py        two-party, append-only, hash-chained ledger
  orchestrator.py  routes messages through agents and the ledger
  state.py         projects order state from ledger entries
  seed.py          replays the simulated dataset into a ledger
  main.py          FastAPI app
data/
  generate_dummy_data.py   simulated dataset generator (seed 42)
  dummy_dataset.json       generated data
  results.json             evaluation output
scripts/
  run_demo.py      end-to-end demo of one order
  evaluate.py      scores the agents on the simulated data
web/index.html     jeweller dashboard + WhatsApp simulator
tests/             unit and flow tests
```

## Roadmap

1. Field visits with jewellers and karigars to replace every simulated number.
2. Connect the WhatsApp Business Cloud API and Indian-language speech-to-text.
3. Pilot with one jeweller and their karigars through a wedding season.
4. With karigar consent, share verified work history with an NBFC partner for working-capital loans.

## Team

Team [Team name], [College name]. Built for Tech4Bharat, GAVS 2026.
