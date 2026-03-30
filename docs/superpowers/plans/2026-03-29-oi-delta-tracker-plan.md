# OI Delta Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track Open Interest delta per strike with retail (<100 contracts) vs block (≥100) breakdown. Display top 3 call + top 3 put buildup in GreeksPanel and as overlay lines in LightweightChart.

**Architecture:** OI snapshots saved every 30 min from Tradier chain data. OI delta computed vs previous close. Retail/block breakdown derived from flow aggregation in `options_flow` table. New `oi_tracker.py` module + REST endpoint.

**Tech Stack:** FastAPI, asyncpg, Tradier API, React TypeScript

---

## File Map

```
backend/
├── db.py                          # ALTER options_flow + CREATE oi_snapshots
├── oi_tracker.py                  # NEW — OITracker class
├── greeks_service.py             # ADD fetch_oi_snapshot() + get_oi_for_strikes()
├── main.py                        # ADD endpoint + background task + startup init
frontend/src/
├── components/
│   ├── GreeksPanel.tsx            # ADD OI Buildup section
│   └── LightweightChart.tsx       # ADD OI overlay lines
```

---

## Task 1: Database Migration

**Files:**
- Modify: `backend/db.py:1-165`

- [ ] **Step 1: Add `oi_delta` column to `options_flow` table**

In `db.py`, after the `options_flow` table creation (line 40-58), add an ALTER statement inside `init_db()`:

```python
# After options_flow hypertable creation (after line 58)
await conn.execute("""
    ALTER TABLE options_flow ADD COLUMN IF NOT EXISTS oi_delta INTEGER;
    COMMENT ON COLUMN options_flow.oi_delta IS 'Delta OI session-over-session for this strike, set on insert from batch OI snapshot';
""")
```

- [ ] **Step 2: Add `oi_snapshots` table creation in `init_db()`**

After the `darkpool_daily` table creation (after line 159), add:

```python
# 9. Table for OI Snapshots (30-min intervals)
await conn.execute("""
    CREATE TABLE IF NOT EXISTS oi_snapshots (
        time TIMESTAMPTZ NOT NULL,
        underlying VARCHAR(10) NOT NULL,
        strike DOUBLE PRECISION NOT NULL,
        oi_total INTEGER NOT NULL,
        oi_delta INTEGER NOT NULL,
        oi_delta_retail INTEGER NOT NULL DEFAULT 0,
        oi_delta_block INTEGER NOT NULL DEFAULT 0,
        side VARCHAR(4) NOT NULL,
        PRIMARY KEY (time, underlying, strike)
    );
""")
try:
    await conn.execute("SELECT create_hypertable('oi_snapshots', 'time', if_not_exists => TRUE);")
except Exception as e:
    print(f"Hypertable oi_snapshots notice: {e}")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_oi_snapshots_underlying_strike
    ON oi_snapshots (underlying, strike, time DESC);
""")
```

- [ ] **Step 3: Verify migration**

Run: `cd backend && python3 -c "import asyncio; from db import init_db; asyncio.run(init_db())"`
Expected: prints "Database initialization complete." with no errors

- [ ] **Step 4: Commit**

```bash
git add backend/db.py
git commit -m "feat(db): add oi_snapshots table and oi_delta column"
```

---

## Task 2: OI Tracker Module

**Files:**
- Create: `backend/oi_tracker.py`

- [ ] **Step 1: Write OITracker class skeleton**

```python
"""
OI Tracker — fetches OI snapshots from Tradier, computes delta vs close,
derives retail/block breakdown from flow, provides buildup API.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

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
            prev_oi = prev.get(strike, oi_total)  # if no prev, assume first observation
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

        # Bulk insert
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

        # Sort by absolute oi_delta, take top 3
        for side in by_side:
            by_side[side].sort(key=lambda x: abs(x["oi_delta"]), reverse=True)
            by_side[side] = by_side[side][:3]

        return {
            "calls": by_side["CALL"],
            "puts": by_side["PUT"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
```

- [ ] **Step 2: Test OITracker module in isolation**

Create `backend/test_oi_tracker.py`:

```python
import asyncio
from oi_tracker import OITracker

async def test():
    from db import get_db_pool
    pool = await get_db_pool()
    tracker = OITracker(pool)
    # Test fetch from Tradier
    data = await tracker.fetch_oi_from_tradier("SPX")
    print(f"SPX strikes with OI: {len(data)}")
    print(f"Sample: {data[:3] if data else 'none'}")
    await pool.close()

if __name__ == "__main__":
    asyncio.run(test())
```

Run: `cd backend && python3 test_oi_tracker.py`
Expected: Prints number of SPX strikes with OI data (should be non-empty during market hours)

- [ ] **Step 3: Remove test file, commit**

```bash
rm backend/test_oi_tracker.py
git add backend/oi_tracker.py
git commit -m "feat: add OITracker class for OI delta tracking"
```

---

## Task 3: Greeks Service — Add OI Snapshot Methods

**Files:**
- Modify: `backend/greeks_service.py:1-369`

- [ ] **Step 1: Add `fetch_oi_snapshot()` to GreeksService class**

After `get_volatility_surface()` method (after line 368), add:

```python
async def fetch_oi_snapshot(self, underlying: str) -> List[dict]:
    """
    Fetch OI per strike from Tradier chain.
    Uses the same chain fetching logic as get_chain_greeks but returns OI.
    """
    chain_data = await self._fetch_chain(underlying)
    result = []
    for opt in chain_data:
        oi = opt.get("open_interest")
        if oi is None:
            continue
        result.append({
            "strike": float(opt.get("strike")),
            "oi_total": int(oi),
            "side": opt.get("option_type", "").upper(),
        })
    return result
```

- [ ] **Step 2: Commit**

```bash
git add backend/greeks_service.py
git commit -m "feat(greeks_service): add fetch_oi_snapshot method"
```

---

## Task 4: Main.py — Endpoint + Background Task

**Files:**
- Modify: `backend/main.py:1-1289`

- [ ] **Step 1: Import OITracker in startup**

In `main.py` startup event (line 32-58), add:

At line 7 (imports), add:
```python
from oi_tracker import OITracker
```

After line 55 (services initialized), add:
```python
oi_tracker = OITracker(db_pool)
```

In `startup_event()` after line 56, add background task:
```python
asyncio.create_task(snapshot_oi_every_30min())
```

- [ ] **Step 2: Add OI snapshot background task**

After `broadcast_reversal_signals()` function (after line 223), add:

```python
async def snapshot_oi_every_30min():
    """Snapshot OI every 30 minutes during RTH (9:30-16:00 ET)."""
    global oi_tracker, db_pool
    await asyncio.sleep(10)  # wait for startup

    while True:
        try:
            now_et = datetime.now(timezone(timedelta(hours=-5)))
            hour = now_et.hour
            # Only run during RTH: 9:30-16:00 ET (14:30-20:00 UTC)
            if 14 <= hour < 20 and oi_tracker and db_pool:
                await oi_tracker.snapshot_and_store("SPX")
                await oi_tracker.snapshot_and_store("QQQ")
                logger.info("OI snapshot completed for SPX and QQQ")
        except Exception as e:
            logger.error(f"OI snapshot error: {e}")
        await asyncio.sleep(1800)  # 30 minutes
```

- [ ] **Step 3: Add OI buildup REST endpoint**

After the darkpool endpoints (after line 1276), add:

```python
@app.get("/api/oi/buildup/{underlying}")
async def get_oi_buildup(underlying: str):
    """Return top 3 calls + top 3 puts per OI delta."""
    if not oi_tracker:
        return {"error": "OI tracker not initialized", "calls": [], "puts": []}
    underlying = underlying.upper()
    if underlying not in ("SPX", "QQQ"):
        return {"error": "Invalid underlying", "calls": [], "puts": []}
    try:
        return oi_tracker.get_buildup(underlying)
    except Exception as e:
        logger.error(f"OI buildup error: {e}")
        return {"error": str(e), "calls": [], "puts": []}
```

- [ ] **Step 4: Test endpoint manually**

Start the backend: `cd backend && uvicorn main:app --reload`
Call: `curl http://localhost:8000/api/oi/buildup/SPX`
Expected: JSON with `calls` and `puts` arrays (empty if no data yet, or populated if market open)

- [ ] **Step 5: Commit**

```bash
git add backend/main.py
git commit -m "feat(main): add OI buildup endpoint and 30min snapshot task"
```

---

## Task 5: GreeksPanel — OI Buildup Section

**Files:**
- Modify: `frontend/src/components/GreeksPanel.tsx:1-117`

- [ ] **Step 1: Add OI Buildup types and state**

After line 30 (before `export const GreeksPanel`), add:

```typescript
interface OIBuildupEntry {
  strike: number
  oi_delta: number
  oi_delta_retail: number
  oi_delta_block: number
  side: 'call' | 'put'
}

interface OIBuildupData {
  calls: OIBuildupEntry[]
  puts: OIBuildupEntry[]
  updated_at: string
}
```

In `GreeksPanel` component (line 31), update state:

```typescript
const [greeks, setGreeks] = useState<GreeksData | null>(null)
const [summary, setSummary] = useState<GreeksSummaryData | null>(null)
const [oiBuildup, setOiBuildup] = useState<OIBuildupData | null>(null)
```

- [ ] **Step 2: Add OI fetch in useEffect**

After line 49 (inside fetchGreeks), add OI fetch:

```typescript
const base = `${window.location.protocol}//${window.location.host}`
const [chainResp, summaryResp, oiResp] = await Promise.all([
    fetch(`${base}/api/greeks/${underlying}`),
    fetch(`${base}/api/greeks/summary/${underlying}`),
    fetch(`${base}/api/oi/buildup/${underlying}`),
])
if (chainResp.ok) setGreeks(await chainResp.json())
if (summaryResp.ok) setSummary(await summaryResp.json())
if (oiResp.ok) setOiBuildup(await oiResp.json())
```

Update the interval to 30000 (30s) for OI polling:
Change `setInterval(fetchGreeks, 60000)` to `setInterval(fetchGreeks, 30000)`

- [ ] **Step 3: Add OI Buildup rendering**

After the last `</div>` in the return statement (before line 116), add:

```typescript
{oiBuildup && (oiBuildup.calls.length > 0 || oiBuildup.puts.length > 0) && (
  <div style={{ marginTop: '12px', borderTop: '1px solid rgba(148,163,184,0.1)', paddingTop: '8px' }}>
    <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginBottom: '6px', fontWeight: 600 }}>
      OI BUILDUP
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', fontSize: '0.58rem' }}>
      {/* Calls */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', color: '#22C55E', marginBottom: '2px' }}>
          <span>CALLS</span><span>ΔOI</span>
        </div>
        {oiBuildup.calls.map((c) => {
          const total = Math.abs(c.oi_delta_retail + c.oi_delta_block);
          const blockPct = total > 0 ? Math.abs(c.oi_delta_block) / total : 0;
          return (
            <div key={c.strike} style={{ display: 'flex', justifyContent: 'space-between', color: '#22C55E', fontFamily: "'JetBrains Mono', monospace" }}>
              <span>{c.strike.toFixed(0)}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span>{c.oi_delta >= 0 ? '+' : ''}{c.oi_delta}</span>
                {blockPct > 0.5 && <span style={{ fontSize: '0.5rem', opacity: 0.7 }}>BLK</span>}
              </div>
            </div>
          );
        })}
      </div>
      {/* Puts */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', color: '#EF4444', marginBottom: '2px' }}>
          <span>PUTS</span><span>ΔOI</span>
        </div>
        {oiBuildup.puts.map((p) => {
          const total = Math.abs(p.oi_delta_retail + p.oi_delta_block);
          const blockPct = total > 0 ? Math.abs(p.oi_delta_block) / total : 0;
          return (
            <div key={p.strike} style={{ display: 'flex', justifyContent: 'space-between', color: '#EF4444', fontFamily: "'JetBrains Mono', monospace" }}>
              <span>{p.strike.toFixed(0)}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span>{p.oi_delta >= 0 ? '+' : ''}{p.oi_delta}</span>
                {blockPct > 0.5 && <span style={{ fontSize: '0.5rem', opacity: 0.7 }}>BLK</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  </div>
)}
```

- [ ] **Step 4: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -30`
Expected: No errors related to OI Buildup types

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/GreeksPanel.tsx
git commit -m "feat(frontend): add OI Buildup section to GreeksPanel"
```

---

## Task 6: LightweightChart — OI Overlay Lines

**Files:**
- Modify: `frontend/src/components/LightweightChart.tsx:1-569`

- [ ] **Step 1: Add OILevel interface**

After line 33 (after `FlowConcentration` interface), add:

```typescript
interface OILevel {
  strike: number
  oiDelta: number
  oiDeltaRetail: number
  oiDeltaBlock: number
  side: 'call' | 'put'
}
```

- [ ] **Step 2: Add `oiLevels` prop to ChartProps**

In `interface ChartProps` (line 35), add after `flowConcentration`:

```typescript
oiLevels?: OILevel[]
```

- [ ] **Step 3: Add OI lines to canvas overlay drawing**

In the `drawOverlay()` function inside the `useEffect` at line 336, after the Skew Zones section (`drawSkewZones()` call, around line 525), add:

```typescript
// ── OI Buildup Levels ───────────────────────────────────────────
if (oiLevels && oiLevels.length > 0 && seriesRef.current) {
  const maxDelta = Math.max(...oiLevels.map(l => Math.abs(l.oiDelta)));
  if (maxDelta > 0) {
    for (const level of oiLevels) {
      // Translate strike to future price using gexData
      let futurePrice = level.strike;
      const strikeData = gexData.find(g => Math.abs(g.strike - level.strike) < 1);
      if (strikeData?.futurePrice) {
        futurePrice = strikeData.futurePrice;
      } else {
        // Fallback using keyLevels
        if (keyLevels?.call_wall?.price && keyLevels?.zgl?.price) {
          const mult = keyLevels.call_wall.price / keyLevels.zgl.price;
          futurePrice = level.strike * mult + keyLevels.zgl.price - level.strike;
        }
      }

      const y = seriesRef.current.priceToCoordinate(futurePrice);
      if (y === null || y < 0 || y > height) continue;

      const isCall = level.side === 'call';
      const color = isCall ? '#00C853' : '#FF1744';
      const opacity = 0.6;
      const isBlockOnly = Math.abs(level.oiDeltaBlock) > Math.abs(level.oiDeltaRetail);
      const dashed = isBlockOnly;
      const prefix = isCall ? 'C' : 'P';

      const r = parseInt(color.slice(1, 3), 16);
      const g = parseInt(color.slice(3, 5), 16);
      const b = parseInt(color.slice(5, 7), 16);
      const rgba = `rgba(${r},${g},${b},${opacity})`;

      ctx.beginPath();
      ctx.strokeStyle = rgba;
      ctx.lineWidth = 1.5;
      ctx.setLineDash(dashed ? [6, 4] : []);
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Label at top of line
      const labelText = `${prefix} ${level.strike.toFixed(0)} ${level.oiDelta >= 0 ? '+' : ''}${level.oiDelta}`;
      ctx.font = '10px monospace';
      const tm = ctx.measureText(labelText);
      const lx = 4;
      const ly = y - 2;
      ctx.fillStyle = 'rgba(10,14,23,0.85)';
      ctx.fillRect(lx - 3, ly - 10, tm.width + 6, 13);
      ctx.fillStyle = rgba;
      ctx.fillText(labelText, lx, ly);
    }
  }
}
```

- [ ] **Step 4: Add `oiLevels` to useEffect dependency array**

In the `useEffect` at line 536, add `oiLevels` to the dependency array:

Change:
```typescript
}, [keyLevels, flowConcentration, containerSize, skewZones]);
```
To:
```typescript
}, [keyLevels, flowConcentration, containerSize, skewZones, oiLevels]);
```

- [ ] **Step 5: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/LightweightChart.tsx
git commit -m "feat(chart): add OI buildup overlay lines to LightweightChart"
```

---

## Task 7: Integration — Pass OI Data from App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add OI state and fetch to App.tsx**

In `App.tsx`, add state and effect similar to other API data. Search for how `gexData` is fetched and follow the same pattern for `/api/oi/buildup/{underlying}`. Pass `oiLevels` to the `LightweightChart` component as the `oiLevels` prop.

- [ ] **Step 2: Commit**

---

## Verification Checklist

After all tasks:
- [ ] DB migration creates `oi_snapshots` table
- [ ] `/api/oi/buildup/SPX` returns calls + puts arrays
- [ ] GreeksPanel shows OI BUILDUP section with top 3 calls + top 3 puts
- [ ] LightweightChart renders 6 vertical colored lines for OI levels
- [ ] No TypeScript errors on frontend build
- [ ] Backend starts without import errors

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| OI delta per strike | Task 2 (oi_tracker.py + derive_retail_block_delta) |
| Retail < 100 / Block ≥ 100 breakdown | Task 2 (RETAIL_THRESHOLD constant) |
| Top 3 calls + top 3 puts | Task 2 (get_buildup()) |
| GreeksPanel visualization | Task 5 |
| Chart overlay lines (green/red, dashed for block-only) | Task 6 |
| 30-min snapshot during RTH | Task 4 (snapshot_oi_every_30min) |
| REST endpoint `/api/oi/buildup/{underlying}` | Task 4 |
