# OI Delta Heatmap — Design Spec

## Overview

Replace `VolSurface.tsx` (IV heatmap) with an OI Delta Heatmap showing how Open Interest buildup shifts during the session. Rows = strikes (both raw index strike + translated future price), columns = 5 most recent 30-min snapshots (9:30–11:30). Cell color intensity = OI delta magnitude, color = call (green) vs put (red).

## Architecture

### Backend

**New endpoint: `GET /api/oi/heatmap/{underlying}`**

```python
@app.get("/api/oi/heatmap/{underlying}")
async def get_oi_heatmap(underlying: str):
    """
    Return OI delta heatmap data for last 5 snapshots (2.5h).
    Columns: timestamps of last 5 snapshots
    Rows: strikes with OI delta
    Each cell: {oi_delta, oi_delta_retail, oi_delta_block}
    """
```

Response:
```json
{
  "underlying": "SPX",
  "spot_price": 6368.85,
  "future_price": 6399.6,
  "offset": 30.75,
  "columns": ["09:30", "10:00", "10:30", "11:00", "11:30"],
  "rows": [
    {
      "strike": 5350,
      "future_price": 5380.75,
      "side": "put",
      "snapshots": [
        { "oi_delta": -120, "oi_delta_retail": -80, "oi_delta_block": -40, "ts": "..." },
        { "oi_delta": -150, "oi_delta_retail": -90, "oi_delta_block": -60, "ts": "..." },
        ...
      ]
    },
    ...
  ],
  "updated_at": "..."
}
```

**Implementation in `main.py`:**
```python
@app.get("/api/oi/heatmap/{underlying}")
async def get_oi_heatmap(underlying: str):
    if not db_pool:
        return {"error": "DB not connected"}
    underlying = underlying.upper()
    if underlying not in ("SPX", "QQQ"):
        return {"error": "Invalid underlying"}

    # Get last 5 snapshot times for this underlying
    times_rows = await db_pool.fetch("""
        SELECT DISTINCT time_bucket('30 min', time) as bucket
        FROM oi_snapshots
        WHERE underlying = $1
          AND time > NOW() - INTERVAL '3 hours'
        ORDER BY bucket DESC
        LIMIT 5
    """, underlying)

    # If no data, try last available
    if not times_rows:
        times_rows = await db_pool.fetch("""
            SELECT DISTINCT time_bucket('30 min', time) as bucket
            FROM oi_snapshots
            WHERE underlying = $1
            ORDER BY bucket DESC
            LIMIT 5
        """, underlying)

    buckets = [r["bucket"] for r in times_rows]

    # Get current spot + future for offset
    offset, multiplier = await get_dynamic_offset(underlying)
    future_row = await db_pool.fetchrow("""
        SELECT price FROM futures_ticks
        WHERE symbol = $1 AND time > NOW() - INTERVAL '5 minutes'
        ORDER BY time DESC LIMIT 1
    """, 'US500-F' if underlying == 'SPX' else 'NAS100-F')
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
            strike_map[strike] = {
                "strike": strike,
                "future_price": strike * multiplier + offset if multiplier != 1.0 else strike + offset,
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

    column_labels = [b.strftime("%H:%M") for b in reversed(buckets)]

    return {
        "underlying": underlying,
        "offset": offset,
        "multiplier": multiplier,
        "future_price": future_price,
        "columns": column_labels,
        "rows": rows_list,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
```

### Frontend

**`VolSurface.tsx` → repurposed as `OIDeltaHeatmap.tsx`**

```typescript
interface OIHeatmapRow {
  strike: number
  future_price: number
  side: 'call' | 'put'
  snapshots: Array<{
    oi_delta: number
    oi_delta_retail: number
    oi_delta_block: number
  } | null>
}

interface OIHeatmapData {
  underlying: string
  offset: number
  future_price: number
  columns: string[]   // ["09:30", "10:00", ...]
  rows: OIHeatmapRow[]
  updated_at: string
}
```

**Canvas heatmap rendering:**

- Rows: sorted strikes (filtered to ATM ±10%)
- Columns: 5 time slots
- Cell color:
  - **Call (positive delta)**: green scale — `#00C853` (strong) → `#b9f6ca` (weak)
  - **Put (negative delta)**: red scale — `#FF1744` (strong) → `#ffcdd2` (weak)
  - **Zero/near-zero**: dark neutral `#1e293b`
- Cell intensity: proportional to `|oi_delta|` / max_abs_delta
- Cell label: show `oi_delta` value if cell width > 40px, otherwise show only color
- Row header (left column): show both `strike` and `future_price` separated by `/`
  - e.g. `5350 / 5381` (put side) or `5400 / 5431` (call side)
- Column headers: time labels `09:30 10:00 10:30 11:00 11:30`
- Tooltip on hover: show strike, future_price, oi_delta, retail, block

**Styling**: match existing sidebar card styling (dark theme, monospace font)

### Data Flow

```
/api/oi/heatmap/{underlying} → VolSurface (now OIDeltaHeatmap)
  └── Canvas renders heatmap with 5 time columns + strikes rows
```

### Component Replacement

- `VolSurface.tsx` is renamed/repurposed as OI Delta Heatmap
- In `App.tsx`, `<VolSurface>` stays as is — the component is simply re-purposed
- GreeksPanel keeps its own OI Buildup table (top 3 + top 3) — separate view

### Edge Cases

- **No data**: show "No OI data available" message in the card
- **Fewer than 5 snapshots**: show whatever is available
- **Missing snapshot for a strike/time**: show null cell (dark/empty)
- **Market closed**: show last available session data with "Stale" badge
