"""
Greeks Service - fetches option chain from Tradier with ORATS Greeks.
Caches results in memory with 60s TTL during RTH.
"""
import os
import time
import logging
import httpx
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("greeks_service")

TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "dHegDyUwRPC6Os2qaiGBYtvAEOQC")
TRADIER_BASE = "https://api.tradier.com/v1/markets/options/chains"

CHAIN_SYMBOLS = {
    "SPX": "SPX",
    "QQQ": "QQQ",
}


class GreeksCache:
    """Per-underlying cache with TTL."""
    def __init__(self, ttl_seconds: int = 60):
        self._cache: dict = {}
        self._ttl = ttl_seconds

    def get(self, underlying: str):
        entry = self._cache.get(underlying)
        if entry and time.time() - entry["ts"] < self._ttl:
            return entry["data"]
        return None

    def set(self, underlying: str, data: dict):
        self._cache[underlying] = {"ts": time.time(), "data": data}


class GreeksService:
    def __init__(self, db_pool=None):
        self.db_pool = db_pool
        self.cache = GreeksCache(ttl_seconds=60)

    async def _get_target_date(self) -> str:
        """Get the current 0DTE date."""
        est = timezone(timedelta(hours=-5))
        now_est = datetime.now(est)
        market_close = now_est.replace(hour=16, minute=30, second=0, microsecond=0)
        if now_est > market_close:
            next_day = now_est.date() + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            return next_day.isoformat()
        return now_est.date().isoformat()

    async def _fetch_chain(self, underlying: str) -> list:
        """Fetch option chain from Tradier with greeks=true."""
        target_date = await self._get_target_date()
        symbol = CHAIN_SYMBOLS.get(underlying, underlying)
        url = f"{TRADIER_BASE}?symbol={symbol}&expiration={target_date}&greeks=true"
        headers = {
            "Authorization": f"Bearer {TRADIER_API_KEY}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    options = data.get("options", {}).get("option", [])
                    return options
                logger.error(f"Tradier API error {underlying}: {resp.status_code}")
        except Exception as e:
            logger.error(f"Tradier fetch error: {e}")
        return []

    async def get_chain_greeks(self, underlying: str) -> dict:
        """Return chain Greeks for ATM +/- 5% strikes."""
        cached = self.cache.get(underlying)
        if cached:
            return cached

        raw_options = await self._fetch_chain(underlying)
        if not raw_options:
            return {"chain": [], "summary": {}, "underlying": underlying, "spot": None}

        spot = None
        for opt in raw_options:
            greeks = opt.get("greeks") or {}
            if greeks.get("mid_iv"):
                spot = opt.get("underlying_price")
                break
        if not spot:
            spot = raw_options[0].get("underlying_price", 0)

        lower = spot * 0.95
        upper = spot * 1.05
        filtered = [o for o in raw_options if lower <= o.get("strike", 0) <= upper]

        chain = []
        for opt in filtered:
            greeks = opt.get("greeks") or {}
            chain.append({
                "strike": opt.get("strike"),
                "option_type": opt.get("option_type"),
                "expiry": opt.get("expiration_date"),
                "delta": greeks.get("delta"),
                "gamma": greeks.get("gamma"),
                "theta": greeks.get("theta"),
                "vega": greeks.get("vega"),
                "bid_iv": greeks.get("bid_iv"),
                "mid_iv": greeks.get("mid_iv"),
                "ask_iv": greeks.get("ask_iv"),
                "smv_vol": greeks.get("smv_vol"),
                "open_interest": opt.get("open_interest"),
                "volume": opt.get("volume"),
            })

        call_ivs = [c["mid_iv"] for c in chain if c["mid_iv"] and c["option_type"] == "call"]
        put_ivs = [c["mid_iv"] for c in chain if c["mid_iv"] and c["option_type"] == "put"]
        gammas = [c["gamma"] for c in chain if c["gamma"]]
        deltas = [c["delta"] for c in chain if c["delta"]]
        thetas = [c["theta"] for c in chain if c["theta"]]

        summary = {
            "total_gamma": sum(gammas) if gammas else None,
            "net_delta": sum(deltas) if deltas else None,
            "avg_theta": sum(thetas) / len(thetas) if thetas else None,
            "call_iv_mean": sum(call_ivs) / len(call_ivs) if call_ivs else None,
            "put_iv_mean": sum(put_ivs) / len(put_ivs) if put_ivs else None,
            "skew": (sum(put_ivs)/len(put_ivs) - sum(call_ivs)/len(call_ivs)) if call_ivs and put_ivs else None,
            "iv_rank": None,
        }

        result = {
            "underlying": underlying,
            "spot": spot,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chain": chain,
            "summary": summary,
        }
        self.cache.set(underlying, result)
        return result

    async def get_greeks_summary(self, underlying: str) -> dict:
        """Return aggregated Greeks summary per expiry."""
        chain_data = await self.get_chain_greeks(underlying)
        if not chain_data["chain"]:
            return {"error": "No data available", "underlying": underlying}

        by_expiry: dict = {}
        for opt in chain_data["chain"]:
            expiry = opt.get("expiry", "unknown")
            if expiry not in by_expiry:
                by_expiry[expiry] = {
                    "expiry": expiry,
                    "dte": 0,
                    "total_gamma": 0,
                    "net_delta": 0,
                    "theta_sum": 0,
                    "theta_count": 0,
                    "iv_sum": 0,
                    "iv_count": 0,
                }
            e = by_expiry[expiry]
            if opt.get("gamma"):
                e["total_gamma"] += opt["gamma"]
            if opt.get("delta"):
                e["net_delta"] += opt["delta"]
            if opt.get("theta"):
                e["theta_sum"] += opt["theta"]
                e["theta_count"] += 1
            if opt.get("mid_iv"):
                e["iv_sum"] += opt["mid_iv"]
                e["iv_count"] += 1

        greeks_by_expiry = []
        for e in by_expiry.values():
            greeks_by_expiry.append({
                "expiry": e["expiry"],
                "dte": e["dte"],
                "total_gamma": round(e["total_gamma"], 6),
                "net_delta": round(e["net_delta"], 4),
                "avg_theta": round(e["theta_sum"] / e["theta_count"], 4) if e["theta_count"] else None,
                "atm_iv": round(e["iv_sum"] / e["iv_count"], 4) if e["iv_count"] else None,
            })

        s = chain_data["summary"]
        atm_iv = s.get("call_iv_mean")
        iv_context = {
            "atm_iv": round(atm_iv, 4) if atm_iv else None,
            "iv_rank_52w": None,
            "iv_percentile_52w": None,
            "skew_25delta": round(s["skew"], 4) if s.get("skew") else None,
            "term_structure": "unknown",
        }

        regime = "unknown"
        total_gex = 0
        if self.db_pool:
            try:
                row = await self.db_pool.fetchrow("""
                    SELECT SUM(total_gex) as total_gex FROM gex_profile
                    WHERE target_date = CURRENT_DATE AND underlying = $1
                """, underlying)
                if row and row["total_gex"]:
                    total_gex = float(row["total_gex"])
                    regime = "long_gamma" if total_gex > 0 else "short_gamma"
            except Exception:
                pass

        return {
            "underlying": underlying,
            "spot": chain_data["spot"],
            "updated_at": chain_data["timestamp"],
            "regime": regime,
            "total_gex": total_gex,
            "net_delta_exposure": round(s.get("net_delta", 0) or 0, 4),
            "avg_theta_decay": round(s["avg_theta"], 4) if s.get("avg_theta") else None,
            "iv_context": iv_context,
            "greeks_by_expiry": greeks_by_expiry,
        }