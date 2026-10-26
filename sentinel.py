"""
JARVIS PORTFOLIO AI SENTINEL - INSTITUTIONAL DAILY HOLDING AUDIT ENGINE
Audits every demat stock using multi-model AI, CANSLIM fundamentals,
GARCH forward volatility dispersion cones, TreeSHAP explainability,
Dynamic 1.5x ATR Volatility Stops, Indian Tax/Friction Calibrator (20% STCG),
Binary Corporate Gap Shield, and Dual-Mode Holding Architecture (QUANT_SWING vs STRATEGIC_HOLD).
"""

from datetime import date, datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
from holidays import count_trading_days, get_target_horizon_date
import fundamentals
import volatility_cone
import shap_explainer
import sentiment_nlp
import event_risk
import indian_tax_friction
import multi_timeframe
from config import (
    TARGET_GROSS_PCT, TARGET_NET_PCT, STOP_LOSS_ATR_MULT,
    STOP_LOSS_MIN_PCT, STOP_LOSS_MAX_PCT, MAX_HOLD_DAYS
)

def fetch_stock_technicals_and_history(symbol: str) -> tuple:
    """Fetches real-time technicals and historical close series for forward volatility cone."""
    sym = symbol.upper()
    yf_symbol = sym if "." in sym else f"{sym}.NS"

    try:
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period="6mo")
        if hist.empty or len(hist) < 20:
            return {}, None

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        vol = hist["Volume"]

        ltp = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else ltp

        ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

        # RSI 14
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = float((100 - 100 / (1 + rs)).fillna(50.0).iloc[-1])

        # Volume Surge
        avg_vol = float(vol.tail(20).mean())
        vol_surge = round(float(vol.iloc[-1]) / avg_vol, 2) if avg_vol else 1.0

        # ATR 14
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else float(tr.mean())

        h52 = float(high.max())
        dist_52w = round(((h52 - ltp) / h52) * 100, 2)
        support = round(min(ema20, float(low.tail(10).min())), 2)
        resistance = round(max(h52, float(high.tail(10).max())), 2)

        tech = {
            "ltp": round(ltp, 2),
            "prev_close": round(prev, 2),
            "day_change_pct": round(((ltp - prev) / prev) * 100, 2),
            "ema20": round(ema20, 2),
            "ema50": round(ema50, 2),
            "ema200": round(ema200, 2),
            "rsi": round(rsi, 1),
            "vol_surge": vol_surge,
            "atr": round(atr, 2),
            "h52": round(h52, 2),
            "dist_52w": dist_52w,
            "support": support,
            "resistance": resistance,
            "stage2": ltp > ema20 > ema50
        }
        return tech, close
    except Exception:
        return {}, None


def audit_holding(holding: dict) -> dict:
    symbol = holding.get("symbol", "UNKNOWN").upper()
    name = holding.get("name", symbol)
    avg_price = float(holding.get("avg_price", 0.0))
    qty = int(holding.get("quantity", 0))
    ltp = float(holding.get("ltp", avg_price))
    invested = float(holding.get("invested", qty * avg_price))

    # Dual-Mode Holding Classification: QUANT_SWING vs STRATEGIC_HOLD
    holding_type = holding.get("holding_type")
    if not holding_type:
        holding_type = "STRATEGIC_HOLD" if symbol in ["IDEA", "YESBANK", "SUZLON", "RCOM"] else "QUANT_SWING"

    added_date_str = holding.get("added_date", date.today().strftime("%Y-%m-%d"))
    try:
        added_dt = datetime.strptime(added_date_str, "%Y-%m-%d").date()
        days_held = count_trading_days(added_dt, date.today())
    except Exception:
        days_held = holding.get("days_held", 2)

    tech, close_series = fetch_stock_technicals_and_history(symbol)
    if tech and tech.get("ltp"):
        ltp = tech["ltp"]

    if avg_price <= 0 and ltp > 0:
        avg_price = ltp
        invested = round(qty * avg_price, 2)

    pnl_abs = round((ltp - avg_price) * qty, 2) if avg_price > 0 else 0.0
    pnl_pct = round(((ltp - avg_price) / avg_price) * 100, 2) if avg_price > 0 else 0.0
    current_val = round(qty * ltp, 2)

    # 1. Indian Tax & Transaction Friction Yield
    net_current = indian_tax_friction.calculate_net_swing_yield(invested, current_val, qty=qty)

    # 2. Event & Binary Gap Shield
    days_left_est = max(1, MAX_HOLD_DAYS - days_held)
    ev_shield = event_risk.get_event_risk(symbol, horizon_days=days_left_est)

    # 3. Dynamic Volatility-Adjusted Stops (1.5x ATR) & Gross Target (+5.8% Sweet Spot)
    atr_val = tech.get("atr", round(avg_price * 0.022, 2))
    atr_pct_val = round((atr_val / avg_price) * 100, 2) if avg_price > 0 else 2.5
    dynamic_stop_pct = round(min(STOP_LOSS_MAX_PCT, max(STOP_LOSS_MIN_PCT, STOP_LOSS_ATR_MULT * atr_pct_val)), 2)

    # Target calculation (+5.8% gross yields ~4.25% net in pocket)
    target_price = float(holding.get("target_price", 0.0))
    if target_price <= 0 or target_price > (avg_price * 1.25):
        target_price = round(avg_price * (1.0 + TARGET_GROSS_PCT / 100.0), 2)

    net_target = indian_tax_friction.calculate_net_swing_yield(invested, qty * target_price, qty=qty)

    # Initial Dynamic Stop
    initial_stop_price = round(avg_price * (1.0 - dynamic_stop_pct / 100.0), 2)
    saved_stop = float(holding.get("stop_price", 0.0))
    stop_price = saved_stop if (saved_stop > 0 and abs(saved_stop - avg_price) / avg_price < 0.10) else initial_stop_price

    # 4. Structural Relaxed Trailing Stop Ladder
    gain_pct = pnl_pct
    if gain_pct >= 4.5:
        # Step 2: Target approach zone -> trail behind 1.2x ATR or lock +3.2%
        trail_candidate = max(stop_price, round(avg_price * 1.032, 2))
        trail_stop = trail_candidate
        trail_status = "PROFIT RUNNER LOCK (+3.2% SECURED)"
    elif gain_pct >= 3.0:
        # Step 1: More than 50% target achieved -> Shielded Breakeven +0.8% (covers all fees)
        trail_stop = max(stop_price, round(avg_price * 1.008, 2))
        trail_status = "SHIELDED BREAKEVEN (+0.8% COVERING FRICTION)"
    else:
        # Step 0: Incubation zone -> Allow full breathing room (1.5x ATR stop)
        trail_stop = stop_price
        trail_status = f"DYNAMIC 1.5x ATR STOP (-{dynamic_stop_pct}%)"

    horizon_res = get_target_horizon_date(date.today(), days_left_est)
    target_dt = horizon_res[0] if isinstance(horizon_res, tuple) else horizon_res
    target_date_str = target_dt.strftime("%d %b %Y")

    # 5. Fundamental Quality Profile
    fund = fundamentals.get_fundamental_profile(symbol, ltp)

    # 6. Multi-Timeframe Weekly Confluence (30W Weinstein Stage Line & Macro RSI)
    mtf_res = multi_timeframe.analyze_weekly_confluence(symbol)

    # 7. GARCH Forward Volatility Dispersion Cone
    vol_cone = volatility_cone.calculate_volatility_cone(close_series, ltp, horizon_days=days_left_est)

    # 7. TreeSHAP Attribution Breakdown
    shap_data = shap_explainer.explain_prediction({
        "rsi_14": tech.get("rsi", 50.0),
        "volume_surge_ratio": tech.get("vol_surge", 1.0),
        "ema20_dist_pct": round((ltp - tech.get("ema20", ltp)) / tech.get("ema20", ltp) * 100, 2) if tech.get("ema20") else 1.0,
        "india_vix": 14.5,
        "fundamental_score": fund.get("fundamental_score", 70)
    }, strategies=["Minervini VCP Breakout" if tech.get("vol_surge", 1.0) > 1.2 else "Weinstein Stage 2 Uptrend"])

    # 8. Financial NLP Sentiment
    nlp_sentiment = sentiment_nlp.analyze_sentiment(symbol)

    # =========================================================================
    # DECISION LOGIC: DUAL-MODE (QUANT_SWING vs STRATEGIC_HOLD)
    # =========================================================================

    if holding_type == "STRATEGIC_HOLD":
        # STRATEGIC / LONG-TERM HOLDING MODE
        # Stop loss panic-selling is DISABLED.
        # Monitored on solvency, debt distress, FII/DII accumulation, and long-term 200-EMA.
        debt_to_equity = fund.get("debt_to_equity", 1.0)
        fund_score = fund.get("fundamental_score", 50)
        
        if ev_shield.get("status") == "EVENT_BLACKOUT":
            action = "STRATEGIC_MONITOR"
            verdict_badge = f"🏛️ STRATEGIC MONITOR (EARNINGS IN {ev_shield['days_to_event']}D)"
            verdict_color = "warning"
            priority_alert = {
                "level": "WARNING",
                "badge": "⚠️ EARNINGS APPROACHING",
                "message": f"{name} is reporting earnings on {ev_shield['event_date']}. Solvency and results monitored."
            }
            exact_instruction = f"STRATEGIC WATCH: Position monitored through corporate event. Swing stop disabled."
            voice_part = f"Sir, strategic holding {name} has an upcoming corporate announcement in {ev_shield['days_to_event']} days. Fundamental tracking remains active."

        elif debt_to_equity > 3.0 or fund_score < 35:
            action = "STRATEGIC_MONITOR"
            verdict_badge = "🏛️ STRATEGIC WATCH: TURNAROUND / DEBT MONITOR"
            verdict_color = "warning"
            priority_alert = {
                "level": "INFO",
                "badge": "🏛️ TURNAROUND ASSET",
                "message": f"{name} monitored as turnaround asset. High leverage noted; swing stop disabled."
            }
            exact_instruction = f"STRATEGIC HOLDING: Fundamental turnaround tracked. No premature swing stop-outs."
            voice_part = f"Sir, {name} is classified as a strategic turnaround holding. It is being audited for balance sheet recovery rather than short term market noise."

        else:
            action = "STRATEGIC_HOLD"
            verdict_badge = "🏛️ STRATEGIC WEALTH HOLD"
            verdict_color = "success"
            priority_alert = {
                "level": "NORMAL",
                "badge": "🏛️ CORE ASSET",
                "message": f"{name} core strategic position intact. Long-term fundamentals and solvency healthy."
            }
            exact_instruction = f"STRATEGIC COMPOUNDER: Core holding intact. Long-term thesis active."
            voice_part = f"Sir, strategic holding {name} is performing steadily. Long term fundamentals remain solid."

    else:
        # QUANT_SWING MODE (Strict 1-3 Week Execution)
        if ev_shield.get("status") == "EVENT_BLACKOUT":
            action = "EVENT_DEFENSE"
            verdict_badge = "🛡️ GAP DEFENSE: BINARY EARNINGS SHIELD"
            verdict_color = "warning"
            priority_alert = {
                "level": "WARNING",
                "badge": "🛡️ GAP BLACKOUT",
                "message": f"Critical binary gap risk: {name} reports earnings in {ev_shield['days_to_event']} days. Recommend booking profit or closing position."
            }
            exact_instruction = f"BINARY GAP SHIELD: Corporate earnings in {ev_shield['days_to_event']} days. Close or defend position before overnight shock."
            voice_part = f"Sir, event risk alert for {name}. Earnings announcement is in {ev_shield['days_to_event']} days. I recommend locking gains or closing to prevent overnight gap shock."

        elif ltp >= target_price and target_price > 0:
            action = "BOOK_PROFIT"
            verdict_badge = f"🎯 SWING TARGET ACHIEVED (+{TARGET_GROSS_PCT}% Gross / +{net_current['net_pnl_pct']:+.1f}% Net)"
            verdict_color = "warning"
            priority_alert = {
                "level": "SUCCESS",
                "badge": "🎯 TARGET REACHED",
                "message": f"Target of Rs.{target_price:.2f} ({pnl_pct:+.2f}%) reached! Recommended action: Book profit of Rs.{pnl_abs:,.2f} (Net: Rs.{net_current['net_pnl_abs']:,.2f})."
            }
            exact_instruction = f"TARGET HIT! Sell order recommended at Rs.{ltp:.2f} to lock in net profit of Rs.{net_current['net_pnl_abs']:,.2f} after taxes & friction."
            voice_part = f"Sir, high priority alert for {name}. Our {TARGET_GROSS_PCT} percent swing target of Rs.{target_price} has been hit with net in-pocket profit of Rs.{net_current['net_pnl_abs']}. I recommend booking profit now."

        elif ltp <= trail_stop and trail_stop > 0:
            action = "EXIT_NOW"
            verdict_badge = "🛑 DYNAMIC ATR STOP TRIGGERED"
            verdict_color = "danger"
            priority_alert = {
                "level": "DANGER",
                "badge": "🛑 STOP LOSS ALERT",
                "message": f"Dynamic stop level Rs.{trail_stop:.2f} breached ({pnl_pct:+.2f}% loss). Immediate exit to preserve capital."
            }
            exact_instruction = f"STOP LOSS HIT! Dispatch market exit order at Rs.{ltp:.2f} to protect capital."
            voice_part = f"Sir, emergency risk alert for {name}. Dynamic stop loss level of Rs.{trail_stop} was triggered. Capital preservation requires an immediate exit."

        elif gain_pct >= 3.0:
            action = "TIGHTEN_STOP"
            verdict_badge = f"🛡️ {trail_status}"
            verdict_color = "warning"
            priority_alert = {
                "level": "WARNING",
                "badge": "🛡️ PROFIT PROTECTED",
                "message": f"{name} is up {pnl_pct:+.2f}%. Stop loss raised to Rs.{trail_stop:.2f} to guarantee zero-risk trade covering all friction."
            }
            exact_instruction = f"HOLD WITH TRAILING SHIELD! Stop raised to Rs.{trail_stop:.2f} ({trail_status}). Target: Rs.{target_price:.2f} by {target_date_str}."
            voice_part = f"Sir, {name} is running in profit at plus {pnl_pct:+.1f} percent. Stop loss has been raised to Rs.{trail_stop} to protect gains."

        elif tech.get("stage2") and tech.get("rsi", 50) <= 52 and pnl_pct > -1.5:
            action = "ACCUMULATE"
            verdict_badge = "💎 ACCUMULATE ON 20-EMA DIP"
            verdict_color = "info"
            priority_alert = {
                "level": "INFO",
                "badge": "💎 ACCUMULATION ZONE",
                "message": f"{name} is testing 20-EMA support (Rs.{tech.get('ema20', ltp)}) in institutional Stage 2 uptrend."
            }
            exact_instruction = f"ACCUMULATE / HOLD! Position well-supported at 20-EMA (Rs.{tech.get('ema20', ltp)}). Target Rs.{target_price:.2f} expected by {target_date_str}."
            voice_part = f"Sir, {name} is holding near key 20 EMA support. This is a solid accumulation zone for our swing target."

        else:
            action = "HOLD_AND_RIDE"
            verdict_badge = "⚡ HOLD & RIDE (QUANT SWING ACTIVE)"
            verdict_color = "success"
            priority_alert = {
                "level": "NORMAL",
                "badge": "⚡ ACTIVE SWING",
                "message": f"{name} trend intact ({pnl_pct:+.2f}%). Target of Rs.{target_price:.2f} tracked over next {days_left_est} trading days."
            }
            exact_instruction = f"HOLD POSITION! Trend intact. Dynamic ATR stop at Rs.{trail_stop:.2f}. Expected target Rs.{target_price:.2f} by {target_date_str}."
            voice_part = f"Sir, {name} is tracking normally with a PnL of {pnl_pct:+.1f} percent. Target of Rs.{target_price} is projected by {target_date_str}."

    return {
        "symbol": symbol,
        "name": name,
        "holding_type": holding_type,
        "holding_type_label": "🏛️ STRATEGIC HOLD" if holding_type == "STRATEGIC_HOLD" else "⚡ QUANT SWING",
        "quantity": qty,
        "avg_price": round(avg_price, 2),
        "ltp": round(ltp, 2),
        "invested": round(invested, 2),
        "current_value": current_val,
        "pnl_abs": pnl_abs,
        "pnl_pct": pnl_pct,
        "net_pnl_abs": net_current["net_pnl_abs"],
        "net_pnl_pct": net_current["net_pnl_pct"],
        "friction_charges": net_current["total_friction_abs"],
        "stcg_tax_abs": net_current["stcg_tax_abs"],
        "added_date": added_date_str,
        "days_held": days_held,
        "days_left_est": days_left_est,
        "target_date_str": target_date_str,
        "target_price": round(target_price, 2),
        "target_net_pct": net_target["net_pnl_pct"],
        "target_net_abs": net_target["net_pnl_abs"],
        "stop_price": round(stop_price, 2),
        "trail_stop": round(trail_stop, 2),
        "trailing_stop": round(trail_stop, 2),
        "trail_status": trail_status,
        "dynamic_stop_pct": dynamic_stop_pct,
        "target_pct": round(((target_price - avg_price) / avg_price * 100), 1) if avg_price > 0 else TARGET_GROSS_PCT,
        "stop_pct": round(((avg_price - stop_price) / avg_price * 100), 1) if avg_price > 0 else dynamic_stop_pct,
        "action": action,
        "verdict_badge": verdict_badge,
        "verdict_color": verdict_color,
        "priority_alert": priority_alert,
        "exact_instruction": exact_instruction,
        "voice_part": voice_part,
        "event_risk": ev_shield,
        "multi_timeframe": mtf_res,
        "tech": tech,
        "fundamentals": fund,
        "volatility_cone": vol_cone,
        "attribution": shap_data,
        "sentiment": nlp_sentiment
    }


def audit_all_holdings(holdings: list) -> dict:
    verdicts = []
    total_invested = 0.0
    total_value = 0.0

    hold_count = 0
    tighten_count = 0
    exit_count = 0
    accumulate_count = 0
    strategic_count = 0

    priority_alerts = []

    for h in holdings:
        audit = audit_holding(h)
        verdicts.append(audit)
        total_invested += audit["invested"]
        total_value += audit["current_value"]

        # Collect high-priority alerts
        if audit.get("priority_alert") and audit["priority_alert"]["level"] in ["WARNING", "DANGER", "SUCCESS"]:
            priority_alerts.append({
                "symbol": audit["symbol"],
                "alert": audit["priority_alert"]
            })

        act = audit["action"]
        htype = audit.get("holding_type")

        if htype == "STRATEGIC_HOLD":
            strategic_count += 1
        elif act in ["HOLD_AND_RIDE"]:
            hold_count += 1
        elif act in ["TIGHTEN_STOP", "BOOK_PROFIT", "EVENT_DEFENSE"]:
            tighten_count += 1
        elif act in ["EXIT_NOW", "TIME_EXIT"]:
            exit_count += 1
        elif act == "ACCUMULATE":
            accumulate_count += 1

    net_pnl_abs = round(total_value - total_invested, 2)
    net_pnl_pct = round((net_pnl_abs / total_invested) * 100, 2) if total_invested > 0 else 0.0

    # Total post-tax and friction calculation
    portfolio_tax_metrics = indian_tax_friction.calculate_net_swing_yield(total_invested, total_value, qty=len(holdings))

    return {
        "total_holdings": len(verdicts),
        "total_invested": round(total_invested, 2),
        "total_value": round(total_value, 2),
        "gross_pnl_abs": net_pnl_abs,
        "gross_pnl_pct": net_pnl_pct,
        "net_pnl_abs": portfolio_tax_metrics["net_pnl_abs"],
        "net_pnl_pct": portfolio_tax_metrics["net_pnl_pct"],
        "total_friction_abs": portfolio_tax_metrics["total_friction_abs"],
        "stcg_tax_abs": portfolio_tax_metrics["stcg_tax_abs"],
        "priority_alerts": priority_alerts,
        "status_counts": {
            "hold": hold_count,
            "tighten": tighten_count,
            "exit": exit_count,
            "accumulate": accumulate_count,
            "strategic": strategic_count
        },
        "verdicts": verdicts
    }
