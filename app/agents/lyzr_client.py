"""Optional Lyzr agent call, used only when the rule-based Intake Agent leaves fields missing.

Set LYZR_API_KEY and LYZR_AGENT_ID (see .env.example). Create the agent in Lyzr Studio with
an instruction like the PROMPT below. Without credentials this module is never called and
the prototype runs fully offline.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import date

from .. import config

PROMPT = (
    "You extract gold job-work entries for an Indian jeweller. The message may be in "
    "transliterated Kannada, Hindi or English. Reply with ONLY a JSON object with keys: "
    "intent (ISSUE or RETURN), karigar, weight_g (number, grams; 1 tola = 11.6638 g), "
    "karat (integer; 916=22, 750=18), item (one of haar, chain, bangle, ring, jhumka, mangalsutra), "
    "due_date (YYYY-MM-DD), piece_g, scrap_g. Use null when unknown. "
)


def extract_fields(text: str, karigar_names: list[str], today: date) -> dict | None:
    if not (config.LYZR_API_KEY and config.LYZR_AGENT_ID):
        return None
    message = (f"{PROMPT}Today is {today.isoformat()}. Known karigars: {', '.join(karigar_names)}.\n"
               f"Message: {text}")
    body = {"user_id": "karigarsetu-prototype", "agent_id": config.LYZR_AGENT_ID,
            "session_id": "karigarsetu-intake", "message": message}
    req = urllib.request.Request(
        config.LYZR_API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": config.LYZR_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    reply = data.get("response") if isinstance(data, dict) else None
    if not reply:
        return None
    m = re.search(r"\{.*\}", reply, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
