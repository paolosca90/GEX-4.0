import asyncio
import math
import logging
from datetime import datetime, date
import httpx
from db import get_db_pool

logger = logging.getLogger("flow_analyzer")

class FlowAnalyzer:
    def __init__(self, db_pool):
        self.db_pool = db_pool

    def determine_sentiment(self, trade_price: float, bid: float, ask: float, opt_sym: str, last_trade_prices: dict) -> str:
        """
        Determine trade sentiment using Bid/Ask proximity.

        POINT 4 â€” SPREAD NEUTRALITY:
        If spread is wide (> $0.50), require trade to be within 25% of bid/ask boundaries
        to be considered directional. Mid-zone trades are classified as NONE (noise).
        """
        if bid == 0 and ask == 0:
            # Tick-test fallback
            last_price = last_trade_prices.get(opt_sym)
            if last_price is not None:
                if trade_price > last_price:
                    return 'BUY'
                elif trade_price < last_price:
                    return 'SELL'
                else:
                    return 'NONE'
            return 'UNKNOWN'

        mid = (bid + ask) / 2
        spread = ask - bid

        # POINT 4 â€” Wide Spread Neutrality
        if spread > 0.50:
            core_threshold = spread * 0.25  # Must be within 25% of bid/ask to count
            if trade_price >= ask - core_threshold:
                return 'BUY'
            elif trade_price <= bid + core_threshold:
                return 'SELL'
            else:
                return 'NONE'  # Ignored: Mid-zone noise on a wide spread

        # Normal spread evaluation
        if trade_price >= ask:
            return 'BUY'
        elif trade_price <= bid:
            return 'SELL'
        elif trade_price > mid:
            return 'BUY'   # Leans Buy
        elif trade_price < mid:
            return 'SELL'  # Leans Sell
        else:
            return 'NONE'  # Exactly at mid

    def compute_weights(self, size: int, price: float, bid: float, ask: float, spot: float, strike: float) -> float:
        """
        Compute a combined trade weight multiplier based on:
          - POINT 2: Block Trade Discounting (logarithmic dampening if size > 200).
          - POINT 3: Urgency Weight (1.5x for at-bid/ask executions, 0.8x for leaning).
          - POINT 3: Distance-to-Spot Weight (ATM options get higher weight via delta proxy).

        Returns the final_multiplier to be applied to raw_premium.
        """
        # POINT 2 â€” Block Trade Discounting
        block_weight = 1.0
        if size > 200:
            # Logarithmic dampening: size=200 â†’ weight~1.0, size=2000 â†’ weight~0.43
            block_weight = math.log(200 + 1) / math.log(size + 1)

        # POINT 3 â€” Urgency / Aggressiveness Weight
        urgency_weight = 1.0
        if ask > 0 and bid > 0:
            if price >= ask or price <= bid:
                urgency_weight = 1.5  # Aggressive at-market execution (Golden Sweep potential)
            else:
                urgency_weight = 0.8  # Mid-leaning, less urgent

        # POINT 3 â€” Distance to Spot (delta proxy)
        distance_weight = 1.0
        if spot > 0 and strike > 0:
            distance_pct = abs(spot - strike) / spot
            # Linear dropoff: 0% distance â†’ 1.0, 10% distance â†’ 0.0 (capped at 0.1 min)
            distance_weight = max(0.1, 1.0 - (distance_pct * 10))

        return block_weight * urgency_weight * distance_weight

    async def process_option_trade(self, trade_data: dict, spot_price: float = 0.0, last_trade_prices: dict = None):
        """
        Receives an option trade payload from the Tradier tape and stores it
        with all 4 algorithmic adjustments applied.

        Example trade_data:
        {
           "symbol": "SPXW240119P04500000",
           "type": "trade",
           "price": 12.50,
           "size": 50,
           "bid": 12.40,
           "ask": 12.60,
           ...
        }
        """
        if last_trade_prices is None:
            last_trade_prices = {}

        try:
            symbol = trade_data['symbol']
            trade_price = float(trade_data['price'])
            trade_size = int(trade_data['size'])
            bid = float(trade_data.get('bid', 0) or 0)
            ask = float(trade_data.get('ask', 0) or 0)

            if trade_size == 0 or trade_price == 0:
                return

            # POINT 4 â€” Spread Neutrality: classify sentiment
            sentiment = self.determine_sentiment(trade_price, bid, ask, symbol, last_trade_prices)
            if sentiment in ('NONE', 'UNKNOWN'):
                return  # Ignore neutral / ambiguous trades

            # Parse option type and strike from symbol
            # Format: SPXWYYMMDD[C/P]STRIKE00 â†’ e.g. SPXW260304C05800000
            is_call = True
            strike = 0.0
            try:
                if 'C' in symbol[6:]:
                    is_call = True
                    strike = float(symbol.split('C')[-1]) / 1000.0
                elif 'P' in symbol[6:]:
                    is_call = False
                    strike = float(symbol.split('P')[-1]) / 1000.0
            except Exception:
                is_call = 'C' in symbol[6:]

            # OTM Filter: Ignore ITM options (they have delta â‰ˆ 1 and add noise)
            if spot_price > 0 and strike > 0:
                if is_call and strike <= spot_price:
                    return  # ITM Call, skip
                if not is_call and strike >= spot_price:
                    return  # ITM Put, skip

            # POINT 2 & 3 â€” Compute combined weight multiplier
            final_multiplier = self.compute_weights(
                size=trade_size, price=trade_price,
                bid=bid, ask=ask,
                spot=spot_price, strike=strike
            )

            raw_premium = trade_price * trade_size * 100
            weighted_premium = raw_premium * final_multiplier
            option_type = 'CALL' if is_call else 'PUT'

            # Parse expiration
            try:
                exp_str = symbol[-15:-9]
                exp_date = datetime.strptime(exp_str, '%y%m%d').date()
            except Exception:
                exp_date = date.today()

            # Store in DB
            await self.db_pool.execute('''
                INSERT INTO options_flow 
                (time, underlying, option_symbol, expiration, strike, option_type, trade_price, trade_size, trade_premium, sentiment, is_0dte)
                VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9, TRUE)
            ''',
                'SPX' if 'SPX' in symbol else 'QQQ',
                symbol, exp_date, strike, option_type,
                trade_price, trade_size, weighted_premium, sentiment
            )

            logger.debug(
                f"Processed: {symbol} | {sentiment} | Raw: ${raw_premium:,.0f} | "
                f"Weighted: ${weighted_premium:,.0f} | Multiplier: {final_multiplier:.2f}"
            )

        except Exception as e:
            logger.error(f"Error processing option trade: {e}", exc_info=True)


    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # MOMENTUM SCORE CALCULATION (for scalp tool 9:30-11:30 EST)
    # Composite score: 0-100 normalized, higher = stronger reversal signal
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def calculate_flow_velocity(self, underlying: str, lookback_1m: int = 5, lookback_5m: int = 15) -> float:
        """
        FLOW VELOCITY (35% weight) â€” measures if momentum is accelerating or decelerating.
        Compares recent 1m drift vs longer 5m drift to detect acceleration.
        """
        now = datetime.now()
        five_min_ago = now.replace(minute=now.minute - 5, second=0, microsecond=0)
        one_min_ago = now.replace(minute=now.minute - 1, second=0, microsecond=0)

        try:
            # Get 1m and 5m net drift
            row_1m = await self.db_pool.fetchrow('''
                SELECT COALESCE(net_drift, 0) as drift
                FROM options_flow_1m
                WHERE underlying = $1 AND time >= $2
                ORDER BY time DESC LIMIT 1
            ''', underlying, one_min_ago)

            row_5m = await self.db_pool.fetchrow('''
                SELECT COALESCE(AVG(net_drift), 0) as drift
                FROM options_flow_1m
                WHERE underlying = $1 AND time >= $2
            ''', underlying, five_min_ago)

            drift_1m = float(row_1m['drift']) if row_1m else 0.0
            drift_5m = float(row_5m['drift']) if row_5m else 0.0

            if drift_5m == 0:
                return 50.0  # Neutral

            velocity = (drift_1m - drift_5m) / abs(drift_5m)

            # Normalize: velocity > 0 means accelerating bullish momentum
            # Map to 0-100 where 50 is neutral
            score = 50.0 + (velocity * 25)
            return max(0.0, min(100.0, score))

        except Exception as e:
            logger.error(f"Flow velocity error: {e}")
            return 50.0

    async def calculate_price_action_score(self, underlying: str, futures_symbol: str) -> float:
        """
        PRICE ACTION SCORE (25% weight) â€” measures recent price deviation from spot.
        Uses last 10 candles to detect overextension and mean-reversion potential.
        """
        try:
            # Get recent futures ticks for this underlying
            rows = await self.db_pool.fetch('''
                SELECT price FROM futures_ticks
                WHERE symbol = $1
                ORDER BY time DESC LIMIT 20
            ''', futures_symbol)

            if not rows or len(rows) < 5:
                return 50.0

            prices = [r['price'] for r in reversed(rows)]
            current = prices[-1]

            # Calculate moving average and std dev
            ma = sum(prices) / len(prices)
            variance = sum((p - ma) ** 2 for p in prices) / len(prices)
            std_dev = variance ** 0.5

            if std_dev == 0:
                return 50.0

            # Z-score: how many std dev is current price from MA
            z_score = (current - ma) / std_dev

            # Overextended (|z| > 2) suggests reversal
            # Negative z = price below MA = potential bounce up
            # Positive z = price above MA = potential pullback
            score = 50.0 - (z_score * 15)
            return max(0.0, min(100.0, score))

        except Exception as e:
            logger.error(f"Price action score error: {e}")
            return 50.0

    async def calculate_gex_positioning(self, underlying: str, current_price: float) -> float:
        """
        GEX POSITIONING (20% weight) â€” measures distance to zero-gamma level.
        Price near ZGL = higher reversal probability (dealers hedged, mean-reversion)
        """
        try:
            today = date.today()

            # Get nearest GEX levels
            rows = await self.db_pool.fetch('''
                SELECT strike, total_gex,
                       ABS(strike - $2) as distance
                FROM gex_profile
                WHERE underlying = $1 AND calc_date = $3
                ORDER BY distance ASC LIMIT 5
            ''', underlying, current_price, today)

            if not rows:
                return 50.0

            # Find the zero-gamma level (where GEX crosses from + to -)
            sorted_rows = sorted(rows, key=lambda r: r['distance'])

            # Check if we're very close to a major GEX level
            nearest = sorted_rows[0]
            distance_pct = nearest['distance'] / current_price

            # Within 0.5% of a level = strong signal
            if distance_pct < 0.002:
                gex_magnitude = abs(nearest['total_gex'])
                # Higher |GEX| near price = stronger reversal force
                intensity = min(gex_magnitude / 1e9, 1.0)  # Cap at 1B gamma
                return 70.0 + (intensity * 30.0)

            # Moderate distance
            if distance_pct < 0.01:
                return 50.0 + (10.0 * (0.01 - distance_pct) / 0.01)

            return 50.0

        except Exception as e:
            logger.error(f"GEX positioning error: {e}")
            return 50.0

    async def calculate_volume_ratio(self, underlying: str) -> float:
        """
        VOLUME RATIO (10% weight) â€” call volume vs put volume imbalance.
        Extreme ratios suggest capitulation and potential reversal.
        """
        try:
            now = datetime.now()
            fifteen_min_ago = now.replace(minute=now.minute - 15, second=0, microsecond=0)

            row = await self.db_pool.fetchrow('''
                SELECT COALESCE(call_volume, 0) as call_vol,
                       COALESCE(put_volume, 0) as put_vol
                FROM options_flow_1m
                WHERE underlying = $1 AND time >= $2
                ORDER BY time DESC LIMIT 1
            ''', underlying, fifteen_min_ago)

            call_vol = float(row['call_vol']) if row else 0.0
            put_vol = float(row['put_vol']) if row else 0.0

            total = call_vol + put_vol
            if total == 0:
                return 50.0

            ratio = call_vol / total  # 0 = all puts, 1 = all calls

            # Extreme ratios ( >80% or <20%) suggest reversal
            if ratio > 0.8:
                return 30.0 + ((1.0 - ratio) * 100)  # Calls too high = potential selloff
            elif ratio < 0.2:
                return 30.0 + (ratio * 100)  # Puts too high = potential bounce
            else:
                return 50.0

        except Exception as e:
            logger.error(f"Volume ratio error: {e}")
            return 50.0

    async def calculate_theta_effect(self, underlying: str, is_0dte: bool = True) -> float:
        """
        THETA EFFECT (10% weight) â€” 0DTE decay acceleration.
        High theta decay in early session = potential volatility spike = reversal chance.
        """
        if not is_0dte:
            return 50.0

        try:
            now = datetime.now()
            # Market open was 9:30 EST = ~14:30 UTC
            # Each hour closer to expiry = accelerating theta
            hour = now.hour

            # Between 9:30-11:30 EST (14:30-16:30 UTC)
            if 14 <= hour <= 16:
                # Theta acceleration factor
                minutes_into_session = (hour - 14) * 60 + now.minute
                theta_factor = min(minutes_into_session / 120, 1.0)  # 0 to 1 over 2 hours

                # Higher theta acceleration = more reversal potential
                return 50.0 + (theta_factor * 30.0)
            elif 17 <= hour <= 19:  # 12:30-2:30 PM EST - still 0DTE
                return 60.0
            else:
                return 50.0

        except Exception as e:
            logger.error(f"Theta effect error: {e}")
            return 50.0

    async def calculate_composite_score(self, underlying: str, futures_symbol: str, current_price: float) -> dict:
        """
        Calculate the full composite momentum score.
        Returns dict with overall score and individual components.
        """
        # Run all calculations in parallel
        flow_vel, price_act, gex_pos, vol_ratio, theta = await asyncio.gather(
            self.calculate_flow_velocity(underlying),
            self.calculate_price_action_score(underlying, futures_symbol),
            self.calculate_gex_positioning(underlying, current_price),
            self.calculate_volume_ratio(underlying),
            self.calculate_theta_effect(underlying)
        )

        # Weighted composite (weights sum to 100%)
        composite = (
            flow_vel * 0.35 +
            price_act * 0.25 +
            gex_pos * 0.20 +
            vol_ratio * 0.10 +
            theta * 0.10
        )

        return {
            'composite': round(composite, 1),
            'flow_velocity': round(flow_vel, 1),
            'price_action': round(price_act, 1),
            'gex_positioning': round(gex_pos, 1),
            'volume_ratio': round(vol_ratio, 1),
            'theta_effect': round(theta, 1)
        }

    async def get_zone_proximity_alert(self, underlying: str, futures_symbol: str, current_price: float) -> dict:
        """
        Main function: check if price is near a reversal zone and return alert.
        Returns signal strength and direction for UI arrows.
        """
        # Get nearby GEX levels (within 1% of current price)
        today = date.today()
        threshold_pct = 0.01  # 1% proximity threshold

        try:
            levels = await self.db_pool.fetch('''
                SELECT strike, total_gex
                FROM gex_profile
                WHERE underlying = $1
                  AND calc_date = $2
                  AND strike BETWEEN $3 * 0.99 AND $3 * 1.01
                ORDER BY ABS(total_gex) DESC
                LIMIT 10
            ''', underlying, today, current_price)

            if not levels:
                return {'in_zone': False, 'signal': 'NEUTRAL'}

            # Find the most significant nearby level
            strongest_level = max(levels, key=lambda l: abs(l['total_gex']))
            distance_pct = abs(strongest_level['strike'] - current_price) / current_price

            if distance_pct > threshold_pct:
                return {'in_zone': False, 'signal': 'NEUTRAL'}

            # Get momentum score
            momentum = await self.calculate_composite_score(underlying, futures_symbol, current_price)

            # Determine direction
            # Price above strong negative GEX = bounce down
            # Price below strong positive GEX = bounce up
            gex_at_level = strongest_level['total_gex']
            level_price = strongest_level['strike']

            if current_price > level_price and gex_at_level < 0:
                # Bearish reversal zone
                direction = 'DOWN'
                signal_strength = min(abs(momentum['composite'] - 50) / 50, 1.0)
            elif current_price < level_price and gex_at_level > 0:
                # Bullish reversal zone
                direction = 'UP'
                signal_strength = min(abs(momentum['composite'] - 50) / 50, 1.0)
            else:
                direction = 'NEUTRAL'
                signal_strength = 0.0

            return {
                'in_zone': True,
                'signal': direction,
                'signal_strength': round(signal_strength, 2),
                'momentum_score': momentum['composite'],
                'level_price': round(level_price, 2),
                'level_gex': round(gex_at_level, 2),
                'distance_pct': round(distance_pct * 100, 3),
                'details': momentum
            }

        except Exception as e:
            logger.error(f"Zone proximity error: {e}")
            return {'in_zone': False, 'signal': 'NEUTRAL'}


async def start_analyzer():
    pool = await get_db_pool()
    analyzer = FlowAnalyzer(pool)
    # The websocket ingestion daemon will push to this class or
    # this will poll via redis/rabbitmq in production.
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(start_analyzer())
