# Skew Gauge + Zone Overlay — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere SkewGauge nel sidebar e Zone Overlay sul grafico per rendere lo skew glanceable per scalping.

**Architecture:** SkewGauge legge da `/api/volatility/surface` e calcola skew medio OTM. LightweightChart.tsx estende il canvas overlay esistente per disegnare zone skew > 15%.

**Tech Stack:** React + Canvas (frontend)

---

## File Map

```
frontend/src/components/
    SkewGauge.tsx         — create: skew gauge component
frontend/src/components/
    LightweightChart.tsx  — modify: add zone overlay
frontend/src/App.tsx       — modify: add SkewGauge import
```

---

## Task 1: Create `SkewGauge.tsx`

**Files:**
- Create: `frontend/src/components/SkewGauge.tsx`

- [ ] **Step 1: Create the component**

```tsx
import React, { useState, useEffect, useCallback } from 'react';

interface StrikeData {
  strike: number;
  iv: number;
  call_iv: number;
  put_iv: number;
  skew: number;
  delta: number;
  gamma: number;
}

interface ExpirySurface {
  expiration: string;
  days_to_expiry: number;
  strikes: StrikeData[];
}

interface SkewGaugeProps {
  underlying: string;
}

const API_BASE = `${window.location.protocol}//${window.location.host}`;
const SKEW_THRESHOLD = 0.15; // 15%

export const SkewGauge: React.FC<SkewGaugeProps> = ({ underlying }) => {
  const [skewValue, setSkewValue] = useState<number | null>(null);
  const [skewDirection, setSkewDirection] = useState<'put' | 'call' | 'neutral' | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchSkew = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/volatility/surface?underlying=${underlying}`);
      const data = await resp.json();
      if (data.error || !data.surface?.length) {
        setLoading(false);
        return;
      }

      // Use 0DTE surface (first expiration)
      const strikes = data.surface[0]?.strikes || [];
      const spot = data.spot_price || 0;

      if (!spot || !strikes.length) {
        setLoading(false);
        return;
      }

      // Filter OTM strikes within ±2% of spot
      const lower = spot * 0.98;
      const upper = spot * 1.02;
      const otmStrikes = strikes.filter(s =>
        s.strike >= lower && s.strike <= upper &&
        s.call_iv != null && s.put_iv != null && s.gamma != null
      );

      if (!otmStrikes.length) {
        setLoading(false);
        return;
      }

      // Weighted average skew (weighted by gamma)
      let totalGamma = 0;
      let weightedSkew = 0;
      for (const s of otmStrikes) {
        const gamma = Math.abs(s.gamma || 0);
        totalGamma += gamma;
        weightedSkew += s.skew * gamma;
      }

      const avgSkew = totalGamma > 0 ? weightedSkew / totalGamma : 0;
      setSkewValue(avgSkew);

      if (avgSkew > SKEW_THRESHOLD) {
        setSkewDirection('put');
      } else if (avgSkew < -SKEW_THRESHOLD) {
        setSkewDirection('call');
      } else {
        setSkewDirection('neutral');
      }

      setLoading(false);
    } catch (e) {
      setLoading(false);
    }
  }, [underlying]);

  useEffect(() => {
    fetchSkew();
    const interval = setInterval(fetchSkew, 120000); // 2 min
    return () => clearInterval(interval);
  }, [fetchSkew]);

  if (loading) {
    return (
      <div className="skew-gauge" style={{
        padding: '0.5rem',
        background: 'rgba(15,23,42,0.8)',
        borderRadius: 6,
        marginTop: '0.25rem',
      }}>
        <div style={{ fontSize: '0.65rem', color: '#64748b', marginBottom: 4 }}>SKEW GAUGE</div>
        <div style={{ color: '#94a3b8', fontSize: '0.7rem' }}>Loading...</div>
      </div>
    );
  }

  const skewColor = skewDirection === 'put' ? '#ef4444' : skewDirection === 'call' ? '#3b82f6' : '#64748b';
  const skewSign = skewValue !== null ? (skewValue >= 0 ? '+' : '') : '';
  const badge = skewDirection === 'put' ? '▲ HIGH RISK' : skewDirection === 'call' ? '▼ HIGH RISK' : '— NEUTRAL';

  return (
    <div className="skew-gauge" style={{
      padding: '0.5rem',
      background: 'rgba(15,23,42,0.8)',
      borderRadius: 6,
      marginTop: '0.25rem',
      border: `1px solid ${skewDirection !== 'neutral' ? skewColor : '#334155'}`,
    }}>
      <div style={{ fontSize: '0.65rem', color: '#64748b', marginBottom: 4 }}>SKEW GAUGE</div>
      {skewValue !== null ? (
        <>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, color: skewColor, fontFamily: 'monospace' }}>
            {skewSign}{(skewValue * 100).toFixed(1)}%
          </div>
          <div style={{
            fontSize: '0.7rem',
            fontWeight: 600,
            color: skewColor,
            marginTop: 2,
          }}>
            {badge}
          </div>
          <div style={{ fontSize: '0.6rem', color: '#475569', marginTop: 4 }}>
            Skew threshold: {(SKEW_THRESHOLD * 100).toFixed(0)}%
          </div>
        </>
      ) : (
        <div style={{ color: '#64748b', fontSize: '0.7rem' }}>No data</div>
      )}
    </div>
  );
};
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/paolo/Desktop/GEX\ 4.0/frontend && npm run build 2>&1 | tail -5
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SkewGauge.tsx && git commit -m "feat: add SkewGauge component"
```

---

## Task 2: Add SkewGauge to App.tsx sidebar

**Files:**
- Modify: `frontend/src/App.tsx` (add import + place in sidebar)

- [ ] **Step 1: Add import and place component**

Add import after VolSurface import:
```tsx
import { SkewGauge } from './components/SkewGauge';
```

In the sidebar panel, add SkewGauge under VolSurface (or above GreeksPanel):
```tsx
<VolSurface underlying={underlying} />
<SkewGauge underlying={underlying} />
<GreeksPanel underlying={underlying} />
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/paolo/Desktop/GEX\ 4.0/frontend && npm run build 2>&1 | tail -5
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx && git commit -m "feat: integrate SkewGauge in sidebar"
```

---

## Task 3: Zone Overlay in LightweightChart.tsx

**Files:**
- Modify: `frontend/src/components/LightweightChart.tsx` (add skew zone drawing)

- [ ] **Step 1: Add skew zones to the canvas overlay**

In the `drawOverlay` function in LightweightChart.tsx, add a new `drawSkewZones()` function call after the GEX levels drawing.

First, add a new state variable to hold skew zone data. Add near the other state declarations:
```tsx
const [skewZones, setSkewZones] = useState<Array<{strike: number; skew: number; type: 'put' | 'call'}>>([]);
```

Add a `fetchSkewZones` function:
```tsx
const fetchSkewZones = useCallback(async (und: string) => {
  try {
    const resp = await fetch(`${API_BASE}/api/volatility/surface?underlying=${und}`);
    const data = await resp.json();
    if (!data.surface?.length) return;

    const strikes = data.surface[0]?.strikes || [];
    const spot = data.spot_price || 0;
    if (!spot) return;

    // Find strikes with |skew| > 15% in 0DTE
    const zones: Array<{strike: number; skew: number; type: 'put' | 'call'}> = [];
    for (const s of strikes) {
      if (s.skew == null || s.call_iv == null || s.put_iv == null) continue;
      if (Math.abs(s.skew) > SKEW_THRESHOLD) {
        zones.push({
          strike: s.strike,
          skew: s.skew,
          type: s.skew > 0 ? 'put' : 'call',
        });
      }
    }

    // Sort: puts by skew desc, calls by skew asc (most extreme first)
    zones.sort((a, b) => {
      if (a.type === 'put' && b.type === 'put') return b.skew - a.skew;
      if (a.type === 'call' && b.type === 'call') return a.skew - b.skew;
      return 0;
    });

    // Take top 3 per side
    const puts = zones.filter(z => z.type === 'put').slice(0, 3);
    const calls = zones.filter(z => z.type === 'call').slice(0, 3);
    setSkewZones([...puts, ...calls]);
  } catch (e) {
    // silently fail
  }
}, []);
```

Add a useEffect to fetch skew zones and to listen for underlying changes. Add after the existing useEffect blocks:
```tsx
useEffect(() => {
  if (underlying) {
    fetchSkewZones(underlying);
    const interval = setInterval(() => fetchSkewZones(underlying), 120000);
    return () => clearInterval(interval);
  }
}, [underlying, fetchSkewZones]);
```

Now add the `drawSkewZones` function in the drawOverlay function. Add it after the GEX levels drawing section:

```tsx
// ── Skew Zones ──────────────────────────────────────────────────────────────
const drawSkewZones = () => {
  if (!seriesRef.current || !skewZones.length || !keyLevels) return;

  const maxY = chartRef.current?.timeScale().getVisibleLogicalRange();
  if (!maxY) return;

  const minPrice = seriesRef.current.getPriceFromLogical(maxY.lower);
  const maxPrice = seriesRef.current.getPriceFromLogical(maxY.upper);

  const SKEW_THRESHOLD = 0.15;

  for (const zone of skewZones) {
    // Translate strike to future price
    const strike = zone.strike;
    const multiplier = keyLevels?.zgl?.price && keyLevels?.call_wall?.price
      ? keyLevels.call_wall.price / (keyLevels.zgl.price || 1)
      : 1;
    const offset = keyLevels?.zgl?.price ? keyLevels.zgl.price - (keyLevels.zgl.price / multiplier) : 0;
    const futurePrice = strike * multiplier + offset;

    if (futurePrice < minPrice || futurePrice > maxPrice) continue;

    const y = seriesRef.current.priceToCoordinate(futurePrice);
    if (y === null) continue;

    const isPut = zone.type === 'put';
    const color = isPut ? '#ef4444' : '#3b82f6';
    const skewPct = (zone.skew * 100).toFixed(0);
    const prefix = isPut ? 'PUT' : 'CALL';

    // Draw dashed line
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.setLineDash([6, 4]);
    ctx.globalAlpha = 0.7;
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;

    // Label
    const labelText = `${prefix} ${strike.toFixed(0)} ${skewPct}%`;
    ctx.font = '9px monospace';
    const tm = ctx.measureText(labelText);
    ctx.fillStyle = 'rgba(10,14,23,0.85)';
    ctx.fillRect(4, y - 10, tm.width + 6, 13);
    ctx.fillStyle = color;
    ctx.fillText(labelText, 6, y);
  }
};
```

Then call `drawSkewZones()` inside the drawOverlay function, after the flow concentration drawing.

**Step 2: Verify build**

```bash
cd /Users/paolo/Desktop/GEX\ 4.0/frontend && npm run build 2>&1 | tail -5
```

**Step 3: Commit**

```bash
git add frontend/src/components/LightweightChart.tsx && git commit -m "feat: add skew zone overlay on chart"
```

---

## Task 4: Deploy to VPS

- [ ] **Step 1: Full deploy**

```bash
python3 .deploy_vps.py
```

- [ ] **Step 2: Verify**

Navigate `http://137.220.63.222` and check:
1. SkewGauge appears in sidebar with value and badge
2. No build errors

---

## Spec Coverage

- [x] SkewGauge component with weighted avg skew OTM ±2% → Task 1
- [x] Badge: ▲ HIGH RISK / ▼ HIGH RISK / — NEUTRAL → Task 1
- [x] SkewGauge in sidebar under VolSurface → Task 2
- [x] Zone overlay on chart with up to 3 lines per side → Task 3
- [x] Dashed red lines for put skew > 15% → Task 3
- [x] Dashed blue lines for call skew < -15% → Task 3
- [x] Labels with strike and skew % → Task 3
- [x] Refresh every 2 minutes → Tasks 1 & 3
- [x] 15% threshold confirmed → all components
