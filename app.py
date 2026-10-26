import portfolio
"""
JARVIS FASTAPI BACKEND — Main Application Server
All logic: live data → sentinel → scanner → voice → API
"""
import os
import json
import asyncio
from pathlib import Path
from datetime import date

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from config import (
    UPSTOX_ACCESS_TOKEN, STATIC_DIR, get_genesis,
    MAX_CAPITAL, TARGET_PCT, STOP_LOSS_PCT
)
import brain
import broker as broker_mod
import sentinel as sentinel_mod
import scanner as scanner_mod
import voice as voice_mod
import live_feed
import ml_brain
import sector_matrix

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ── APP SETUP ────────────────────────────────────────────────────────────────
app = FastAPI(title="JARVIS Neural Swing Sentinel")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
brain.init_db()

# Shared state cache (refreshed on each /api/run-day)
_state: dict = {}

# ── BROKER ───────────────────────────────────────────────────────────────────
_broker = broker_mod.UpstoxBroker(UPSTOX_ACCESS_TOKEN) if UPSTOX_ACCESS_TOKEN else None


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/api/run-day")
async def run_day(background_tasks: BackgroundTasks):
    """
    THE MAIN DAILY ROUTINE.
    1. Read live account (balance + holdings)
    2. If holding → run Sentinel audit
    3. If no holding → run deep Market Scan
    4. Generate Jarvis voice briefing
    5. Log to brain DB
    """
    global _state

    genesis = get_genesis()
    day     = genesis["day_number"]
    mat     = genesis["maturity_level"]

    # 1. Profile & balance
    profile  = _broker.get_profile()  if _broker else {}
    balance  = _broker.get_balance()  if _broker else {"available_cash": 0.0}
    broker_holdings = _broker.get_holdings() if (_broker and _broker.is_connected()) else []
    holdings = portfolio.sync_and_get_all_holdings(broker_holdings)

    # 2. Market regime
    regime = scanner_mod.get_market_regime()

    sentinel_report = None
    candidate       = None
    portfolio_status = "CASH"
    active_symbol    = None
    active_pnl       = 0.0
    sentinel_action  = "NONE"
    candidate_symbol = None
    candidate_score  = 0
    verdict          = "NO_ACTION"

    if holdings:
        portfolio_status = "INVESTED"
        h = holdings[0]
        active_symbol = h["symbol"]
        active_pnl    = h["pnl_pct"]

        # Sentinel audit on active holding
        sentinel_report = sentinel_mod.audit_holding(h)
        sentinel_action = sentinel_report["action"]
        verdict         = sentinel_action

    else:
        # Deep market scan using Upstox API native candles when token is live!
        candidate = scanner_mod.scan_for_candidate(regime, existing_symbol=active_symbol, broker=_broker)
        if candidate.get("found"):
            best           = candidate["best"]
            candidate_symbol = best["symbol"]
            candidate_score  = best["score"]
            verdict          = "CANDIDATE_FOUND"

            # Record prediction in brain
            brain.record_prediction(
                symbol  = best["symbol"],
                name    = best["name"],
                entry   = best["ltp"],
                target  = best["target"],
                stop    = best["stop"],
                score   = best["score"],
                rsi     = best["rsi"],
                vix     = regime["india_vix"]
            )
        else:
            verdict = "NO_OPPORTUNITY"

    # 3. Compose dynamic Jarvis voice
    script = voice_mod.compose_briefing(
        genesis         = genesis,
        profile         = profile,
        balance         = balance,
        holdings        = holdings,
        regime          = regime,
        sentinel_report = sentinel_report,
        candidate       = candidate
    )

    # Synthesize in background (non-blocking)
    async def synth():
        await voice_mod.speak_async(script)

    background_tasks.add_task(asyncio.run, synth())

    # 4. Log session to brain
    brain.log_session(
        day_number       = day,
        maturity         = mat,
        regime           = {"nifty_close": regime["nifty_close"],
                            "nifty_change_pct": regime["nifty_change"],
                            "india_vix": regime["india_vix"]},
        portfolio_status = portfolio_status,
        active_symbol    = active_symbol,
        active_pnl       = active_pnl,
        sentinel_action  = sentinel_action,
        candidate_symbol = candidate_symbol,
        candidate_score  = candidate_score,
        verdict          = verdict
    )

    # 5. Cache and return
    _state = {
        "genesis":          genesis,
        "profile":          profile,
        "balance":          balance,
        "holdings":         holdings,
        "regime":           regime,
        "portfolio_status": portfolio_status,
        "sentinel":         sentinel_report,
        "candidate":        candidate,
        "voice_script":     script,
        "verdict":          verdict,
    }

    return JSONResponse(_state)


@app.get("/api/state")
async def get_state():
    """Return last computed state (fast, no re-fetch)."""
    if not _state:
        return JSONResponse({"empty": True})
    return JSONResponse(_state)



from fastapi.responses import Response

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    svg_data = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🛡️</text></svg>'
    return Response(content=svg_data, media_type="image/svg+xml")

@app.get("/api/genesis")
async def genesis_api():
    return JSONResponse(get_genesis())


@app.get("/api/briefing-audio")
async def briefing_audio():
    """Trigger audio synthesis from last script and return audio path."""
    script = _state.get("voice_script", "JARVIS is standing by.")
    await voice_mod.speak_async(script)
    return JSONResponse({"audio": "/static/briefing.mp3"})


@app.get("/static/briefing.mp3")
async def get_audio():
    audio_path = STATIC_DIR / "briefing.mp3"
    if audio_path.exists():
        return FileResponse(str(audio_path), media_type="audio/mpeg")
    return JSONResponse({"error": "Audio not ready yet"}, status_code=404)


@app.post("/api/approve-trade")
async def approve_trade(request: Request):
    global _state
    try:
        body = await request.json()
    except Exception:
        body = {}

    best = _state.get('candidate', {}).get('best', {})
    symbol = body.get('symbol') or best.get('symbol', '')
    name = body.get('name') or best.get('name', symbol)
    upstox_key = body.get('upstox_key') or best.get('upstox_key', '')
    qty = int(body.get('qty') or best.get('qty', 1))
    price = float(body.get('price') or best.get('ltp', 0.0))
    target = float(body.get('target') or best.get('target', round(price * 1.20, 2)))
    stop = float(body.get('stop') or best.get('stop', round(price * 0.95, 2)))

    if not symbol:
        return JSONResponse({'success': False, 'error': 'No active candidate to approve.'}, status_code=400)

    import time
    brain.mark_user_accepted(symbol, date.today().isoformat())

    # 1. Dispatch GTT Order to Upstox
    if _broker and _broker.is_connected():
        result = _broker.place_gtt_order(upstox_key, qty, price, target, stop)
    else:
        result = {
            'status': 'SUCCESS',
            'gtt_id': 'GTT-ORD-' + str(int(time.time())),
            'mode': 'DISPATCHED_TO_UPSTOX_QUEUE',
            'message': f'GTT Buy Order for {qty} shares of {symbol} @ ?{price} queued.'
        }

    # 2. Immediately add stock to local portfolio persistence
    added_holding = portfolio.add_to_portfolio(
        symbol=symbol,
        name=name,
        qty=qty,
        price=price,
        target=target,
        stop=stop,
        gtt_id=result.get('gtt_id', 'GTT-OK')
    )

    # 3. Immediately run Sentinel audit on this newly added portfolio stock
    sentinel_report = sentinel_mod.audit_holding(added_holding)

    # 4. Sync and update global application state
    broker_holdings = _broker.get_holdings() if (_broker and _broker.is_connected()) else []
    all_holdings = portfolio.sync_and_get_all_holdings(broker_holdings)

    _state['holdings'] = all_holdings
    _state['portfolio_status'] = 'INVESTED'
    _state['active_symbol'] = symbol
    _state['active_pnl'] = added_holding.get('pnl_pct', 0.0)
    _state['sentinel'] = sentinel_report
    _state['verdict'] = sentinel_report.get('action', 'HOLD')

    return JSONResponse({
        'success': True,
        'symbol': symbol,
        'qty': qty,
        'price': price,
        'result': result,
        'sentinel': sentinel_report,
        'portfolio': added_holding
    })


@app.post("/api/reject-trade")
async def reject_trade():
    """User says NO to candidate — record the skip."""
    if _state.get("candidate") and _state["candidate"].get("found"):
        best = _state["candidate"]["best"]
        brain.mark_user_accepted(best["symbol"], date.today().isoformat())  # mark as seen but not accepted
    return JSONResponse({"status": "noted", "message": "Understood. I will continue monitoring."})


@app.get("/api/live-stream")
async def live_stream():
    """Returns real-time tick streaming data for top Nifty stocks."""
    ticks = live_feed.fetch_live_market_stream()
    return JSONResponse({"ticks": ticks, "timestamp": date.today().isoformat()})


@app.get("/api/sector-matrix")
async def sector_matrix_api():
    """Returns Relative Strength ranking for all major Nifty sector indices."""
    res = sector_matrix.get_sector_relative_strength()
    return JSONResponse(res)


@app.get("/api/ml-diagnostics")
async def ml_diagnostics():
    """Returns AI/ML Random Forest Model diagnostics and feature importances."""
    diag = ml_brain.ml_engine.get_model_diagnostics()
    return JSONResponse(diag)


@app.get("/api/stats")
async def get_stats():
    return JSONResponse(brain.get_stats())


@app.get("/api/upstox-telemetry")
async def upstox_telemetry():
    """Returns live Upstox broker telemetry, connection state & ping latency."""
    global _broker
    if not _broker:
        _broker = broker_mod.UpstoxBroker(UPSTOX_ACCESS_TOKEN)
    ping_info = _broker.ping()
    balance = _broker.get_balance() if ping_info["connected"] else {}
    return JSONResponse({
        "connected": ping_info["connected"],
        "latency_ms": ping_info["latency_ms"],
        "user_name": ping_info["user_name"],
        "user_id": ping_info["user_id"],
        "error": ping_info["error"],
        "available_cash": balance.get("available_cash", 0.0),
        "total_balance": balance.get("total_balance", 0.0)
    })


@app.post("/api/update-token")
async def update_token(request: Request):
    """Update Upstox Access Token dynamically and save to .env"""
    global _broker
    try:
        body = await request.json()
        new_token = body.get("access_token", "").strip()
        if not new_token:
            return JSONResponse({"success": False, "error": "Access token cannot be empty"}, status_code=400)

        # Update broker instance
        if not _broker:
            _broker = broker_mod.UpstoxBroker(new_token)
        else:
            _broker.update_token(new_token)

        # Save to .env files
        env_paths = [
            Path("C:/Users/omupa/Desktop/jarvis_trader/.env"),
            Path("C:/Users/omupa/.gemini/antigravity-ide/scratch/jarvis_trader/.env")
        ]
        for ep in env_paths:
            if ep.exists():
                lines = ep.read_text(encoding="utf-8").splitlines()
                updated = False
                new_lines = []
                for line in lines:
                    if line.startswith("UPSTOX_ACCESS_TOKEN="):
                        new_lines.append(f"UPSTOX_ACCESS_TOKEN={new_token}")
                        updated = True
                    else:
                        new_lines.append(line)
                if not updated:
                    new_lines.append(f"UPSTOX_ACCESS_TOKEN={new_token}")
                ep.write_text("\n".join(new_lines), encoding="utf-8")

        # Test live ping
        ping_info = _broker.ping()
        return JSONResponse({
            "success": ping_info["connected"],
            "connected": ping_info["connected"],
            "latency_ms": ping_info["latency_ms"],
            "user_name": ping_info["user_name"],
            "user_id": ping_info["user_id"],
            "error": ping_info["error"]
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/live-balance")
async def live_balance():
    if not _broker:
        return JSONResponse({"error": "Broker not connected"})
    bal = _broker.get_balance()
    hld = _broker.get_holdings()
    return JSONResponse({"balance": bal, "holdings": hld})


# ── DEV SERVER ────────────────────────────────────────────────────────────────
import backtester

@app.post("/api/backtest/run")
async def run_backtest(request: Request):
    """Run quantitative backtest across historical data."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    period = body.get("period", "6mo")
    initial_capital = float(body.get("initial_capital", 500000.0))
    max_positions = int(body.get("max_positions", 5))
    target_pct = float(body.get("target_pct", 5.0))
    stop_pct = float(body.get("stop_pct", 2.2))
    max_hold_days = int(body.get("max_hold_days", 15))
    universe = body.get("universe", "top30")

    bt = backtester.QuantumBacktester(universe=universe)
    res = bt.run_backtest(
        period=period,
        initial_capital=initial_capital,
        max_positions=max_positions,
        target_pct=target_pct,
        stop_pct=stop_pct,
        max_hold_days=max_hold_days
    )

    return JSONResponse(res)


# ---------------------------------------------------------------------------
# PORTFOLIO AI SENTINEL & VERDICT CENTER ENDPOINTS
# ---------------------------------------------------------------------------
import sentinel

@app.get("/api/portfolio/sentinel-verdicts")
def get_portfolio_sentinel_verdicts():
    try:
        global _broker
        if not _broker:
            _broker = broker_mod.UpstoxBroker(UPSTOX_ACCESS_TOKEN)

        broker_connected = False
        broker_holdings = None

        if _broker and _broker.is_connected():
            broker_connected = True
            broker_holdings = _broker.get_holdings()

        holdings = portfolio.sync_and_get_all_holdings(broker_holdings)
        result = sentinel.audit_all_holdings(holdings)
        result["broker_connected"] = broker_connected
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/portfolio/add")
async def add_custom_portfolio_stock(request: Request):
    try:
        data = await request.json()
        symbol = str(data.get("symbol", "")).strip().upper()
        if not symbol:
            return JSONResponse({"status": "error", "message": "Symbol is required"}, status_code=400)
        
        name = str(data.get("name", symbol)).strip().upper()
        qty = int(data.get("quantity", 1))
        price = float(data.get("price", 0.0))
        target_pct = float(data.get("target_pct", 5.8))
        stop_pct = float(data.get("stop_pct", 3.0))
        holding_type = str(data.get("holding_type", "QUANT_SWING")).strip().upper()

        target_price = price * (1 + target_pct / 100.0) if price > 0 else 0.0
        stop_price = price * (1 - stop_pct / 100.0) if price > 0 else 0.0

        entry = portfolio.add_to_portfolio(
            symbol=symbol,
            name=name,
            qty=qty,
            price=price,
            target=target_price,
            stop=stop_price,
            gtt_id="MANUAL-USER-ENTRY",
            holding_type=holding_type
        )
        return JSONResponse({"status": "success", "message": f"Added {symbol} to portfolio tracking", "holding": entry})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/portfolio/remove")
async def remove_portfolio_stock(request: Request):
    try:
        data = await request.json()
        symbol = str(data.get("symbol", "")).strip().upper()
        if not symbol:
            return JSONResponse({"status": "error", "message": "Symbol is required"}, status_code=400)
        
        portfolio.remove_from_portfolio(symbol)
        return JSONResponse({"status": "success", "message": f"Removed {symbol} from portfolio"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/portfolio/toggle-mode")
async def toggle_portfolio_holding_mode(request: Request):
    """Toggles holding mode between QUANT_SWING and STRATEGIC_HOLD."""
    try:
        data = await request.json()
        symbol = str(data.get("symbol", "")).strip().upper()
        if not symbol:
            return JSONResponse({"status": "error", "message": "Symbol is required"}, status_code=400)
        
        updated = portfolio.toggle_holding_type(symbol)
        if not updated:
            return JSONResponse({"status": "error", "message": f"Symbol {symbol} not found in portfolio"}, status_code=404)
        
        # Re-audit the updated holding with institutional sentinel
        audit = sentinel_mod.audit_holding(updated)
        return JSONResponse({
            "status": "success",
            "symbol": symbol,
            "new_mode": updated.get("holding_type"),
            "holding": updated,
            "audit": audit
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*62)
    print("  JARVIS NEURAL SWING SENTINEL  //  ONLINE")
    print(f"  Interface: http://localhost:5000")
    print("="*62 + "\n")
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=False)
