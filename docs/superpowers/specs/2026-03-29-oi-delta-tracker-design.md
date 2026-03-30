# OI Delta Tracker — Design Spec

## Overview

Traccia la variazione di Open Interest (OI) per strike durante la sessione, distinguendo build-up retail (<100 contratti) da block flow (≥100). Mostra top 3 call e top 3 put per OI delta in GreeksPanel e come overlay lines nel chart.

## Architecture

### Database Schema

**`options_flow` table** — aggiunta colonna:
```sql
ALTER TABLE options_flow ADD COLUMN IF NOT EXISTS oi_delta INTEGER;
COMMENT ON COLUMN options_flow.oi_delta IS 'Delta OI session-over-session for this strike, set on insert from batch OI snapshot';
```

**Nuova tabella `oi_snapshots`**:
```sql
CREATE TABLE oi_snapshots (
    time TIMESTAMPTZ NOT NULL,
    underlying TEXT NOT NULL,      -- 'SPX' or 'QQQ'
    strike INTEGER NOT NULL,
    oi_total INTEGER NOT NULL,       -- absolute OI at snapshot time
    oi_delta INTEGER NOT NULL,       -- delta vs previous close
    oi_delta_retail INTEGER NOT NULL,
    oi_delta_block INTEGER NOT NULL,
    PRIMARY KEY (time, underlying, strike)
);
SELECT create_hypertable('oi_snapshots', 'time');
CREATE INDEX idx_oi_snapshots_underlying_strike ON oi_snapshots (underlying, strike, time DESC);
```

### Backend

**`greeks_service.py`** — aggiunte:
```python
async def fetch_oi_snapshot(underlying: str) -> List[dict]:
    """Fetch OI per strike da Tradier options chain. Chiamato ogni 30 min."""
    # Usa Tradier /markets/options chain endpoint
    # Restituisce [{strike, oi_total, side}] per tutti gli strike

async def get_oi_for_strikes(underlying: str, strikes: List[int]) -> dict:
    """Fetch OI per una lista di strike (usa la chain intera, cache 60s)."""
    # Riutilizza logica esistente Greeks cache

def compute_oi_delta(snapshot: dict, prev_close_oi: dict) -> int:
    """OI attuale - OI close ieri per strike."""
    return snapshot['oi_total'] - prev_close_oi.get(snapshot['strike'], 0)
```

**Nuovo file `oi_tracker.py`**:
```python
class OITracker:
    def __init__(self, db_pool):
        self.db = db_pool
        self.prev_close_oi: Dict[str, Dict[int, int]] = {}  # underlying → strike → oi

    async def load_prev_close_oi(self, underlying: str) -> None:
        """Carica OI close ieri da oi_snapshots più recente pre-market."""
        # SELECT strike, oi_total FROM oi_snapshots
        # WHERE underlying = X AND time < today 09:30 ORDER BY time DESC LIMIT 1

    async def compute_breakdown(self, underlying: str, strike: int, lookback_minutes: int = 120) -> tuple[int, int]:
        """Deriva retail/block OI delta dal flow.
        - retail: sum of trade_size < 100 from options_flow
        - block: sum of trade_size >= 100
        """
        # SELECT SUM(CASE WHEN trade_size < 100 THEN sentiment_value ELSE 0 END),
        #        SUM(CASE WHEN trade_size >= 100 THEN sentiment_value ELSE 0 END)
        # FROM options_flow
        # WHERE underlying = X AND strike = Y AND time > now() - interval '120 minutes'

    async def snapshot_and_store(self, underlying: str) -> None:
        """Fetch OI da Tradier, calcola delta, salva in oi_snapshots."""
        # load_prev_close_oi se non ancora caricato
        # fetch_oi_snapshot() → per ogni strike
        # compute_oi_delta() → oi_delta
        # compute_breakdown() → oi_delta_retail, oi_delta_block
        # bulk INSERT into oi_snapshots

    def get_buildup(self, underlying: str) -> dict:
        """Ritorna top 3 calls + top 3 puts per absolute oi_delta."""
        # SELECT strike, oi_delta, oi_delta_retail, oi_delta_block, side
        # FROM latest_oi_buildup_view  -- view su oi_snapshots per ogni underlying
        # ORDER BY ABS(oi_delta) DESC
        # LIMIT 3 per side
```

**`main.py`** — aggiunte:
```python
# Startup: avvia OIT racker
# Background task: ogni 30 min durante 9:30-16:00 EST chiama oi_tracker.snapshot_and_store()

@app.get("/api/oi/buildup/{underlying}")
async def get_oi_buildup(underlying: str):
    """Top 3 calls + top 3 puts per OI delta."""
    result = oi_tracker.get_buildup(underlying.upper())
    return result
```

### Frontend

**GreeksPanel.tsx** — nuova sezione:
```
┌─ OI BUILDUP ─────────────────────┐
│ CALLS              │ PUTS        │
│ Strike  OI Δ  Blk  │ Strike OI Δ │
│ 5500   +240  ██   │ 5400  -180 ██│
│ 5510   +120  █    │ 5390  -90  █ │
│ 5520   +80   █    │ 5380  -60    │
└────────────────────┴─────────────┘
```
- 3 righe calls (verde), 3 righe puts (rosso)
- Colonna "Blk" mostra barra proporzionale block vs retail
- Badge "BUILDING ↑" / "UNWINDING ↓" sotto ogni riga
- Polling `/api/oi/buildup/{underlying}` every 30s

**LightweightChart.tsx** — overlay lines:
```typescript
interface OILevel {
  strike: number;
  translatedPrice: number;  // future price
  oiDelta: number;
  side: 'call' | 'put';
  isBlockOnly: boolean;     // true se solo block (no retail)
}

// Aggiunto a GEXOverlayData:
oiLevels: OILevel[]

// Canvas drawing (aggiunto a drawOverlays):
// 6 linee verticali
// Colore: #00C853 (call/verde), #FF1744 (put/rosso)
// Opacità: 0.6, dashed per isBlockOnly, solid altrimenti
// Label: "5500C +240" in alto alla linea
// Z-index: sopra GEX lines, sotto price label
```

### Data Flow

```
Tradier API ──► fetch_oi_snapshot() ──► oi_snapshots table (ogni 30 min)
                                           │
                              compute_oi_delta() ◄── prev_close_oi
                              compute_breakdown() ◄── options_flow table
                                           │
                              get_buildup() ──► /api/oi/buildup/{underlying}
                                                 │
                                    ┌────────────┴───────────┐
                                    ▼                        ▼
                             GreeksPanel              LightweightChart
                             (tabella 6 righe)         (6 overlay lines)
```

### Implementation Order

1. DB migration (colonna options_flow.oi_delta + tabella oi_snapshots)
2. `oi_tracker.py` — OITracker class
3. `greeks_service.py` — fetch_oi_snapshot()
4. `main.py` — endpoint + background snapshot task
5. `GreeksPanel.tsx` — OI Buildup section
6. `LightweightChart.tsx` — overlay lines

### Edge Cases

- **No OI data from Tradier**: skip snapshot, log warning, retry next interval
- **Stale prev close OI**: se load_prev_close_oi non trova dati, usa oi_delta = oi_total (primo giorno)
- **No flow per strike**: oi_delta_retail/block = 0, mostra solo oi_delta
- **Market closed**: non eseguire snapshot task fuori 9:30-16:00 EST
