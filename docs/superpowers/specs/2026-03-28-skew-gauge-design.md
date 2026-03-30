# Skew Gauge + Zone Overlay — Design Spec

## Context

La Volatility Surface heatmap è stata implementata ma è information-dense e non glanceable per scalping. L'obiettivo è rendere la lettura dello skew immediata per il trading intraday.

## Concept & Vision

Due componenti complementari:
1. **SkewGauge**: un indicatore numerico nel sidebar che mostra lo skew medio OTM e un badge testuale — glanceable in 1 secondo
2. **Zone Overlay**: linee colorate disegnate direttamente sul grafico candlestick che indicano le zone dove lo skew è estremo — actionable al primo sguardo

## Design

### 1. SkewGauge Component (sidebar)

**Posizione**: sidebar panel, sotto Greeks (o sotto VolSurface)

**Visualizzazione**:
- Numero grande: skew medio ponderato degli strike OTM entro ±2% ATM
  - Formato: `+18.3%` o `-12.1%`
  - Colore: rosso (#ef4444) se > +15%, blu (#3b82f6) se < -15%, grigio (#64748b) se dentro soglia
- Badge sotto il numero:
  - `▲ HIGH RISK` (skew > +15%, put skew estremo → possible reversal LONG)
  - `▼ HIGH RISK` (skew < -15%, call skew estremo → possible reversal SHORT)
  - `— NEUTRAL` (skew tra -15% e +15%)

**Calcolo**:
- Filtra strike con moneyness tra 0.98 e 1.02 (OTM ±2%)
- Skew medio = media ponderata per gamma di ogni strike
- Skip strike senza entrambi call_iv e put_iv

**Soglia**: configurabile, default 15% (0.15 in decimale)

### 2. Zone Overlay (sul grafico)

**Posizione**: LightweightChart.tsx, stesso canvas overlay delle GEX levels esistenti

**Visualizzazione**:
- Fino a 3 linee per lato (put / call) dove |skew| > 15%
- Linee disegnate alla price coordinate del future price corrispondente allo strike
- Put zones (skew > +15%): linea rossa tratteggiata (#ef4444, 1px, dash [6,4])
- Call zones (skew < -15%): linea blu tratteggiata (#3b82f6, 1px, dash [6,4])
- Label a sinistra della linea: es. `PUT 5800 +18%`
- Le zone sono ordinate per skew decrescente (le più estreme in alto)

**Calcolo**:
- Usa i dati da `/api/volatility/surface?underlying=SPX` (già disponibili)
- Filtra strike 0DTE dove |skew| > 0.15
- Ordina per skew descending, prendi top 3 per lato
- Traduci strike in future price usando il moltiplicatore esistente

### Layout

```
Sidebar (sotto Greeks):
┌─────────────────────────┐
│  SKEW GAUGE            │
│     +18.3%             │
│  ▲ HIGH RISK           │
│  Skew threshold: 15%   │
└─────────────────────────┘

Chart overlay:
  ════════  6500 PUT +22%  (red dashed)
  ────────  6400 CALL -18%  (blue dashed)
  ════════  6350 PUT +16%  (red dashed)
```

## API Design

Nessuna modifica backend necessaria — i dati arrivano da `/api/volatility/surface` già implementato.

Response usato:
```json
{
  "surface": [{
    "days_to_expiry": 0,
    "strikes": [
      { "strike": 5800, "iv": 0.28, "call_iv": 0.22, "put_iv": 0.34, "skew": 0.12, "gamma": 0.003 }
    ]
  }]
}
```

## Component Structure

```
frontend/src/components/
├── SkewGauge.tsx          # NEW: skew indicator component
├── LightweightChart.tsx   # MODIFY: add zone overlay
```

## Technical Approach

### SkewGauge
- Legge da `/api/volatility/surface` (già in polling ogni 2 min nel componente VolSurface)
- states: skew value, skew direction, badge status
- Calcolo inline nel componente (nessun backend modificato)
- Stile: pannello scuro con bordo sottile

### LightweightChart Zone Overlay
- Estende il canvas overlay esistente (quello che disegna GEX levels)
- Nuova funzione `drawSkewZones()` chiamata dopo `drawOverlay()`
- Usa `series.priceToCoordinate()` per convertire strike → y coordinate
- Ordine di disegno: GEX levels → Skew zones (così GEX ha priorità visiva)

## Reversal Signal Integration

Quando SkewGauge mostra HIGH RISK e il prezzo si avvicina a una zona (within 5 points):
- Il ReversalGauge esistente già combina GEX proximity + flow divergence
- Possibile estensione futura: aggiungere skew proximity come 6° componente

## Open Questions
- Soglia: 15% va bene o preferisci 20%?
- Quante zone max: 3 confermato?
