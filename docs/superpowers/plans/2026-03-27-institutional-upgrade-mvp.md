# GEX Dashboard 4.0 — Institutional Upgrade MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Greeks+IV from ORATS, Alerts & Signals Engine, Dark Pool DIX indicator, and dark theme UI to transform GEX Dashboard into an institutional-grade product.

**Architecture:** Backend-first approach — new Python services (greeks_service, alert_engine, darkpool_analyzer) integrate into existing FastAPI server. Frontend adds 3 new React components and applies dark theme to 5 existing ones. All new data flows through existing WebSocket broadcast pattern.

**Tech Stack:** Python 3 + FastAPI + asyncpg + httpx (backend), React 17 + Vite + TypeScript + Lightweight Charts (frontend), PostgreSQL + TimescaleDB (database), Tradier API with ORATS Greeks (data source), FINRA Reg SHO (dark pool data).

**Spec:** `docs/superpowers/specs/2026-03-27-institutional-upgrade-mvp-design.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `backend/greeks_service.py` | Fetch Tradier option chain with `greeks=true`, parse, aggregate, cache |
| `backend/alert_engine.py` | Evaluate 6 alert rules on tick/flow events, fire with cooldown |
| `backend/darkpool_analyzer.py` | Download FINRA Reg SHO daily CSV, parse SPY/QQQ, calculate DIX |
| `frontend/src/components/GreeksPanel.tsx` | Display Greeks table, IV gauge, regime badge |
| `frontend/src/components/AlertsPanel.tsx` | Real-time alert list with severity icons + AlertBadge |
| `frontend/src/components/DarkPoolPanel.tsx` | DIX gauge, short ratio bar, 7-day sparkline |

### Modified Files

| File | Changes |
|------|---------|
| `backend/db.py:18-127` | Add `alerts` and `darkpool_daily` table creation in `init_db()` |
| `backend/main.py:24-41` | Initialize greeks_service, alert_engine in startup; add 7 new endpoints |
| `frontend/src/App.css:1-352` | Replace green matrix theme with dark professional theme, add grid layout |
| `frontend/src/App.tsx:1-273` | Add GreeksPanel/AlertsPanel/DarkPoolPanel to sidebar, alert WS listener |
| `frontend/src/components/LightweightChart.tsx:59-89` | Update chart colors to dark theme |
| `frontend/src/components/GexProfile.tsx:115-120` | Update header/bars colors to dark theme |
| `frontend/src/components/SmartMoneyBox.tsx:228-308` | Update box/metrics colors to dark theme |

---

## Task 1: Database Schema — Add `alerts` and `darkpool_daily` Tables

**Files:**
- Modify: `backend/db.py:107-127` (append after table 6)

- [ ] **Step 1: Add `alerts` table to `db.py`**

After the `gex_level_interactions` hypertable creation (line 124), add:

```python
    # 7. Table for Alerts (real-time signals)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id BIGSERIAL PRIMARY KEY,
            time TIMESTAMPTZ NOT NULL,
            underlying VARCHAR(10) NOT NULL,
            alert_type VARCHAR(30) NOT NULL,
            severity VARCHAR(10) NOT NULL,
            direction VARCHAR(10),
            trigger_price DOUBLE PRECISION,
            level_price DOUBLE PRECISION,
            message TEXT,
            metadata JSONB
        );
    """)
    try:
        await conn.execute("SELECT create_hypertable('alerts', 'time', if_not_exists => TRUE);")
    except Exception as e:
        print(f"Hypertable alerts notice: {e}")

    # 8. Table for Dark Pool Daily (DIX indicator)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS darkpool_daily (
            date DATE NOT NULL,
            underlying VARCHAR(10) NOT NULL,
            short_volume BIGINT,
            total_volume BIGINT,
            short_ratio DOUBLE PRECISION,
            dix DOUBLE PRECISION,
            dark_volume_estimate BIGINT,
            updated_at TIMESTAMPTZ,
            PRIMARY KEY (date, underlying)
        );
    """)
```

- [ ] **Step 2: Run schema migration**

Run: `cd backend && python3 -c "import asyncio; from db import init_db; asyncio.run(init_db())"`
Expected: "Database initialization complete." (requires DB connection)

- [ ] **Step 3: Commit**

```bash
git add backend/db.py
git commit -m "feat(db): add alerts and darkpool_daily tables for institutional MVP"
```

---

## Task 2: Greeks Service — Backend

**Files:**
- Create: `backend/greeks_service.py`
- Reference: `backend/gex_calculator.py:45-59` (existing Tradier API pattern with `greeks=true`)

- [ ] **Step 1: Create `greeks_service.py`**

```python
"""
Greeks Service — fetches option chain from Tradier with ORATS Greeks.
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

# Underlying -> ETF mapping for options chain lookup
CHAIN_SYMBOLS = {
    "SPX": "SPX",   # SPX has its own options
    "QQQ": "QQQ",   # QQQ has its own options
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
        """Get the current 0DTE date (same logic as main.py)."""
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

        # Get current spot from greeks data
        spot = None
        for opt in raw_options:
            greeks = opt.get("greeks") or {}
            if greeks.get("mid_iv"):
                spot = opt.get("underlying_price")
                break
        if not spot:
            spot = raw_options[0].get("underlying_price", 0)

        # Filter ATM +/- 5%
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

        # Calculate summary
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
            "iv_rank": None,  # Requires historical data, filled later
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

        # Group by expiry
        by_expiry: dict = {}
        for opt in chain_data["chain"]:
            expiry = opt.get("expiry", "unknown")
            if expiry not in by_expiry:
                by_expiry[expiry] = {
                    "expiry": expiry,
                    "dte": 0,  # 0DTE focus
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

        # Determine regime from GEX data if db_pool available
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
```

- [ ] **Step 2: Verify import works**

Run: `cd backend && python3 -c "from greeks_service import GreeksService; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/greeks_service.py
git commit -m "feat(backend): add Greeks service with ORATS data from Tradier"
```

---

## Task 3: Alert Engine — Backend

**Files:**
- Create: `backend/alert_engine.py`

- [ ] **Step 1: Create `alert_engine.py`**

```python
"""
Alert Engine — evaluates 6 alert rules on tick/flow events.
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
        self.last_fired: dict[tuple[str, str], float] = {}
        # Cache GEX levels: underlying -> {zgl, call_wall, put_wall, regime}
        self.gex_cache: dict[str, dict] = {}

    def update_gex_cache(self, underlying: str, gex_levels: list):
        """Called when GEX profile is refreshed. Extracts key levels."""
        if not gex_levels:
            return

        sorted_levels = sorted(gex_levels, key=lambda x: x.get("futurePrice", x.get("strike", 0)))

        # Find ZGL (zero gamma level) via cumulative sum
        cumulative = 0
        min_cumulative = float("inf")
        zgl = sorted_levels[len(sorted_levels) // 2].get("futurePrice", 0) if sorted_levels else 0

        for level in sorted_levels:
            gex = level.get("gex", 0)
            cumulative += gex
            if cumulative < min_cumulative:
                min_cumulative = cumulative
                zgl = level.get("futurePrice", level.get("strike", 0))

        # Find Call Wall (max positive GEX) and Put Wall (max negative GEX)
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
            direction = "BULLISH" if gex["zgl"] > price else "BEARISH"
            if gex["regime"] == "long_gamma":
                direction = "BULLISH" if price < gex["zgl"] else "BEARISH"
            await self._fire(
                alert_type="zgl_proximity",
                severity="HIGH",
                direction=direction,
                underlying=underlying,
                trigger_price=price,
                level_price=gex["zgl"],
                message=f"{underlying} {distance:.1f} pts from ZGL ({gex['zgl']:.0f}) — {gex['regime']}"
            )

        # A2: Wall Test — Call Wall
        if gex.get("call_wall"):
            distance = abs(price - gex["call_wall"])
            if distance <= self.config["wall_proximity_points"]:
                await self._fire(
                    alert_type="wall_test",
                    severity="HIGH",
                    direction="BEARISH",
                    underlying=underlying,
                    trigger_price=price,
                    level_price=gex["call_wall"],
                    message=f"{underlying} {distance:.1f} pts from Call Wall ({gex['call_wall']:.0f})"
                )

        # A2: Wall Test — Put Wall
        if gex.get("put_wall"):
            distance = abs(price - gex["put_wall"])
            if distance <= self.config["wall_proximity_points"]:
                await self._fire(
                    alert_type="wall_test",
                    severity="HIGH",
                    direction="BULLISH",
                    underlying=underlying,
                    trigger_price=price,
                    level_price=gex["put_wall"],
                    message=f"{underlying} {distance:.1f} pts from Put Wall ({gex['put_wall']:.0f})"
                )

    async def evaluate_flow(self, underlying: str, net_drift: float, call_premium: float, put_premium: float):
        """Called on every flow tick broadcast."""
        # A3: Flow Spike
        net_flow = abs(call_premium - put_premium)
        if net_flow >= self.config["flow_spike_threshold"]:
            direction = "BULLISH" if call_premium > put_premium else "BEARISH"
            await self._fire(
                alert_type="flow_spike",
                severity="MEDIUM",
                direction=direction,
                underlying=underlying,
                trigger_price=None,
                level_price=None,
                message=f"{underlying} Flow Spike: ${net_flow/1e6:.1f}M net — {direction}",
                metadata={"net_flow": net_flow, "call_premium": call_premium, "put_premium": put_premium}
            )

    async def _fire(self, alert_type: str, severity: str, direction: str,
                    underlying: str, trigger_price: float | None,
                    level_price: float | None, message: str, metadata: dict | None = None):
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
            "metadata": json.dumps(metadata) if metadata else None,
        }

        # Insert to DB
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

        # Broadcast via WebSocket
        if self.broadcast_fn:
            try:
                await self.broadcast_fn({
                    "type": "alert",
                    "data": alert,
                })
            except Exception as e:
                logger.error(f"Alert broadcast error: {e}")

        logger.info(f"ALERT [{severity}] {alert_type} {underlying} {direction}: {message}")

    async def get_recent_alerts(self, limit: int = 100) -> list:
        """Fetch recent alerts from DB."""
        if not self.db_pool:
            return []
        rows = await self.db_pool.fetch("""
            SELECT id, time, underlying, alert_type, severity, direction,
                   trigger_price, level_price, message, metadata
            FROM alerts
            ORDER BY time DESC
            LIMIT $1
        """, limit)
        return [dict(r) for r in rows]
```

- [ ] **Step 2: Verify import works**

Run: `cd backend && python3 -c "from alert_engine import AlertEngine; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/alert_engine.py
git commit -m "feat(backend): add alert engine with 6 rule types and cooldown"
```

---

## Task 4: Dark Pool Analyzer — Backend

**Files:**
- Create: `backend/darkpool_analyzer.py`

- [ ] **Step 1: Create `darkpool_analyzer.py`**

```python
"""
Dark Pool Analyzer — downloads FINRA Reg SHO daily short volume.
Calculates DIX (Dark Index) for SPY and QQQ.
"""
import csv
import io
import logging
import os
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger("darkpool_analyzer")

# FINRA Reg SHO daily short volume URL
FINRA_URL = "https://otctransparency.finra.com/api/shortsale/volume"

# Map our underlyings to FINRA symbols
FINRA_SYMBOL_MAP = {
    "SPX": "SPY",   # FINRA tracks SPY, not SPX
    "QQQ": "QQQ",
}


class DarkPoolAnalyzer:
    def __init__(self, db_pool=None):
        self.db_pool = db_pool
        self.cache: dict[str, dict] = {}  # underlying -> latest data

    async def download_and_parse(self, target_date: str | None = None) -> dict:
        """
        Download FINRA Reg SHO data for a given date.
        Returns {symbol: {short_volume, total_volume, short_ratio, dix}}.
        """
        if not target_date:
            # Default to yesterday (FINRA publishes next day)
            est = timezone(timedelta(hours=-5))
            yesterday = datetime.now(est).date() - timedelta(days=1)
            # Skip weekends
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

                # Parse pipe-delimited data
                text = resp.text
                reader = csv.DictReader(io.StringIO(text), delimiter="|")
                results = {}

                for row in reader:
                    symbol = row.get("symbol", "").strip()
                    if symbol not in ("SPY", "QQQ"):
                        continue

                    short_vol = int(row.get("shortVolume", 0))
                    total_vol = int(row.get("totalVolume", 0))
                    short_exempt = int(row.get("shortExemptVolume", 0))

                    if total_vol > 0:
                        short_ratio = short_vol / total_vol
                        dix = 1.0 - short_ratio
                    else:
                        short_ratio = 0
                        dix = 0

                    results[symbol] = {
                        "short_volume": short_vol,
                        "total_volume": total_vol,
                        "short_exempt_volume": short_exempt,
                        "short_ratio": round(short_ratio, 4),
                        "dix": round(dix, 4),
                        "dark_volume_estimate": short_vol,  # Approximation
                    }

                return results

        except Exception as e:
            logger.error(f"FINRA download error: {e}")
            return {}

    async def update_daily(self):
        """Download latest data and store in DB. Called at startup and daily."""
        results = await self.download_and_parse()
        if not results:
            logger.warning("No FINRA data downloaded")
            return

        est = timezone(timedelta(hours=-5))
        yesterday = datetime.now(est).date() - timedelta(days=1)
        while yesterday.weekday() >= 5:
            yesterday -= timedelta(days=1)

        for finra_sym, data in results.items():
            # Map back to our underlying
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
        # Check cache first
        if underlying in self.cache:
            return self.cache[underlying]

        # Fallback to DB
        if self.db_pool:
            row = await self.db_pool.fetchrow("""
                SELECT date, underlying, short_volume, total_volume,
                       short_ratio, dix, dark_volume_estimate
                FROM darkpool_daily
                WHERE underlying = $1
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
            FROM darkpool_daily
            WHERE underlying = $1
            ORDER BY date DESC LIMIT $2
        """, underlying, days)
        return [dict(r) for r in rows]
```

- [ ] **Step 2: Verify import works**

Run: `cd backend && python3 -c "from darkpool_analyzer import DarkPoolAnalyzer; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/darkpool_analyzer.py
git commit -m "feat(backend): add dark pool analyzer with FINRA Reg SHO DIX calculation"
```

---

## Task 5: Backend Endpoints — Wire Everything into `main.py`

**Files:**
- Modify: `backend/main.py`

This task adds: service initialization in startup, 7 new REST endpoints, alert evaluation in broadcast loops, and GEX cache update.

- [ ] **Step 1: Add imports and service instances at the top of `main.py`**

After line 9 (`logger = ...`), add:

```python
from greeks_service import GreeksService
from alert_engine import AlertEngine
from darkpool_analyzer import DarkPoolAnalyzer

greeks_service = None
alert_engine = None
darkpool_analyzer = None
```

- [ ] **Step 2: Update `startup_event()` to initialize services**

In `startup_event()` (line 25), after `asyncio.create_task(start_gex_engine())` (line 40), add:

```python
    # Initialize Greeks service
    global greeks_service, alert_engine, darkpool_analyzer
    greeks_service = GreeksService(db_pool)
    alert_engine = AlertEngine(db_pool, broadcast_fn=manager.broadcast)
    darkpool_analyzer = DarkPoolAnalyzer(db_pool)

    # Download initial dark pool data
    asyncio.create_task(darkpool_analyzer.update_daily())
```

- [ ] **Step 3: Add alert evaluation to `broadcast_ticks()`**

In `broadcast_ticks()` (line 95), inside the `for row in rows:` loop after the broadcast (line 103), add:

```python
                    # Evaluate alert rules on tick
                    if alert_engine:
                        await alert_engine.evaluate_tick(row["symbol"], float(row["price"]))
```

- [ ] **Step 4: Add alert evaluation to `broadcast_flow_ticks()`**

In `broadcast_flow_ticks()` (line 140), inside the `for row in rows:` loop after the broadcast (line 151), add:

```python
                    # Evaluate alert rules on flow
                    if alert_engine:
                        await alert_engine.evaluate_flow(
                            row["underlying"],
                            float(row["net_drift"] or 0),
                            float(row["call_premium"] or 0),
                            float(row["put_premium"] or 0)
                        )
```

- [ ] **Step 5: Add GEX cache update to `get_gex_latest()`**

In `get_gex_latest()` (line 672), after computing `gex_data` (line 662) and before the return statement (line 672), add:

```python
    # Update alert engine GEX cache
    if alert_engine:
        alert_engine.update_gex_cache(row_underlying, gex_data)
```

- [ ] **Step 6: Add 7 new REST endpoints**

Before the WebSocket endpoint (line 902), add:

```python
# ──────────────────────────── Greeks Endpoints ────────────────────────────
@app.get("/api/greeks/{underlying}")
async def get_greeks(underlying: str):
    """Return chain Greeks ATM +/-5% with IV data from ORATS."""
    if not greeks_service:
        return {"error": "Greeks service not initialized"}
    return await greeks_service.get_chain_greeks(underlying.upper())


@app.get("/api/greeks/summary/{underlying}")
async def get_greeks_summary(underlying: str):
    """Return aggregated Greeks summary per expiry."""
    if not greeks_service:
        return {"error": "Greeks service not initialized"}
    return await greeks_service.get_greeks_summary(underlying.upper())


# ──────────────────────────── Alert Endpoints ────────────────────────────
@app.get("/api/alerts")
async def get_alerts(limit: int = Query(100, description="Max alerts to return")):
    """Return recent alerts."""
    if not alert_engine:
        return {"alerts": []}
    alerts = await alert_engine.get_recent_alerts(limit)
    return {"alerts": alerts}


@app.get("/api/alerts/config")
async def get_alert_config():
    """Return current alert configuration."""
    if not alert_engine:
        return {"config": {}}
    return {"config": alert_engine.config}


@app.put("/api/alerts/config")
async def update_alert_config(config: dict):
    """Update alert configuration."""
    if not alert_engine:
        return {"error": "Alert engine not initialized"}
    for key, value in config.items():
        if key in alert_engine.config:
            alert_engine.config[key] = value
    return {"config": alert_engine.config}


# ──────────────────────────── Dark Pool Endpoints ────────────────────────────
@app.get("/api/darkpool/dix/{underlying}")
async def get_darkpool_dix(underlying: str):
    """Return latest DIX score for underlying."""
    if not darkpool_analyzer:
        return {"error": "Dark pool analyzer not initialized"}
    return await darkpool_analyzer.get_dix(underlying.upper())


@app.get("/api/darkpool/history/{underlying}")
async def get_darkpool_history(
    underlying: str,
    days: int = Query(30, description="Days of history"),
):
    """Return historical DIX data."""
    if not darkpool_analyzer:
        return {"history": []}
    data = await darkpool_analyzer.get_history(underlying.upper(), days)
    return {"history": data}
```

- [ ] **Step 7: Verify server starts**

Run: `cd backend && timeout 5 python3 -c "from main import app; print('FastAPI app loaded OK')" || true`
Expected: `FastAPI app loaded OK`

- [ ] **Step 8: Commit**

```bash
git add backend/main.py
git commit -m "feat(backend): wire Greeks, alerts, darkpool services into FastAPI with 7 new endpoints"
```

---

## Task 6: Frontend — Dark Theme CSS

**Files:**
- Modify: `frontend/src/App.css` (full rewrite of color variables and base styles)

- [ ] **Step 1: Replace the color scheme in `App.css`**

Replace lines 1-13 (the body/base styles) with:

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

:root {
  --bg-primary: #0a0e17;
  --bg-surface: #111827;
  --bg-surface-hover: #1a2332;
  --border: #1e293b;
  --border-active: #334155;
  --primary: #3b82f6;
  --primary-glow: rgba(59, 130, 246, 0.3);
  --success: #10b981;
  --success-glow: rgba(16, 185, 129, 0.3);
  --danger: #ef4444;
  --danger-glow: rgba(239, 68, 68, 0.3);
  --warning: #f59e0b;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Inter', -apple-system, sans-serif;
  background-color: var(--bg-primary);
  color: var(--text-primary);
}

.mono {
  font-family: 'JetBrains Mono', monospace;
}
```

- [ ] **Step 2: Update header styles**

Replace `.dashboard-header` through `.status-indicator.disconnected` (lines 23-79) with:

```css
/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1.5rem;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.header-logo {
  height: 40px;
  width: auto;
  object-fit: contain;
  filter: brightness(1.1);
}

.dashboard-header h1 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 1rem;
}

/* Status */
.status-indicator {
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.7rem;
  letter-spacing: 0.03em;
  font-family: 'JetBrains Mono', monospace;
}

.status-indicator.connected {
  background: rgba(16, 185, 129, 0.15);
  color: var(--success);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.status-indicator.disconnected {
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger);
  border: 1px solid rgba(239, 68, 68, 0.3);
}
```

- [ ] **Step 3: Update chart panel and panel-header styles**

Replace `.chart-panel` through `.panel-price` (lines 92-135) with:

```css
/* Chart Panel */
.chart-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
  border-radius: 8px;
  border: 1px solid var(--border);
  overflow: hidden;
  min-width: 0;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
}

.panel-header h2 {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.zero-gamma-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--bg-primary);
  background: var(--warning);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
}

.panel-price {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
}
```

- [ ] **Step 4: Update timeframe selector styles**

Replace `.timeframe-selector` through `.timeframe-btn.active` (lines 154-186) with:

```css
/* Timeframe Selector */
.timeframe-selector {
  display: flex;
  gap: 0.25rem;
  background: var(--bg-primary);
  padding: 2px;
  border-radius: 6px;
}

.timeframe-btn {
  background: transparent;
  border: none;
  padding: 4px 10px;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: 'JetBrains Mono', monospace;
}

.timeframe-btn:hover {
  background: var(--bg-surface-hover);
  color: var(--text-secondary);
}

.timeframe-btn.active {
  background: var(--primary);
  color: white;
}
```

- [ ] **Step 5: Update smart money box styles**

Replace `.smart-money-overlay` through `.smart-money-status.frozen` (lines 188-254) with:

```css
/* Smart Money Power Meter Overlay */
.smart-money-overlay {
  position: absolute;
  top: 10px;
  left: 10px;
  pointer-events: auto;
  z-index: 100;
  cursor: grab;
}

.smart-money-overlay:active {
  cursor: grabbing;
}

.smart-money-box {
  background: rgba(17, 24, 39, 0.92);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem 0.7rem;
  min-width: 170px;
  backdrop-filter: blur(12px);
}

.smart-money-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.3rem;
  padding-bottom: 0.3rem;
  border-bottom: 1px solid var(--border);
}

.smart-money-title {
  font-size: 0.6rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.smart-money-underlying {
  font-size: 0.55rem;
  color: var(--text-muted);
  margin-left: auto;
}

.smart-money-status {
  font-size: 0.5rem;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 3px;
}

.smart-money-status.live {
  background: rgba(16, 185, 129, 0.15);
  color: var(--success);
}

.smart-money-status.frozen {
  background: rgba(245, 158, 11, 0.15);
  color: var(--warning);
}
```

- [ ] **Step 6: Update metric and bar styles**

Replace `.smart-money-signal` through `.bar-label` (lines 270-352) with:

```css
.smart-money-signal {
  font-size: 0.75rem;
  font-weight: 700;
  text-align: center;
  padding: 0.2rem 0;
  margin-bottom: 0.3rem;
}

.smart-money-metrics {
  display: flex;
  gap: 0.8rem;
  margin-bottom: 0.3rem;
}

.metric {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.metric-label {
  font-size: 0.5rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.metric-value {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
}

.metric-value.positive {
  color: var(--success);
}

.metric-value.negative {
  color: var(--danger);
}

.premium-bar {
  display: flex;
  height: 14px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--bg-primary);
  border: 1px solid var(--border);
}

.put-bar {
  background: linear-gradient(90deg, var(--danger) 0%, #991b1b 100%);
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding-left: 4px;
  transition: width 0.3s ease;
}

.call-bar {
  background: linear-gradient(90deg, var(--success) 0%, #065f46 100%);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 4px;
  transition: width 0.3s ease;
}

.volume-bar {
  border: 1px solid var(--border);
}

.bar-label {
  font-size: 0.45rem;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}
```

- [ ] **Step 7: Add new component styles at the end of App.css**

Append these styles for the new components and sidebar:

```css
/* ──────────────────────────── Right Sidebar ──────────────────────────── */
.sidebar-panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 320px;
  min-width: 280px;
  overflow-y: auto;
}

.sidebar-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem;
}

.sidebar-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid var(--border);
}

.sidebar-card-title {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* ──────────────────────────── Greeks Panel ──────────────────────────── */
.greeks-table {
  width: 100%;
  font-size: 0.7rem;
  font-family: 'JetBrains Mono', monospace;
}

.greeks-row {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
  border-bottom: 1px solid rgba(30, 41, 59, 0.5);
}

.greeks-label {
  color: var(--text-muted);
}

.greeks-value {
  color: var(--text-primary);
  font-weight: 600;
}

.greeks-value.positive {
  color: var(--success);
}

.greeks-value.negative {
  color: var(--danger);
}

.regime-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.regime-badge.long {
  background: rgba(16, 185, 129, 0.15);
  color: var(--success);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.regime-badge.short {
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.iv-bar {
  height: 6px;
  border-radius: 3px;
  background: var(--bg-primary);
  overflow: hidden;
  margin-top: 4px;
}

.iv-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--primary);
  transition: width 0.5s ease;
}

/* ──────────────────────────── Alerts Panel ──────────────────────────── */
.alert-list {
  max-height: 200px;
  overflow-y: auto;
}

.alert-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.4rem 0;
  border-bottom: 1px solid rgba(30, 41, 59, 0.3);
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from { opacity: 0; transform: translateX(10px); }
  to { opacity: 1; transform: translateX(0); }
}

.alert-icon {
  font-size: 0.7rem;
  margin-top: 2px;
}

.alert-content {
  flex: 1;
}

.alert-type {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-primary);
}

.alert-message {
  font-size: 0.55rem;
  color: var(--text-secondary);
  margin-top: 2px;
}

.alert-time {
  font-size: 0.5rem;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}

.alert-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger);
  border: 1px solid rgba(239, 68, 68, 0.3);
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
}

/* ──────────────────────────── Dark Pool Panel ──────────────────────────── */
.dix-gauge {
  position: relative;
  width: 100%;
  height: 8px;
  border-radius: 4px;
  background: var(--bg-primary);
  overflow: hidden;
  margin: 8px 0;
}

.dix-gauge-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease, background 0.3s ease;
}

.dix-gauge-fill.low { background: var(--danger); }
.dix-gauge-fill.mid { background: var(--warning); }
.dix-gauge-fill.high { background: var(--success); }

.dix-metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 0;
}

.dix-label {
  font-size: 0.6rem;
  color: var(--text-muted);
}

.dix-value {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
}

/* ──────────────────────────── Responsive ──────────────────────────── */
@media (max-width: 1200px) {
  .dashboard-content {
    flex-direction: column;
  }
  .sidebar-panel {
    width: 100%;
    flex-direction: row;
    flex-wrap: wrap;
  }
  .sidebar-card {
    flex: 1;
    min-width: 250px;
  }
}

@media (max-width: 768px) {
  .sidebar-panel {
    flex-direction: column;
  }
  .sidebar-card {
    min-width: 100%;
  }
}
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.css
git commit -m "feat(frontend): apply dark professional theme with CSS variables"
```

---

## Task 7: Frontend — GreeksPanel Component

**Files:**
- Create: `frontend/src/components/GreeksPanel.tsx`

- [ ] **Step 1: Create `GreeksPanel.tsx`**

```tsx
import React, { useState, useEffect } from 'react'

interface GreeksSummary {
  total_gamma: number | null
  net_delta: number | null
  avg_theta: number | null
  call_iv_mean: number | null
  put_iv_mean: number | null
  skew: number | null
  iv_rank: number | null
}

interface GreeksData {
  underlying: string
  spot: number | null
  timestamp: string
  summary: GreeksSummary
}

interface GreeksSummaryData {
  regime: string
  total_gex: number
  avg_theta_decay: number | null
  iv_context: {
    atm_iv: number | null
    skew_25delta: number | null
    term_structure: string
  }
}

export const GreeksPanel: React.FC<{ underlying: string }> = ({ underlying }) => {
  const [greeks, setGreeks] = useState<GreeksData | null>(null)
  const [summary, setSummary] = useState<GreeksSummaryData | null>(null)

  useEffect(() => {
    const fetchGreeks = async () => {
      try {
        const base = `${window.location.protocol}//${window.location.host}`
        const [chainResp, summaryResp] = await Promise.all([
          fetch(`${base}/api/greeks/${underlying}`),
          fetch(`${base}/api/greeks/summary/${underlying}`),
        ])
        if (chainResp.ok) setGreeks(await chainResp.json())
        if (summaryResp.ok) setSummary(await summaryResp.json())
      } catch (err) {
        console.error('Greeks fetch error:', err)
      }
    }
    fetchGreeks()
    const interval = setInterval(fetchGreeks, 60000)
    return () => clearInterval(interval)
  }, [underlying])

  const regime = summary?.regime || 'unknown'
  const isLong = regime === 'long_gamma'
  const ivPct = greeks?.summary?.call_iv_mean
    ? Math.round(greeks.summary.call_iv_mean * 10000) / 100
    : null

  return (
    <div className="sidebar-card">
      <div className="sidebar-card-header">
        <span className="sidebar-card-title">Greeks &amp; IV</span>
        <span className={`regime-badge ${isLong ? 'long' : 'short'}`}>
          {regime === 'unknown' ? 'N/A' : isLong ? 'LONG GAMMA' : 'SHORT GAMMA'}
        </span>
      </div>

      {/* IV Bar */}
      {ivPct !== null && (
        <div style={{ marginBottom: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: 'var(--text-muted)' }}>
            <span>ATM IV</span>
            <span style={{ color: 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace" }}>
              {ivPct.toFixed(1)}%
            </span>
          </div>
          <div className="iv-bar">
            <div className="iv-bar-fill" style={{ width: `${Math.min(100, ivPct * 2)}%` }} />
          </div>
        </div>
      )}

      {/* Key Greeks */}
      <div className="greeks-table">
        <div className="greeks-row">
          <span className="greeks-label">Net Delta</span>
          <span className={`greeks-value ${(greeks?.summary?.net_delta || 0) >= 0 ? 'positive' : 'negative'}`}>
            {greeks?.summary?.net_delta?.toFixed(4) || '—'}
          </span>
        </div>
        <div className="greeks-row">
          <span className="greeks-label">Total Gamma</span>
          <span className="greeks-value">
            {greeks?.summary?.total_gamma?.toFixed(6) || '—'}
          </span>
        </div>
        <div className="greeks-row">
          <span className="greeks-label">Avg Theta</span>
          <span className={`greeks-value ${(greeks?.summary?.avg_theta || 0) <= 0 ? 'negative' : 'positive'}`}>
            {greeks?.summary?.avg_theta?.toFixed(4) || '—'}
          </span>
        </div>
        <div className="greeks-row">
          <span className="greeks-label">Skew</span>
          <span className={`greeks-value ${(greeks?.summary?.skew || 0) >= 0 ? 'positive' : 'negative'}`}>
            {greeks?.summary?.skew != null ? `${(greeks.summary.skew * 100).toFixed(2)}%` : '—'}
          </span>
        </div>
        <div className="greeks-row">
          <span className="greeks-label">Term Structure</span>
          <span className="greeks-value">
            {summary?.iv_context?.term_structure || '—'}
          </span>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit src/components/GreeksPanel.tsx 2>&1 | head -5`
Expected: No errors (may show unrelated warnings)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/GreeksPanel.tsx
git commit -m "feat(frontend): add GreeksPanel with IV gauge and regime badge"
```

---

## Task 8: Frontend — AlertsPanel Component

**Files:**
- Create: `frontend/src/components/AlertsPanel.tsx`

- [ ] **Step 1: Create `AlertsPanel.tsx`**

```tsx
import React, { useState, useEffect } from 'react'

interface Alert {
  id: number
  time: string
  underlying: string
  alert_type: string
  severity: string
  direction: string
  trigger_price: number | null
  level_price: number | null
  message: string
}

const SEVERITY_ICON: Record<string, string> = {
  HIGH: '🔴',
  MEDIUM: '🟡',
  LOW: '🟢',
}

const SEVERITY_COLOR: Record<string, string> = {
  HIGH: 'var(--danger)',
  MEDIUM: 'var(--warning)',
  LOW: 'var(--success)',
}

const TYPE_LABELS: Record<string, string> = {
  zgl_proximity: 'ZGL Proximity',
  wall_test: 'Wall Test',
  flow_spike: 'Flow Spike',
  gamma_flip: 'Gamma Flip',
  momentum_reversal: 'Momentum Rev',
  dix_extreme: 'DIX Extreme',
}

export const AlertsPanel: React.FC = () => {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [badgeCount, setBadgeCount] = useState(0)

  // Initial fetch
  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const base = `${window.location.protocol}//${window.location.host}`
        const resp = await fetch(`${base}/api/alerts?limit=50`)
        if (resp.ok) {
          const data = await resp.json()
          setAlerts(data.alerts || [])
          setBadgeCount((data.alerts || []).filter((a: Alert) => a.severity === 'HIGH').length)
        }
      } catch (err) {
        console.error('Alerts fetch error:', err)
      }
    }
    fetchAlerts()
    const interval = setInterval(fetchAlerts, 30000)
    return () => clearInterval(interval)
  }, [])

  // Listen for real-time alerts via WebSocket
  useEffect(() => {
    const handleAlert = (e: CustomEvent) => {
      const alert = e.detail?.data
      if (!alert) return
      setAlerts(prev => [alert, ...prev].slice(0, 50))
      if (alert.severity === 'HIGH') {
        setBadgeCount(prev => prev + 1)
      }
    }
    window.addEventListener('alert', handleAlert as EventListener)
    return () => window.removeEventListener('alert', handleAlert as EventListener)
  }, [])

  const formatTime = (isoStr: string): string => {
    try {
      const d = new Date(isoStr)
      return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
    } catch {
      return ''
    }
  }

  return (
    <div className="sidebar-card">
      <div className="sidebar-card-header">
        <span className="sidebar-card-title">Alerts</span>
        {badgeCount > 0 && (
          <span className="alert-badge">{badgeCount} new</span>
        )}
      </div>
      <div className="alert-list">
        {alerts.length === 0 ? (
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', padding: '8px 0' }}>
            No alerts yet
          </div>
        ) : (
          alerts.slice(0, 10).map((alert) => (
            <div key={alert.id || alert.time} className="alert-item">
              <span className="alert-icon">{SEVERITY_ICON[alert.severity] || '⚪'}</span>
              <div className="alert-content">
                <div className="alert-type" style={{ color: SEVERITY_COLOR[alert.severity] }}>
                  {TYPE_LABELS[alert.alert_type] || alert.alert_type}
                </div>
                <div className="alert-message">{alert.message}</div>
              </div>
              <span className="alert-time">{formatTime(alert.time)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AlertsPanel.tsx
git commit -m "feat(frontend): add AlertsPanel with real-time alert list and severity icons"
```

---

## Task 9: Frontend — DarkPoolPanel Component

**Files:**
- Create: `frontend/src/components/DarkPoolPanel.tsx`

- [ ] **Step 1: Create `DarkPoolPanel.tsx`**

```tsx
import React, { useState, useEffect } from 'react'

interface DixData {
  date: string
  underlying: string
  short_volume: number
  total_volume: number
  short_ratio: number
  dix: number
  dark_volume_estimate: number
}

export const DarkPoolPanel: React.FC<{ underlying: string }> = ({ underlying }) => {
  const [dixData, setDixData] = useState<DixData | null>(null)
  const [history, setHistory] = useState<DixData[]>([])

  useEffect(() => {
    const fetchData = async () => {
      try {
        const base = `${window.location.protocol}//${window.location.host}`
        const [dixResp, histResp] = await Promise.all([
          fetch(`${base}/api/darkpool/dix/${underlying}`),
          fetch(`${base}/api/darkpool/history/${underlying}?days=7`),
        ])
        if (dixResp.ok) {
          const data = await dixResp.json()
          setDixData(data)
        }
        if (histResp.ok) {
          const data = await histResp.json()
          setHistory(data.history || [])
        }
      } catch (err) {
        console.error('Dark pool fetch error:', err)
      }
    }
    fetchData()
    const interval = setInterval(fetchData, 300000) // Refresh every 5 min
    return () => clearInterval(interval)
  }, [underlying])

  const dix = dixData?.dix
  const shortRatio = dixData?.short_ratio
  const totalVol = dixData?.total_volume

  const dixLevel: 'low' | 'mid' | 'high' = dix != null
    ? (dix < 0.15 ? 'low' : dix > 0.45 ? 'high' : 'mid')
    : 'mid'

  const formatVol = (v: number | undefined): string => {
    if (!v) return '—'
    if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`
    if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`
    if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`
    return v.toString()
  }

  return (
    <div className="sidebar-card">
      <div className="sidebar-card-header">
        <span className="sidebar-card-title">Dark Pool</span>
        <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>
          {dixData?.date || '—'}
        </span>
      </div>

      {/* DIX Gauge */}
      <div style={{ marginBottom: '8px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: 'var(--text-muted)' }}>
          <span>DIX (Dark Index)</span>
          <span style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontWeight: 700,
            color: dixLevel === 'high' ? 'var(--success)' : dixLevel === 'low' ? 'var(--danger)' : 'var(--warning)',
          }}>
            {dix != null ? dix.toFixed(4) : '—'}
          </span>
        </div>
        <div className="dix-gauge">
          <div
            className={`dix-gauge-fill ${dixLevel}`}
            style={{ width: `${dix != null ? dix * 100 : 0}%` }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.45rem', color: 'var(--text-muted)' }}>
          <span>0 (bearish)</span>
          <span>1 (bullish)</span>
        </div>
      </div>

      {/* Metrics */}
      <div className="dix-metric">
        <span className="dix-label">Short Ratio</span>
        <span className="dix-value">
          {shortRatio != null ? `${(shortRatio * 100).toFixed(1)}%` : '—'}
        </span>
      </div>
      <div className="dix-metric">
        <span className="dix-label">Total Volume</span>
        <span className="dix-value">{formatVol(totalVol)}</span>
      </div>
      <div className="dix-metric">
        <span className="dix-label">Dark Vol Est.</span>
        <span className="dix-value">{formatVol(dixData?.dark_volume_estimate)}</span>
      </div>

      {/* 7-day Sparkline */}
      {history.length > 1 && (
        <div style={{ marginTop: '8px' }}>
          <div style={{ fontSize: '0.55rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
            7-Day DIX
          </div>
          <svg viewBox="0 0 100 30" style={{ width: '100%', height: 30 }}>
            {(() => {
              const points = history.reverse()
              const min = Math.min(...points.map(p => p.dix))
              const max = Math.max(...points.map(p => p.dix))
              const range = max - min || 0.01
              const pathD = points.map((p, i) => {
                const x = (i / (points.length - 1)) * 100
                const y = 28 - ((p.dix - min) / range) * 26
                return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
              }).join(' ')
              return <path d={pathD} fill="none" stroke="var(--primary)" strokeWidth="1.5" />
            })()}
          </svg>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/DarkPoolPanel.tsx
git commit -m "feat(frontend): add DarkPoolPanel with DIX gauge and sparkline"
```

---

## Task 10: Frontend — Wire Components into App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add imports for new components**

After line 3 (`import { SmartMoneyBox }...`), add:

```tsx
import { GreeksPanel } from './components/GreeksPanel'
import { AlertsPanel } from './components/AlertsPanel'
import { DarkPoolPanel } from './components/DarkPoolPanel'
```

- [ ] **Step 2: Add alert WebSocket listener in App component**

In the `App` function, inside the `ws.onmessage` handler (line 219), after the existing `if (msg.type === 'tick' || msg.type === 'flow_tick')` block (line 222), add:

```tsx
          if (msg.type === 'alert') {
            window.dispatchEvent(new CustomEvent('alert', { detail: msg }))
          }
```

- [ ] **Step 3: Add sidebar panels to the ChartPanel component**

In `ChartPanel`, after the closing `</div>` of `chart-container` (line 200), and before the closing `</div>` of `chart-panel` (line 201), add a sidebar section:

Replace the return statement of `ChartPanel` (lines 155-202) with:

```tsx
  return (
    <div className="chart-panel">
      <div className="panel-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
          <h2>{label}</h2>
          <div className="timeframe-selector">
            {(['1m', '5m', '15m'] as const).map(tf => (
              <button
                key={tf}
                className={`timeframe-btn ${intervalOption === tf ? 'active' : ''}`}
                onClick={() => setIntervalOption(tf)}
              >
                {tf}
              </button>
            ))}
            <button
              className="timeframe-btn"
              onClick={onExpandToggle}
              title={isExpanded ? "Collapse" : "Expand"}
            >
              {isExpanded ? '⛶' : '⛶'}
            </button>
          </div>
          {zeroGamma && <span className="zero-gamma-label" title="Zero Gamma Level">0GEX: {zeroGamma}</span>}
        </div>
        {lastPrice && <span className="panel-price">{lastPrice.toFixed(2)}</span>}
      </div>
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div className="chart-container" style={{ flex: 1 }}>
          <div className="chart-main">
            <LightweightChart candles={candles} lastTick={lastTick} gexData={gexData} />
            <div
              className="smart-money-overlay"
              style={{ left: pos.x, top: pos.y }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
            >
              <SmartMoneyBox underlying={underlying} />
            </div>
          </div>
        </div>
        <div className="sidebar-panel" style={{ padding: '0.5rem', overflowY: 'auto' }}>
          <GreeksPanel underlying={underlying} />
          <AlertsPanel />
          <DarkPoolPanel underlying={underlying} />
        </div>
      </div>
    </div>
  )
```

- [ ] **Step 4: Verify build compiles**

Run: `cd frontend && npm run build 2>&1 | tail -10`
Expected: Build succeeds with no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): wire GreeksPanel, AlertsPanel, DarkPoolPanel into sidebar layout"
```

---

## Task 11: Frontend — Update Existing Component Themes

**Files:**
- Modify: `frontend/src/components/LightweightChart.tsx`
- Modify: `frontend/src/components/SmartMoneyBox.tsx`

- [ ] **Step 1: Update chart colors in `LightweightChart.tsx`**

In the chart creation options (lines 60-88), replace the color values:

Line 63: `'transparent'` stays (background is handled by CSS)
Line 64: `textColor: '#00ff41'` → `textColor: '#94a3b8'`
Lines 67-68: grid colors → `rgba(30, 41, 59, 0.5)` (both vertLines and horzLines)
Line 72: `borderColor: '#008f11'` → `borderColor: '#1e293b'`
Line 86: `borderColor: '#008f11'` → `borderColor: '#1e293b'`

Candle colors (lines 94-98):
```
upColor: '#10b981'
downColor: '#ef4444'
wickUpColor: '#10b981'
wickDownColor: '#ef4444'
```

Canvas background (line 314): `'#000000'` → `'#0a0e17'`

Heatmap line colors (lines 359, 361):
- Call: `rgba(239, 68, 68, ${alpha})` (red)
- Put: `rgba(16, 185, 129, ${alpha})` (green)

Gamma Flip label (lines 393-394): Keep gold but use `rgba(245, 158, 11, 0.9)`

- [ ] **Step 2: Update SmartMoneyBox inline styles**

In `SmartMoneyBox.tsx`, update the inline style colors:

Line 241: `borderBottom: '1px solid #003b00'` → `borderBottom: '1px solid var(--border)'`
Line 257: `color: '#008f11'` → `color: 'var(--text-muted)'`
Line 261: `background: '#0a0a0a'` → `background: 'var(--bg-primary)'`
Line 261: `border: '1px solid #003b00'` → `border: '1px solid var(--border)'`
Line 263: `background: '#008f11'` → `background: 'var(--border)'`
Line 293: `color: '#008f11'` → `color: 'var(--text-muted)'`
Line 297: `background: '#050505'` → `background: 'var(--bg-primary)'`

Signal colors — replace hex with CSS variables:
- `#00ff41` → `'var(--success)'` (for bullish)
- `#ff003c` → `'var(--danger)'` (for bearish)
- `#008f11` → `'var(--text-muted)'` (for neutral)

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LightweightChart.tsx frontend/src/components/SmartMoneyBox.tsx
git commit -m "feat(frontend): apply dark theme to chart and smart money components"
```

---

## Task 12: Final Integration Test & Deploy

- [ ] **Step 1: Full backend smoke test**

Run: `cd backend && python3 -c "from main import app; from greeks_service import GreeksService; from alert_engine import AlertEngine; from darkpool_analyzer import DarkPoolAnalyzer; print('All imports OK')"`

- [ ] **Step 2: Frontend production build**

Run: `cd frontend && npm run build`
Expected: `dist/` generated with no errors

- [ ] **Step 3: Deploy to VPS**

```bash
python3 .deploy_vps.py
```

Or manual:
```bash
cd frontend && npm run build
scp -r dist/* root@137.220.63.222:/opt/gex_dashboard/frontend/dist/
```

- [ ] **Step 4: Verify endpoints on VPS**

After deploy, check:
- `curl http://137.220.63.222:8000/api/greeks/SPX`
- `curl http://137.220.63.222:8000/api/alerts`
- `curl http://137.220.63.222:8000/api/darkpool/dix/SPX`
- `curl http://137.220.63.222:8000/health`

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: institutional MVP complete — Greeks, Alerts, DarkPool, Dark Theme"
```

---

## Execution Order Summary

Tasks can be parallelized as follows:

**Parallel Group 1** (no dependencies between them):
- Task 1: DB schema
- Task 2: Greeks service
- Task 3: Alert engine
- Task 4: Dark pool analyzer

**Sequential after Group 1:**
- Task 5: Wire into main.py (depends on Tasks 1-4)

**Parallel Group 2** (no dependencies between them, can use mock data):
- Task 6: Dark theme CSS
- Task 7: GreeksPanel
- Task 8: AlertsPanel
- Task 9: DarkPoolPanel

**Sequential after Group 2:**
- Task 10: Wire into App.tsx (depends on Tasks 7-9)
- Task 11: Update existing component themes (depends on Task 6)

**Final:**
- Task 12: Integration test & deploy (depends on all)
