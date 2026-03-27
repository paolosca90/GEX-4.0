# GEX Dashboard 4.0 — Institutional Upgrade MVP Design

**Data**: 2026-03-27
**Scope**: MVP in 2 giorni per trasformare la dashboard in prodotto di livello istituzionale
**Target**: SaaS commerciale per traders retail avanzati

---

## Obiettivo

Trasformare la GEX Dashboard da tool personale a prodotto commerciale SaaS di livello istituzionale, focalizzato su 0DTE scalping su ES/NQ. L'MVP aggiunge 4 macro-feature: Greeks + IV reali da ORATS, Alerts & Signals Engine, UI/UX overhaul con dark theme, e Dark Pool indicatori.

---

## Sezione 1: Greeks + IV Reali da ORATS

### Scoperta Chiave

Tradier fornisce gia' Greeks completi tramite ORATS con il parametro `greeks=true`. Non serve implementare Black-Scholes.

### Dati Disponibili da Tradier ORATS

Ogni option chain restituisce:
- **Greeks**: delta, gamma, theta, vega, rho, phi
- **IV**: bid_iv, mid_iv, ask_iv, smv_vol (ORATS model)
- **Open Interest**: aggiornato ogni ora
- **Pricing**: bid, ask, mid, last, underlying_price

### Endpoint Nuovi

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/api/greeks/{underlying}` | Chain Greeks ATM ±5% con IV |
| GET | `/api/greeks/summary/{underlying}` | Greeks aggregati per expiry (0DTE focus) |

### Dati Restituiti — `/api/greeks/{underlying}`

```json
{
  "underlying": "SPX",
  "spot": 5900.50,
  "timestamp": "2026-03-27T14:30:00Z",
  "chain": [
    {
      "strike": 5900,
      "option_type": "call",
      "expiry": "2026-03-27",
      "delta": 0.51,
      "gamma": 0.0089,
      "theta": -2.45,
      "vega": 0.32,
      "bid_iv": 0.185,
      "mid_iv": 0.190,
      "ask_iv": 0.195,
      "smv_vol": 0.188,
      "open_interest": 12450,
      "volume": 3200
    }
  ],
  "summary": {
    "total_gamma": 0.0234,
    "net_delta": -0.15,
    "avg_theta": -1.89,
    "call_iv_mean": 0.192,
    "put_iv_mean": 0.215,
    "skew": 0.023,
    "iv_rank": 45.2
  }
}
```

### Dati Restituiti — `/api/greeks/summary/{underlying}`

```json
{
  "underlying": "SPX",
  "spot": 5900.50,
  "updated_at": "2026-03-27T14:30:00Z",
  "regime": "long_gamma",
  "total_gex": 1.2e9,
  "net_delta_exposure": -850e6,
  "avg_theta_decay": -2.1,
  "iv_context": {
    "atm_iv": 0.190,
    "iv_rank_52w": 42,
    "iv_percentile_52w": 38,
    "skew_25delta": 0.023,
    "term_structure": "contango"
  },
  "greeks_by_expiry": [
    {
      "expiry": "2026-03-27",
      "dte": 0,
      "total_gamma": 0.0156,
      "net_delta": -0.08,
      "avg_theta": -3.2,
      "atm_iv": 0.195
    }
  ]
}
```

### Implementazione Backend

**File**: `backend/greeks_service.py` (nuovo)

Responsabilita':
1. Fetch Tradier option chain con `greeks=true` per SPX e QQQ
2. Parsing e aggregazione Greeks per strike e expiry
3. Calcolo metriche derivate: IV rank, skew, term structure
4. Cache in memoria con TTL 60 secondi (durante RTH)
5. Esposizione via `main.py` endpoints

**Modifica**: `backend/main.py`
- Aggiungere 2 endpoint REST
- Integrare `greeks_service` nel lifecycle (start/stop)

### IV Rank e Skew Calculation

```python
# IV Rank (richiede storico 52 settimane, inizialmente usare range giornata)
iv_rank = (current_iv - iv_min) / (iv_max - iv_min) * 100

# Skew 25-delta
skew = iv_25delta_put - iv_25delta_call

# Term structure
term = "contango" if iv_short < iv_long else "backwardation"
```

Nota: IV Rank completo richiede storico 52w. Per l'MVP, usare range intraday come proxy. Lo storico si accumula naturalmente nel DB nel tempo.

### Frontend

**File**: `frontend/src/components/GreeksPanel.tsx` (nuovo)

Contenuto:
- Tabella Greeks ATM (delta, gamma, theta, vega)
- IV gauge (bid/mid/ask spread)
- Skew indicator (barra orizzontale)
- Term structure mini-chart
- Regime badge (LONG GAMMA / SHORT GAMMA)

Posizionamento: Pannello laterale destro, sotto il GexProfile.

---

## Sezione 2: Alerts & Signals Engine

### Tipologie di Alert

| ID | Tipo | Trigger | Priorita |
|----|------|---------|----------|
| A1 | **ZGL Proximity** | Prezzo entro N punti dallo Zero Gamma Level | HIGH |
| A2 | **Wall Test** | Prezzo entro N punti da Call/Put Wall | HIGH |
| A3 | **Flow Spike** | Net flow > $5M/min in una direzione | MEDIUM |
| A4 | **Gamma Flip** | Prezzo attraversa gamma flip zone | HIGH |
| A5 | **Momentum Reversal** | Momentum score crossing 70/30 con divergenza | MEDIUM |
| A6 | **Dark Pool DIX Extreme** | DIX > 0.45 o < 0.15 | LOW |

### Architettura Engine

```
┌─────────────────────────────────────────────┐
│              AlertEngine (backend)           │
│                                             │
│  tick_stream ──→ rule_evaluator ──→ fire()  │
│  flow_stream ──→ rule_evaluator ──→ fire()  │
│  gex_profile ──→ rule_evaluator ──→ fire()  │
│                                             │
│  fire() → DB insert → WS broadcast → log    │
└─────────────────────────────────────────────┘
```

L'engine gira come task async nel backend FastAPI. Valuta regole ad ogni tick/flow update. Non e' un daemon separato — vive dentro `main.py` come `asyncio.create_task()`.

### Database — Nuova Tabella

```sql
CREATE TABLE alerts (
    id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    underlying VARCHAR(10) NOT NULL,
    alert_type VARCHAR(30) NOT NULL,   -- zgl_proximity, wall_test, flow_spike, gamma_flip, momentum_reversal, dix_extreme
    severity VARCHAR(10) NOT NULL,     -- HIGH, MEDIUM, LOW
    direction VARCHAR(10),             -- BULLISH, BEARISH, NEUTRAL
    trigger_price DOUBLE PRECISION,
    level_price DOUBLE PRECISION,
    message TEXT,
    metadata JSONB                     -- dati aggiuntivi per tipo
);

SELECT create_hypertable('alerts', 'time');
```

### Endpoint Nuovi

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/api/alerts` | Ultimi alerts attivi (ultimi 100) |
| GET | `/api/alerts/config` | Configurazione soglie alert |
| PUT | `/api/alerts/config` | Aggiorna soglie alert |

### WebSocket — Nuovo Messaggio

```json
{
  "type": "alert",
  "data": {
    "id": 12345,
    "alert_type": "zgl_proximity",
    "severity": "HIGH",
    "direction": "BULLISH",
    "underlying": "SPX",
    "trigger_price": 5898.50,
    "level_price": 5900.00,
    "message": "SPX 1.5 pts from ZGL (5900.00) — long gamma regime, expect bounce",
    "timestamp": "2026-03-27T14:30:15Z"
  }
}
```

### Configurazione Alert (Default)

```json
{
  "zgl_proximity_points": 3.0,
  "wall_proximity_points": 2.0,
  "flow_spike_threshold": 5000000,
  "momentum_high": 70,
  "momentum_low": 30,
  "dix_extreme_high": 0.45,
  "dix_extreme_low": 0.15,
  "cooldown_seconds": 300
}
```

Il `cooldown_seconds` previene spam: stesso tipo di alert per stesso underlying non viene rifireato entro 5 minuti.

### Implementazione Backend

**File**: `backend/alert_engine.py` (nuovo)

```python
class AlertEngine:
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.config = AlertConfig()
        self.last_fired = {}  # (alert_type, underlying) -> timestamp
        self.gex_cache = {}   # underlying -> {zgl, call_wall, put_wall, regime}

    async def evaluate_tick(self, tick):
        """Chiamato ad ogni futures tick"""
        underlying = SYMBOL_TO_UNDERLYING.get(tick['symbol'])
        if not underlying:
            return
        await self._check_zgl_proximity(tick, underlying)
        await self._check_wall_proximity(tick, underlying)

    async def evaluate_flow(self, flow_tick):
        """Chiamato ad ogni flow tick"""
        await self._check_flow_spike(flow_tick)

    async def evaluate_momentum(self, momentum):
        """Chiamato quando momentum score si aggiorna"""
        await self._check_momentum_reversal(momentum)

    async def _fire(self, alert_type, severity, direction, underlying,
                    trigger_price, level_price, message, metadata=None):
        """Fire alert con cooldown check"""
        key = (alert_type, underlying)
        now = time.time()
        if key in self.last_fired:
            if now - self.last_fired[key] < self.config.cooldown_seconds:
                return
        self.last_fired[key] = now
        # Insert DB + broadcast WS
        ...
```

**Modifica**: `backend/main.py`
- Istanziare `AlertEngine` come singleton nel lifecycle
- Passare tick e flow all'engine nei broadcast loops
- Aggiungere 3 endpoint REST

---

## Sezione 3: UI/UX Overhaul

### Tema Dark Professionale

Paleta colori:
```
Background:     #0a0e17 (blu-nero)
Surface:        #111827 (card)
Border:         #1e293b (divisorio)
Primary:        #3b82f6 (blu)
Success:        #10b981 (verde)
Danger:         #ef4444 (rosso)
Warning:        #f59e0b (giallo)
Text primary:   #f1f5f9
Text secondary: #94a3b8
```

### Layout Revisonato

```
┌──────────────────────────────────────────────────────────────────┐
│  GEX Dashboard 4.0          [SPX] [QQQ]     🔔 Alerts (3)      │
├──────────────────────────────────┬───────────────────────────────┤
│                                  │  GreeksPanel                  │
│                                  │  ┌──────────────────────────┐ │
│                                  │  │ Regime: LONG GAMMA       │ │
│     LightweightChart             │  │ Delta: -0.15  Theta: -2.1│ │
│     (candele + GEX bars          │  │ IV: 19.0%  Skew: +2.3%  │ │
│      + dark pool overlay)        │  │ Term: contango           │ │
│                                  │  └──────────────────────────┘ │
│                                  │                               │
│                                  │  GexProfile                   │
│                                  │  (barre GEX esistenti)        │
│                                  │                               │
│  ┌───────────────────────────┐   │  AlertsPanel                  │
│  │  SmartMoneyBox (draggable)│   │  ┌──────────────────────────┐ │
│  │  Net Flow  Drift  Score   │   │  │ 🔴 ZGL Proximity 14:30  │ │
│  └───────────────────────────┘   │  │ 🟡 Flow Spike 14:28     │ │
│                                  │  │ 🟢 Momentum Rev 14:25   │ │
│                                  │  └──────────────────────────┘ │
│                                  │                               │
│                                  │  DarkPoolPanel                │
│                                  │  ┌──────────────────────────┐ │
│                                  │  │ DIX: 0.38  ▓▓▓▓▓░░░░   │ │
│                                  │  │ Dark Vol: $2.1B          │ │
│                                  │  │ Short Ratio: 48.2%       │ │
│                                  │  └──────────────────────────┘ │
└──────────────────────────────────┴───────────────────────────────┘
```

### Componenti Frontend

#### Nuovi Componenti

| Componente | File | Descrizione |
|-----------|------|-------------|
| **GreeksPanel** | `GreeksPanel.tsx` | Tabella Greeks, IV gauge, regime badge |
| **AlertsPanel** | `AlertsPanel.tsx` | Lista alert in tempo reale con icone severita |
| **DarkPoolPanel** | `DarkPoolPanel.tsx` | DIX gauge, volume bars, short ratio |
| **AlertBadge** | Dentro `AlertsPanel.tsx` | Contatore alert nel header, click per aprire |

#### Componenti Modificati

| Componente | Modifica |
|-----------|----------|
| **App.tsx** | Nuovo layout a griglia, header con AlertBadge, listeners per alert WS |
| **App.css** | Dark theme completo, nuova griglia CSS |
| **LightweightChart.tsx** | Dark theme chart, overlay linee ZGL/Wall, dark pool level markers |
| **GexProfile.tsx** | Dark theme bars, regime color coding |
| **SmartMoneyBox.tsx** | Dark theme, layout compatto |

### Responsive Design

- Desktop (>1200px): Layout 2 colonne come sopra
- Tablet (768-1200px): Chart full-width, pannelli impilati sotto
- Mobile (<768px): Single column, swipe tra pannelli

### Animazioni e Feedback

- Alert appearance: slide-in da destra con fade
- Regime change: flash del badge colore
- Flow spike: pulsazione del power meter
- GEX level touch: highlight temporaneo sulla barra

---

## Sezione 4: Dark Pool Levels

### Cos'è un Dark Pool Level

Livelli di prezzo derivati dove si concentra attivita' istituzionale fuori borsa. Non sono un dato nativo — si calcolano aggregando:

1. **Volume-weighted price clustering** — prezzi con block trade off-exchange concentrati
2. **Strike correlation** — dark pool prints attorno a strike specifici
3. **Cumulative delta** — net buying/selling per livello

Quando dark pool levels coincidono con livelli GEX → confluence zone ad alta probabilita' di reversal/continuazione.

### Fonti Dati

**Tradier NON fornisce dati dark pool.**

| Fonte | Latenza | Costo/mese | Integrazione |
|-------|---------|------------|--------------|
| **FINRA Reg SHO** | Giornaliero | Gratis | CSV download, DIX indicator |
| **FlowAlgo** | Real-time | $49-99 | WebSocket, plug in daemon |
| **Polygon.io Pro** | Real-time | $199 | Condition codes, block trade flag |
| **SqueezeMetrics** | Giornaliero | ~$720 | REST API, DIX + GEX |
| **SpotGamma** | 2x/giorno | $99-499 | Pre-computed levels |

### MVP: DIX Indicator (Gratis)

Il DIX (Dark Index) e' derivato dai dati FINRA Reg SHO:
```
DIX = 1 - (short_off_exchange_volume / total_off_exchange_volume)
```

Range: 0-1. Valori alti (>0.45) = molto short activity nei dark pool = potenziale bottom. Valori bassi (<0.15) = poco short = potenziale top.

### Implementazione MVP

**File**: `backend/darkpool_analyzer.py` (nuovo)

Responsabilita':
1. Download automatico giornaliero da FINRA: `https://otctransparency.finra.com/api/shortsale/volume?date=YYYYMMDD`
2. Parsing CSV, filtro per SPY e QQQ
3. Calcolo DIX, short volume ratio, dark pool volume totale
4. Salvataggio in tabella `darkpool_daily`
5. Cache in memoria, refresh giornaliero alle 18:00 ET

**Tabella DB**:

```sql
CREATE TABLE darkpool_daily (
    date DATE PRIMARY KEY,
    underlying VARCHAR(10) NOT NULL,
    short_volume BIGINT,
    total_volume BIGINT,
    short_ratio DOUBLE PRECISION,    -- short_volume / total_volume
    dix DOUBLE PRECISION,            -- 1 - short_ratio
    dark_volume_estimate BIGINT,     -- off-exchange short volume estimate
    updated_at TIMESTAMPTZ
);
```

### Endpoint

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/api/darkpool/dix/{underlying}` | DIX + metriche giornaliere |
| GET | `/api/darkpool/history/{underlying}?days=30` | Storico DIX |

### Frontend

**File**: `frontend/src/components/DarkPoolPanel.tsx` (nuovo)

Contenuto:
- DIX gauge (semicircular, range 0-1)
- Short volume ratio bar
- 7-day DIX mini chart (sparkline)
- Color coding: rosso (<0.15), giallo (0.15-0.45), verde (>0.45)

### Post-MVP: Real-time Dark Pool Feed

Architettura predisposta per integrazione FlowAlgo:
- Nuovo `darkpool_daemon.py` con WebSocket connection a FlowAlgo
- Stesso pattern di `options_flow_daemon.py`: buffer → DB → broadcast
- Filtra prints > $1M notional per institutional relevance
- Aggrega per livello prezzo, confronta con GEX per confluence zones
- Nuova tabella `darkpool_prints` (hypertable)
- Overlay sul LightweightChart come linee tratteggiate

---

## Sezione 5: Piano di Implementazione Parallelo

### Stream A: Backend (Giorno 1-2)

```
Giorno 1 Mattina:
  1. greeks_service.py — fetch Tradier chain con greeks=true
  2. Endpoint /api/greeks/{underlying} e /api/greeks/summary/{underlying}
  3. darkpool_analyzer.py — FINRA download + DIX calc
  4. Tabella darkpool_daily in db.py
  5. Endpoint /api/darkpool/dix/{underlying}

Giorno 1 Pomeriggio:
  6. alert_engine.py — AlertEngine class con 6 regole
  7. Tabella alerts in db.py
  8. Endpoint /api/alerts, /api/alerts/config
  9. Integrazione AlertEngine in main.py lifecycle
  10. WS broadcast messaggi alert

Giorno 2:
  11. Test end-to-end tutti endpoint
  12. Alert tuning (soglie, cooldown)
  13. Greeks caching e IV rank calculation
  14. Error handling e fallback
```

### Stream B: Frontend (Giorno 1-2)

```
Giorno 1 Mattina:
  1. Dark theme CSS (App.css rewrite)
  2. Layout grid 2 colonne responsive
  3. GreeksPanel.tsx — tabella + IV gauge + regime badge

Giorno 1 Pomeriggio:
  4. AlertsPanel.tsx — lista real-time con severita
  5. AlertBadge nel header
  6. DarkPoolPanel.tsx — DIX gauge + sparkline

Giorno 2:
  7. LightweightChart dark theme + ZGL/Wall overlay lines
  8. GexProfile dark theme
  9. SmartMoneyBox dark theme + compact layout
  10. Animazioni (alert slide-in, regime flash)
  11. Responsive breakpoints (tablet/mobile)
  12. Test cross-browser
```

### Dipendenze

```
Frontend GreeksPanel ──→ dipende da ──→ Backend /api/greeks/*
Frontend AlertsPanel ──→ dipende da ──→ Backend /api/alerts + WS alert messages
Frontend DarkPoolPanel ──→ dipende da ──→ Backend /api/darkpool/*
```

I componenti frontend possono essere sviluppati con mock data in parallelo al backend.

---

## File Nuovi e Modificati — Riepilogo

### File Nuovi

| File | Scope |
|------|-------|
| `backend/greeks_service.py` | Fetch + cache Greeks da Tradier ORATS |
| `backend/alert_engine.py` | 6 regole alert con cooldown |
| `backend/darkpool_analyzer.py` | FINRA download + DIX calc |
| `frontend/src/components/GreeksPanel.tsx` | Pannello Greeks + IV |
| `frontend/src/components/AlertsPanel.tsx` | Lista alert real-time |
| `frontend/src/components/DarkPoolPanel.tsx` | DIX gauge + volume |

### File Modificati

| File | Modifiche |
|------|-----------|
| `backend/main.py` | +6 endpoint, AlertEngine lifecycle, greeks_service init |
| `backend/db.py` | +2 tabelle (alerts, darkpool_daily) |
| `frontend/src/App.tsx` | Layout grid, AlertBadge, WS alert listener |
| `frontend/src/App.css` | Dark theme completo |
| `frontend/src/components/LightweightChart.tsx` | Dark theme + ZGL/Wall lines |
| `frontend/src/components/GexProfile.tsx` | Dark theme |
| `frontend/src/components/SmartMoneyBox.tsx` | Dark theme + compact |

### Tabelle DB Nuove

| Tabella | Tipo | Scopo |
|---------|------|-------|
| `alerts` | Hypertable | Storico alert fireati |
| `darkpool_daily` | Regular | DIX giornaliero per underlying |

---

## Considerazioni Post-MVP

1. **IV Rank storico**: Accumulare IV giornaliero nel DB per calcolo 52-week rank reale
2. **FlowAlgo integration**: WebSocket feed per dark pool prints real-time
3. **Backtesting**: Storico alert vs price action per calibrare soglie
4. **User auth**: Per SaaS commerciale, aggiungere login + subscription
5. **Multi-user**: WebSocket sessions per-user con alert preferences
6. **Mobile app**: React Native wrapper o PWA
7. **Billing**: Stripe integration per subscription management
