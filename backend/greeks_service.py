"""
Greeks Service - fetches option chain from Tradier with ORATS Greeks.
Caches results in memory with 60s TTL during RTH.
"""
import asyncio
import os
import time
import logging
import httpx
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("greeks_service")

TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "mVoOWSiu47rIQoSq2u2C0fZxOtwc")
TRADIER_CHAIN_URL = "https://api.tradier.com/v1/markets/options/chains"
TRADIER_EXPIRATIONS_URL = "https://api.tradier.com/v1/markets/options/expirations"
TRADIER_QUOTES_URL = "https://api.tradier.com/v1/markets/quotes"

# SPX and QQQ both have daily expirations on Tradier with ORATS greeks.
# Query them directly — no mapping needed.
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

    async def _get_spot_from_quotes(self, symbol: str) -> float:
        """Get spot price from Tradier quotes endpoint."""
        headers = {
            "Authorization": f"Bearer {TRADIER_API_KEY}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{TRADIER_QUOTES_URL}?symbols={symbol}", headers=headers)
                if resp.status_code == 200:
                    quotes = resp.json().get("quotes", {}).get("quote", [])
                    if isinstance(quotes, dict):
                        quotes = [quotes]
                    if quotes:
                        last = quotes[0].get("last")
                        if last:
                            return float(last)
        except Exception as e:
            logger.error(f"Quotes fetch error: {e}")
        return 0.0

    async def _fetch_chain(self, underlying: str) -> list:
        """Fetch option chain from Tradier with greeks=true.
        Queries available expirations first, then tries each until we get options."""
        symbol = CHAIN_SYMBOLS.get(underlying, underlying)
        headers = {
            "Authorization": f"Bearer {TRADIER_API_KEY}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # First get available expirations (includeAllRoots to get SPXW weeklys too)
                exp_url = f"{TRADIER_EXPIRATIONS_URL}?symbol={symbol}&includeAllRoots=true"
                exp_resp = await client.get(exp_url, headers=headers)
                available_dates = []
                if exp_resp.status_code == 200:
                    exp_data = exp_resp.json()
                    available_dates = exp_data.get("expirations", {}).get("date", [])

                if not available_dates:
                    logger.warning(f"No expirations found for {underlying} ({symbol})")
                    return []

                # Probe up to 5 expirations concurrently; return first with options
                async def try_expiry(exp: str):
                    url = f"{TRADIER_CHAIN_URL}?symbol={symbol}&expiration={exp}&greeks=true"
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        opts = data.get("options", {}).get("option", [])
                        if opts:
                            return opts, exp
                    return None, exp

                # Fire all requests in parallel; first successful one wins
                results = await asyncio.gather(*[try_expiry(exp) for exp in available_dates[:5]])
                for options, exp in results:
                    if options:
                        logger.info(f"Tradier chain OK: {underlying} ({symbol}) exp={exp} | {len(options)} options")
                        return options
                logger.warning(f"No chain data for {underlying} ({symbol}) across {[exp for exp in available_dates[:5]]}")
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

        # Get spot price from Tradier quotes endpoint
        chain_symbol = CHAIN_SYMBOLS.get(underlying, underlying)
        spot = await self._get_spot_from_quotes(chain_symbol)
        if not spot:
            # Fallback: try to infer from strike range + greeks
            logger.warning(f"Spot price unavailable from quotes for {chain_symbol}, skipping ATM filter")
            spot = 0.0

        if spot > 0:
            lower = spot * 0.95
            upper = spot * 1.05
            filtered = [o for o in raw_options if lower <= o.get("strike", 0) <= upper]
        else:
            # Last resort: no filter, use all options
            filtered = raw_options

        logger.info(f"Greeks filter: {underlying} spot={spot} | {len(filtered)}/{len(raw_options)} options in ATM±5%")

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

    async def get_volatility_surface(self, underlying: str) -> dict:
        """
        Fetch volatility surface for 0DTE + 1DTE expirations.
        Returns strikes with IV, delta, gamma, call_iv, put_iv, skew per strike.
        """
        symbol = CHAIN_SYMBOLS.get(underlying, underlying)
        headers = {
            "Authorization": f"Bearer {TRADIER_API_KEY}",
            "Accept": "application/json",
        }

        # Step 1: get available expirations
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                exp_url = f"{TRADIER_EXPIRATIONS_URL}?symbol={symbol}&includeAllRoots=true"
                exp_resp = await client.get(exp_url, headers=headers)
                available_dates = []
                if exp_resp.status_code == 200:
                    exp_data = exp_resp.json()
                    raw_dates = exp_data.get("expirations", {}).get("date", [])
                    if isinstance(raw_dates, list):
                        available_dates = raw_dates[:5]  # take first 5 expirations
        except Exception as e:
            logger.error(f"Expirations fetch error: {e}")
            return {"error": str(e), "surface": [], "underlying": underlying}

        # Step 2: fetch chains for up to 2 expirations in parallel
        async def fetch_single_expiry(exp: str):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    url = f"{TRADIER_CHAIN_URL}?symbol={symbol}&expiration={exp}&greeks=true"
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        opts = data.get("options", {}).get("option", [])
                        if opts:
                            return opts, exp
            except Exception as e:
                logger.error(f"Chain fetch error for {exp}: {e}")
            return [], exp

        # Only use first 2 expirations (0DTE + 1DTE)
        results = await asyncio.gather(*[fetch_single_expiry(exp) for exp in available_dates[:2]])

        surface = []
        for options, exp in results:
            if not options:
                continue

            strikes_map = {}
            for opt in options:
                strike = float(opt.get("strike", 0))
                greeks = opt.get("greeks") or {}
                option_type = opt.get("option_type")
                mid_iv = greeks.get("mid_iv") or 0.0

                if strike not in strikes_map:
                    strikes_map[strike] = {
                        "strike": strike,
                        "delta": greeks.get("delta"),
                        "gamma": greeks.get("gamma"),
                    }
                if option_type == "call":
                    strikes_map[strike]["call_iv"] = mid_iv
                else:
                    strikes_map[strike]["put_iv"] = mid_iv

            # Compute skew and ATM flag per strike
            for strike, data in strikes_map.items():
                call_iv = data.get("call_iv", 0)
                put_iv = data.get("put_iv", 0)
                data["iv"] = (call_iv + put_iv) / 2 if call_iv and put_iv else (call_iv or put_iv or 0)
                data["skew"] = put_iv - call_iv if call_iv and put_iv else 0

            strikes_list = list(strikes_map.values())

            # Determine DTE
            try:
                exp_dt = datetime.strptime(exp, "%Y-%m-%d").date()
                today = datetime.now(timezone(timedelta(hours=-5))).date()
                dte = max(0, (exp_dt - today).days)
            except Exception:
                dte = 0

            surface.append({
                "expiration": exp,
                "days_to_expiry": dte,
                "strikes": strikes_list,
            })

        # Get spot price
        spot = await self._get_spot_from_quotes(symbol)
        if not spot:
            # Fallback to any available strike midpoint
            if surface and surface[0]["strikes"]:
                spot = surface[0]["strikes"][len(surface[0]["strikes"])//2]["strike"]

        return {
            "underlying": underlying,
            "spot_price": spot,
            "surface": surface,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
