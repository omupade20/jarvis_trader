import json
import os
from datetime import date, datetime
from pathlib import Path

PORTFOLIO_FILE = Path(r"C:\Users\omupa\Desktop\jarvis_trader\portfolio.json")

def load_portfolio() -> list:
    if not PORTFOLIO_FILE.exists():
        return []
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            holdings = json.load(f)
            # Ensure each holding has holding_type
            for h in holdings:
                if "holding_type" not in h:
                    sym = h.get("symbol", "").upper()
                    h["holding_type"] = "STRATEGIC_HOLD" if sym in ["IDEA", "YESBANK", "SUZLON", "RCOM"] else "QUANT_SWING"
            return holdings
    except Exception:
        return []

def save_portfolio(holdings: list):
    try:
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(holdings, f, indent=2)
    except Exception as e:
        print(f"Error saving portfolio: {e}")

def add_to_portfolio(symbol: str, name: str, qty: int, price: float, target: float = 0.0, stop: float = 0.0, gtt_id: str = "", holding_type: str = "QUANT_SWING") -> dict:
    holdings = load_portfolio()
    
    entry = None
    for h in holdings:
        if h.get("symbol") == symbol:
            entry = h
            break
            
    avg_price = round(price, 2)
    target_price = round(target or (avg_price * 1.058), 2)  # 5.8% gross target
    stop_price = round(stop or (avg_price * 0.97), 2)
    invested = round(qty * avg_price, 2)
    
    if entry:
        old_qty = entry.get("quantity", 0)
        old_avg = entry.get("avg_price", price)
        new_qty = old_qty + qty
        new_avg = round(((old_qty * old_avg) + (qty * price)) / new_qty, 2)
        entry["quantity"] = new_qty
        entry["avg_price"] = new_avg
        entry["invested"] = round(new_qty * new_avg, 2)
        entry["target_price"] = target_price
        entry["stop_price"] = stop_price
        if gtt_id:
            entry["gtt_id"] = gtt_id
        if holding_type:
            entry["holding_type"] = holding_type
    else:
        entry = {
            "symbol": symbol,
            "name": name or symbol,
            "quantity": qty,
            "avg_price": avg_price,
            "ltp": avg_price,
            "target_price": target_price,
            "stop_price": stop_price,
            "invested": invested,
            "pnl_abs": 0.0,
            "pnl_pct": 0.0,
            "added_date": date.today().isoformat(),
            "days_held": 1,
            "gtt_status": "ACTIVE_GTT",
            "gtt_id": gtt_id or "GTT-SENTINEL-TRACKED",
            "holding_type": holding_type
        }
        holdings.append(entry)
        
    save_portfolio(holdings)
    return entry

def remove_from_portfolio(symbol: str):
    holdings = load_portfolio()
    holdings = [h for h in holdings if h.get("symbol") != symbol]
    save_portfolio(holdings)

def toggle_holding_type(symbol: str) -> dict:
    holdings = load_portfolio()
    target_holding = None
    for h in holdings:
        if h.get("symbol") == symbol:
            cur_type = h.get("holding_type", "QUANT_SWING")
            new_type = "STRATEGIC_HOLD" if cur_type == "QUANT_SWING" else "QUANT_SWING"
            h["holding_type"] = new_type
            target_holding = h
            break
    if target_holding:
        save_portfolio(holdings)
    return target_holding

def sync_and_get_all_holdings(broker_holdings: list = None) -> list:
    local_holdings = load_portfolio()
    merged = {h["symbol"]: h for h in local_holdings if "symbol" in h}

    # Only sync if broker explicitly returns an active list of holdings
    if broker_holdings and len(broker_holdings) > 0:
        broker_syms = set()
        for bh in broker_holdings:
            sym = (bh.get("symbol") or bh.get("tradingsymbol") or bh.get("trading_symbol") or "").upper()
            if not sym:
                continue
            broker_syms.add(sym)
            qty = int(bh.get("quantity", 1))
            avg = float(bh.get("avg_price") or bh.get("average_price") or 0.0)
            ltp = float(bh.get("ltp") or bh.get("last_price") or avg)
            if avg <= 0:
                avg = ltp

            target_price = round(avg * 1.058, 2)  # 5.8% gross target sweet spot
            stop_price = round(avg * 0.97, 2)     # ~3% dynamic stop buffer
            invested = round(qty * avg, 2)
            pnl_abs = round((ltp - avg) * qty, 2)
            pnl_pct = round(((ltp - avg) / avg * 100), 2) if avg > 0 else 0.0

            if sym in merged:
                merged[sym]["quantity"] = qty
                merged[sym]["avg_price"] = avg
                merged[sym]["ltp"] = ltp
                merged[sym]["invested"] = invested
                merged[sym]["pnl_abs"] = pnl_abs
                merged[sym]["pnl_pct"] = pnl_pct
                # Keep target and stop if already established
                if not merged[sym].get("target_price"):
                    merged[sym]["target_price"] = target_price
                if not merged[sym].get("stop_price"):
                    merged[sym]["stop_price"] = stop_price
                merged[sym]["gtt_status"] = "BROKER_SYNCED"
                if "holding_type" not in merged[sym]:
                    merged[sym]["holding_type"] = "STRATEGIC_HOLD" if sym in ["IDEA", "YESBANK", "SUZLON"] else "QUANT_SWING"
            else:
                merged[sym] = {
                    "symbol": sym,
                    "name": bh.get("name") or bh.get("company_name") or sym,
                    "quantity": qty,
                    "avg_price": avg,
                    "ltp": ltp,
                    "target_price": target_price,
                    "stop_price": stop_price,
                    "invested": invested,
                    "pnl_abs": pnl_abs,
                    "pnl_pct": pnl_pct,
                    "added_date": date.today().isoformat(),
                    "days_held": 1,
                    "gtt_status": "BROKER_SYNCED",
                    "gtt_id": "GTT-LIVE-SYNC",
                    "holding_type": "STRATEGIC_HOLD" if sym in ["IDEA", "YESBANK", "SUZLON"] else "QUANT_SWING"
                }

    result = list(merged.values())
    save_portfolio(result)
    return result
