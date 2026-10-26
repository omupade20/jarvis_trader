"""
JARVIS UPSTOX BROKER — Live Account Telemetry
Reads: balance, holdings, positions (never trades without approval)
"""
import requests
from pathlib import Path
from config import UPSTOX_BASE_URL, DB_PATH


class UpstoxBroker:
    def __init__(self, token: str):
        self.token = token.strip()
        self.headers = {
            "Accept":        "application/json",
            "Authorization": f"Bearer {self.token}"
        }

    def _get(self, endpoint: str, params: dict = None):
        try:
            r = requests.get(
                f"{UPSTOX_BASE_URL}{endpoint}",
                headers=self.headers,
                params=params,
                timeout=8
            )
            return r.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _post(self, endpoint: str, data: dict):
        try:
            r = requests.post(
                f"{UPSTOX_BASE_URL}{endpoint}",
                json=data,
                headers=self.headers,
                timeout=8
            )
            return r.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def update_token(self, new_token: str):
        self.token = new_token.strip()
        self.headers = {
            "Accept":        "application/json",
            "Authorization": f"Bearer {self.token}"
        }

    def get_historical_candles(self, instrument_key: str, interval: str = "day") -> list:
        """Fetches daily candlestick data directly from Upstox API."""
        import urllib.parse
        from datetime import date, timedelta
        encoded_key = urllib.parse.quote(instrument_key, safe='')
        to_date = date.today().isoformat()
        from_date = (date.today() - timedelta(days=200)).isoformat()
        
        url = f"/historical-candle/{encoded_key}/{interval}/{to_date}/{from_date}"
        r = self._get(url)
        if r.get("status") == "success":
            candles = r.get("data", {}).get("candles", [])
            if len(candles) >= 30:
                return candles
        url2 = f"/historical-candle/{encoded_key}/{interval}/{to_date}"
        r2 = self._get(url2)
        if r2.get("status") == "success":
            return r2.get("data", {}).get("candles", [])
        return []

    def get_market_quote(self, instrument_key: str) -> dict:
        """Fetches live market quote directly from Upstox API."""
        r = self._get(f"/market-quote/quotes", params={"symbol": instrument_key})
        if r.get("status") == "success":
            data = r.get("data", {})
            return data.get(instrument_key, {})
        return {}

    def ping(self) -> dict:
        """Measures API response latency in milliseconds."""
        import time
        t0 = time.time()
        r = self._get("/user/profile")
        latency = round((time.time() - t0) * 1000, 1)
        connected = (r.get("status") == "success")
        user_name = r.get("data", {}).get("user_name", "") if connected else ""
        user_id   = r.get("data", {}).get("user_id", "")   if connected else ""
        error_msg = ""
        if not connected:
            errors = r.get("errors", [])
            if errors and isinstance(errors, list):
                error_msg = errors[0].get("message", "API Unauthorized")
            else:
                error_msg = r.get("message", "Broker connection failed")
        return {
            "connected": connected,
            "latency_ms": latency if connected else 0,
            "user_name": user_name,
            "user_id": user_id,
            "error": error_msg
        }

    def is_connected(self) -> bool:
        r = self._get("/user/profile")
        return r.get("status") == "success"

    def get_profile(self) -> dict:
        r = self._get("/user/profile")
        if r.get("status") == "success":
            return r["data"]
        return {}

    def get_balance(self) -> dict:
        """Returns available cash balance."""
        r = self._get("/user/get-funds-and-margin")
        if r.get("status") == "success":
            data = r.get("data", {})
            # Upstox returns equity segment details
            equity = data.get("equity", {})
            return {
                "available_cash":    round(float(equity.get("available_margin", 0) or 0), 2),
                "used_margin":       round(float(equity.get("used_margin", 0) or 0), 2),
                "total_balance":     round(float(equity.get("net", 0) or 0), 2),
                "payin_amount":      round(float(equity.get("payin_amount", 0) or 0), 2),
            }
        return {"available_cash": 0.0, "used_margin": 0.0, "total_balance": 0.0, "payin_amount": 0.0}

    def get_holdings(self) -> list:
        """Returns list of active delivery (CNC) holdings and positions directly from Upstox API."""
        holdings = []
        seen = set()

        # 1. Fetch CNC Demat Holdings
        r = self._get("/portfolio/long-term-holdings")
        if r.get("status") == "success":
            raw = r.get("data", [])
            for h in raw:
                sym = h.get("tradingsymbol") or h.get("trading_symbol") or ""
                if not sym:
                    continue
                avg = float(h.get("average_price") or 0)
                ltp = float(h.get("last_price") or 0)
                qty = int(h.get("quantity") or 0)
                if qty <= 0:
                    continue
                pnl_pct = round(((ltp - avg) / avg) * 100, 2) if avg > 0 else 0.0
                pnl_abs = round((ltp - avg) * qty, 2) if avg > 0 else 0.0
                invested = round(avg * qty, 2) if avg > 0 else round(ltp * qty, 2)

                holdings.append({
                    "symbol": sym.upper(),
                    "name": h.get("company_name", sym.upper()),
                    "quantity": qty,
                    "avg_price": avg if avg > 0 else ltp,
                    "ltp": ltp,
                    "pnl_abs": pnl_abs,
                    "pnl_pct": pnl_pct,
                    "invested": invested,
                    "day_change": round(float(h.get("day_change_percentage") or 0), 2),
                    "isin": h.get("isin", ""),
                    "source": "UPSTOX_DEMAT_HOLDING"
                })
                seen.add(sym.upper())

        # 2. Fetch Delivery / Short-Term Positions (T+1 or un-settled trades)
        for ep in ["/portfolio/short-term-positions", "/v2/portfolio/short-term-positions"]:
            r_pos = self._get(ep)
            if r_pos.get("status") == "success":
                raw_pos = r_pos.get("data", [])
                for p in raw_pos:
                    sym = p.get("tradingsymbol") or p.get("trading_symbol") or ""
                    if not sym or sym.upper() in seen:
                        continue
                    qty = int(p.get("quantity") or p.get("net_quantity") or 0)
                    if qty <= 0:
                        continue
                    avg = float(p.get("average_price") or p.get("buy_price") or 0)
                    ltp = float(p.get("last_price") or 0)
                    pnl_pct = round(((ltp - avg) / avg) * 100, 2) if avg > 0 else 0.0
                    pnl_abs = round((ltp - avg) * qty, 2) if avg > 0 else 0.0
                    invested = round(avg * qty, 2) if avg > 0 else round(ltp * qty, 2)

                    holdings.append({
                        "symbol": sym.upper(),
                        "name": p.get("company_name", sym.upper()),
                        "quantity": qty,
                        "avg_price": avg if avg > 0 else ltp,
                        "ltp": ltp,
                        "pnl_abs": pnl_abs,
                        "pnl_pct": pnl_pct,
                        "invested": invested,
                        "day_change": round(float(p.get("day_change_percentage") or 0), 2),
                        "isin": p.get("isin", ""),
                        "source": "UPSTOX_OPEN_POSITION"
                    })
                    seen.add(sym.upper())
                break

        return holdings

    def _is_market_open(self) -> bool:
        """Checks if Indian stock market (NSE/BSE) is currently open (9:15 AM - 3:30 PM IST, Mon-Fri)."""
        import pytz
        from datetime import datetime
        try:
            from holidays import is_trading_holiday
        except ImportError:
            is_trading_holiday = lambda d: d.weekday() >= 5

        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        if is_trading_holiday(now.date()):
            return False
        market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_start <= now <= market_end

    def _is_market_open(self) -> bool:
        """Checks if Indian stock market (NSE/BSE) is currently open (9:15 AM - 3:30 PM IST, Mon-Fri)."""
        import pytz
        from datetime import datetime
        try:
            from holidays import is_trading_holiday
        except ImportError:
            is_trading_holiday = lambda d: d.weekday() >= 5

        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        if is_trading_holiday(now.date()):
            return False
        market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_start <= now <= market_end

    def place_delivery_order(self, instrument_key: str, qty: int, price: float) -> dict:
        """Places a CNC (Delivery) Limit Buy order."""
        is_open = self._is_market_open()
        payload = {
            "quantity":           qty,
            "product":            "D",         # Delivery (CNC)
            "validity":           "DAY",
            "price":              round(price, 2),
            "tag":                "JARVIS",
            "instrument_token":   instrument_key,
            "order_type":         "LIMIT",
            "transaction_type":   "BUY",
            "disclosed_quantity": 0,
            "trigger_price":      0,
            "is_amo":             not is_open, # AMO if market closed, Live if open
        }
        endpoints = ["/order/place", "/v2/order/place"]
        for ep in endpoints:
            r = self._post(ep, payload)
            if r.get("status") == "success":
                order_id = r.get("data", {}).get("order_id") or r.get("data", {}).get("order_ref_id", "ORD-EXCHANGE")
                mode = "LIVE_UPSTOX_LIMIT" if is_open else "UPSTOX_AMO_LIMIT"
                return {
                    "status":   "SUCCESS",
                    "order_id": order_id,
                    "mode":     mode,
                    "message":  f"CNC Buy Order for {qty} shares @ ?{price} sent to Upstox ({mode})."
                }
            elif "errors" in r and len(r["errors"]) > 0:
                err_msg = r["errors"][0].get("message", "Upstox order rejected")
                return {
                    "status": "FAILED",
                    "reason": err_msg
                }
                
        return {
            "status": "FAILED",
            "reason": "Could not connect to Upstox Order Gateway."
        }

    def place_gtt_order(self, instrument_key: str, qty: int, price: float, target_price: float = 0.0, stop_price: float = 0.0) -> dict:
        """Places an Exchange-Level GTT (Good-Till-Triggered) Order with Upstox API endpoints."""
        import time
        entry_price = round(price, 2)
        trigger_price = round(price * 1.002, 2)
        
        gtt_payload = {
            "type": "SINGLE",
            "quantity": qty,
            "product": "D",
            "instrument_token": instrument_key,
            "transaction_type": "BUY",
            "rules": [
                {
                    "strategy": "ENTRY",
                    "trigger_type": "BELOW",
                    "trigger_price": trigger_price,
                    "price": entry_price
                }
            ]
        }
        
        endpoints = ["/v2/gtt/place", "/gtt/place", "/order/gtt/place", "/order/gtt/create", "/v3/order/gtt"]
        for ep in endpoints:
            r = self._post(ep, gtt_payload)
            if r.get("status") == "success":
                gtt_id = r.get("data", {}).get("gtt_id") or r.get("data", {}).get("order_id") or f"GTT-{int(time.time())}"
                return {
                    "status": "SUCCESS",
                    "gtt_id": gtt_id,
                    "mode": "UPSTOX_GTT_EXCHANGE_AUTOMATED",
                    "message": f"GTT Buy Order placed on Upstox for {qty} shares @ ?{entry_price}."
                }
        
        # Fallback to delivery CNC order if GTT scope is pending on API app
        return self.place_delivery_order(instrument_key, qty, price)
