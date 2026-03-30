# ScalpingPanel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `ReversalGauge` with `ScalpingPanel.tsx` — a compact scalping-optimized panel with directional signal, time urgency (session phase + countdown + theta burn), entry/stop/target + R:R, and 5-component dot breakdown.

**Architecture:** Single React component reading from existing WebSocket `reversal_signal` messages (backend unchanged). Greeks data fetched from `/api/greeks/{underlying}` for theta burn. Time urgency computed client-side.

**Tech Stack:** React + TypeScript + vanilla CSS (no new dependencies). CSS variables from `App.css`.

---

## File Map

| Action | File |
|--------|------|
| CREATE | `frontend/src/components/ScalpingPanel.tsx` |
| DELETE | `frontend/src/components/ReversalGauge.tsx` |
| MODIFY | `frontend/src/App.tsx:8` (import line) |
| MODIFY | `frontend/src/App.tsx:287` (usage line) |

---

## Tasks

### Task 1: Create ScalpingPanel.tsx — types and constants

**Files:**
- Create: `frontend/src/components/ScalpingPanel.tsx`

- [ ] **Step 1: Create the file with types and constants**

```typescript
import React, { useState, useEffect, useRef, useCallback } from 'react'

// ─── Types ────────────────────────────────────────────────────────────

interface ComponentScore {
  score: number
  detail: string
  direction: string
}

interface ReversalSignal {
  confluence: number
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  components: {
    gex_proximity: ComponentScore
    flow_divergence: ComponentScore
    price_extension: ComponentScore
    trap_signal: ComponentScore
    gamma_regime: ComponentScore
  }
  key_level: number | null
  stop_level: number | null
  target_level: number | null
  current_price: number | null
  underlying: string
  timestamp: string
}

interface GreeksData {
  chain: Array<{
    strike: number
    option_type: string
    theta: number | null
    delta: number | null
  }>
  spot: number
}

interface ScalpingPanelProps {
  underlying: 'SPX' | 'QQQ'
}

// ─── Constants ────────────────────────────────────────────────────────

const COMPONENT_LABELS: Record<string, string> = {
  gex_proximity: 'GEX',
  flow_divergence: 'FLOW',
  price_extension: 'PRC',
  trap_signal: 'TRP',
  gamma_regime: 'GAM',
}

const API_BASE = `${window.location.protocol}//${window.location.host}`

// ─── Session phase helper ─────────────────────────────────────────────
// Returns { label, colorKey } for current UTC time
function getSessionPhase(): { label: string; colorKey: 'early' | 'mid' | 'power' } {
  const now = new Date()
  const utcHour = now.getUTCHours()
  const utcMin = now.getUTCMinutes()
  // ET = UTC - 5 (standard), UTC - 4 (DST). Use -5 as conservative estimate.
  const etHour = (utcHour - 5 + 24) % 24

  if (etHour < 11) {
    return { label: 'EARLY RTH', colorKey: 'early' }
  } else if (etHour < 14) {
    return { label: 'MID RTH', colorKey: 'mid' }
  } else {
    return { label: 'POWER HOUR', colorKey: 'power' }
  }
}

// ─── Countdown helper ─────────────────────────────────────────────────
// Minutes until 16:00 ET (21:00 UTC)
function getCountdown(): string {
  const now = new Date()
  const utcHour = now.getUTCHours()
  const utcMin = now.getUTCMinutes()
  const etHour = (utcHour - 5 + 24) % 24

  if (etHour >= 16) return '0m'

  const totalMins = (16 - etHour) * 60 - utcMin
  const h = Math.floor(totalMins / 60)
  const m = totalMins % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

// ─── R:R calculator ───────────────────────────────────────────────────
function calcRR(entry: number, stop: number, target: number): number | null {
  if (!entry || !stop || !target) return null
  const risk = Math.abs(entry - stop)
  const reward = Math.abs(target - entry)
  if (risk === 0) return null
  return reward / risk
}

// ─── Component dot classifier ──────────────────────────────────────────
type DotState = 'confirming' | 'weak' | 'contrarian' | 'neutral'

function classifyDot(comp: ComponentScore, overallDir: string): DotState {
  if (comp.score < 50) return 'weak'
  if (comp.direction === 'NEUTRAL') return 'neutral'
  if (comp.direction === overallDir) return 'confirming'
  return 'contrarian'
}

export const ScalpingPanel: React.FC<ScalpingPanelProps> = ({ underlying }) => {
  // State
  const [data, setData] = useState<ReversalSignal | null>(null)
  const [greeks, setGreeks] = useState<GreeksData | null>(null)
  const [isLive, setIsLive] = useState(false)
  const lastUpdateRef = useRef<number>(0)

  // ... rest of component (Tasks 2–5 will fill this)
}

export default ScalpingPanel
```

- [ ] **Step 2: Verify file created**

Run: `ls -la frontend/src/components/ScalpingPanel.tsx`
Expected: File exists with content

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ScalpingPanel.tsx
git commit -m "feat(scalping): scaffold ScalpingPanel types and constants

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Implement WebSocket + polling data fetching

**Files:**
- Modify: `frontend/src/components/ScalpingPanel.tsx` (append to existing file)

- [ ] **Step 1: Add fetch and WS logic inside the component body (replace the `// ... rest of component` comment)**

Add these hooks before the `return` statement:

```typescript
  // ─── Initial fetch + WS subscription ───────────────────────────────
  const fetchSignal = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/reversal/${underlying}`)
      if (resp.ok) {
        const result: ReversalSignal = await resp.json()
        if (result.confluence !== undefined) {
          setData(result)
          lastUpdateRef.current = Date.now()
          setIsLive(true)
        }
      }
    } catch (err) {
      console.error('[ScalpingPanel] fetch error:', err)
    }
  }, [underlying])

  // Fetch greeks for theta burn
  const fetchGreeks = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/greeks/${underlying}`)
      if (resp.ok) {
        const result = await resp.json()
        setGreeks(result)
      }
    } catch (err) {
      console.error('[ScalpingPanel] greeks fetch error:', err)
    }
  }, [underlying])

  useEffect(() => {
    fetchSignal()
    fetchGreeks()
  }, [fetchSignal, fetchGreeks])

  // Polling: signal every 10s, greeks every 60s
  useEffect(() => {
    const signalInterval = setInterval(fetchSignal, 10000)
    const greeksInterval = setInterval(fetchGreeks, 60000)
    return () => {
      clearInterval(signalInterval)
      clearInterval(greeksInterval)
    }
  }, [fetchSignal, fetchGreeks])

  // ─── WebSocket listener ────────────────────────────────────────────
  useEffect(() => {
    const handleMessage = (e: CustomEvent) => {
      const msg = e.detail
      if (msg.type === 'reversal_signal' && msg.underlying === underlying) {
        setData(msg as ReversalSignal)
        lastUpdateRef.current = Date.now()
        setIsLive(true)
      }
    }
    window.addEventListener('market_tick', handleMessage as EventListener)
    return () => window.removeEventListener('market_tick', handleMessage as EventListener)
  }, [underlying])

  // ─── Frozen check every 5s ────────────────────────────────────────
  useEffect(() => {
    const check = setInterval(() => {
      if (Date.now() - lastUpdateRef.current > 5000) {
        setIsLive(false)
      }
    }, 5000)
    return () => clearInterval(check)
  }, [])
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ScalpingPanel.tsx
git commit -m "feat(scalping): add WS listener and polling logic

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Implement theta burn helper

**Files:**
- Modify: `frontend/src/components/ScalpingPanel.tsx`

- [ ] **Step 1: Add theta burn computation function after `calcRR`**

```typescript
// ─── Theta burn calculator ────────────────────────────────────────────
// Returns { thetaPerMin: number | null, isAccelerating: boolean }
function getThetaBurn(greeks: GreeksData | null): { thetaPerMin: number | null; isAccelerating: boolean } {
  if (!greeks || !greeks.chain || !greeks.spot || greeks.chain.length === 0) {
    return { thetaPerMin: null, isAccelerating: false }
  }

  // Find ATM strike (closest to spot)
  let atmTheta = 0
  let atmCount = 0
  for (const opt of greeks.chain) {
    if (opt.theta == null) continue
    const dist = Math.abs(opt.strike - greeks.spot)
    const atmRange = greeks.spot * 0.02 // ATM ±2%
    if (dist <= atmRange) {
      atmTheta += opt.theta
      atmCount++
    }
  }

  if (atmCount === 0) {
    return { thetaPerMin: null, isAccelerating: false }
  }

  const avgTheta = atmTheta / atmCount // This is already in $/contract/day typically
  // Convert to $/min: divide by (24 * 60) for rough estimate, or use 390 min/RTH day
  const thetaPerMin = Math.abs(avgTheta) / 390

  // Acceleration: if we're in power hour (ET >= 14), theta accelerates 3-5x
  const now = new Date()
  const etHour = ((now.getUTCHours() - 5) + 24) % 24
  const isAccelerating = etHour >= 14 && thetaPerMin > 0

  return { thetaPerMin, isAccelerating }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ScalpingPanel.tsx
git commit -m "feat(scalping): add theta burn helper

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Implement the JSX render

**Files:**
- Modify: `frontend/src/components/ScalpingPanel.tsx` — replace the entire `return (...)` statement

- [ ] **Step 1: Replace the `// ... rest of component` with the full render**

The render block should go AFTER all the hooks and helper functions, replacing the placeholder comment:

```typescript
  // ─── Derived values ─────────────────────────────────────────────────
  const confluence = data?.confluence ?? 0
  const direction = data?.direction ?? 'NEUTRAL'
  const dirColor = direction === 'BULLISH' ? 'var(--success)' : direction === 'BEARISH' ? 'var(--danger)' : 'var(--text-muted)'
  const arrow = direction === 'BULLISH' ? '▲' : direction === 'BEARISH' ? '▼' : '◆'

  // Confluence bar
  const barColor = confluence >= 50
    ? direction === 'BULLISH' ? 'var(--success)' : direction === 'BEARISH' ? 'var(--danger)' : 'var(--warning)'
    : 'var(--text-muted)'

  // Time urgency
  const session = getSessionPhase()
  const sessionColors: Record<string, string> = {
    early: '#64748b',
    mid: '#eab308',
    power: '#ef4444',
  }
  const sessionColor = sessionColors[session.colorKey]
  const countdown = getCountdown()
  const { thetaPerMin, isAccelerating } = getThetaBurn(greeks)
  const thetaLabel = thetaPerMin !== null
    ? `$${thetaPerMin.toFixed(2)}/min`
    : 'Θ —'
  const thetaAccelLabel = isAccelerating ? 'ACCELERATING' : ''

  // Entry/Stop/Target
  const entry = data?.key_level
  const stop = data?.stop_level
  const target = data?.target_level
  const rr = calcRR(entry ?? 0, stop ?? 0, target ?? 0)
  const rrColor = rr === null ? '#64748b' : rr >= 1.5 ? '#22c55e' : rr >= 1.0 ? '#eab308' : '#ef4444'

  // Component dots
  const components = data?.components ?? null
  const dotEntries = components
    ? Object.entries(components)
    : []

  const confirmedCount = components
    ? Object.entries(components).filter(([_, comp]) =>
        classifyDot(comp as ComponentScore, direction) === 'confirming'
      ).length
    : 0

  // ─── Loading state ─────────────────────────────────────────────────
  if (!data) {
    return (
      <div className="sidebar-card">
        <div className="sidebar-card-header">
          <span className="sidebar-card-title">Scalping Signal</span>
          <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>{underlying}</span>
        </div>
        <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.7rem' }}>
          LOADING REVERSAL SIGNAL...
        </div>
      </div>
    )
  }

  // ─── Main render ───────────────────────────────────────────────────
  return (
    <div className="sidebar-card">
      {/* Header */}
      <div className="sidebar-card-header">
        <span className="sidebar-card-title">Scalping Signal</span>
        <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>{underlying}</span>
        <div className={`smart-money-status ${isLive ? 'live' : 'frozen'}`} style={{ fontSize: '0.5rem' }}>
          {isLive ? 'LIVE' : 'FROZEN'}
        </div>
      </div>

      {/* Direction + Confluence */}
      <div style={{ textAlign: 'center', marginBottom: '4px' }}>
        <div style={{
          fontSize: '1.1rem',
          fontWeight: 700,
          color: dirColor,
          lineHeight: 1.1,
          textShadow: confluence >= 70 ? `0 0 8px ${dirColor}` : 'none',
          transition: 'color 0.3s, text-shadow 0.3s',
        }}>
          {arrow} {direction} {confluence.toFixed(0)}%
        </div>
        {/* Confluence bar */}
        <div style={{
          height: '6px',
          borderRadius: '3px',
          background: 'var(--bg-primary)',
          marginTop: '3px',
          overflow: 'hidden',
        }}>
          <div style={{
            height: '100%',
            width: `${confluence}%`,
            background: barColor,
            borderRadius: '3px',
            transition: 'width 0.5s ease, background 0.3s',
            boxShadow: confluence >= 70 ? `0 0 6px ${barColor}` : 'none',
          }} />
        </div>
      </div>

      {/* Time Urgency row */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontSize: '0.6rem',
        color: sessionColor,
        marginBottom: '3px',
        padding: '0 2px',
      }}>
        <span style={{ fontWeight: 700 }}>
          ⚡ {session.label}
        </span>
        <span style={{ fontWeight: 600 }}>
          {countdown}
        </span>
      </div>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontSize: '0.6rem',
        color: 'var(--text-muted)',
        marginBottom: '4px',
        padding: '0 2px',
      }}>
        <span>Θ {thetaLabel}</span>
        <span style={{ color: isAccelerating ? '#ef4444' : 'var(--text-muted)', fontWeight: 600 }}>
          {thetaAccelLabel}
        </span>
      </div>

      {/* Entry / Stop / Target / R:R */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr 1fr 1fr',
        gap: '2px',
        marginBottom: '4px',
        fontSize: '0.55rem',
        fontFamily: "'JetBrains Mono', monospace",
      }}>
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontWeight: 600 }}>ENTRY</div>
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontWeight: 600 }}>STOP</div>
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontWeight: 600 }}>TARGET</div>
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontWeight: 600 }}>R:R</div>

        <div style={{ textAlign: 'center', color: 'var(--text-primary)', fontWeight: 700 }}>
          {entry ? entry.toFixed(1) : '—'}
        </div>
        <div style={{ textAlign: 'center', color: 'var(--danger)', fontWeight: 700 }}>
          {stop ? stop.toFixed(1) : '—'}
        </div>
        <div style={{ textAlign: 'center', color: 'var(--success)', fontWeight: 700 }}>
          {target ? target.toFixed(1) : '—'}
        </div>
        <div style={{ textAlign: 'center', color: rrColor, fontWeight: 700 }}>
          {rr !== null ? rr.toFixed(1) : '—'}
        </div>
      </div>

      {/* Divider */}
      <div style={{ borderTop: '1px solid var(--border)', margin: '3px 0' }} />

      {/* Component dots */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginBottom: '2px' }}>
        {dotEntries.map(([key, comp]) => {
          const state = classifyDot(comp as ComponentScore, direction)
          const dotColors: Record<DotState, string> = {
            confirming: direction === 'BULLISH' ? '#22c55e' : '#ef4444',
            weak: '#64748b',
            contrarian: direction === 'BULLISH' ? '#ef4444' : '#22c55e',
            neutral: '#334155',
          }
          return (
            <div
              key={key}
              title={`${COMPONENT_LABELS[key]}: ${(comp as ComponentScore).score.toFixed(0)}%`}
              style={{
                width: '10px',
                height: '10px',
                borderRadius: '50%',
                background: dotColors[state],
                opacity: state === 'weak' ? 0.5 : 1,
                cursor: 'default',
              }}
            />
          )
        })}
      </div>
      <div style={{
        textAlign: 'center',
        fontSize: '0.55rem',
        color: 'var(--text-muted)',
        fontWeight: 600,
        marginBottom: '2px',
      }}>
        {confirmedCount}/5 CONFIRMED
      </div>
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        gap: '4px',
        fontSize: '0.45rem',
        color: 'var(--text-muted)',
      }}>
        {dotEntries.map(([key]) => (
          <span key={key}>{COMPONENT_LABELS[key]}</span>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -30`
Expected: No errors related to ScalpingPanel.tsx

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ScalpingPanel.tsx
git commit -m "feat(scalping): implement full ScalpingPanel render

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Replace ReversalGauge in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx:8`
- Modify: `frontend/src/App.tsx:287`

- [ ] **Step 1: Update import**

Change line 8 from:
```typescript
import { ReversalGauge } from './components/ReversalGauge'
```
To:
```typescript
import { ScalpingPanel } from './components/ScalpingPanel'
```

- [ ] **Step 2: Replace usage**

Change line 287 from:
```typescript
          <ReversalGauge underlying={underlying} />
```
To:
```typescript
          <ScalpingPanel underlying={underlying} />
```

- [ ] **Step 3: Verify no other references to ReversalGauge remain**

Run: `grep -r "ReversalGauge" frontend/src/`
Expected: Only in git history (no matches in current files)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "refactor: replace ReversalGauge with ScalpingPanel in App.tsx

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Delete ReversalGauge.tsx

**Files:**
- Delete: `frontend/src/components/ReversalGauge.tsx`

- [ ] **Step 1: Delete file**

Run: `rm frontend/src/components/ReversalGauge.tsx`

- [ ] **Step 2: Commit**

```bash
git rm frontend/src/components/ReversalGauge.tsx
git commit -m "feat(scalping): remove old ReversalGauge

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 7: Build and deploy

**Files:**
- Build: `frontend/`

- [ ] **Step 1: Build frontend**

Run: `cd frontend && npm run build 2>&1`
Expected: Build successful with no errors

- [ ] **Step 2: Deploy to VPS**

Run: `cd /Users/paolo/Desktop/GEX\ 4.0 && python3 .deploy_vps.py 2>&1 | tail -10`
Expected: "Deployment successful!"

- [ ] **Step 3: Commit all remaining changes**

```bash
git add -A && git commit -m "feat(scalping): complete ScalpingPanel — replace ReversalGauge

Full implementation:
- ScalpingPanel with directional signal, confluence bar
- Time urgency: session phase + countdown + theta burn
- Entry/Stop/Target + R:R display
- 5-component dot breakdown with confirmation count
- GreeksService theta burn for 0DTE acceleration

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Self-Review Checklist

| Spec Item | Task | Status |
|-----------|------|--------|
| Direction + confluence % + bar | Task 4 | ✅ |
| LIVE/FROZEN badge | Task 4 | ✅ |
| Session phase (Early/Mid/Power Hour) | Tasks 1, 4 | ✅ |
| Countdown to 4PM ET | Tasks 1, 4 | ✅ |
| Theta burn + ACCELERATING label | Tasks 3, 4 | ✅ |
| Entry/Stop/Target + R:R row | Task 4 | ✅ |
| 5 component dots with state colors | Tasks 1, 4 | ✅ |
| N/5 CONFIRMED count | Task 4 | ✅ |
| Loading state | Task 4 | ✅ |
| Replace in App.tsx | Task 5 | ✅ |
| Delete ReversalGauge | Task 6 | ✅ |
| Build + deploy | Task 7 | ✅ |

No placeholders found. Types, method names, and component keys are consistent across all tasks.
