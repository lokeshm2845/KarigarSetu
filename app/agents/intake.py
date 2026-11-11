"""Intake Agent: turns a (transcribed) voice note or typed message into a structured ledger entry.

Handles transliterated Kannada and Hindi as well as English, for example:
    "Ravi ge 42.350 gram 22 carat, haar, 15 December"
    "Suresh ko 3 tola 916 kangan dena hai, 20 Nov tak"
    "Ravi returned A001 39.700 g, scrap 0.200 g"

Rule-based first (fast, offline, predictable). If required fields are still missing
and a Lyzr agent is configured, the Lyzr agent is asked to fill the gaps.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from .. import config

TOLA_G = 11.6638

MONTHS = {
    "jan": 1, "january": 1, "janavari": 1, "janvari": 1,
    "feb": 2, "february": 2, "farvari": 2, "pebravari": 2,
    "mar": 3, "march": 3, "marc": 3, "maarch": 3,
    "apr": 4, "april": 4, "epril": 4,
    "may": 5, "mei": 5, "mey": 5,
    "jun": 6, "june": 6, "joon": 6,
    "jul": 7, "july": 7, "julai": 7,
    "aug": 8, "august": 8, "agast": 8,
    "sep": 9, "sept": 9, "september": 9, "sitambar": 9,
    "oct": 10, "october": 10, "aktubar": 10, "aktobar": 10,
    "nov": 11, "november": 11, "navambar": 11, "navembar": 11,
    "dec": 12, "december": 12, "disambar": 12, "disembar": 12,
}

ITEMS = {
    "haar": "haar", "haara": "haar", "necklace": "haar", "har": "haar", "nekles": "haar",
    "chain": "chain", "sara": "chain", "sarra": "chain", "chen": "chain",
    "bangle": "bangle", "bangles": "bangle", "bale": "bangle", "kangan": "bangle", "kada": "bangle", "chudi": "bangle",
    "ring": "ring", "ungura": "ring", "ungara": "ring", "anguthi": "ring", "angoothi": "ring",
    "jhumka": "jhumka", "jhumki": "jhumka", "earring": "jhumka", "earrings": "jhumka", "oole": "jhumka", "bugadi": "jhumka",
    "mangalsutra": "mangalsutra", "taali": "mangalsutra", "thali": "mangalsutra", "tali": "mangalsutra",
}

HALLMARK_TO_KARAT = {"916": 22, "750": 18, "585": 14, "999": 24, "958": 23}

RETURN_WORDS = ("returned", "return", "vapas", "wapas", "waapas", "kottiddane", "kottidde", "kottide",
                "thandiddane", "tandiddane", "jama", "submitted", "delivered")
SCRAP_WORDS = ("scrap", "bura", "burada", "dust", "kachra", "jhaad", "polish", "lemel", "filing")
TOMORROW_WORDS = ("tomorrow", "naale", "nale", "kal")

_NUM = r"(\d+(?:\.\d+)?)"
WEIGHT_RE = re.compile(_NUM + r"\s*(grams|gram|gms|gm|g|grm|ग्राम|ಗ್ರಾಂ|tola|tolas)\b", re.I)
KARAT_RE = re.compile(r"\b(\d{2})\s*(?:k|kt|karat|carat|caret|ct|कैरेट|ಕ್ಯಾರೆಟ್)\b", re.I)
HALLMARK_RE = re.compile(r"\b(916|750|585|999|958)\b")
ORDER_RE = re.compile(r"#?\b([A-Z]\d{3})\b", re.I)
DAY_MONTH_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\b", re.I)
MONTH_DAY_RE = re.compile(r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
IN_DAYS_RE = re.compile(r"\b(?:in\s+)?(\d{1,2})\s*(?:days|din|dina|dinadalli|dinon)\b", re.I)


def _next_date(day: int, month: int, today: date, year: int | None = None) -> date | None:
    try:
        if year:
            return date(year if year > 100 else 2000 + year, month, day)
        d = date(today.year, month, day)
        return d if d >= today else date(today.year + 1, month, day)
    except ValueError:
        return None


def _find_karigar(text: str, karigar_names: list[str]) -> str | None:
    low = text.lower()
    for name in sorted(karigar_names, key=len, reverse=True):
        # prefix match so that Kannada "Ravige" / Hindi "Ravi ko" both work
        if re.search(r"\b" + re.escape(name.lower()), low):
            return name
    return None


def _find_date(text: str, today: date) -> date | None:
    low = text.lower()
    for m in DAY_MONTH_RE.finditer(low):
        if m.group(2) in MONTHS:
            return _next_date(int(m.group(1)), MONTHS[m.group(2)], today)
    for m in MONTH_DAY_RE.finditer(low):
        if m.group(1) in MONTHS:
            return _next_date(int(m.group(2)), MONTHS[m.group(1)], today)
    m = NUMERIC_DATE_RE.search(low)
    if m:
        year = int(m.group(3)) if m.group(3) else None
        return _next_date(int(m.group(1)), int(m.group(2)), today, year)
    m = IN_DAYS_RE.search(low)
    if m:
        return today + timedelta(days=int(m.group(1)))
    if any(re.search(r"\b" + w + r"\b", low) for w in TOMORROW_WORDS):
        return today + timedelta(days=1)
    return None


def _weights(text: str) -> list[tuple[float, int, bool]]:
    """Returns (grams, position, is_scrap) for every weight mentioned."""
    out = []
    low = text.lower()
    prev_end = 0
    for m in WEIGHT_RE.finditer(low):
        value = float(m.group(1))
        unit = m.group(2).lower()
        grams = round(value * TOLA_G, 3) if unit.startswith("tola") else value
        # "scrap 0.200 g" (word before, since the previous weight) or "0.200 g scrap" (word right after,
        # before any comma or next number) both mark scrap.
        before = low[max(prev_end, m.start() - 20): m.start()]
        after = re.split(r"[,;\d]", low[m.end(): m.end() + 12], maxsplit=1)[0]
        is_scrap = any(w in before or w in after for w in SCRAP_WORDS)
        out.append((grams, m.start(), is_scrap))
        prev_end = m.end()
    return out


def parse(text: str, karigar_names: list[str], today: date, default_karigar: str | None = None) -> dict:
    low = text.lower()
    result: dict = {"raw": text, "source": "rules"}

    is_return = any(re.search(r"\b" + w, low) for w in RETURN_WORDS)
    weights = _weights(text)
    result["intent"] = "RETURN" if is_return else ("ISSUE" if weights else "UNKNOWN")

    result["karigar"] = _find_karigar(text, karigar_names) or default_karigar

    item = None
    for word in re.findall(r"[a-z]+", low):
        if word in ITEMS:
            item = ITEMS[word]
            break
    result["item"] = item

    m = ORDER_RE.search(text)
    result["order_ref"] = m.group(1).upper() if m else None

    if result["intent"] == "RETURN":
        pieces = [w for w in weights if not w[2]]
        scraps = [w for w in weights if w[2]]
        result["piece_g"] = round(pieces[0][0], 3) if pieces else 0.0
        result["scrap_g"] = round(sum(s[0] for s in scraps), 3)
        missing = []
        if not (result["karigar"] or result["order_ref"]):
            missing.append("karigar")
        if not pieces and not scraps:
            missing.append("weight")
    else:
        result["weight_g"] = round(weights[0][0], 3) if weights else None
        karat = None
        km = KARAT_RE.search(text)
        if km and 8 <= int(km.group(1)) <= 24:
            karat = int(km.group(1))
        else:
            hm = HALLMARK_RE.search(text)
            if hm:
                karat = HALLMARK_TO_KARAT[hm.group(1)]
        result["karat"] = karat
        due = _find_date(text, today)
        result["due_date"] = due.isoformat() if due else None
        missing = [f for f, v in (("karigar", result["karigar"]), ("weight", result["weight_g"]),
                                  ("karat", karat), ("item", item), ("due_date", due)) if not v]

    result["missing"] = missing

    if missing and config.LYZR_API_KEY and config.LYZR_AGENT_ID:
        from .lyzr_client import extract_fields
        llm = extract_fields(text, karigar_names, today)
        if llm:
            for k, v in llm.items():
                if result.get(k) in (None, 0.0) and v not in (None, ""):
                    result[k] = v
            result["missing"] = [f for f in missing if not result.get(_FIELD_KEY.get(f, f))]
            result["source"] = "rules+lyzr"
    return result


_FIELD_KEY = {"weight": "weight_g"}

_QUESTIONS = {
    "karigar": "Which karigar is this for?",
    "weight": "How many grams? (you can also send a photo of the scale)",
    "karat": "What purity: 22K (916) or 18K (750)?",
    "item": "What piece is it (haar, chain, bangle, ring, jhumka, mangalsutra)?",
    "due_date": "By which date is it needed?",
}


def followup_question(parsed: dict) -> str:
    asks = [_QUESTIONS[f] for f in parsed.get("missing", []) if f in _QUESTIONS]
    return "I need a little more detail: " + " ".join(asks) if asks else "Could you say that again?"
