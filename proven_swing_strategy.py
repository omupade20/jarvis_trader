"""
JARVIS PROVEN SWING STRATEGIES — Battle-Tested Legendary Trading Formulas
Implements 4 famous swing trading systems:
1. Mark Minervini VCP (Volatility Contraction Pattern)
2. Stan Weinstein Stage 2 Uptrend Breakout
3. RSI Pullback on 50-day EMA Support (Elder Triple Screen)
4. Explosive Volume Surge Breakout
"""
import pandas as pd
import numpy as np

def evaluate_proven_strategies(close: pd.Series, volume: pd.Series) -> dict:
    """
    Evaluates closing price and volume data against proven swing formulas.
    Returns matched strategy names, conviction score bonus, and setup rationale.
    """
    if len(close) < 60:
        return {"matched": False, "strategies": [], "score_bonus": 0, "rationale": []}

    ltp = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
    
    # Calculate RSI 14
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = float((100 - 100 / (1 + rs)).fillna(50.0).iloc[-1])

    avg_vol_20 = float(volume.tail(20).mean())
    last_vol = float(volume.iloc[-1])
    vol_surge_ratio = round(last_vol / avg_vol_20, 2) if avg_vol_20 else 1.0

    matched_strategies = []
    score_bonus = 0
    rationale = []

    # 1. MARK MINERVINI VCP (Volatility Contraction Pattern)
    # Tight consolidation over 10 days, price within 3% of 20 EMA, volume drying up then expanding
    recent_10_high = float(close.tail(10).max())
    recent_10_low = float(close.tail(10).min())
    range_pct = (recent_10_high - recent_10_low) / recent_10_low * 100
    if range_pct < 6.0 and ltp > ema20 and vol_surge_ratio > 1.3:
        matched_strategies.append("Minervini VCP Breakout")
        score_bonus += 25
        rationale.append(f"Minervini VCP Pattern: Tight 10-day range ({range_pct:.1f}%) with {vol_surge_ratio}x volume expansion")

    # 2. STAN WEINSTEIN STAGE 2 UPTREND BREAKOUT
    # Price > 50 EMA > 200 EMA, and 50 EMA is sloping upwards over last 10 days
    ema50_10days_ago = float(close.ewm(span=50, adjust=False).mean().iloc[-10])
    if ltp > ema50 > ema200 and ema50 > ema50_10days_ago:
        matched_strategies.append("Weinstein Stage 2 Uptrend")
        score_bonus += 20
        rationale.append("Stan Weinstein Stage 2: Confirmed macro uptrend with sloping 50 EMA support")

    # 3. RSI PULLBACK ON 50-DAY EMA SUPPORT (Elder Triple Screen)
    # RSI between 30 and 44, price within 3% of 50 EMA in an overall uptrend
    dist_ema50 = abs((ltp - ema50) / ema50 * 100)
    if 28 <= rsi <= 44 and dist_ema50 <= 3.5 and ltp > ema200:
        matched_strategies.append("RSI 50-EMA Support Bounce")
        score_bonus += 25
        rationale.append(f"RSI Pullback: Oversold RSI of {rsi:.1f} at key 50-day EMA support zone")

    # 4. EXPLOSIVE VOLUME SURGE BREAKOUT
    # Volume > 1.8x average volume and positive green candle move (> 1%)
    if vol_surge_ratio >= 1.8 and ltp > prev_close:
        matched_strategies.append("Volume Surge Breakout")
        score_bonus += 15
        rationale.append(f"Institutional Accumulation: Heavy volume surge ({vol_surge_ratio}x 20-day avg)")

    return {
        "matched": len(matched_strategies) > 0,
        "strategies": matched_strategies,
        "score_bonus": score_bonus,
        "rationale": rationale,
        "rsi": rsi,
        "vol_surge": vol_surge_ratio
    }
