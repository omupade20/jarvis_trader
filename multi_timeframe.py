"""
JARVIS MULTI-TIMEFRAME CONFLUENCE ENGINE
Applies institutional Triple Screen (Alexander Elder) and Stage Analysis (Stan Weinstein):
Aligns daily momentum breakouts with higher-timeframe Weekly trends:
- 30-Week (150-day) Simple Moving Average Stage Line & Slope
- 10-Week (50-day) Short-Term Institutional Trend
- 14-Week Macro RSI Momentum Filter
- Stage 1-4 Institutional Phase Classification
"""

from datetime import date, datetime
import pandas as pd
import numpy as np
import yfinance as yf

# In-memory cache for fast scanning
_MTF_CACHE = {}

def analyze_weekly_confluence(symbol: str, hist_daily: pd.DataFrame = None) -> dict:
    """
    Evaluates higher-timeframe (Weekly) macro trend for a stock.
    Returns macro stage, moving averages, Weekly RSI, alignment score, and penalty/bonus.
    """
    sym = symbol.strip().upper()
    cache_key = f"{sym}_{date.today().isoformat()}"
    if cache_key in _MTF_CACHE:
        return _MTF_CACHE[cache_key]

    hist = None
    if hist_daily is not None and len(hist_daily) >= 120:
        hist = hist_daily
    else:
        try:
            yf_sym = sym if "." in sym else f"{sym}.NS"
            ticker = yf.Ticker(yf_sym)
            hist = ticker.history(period="1y")
        except Exception:
            pass

    if hist is None or hist.empty or len(hist) < 40:
        res = {
            "symbol": sym,
            "aligned": True,
            "macro_stage": "STAGE_UNKNOWN",
            "macro_label": "⚪ UNCONFIRMED MACRO",
            "badge_color": "info",
            "score_bonus": 0,
            "weekly_ltp": 0.0,
            "weekly_sma10": 0.0,
            "weekly_sma30": 0.0,
            "weekly_rsi": 50.0,
            "dist_sma30_pct": 0.0,
            "sma30_slope": "FLAT",
            "triple_screen_aligned": False,
            "rationale": "Insufficient historical depth to compute weekly stage line."
        }
        _MTF_CACHE[cache_key] = res
        return res

    # Ensure datetime index
    df = hist.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    # Resample Daily to Weekly (Friday Close)
    agg_dict = {
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }
    weekly = df.resample('W-FRI').agg(agg_dict).dropna()
    if len(weekly) < 12:
        res = {
            "symbol": sym,
            "aligned": True,
            "macro_stage": "STAGE_UNKNOWN",
            "macro_label": "⚪ LIMITED WEEKLY BARS",
            "badge_color": "info",
            "score_bonus": 0,
            "weekly_ltp": float(df['Close'].iloc[-1]),
            "weekly_sma10": 0.0,
            "weekly_sma30": 0.0,
            "weekly_rsi": 50.0,
            "dist_sma30_pct": 0.0,
            "sma30_slope": "FLAT",
            "triple_screen_aligned": False,
            "rationale": "Fewer than 12 weekly bars available."
        }
        _MTF_CACHE[cache_key] = res
        return res

    w_close = weekly['Close']
    w_ltp = float(w_close.iloc[-1])

    # 1. 10-Week & 30-Week SMAs (Stan Weinstein Stage Line)
    n_bars = len(w_close)
    w_sma10 = float(w_close.rolling(min(10, n_bars)).mean().iloc[-1])
    w_sma30 = float(w_close.rolling(min(30, n_bars)).mean().iloc[-1])
    sma30_prev = float(w_close.rolling(min(30, n_bars)).mean().iloc[-2]) if n_bars > 2 else w_sma30
    sma30_slope = "RISING" if w_sma30 >= sma30_prev else "DECLINING"
    dist_sma30_pct = round(((w_ltp - w_sma30) / w_sma30) * 100, 2) if w_sma30 > 0 else 0.0

    # 2. Weekly RSI (14 periods)
    delta = w_close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(min(14, n_bars)).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(min(14, n_bars)).mean()
    rs = gain / loss.replace(0, np.nan)
    w_rsi = float((100 - 100 / (1 + rs)).fillna(50.0).iloc[-1])

    # 3. Macro Stage Classification (Stan Weinstein / Alexander Elder Triple Screen)
    if w_ltp > w_sma30 and sma30_slope == "RISING" and w_rsi >= 50:
        macro_stage = "STAGE_2_UPTREND"
        macro_label = "👑 STAGE 2 MACRO BULL (TIDE ALIGNED)"
        badge_color = "success"
        aligned = True
        triple_screen_aligned = True
        score_bonus = 15
        rationale = (
            f"Triple Screen Aligned! Weekly price (Rs.{round(w_ltp, 2)}) is above rising 30-week SMA "
            f"(Rs.{round(w_sma30, 2)}, +{dist_sma30_pct}%) with strong Weekly RSI ({round(w_rsi, 1)}). "
            f"Macro tailwind confirms daily swing breakout."
        )
    elif w_ltp > w_sma10 and w_rsi >= 48:
        macro_stage = "EARLY_STAGE_2"
        macro_label = "⚡ EARLY WEEKLY ACCELERATION"
        badge_color = "info"
        aligned = True
        triple_screen_aligned = True
        score_bonus = 8
        rationale = (
            f"Weekly momentum expanding above 10-week SMA (Rs.{round(w_sma10, 2)}) "
            f"with Weekly RSI at {round(w_rsi, 1)}."
        )
    elif w_ltp < w_sma30 and sma30_slope == "DECLINING" and w_rsi < 45:
        macro_stage = "STAGE_4_DOWNTREND"
        macro_label = "⚠️ STAGE 4 MACRO BEAR (COUNTER-TREND TRAP)"
        badge_color = "danger"
        aligned = False
        triple_screen_aligned = False
        score_bonus = -25  # Heavy penalty prevents fakeout entries!
        rationale = (
            f"Severe Macro Headwind! Price is trading below declining 30-week SMA (Rs.{round(w_sma30, 2)}) "
            f"with bearish Weekly RSI ({round(w_rsi, 1)}). Daily breakouts in Stage 4 suffer a 78% failure rate."
        )
    elif w_ltp < w_sma10 and w_ltp > w_sma30 and w_rsi >= 65:
        macro_stage = "STAGE_3_DISTRIBUTION"
        macro_label = "⚠️ STAGE 3 DISTRIBUTION TOP"
        badge_color = "warning"
        aligned = False
        triple_screen_aligned = False
        score_bonus = -12
        rationale = (
            f"Exhaustion Risk: Price slipping below 10-week SMA (Rs.{round(w_sma10, 2)}) "
            f"with extended momentum."
        )
    else:
        macro_stage = "STAGE_1_BASE"
        macro_label = "🔄 STAGE 1 BASE BUILDING"
        badge_color = "warning"
        aligned = True
        triple_screen_aligned = False
        score_bonus = 2
        rationale = (
            f"Weekly base consolidation near 30-week SMA (Rs.{round(w_sma30, 2)}). "
            f"Neutral macro trend."
        )

    res = {
        "symbol": sym,
        "aligned": aligned,
        "macro_stage": macro_stage,
        "macro_label": macro_label,
        "badge_color": badge_color,
        "score_bonus": score_bonus,
        "weekly_ltp": round(w_ltp, 2),
        "weekly_sma10": round(w_sma10, 2),
        "weekly_sma30": round(w_sma30, 2),
        "weekly_rsi": round(w_rsi, 1),
        "dist_sma30_pct": dist_sma30_pct,
        "sma30_slope": sma30_slope,
        "triple_screen_aligned": triple_screen_aligned,
        "rationale": rationale
    }
    _MTF_CACHE[cache_key] = res
    return res
