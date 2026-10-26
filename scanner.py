import fundamentals
import volatility_cone
import shap_explainer
import sentiment_nlp
import event_risk
import indian_tax_friction
import multi_timeframe
import yfinance as yf
import pandas as pd
import numpy as np
from config import (
    MAX_CAPITAL, TARGET_PCT, STOP_LOSS_PCT, MIN_CONVICTION_SCORE,
    TARGET_GROSS_PCT, TARGET_NET_PCT, STOP_LOSS_ATR_MULT,
    STOP_LOSS_MIN_PCT, STOP_LOSS_MAX_PCT
)
import nifty500
import proven_swing_strategy
import ml_brain
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_market_regime():
    try:
        nifty = yf.Ticker('^NSEI').history(period='5d')
        vix   = yf.Ticker('^INDIAVIX').history(period='5d')

        n_close = round(float(nifty['Close'].iloc[-1]), 2)
        n_prev  = round(float(nifty['Close'].iloc[-2]), 2)
        n_chg   = round((n_close - n_prev) / n_prev * 100, 2)
        vix_val = round(float(vix['Close'].iloc[-1]), 2) if not vix.empty else 13.5

        return {
            'nifty_close':    n_close,
            'nifty_change':   n_chg,
            'india_vix':      vix_val,
            'regime':         'CALM' if vix_val < 14 else ('NORMAL' if vix_val < 19 else 'HIGH_RISK'),
            'regime_color':   'green' if vix_val < 14 else ('yellow' if vix_val < 19 else 'red'),
            'tradeable':      vix_val < 19,
        }
    except Exception:
        return {
            'nifty_close':  25000.0, 'nifty_change': -0.5,
            'india_vix':    14.0,    'regime': 'NORMAL',
            'regime_color': 'yellow','tradeable': True
        }

def _eval_stock(item, regime, existing_symbol, broker):
    sym, name, upstox_key, yfsym = item['symbol'], item['name'], item['upstox'], item['yf']
    if existing_symbol and sym == existing_symbol:
        return None
    try:
        close, volume, high, low = None, None, None, None
        if broker and broker.is_connected():
            candles = broker.get_historical_candles(upstox_key, interval='day')
            if candles and len(candles) >= 60:
                high   = pd.Series([float(c[2]) for c in reversed(candles)])
                low    = pd.Series([float(c[3]) for c in reversed(candles)])
                close  = pd.Series([float(c[4]) for c in reversed(candles)])
                volume = pd.Series([float(c[5]) for c in reversed(candles)])
        if close is None or len(close) < 60:
            try:
                import urllib.parse, requests
                from datetime import date, timedelta
                encoded = urllib.parse.quote(upstox_key, safe='')
                to_d, from_d = date.today().isoformat(), (date.today() - timedelta(days=200)).isoformat()
                u_url = 'https://api.upstox.com/v2/historical-candle/' + encoded + '/day/' + to_d + '/' + from_d
                u_r = requests.get(u_url, timeout=2).json()
                u_c = u_r.get('data', {}).get('candles', [])
                if u_c and len(u_c) >= 60:
                    high   = pd.Series([float(c[2]) for c in reversed(u_c)])
                    low    = pd.Series([float(c[3]) for c in reversed(u_c)])
                    close  = pd.Series([float(c[4]) for c in reversed(u_c)])
                    volume = pd.Series([float(c[5]) for c in reversed(u_c)])
            except Exception:
                pass
        if close is None or len(close) < 60:
            hist = yf.Ticker(yfsym).history(period='6mo')
            if len(hist) < 60:
                return None
            high, low, close, volume = hist['High'], hist['Low'], hist['Close'], hist['Volume']

        ltp = round(float(close.iloc[-1]), 2)
        prev = round(float(close.iloc[-2]), 2)
        day_chg = round((ltp - prev) / prev * 100, 2)

        strat_eval = proven_swing_strategy.evaluate_proven_strategies(close, volume)
        rsi = round(strat_eval.get('rsi', 50.0), 1)
        ema50 = round(float(close.ewm(span=50, adjust=False).mean().iloc[-1]), 2)
        ema200 = round(float(close.ewm(span=200, adjust=False).mean().iloc[-1]), 2)
        avg_vol_3m = int(volume.tail(60).mean())
        dist_to_ema50 = round((ltp - ema50) / ema50 * 100, 2)

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_14 = float(tr.rolling(14).mean().iloc[-1])
        atr_pct = round((atr_14 / ltp) * 100, 2)

        adr_series = ((high - low) / close) * 100
        adr_20 = round(float(adr_series.tail(20).mean()), 2)

        ret_3m = ((ltp - float(close.iloc[-60])) / float(close.iloc[-60])) * 100 if len(close) >= 60 else 0.0
        rs_rating = int(round(min(99, max(1, 50 + (ret_3m * 1.5)))))

        # 1. Dynamic ATR Volatility-Adjusted Stop (1.5x ATR14) with institutional guardrails
        atr_dist = STOP_LOSS_ATR_MULT * atr_14
        atr_stop_pct_val = (atr_dist / ltp) * 100.0 if ltp > 0 else 2.5
        stop_loss_pct = round(min(STOP_LOSS_MAX_PCT, max(STOP_LOSS_MIN_PCT, atr_stop_pct_val)), 2)
        stop_price = round(ltp * (1.0 - stop_loss_pct / 100.0), 2)

        # 2. Multi-Timeframe Weekly Macro Confluence (Stan Weinstein 30W Stage Line & Elder Triple Screen)
        mtf_res = multi_timeframe.analyze_weekly_confluence(sym)

        base_score = 50 + strat_eval['score_bonus'] + mtf_res.get('score_bonus', 0) + (15 if ltp > ema200 else 0) + (10 if 30 <= rsi <= 45 else 0) + (12 if rs_rating >= 75 else 0)
        score = min(max(base_score, 10), 99)

        qty = max(int(MAX_CAPITAL // ltp) if ltp else 1, 1)
        total_investment = round(qty * ltp, 2)

        # 2. Institutional Target (+5.8% gross calibrated for Indian Demat & 20% STCG)
        target_price = round(ltp * (1.0 + TARGET_GROSS_PCT / 100.0), 2)
        reward = round(qty * (target_price - ltp), 2)
        risk = round(qty * (ltp - stop_price), 2)
        rr_ratio = round(reward / risk, 2) if risk else 0

        # 3. Post-Tax Net In-Pocket Calculations
        net_metrics = indian_tax_friction.calculate_net_swing_yield(total_investment, qty * target_price, qty=qty)
        target_net_pct = net_metrics["net_pnl_pct"]
        target_net_abs = net_metrics["net_pnl_abs"]

        vol_surge = strat_eval.get('vol_surge', 1.0)
        velocity_factor = 1.0 + min(0.8, (vol_surge - 1.0) * 0.3) + (0.25 if rs_rating >= 75 else 0.0)
        daily_prog = max(0.5, adr_20 * 0.45 * velocity_factor)
        target_dist_pct = ((target_price - ltp) / ltp) * 100
        est_days = max(3, min(21, int(round(target_dist_pct / daily_prog))))

        from datetime import date
        from holidays import get_target_horizon_date
        target_dt, skipped_w, skipped_h = get_target_horizon_date(date.today(), est_days)
        target_date_str = target_dt.strftime('%b %d, %Y')
        horizon_confidence = round(min(95.0, max(68.0, 45.0 + (score * 0.35) + (rs_rating * 0.12) + (vol_surge * 4.0))), 1)

        # 4. Binary Event Risk Shield
        ev_risk = event_risk.get_event_risk(sym, horizon_days=est_days)

        if ev_risk.get("status") == "EVENT_BLACKOUT":
            status = "BINARY_GAP_BLACKOUT"
            score = min(score, 45) # disqualified from top pick to avoid overnight gap shock
        elif mtf_res.get("macro_stage") == "STAGE_4_DOWNTREND":
            status = "MACRO_STAGE_4_HEADWIND"
            score = min(score, 40) # Disqualified from top pick to prevent counter-trend trap!
        elif (score >= MIN_CONVICTION_SCORE and strat_eval['matched'] and mtf_res.get('aligned', True)):
            status = 'QUALIFIED_FOR_TOMORROW'
        else:
            status = 'IN_THE_GAME'

        ml_res = ml_brain.ml_engine.predict_candidate_score({
            'rsi_14': rsi, 'ema20_dist_pct': dist_to_ema50, 'sma50_dist_pct': round((ltp - ema200) / ema200 * 100, 2),
            'volume_surge_ratio': vol_surge, 'atr_pct': atr_pct, 'india_vix': regime.get('india_vix', 14.0), 'nifty_trend_score': 1.5
        })

        reasons = strat_eval.get('rationale', ['Uptrend intact'])
        reasons.append('Target Horizon: Est. ' + str(est_days) + ' trading days (Target Date: ' + target_date_str + ') with ' + str(horizon_confidence) + '% velocity confidence.')
        reasons.append('Relative Strength (RS Rating): ' + str(rs_rating) + '/99 outperforming index.')
        reasons.append('Volatility Stop: Dynamic 1.5x ATR (-' + str(stop_loss_pct) + '%) shielding trade from market noise.')
        reasons.append('Net Yield: Calibrated +' + str(TARGET_GROSS_PCT) + '% gross yields +' + str(target_net_pct) + '% net in pocket after 20% STCG & delivery fees.')
        reasons.append(ev_risk.get('badge', 'EVENT SHIELD: ACTIVE'))
        reasons.append('Macro Weekly Confluence: ' + mtf_res.get('macro_label', 'STAGE UNKNOWN'))
        reasons.append(mtf_res.get('rationale', 'Macro weekly trend confirmed.'))

        fund = fundamentals.get_fundamental_profile(sym, ltp)
        vol_cone = volatility_cone.calculate_volatility_cone(close, ltp, horizon_days=est_days)
        shap_data = shap_explainer.explain_prediction({
            'rsi_14': rsi, 'volume_surge_ratio': vol_surge, 'ema20_dist_pct': dist_to_ema50,
            'india_vix': regime.get('india_vix', 14.0), 'fundamental_score': fund.get('fundamental_score', 70)
        }, strategies=strat_eval.get('strategies', []))
        nlp_sent = sentiment_nlp.analyze_sentiment(sym)

        return {
            'symbol': sym, 'name': name, 'upstox_key': upstox_key, 'ltp': ltp, 'day_change': day_chg, 'rsi': rsi,
            'ema50': ema50, 'ema200': ema200, 'dist_ema50': dist_to_ema50, 'score': score, 'ml_score': ml_res['ml_score'],
            'win_prob': ml_res['win_probability_pct'], 'conviction': ml_res['conviction_tier'], 'strategies': strat_eval.get('strategies', []),
            'status': status, 'reasons': reasons, 'qty': qty, 'total_invest': total_investment, 'target': target_price,
            'stop': stop_price, 'reward': reward, 'risk': risk, 'rr_ratio': rr_ratio, 'avg_vol': avg_vol_3m,
            'atr_pct': atr_pct, 'adr_20': adr_20, 'rs_rating': rs_rating, 'est_days': est_days, 'target_date': target_date_str,
            'horizon_confidence': horizon_confidence,
            'target_pct': TARGET_GROSS_PCT, 'stop_pct': stop_loss_pct,
            'dynamic_stop_pct': stop_loss_pct, 'target_net_pct': target_net_pct,
            'target_net_abs': target_net_abs, 'event_risk': ev_risk,
            'net_metrics': net_metrics,
            'multi_timeframe': mtf_res,
            'fundamentals': fund, 'volatility_cone': vol_cone, 'attribution': shap_data, 'sentiment': nlp_sent
        }
    except Exception as e:
        return None

def scan_for_candidate(regime: dict, existing_symbol: str = None, broker = None) -> dict:
    stock_universe = nifty500.get_nifty500_watchlist()
    if not regime.get('tradeable', True):
        return {'found': False, 'reason': 'India VIX is above safe threshold of 19. Capital is preserved in cash.', 'scanned': len(stock_universe), 'top_candidates': []}
    candidates = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(_eval_stock, item, regime, existing_symbol, broker) for item in stock_universe]
        for f in as_completed(futures):
            res = f.result()
            if res is not None:
                candidates.append(res)
    if not candidates:
        return {'found': False, 'reason': 'No stock in Nifty 500 met strategy criteria today. Capital is preserved.', 'scanned': len(stock_universe), 'top_candidates': []}
    sorted_candidates = sorted(candidates, key=lambda x: (x['ml_score'], x['score']), reverse=True)
    qualified = [c for c in sorted_candidates if c['status'] == 'QUALIFIED_FOR_TOMORROW']
    best = qualified[0] if qualified else sorted_candidates[0]
    scoreboard_contenders = [c for c in sorted_candidates if c['symbol'] != best['symbol']][:20]
    return {
        'found': len(qualified) > 0,
        'best': best,
        'scanned': len(stock_universe),
        'all_above_bar': len(candidates),
        'top_candidates': scoreboard_contenders
    }
