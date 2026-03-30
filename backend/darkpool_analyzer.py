"""
Dark Pool Analyzer - downloads FINRA Reg SHO daily short volume.
Calculates DIX (Dark Index) for SPY and QQQ.
"""
import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

logger = logging.getLogger("darkpool_analyzer")

FINRA_URL = "https://otctransparency.finra.com/api/shortsale/volume"

FINRA_SYMBOL_MAP = {
    "SPX": "SPY",
    "QQQ": "QQQ",
}


class DarkPoolAnalyzer:
    def __init__(self, db_pool=None):
        self.db_pool = db_pool
        self.cache: dict[str, dict] = {}

    async def download_and_parse(self, target_date: Optional[str] = None) -> dict:
        """
        Download FINRA Reg SHO data for a given date.
        Returns {symbol: {short_volume, total_volume, short_ratio, dix}}.
        """
        if not target_date:
            est = timezone(timedelta(hours=-5))
            yesterday = datetime.now(est).date() - timedelta(days=1)
            while yesterday.weekday() >= 5:
                yesterday -= timedelta(days=1)
            target_date = yesterday.strftime("%Y%m%d")

        url = f"{FINRA_URL}?date={target_date}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.error(f"FINRA download error: {resp.status_code}")
                    return {}

                text = resp.text
                reader = csv.DictReader(io.StringIO(text), delimiter="|")
                results = {}

                for row in reader:
                    symbol = row.get("symbol", "").strip()
                    if symbol not in ("SPY", "QQQ"):
                        continue

                    short_vol = int(row.get("shortVolume", 0))
                    total_vol = int(row.get("totalVolume", 0))

                    if total_vol > 0:
                        short_ratio = short_vol / total_vol
                        dix = 1.0 - short_ratio
                    else:
                        short_ratio = 0
                        dix = 0

                    results[symbol] = {
                        "short_volume": short_vol,
                        "total_volume": total_vol,
                        "short_ratio": round(short_ratio, 4),
                        "dix": round(dix, 4),
                        "dark_volume_estimate": short_vol,
                    }

                return results

        except Exception as e:
            logger.error(f"FINRA download error: {e}")
            return {}

    async def update_daily(self):
        """Download latest data and store in DB."""
        results = await self.download_and_parse()
        if not results:
            logger.warning("No FINRA data downloaded")
            return

        est = timezone(timedelta(hours=-5))
        yesterday = datetime.now(est).date() - timedelta(days=1)
        while yesterday.weekday() >= 5:
            yesterday -= timedelta(days=1)

        for finra_sym, data in results.items():
            underlying = "SPX" if finra_sym == "SPY" else "QQQ"

            self.cache[underlying] = {
                "date": str(yesterday),
                "underlying": underlying,
                **data,
            }

            if self.db_pool:
                try:
                    await self.db_pool.execute("""
                        INSERT INTO darkpool_daily (date, underlying, short_volume, total_volume,
                                                    short_ratio, dix, dark_volume_estimate, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                        ON CONFLICT (date, underlying) DO UPDATE SET
                            short_volume = EXCLUDED.short_volume,
                            total_volume = EXCLUDED.total_volume,
                            short_ratio = EXCLUDED.short_ratio,
                            dix = EXCLUDED.dix,
                            dark_volume_estimate = EXCLUDED.dark_volume_estimate,
                            updated_at = NOW()
                    """, yesterday, underlying, data["short_volume"], data["total_volume"],
                         data["short_ratio"], data["dix"], data["dark_volume_estimate"])
                except Exception as e:
                    logger.error(f"Darkpool DB error: {e}")

        logger.info(f"Dark pool data updated for {list(results.keys())}")

    async def get_dix(self, underlying: str) -> dict:
        """Get latest DIX data for an underlying."""
        if underlying in self.cache:
            return self.cache[underlying]

        if self.db_pool:
            row = await self.db_pool.fetchrow("""
                SELECT date, underlying, short_volume, total_volume,
                       short_ratio, dix, dark_volume_estimate
                FROM darkpool_daily WHERE underlying = $1
                ORDER BY date DESC LIMIT 1
            """, underlying)
            if row:
                return dict(row)

        return {"underlying": underlying, "dix": None, "short_ratio": None, "message": "No data"}

    async def get_history(self, underlying: str, days: int = 30) -> list:
        """Get historical DIX data."""
        if not self.db_pool:
            return []
        rows = await self.db_pool.fetch("""
            SELECT date, underlying, short_volume, total_volume,
                   short_ratio, dix, dark_volume_estimate
            FROM darkpool_daily WHERE underlying = $1
            ORDER BY date DESC LIMIT $2
        """, underlying, days)
        return [dict(r) for r in rows]