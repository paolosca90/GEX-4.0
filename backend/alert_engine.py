"""
Alert Engine - evaluates 6 alert rules on tick/flow events.
Runs as async task inside FastAPI lifecycle.
"""
import time
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("alert_engine")

SYMBOL_TO_UNDERLYING = {
    "US500-F": "SPX",
    "NAS100-F": "QQQ",
    "SPX": "SPX",
    "QQQ": "QQQ",
}

DEFAULT_CONFIG = {
    "zgl_proximity_points": 3.0,
    "wall_proximity_points": 2.0,
    "flow_spike_threshold": 5_000_000,
    "momentum_high": 70,
    "momentum_low": 30,
    "dix_extreme_high": 0.45,
    "dix_extreme_low": 0.15,
    "cooldown_seconds": 300,
}


class AlertEngine:
    def __init__(self, db_pool, broadcast_fn=None):
        self.db_pool = db_pool
        self.broadcast_fn = broadcast_fn
        self.config = dict(DEFAULT_CONFIG)
        self.last_fired: dict = {}
        self.gex_cache: dict = {}

    def update_gex_cache(self, underlying: str, gex_levels: list):
        """Called when GEX profile is refreshed. Extracts key levels."""
        if not gex_levels:
            return
        sorted_levels = sorted(gex_levels, key=lambda x: x.get("futurePrice", x.get("strike", 0)))

        cumulative = 0
        min_cumulative = float("inf")
        zgl = sorted_levels[len(sorted_levels) // 2].get("futurePrice", 0) if sorted_levels else 0
        for level in sorted_levels:
            gex = level.get("gex", 0)
            cumulative += gex
            if cumulative < min_cumulative:
                min_cumulative = cumulative
                zgl = level.get("futurePrice", level.get("strike", 0))

        call_wall = max(sorted_levels, key=lambda x: x.get("gex", 0)) if sorted_levels else None
        put_wall = min(sorted_levels, key=lambda x: x.get("gex", 0)) if sorted_levels else None
        total_gex = sum(l.get("gex", 0) for l in sorted_levels)
        regime = "long_gamma" if total_gex > 0 else "short_gamma"

        self.gex_cache[underlying] = {
            "zgl": zgl,
            "call_wall": call_wall.get("futurePrice", call_wall.get("strike", 0)) if call_wall else None,
            "put_wall": put_wall.get("futurePrice", put_wall.get("strike", 0)) if put_wall else None,
            "regime": regime,
            "total_gex": total_gex,
        }

    async def evaluate_tick(self, symbol: str, price: float):
        """Called on every futures tick broadcast."""
        underlying = SYMBOL_TO_UNDERLYING.get(symbol)
        if not underlying or underlying not in self.gex_cache:
            return
        gex = self.gex_cache[underlying]
        if not gex.get("zgl"):
            return

        # A1: ZGL Proximity
        distance = abs(price - gex["zgl"])
        if distance <= self.config["zgl_proximity_points"]:
            direction = "BULLISH" if gex["regime"] == "long_gamma" and price < gex["zgl"] else "BEARISH"
            await self._fire("zgl_proximity", "HIGH", direction, underlying, price, gex["zgl"],
                f"{underlying} {distance:.1f} pts from ZGL ({gex['zgl']:.0f}) - {gex['regime']}")

        # A2: Wall Test — disabled (user preference)
        # if gex.get("call_wall"):
        #     distance = abs(price - gex["call_wall"])
        #     if distance <= self.config["wall_proximity_points"]:
        #         await self._fire("wall_test", "HIGH", "BEARISH", underlying, price, gex["call_wall"],
        #             f"{underlying} {distance:.1f} pts from Call Wall ({gex['call_wall']:.0f})")
        #
        # if gex.get("put_wall"):
        #     distance = abs(price - gex["put_wall"])
        #     if distance <= self.config["wall_proximity_points"]:
        #         await self._fire("wall_test", "HIGH", "BULLISH", underlying, price, gex["put_wall"],
        #             f"{underlying} {distance:.1f} pts from Put Wall ({gex['put_wall']:.0f})")

    async def evaluate_flow(self, underlying: str, net_drift: float, call_premium: float, put_premium: float):
        """Called on every flow tick broadcast."""
        net_flow = abs(call_premium - put_premium)
        if net_flow >= self.config["flow_spike_threshold"]:
            direction = "BULLISH" if call_premium > put_premium else "BEARISH"
            await self._fire("flow_spike", "MEDIUM", direction, underlying, None, None,
                f"{underlying} Flow Spike: ${net_flow/1e6:.1f}M net - {direction}",
                {"net_flow": net_flow, "call_premium": call_premium, "put_premium": put_premium})

    async def _fire(self, alert_type: str, severity: str, direction: str,
                    underlying: str, trigger_price, level_price, message: str, metadata=None):
        """Fire alert with cooldown check, DB insert, and WS broadcast."""
        key = (alert_type, underlying)
        now = time.time()
        if key in self.last_fired:
            if now - self.last_fired[key] < self.config["cooldown_seconds"]:
                return
        self.last_fired[key] = now

        alert = {
            "time": datetime.now(timezone.utc).isoformat(),
            "underlying": underlying,
            "alert_type": alert_type,
            "severity": severity,
            "direction": direction,
            "trigger_price": trigger_price,
            "level_price": level_price,
            "message": message,
        }

        if self.db_pool:
            try:
                await self.db_pool.execute("""
                    INSERT INTO alerts (time, underlying, alert_type, severity, direction,
                                       trigger_price, level_price, message, metadata)
                    VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                """, underlying, alert_type, severity, direction,
                     trigger_price, level_price, message,
                     json.dumps(metadata) if metadata else None)
            except Exception as e:
                logger.error(f"Alert DB insert error: {e}")

        if self.broadcast_fn:
            try:
                await self.broadcast_fn({"type": "alert", "data": alert})
            except Exception as e:
                logger.error(f"Alert broadcast error: {e}")

        logger.info(f"ALERT [{severity}] {alert_type} {underlying} {direction}: {message}")

    async def get_recent_alerts(self, limit: int = 100) -> list:
        """Fetch recent alerts from DB."""
        if not self.db_pool:
            return []
        rows = await self.db_pool.fetch("""
            SELECT id, time, underlying, alert_type, severity, direction,
                   trigger_price, level_price, message
            FROM alerts ORDER BY time DESC LIMIT $1
        """, limit)
        return [dict(r) for r in rows]

    async def fire_reversal_alert(self, signal: dict):
        """Fire a reversal confluence alert when score >= 70."""
        underlying = signal.get("underlying", "")
        direction = signal.get("direction", "NEUTRAL")
        confluence = signal.get("confluence", 0)
        key_level = signal.get("key_level")
        current_price = signal.get("current_price")

        # Determine severity based on confluence
        if confluence >= 85:
            severity = "HIGH"
        elif confluence >= 70:
            severity = "MEDIUM"
        else:
            return

        arrow = "▲" if direction == "BULLISH" else "▼"
        msg = (
            f"{arrow} {underlying} REVERSAL {direction} — "
            f"Confluence: {confluence:.0f}% | "
            f"Price: {current_price:.1f}"
        )
        if key_level:
            msg += f" | Key Level: {key_level:.1f}"

        await self._fire(
            "reversal_confluence", severity, direction,
            underlying, current_price, key_level, msg,
            {"confluence": confluence, "components": {
                k: v.get("score", 0) for k, v in signal.get("components", {}).items()
            }}
        )