"""
JARVIS BRAIN — SQLite Memory, Learning, and Day Tracking
"""
import sqlite3
from datetime import datetime, date
from pathlib import Path
from config import DB_PATH


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    db = conn()
    cur = db.cursor()

    # Daily session log — every day JARVIS runs is recorded
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_date TEXT UNIQUE,
        day_number INTEGER,
        maturity_level TEXT,
        nifty_close REAL,
        nifty_change_pct REAL,
        india_vix REAL,
        portfolio_status TEXT,
        active_symbol TEXT,
        active_pnl_pct REAL,
        sentinel_action TEXT,
        candidate_symbol TEXT,
        candidate_score INTEGER,
        verdict TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # Every candidate JARVIS presents — tracked for learning
    cur.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        presented_date TEXT,
        symbol TEXT,
        name TEXT,
        entry_price REAL,
        target_price REAL,
        stop_price REAL,
        conviction_score INTEGER,
        rsi_at_entry REAL,
        vix_at_entry REAL,
        user_accepted INTEGER DEFAULT 0,   -- 1 if user said Yes
        entered_portfolio INTEGER DEFAULT 0, -- 1 if Upstox confirms it
        outcome TEXT DEFAULT 'PENDING',    -- WIN / LOSS / TIMEOUT
        outcome_price REAL,
        outcome_days INTEGER,
        outcome_pct REAL,
        lesson TEXT
    )""")

    # Evolving system wisdom — updated as outcomes come in
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wisdom (
        rule_key TEXT PRIMARY KEY,
        description TEXT,
        samples INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        confidence REAL DEFAULT 0.5,
        updated_at TEXT
    )""")

    db.commit()

    # Seed initial wisdom if first run
    cur.execute("SELECT COUNT(*) FROM wisdom")
    if cur.fetchone()[0] == 0:
        _seed_wisdom(cur)
        db.commit()

    db.close()


def _seed_wisdom(cur):
    now = date.today().isoformat()
    rules = [
        ("RSI_BELOW_35_LOW_VIX",  "RSI<35 + VIX<14 → strong mean-reversion bounce setup",   8, 7, 1, 0.875, now),
        ("EMA50_SUPPORT_BOUNCE",  "Price near 50 EMA in uptrend → high-probability entry",   6, 5, 1, 0.833, now),
        ("HIGH_VIX_NO_TRADE",     "VIX>19 → skip all trades regardless of RSI",              5, 5, 0, 1.000, now),
        ("BROAD_MARKET_DOWNTREND","Nifty below 200 EMA → no new buys",                       4, 4, 0, 1.000, now),
    ]
    cur.executemany("""
    INSERT OR IGNORE INTO wisdom (rule_key, description, samples, wins, losses, confidence, updated_at)
    VALUES (?,?,?,?,?,?,?)""", rules)


def log_session(day_number, maturity, regime, portfolio_status, active_symbol, active_pnl,
                sentinel_action, candidate_symbol, candidate_score, verdict):
    db = conn()
    today = date.today().isoformat()
    try:
        db.execute("""
        INSERT OR REPLACE INTO sessions
        (session_date, day_number, maturity_level, nifty_close, nifty_change_pct, india_vix,
         portfolio_status, active_symbol, active_pnl_pct, sentinel_action,
         candidate_symbol, candidate_score, verdict)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (today, day_number, maturity,
              regime.get("nifty_close"), regime.get("nifty_change_pct"), regime.get("india_vix"),
              portfolio_status, active_symbol, active_pnl,
              sentinel_action, candidate_symbol, candidate_score, verdict))
        db.commit()
    finally:
        db.close()


def record_prediction(symbol, name, entry, target, stop, score, rsi, vix):
    db = conn()
    today = date.today().isoformat()
    try:
        db.execute("""
        INSERT INTO predictions
        (presented_date, symbol, name, entry_price, target_price, stop_price,
         conviction_score, rsi_at_entry, vix_at_entry)
        VALUES (?,?,?,?,?,?,?,?,?)
        """, (today, symbol, name, entry, target, stop, score, rsi, vix))
        db.commit()
    finally:
        db.close()


def mark_user_accepted(symbol, presented_date):
    db = conn()
    db.execute("""
    UPDATE predictions SET user_accepted=1
    WHERE symbol=? AND presented_date=? AND outcome='PENDING'
    """, (symbol, presented_date))
    db.commit()
    db.close()


def update_prediction_outcome(symbol, outcome, outcome_price, outcome_pct, days, lesson):
    db = conn()
    db.execute("""
    UPDATE predictions
    SET outcome=?, outcome_price=?, outcome_pct=?, outcome_days=?, lesson=?
    WHERE symbol=? AND outcome='PENDING'
    ORDER BY id DESC LIMIT 1
    """, (outcome, outcome_price, outcome_pct, days, lesson, symbol))
    db.commit()
    db.close()


def retrospective_evaluate(active_holdings_symbols: list):
    """Called every evening: checks PENDING predictions that are now in portfolio and evaluates past outcomes."""
    db = conn()
    cur = db.cursor()
    cur.execute("SELECT * FROM predictions WHERE outcome='PENDING' AND user_accepted=1")
    pending = [dict(r) for r in cur.fetchall()]
    db.close()

    results = []
    for p in pending:
        results.append({
            "symbol":       p["symbol"],
            "name":         p["name"],
            "entry_price":  p["entry_price"],
            "target_price": p["target_price"],
            "stop_price":   p["stop_price"],
            "presented_date": p["presented_date"],
            "in_portfolio": p["symbol"] in active_holdings_symbols
        })
    return results


def get_stats():
    db = conn()
    cur = db.cursor()

    cur.execute("SELECT COUNT(*) FROM predictions WHERE outcome != 'PENDING'")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM predictions WHERE outcome='WIN'")
    wins = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM predictions WHERE outcome='LOSS'")
    losses = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM sessions")
    sessions = cur.fetchone()[0]
    cur.execute("SELECT * FROM wisdom ORDER BY confidence DESC LIMIT 1")
    top_wisdom = dict(cur.fetchone() or {})
    cur.execute("SELECT * FROM predictions ORDER BY id DESC LIMIT 8")
    history = [dict(r) for r in cur.fetchall()]

    db.close()
    win_rate = round(wins / total * 100, 1) if total else 0.0
    return {
        "total_evaluated": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_sessions": sessions,
        "top_wisdom": top_wisdom,
        "history": history
    }
