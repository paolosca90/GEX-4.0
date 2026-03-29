"""
OI Tracker — fetches OI snapshots from Tradier, computes delta vs close,
derives retail/block breakdown from flow, provides buildup API.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

logger = logging.getLogger("oi_tracker")

RETAIL_THRESHOLD = 100  # contracts


class OITracker:
    def __init__(self, db_pool):
        self.db = db_pool
        self.prev_close_oi: Dict[str, Dict[float, int]] = {}  # underlying → strike → oi

    async def load_prev_close_oi(self, underlying: str) -> None:
        """Load OI close from most recent pre-market snapshot."""
        rows = await self.db.fetch("""
            SELECT strike, oi_total
            FROM oi_snapshots
            WHERE underlying = $1
              AND time < (CURRENT_DATE AT TIME ZONE 'America/New_York' + INTERVAL '9 hours')
            ORDER BY time DESC
            LIMIT 1
        """, underlying)
        self.prev_close_oi[underlying] = {float(r["strike"]): int(r["oi_total"]) for r in rows}

    async def fetch_oi_from_tradier(self, underlying: str) -> List[dict]:
        """Fetch OI per strike from Tradier chain (open_interest field)."""
        import httpx
        import os
        TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "mVoOWSiu47rIQoSq2u2C0fZxOtwc")
        CHAIN_URL = "https://api.tradier.com/v1/markets/options/chains"
        EXP_URL = "https://api.tradier.com/v1/markets/options/expirations"
        SYMBOL = "SPX" if underlying == "SPX" else "QQQ"
        headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Get first expiration (0DTE)
                exp_resp = await client.get(f"{EXP_URL}?symbol={SYMBOL}", headers=headers)
                if exp_resp.status_code != 200:
                    return []
                dates = exp_resp.json().get("expirations", {}).get("date", [])
                if not dates:
                    return []
                chain_resp = await client.get(
                    f"{CHAIN_URL}?symbol={SYMBOL}&expiration={dates[0]}",
                    headers=headers
                )
                if chain_resp.status_code != 200:
                    return []
                options = chain_resp.json().get("options", {}).get("option", [])
                result = []
                for opt in options:
                    oi = opt.get("open_interest")
                    if oi is None:
                        continue
                    result.append({
                        "strike": float(opt["strike"]),
                        "oi_total": int(oi),
                        "side": opt["option_type"].upper(),
                    })
                logger.info(f"Tradier OI: {underlying} | {len(result)} strikes with OI")
                return result
        except Exception as e:
            logger.error(f"Tradier OI fetch error: {e}")
            return []

    async def derive_retail_block_delta(self, underlying: str, strike: float, lookback_minutes: int = 120) -> tuple[int, int]:
        """Aggregate flow from options_flow to derive retail/block OI delta."""
        rows = await self.db.fetch("""
            SELECT
                SUM(CASE WHEN trade_size < $2 AND sentiment = 'BUY' THEN 1
                         WHEN trade_size < $2 AND sentiment = 'SELL' THEN -1 ELSE 0 END) AS retail_delta,
                SUM(CASE WHEN trade_size >= $2 AND sentiment = 'BUY' THEN 1
                         WHEN trade_size >= $2 AND sentiment = 'SELL' THEN -1 ELSE 0 END) AS block_delta
            FROM options_flow
            WHERE underlying = $1
              AND strike = $3
              AND time > NOW() - make_interval(mins => $4)
        """, underlying, RETAIL_THRESHOLD, strike, lookback_minutes)
        r = rows[0]
        retail = int(r["retail_delta"] or 0)
        block = int(r["block_delta"] or 0)
        return retail, block

    async def snapshot_and_store(self, underlying: str) -> None:
        """Fetch Tradier OI, compute delta vs close, derive retail/block, store snapshot."""
        if underlying not in self.prev_close_oi:
            await self.load_prev_close_oi(underlying)

        raw_oi = await self.fetch_oi_from_tradier(underlying)
        if not raw_oi:
            logger.warning(f"No OI data from Tradier for {underlying}, skipping snapshot")
            return

        prev = self.prev_close_oi.get(underlying, {})
        records = []
        for entry in raw_oi:
            strike = entry["strike"]
            oi_total = entry["oi_total"]
            prev_oi = prev.get(strike, oi_total)
            oi_delta = oi_total - prev_oi
            retail, block = await self.derive_retail_block_delta(underlying, strike)
            records.append({
                "time": datetime.now(timezone.utc),
                "underlying": underlying,
                "strike": strike,
                "oi_total": oi_total,
                "oi_delta": oi_delta,
                "oi_delta_retail": retail,
                "oi_delta_block": block,
                "side": entry["side"],
            })

        if records:
            await self.db.executemany("""
                INSERT INTO oi_snapshots (time, underlying, strike, oi_total, oi_delta, oi_delta_retail, oi_delta_block, side)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (time, underlying, strike) DO UPDATE SET
                    oi_total = EXCLUDED.oi_total,
                    oi_delta = EXCLUDED.oi_delta,
                    oi_delta_retail = EXCLUDED.oi_delta_retail,
                    oi_delta_block = EXCLUDED.oi_delta_block
            """, [(r["time"], r["underlying"], r["strike"], r["oi_total"],
                   r["oi_delta"], r["oi_delta_retail"], r["oi_delta_block"], r["side"]) for r in records])
            logger.info(f"OI snapshot stored: {underlying} | {len(records)} strikes")

    def get_buildup(self, underlying: str) -> dict:
        """Return top 3 calls + top 3 puts by absolute oi_delta from latest snapshot."""
        rows = self.db.fetch("""
            SELECT DISTINCT ON (strike)
                strike, oi_delta, oi_delta_retail, oi_delta_block, side
            FROM oi_snapshots
            WHERE underlying = $1
            ORDER BY strike, time DESC
        """, underlying)

        by_side = {"CALL": [], "PUT": []}
        for r in rows:
            side = r["side"].upper()
            if side in by_side:
                by_side[side].append({
                    "strike": float(r["strike"]),
                    "oi_delta": int(r["oi_delta"]),
                    "oi_delta_retail": int(r["oi_delta_retail"]),
                    "oi_delta_block": int(r["oi_delta_block"]),
                    "side": side.lower(),
                })

        for side in by_side:
            by_side[side].sort(key=lambda x: abs(x["oi_delta"]), reverse=True)
            by_side[side] = by_side[side][:3]

        return {
            "calls": by_side["CALL"],
            "puts": by_side["PUT"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }