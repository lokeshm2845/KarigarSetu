"""Central configuration. All values can be overridden with environment variables."""
import os
from datetime import date

# Simulated gold rate used for rupee conversions (NOT a live rate).
GOLD_RATE_INR_PER_G = float(os.getenv("GOLD_RATE_INR_PER_G", "7400"))

# A return is flagged when loss exceeds the agreed wastage by more than this many percentage points.
WASTAGE_TOLERANCE_PP = float(os.getenv("WASTAGE_TOLERANCE_PP", "0.25"))

# Deadline agent warns this many days before the due date at the latest.
DEADLINE_WARN_DAYS = int(os.getenv("DEADLINE_WARN_DAYS", "3"))

DB_PATH = os.getenv("KARIGARSETU_DB", ":memory:")

# "Today" for the demo. The simulated dataset covers orders issued Aug-Oct 2026, so the default
# replays it up to 20 Oct 2026, leaving some orders still with karigars. Override with DEMO_TODAY.
DEMO_TODAY = date.fromisoformat(os.getenv("DEMO_TODAY", "2026-10-20"))

# Optional Lyzr agent used as a fallback when the rule-based intake cannot parse a message.
LYZR_API_KEY = os.getenv("LYZR_API_KEY", "")
LYZR_AGENT_ID = os.getenv("LYZR_AGENT_ID", "")
LYZR_API_URL = os.getenv("LYZR_API_URL", "https://agent-prod.studio.lyzr.ai/v3/inference/chat/")

# Design categories: agreed wastage %, typical working days, labour (INR per gram).
CATEGORIES = {
    "chain":       {"agreed_wastage_pct": 2.5, "base_days": 6,  "labour_per_g": 90},
    "bangle":      {"agreed_wastage_pct": 2.5, "base_days": 8,  "labour_per_g": 110},
    "ring":        {"agreed_wastage_pct": 3.0, "base_days": 4,  "labour_per_g": 180},
    "haar":        {"agreed_wastage_pct": 3.0, "base_days": 12, "labour_per_g": 150},
    "mangalsutra": {"agreed_wastage_pct": 3.0, "base_days": 8,  "labour_per_g": 120},
    "jhumka":      {"agreed_wastage_pct": 4.0, "base_days": 7,  "labour_per_g": 200},
}
