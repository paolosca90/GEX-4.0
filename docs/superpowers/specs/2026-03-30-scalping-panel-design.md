# ScalpingPanel Design — Replacement for ReversalGauge

## Overview

Replace `ReversalGauge` with a compact, single-panel component (`ScalpingPanel.tsx`) that combines directional signal, time urgency, entry/stop/target levels, and 5-component confluence breakdown. Optimized for short-term mean reversion trades (5–15 min hold, 8–10 pt stops, 1.5:1 R:R target).

## Visual Design

```
┌─────────────────────────────────────┐
│  ▼ BEARISH  72%           [LIVE]  │  ← Arrow, direction, confluence %, status badge
│  ████████████░░░░░░░░             │  ← Full-width confluence bar (filled = score %)
├─────────────────────────────────────┤
│  ⚡ POWER HOUR  ·  1h 47m         │  ← Session phase + countdown to 0DTE expiry
│  Θ -$X/min  ·  ACCELERATING       │  ← Theta burn rate + acceleration indicator
├─────────────────────────────────────┤
│  ENTRY    STOP    TARGET    R:R   │
│  5818    5825    5802      2.3   │  ← Monospace, color-coded R:R
├─────────────────────────────────────┤
│  ● ● ● ● ○   4/5 CONFIRMED        │  ← 5 dots + component count
│  GEX FLOW PRC  TRP  GAM          │  ← Component labels (abbreviated)
└─────────────────────────────────────┘
```

### Color Palette

| Element | Bullish | Bearish | Neutral |
|---------|---------|---------|---------|
| Direction text + bar | `#22c55e` (green) | `#ef4444` (red) | `#64748b` (gray) |
| R:R ≥ 1.5 | `#22c55e` | | |
| R:R 1.0–1.5 | `#eab308` (yellow) | | |
| R:R < 1.0 | `#ef4444` | | |
| Session: Early RTH | `#64748b` | | |
| Session: Mid RTH | `#eab308` | | |
| Session: Power Hour | `#ef4444` | | |
| Live indicator | `#22c55e` (pulsing) | | |
| Frozen indicator | `#ef4444` | | |
| Component dot: confirming | filled `#22c55e` or `#ef4444` | | |
| Component dot: weak | filled `#64748b` at 50% opacity | | |
| Component dot: contrarian | filled `#ef4444` (bearish) or `#22c55e` (bullish) | | |

### Component Abbreviations

| Key | Full Name |
|-----|-----------|
| GEX | GEX Proximity |
| FLOW | Flow Divergence |
| PRC | Price Extension |
| TRP | Trap Signal |
| GAM | Gamma Regime |

## Behaviors

### Live / Frozen Detection
- Track `lastUpdateRef` (timestamp of last WS message)
- If > 5s since last update → `[FROZEN]` badge in red
- Else → `[LIVE]` badge in green with CSS pulse animation

### Confluence Bar
- Width = `confluence %`
- Color = bullish/bearish based on direction
- Transition: 0.5s ease width, 0.3s color

### Time Urgency (3-in-1 row)

**Session Phase** (color-coded):
- `EARLY RTH` — 09:30–11:00 ET (14:30–16:00 UTC), gray
- `MID RTH` — 11:00–14:00 ET (16:00–19:00 UTC), yellow
- `POWER HOUR` — 14:00–16:00 ET (19:00–21:00 UTC), red

**Countdown**: minutes remaining until 16:00 ET (4PM market close / 0DTE expiry). Format: `1h 47m` or `47m` if < 1h.

**Theta Burn** (shown on same row): Estimated theta decay in $/min at ATM. Computed client-side from GreeksService data or from `theta` field in greeks chain if available. Label: `ACCELERATING` if > 2x avg, `NORMAL` otherwise.

### Entry / Stop / Target Row

| Field | Source | Color |
|-------|--------|-------|
| ENTRY | `key_level` from reversal_signal | white |
| STOP | `stop_level` from reversal_signal | red |
| TARGET | `target_level` from reversal_signal | green |
| R:R | `abs(entry - stop) / abs(target - entry)` | green/yellow/red |

All values in future price points (e.g., US500-F price scale).

### Component Dots

- 5 dots, one per component
- A dot is **confirming** if its direction matches the overall signal direction
- A dot is **weak** if score < 50
- A dot is **contrarian** if its direction opposes the overall signal direction
- Count shown as `N/5 CONFIRMED`

### Loading State
While fetching or no data:
```
┌─────────────────────────────────────┐
│  LOADING REVERSAL SIGNAL...        │
└─────────────────────────────────────┘
```

## Technical

### Props

```typescript
interface ScalpingPanelProps {
  underlying: 'SPX' | 'QQQ'
}
```

### Data Source

WebSocket message type `reversal_signal` (already broadcast by backend every 1s):

```typescript
interface ReversalSignal {
  confluence: number         // 0–100
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  components: {
    gex_proximity:    { score: number, direction: string }
    flow_divergence:  { score: number, direction: string }
    price_extension:  { score: number, direction: string }
    trap_signal:      { score: number, direction: string }
    gamma_regime:     { score: number, direction: string }
  }
  key_level: number | null
  stop_level: number | null
  target_level: number | null
  current_price: number | null
  underlying: string
  timestamp: string
}
```

### State

- `data: ReversalSignal | null` — current signal from WS
- `lastUpdate: number` — timestamp of last WS message (for frozen check)

### Initial Fetch + Polling Fallback

Same pattern as `ReversalGauge`:
1. On mount: fetch `/api/reversal/{underlying}`
2. Start polling interval: 10s
3. Listen for WS `reversal_signal` events
4. Frozen check every 5s

### Greeks Data (for Theta)

Fetch `/api/greeks/{underlying}` every 60s. Extract ATM strike theta (average of ATM call and put theta). Fall back to static label if unavailable.

## File Change

- **DELETE** `frontend/src/components/ReversalGauge.tsx`
- **CREATE** `frontend/src/components/ScalpingPanel.tsx`
- **MODIFY** `frontend/src/App.tsx` — replace `ReversalGauge` import and usage with `ScalpingPanel`

## Metrics

- **Confluence bar** width: 100% of panel width, height 6px
- **R:R** display: 1 decimal place
- **Countdown**: updates every minute (no visible "flicker")
- **Dots**: 10px diameter, 4px gap, centered with labels below
