# Volatility Surface Heatmap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere heatmap 2D della volatilità implicita (strikes × expirations 0DTE + 1DTE) nel sidebar panel per aiutare a individuare inversioni intraday.

**Architecture:** Il backend chiama Tradier chains per 0DTE e 1DTE in parallelo, estrae IV/delta/gamma per strike, restituisce surface al frontend che la renderizza come heatmap canvas-based.

**Tech Stack:** FastAPI + httpx (backend), React + Canvas (frontend)

---

## File Map

```
backend/greeks_service.py   — modify: aggiungere get_volatility_surface()
backend/main.py              — modify: aggiungere GET /api/volatility/surface
frontend/src/components/
    VolSurface.tsx           — create: heatmap canvas component
frontend/src/App.tsx        — modify: integrare VolSurface nel sidebar
```

---

## Task 1: Backend — `get_volatility_surface()` in greeks_service.py

**Files:**
- Modify: `backend/greeks_service.py` (aggiungere metodo alla classe GreeksService)

- [ ] **Step 1: Aggiungere metodo `get_volatility_surface()` alla classe GreeksService**

Inserire alla fine della classe `GreeksService` (dopo riga 263):

```python
async def get_volatility_surface(self, underlying: str, max_strikes: int = 20) -> dict:
    """
    Fetch volatility surface for 0DTE + 1DTE expirations.
    Returns strikes with IV, delta, gamma, call_iv, put_iv, skew per strike.
    """
    symbol = CHAIN_SYMBOLS.get(underlying, underlying)
    headers = {
        "Authorization": f"Bearer {TRADIER_API_KEY}",
        "Accept": "application/json",
    }

    # Step 1: get available expirations
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            exp_url = f"{TRADIER_EXPIRATIONS_URL}?symbol={symbol}&includeAllRoots=true"
            exp_resp = await client.get(exp_url, headers=headers)
            available_dates = []
            if exp_resp.status_code == 200:
                exp_data = exp_resp.json()
                raw_dates = exp_data.get("expirations", {}).get("date", [])
                if isinstance(raw_dates, list):
                    available_dates = raw_dates[:5]  # take first 5 expirations
    except Exception as e:
        logger.error(f"Expirations fetch error: {e}")
        return {"error": str(e), "surface": [], "underlying": underlying}

    # Step 2: fetch chains for up to 2 expirations in parallel
    async def fetch_single_expiry(exp: str):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                url = f"{TRADIER_CHAIN_URL}?symbol={symbol}&expiration={exp}&greeks=true"
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    opts = data.get("options", {}).get("option", [])
                    if opts:
                        return opts, exp
        except Exception as e:
            logger.error(f"Chain fetch error for {exp}: {e}")
        return [], exp

    # Only use first 2 expirations (0DTE + 1DTE)
    results = await asyncio.gather(*[fetch_single_expiry(exp) for exp in available_dates[:2]])

    surface = []
    for options, exp in results:
        if not options:
            continue

        strikes_map = {}
        for opt in options:
            strike = float(opt.get("strike", 0))
            if strike in strikes_map:
                continue
            greeks = opt.get("greeks") or {}
            option_type = opt.get("option_type")
            mid_iv = greeks.get("mid_iv") or 0.0

            strikes_map[strike] = {
                "strike": strike,
                "delta": greeks.get("delta"),
                "gamma": greeks.get("gamma"),
            }
            if option_type == "call":
                strikes_map[strike]["call_iv"] = mid_iv
            else:
                strikes_map[strike]["put_iv"] = mid_iv

        # Compute skew and ATM flag per strike
        sorted_strikes = sorted(strikes_map.keys())
        for strike, data in strikes_map.items():
            call_iv = data.get("call_iv", 0)
            put_iv = data.get("put_iv", 0)
            data["iv"] = (call_iv + put_iv) / 2 if call_iv and put_iv else (call_iv or put_iv or 0)
            data["skew"] = put_iv - call_iv if call_iv and put_iv else 0

        strikes_list = list(strikes_map.values())

        # Determine DTE
        try:
            exp_dt = datetime.strptime(exp, "%Y-%m-%d").date()
            today = datetime.now(timezone(timedelta(hours=-5))).date()
            dte = max(0, (exp_dt - today).days)
        except Exception:
            dte = 0

        surface.append({
            "expiration": exp,
            "days_to_expiry": dte,
            "strikes": strikes_list,
        })

    # Get spot price
    spot = await self._get_spot_from_quotes(symbol)
    if not spot:
        # Fallback to any available strike midpoint
        if surface and surface[0]["strikes"]:
            spot = surface[0]["strikes"][len(surface[0]["strikes"])//2]["strike"]

    return {
        "underlying": underlying,
        "spot_price": spot,
        "surface": surface,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
```

- [ ] **Step 2: Test locale del metodo**

Run: `cd backend && python3 -c "import asyncio; from greeks_service import GreeksService; s=GreeksService(); print(asyncio.run(s.get_volatility_surface('SPX')))"`
Expected: dict con "surface" contentente strikes con iv, skew, delta, gamma

- [ ] **Step 3: Commit**

```bash
git add backend/greeks_service.py
git commit -m "feat: add get_volatility_surface() for 0DTE+1DTE IV heatmap"
```

---

## Task 2: Backend — Endpoint `/api/volatility/surface`

**Files:**
- Modify: `backend/main.py` (aggiungere endpoint FastAPI)
- Test: `curl http://localhost:8000/api/volatility/surface?underlying=SPX`

- [ ] **Step 1: Aggiungere endpoint in main.py**

Trovare la sezione degli endpoint greeks in main.py e aggiungere dopo `get_greeks_summary`:

```python
@app.get("/api/volatility/surface")
async def get_volatility_surface(underlying: str = Query(..., description="Underlying: SPX or QQQ")):
    """
    Return volatility surface data for 0DTE + 1DTE.
    Includes IV, skew, delta, gamma per strike.
    """
    if not greeks_service:
        return {"error": "Service not available", "surface": []}
    try:
        data = await greeks_service.get_volatility_surface(underlying)
        return data
    except Exception as e:
        logger.error(f"Volatility surface error: {e}")
        return {"error": str(e), "surface": []}
```

- [ ] **Step 2: Verificare endpoint**

Run: `curl -s "http://localhost:8000/api/volatility/surface?underlying=SPX" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Surface exps: {[e[\"expiration\"] for e in d.get(\"surface\",[])]}'); print(f'Strikes in first exp: {len(d[\"surface\"][0][\"strikes\"]) if d.get(\"surface\") else 0}')"`

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add GET /api/volatility/surface endpoint"
```

---

## Task 3: Frontend — `VolSurface.tsx` Component

**Files:**
- Create: `frontend/src/components/VolSurface.tsx`

- [ ] **Step 1: Creare il componente VolSurface.tsx**

```tsx
import React, { useState, useEffect, useRef, useCallback } from 'react';

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

interface VolSurfaceProps {
  underlying: string;
}

const API_BASE = `${window.location.protocol}//${window.location.host}`;

const COLOR_SCALE: [number, string][] = [
  [0.10, '#1e40af'],  // <10% IV → deep blue
  [0.20, '#60a5fa'],  // 10-20% → light blue
  [0.30, '#22c55e'],  // 20-30% → green
  [0.40, '#eab308'],  // 30-40% → yellow
  [0.50, '#f97316'],  // 40-50% → orange
  [1.00, '#ef4444'],  // 50%+  → red
];

function ivToColor(iv: number): string {
  for (const [threshold, color] of COLOR_SCALE) {
    if (iv < threshold) return color;
  }
  return '#ef4444';
}

function interpolateColor(iv: number): string {
  // Linear interpolation between scale steps
  const stops: [number, [number, number, number]][] = [
    [0.10, [30, 64, 175]],
    [0.20, [96, 165, 250]],
    [0.30, [34, 197, 94]],
    [0.40, [234, 179, 8]],
    [0.50, [249, 115, 22]],
    [1.00, [239, 68, 68]],
  ];
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, [r0, g0, b0]] = stops[i];
    const [t1, [r1, g1, b1]] = stops[i + 1];
    if (iv >= t0 && iv < t1) {
      const ratio = (iv - t0) / (t1 - t0);
      const r = Math.round(r0 + (r1 - r0) * ratio);
      const g = Math.round(g0 + (g1 - g0) * ratio);
      const b = Math.round(b0 + (b1 - b0) * ratio);
      return `rgb(${r},${g},${b})`;
    }
  }
  return 'rgb(239,68,68)';
}

export const VolSurface: React.FC<VolSurfaceProps> = ({ underlying }) => {
  const [surface, setSurface] = useState<ExpirySurface[]>([]);
  const [spotPrice, setSpotPrice] = useState<number>(0);
  const [updatedAt, setUpdatedAt] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [hoveredCell, setHoveredCell] = useState<{expiry: string, strike: StrikeData, x: number, y: number} | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchSurface = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/volatility/surface?underlying=${underlying}`);
      const data = await resp.json();
      if (data.error) {
        setError(data.error);
        return;
      }
      setSurface(data.surface || []);
      setSpotPrice(data.spot_price || 0);
      setUpdatedAt(data.updated_at || '');
      setError('');
    } catch (e) {
      setError('Failed to fetch');
    }
  }, [underlying]);

  useEffect(() => {
    fetchSurface();
    const interval = setInterval(fetchSurface, 120000); // 2 min
    return () => clearInterval(interval);
  }, [fetchSurface]);

  // Draw heatmap on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || surface.length === 0) return;

    const strikes = surface[0]?.strikes || [];
    if (strikes.length === 0) return;

    const numExpirations = surface.length;
    const numStrikes = Math.min(strikes.length, 25); // cap at 25 for readability

    const CELL_WIDTH = Math.floor(container.clientWidth / numExpirations);
    const CELL_HEIGHT = 22;
    const HEADER_HEIGHT = 24;
    const canvasHeight = HEADER_HEIGHT + numStrikes * CELL_HEIGHT;

    canvas.width = container.clientWidth;
    canvas.height = canvasHeight;
    canvas.style.height = `${canvasHeight}px`;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw column headers
    ctx.font = 'bold 11px monospace';
    ctx.fillStyle = '#94a3b8';
    surface.forEach((exp, col) => {
      const label = exp.days_to_expiry === 0 ? '0DTE' : `${exp.days_to_expiry}DTE`;
      ctx.fillText(label, col * CELL_WIDTH + 4, HEADER_HEIGHT - 6);
    });

    // Bucket strikes: select evenly spaced strikes
    const bucketSize = Math.max(1, Math.floor(strikes.length / numStrikes));
    const bucketedStrikes = strikes.filter((_, i) => i % bucketSize === 0).slice(0, numStrikes);

    // Find ATM index
    const atmIdx = bucketedStrikes.findIndex(s => s.strike >= spotPrice);

    // Draw cells
    bucketedStrikes.forEach((strikeData, row) => {
      const isATM = Math.abs(strikeData.strike - spotPrice) < (spotPrice * 0.005);

      surface.forEach((exp, col) => {
        // Find matching strike in this expiration
        const expStrike = exp.strikes.find(s => s.strike === strikeData.strike);
        if (!expStrike) return;

        const x = col * CELL_WIDTH;
        const y = HEADER_HEIGHT + row * CELL_HEIGHT;

        // Background color from IV
        ctx.fillStyle = interpolateColor(expStrike.iv);
        ctx.fillRect(x + 1, y + 1, CELL_WIDTH - 2, CELL_HEIGHT - 2);

        // ATM highlight border
        if (isATM) {
          ctx.strokeStyle = '#fbbf24';
          ctx.lineWidth = 2;
          ctx.strokeRect(x + 1, y + 1, CELL_WIDTH - 2, CELL_HEIGHT - 2);
        }

        // Strike label on left
        if (col === 0) {
          ctx.fillStyle = '#e2e8f0';
          ctx.font = '9px monospace';
          ctx.fillText(`${strikeData.strike.toFixed(0)}`, 2, y + CELL_HEIGHT - 4);
        }

        // Skew indicator: small triangle if skew > 0.15
        if (Math.abs(expStrike.skew) > 0.15) {
          ctx.fillStyle = expStrike.skew > 0 ? '#ef4444' : '#3b82f6';
          ctx.font = '8px monospace';
          ctx.fillText(expStrike.skew > 0 ? '▲' : '▼', x + CELL_WIDTH - 12, y + CELL_HEIGHT - 4);
        }
      });
    });

    // Draw strike scale on right side
    ctx.fillStyle = '#475569';
    ctx.font = '9px monospace';
    bucketedStrikes.forEach((strikeData, row) => {
      const y = HEADER_HEIGHT + row * CELL_HEIGHT + CELL_HEIGHT - 4;
      // Nothing extra needed — left labels work
    });

  }, [surface, spotPrice]);

  if (error) {
    return (
      <div className="vol-surface-panel" style={{ padding: '0.5rem', color: '#ef4444', fontSize: '0.75rem' }}>
        Vol Surface: {error}
      </div>
    );
  }

  if (surface.length === 0) {
    return (
      <div className="vol-surface-panel" style={{ padding: '0.5rem', color: '#94a3b8', fontSize: '0.75rem' }}>
        Loading Vol Surface...
      </div>
    );
  }

  return (
    <div className="vol-surface-panel" style={{ padding: '0.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
        <span style={{ fontSize: '0.7rem', fontWeight: 600, color: '#e2e8f0' }}>VOL SURFACE</span>
        <span style={{ fontSize: '0.65rem', color: '#64748b' }}>
          {updatedAt ? `Updated ${new Date(updatedAt).toLocaleTimeString()}` : ''}
        </span>
      </div>
      <div ref={containerRef} style={{ position: 'relative', width: '100%', overflow: 'hidden' }}>
        <canvas
          ref={canvasRef}
          style={{ display: 'block', width: '100%' }}
          onMouseMove={(e) => {
            const canvas = canvasRef.current;
            if (!canvas) return;
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const col = Math.floor(x / (canvas.width / surface.length));
            const HEADER_HEIGHT = 24;
            const CELL_HEIGHT = 22;
            const row = Math.floor((y - HEADER_HEIGHT) / CELL_HEIGHT);
            const strikes = surface[0]?.strikes || [];
            const bucketSize = Math.max(1, Math.floor(strikes.length / Math.min(strikes.length, 25)));
            const bucketedStrikes = strikes.filter((_, i) => i % bucketSize === 0).slice(0, 25);
            if (col >= 0 && col < surface.length && row >= 0 && row < bucketedStrikes.length) {
              const exp = surface[col];
              const strike = bucketedStrikes[row];
              const expStrike = exp?.strikes?.find(s => s.strike === strike?.strike);
              if (expStrike) {
                setHoveredCell({ expiry: exp.expiration, strike: expStrike, x: e.clientX, y: e.clientY });
              }
            }
          }}
          onMouseLeave={() => setHoveredCell(null)}
        />
        {hoveredCell && (
          <div
            style={{
              position: 'fixed',
              left: hoveredCell.x + 12,
              top: hoveredCell.y - 60,
              background: 'rgba(15,23,42,0.95)',
              border: '1px solid #334155',
              borderRadius: 4,
              padding: '6px 10px',
              fontSize: '0.7rem',
              color: '#e2e8f0',
              pointerEvents: 'none',
              zIndex: 1000,
              minWidth: 140,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 3 }}>{hoveredCell.expiry}</div>
            <div>Strike: <b>{hoveredCell.strike.strike.toFixed(0)}</b></div>
            <div>IV: <b>{(hoveredCell.strike.iv * 100).toFixed(1)}%</b></div>
            <div>C IV: {(hoveredCell.strike.call_iv * 100).toFixed(1)}% | P IV: {(hoveredCell.strike.put_iv * 100).toFixed(1)}%</div>
            <div>Skew: <b style={{ color: hoveredCell.strike.skew > 0 ? '#ef4444' : '#3b82f6' }}>{(hoveredCell.strike.skew * 100).toFixed(1)}%</b></div>
            <div>Delta: {hoveredCell.strike.delta?.toFixed(3)} | Gamma: {hoveredCell.strike.gamma?.toFixed(4)}</div>
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.6rem', color: '#64748b' }}>IV:</span>
        {COLOR_SCALE.map(([t, c]) => (
          <span key={t} style={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: '0.6rem', color: '#64748b' }}>
            <span style={{ width: 8, height: 8, background: c, borderRadius: 1, display: 'inline-block' }} />
            {(t * 100).toFixed(0)}%
          </span>
        ))}
        <span style={{ fontSize: '0.6rem', color: '#64748b', marginLeft: 4 }}>| Skew ▲=Put {'>'}=Call</span>
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/VolSurface.tsx
git commit -m "feat: add VolSurface heatmap component"
```

---

## Task 4: Integrazione in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx` (aggiungere import e posizionare VolSurface)

- [ ] **Step 1: Aggiungere import e inserire nel sidebar panel**

In App.tsx, dopo l'import di ReversalGauge aggiungere:
```tsx
import { VolSurface } from './components/VolSurface';
```

Nel sidebar panel (sotto `</ReversalGauge>`), aggiungere:
```tsx
<VolSurface underlying={underlying} />
<GreeksPanel underlying={underlying} />
```

- [ ] **Step 2: Build e verificare**

Run: `cd frontend && npm run build`
Expected: build succeeds with no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: integrate VolSurface in sidebar panel"
```

---

## Task 5: Deploy to VPS

**Files:**
- Deploy: `backend/main.py`, `backend/greeks_service.py`, `frontend/dist/`

- [ ] **Step 1: Full deploy**

Run: `python3 .deploy_vps.py`

- [ ] **Step 2: Verificare endpoint**

Run: `curl -s "http://137.220.63.222/api/volatility/surface?underlying=SPX" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Expirations: {[e[\"expiration\"] for e in d[\"surface\"]]}')"`

- [ ] **Step 3: Verificare nel browser**

Navigate: `http://137.220.63.222` → verificare che la heatmap appaia nel sidebar panel sotto ReversalGauge

---

## Spec Coverage Check

- [x] Backend: `get_volatility_surface()` con 0DTE + 1DTE → Task 1
- [x] API endpoint `/api/volatility/surface` → Task 2
- [x] VolSurface.tsx canvas heatmap → Task 3
- [x] Integrazione in App.tsx sidebar → Task 4
- [x] Deploy to VPS → Task 5
- [x] Skew flag (▲/▼) quando skew > 0.15 per strike
- [x] Color scale IV da blu (low) a rosso (high)
- [x] Tooltip on-hover con dettagli strike
- [x] Refresh ogni 2 minuti
- [x] ATM highlight con bordo giallo

**Open question risolto**: bucket strikes — mostriamo fino a 25 strike evenly spaced (ogni ~25pt per SPX, ogni ~5pt per QQQ), raggruppati dall'alto verso il basso.
