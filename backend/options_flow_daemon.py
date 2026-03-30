import asyncio
import os
import json
import logging
import math
from datetime import datetime, timezone, time
from collections import deque
try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz # fallback
import websockets
import httpx
from db import get_db_pool

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("flow_daemon")

TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "mVoOWSiu47rIQoSq2u2C0fZxOtwc")
TRADIER_WS_URL = "wss://ws.tradier.com/v1/markets/events"
TRADIER_REST_URL = "https://api.tradier.com/v1"

SYMBOLS = ["SPX", "QQQ"]

# We will collect flow data for exactly 1 minute at a time, then insert.
current_minute_data = {} # { underlying: { call_premium, put_premium, call_volume, put_volume } }
last_insert_minute = None

# We will collect flow data roughly every 2 seconds for the live tick chart
current_tick_data = {} 
last_insert_tick = None

# Rolling buffers to keep track of the last 5 minutes of ticks
# 5 minutes / 2 seconds = 150 items max
rolling_buffer = {
    "SPX": deque(maxlen=150),
    "QQQ": deque(maxlen=150)
}

def reset_tick_data():
    global current_tick_data
    current_tick_data = {
        "SPX": { "call_premium": 0, "put_premium": 0, "call_volume": 0, "put_volume": 0 },
        "QQQ": { "call_premium": 0, "put_premium": 0, "call_volume": 0, "put_volume": 0 }
    }
reset_tick_data()

latest_quotes = {} # { option_symbol: { bid: float, ask: float } }
latest_spot = {"SPX": 0.0, "QQQ": 0.0}

async def update_spot_prices(db_pool):
    """Periodically fetch the latest spot price to determine OTM/ITM status."""
    while True:
        try:
            for sym in SYMBOLS:
                row = await db_pool.fetchrow(f"SELECT price FROM futures_ticks WHERE symbol='{sym}' ORDER BY time DESC LIMIT 1")
                if row:
                    latest_spot[sym] = float(row['price'])
        except Exception as e:
            logger.error(f"Error fetching spot prices: {e}")
        await asyncio.sleep(5)

async def fetch_0dte_option_symbols(symbol, db_pool=None):
    """Fetch exactly the same list of 0DTE symbols that the GEX calculator uses."""
    ny_tz = None
    try:
        ny_tz = ZoneInfo("America/New_York")
    except:
        pass

    now_ny = datetime.now(ny_tz) if ny_tz else datetime.now()
    today_date = now_ny.date()

    # Get spot price for filtering
    spot = 0.0
    if db_pool:
        try:
            row = await db_pool.fetchrow(f"SELECT price FROM futures_ticks WHERE symbol='{symbol}' ORDER BY time DESC LIMIT 1")
            if row:
                spot = float(row['price'])
        except:
            pass

    async with httpx.AsyncClient() as client:
        try:
            exp_resp = await client.get(
                f"{TRADIER_REST_URL}/markets/options/expirations?symbol={symbol}&includeAllRoots=true",
                headers={"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}
            )
            if exp_resp.status_code != 200:
                logger.error(f"Failed to fetch expirations for {symbol}")
                return []

            exp_data = exp_resp.json()
            date_list = exp_data.get('expirations', {}).get('date', [])
            if not date_list:
                return []
            if isinstance(date_list, str):
                date_list = [date_list]

            is_after_hours = now_ny.time() >= time(16, 30)
            valid_dates = []
            for d_str in date_list:
                d_obj = datetime.strptime(d_str, '%Y-%m-%d').date()
                if d_obj > today_date:
                    valid_dates.append(d_str)
                elif d_obj == today_date and not is_after_hours:
                    valid_dates.append(d_str)

            if not valid_dates:
                valid_dates = date_list

            target_date = valid_dates[0]

            url = f"{TRADIER_REST_URL}/markets/options/chains?symbol={symbol}&expiration={target_date}"
            chain_resp = await client.get(
                url, headers={"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}
            )

            if chain_resp.status_code == 200:
                data = chain_resp.json()
                options = data.get('options', {}).get('option', [])
                if isinstance(options, dict):
                    options = [options]

                # Filter to only ATM options (within 5% of spot) and limit to 200 per symbol
                filtered = []
                for opt in options:
                    strike = float(opt.get('strike', 0))
                    if strike > 0:
                        distance_pct = abs(spot - strike) / spot if spot > 0 else 999
                        if distance_pct <= 0.05:  # Within 5% of spot
                            filtered.append(opt['symbol'])
                            if len(filtered) >= 200:
                                break

                logger.info(f"Filtered {symbol} to {len(filtered)} ATM options (from {len(options)} total)")
                return filtered
            else:
                return []
        except Exception as e:
            logger.error(f"Exception fetching chain for {symbol}: {e}")
            return []

async def create_tradier_session():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TRADIER_REST_URL}/markets/events/session",
            headers={"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}
        )
        if response.status_code == 200:
            data = response.json()
            return data['stream']['sessionid'], data['stream']['url']
        return None, None

last_trade_prices = {}

def calculate_delta_approx(strike: float, spot: float, is_call: bool) -> float:
    """
    Approximate delta based on moneyness (distance of strike from spot).
    This is a simplified model - real delta comes from options pricing model.

    For ATM (strike ≈ spot): delta ≈ 0.50 for calls, -0.50 for puts
    For OTM: delta approaches 0
    For ITM: delta approaches 1 (calls) or -1 (puts)
    """
    if spot <= 0 or strike <= 0:
        return 0.5 if is_call else -0.5

    moneyness = spot / strike if strike > 0 else 1.0

    if is_call:
        if moneyness >= 1.05:  # >5% ITM
            return 0.90
        elif moneyness >= 1.02:  # 2-5% ITM
            return 0.70
        elif moneyness >= 0.98:  # 2% OTM to 2% ITM (ATM)
            return 0.50
        elif moneyness >= 0.95:  # 5% OTM
            return 0.25
        else:  # >5% OTM
            return 0.05
    else:  # put
        if moneyness <= 0.95:  # >5% ITM (put is ITM when strike < spot)
            return -0.90
        elif moneyness <= 0.98:  # 2-5% ITM
            return -0.70
        elif moneyness >= 1.02:  # 2% OTM to ATM
            return -0.50
        elif moneyness >= 1.05:  # 5% OTM
            return -0.25
        else:  # >5% OTM
            return -0.05

def determine_sentiment(trade_price, bid, ask, opt_sym):
    """Determine if trade was bought or sold based on proximity to Bid/Ask or previous tick."""
    if bid == 0 and ask == 0:
        # Tick-test fallback
        last_price = last_trade_prices.get(opt_sym)
        if last_price is not None:
            if trade_price > last_price:
                return 'BUY'
            elif trade_price < last_price:
                return 'SELL'
            else:
                return 'NONE' # No change
        return 'UNKNOWN'
    
    mid = (bid + ask) / 2
    spread = ask - bid
    
    # 1. Spread Neutrality: If spread is wide (e.g., > $0.50), require trade to be closer to bounds
    if spread > 0.50:
        core_threshold = spread * 0.25 # Must be within 25% of bid/ask to be considered directional
        if trade_price >= ask - core_threshold:
            return 'BUY'
        elif trade_price <= bid + core_threshold:
            return 'SELL'
        else:
            return 'NONE' # Too close to mid on a wide spread
            
    # Normal spread evaluation
    if trade_price >= ask:
        return 'BUY'
    elif trade_price <= bid:
        return 'SELL'
    elif trade_price > mid:
        return 'BUY' # Leans Buy
    elif trade_price < mid:
        return 'SELL' # Leans Sell
    else:
        return 'NONE' # Exactly mid

def reset_minute_data():
    global current_minute_data
    current_minute_data = {
        "SPX": { "call_premium": 0, "put_premium": 0, "call_volume": 0, "put_volume": 0 },
        "QQQ": { "call_premium": 0, "put_premium": 0, "call_volume": 0, "put_volume": 0 }
    }

async def flow_daemon():
    global last_insert_minute, last_insert_tick
    logger.info("Starting Options Flow Daemon...")
    db_pool = await get_db_pool()
    reset_minute_data()
    raw_trades_buffer = []
    
    # Start background task to keep spot prices fresh for OTM filtering
    asyncio.create_task(update_spot_prices(db_pool))
    
    while True:
        try:
            # 1. Fetch Option Symbols
            all_symbols = []
            for underlying in SYMBOLS:
                syms = await fetch_0dte_option_symbols(underlying, db_pool)
                all_symbols.extend(syms)
                
            if not all_symbols:
                logger.warning("No options symbols found. Retrying in 60s.")
                await asyncio.sleep(60)
                continue
                
            logger.info(f"Subscribing to {len(all_symbols)} options for Net Flow...")

            # 2. Start Session
            session_id, _ = await create_tradier_session()
            if not session_id:
                logger.error(f"Failed to create Tradier session")
                await asyncio.sleep(10)
                continue

            async with websockets.connect(TRADIER_WS_URL) as ws:
                # API limit payload size, so batch them if needed, but Tradier accepts huge lists.
                payload = {
                    "events": ["trade", "quote"],
                    "sessionid": session_id,
                    "symbols": all_symbols,
                    "linebreak": True
                }
                await ws.send(json.dumps(payload))
                
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
                        data = json.loads(msg)
                    except asyncio.TimeoutError:
                        # Periodic ping if no volume
                        now = datetime.now(timezone.utc)
                        if last_insert_tick and (now - last_insert_tick).total_seconds() >= 2:
                            for u in SYMBOLS:
                                t = current_tick_data[u]
                                # Add current 2s tick to the rolling buffer
                                rolling_buffer[u].append({
                                    "time": now,
                                    "call_premium": t['call_premium'],
                                    "put_premium": t['put_premium'],
                                    "call_volume": t['call_volume'],
                                    "put_volume": t['put_volume']
                                })
                                
                                # Prune old items from buffer (older than 5 minutes = 300s)
                                while rolling_buffer[u] and (now - rolling_buffer[u][0]["time"]).total_seconds() > 300:
                                    rolling_buffer[u].popleft()
                                    
                                # Calculate 1m sum (premium, volume)
                                items_1m = [item for item in rolling_buffer[u] if (now - item["time"]).total_seconds() <= 60]
                                sum_1m_cp = sum(item["call_premium"] for item in items_1m)
                                sum_1m_pp = sum(item["put_premium"] for item in items_1m)
                                sum_1m_cv = sum(item["call_volume"] for item in items_1m)
                                sum_1m_pv = sum(item["put_volume"] for item in items_1m)
                                
                                # Calculate 5m sum (drift)
                                sum_5m_cp = sum(item["call_premium"] for item in rolling_buffer[u])
                                sum_5m_pp = sum(item["put_premium"] for item in rolling_buffer[u])
                                sum_5m_drift = sum_5m_cp - sum_5m_pp
                                
                                # Only write if we have some data in the buffers to prevent dead zeros
                                if sum_1m_cv != 0 or sum_1m_pv != 0 or len(rolling_buffer[u]) > 0:
                                    await db_pool.execute('''
                                        INSERT INTO options_flow_ticks 
                                        (time, underlying, call_premium, put_premium, call_volume, put_volume, net_drift)
                                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                                    ''', now, u, 
                                    sum_1m_cp, sum_1m_pp, sum_1m_cv, sum_1m_pv, sum_5m_drift)
                            last_insert_tick = now
                            reset_tick_data()
                        continue
                        
                    typ = data.get('type')
                    opt_sym = data.get('symbol', '')
                    
                    if not opt_sym: continue
                    
                    # Deduce underlying from symbol (basic)
                    underlying = "SPX" if "SPX" in opt_sym else "QQQ"
                    
                    if typ == 'quote':
                        bid = float(data.get('bid', 0) if data.get('bid') not in [None, ''] else 0)
                        ask = float(data.get('ask', 0) if data.get('ask') not in [None, ''] else 0)
                        if bid > 0 or ask > 0:
                            latest_quotes[opt_sym] = {"bid": bid, "ask": ask}
                            
                    elif typ == 'trade':
                        price = float(data.get('price', 0) if data.get('price') not in [None, ''] else 0)
                        size = int(data.get('size', 0) if data.get('size') not in [None, ''] else 0)
                        
                        if size == 0 or price == 0: continue
                        
                        quotes = latest_quotes.get(opt_sym, {"bid": 0, "ask": 0})
                        sentiment = determine_sentiment(price, quotes['bid'], quotes['ask'], opt_sym)
                        
                        # Store last trade price for future tick-tests
                        last_trade_prices[opt_sym] = price
                        
                        if sentiment == 'UNKNOWN' or sentiment == 'NONE':
                            continue # Ignore neutral/unknown flow for Net metrics
                            
                        # Parse Call/Put and Strike from Symbol
                        # Format example: SPXW260304C05800000 -> last 8 digits = strike * 1000
                        try:
                            # Safely extract by splitting Call/Put character
                            if 'C' in opt_sym[6:]:
                                is_call = True
                                strike_str = opt_sym.split('C')[-1]
                            elif 'P' in opt_sym[6:]:
                                is_call = False
                                strike_str = opt_sym.split('P')[-1]
                            else:
                                raise ValueError("No C/P found")
                                
                            if not strike_str: raise ValueError("Empty strike")
                            strike = float(strike_str) / 1000.0
                        except Exception:
                            # If parsing fails, default to Call to not break flow
                            is_call = 'C' in opt_sym[6:]
                            strike = 0
                            
                        # === OTM Filter Logic ===
                        spot = latest_spot.get(underlying, 0.0)
                        if spot > 0 and strike > 0:
                            if is_call and strike <= spot:
                                continue # ITM Call, ignore 
                            if not is_call and strike >= spot:
                                continue # ITM Put, ignore
                        # ========================
                            
                        # 2. Block vs Sweep Filter: Discount massive block trades (e.g. > 200 contracts)
                        # A single 1000 contract trade might just be hedging.
                        block_weight = 1.0
                        if size > 200:
                            # Logarithmic dampening for massive trades
                            # If size is 200, weight ~ 1.0. If size is 2000, weight is ~ 0.43 (so premium reduced)
                            block_weight = math.log(200 + 1) / math.log(size + 1)
                            
                        # 3. Aggressiveness & Spot Distance Weighting
                        # Trades at the exact Ask/Bid indicate high urgency. Mid-leaning trades are less urgent.
                        urgency_weight = 1.0
                        if quotes['ask'] > 0 and quotes['bid'] > 0:
                            if price >= quotes['ask'] or price <= quotes['bid']:
                                urgency_weight = 1.5 # High urgency (Golden Sweep potential)
                            elif quotes['ask'] - quotes['bid'] > 0:
                                # Normal leaning
                                urgency_weight = 0.8
                                
                        # Distance to Spot Weighting (Delta proxy): Closer to ATM = higher weight
                        distance_weight = 1.0
                        if spot > 0 and strike > 0:
                            distance_pct = abs(spot - strike) / spot
                            # Example: if distance is 1%, distance_pct is 0.01.
                            # We want weight to drop off to 0.1 at 10% distance.
                            distance_weight = max(0.1, 1.0 - (distance_pct * 10))

                        # Combine multipliers
                        final_multiplier = block_weight * urgency_weight * distance_weight
                        
                        raw_premium = price * size * 100
                        premium = raw_premium * final_multiplier
                        volume = size * 100
                        
                        # Apply Direction
                        # Buy = (+), Sell = (-)
                        direction_multiplier = 1 if sentiment == 'BUY' else -1
                        
                        trade_time = datetime.now(timezone.utc)
                        try:
                            exp_str = opt_sym[-15:-9]
                            exp_date = datetime.strptime(exp_str, '%y%m%d').date()
                        except Exception:
                            exp_date = trade_time.date()
                            
                        raw_trades_buffer.append((
                            trade_time, underlying, opt_sym, exp_date, strike,
                            'CALL' if is_call else 'PUT', price, size, premium, sentiment, True
                        ))

                        # Also store in options_trade_prints for momentum analysis
                        # Calculate delta approximation based on moneyness
                        spot_for_delta = latest_spot.get(underlying, 0.0)
                        delta_approx = calculate_delta_approx(strike, spot_for_delta, is_call)

                        # Mark as sweep if large trade (>500 contracts)
                        is_sweep = size >= 500

                        # Store individual trade print for detailed analysis
                        try:
                            await db_pool.execute('''
                                INSERT INTO options_trade_prints (
                                    time, underlying, option_symbol, strike, expiration,
                                    option_type, trade_price, trade_size, trade_premium,
                                    direction, delta, is_0dte, is_sweep, exchange
                                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                            ''', trade_time, underlying, opt_sym, strike, exp_date,
                                'CALL' if is_call else 'PUT', price, size, premium,
                                sentiment, delta_approx, True, is_sweep, data.get('exchange', ''))
                        except Exception as e:
                            logger.debug(f"Error storing trade print: {e}")
                        
                        metric = current_minute_data[underlying]
                        tick_metric = current_tick_data[underlying]
                        if is_call:
                            metric['call_premium'] += (premium * direction_multiplier)
                            metric['call_volume'] += (volume * direction_multiplier)
                            tick_metric['call_premium'] += (premium * direction_multiplier)
                            tick_metric['call_volume'] += (volume * direction_multiplier)
                        else:
                            metric['put_premium'] += (premium * direction_multiplier)
                            metric['put_volume'] += (volume * direction_multiplier)
                            tick_metric['put_premium'] += (premium * direction_multiplier)
                            tick_metric['put_volume'] += (volume * direction_multiplier)
                            
                    now = datetime.now(timezone.utc)
                            
                    # Periodic 2-second tick flush
                    if last_insert_tick is None:
                        last_insert_tick = now
                        
                    if (now - last_insert_tick).total_seconds() >= 2:
                        for u in SYMBOLS:
                            t = current_tick_data[u]
                            
                            # Add current 2s tick to the rolling buffer
                            rolling_buffer[u].append({
                                "time": now,
                                "call_premium": t['call_premium'],
                                "put_premium": t['put_premium'],
                                "call_volume": t['call_volume'],
                                "put_volume": t['put_volume']
                            })
                            
                            # Prune old items from buffer (older than 5 minutes = 300s)
                            while rolling_buffer[u] and (now - rolling_buffer[u][0]["time"]).total_seconds() > 300:
                                rolling_buffer[u].popleft()
                                
                            # Calculate 1m sum (premium, volume) - Unweighted for raw totals in 1m
                            items_1m = [item for item in rolling_buffer[u] if (now - item["time"]).total_seconds() <= 60]
                            sum_1m_cp = sum(item["call_premium"] for item in items_1m)
                            sum_1m_pp = sum(item["put_premium"] for item in items_1m)
                            sum_1m_cv = sum(item["call_volume"] for item in items_1m)
                            sum_1m_pv = sum(item["put_volume"] for item in items_1m)
                            
                            # 4. EMA Time Decay for 5m Net Drift calculation
                            # Using an exponential decay so recent trades weigh much more than trades 4 minutes ago.
                            tau = 120.0 # Time constant: 120 seconds. Trades older than 2m lose ~63% power.
                            weighted_net_drift = 0.0
                            for item in rolling_buffer[u]:
                                elapsed = (now - item["time"]).total_seconds()
                                decay_factor = math.exp(-elapsed / tau)
                                weighted_net_drift += (item["call_premium"] - item["put_premium"]) * decay_factor
                                
                            sum_5m_drift = weighted_net_drift
                            
                            # Only write if we have some data in the buffers to prevent dead zeros
                            if sum_1m_cv != 0 or sum_1m_pv != 0 or len(rolling_buffer[u]) > 0:
                                await db_pool.execute('''
                                    INSERT INTO options_flow_ticks 
                                    (time, underlying, call_premium, put_premium, call_volume, put_volume, net_drift)
                                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                                ''', now, u, 
                                sum_1m_cp, sum_1m_pp, sum_1m_cv, sum_1m_pv, sum_5m_drift)
                                
                        if raw_trades_buffer:
                            buffer_copy = raw_trades_buffer.copy()
                            raw_trades_buffer.clear()
                            try:
                                await db_pool.executemany('''
                                    INSERT INTO options_flow (
                                        time, underlying, option_symbol, expiration, strike, option_type, 
                                        trade_price, trade_size, trade_premium, sentiment, is_0dte
                                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                                ''', buffer_copy)
                            except Exception as e:
                                logger.error(f"Error bulk inserting raw trades: {e}")
                                
                        last_insert_tick = now
                        reset_tick_data()
                            
                    # Periodic 1-minute flush
                    current_minute = now.replace(second=0, microsecond=0)
                    
                    if last_insert_minute is None:
                        last_insert_minute = current_minute
                        
                    if current_minute > last_insert_minute:
                        # Flush to DB
                        for u in SYMBOLS:
                            m = current_minute_data[u]
                            net_drift = m['call_premium'] - m['put_premium']
                            # Insert if any activity
                            if m['call_volume'] != 0 or m['put_volume'] != 0:
                                await db_pool.execute('''
                                    INSERT INTO options_flow_1m 
                                    (time, underlying, call_premium, put_premium, call_volume, put_volume, net_drift)
                                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                                ''', last_insert_minute, u, 
                                m['call_premium'], m['put_premium'], m['call_volume'], m['put_volume'], net_drift)
                                
                        logger.info(f"Flushed 1m Net Flow data for {last_insert_minute}")
                        last_insert_minute = current_minute
                        reset_minute_data()

        except websockets.ConnectionClosed:
            logger.warning("Options Flow WS closed, reconnecting...")
        except Exception as e:
            logger.error(f"Options Flow WS loop error: {e}")
            
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(flow_daemon())
