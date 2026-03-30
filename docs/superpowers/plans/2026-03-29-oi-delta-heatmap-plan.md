# OI Delta Heatmap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace VolSurface.tsx (IV heatmap) with OI Delta Heatmap — shows how OI buildup shifts over last 5 snapshots (9:30–11:30). Rows = strikes (raw + translated future price), columns = time slots, cell color = call (green) vs put (red).

**Architecture:** New REST endpoint `/api/oi/heatmap/{underlying}` in `main.py` returns heatmap data. `VolSurface.tsx` is repurposed as `OIDeltaHeatmap` — existing component refactored to canvas heatmap with same data structure.

**Tech Stack:** FastAPI, asyncpg, React TypeScript, Canvas API

---

## File Map

```
backend/main.py                 # ADD /api/oi/heatmap/{underlying} endpoint
frontend/src/components/
├── VolSurface.tsx              # REPURPOSE as OI Delta Heatmap
└── App.tsx                    # (no change — component name stays VolSurface)
```

---

## Task 1: Backend — OI Heatmap Endpoint

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add `GET /api/oi/heatmap/{underlying}` endpoint**

After the existing `/api/oi/buildup/{underlying}` endpoint (after line 1315), add:

```python
@app.get("/api/oi/heatmap/{underlying}")
async def get_oi_heatmap(underlying: str):
    """
    Return OI delta heatmap data for last 5 snapshots (2.5h).
    Columns: timestamps of last 5 snapshots
    Rows: strikes with OI delta + translated future price
    """
    if not db_pool:
        return {"error": "DB not connected", "columns": [], "rows": []}
    underlying = underlying.upper()
    if underlying not in ("SPX", "QQQ"):
        return {"error": "Invalid underlying", "columns": [], "rows": []}

    try:
        # Get last 5 snapshot times
        times_rows = await db_pool.fetch("""
            SELECT DISTINCT time_bucket('30 min', time) as bucket
            FROM oi_snapshots
            WHERE underlying = $1
              AND time > NOW() - INTERVAL '3 hours'
            ORDER BY bucket DESC
            LIMIT 5
        """, underlying)

        if not times_rows:
            times_rows = await db_pool.fetch("""
                SELECT DISTINCT time_bucket('30 min', time) as bucket
                FROM oi_snapshots
                WHERE underlying = $1
                ORDER BY bucket DESC
                LIMIT 5
            """, underlying)

        if not times_rows:
            return {
                "underlying": underlying,
                "offset": 0,
                "multiplier": 1.0,
                "future_price": 0,
                "columns": [],
                "rows": [],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        buckets = [r["bucket"] for r in reversed(times_rows)]

        # Get offset and future price
        offset, multiplier = await get_dynamic_offset(underlying)
        future_sym = 'US500-F' if underlying == 'SPX' else 'NAS100-F'
        future_row = await db_pool.fetchrow("""
            SELECT price FROM futures_ticks
            WHERE symbol = $1 AND time > NOW() - INTERVAL '5 minutes'
            ORDER BY time DESC LIMIT 1
        """, future_sym)
        future_price = float(future_row['price']) if future_row else 0

        # Get all strikes with data in these buckets
        rows = await db_pool.fetch("""
            SELECT
                strike,
                side,
                time_bucket('30 min', time) as bucket,
                oi_delta,
                oi_delta_retail,
                oi_delta_block
            FROM oi_snapshots
            WHERE underlying = $1
              AND time_bucket('30 min', time) = ANY($2::timestamptz[])
            ORDER BY strike, bucket
        """, underlying, buckets)

        # Build heatmap structure
        strike_map = {}
        for r in rows:
            strike = float(r["strike"])
            if strike not in strike_map:
                # Compute translated future price
                if multiplier != 1.0:
                    future_p = strike * multiplier + offset
                else:
                    future_p = strike + offset
                strike_map[strike] = {
                    "strike": strike,
                    "future_price": round(future_p, 2),
                    "side": r["side"].lower(),
                    "snapshots": [None] * len(buckets)
                }
            bucket_idx = buckets.index(r["bucket"])
            strike_map[strike]["snapshots"][bucket_idx] = {
                "oi_delta": int(r["oi_delta"]),
                "oi_delta_retail": int(r["oi_delta_retail"]),
                "oi_delta_block": int(r["oi_delta_block"])
            }

        rows_list = sorted(strike_map.values(), key=lambda x: x["strike"])
        column_labels = [b.strftime("%H:%M") for b in buckets]

        return {
            "underlying": underlying,
            "offset": round(offset, 4),
            "multiplier": round(multiplier, 6),
            "future_price": round(future_price, 2),
            "columns": column_labels,
            "rows": rows_list,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"OI heatmap error: {e}", exc_info=True)
        return {"error": str(e), "columns": [], "rows": []}
```

- [ ] **Step 2: Verify syntax**

Run: `cd /Users/paolo/Desktop/GEX\ 4.0/backend && python3 -m py_compile main.py`
Expected: no output (success)

- [ ] **Step 3: Commit**

```bash
cd /Users/paolo/Desktop/GEX\ 4.0
git add backend/main.py
git commit -m "feat(main): add OI heatmap endpoint /api/oi/heatmap/{underlying}"
```

---

## Task 2: Frontend — Repurpose VolSurface as OI Delta Heatmap

**Files:**
- Modify: `frontend/src/components/VolSurface.tsx`

- [ ] **Step 1: Replace all content of VolSurface.tsx**

The entire file needs to be replaced with the new OI Delta Heatmap component.

Current file is ~430 lines. Replace with:

```typescript
import React, { useEffect, useRef, useState, useCallback } from 'react'

interface Snapshot {
  oi_delta: number
  oi_delta_retail: number
  oi_delta_block: number
}

interface OIRow {
  strike: number
  future_price: number
  side: 'call' | 'put'
  snapshots: (Snapshot | null)[]
}

interface OIHeatmapData {
  underlying: string
  offset: number
  multiplier: number
  future_price: number
  columns: string[]   // ["09:30", "10:00", "10:30", "11:00", "11:30"]
  rows: OIRow[]
  updated_at: string
}

export const VolSurface: React.FC<{ underlying: string }> = ({ underlying }) => {
  const [data, setData] = useState<OIHeatmapData | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [tooltip, setTooltip] = useState<{ x: number; y: number; content: string } | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const base = `${window.location.protocol}//${window.location.host}`
      const resp = await fetch(`${base}/api/oi/heatmap/${underlying}`)
      if (resp.ok) {
        const json = await resp.json()
        if (json.columns?.length > 0 || json.rows?.length > 0) {
          setData(json)
        }
      }
    } catch (err) {
      console.error('OI heatmap fetch error:', err)
    }
  }, [underlying])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60000)
    return () => clearInterval(interval)
  }, [fetchData])

  // Canvas rendering
  useEffect(() => {
    if (!canvasRef.current || !data || data.rows.length === 0) return

    const canvas = canvasRef.current
    const container = containerRef.current
    if (!container) return

    canvas.width = container.clientWidth
    canvas.height = Math.max(200, data.rows.length * 28 + 40)

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const COLS = data.columns.length
    const ROWS = data.rows.length
    const HEADER_H = 28
    const ROW_H = 28
    const COL_W = Math.max(50, (canvas.width - 100) / COLS)
    const LABEL_W = 100

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Background
    ctx.fillStyle = '#0a0e17'
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // Column headers (times)
    ctx.font = '11px JetBrains Mono, monospace'
    ctx.fillStyle = '#94a3b8'
    ctx.textAlign = 'center'
    data.columns.forEach((col, j) => {
      const x = LABEL_W + j * COL_W + COL_W / 2
      ctx.fillText(col, x, HEADER_H - 8)
    })

    // Find max absolute delta for scaling
    let maxAbs = 1
    for (const row of data.rows) {
      for (const snap of row.snapshots) {
        if (snap && Math.abs(snap.oi_delta) > maxAbs) {
          maxAbs = Math.abs(snap.oi_delta)
        }
      }
    }

    // Rows
    data.rows.forEach((row, i) => {
      const y = HEADER_H + i * ROW_H

      // Row label (strike / future_price)
      ctx.font = '10px JetBrains Mono, monospace'
      ctx.fillStyle = row.side === 'call' ? '#22C55E' : '#EF4444'
      ctx.textAlign = 'left'
      ctx.fillText(`${row.strike.toFixed(0)} / ${row.future_price.toFixed(0)}`, 4, y + ROW_H - 8)

      // Cells
      row.snapshots.forEach((snap, j) => {
        const x = LABEL_W + j * COL_W
        if (snap === null) {
          ctx.fillStyle = '#1e293b'
        } else {
          const abs = Math.abs(snap.oi_delta)
          const intensity = Math.min(1, abs / maxAbs)
          if (snap.oi_delta > 0) {
            // Call — green scale
            const r = Math.round(0 + (34 - 0) * (1 - intensity))
            const g = Math.round(200 + (255 - 200) * intensity)
            const b = Math.round(83 + (202 - 83) * (1 - intensity))
            ctx.fillStyle = `rgba(${r},${g},${b},0.85)`
          } else if (snap.oi_delta < 0) {
            // Put — red scale
            const r = Math.round(255 + (239 - 255) * (1 - intensity))
            const g = Math.round(23 + (68 - 23) * (1 - intensity))
            const b = Math.round(68 + (69 - 68) * (1 - intensity))
            ctx.fillStyle = `rgba(${r},${g},${b},0.85)`
          } else {
            ctx.fillStyle = '#1e293b'
          }
        }
        ctx.fillRect(x + 1, y + 1, COL_W - 2, ROW_H - 2)

        // Cell value label
        if (snap !== null && COL_W > 45) {
          ctx.font = '9px JetBrains Mono, monospace'
          ctx.fillStyle = '#ffffff'
          ctx.textAlign = 'center'
          const label = snap.oi_delta >= 0 ? `+${snap.oi_delta}` : `${snap.oi_delta}`
          ctx.fillText(label, x + COL_W / 2, y + ROW_H / 2 + 3)
        }
      })
    })

    // Hover detection
    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top

      if (my < HEADER_H || mx < LABEL_W) {
        setTooltip(null)
        return
      }

      const col = Math.floor((mx - LABEL_W) / COL_W)
      const row = Math.floor((my - HEADER_H) / ROW_H)

      if (col >= 0 && col < COLS && row >= 0 && row < ROWS) {
        const r = data.rows[row]
        const s = r.snapshots[col]
        if (s) {
          setTooltip({
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
            content: `Strike: ${r.strike.toFixed(0)} | Future: ${r.future_price.toFixed(2)}\n` +
                     `OI Δ: ${s.oi_delta >= 0 ? '+' : ''}${s.oi_delta}\n` +
                     `Retail: ${s.oi_delta_retail >= 0 ? '+' : ''}${s.oi_delta_retail} | ` +
                     `Block: ${s.oi_delta_block >= 0 ? '+' : ''}${s.oi_delta_block}`
          })
          return
        }
      }
      setTooltip(null)
    }

    canvas.onmousemove = handleMouseMove
    canvas.onmouseleave = () => setTooltip(null)

  }, [data])

  return (
    <div className="sidebar-card" style={{ position: 'relative' }}>
      <div className="sidebar-card-header">
        <span className="sidebar-card-title">OI Delta Heatmap</span>
        {data && (
          <span style={{ fontSize: '0.55rem', color: 'var(--text-muted)' }}>
            {data.underlying} · FP: {data.future_price.toFixed(2)}
          </span>
        )}
      </div>

      {!data || (data.rows.length === 0) ? (
        <div style={{ padding: '12px', fontSize: '0.6rem', color: 'var(--text-muted)', textAlign: 'center' }}>
          No OI data available
        </div>
      ) : (
        <div ref={containerRef} style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
          <canvas ref={canvasRef} style={{ display: 'block', minWidth: '100%' }} />
          {tooltip && (
            <div style={{
              position: 'absolute',
              left: tooltip.x + 10,
              top: tooltip.y - 10,
              background: 'rgba(10,14,23,0.95)',
              border: '1px solid #334155',
              borderRadius: '4px',
              padding: '6px 8px',
              fontSize: '0.58rem',
              fontFamily: 'JetBrains Mono, monospace',
              color: '#e2e8f0',
              whiteSpace: 'pre-line',
              pointerEvents: 'none',
              zIndex: 10,
            }}>
              {tooltip.content}
            </div>
          )}
        </div>
      )}

      {data && data.updated_at && (
        <div style={{ fontSize: '0.5rem', color: 'var(--text-muted)', textAlign: 'right', padding: '2px 4px' }}>
          {new Date(data.updated_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd /Users/paolo/Desktop/GEX\ 4.0/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
cd /Users/paolo/Desktop/GEX\ 4.0
git add frontend/src/components/VolSurface.tsx
git commit -m "feat(frontend): repurpose VolSurface as OI Delta Heatmap"
```

---

## Task 3: Redeploy to VPS

**Files:**
- Modify: `backend/main.py` (already committed)

- [ ] **Step 1: Build frontend**

Run: `cd /Users/paolo/Desktop/GEX\ 4.0/frontend && npm run build 2>&1 | tail -5`
Expected: Build completed

- [ ] **Step 2: Deploy via .deploy_frontend.py**

Run: `cd /Users/paolo/Desktop/GEX\ 4.0 && python3 .deploy_frontend.py 2>&1 | tail -10`
Expected: Deployment complete

- [ ] **Step 3: Manually upload oi_tracker.py and main.py (if not in tarball)**

The .deploy_frontend.py only uploads main.py and frontend dist. Need to check if it handles backend files properly or manually upload main.py.

```bash
# Check if main.py is in the dist tarball
python3 -c "
import tarfile
with tarfile.open('/Users/paolo/Desktop/GEX 4.0/gex_deploy.tar.gz') as t:
    names = t.getnames()
    print([n for n in names if 'main.py' in n or 'oi_tracker' in n])
"
```

If not included, use paramiko to upload both files and restart gex_api.

- [ ] **Step 4: Test endpoint**

```bash
curl -s http://137.220.63.222/api/oi/heatmap/SPX | python3 -m json.tool
```
Expected: JSON with columns and rows (empty if no OI data yet)

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| New endpoint `/api/oi/heatmap/{underlying}` | Task 1 |
| 5 snapshot columns (9:30–11:30) | Task 1 |
| Strikes with future_price translation | Task 1 |
| Canvas heatmap rendering | Task 2 |
| Green for calls, red for puts, intensity = magnitude | Task 2 |
| Strike / future_price label per row | Task 2 |
| Tooltip on hover | Task 2 |
| "No data" state | Task 2 |
| Deployment to VPS | Task 3 |
