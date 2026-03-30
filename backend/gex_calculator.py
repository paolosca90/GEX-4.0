import asyncio
import logging
from datetime import datetime, timezone, timedelta
import os
import httpx
from db import get_db_pool

logger = logging.getLogger("gex_calculator")

class GEXEngine:
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.current_offset_es = 0.0
        self.current_offset_nq = 0.0

    async def update_offsets(self):
        """
        Periodically calculates the offset between Future and Spot index.
        Offset = Future Price - Spot Price
        Example: ESH26 - SPX = Offset_ES
        """
        while True:
            try:
                # Fetch latest ES! and NQ!
                es_row = await self.db_pool.fetchrow("SELECT price FROM futures_ticks WHERE symbol='US500' ORDER BY time DESC LIMIT 1")
                nq_row = await self.db_pool.fetchrow("SELECT price FROM futures_ticks WHERE symbol='US100' ORDER BY time DESC LIMIT 1")
                
                # Fetch latest SPX and QQQ (saved in the same table temporarily or queried directly)
                spx_row = await self.db_pool.fetchrow("SELECT price FROM futures_ticks WHERE symbol='SPX' ORDER BY time DESC LIMIT 1")
                qqq_row = await self.db_pool.fetchrow("SELECT price FROM futures_ticks WHERE symbol='QQQ' ORDER BY time DESC LIMIT 1")
                
                if es_row and spx_row:
                    self.current_offset_es = es_row['price'] - spx_row['price']
                    # logger.info(f"Updated ES Offset: {self.current_offset_es}")
                    
                if nq_row and qqq_row:
                    self.current_offset_nq = nq_row['price'] - qqq_row['price']
                    # logger.info(f"Updated NQ Offset: {self.current_offset_nq}")
                    
            except Exception as e:
                logger.error(f"Error calculating offset: {e}")
                
            await asyncio.sleep(1) # Recalculate every second

    async def fetch_tradier_options_chain(self, underlying: str, target_date: str):
        url = f"https://api.tradier.com/v1/markets/options/chains?symbol={underlying}&expiration={target_date}&greeks=true"
        headers = {
            "Authorization": f"Bearer {os.getenv('TRADIER_API_KEY', 'mVoOWSiu47rIQoSq2u2C0fZxOtwc')}",
            "Accept": "application/json"
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('options') and data['options'].get('option'):
                    return data['options']['option']
            else:
                logger.error(f"Tradier API Error for {underlying}: {resp.text}")
        return []

    async def calculate_0dte_gex_job(self):
        """
        Runs daily at 16:30 EST to fetch the next trading day's 0DTE options chain
        and calculate the Absolute GEX for each strike.
        GEX = Gamma * Open Interest * 100 * SpotPrice
        """
        logger.info("Executing 16:30 EST 0DTE GEX Calculation...")
        
        # 1. Determine Target Date
        # When market is closed (weekend or after hours), always use NEXT trading day.
        # This ensures Saturday/Sunday runs still calculate for Monday's 0DTE.
        now_est = datetime.now(timezone(timedelta(hours=-5)))
        market_close = now_est.replace(hour=16, minute=30, second=0, microsecond=0)

        target_date = now_est.date()
        # If after market close OR it's a weekend day, go to next trading day
        if now_est > market_close or target_date.weekday() >= 5:
            while target_date.weekday() >= 5:  # Skip weekend
                target_date += timedelta(days=1)
                
        target_date_str = target_date.strftime("%Y-%m-%d")
        calc_date = now_est.date()
        
        for underlying in ["SPX", "QQQ"]:
            # Fetch latest spot price for the GEX calculation
            spot_row = await self.db_pool.fetchrow("SELECT price FROM futures_ticks WHERE symbol=$1 ORDER BY time DESC LIMIT 1", underlying)
            spot_price = spot_row['price'] if spot_row else 0
            
            if spot_price == 0:
                logger.error(f"No spot price found for {underlying}, skipping GEX calculation.")
                continue

            # Fetch Option Chain from Tradier
            options = await self.fetch_tradier_options_chain(underlying, target_date_str)
            if not isinstance(options, list) or not options:
                logger.warning(f"No options data fetched for {underlying} on {target_date_str}")
                continue
                
            logger.info(f"Fetched {len(options)} options for {underlying} expiring {target_date_str}")
            
            # Aggregate Gamma and OI by Strike
            strike_data: dict[float, float] = {}
            for opt in options:
                strike = float(opt['strike'])
                opt_type = opt['option_type'] # 'call' or 'put'
                oi = float(opt.get('open_interest', 0))
                
                greeks = opt.get('greeks')
                if not greeks:
                    continue
                    
                gamma = float(greeks.get('gamma', 0))
                if gamma == 0 or oi == 0:
                    continue
                
                # GEX = Gamma * Open Interest * 100 * SpotPrice
                # Call GEX is positive, Put GEX is negative
                abs_gex = gamma * oi * 100 * spot_price
                if opt_type == 'put':
                    abs_gex = -abs_gex
                
                if strike not in strike_data:
                    strike_data[strike] = 0
                strike_data[strike] += abs_gex
                
            if not strike_data:
                logger.warning(f"No valid greeks/OI found for {underlying} on {target_date_str}")
                continue

            # Delete old profile for this target date just in case of a rerun
            await self.db_pool.execute(
                "DELETE FROM gex_profile WHERE target_date = $1 AND underlying = $2", 
                target_date, underlying
            )

            inserted = 0
            for strike, total_gex in strike_data.items():
                if total_gex == 0: continue
                # Insert into DB
                # translated_future_price is a legacy column required by schema
                await self.db_pool.execute("""
                    INSERT INTO gex_profile (calc_date, target_date, underlying, strike, total_gex, translated_future_price)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, calc_date, target_date, underlying, strike, total_gex, strike)
                inserted += 1
                
            logger.info(f"Successfully inserted {inserted} GEX levels for {underlying} into gex_profile.")

    async def _schedule_loop(self):
        while True:
            now_est = datetime.now(timezone(timedelta(hours=-5)))
            
            # Check if it's exactly 16:30 EST (with 1 min tolerance to run once)
            if now_est.hour == 16 and now_est.minute == 30:
                await self.calculate_0dte_gex_job()
                # Sleep for 61 seconds to avoid triggering twice in the same minute
                await asyncio.sleep(61)
                
            await asyncio.sleep(20)

    def start_background_tasks(self):
        asyncio.create_task(self.update_offsets())
        asyncio.create_task(self._schedule_loop())

async def start_gex_engine():
    pool = await get_db_pool()
    engine = GEXEngine(pool)
    engine.start_background_tasks()
    
    # Keep alive
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(start_gex_engine())
