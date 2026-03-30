# Volatility Surface Heatmap — Design Spec

## Context

GEX 4.0 attualmente mostra ATM IV e uno skew testuale basilare nel pannello Greeks. Per individuare inversioni intraday è necessario visualizzare la **superficie di volatilità** — come cambia l'IV attraverso strikes e scadenze.

## Concept & Vision

Heatmap 2D della volatilità implicita per 0DTE + 1DTE, orientata al trading intraday:
- **Asse Y**: Strike prices (ATM al centro, OTM put a sinistra, OTM call a destra)
- **Asse X**: Expirations (0DTE = oggi, 1DTE = domani)
- **Colore cella**: IV % (blu = vol-bassa, rosso = vol-alta)
- **Cella selezionata**: mostra i dettagli (strike, IV, delta, gamma)

L'obiettivo è identificare **skew estremi** — quando le celle OTM Put sono molto più rosse delle OTM Call → zona di paura → probabile inversione bullish.

## Design

### Layout
- Nuovo componente `VolSurface.tsx` posizionato nel sidebar panel sotto Greeks
- Grid di celle colorate (canvas-based per performance)
- Tooltip on-hover con dettagli
- Toggle per mostrare/nascondere

### Color Scale
- 0-10% IV: blu scuro `#1e40af`
- 10-20% IV: blu chiaro `#60a5fa`
- 20-30% IV: verde `#22c55e`
- 30-40% IV: giallo `#eab308`
- 40-50% IV: arancio `#f97316`
- 50%+ IV: rosso `#ef4444`

### Data Refresh
- Polling ogni 2 minuti (le chain Tradier hanno rate limit)
- Indicatore "Last updated" timestamp

## API Design

### New Endpoint
`GET /api/volatility/surface?underlying=SPX`

Response:
```json
{
  "underlying": "SPX",
  "spot_price": 5685.0,
  "surface": [
    {
      "expiration": "2026-03-30",
      "days_to_expiry": 0,
      "strikes": [
        { "strike": 5500, "iv": 0.32, "delta": -0.12, "gamma": 0.002, "call_iv": 0.28, "put_iv": 0.36 },
        { "strike": 5550, "iv": 0.27, "delta": -0.05, "gamma": 0.003, "call_iv": 0.25, "put_iv": 0.29 },
        ...
      ]
    },
    {
      "expiration": "2026-03-31",
      "days_to_expiry": 1,
      "strikes": [...]
    }
  ],
  "updated_at": "2026-03-28T17:30:00Z"
}
```

### Backend Implementation
- `greeks_service.py`: aggiungere `get_volatility_surface(underlying)` che:
  1. Chiama Tradier `/v1/markets/options/chains` per 0DTE e 1DTE
  2. Estrae IV, delta, gamma per ogni strike dalla risposta greeks
  3. Calcola skew = put_iv - call_iv per ogni strike
  4. Restituisce la struttura aggregata

### Data Flow
Tradier API → greeks_service.py → new REST endpoint → VolSurface.tsx → Canvas heatmap

## Component Structure

```
frontend/src/components/
├── VolSurface.tsx        # Main component (heatmap canvas + tooltip)
```

## Technical Approach

### Backend
- Estendere `greeks_service.py` con `fetch_volatility_surface()`
- Usare le expiration dates disponibili in Tradier (0DTE + 1DTE)
- `asyncio.gather()` per chiamate parallele alle due chain
- Risposta cached per 2 minuti per evitare rate limit

### Frontend
- Componente canvas-based: disegna celle rettangolari colorate
- Scala colori interpolata tra i threshold
- Strikes normalizzati: raggruppati in bucket (ogni cella = 1 bucket di strike)
- Max 20 strikes visibili per heatmap leggibile

## Reversal Detection

La heatmap da sola è visiva. Per renderla **actionable**:
- Quando put_iv > call_iv + 15% (skew > 0.15) agli strikes OTM → flag "HIGH SKEW" in rosso
- Quando il pattern della riga 0DTE mostra smile invertito (call > put agli strike OTM alti) → flag "SKEW REVERSAL"

## Open Questions
- Quante expiration? (0DTE + 1DTE confermato)
- Bucket strikes: ogni quanto? (ogni 25 punti per SPX, ogni 5 per QQQ)
