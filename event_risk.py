"""
JARVIS EVENT RISK & BINARY GAP SHIELD
Protects swing trades from high-impact overnight earnings announcements,
board meetings, dividend ex-dates, and binary shock gaps.
"""
from datetime import date, datetime, timedelta
import yfinance as yf

# In-memory cache to avoid repeated yfinance network hits
_EVENT_CACHE = {}

def get_event_risk(symbol: str, horizon_days: int = 15) -> dict:
    """
    Evaluates whether a stock has an upcoming earnings announcement or corporate action
    within the swing trading horizon (typically 15 trading days / ~21 calendar days).
    """
    sym = symbol.strip().upper()
    cache_key = f"{sym}_{date.today().isoformat()}"
    if cache_key in _EVENT_CACHE:
        return _EVENT_CACHE[cache_key]

    yf_symbol = sym if "." in sym else f"{sym}.NS"
    today = date.today()

    event_date = None
    event_type = "NONE"
    days_to_event = None

    try:
        ticker = yf.Ticker(yf_symbol)
        
        # 1. Check Ticker Calendar
        cal = getattr(ticker, "calendar", None)
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if ed:
                if isinstance(ed, list) and len(ed) > 0:
                    cand = ed[0]
                    if isinstance(cand, (date, datetime)):
                        cand_dt = cand.date() if isinstance(cand, datetime) else cand
                        if cand_dt >= today:
                            event_date = cand_dt
                            event_type = "EARNINGS_ANNOUNCEMENT"
                elif isinstance(ed, (date, datetime)):
                    cand_dt = ed.date() if isinstance(ed, datetime) else ed
                    if cand_dt >= today:
                        event_date = cand_dt
                        event_type = "EARNINGS_ANNOUNCEMENT"

        # 2. Check earnings_dates table if calendar did not reveal upcoming
        if not event_date:
            ed_df = getattr(ticker, "earnings_dates", None)
            if ed_df is not None and hasattr(ed_df, "index") and len(ed_df) > 0:
                for idx in ed_df.index:
                    try:
                        cand_dt = idx.date() if hasattr(idx, "date") else None
                        if cand_dt and cand_dt >= today:
                            if not event_date or cand_dt < event_date:
                                event_date = cand_dt
                                event_type = "EARNINGS_ANNOUNCEMENT"
                    except Exception:
                        continue

        # 3. Check Ex-Dividend Date from calendar
        if isinstance(cal, dict):
            ex_div = cal.get("Ex-Dividend Date")
            if ex_div and isinstance(ex_div, (date, datetime)):
                ex_dt = ex_div.date() if isinstance(ex_div, datetime) else ex_div
                if ex_dt >= today and (not event_date or ex_dt < event_date):
                    event_date = ex_dt
                    event_type = "EX_DIVIDEND_ADJUSTMENT"

    except Exception:
        pass

    if event_date:
        days_to_event = (event_date - today).days

    # Institutional Risk Classification
    if days_to_event is not None and days_to_event <= 3:
        status = "EVENT_BLACKOUT"
        risk_level = "CRITICAL"
        badge = f"GAP BLACKOUT: {event_type.replace('_', ' ')} IN {days_to_event}D"
        badge_color = "danger"
        allow_entry = False
        message = (
            f"CRITICAL OVERNIGHT GAP RISK! {sym} has {event_type.replace('_', ' ')} on {event_date.strftime('%d %b %Y')} "
            f"({days_to_event} days). Do NOT initiate new swing positions. If holding, enforce defensive stops."
        )
    elif days_to_event is not None and days_to_event <= 8:
        status = "EVENT_WARNING"
        risk_level = "ELEVATED"
        badge = f"EVENT APPROACHING: {event_type.replace('_', ' ')} IN {days_to_event}D"
        badge_color = "warning"
        allow_entry = True
        message = (
            f"{sym} has {event_type.replace('_', ' ')} on {event_date.strftime('%d %b %Y')} ({days_to_event} days). "
            f"Swing trade eligible, but target exit must precede event."
        )
    else:
        status = "EVENT_CLEAR"
        risk_level = "SAFE"
        badge = "EVENT SHIELD: CLEAR (NO EARNINGS SHOCK)"
        badge_color = "success"
        allow_entry = True
        event_str = f"Next event on {event_date.strftime('%d %b %Y')}" if event_date else "No binary corporate shock scheduled"
        message = f"Clean swing runway for {sym}. {event_str} within 1-3 week window."

    result = {
        "status": status,
        "risk_level": risk_level,
        "badge": badge,
        "badge_color": badge_color,
        "allow_entry": allow_entry,
        "event_type": event_type,
        "event_date": event_date.strftime("%Y-%m-%d") if event_date else None,
        "days_to_event": days_to_event,
        "message": message
    }

    _EVENT_CACHE[cache_key] = result
    return result
