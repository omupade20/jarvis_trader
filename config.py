"""
JARVIS CORE CONFIG
All system-wide constants, settings, and the Genesis Clock.
"""
import os
import json
import sqlite3
from datetime import datetime, date
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ── UPSTOX ─────────────────────────────────────────────────────────────────
UPSTOX_API_KEY      = os.getenv("UPSTOX_API_KEY", "")
UPSTOX_API_SECRET   = os.getenv("UPSTOX_API_SECRET", "")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:5000/callback")
UPSTOX_BASE_URL     = "https://api.upstox.com/v2"
IS_LIVE             = bool(UPSTOX_ACCESS_TOKEN)

# ── RISK & CAPITAL ──────────────────────────────────────────────────────────
# ── RISK & CAPITAL (INSTITUTIONAL CALIBRATION) ─────────────────────────────
MAX_CAPITAL          = 10000.0    # Rs. per trade
TARGET_GROSS_PCT     = 5.8        # Calibrated gross target (+5.8% sweet spot yields ~4.2%-4.5% net)
TARGET_NET_PCT       = 4.5        # Institutional net in-pocket yield target
TARGET_PCT           = 5.8        # Backward compatible alias for TARGET_GROSS_PCT
STOP_LOSS_ATR_MULT   = 1.5        # Dynamic ATR Multiplier (1.5x ATR14)
STOP_LOSS_MIN_PCT    = 2.5        # Guardrail floor: minimum stop distance (avoids intraday noise)
STOP_LOSS_MAX_PCT    = 4.5        # Guardrail ceiling: maximum allowable swing stop
STOP_LOSS_PCT        = 3.0        # Baseline default
MIN_CONVICTION_SCORE = 70         # Minimum score (0-100) to present a candidate
MAX_HOLD_DAYS        = 15         # 1-3 weeks maximum horizon (5-15 trading days)
STCG_TAX_PCT         = 20.0       # Indian Finance Act 2024 STCG Tax Rate (20%)         # 1-3 weeks maximum horizon (5-15 trading days)

# ── JARVIS VOICE ────────────────────────────────────────────────────────────
JARVIS_VOICE = os.getenv("JARVIS_VOICE", "en-GB-RyanNeural")
JARVIS_RATE  = "+0%"
JARVIS_PITCH = "-4Hz"

# ── PATHS ───────────────────────────────────────────────────────────────────
DB_PATH        = BASE_DIR / "jarvis_brain.db"
STATIC_DIR     = BASE_DIR / "static"
AUDIO_PATH     = STATIC_DIR / "briefing.mp3"
GENESIS_FILE   = BASE_DIR / "genesis.json"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# ── STOCK UNIVERSE (NSE Large-Cap only — no penny stocks) ──────────────────
# Symbol format for Upstox: NSE_EQ|SYMBOL
WATCHLIST = [
    {"symbol": "RELIANCE",    "name": "Reliance Industries",        "upstox": "NSE_EQ|RELIANCE",    "yf": "RELIANCE.NS"},
    {"symbol": "TCS",         "name": "Tata Consultancy Services",  "upstox": "NSE_EQ|TCS",         "yf": "TCS.NS"},
    {"symbol": "INFY",        "name": "Infosys Ltd",                "upstox": "NSE_EQ|INFY",        "yf": "INFY.NS"},
    {"symbol": "HDFCBANK",    "name": "HDFC Bank",                  "upstox": "NSE_EQ|HDFCBANK",    "yf": "HDFCBANK.NS"},
    {"symbol": "ICICIBANK",   "name": "ICICI Bank",                 "upstox": "NSE_EQ|ICICIBANK",   "yf": "ICICIBANK.NS"},
    {"symbol": "SBIN",        "name": "State Bank of India",        "upstox": "NSE_EQ|SBIN",        "yf": "SBIN.NS"},
    {"symbol": "BHARTIARTL",  "name": "Bharti Airtel",              "upstox": "NSE_EQ|BHARTIARTL",  "yf": "BHARTIARTL.NS"},
    {"symbol": "ITC",         "name": "ITC Limited",                "upstox": "NSE_EQ|ITC",         "yf": "ITC.NS"},
    {"symbol": "LT",          "name": "Larsen & Toubro",            "upstox": "NSE_EQ|LT",          "yf": "LT.NS"},
    {"symbol": "AXISBANK",    "name": "Axis Bank",                  "upstox": "NSE_EQ|AXISBANK",    "yf": "AXISBANK.NS"},
    {"symbol": "KOTAKBANK",   "name": "Kotak Mahindra Bank",        "upstox": "NSE_EQ|KOTAKBANK",   "yf": "KOTAKBANK.NS"},
    {"symbol": "TITAN",       "name": "Titan Company",              "upstox": "NSE_EQ|TITAN",       "yf": "TITAN.NS"},
    {"symbol": "BAJFINANCE",  "name": "Bajaj Finance",              "upstox": "NSE_EQ|BAJFINANCE",  "yf": "BAJFINANCE.NS"},
    {"symbol": "WIPRO",       "name": "Wipro Ltd",                  "upstox": "NSE_EQ|WIPRO",       "yf": "WIPRO.NS"},
    {"symbol": "TATAMOTORS",  "name": "Tata Motors",                "upstox": "NSE_EQ|TATAMOTORS",  "yf": "TATAMOTORS.NS"},
    {"symbol": "SUNPHARMA",   "name": "Sun Pharma",                 "upstox": "NSE_EQ|SUNPHARMA",   "yf": "SUNPHARMA.NS"},
    {"symbol": "TATASTEEL",   "name": "Tata Steel",                 "upstox": "NSE_EQ|TATASTEEL",   "yf": "TATASTEEL.NS"},
    {"symbol": "MARUTI",      "name": "Maruti Suzuki",              "upstox": "NSE_EQ|MARUTI",      "yf": "MARUTI.NS"},
    {"symbol": "NTPC",        "name": "NTPC Limited",               "upstox": "NSE_EQ|NTPC",        "yf": "NTPC.NS"},
    {"symbol": "POWERGRID",   "name": "Power Grid Corporation",     "upstox": "NSE_EQ|POWERGRID",   "yf": "POWERGRID.NS"},
    {"symbol": "ONGC",        "name": "Oil & Natural Gas Corp",     "upstox": "NSE_EQ|ONGC",        "yf": "ONGC.NS"},
    {"symbol": "COALINDIA",   "name": "Coal India Ltd",             "upstox": "NSE_EQ|COALINDIA",   "yf": "COALINDIA.NS"},
    {"symbol": "HINDUNILVR",  "name": "Hindustan Unilever",         "upstox": "NSE_EQ|HINDUNILVR",  "yf": "HINDUNILVR.NS"},
    {"symbol": "ADANIENT",    "name": "Adani Enterprises",          "upstox": "NSE_EQ|ADANIENT",    "yf": "ADANIENT.NS"},
    {"symbol": "ADANIPORTS",   "name": "Adani Ports",                "upstox": "NSE_EQ|ADANIPORTS",  "yf": "ADANIPORTS.NS"},
    {"symbol": "ULTRACEMCO",  "name": "UltraTech Cement",           "upstox": "NSE_EQ|ULTRACEMCO",  "yf": "ULTRACEMCO.NS"},
    {"symbol": "GRASIM",      "name": "Grasim Industries",          "upstox": "NSE_EQ|GRASIM",      "yf": "GRASIM.NS"},
    {"symbol": "HEROMOTOCO",  "name": "Hero MotoCorp",              "upstox": "NSE_EQ|HEROMOTOCO",  "yf": "HEROMOTOCO.NS"},
    {"symbol": "EICHERMOT",   "name": "Eicher Motors",              "upstox": "NSE_EQ|EICHERMOT",   "yf": "EICHERMOT.NS"},
    {"symbol": "NIFTYBEES",   "name": "Nifty 50 ETF",              "upstox": "NSE_EQ|NIFTYBEES",   "yf": "NIFTYBEES.NS"}
]


# ── GENESIS CLOCK ───────────────────────────────────────────────────────────
def get_genesis() -> dict:
    """Returns genesis info: start_date, day_number, maturity_level."""
    if GENESIS_FILE.exists():
        try:
            data = json.loads(GENESIS_FILE.read_text())
            start = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
            day_number = (date.today() - start).days + 1
            data["day_number"] = max(day_number, 1)
            data["maturity_level"] = _maturity(day_number)
            return data
        except Exception:
            pass

    # First ever run — initialize
    today = date.today().strftime("%Y-%m-%d")
    data = {"start_date": today, "day_number": 1, "maturity_level": "NEWBORN"}
    GENESIS_FILE.write_text(json.dumps(data, indent=2))
    return {**data}


def _maturity(days: int) -> str:
    if days <= 7:   return "NEWBORN"
    if days <= 30:  return "LEARNING"
    if days <= 90:  return "DEVELOPING"
    if days <= 180: return "EXPERIENCED"
    return "MASTER"
