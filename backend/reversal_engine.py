"""
Reversal Engine - Detects high-probability market reversals by combining
multiple signals with a focus on 0DTE scalping during RTH.

Confluence Score (0-100):
  - GEX Proximity   (25%): Distance from ZGL / Call Wall / Put Wall
  - Flow Divergence (25%): EMA drift deceleration + counter-flow surge
  - Price Extension (20%): Z-score from GEX key levels
  - Trap Signal     (15%): Bear/Bull trap from flow vs drift divergence
  - Gamma Regime    (15%): Long/short gamma + position relative to ZGL
"""
import math
import logging
from datetime import datetime, timezone, timedelta, date
from db import get_db_pool

logger = logging.getLogger("reversal_engine")


class ReversalEngine:
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self._gex_cache: dict = {}  # underlying -> {zgl, call_wall, put_wall, regime, total_gex, levels}

    def update_gex_cache(self, underlying: str, gex_levels: list):
        """Called when GEX profile is refreshed. Caches key levels for fast lookup."""
        if not gex_levels:
            return

        sorted_levels = sorted(gex_levels, key=lambda x: x.get("futurePrice", x.get("strike", 0)))

        # ZGL: where cumulative GEX is most negative (after sorting by price ascending)
        cumulative = 0
        min_cumulative = float("inf")
        zgl = 0
        for level in sorted_levels:
            gex = level.get("gex", 0)
            cumulative += gex
            if cumulative < min_cumulative:
                min_cumulative = cumulative
                zgl = level.get("futurePrice", level.get("strike", 0))

        # Call Wall: max positive GEX
        call_levels = [l for l in sorted_levels if l.get("gex", 0) > 0]
        call_wall = max(call_levels, key=lambda x: x["gex"])["futurePrice"] if call_levels else None

        # Put Wall: min (most negative) GEX
        put_levels = [l for l in sorted_levels if l.get("gex", 0) < 0]
        put_wall = min(put_levels, key=lambda x: x["gex"])["futurePrice"] if put_levels else None

        total_gex = sum(l.get("gex", 0) for l in sorted_levels)
        regime = "long_gamma" if total_gex > 0 else "short_gamma"

        self._gex_cache[underlying] = {
            "zgl": zgl,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "regime": regime,
            "total_gex": total_gex,
            "levels": sorted_levels,
        }

    # ─── Component 1: GEX Proximity (25%) ─────────────────────────────
    async def score_gex_proximity(self, underlying: str, current_price: float) -> dict:
        """
        How close is price to a major GEX level (ZGL, Call Wall, Put Wall)?
        Closer = stronger reversal force.
        Returns 0-100 and which level is driving the signal.
        """
        gex = self._gex_cache.get(underlying)
        if not gex or not gex.get("zgl"):
            return {"score": 50, "detail": "No GEX data", "nearest_level": None, "direction": "NEUTRAL"}

        nearest = None
        nearest_dist = float("inf")
        direction = "NEUTRAL"

        # Check each key level
        levels_to_check = []
        if gex["zgl"]:
            levels_to_check.append(("ZGL", gex["zgl"], "FLIP"))
        if gex["call_wall"]:
            levels_to_check.append(("Call Wall", gex["call_wall"], "RESISTANCE"))
        if gex["put_wall"]:
            levels_to_check.append(("Put Wall", gex["put_wall"], "SUPPORT"))

        for name, price, role in levels_to_check:
            dist = abs(current_price - price)
            dist_pct = dist / current_price if current_price > 0 else 1
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = (name, price, role)

                # Direction: approaching resistance from below = bearish reversal potential
                if role == "RESISTANCE" and current_price <= price:
                    direction = "BEARISH"
                elif role == "SUPPORT" and current_price >= price:
                    direction = "BULLISH"
                elif role == "FLIP":
                    # Near ZGL: direction depends on which side of ZGL we're on
                    # Short gamma regime: ZGL is the pivot
                    if gex["regime"] == "short_gamma":
                        direction = "BEARISH" if current_price > price else "BULLISH"
                    else:
                        direction = "BULLISH" if current_price > price else "BEARISH"

        if not nearest:
            return {"score": 50, "detail": "No key levels", "nearest_level": None, "direction": "NEUTRAL"}

        # Score: within 0.2% = 90+, within 0.5% = 70+, within 1% = 50+, beyond = 30
        dist_pct = nearest_dist / current_price if current_price > 0 else 1
        if dist_pct < 0.001:    # < 0.1%
            score = 95
        elif dist_pct < 0.002:  # < 0.2%
            score = 85
        elif dist_pct < 0.005:  # < 0.5%
            score = 70
        elif dist_pct < 0.01:   # < 1%
            score = 55
        else:
            score = 35

        name, price, role = nearest
        return {
            "score": score,
            "detail": f"{nearest_dist:.1f} pts from {name} ({price:.0f})",
            "nearest_level": price,
            "direction": direction,
        }

    # ─── Component 2: Flow Divergence (25%) ───────────────────────────
    async def score_flow_divergence(self, underlying: str) -> dict:
        """
        Detects drift deceleration + counter-flow surge.
        Key reversal signal: drift still positive but decelerating while
        counter-directional flow is increasing.
        """
        try:
            # Get last 5 x 1-min flow bars
            rows = await self.db_pool.fetch('''
                SELECT net_drift, call_premium, put_premium, call_volume, put_volume
                FROM options_flow_1m
                WHERE underlying = $1
                ORDER BY time DESC LIMIT 5
            ''', underlying)

            if len(rows) < 3:
                return {"score": 50, "detail": "Insufficient flow data", "direction": "NEUTRAL"}

            # Current drift vs 5-bar average
            current_drift = float(rows[0]["net_drift"] or 0)
            avg_drift = sum(float(r["net_drift"] or 0) for r in rows) / len(rows)

            # Flow velocity: is drift accelerating or decelerating?
            if avg_drift == 0:
                velocity = 0
            else:
                velocity = (current_drift - avg_drift) / max(abs(avg_drift), 1)

            # Counter-flow check: if drift is bullish but put premium surged
            current_call_prem = float(rows[0]["call_premium"] or 0)
            current_put_prem = float(rows[0]["put_premium"] or 0)
            prev_call_prem = float(rows[1]["call_premium"] or 0)
            prev_put_prem = float(rows[1]["put_premium"] or 0)

            put_surge = (current_put_prem - prev_put_prem) / max(prev_put_prem, 1)
            call_surge = (current_call_prem - prev_call_prem) / max(prev_call_prem, 1)

            # Detect divergence
            score = 50
            direction = "NEUTRAL"
            detail_parts = []

            if current_drift > 0 and velocity < -0.3:
                # Bullish drift decelerating = potential bearish reversal
                score += min(30, abs(velocity) * 30)
                direction = "BEARISH"
                detail_parts.append("Call drift decelerating")

                if put_surge > 0.5:
                    score += 15
                    detail_parts.append(f"Put surge +{put_surge:.0%}")

            elif current_drift < 0 and velocity > 0.3:
                # Bearish drift decelerating = potential bullish reversal
                score += min(30, abs(velocity) * 30)
                direction = "BULLISH"
                detail_parts.append("Put drift decelerating")

                if call_surge > 0.5:
                    score += 15
                    detail_parts.append(f"Call surge +{call_surge:.0%}")

            elif current_drift > 0 and put_surge > 1.0:
                # Strong put counter-flow despite bullish drift
                score += 25
                direction = "BEARISH"
                detail_parts.append("Counter put flow")

            elif current_drift < 0 and call_surge > 1.0:
                # Strong call counter-flow despite bearish drift
                score += 25
                direction = "BULLISH"
                detail_parts.append("Counter call flow")

            if not detail_parts:
                detail_parts.append(f"Drift {'bullish' if current_drift > 0 else 'bearish'}, steady")

            score = max(0, min(100, score))

            return {
                "score": score,
                "detail": " | ".join(detail_parts),
                "direction": direction,
            }

        except Exception as e:
            logger.error(f"Flow divergence error: {e}")
            return {"score": 50, "detail": f"Error: {e}", "direction": "NEUTRAL"}

    # ─── Component 3: Price Extension (20%) ───────────────────────────
    async def score_price_extension(self, futures_symbol: str) -> dict:
        """
        Z-score of current price from recent mean.
        Overextended (>2 std dev) = higher reversal probability.
        Uses 20-tick rolling window.
        """
        try:
            rows = await self.db_pool.fetch('''
                SELECT price FROM futures_ticks
                WHERE symbol = $1
                ORDER BY time DESC LIMIT 20
            ''', futures_symbol)

            if len(rows) < 5:
                return {"score": 50, "detail": "Insufficient price data", "direction": "NEUTRAL"}

            prices = [float(r["price"]) for r in reversed(rows)]
            current = prices[-1]
            ma = sum(prices) / len(prices)
            variance = sum((p - ma) ** 2 for p in prices) / len(prices)
            std_dev = math.sqrt(variance) if variance > 0 else 1

            z_score = (current - ma) / std_dev

            # Overextended above MA = potential bearish reversal (pull back down)
            # Overextended below MA = potential bullish reversal (bounce up)
            # Score increases with |z_score|
            abs_z = abs(z_score)

            if abs_z > 2.5:
                score = 90
            elif abs_z > 2.0:
                score = 80
            elif abs_z > 1.5:
                score = 65
            elif abs_z > 1.0:
                score = 55
            else:
                score = 40  # Not extended, low reversal probability

            direction = "BEARISH" if z_score > 0 else "BULLISH"

            return {
                "score": score,
                "detail": f"Z-score: {z_score:+.2f} ({'above' if z_score > 0 else 'below'} MA)",
                "direction": direction,
                "z_score": round(z_score, 2),
            }

        except Exception as e:
            logger.error(f"Price extension error: {e}")
            return {"score": 50, "detail": f"Error: {e}", "direction": "NEUTRAL"}

    # ─── Component 4: Trap Signal (15%) ───────────────────────────────
    async def score_trap_signal(self, underlying: str) -> dict:
        """
        Detects bear/bull traps: price moving one direction but
        counter-directional options flow is surging.
        Uses the latest flow tick from options_flow_ticks.
        """
        try:
            row = await self.db_pool.fetchrow('''
                SELECT call_premium, put_premium, call_volume, put_volume, net_drift
                FROM options_flow_ticks
                WHERE underlying = $1
                ORDER BY time DESC LIMIT 1
            ''', underlying)

            if not row:
                return {"score": 50, "detail": "No flow tick", "direction": "NEUTRAL"}

            call_prem = float(row["call_premium"] or 0)
            put_prem = float(row["put_premium"] or 0)
            call_vol = int(row["call_volume"] or 0)
            put_vol = int(row["put_volume"] or 0)
            drift = float(row["net_drift"] or 0)

            total_prem = call_prem + put_prem
            total_vol = call_vol + put_vol

            if total_prem == 0 and total_vol == 0:
                return {"score": 50, "detail": "No flow", "direction": "NEUTRAL"}

            call_pct = call_prem / total_prem if total_prem > 0 else 0.5
            put_pct = put_prem / total_prem if total_prem > 0 else 0.5
            call_vol_pct = call_vol / total_vol if total_vol > 0 else 0.5
            put_vol_pct = put_vol / total_vol if total_vol > 0 else 0.5

            # Bear trap: drift is bearish (down) but call buying is heavy
            if drift < -10000 and (call_pct > 0.55 or call_vol_pct > 0.55):
                trap_strength = max(call_pct, call_vol_pct)
                score = 55 + int((trap_strength - 0.55) * 200)
                return {
                    "score": min(90, score),
                    "detail": f"Bear trap: calls {call_pct:.0%} prem vs bearish drift",
                    "direction": "BULLISH",
                }

            # Bull trap: drift is bullish (up) but put buying is heavy
            if drift > 10000 and (put_pct > 0.55 or put_vol_pct > 0.55):
                trap_strength = max(put_pct, put_vol_pct)
                score = 55 + int((trap_strength - 0.55) * 200)
                return {
                    "score": min(90, score),
                    "detail": f"Bull trap: puts {put_pct:.0%} prem vs bullish drift",
                    "direction": "BEARISH",
                }

            # No trap detected
            return {
                "score": 45,
                "detail": f"No trap: drift {'+' if drift > 0 else ''}{drift/1e3:.0f}K, balanced flow",
                "direction": "NEUTRAL",
            }

        except Exception as e:
            logger.error(f"Trap signal error: {e}")
            return {"score": 50, "detail": f"Error: {e}", "direction": "NEUTRAL"}

    # ─── Component 5: Gamma Regime (15%) ──────────────────────────────
    async def score_gamma_regime(self, underlying: str, current_price: float) -> dict:
        """
        Evaluates the gamma regime and position relative to ZGL.
        Short gamma + near ZGL = highest reversal probability (pinning).
        Long gamma + between walls = mean-reversion expected.
        """
        gex = self._gex_cache.get(underlying)
        if not gex or not gex.get("zgl"):
            return {"score": 50, "detail": "No GEX cache", "direction": "NEUTRAL"}

        regime = gex["regime"]
        zgl = gex["zgl"]
        total_gex = gex["total_gex"]

        distance_from_zgl = current_price - zgl
        dist_pct = abs(distance_from_zgl) / current_price if current_price > 0 else 1

        score = 50
        direction = "NEUTRAL"

        if regime == "short_gamma":
            # Short gamma: dealers hedging amplifies moves
            # Near ZGL = high volatility expected, direction depends on side
            if dist_pct < 0.005:  # Very close to ZGL
                score = 85
                direction = "BEARISH" if distance_from_zgl > 0 else "BULLISH"
            elif dist_pct < 0.01:
                score = 65
                direction = "BEARISH" if distance_from_zgl > 0 else "BULLISH"
            else:
                score = 45
        else:
            # Long gamma: dealers provide liquidity, mean-reversion expected
            # Between walls = calm, near wall = potential bounce
            if gex.get("call_wall") and current_price > gex["call_wall"] * 0.998:
                score = 75
                direction = "BEARISH"  # Bouncing off call wall
            elif gex.get("put_wall") and current_price < gex["put_wall"] * 1.002:
                score = 75
                direction = "BULLISH"  # Bouncing off put wall
            else:
                score = 45

        abs_gex = abs(total_gex)
        gex_b = abs_gex / 1e9
        regime_label = regime.replace("_", " ").title()

        return {
            "score": score,
            "detail": f"{regime_label} | GEX: {gex_b:.1f}B | {dist_pct:.2%} from ZGL",
            "direction": direction,
        }

    # ─── Composite Signal ─────────────────────────────────────────────
    async def get_reversal_signal(self, underlying: str, futures_symbol: str, current_price: float) -> dict:
        """
        Calculate full reversal confluence signal.
        Returns composite score, direction, all components, and suggested levels.
        """
        import asyncio

        # Run all components in parallel
        gex_prox, flow_div, price_ext, trap, gamma_reg = await asyncio.gather(
            self.score_gex_proximity(underlying, current_price),
            self.score_flow_divergence(underlying),
            self.score_price_extension(futures_symbol),
            self.score_trap_signal(underlying),
            self.score_gamma_regime(underlying, current_price),
        )

        components = {
            "gex_proximity": gex_prox,
            "flow_divergence": flow_div,
            "price_extension": price_ext,
            "trap_signal": trap,
            "gamma_regime": gamma_reg,
        }

        # Weighted composite
        weights = {
            "gex_proximity": 0.25,
            "flow_divergence": 0.25,
            "price_extension": 0.20,
            "trap_signal": 0.15,
            "gamma_regime": 0.15,
        }

        composite = sum(
            components[k]["score"] * weights[k]
            for k in weights
        )

        # Determine dominant direction by weighted vote
        bull_score = 0
        bear_score = 0
        for k, w in weights.items():
            d = components[k]["direction"]
            s = components[k]["score"] * w
            if d == "BULLISH":
                bull_score += s
            elif d == "BEARISH":
                bear_score += s

        if bull_score > bear_score and (bull_score - bear_score) > 3:
            direction = "BULLISH"
        elif bear_score > bull_score and (bear_score - bull_score) > 3:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        # Compute key, stop, target levels
        gex = self._gex_cache.get(underlying, {})
        key_level = None
        stop_level = None
        target_level = None

        if direction == "BEARISH":
            key_level = gex.get("call_wall") or gex.get("zgl")
            if key_level and current_price > 0:
                stop_level = key_level + (abs(current_price - key_level) * 0.5)
                target_level = gex.get("zgl") or gex.get("put_wall")
        elif direction == "BULLISH":
            key_level = gex.get("put_wall") or gex.get("zgl")
            if key_level and current_price > 0:
                stop_level = key_level - (abs(current_price - key_level) * 0.5)
                target_level = gex.get("zgl") or gex.get("call_wall")

        return {
            "confluence": round(composite, 1),
            "direction": direction,
            "components": components,
            "key_level": round(key_level, 2) if key_level else None,
            "stop_level": round(stop_level, 2) if stop_level else None,
            "target_level": round(target_level, 2) if target_level else None,
            "current_price": round(current_price, 2),
            "underlying": underlying,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def start_reversal_engine():
    """Standalone runner for testing."""
    pool = await get_db_pool()
    engine = ReversalEngine(pool)
    result = await engine.get_reversal_signal("SPX", "US500-F", 5820.0)
    print(result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(start_reversal_engine())
