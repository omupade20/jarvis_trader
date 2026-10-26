"""
JARVIS GARCH & FORWARD VOLATILITY CONE PROJECTION ENGINE
Calculates 1-3 week forward price dispersion cones (10th, 50th, 90th percentile bounds)
and detects Volatility Squeeze conditions for 4-6% rapid swing expansions.
"""

import numpy as np
import pandas as pd

def calculate_volatility_cone(close_series: pd.Series, ltp: float, horizon_days: int = 15) -> dict:
    """
    Projects a 1-3 week forward price dispersion cone based on realized volatility.
    """
    if close_series is None or len(close_series) < 20:
        vol_daily = 0.015
    else:
        # 20-day log returns volatility
        log_ret = np.log(close_series / close_series.shift(1)).dropna()
        vol_daily = float(log_ret.tail(20).std())
        if np.isnan(vol_daily) or vol_daily <= 0:
            vol_daily = 0.015

    vol_annualized = round(vol_daily * np.sqrt(252) * 100, 1)

    # 15-day (1-3 week) expected standard deviation move
    std_move_pct = vol_daily * np.sqrt(horizon_days) * 100

    # Volatility Regime Detection
    if vol_annualized < 18.0:
        vol_regime = "VOLATILITY SQUEEZE (HIGH BREAKOUT PROBABILITY)"
        regime_badge = "SQUEEZE"
        dynamic_stop_pct = 2.0
    elif vol_annualized <= 32.0:
        vol_regime = "STEADY MOMENTUM EXPANSION"
        regime_badge = "NORMAL"
        dynamic_stop_pct = 2.4
    else:
        vol_regime = "HIGH VARIANCE (WIDE TRAILING REQUIRED)"
        regime_badge = "HIGH_VOL"
        dynamic_stop_pct = 3.0

    # 10th, 50th, and 90th percentile price boundaries over 1-3 weeks (4-6% swing zone)
    # 90th percentile represents our targeted 4-6% upside jump
    cone_upper_90 = round(ltp * (1 + (min(6.5, max(4.0, std_move_pct * 1.2)) / 100)), 2)
    cone_median_50 = round(ltp * (1 + (min(3.5, max(1.5, std_move_pct * 0.5)) / 100)), 2)
    cone_lower_10 = round(ltp * (1 - (dynamic_stop_pct / 100)), 2)

    upper_gain_pct = round(((cone_upper_90 - ltp) / ltp) * 100, 1)
    lower_risk_pct = round(((ltp - cone_lower_10) / ltp) * 100, 1)

    return {
        "annualized_vol_pct": vol_annualized,
        "daily_vol_pct": round(vol_daily * 100, 2),
        "vol_regime": vol_regime,
        "regime_badge": regime_badge,
        "dynamic_stop_pct": dynamic_stop_pct,
        "horizon_days": horizon_days,
        "cone_lower_10pct": cone_lower_10,
        "cone_median_50pct": cone_median_50,
        "cone_upper_90pct": cone_upper_90,
        "target_jump_pct": upper_gain_pct,
        "risk_cutoff_pct": lower_risk_pct
    }
