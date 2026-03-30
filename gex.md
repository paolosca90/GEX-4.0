# GEX 4.0 — Documentazione Completa

## Contesto di Trading

**Mercato:** Futures CME (ES/NQ) + Opzioni 0DTE su SPX/QQQ
**Orario:** Regular Trading Hours (RTH): 09:30–16:00 ET
**Oracol:** Tutti i dati in tempo reale via WebSocket broadcast

---

## 1. GEX Profile (Gamma Exposure)

### Cos'è
La **Gamma Exposure** è la sensitività del delta delle opzioni a variazioni del underlying. Viene calcolata per ogni strike e sommata per creare il GEX profile giornaliero.

### Come si Calcola
```
GEX_per_strike = (Open_Interest_CALL + Open_Interest_PUT) × Gamma × Future_Price
```

Ogni strike ha:
- **strike** — prezzo di esercizio
- **gex** — gamma exposure in dollari (positivo = dealers long gamma, negativo = dealers short gamma)
- **futurePrice** — strike tradotto in prezzo futures (per allineamento chart)

### Livelli Chiave dal GEX Profile

| Livello | Calcolo | Significato |
|----------|---------|-------------|
| **ZGL (Zero Gamma Level)** | Strike dove la cumulativa GEX è minima (più negativa) | Livello di pinning in short gamma; price tende a reversare da qui |
| **Call Wall** | Strike con GEX massima positiva | Resistenza; in long gamma price consolida attorno |
| **Put Wall** | Strike con GEX più negativa | Supporto; in short gamma price accelera attraverso |

### Offset Dinamico (Future vs Strike)
I prezzi degli strike Tradier sono in punti index (es. 560 per QQQ), ma il chart è in prezzi futures (es. 23,200). L'offset si calcola:

```
# SPX (additivo)
offset = US500-F − SPX_spot
futurePrice = strike + offset

# QQQ (additivo)
offset = NAS100-F − QQQ_spot
futurePrice = strike + offset
```

---

## 2. Reversal Signal (ScalpingPanel)

### Cos'è
Score 0–100% che indica la probabilità di un **reversal a breve termine** (5–15 min hold, stop 8–10 pts).

### 5 Componenti

| Componente | Peso | Dato Sorgente | Cosa Misura |
|------------|------|---------------|-------------|
| **GEX Proximity** | 25% | GEX Profile (future price) | Distanza del prezzo attuale dallo ZGL / Call Wall / Put Wall |
| **Flow Divergence** | 25% | options_flow_1m (2s aggregated) | Drift decelerante + counter-flow surge |
| **Price Extension** | 20% | futures_ticks (20 tick window) | Z-score del prezzo dalla media mobile 20-tick |
| **Trap Signal** | 15% | options_flow_ticks | Bear/Bull trap (drift vs counter-flow) |
| **Gamma Regime** | 15% | GEX Profile + regime | Short gamma + vicino ZGL = pinning atteso |

### Calcolo Confluence
```
confluence = Σ (score_componente × peso_componente)
```

### Direzione
```
bull_score = Σ (score × peso) per componenti con direction=BULLISH
bear_score = Σ (score × peso) per componenti con direction=BEARISH
direction = BULLISH se bull_score − bear_score > 3, altrimenti BEARISH
```

### Interpretazione

| Confluence | Significato |
|------------|-------------|
| **≥ 70%** | Segnale forte — reversal probabile |
| **50–69%** | Segnale moderato — cautela |
| **< 50%** | Neutrale — nessun setup |

### Livelli Operativi (Entry / Stop / Target)

| Campo | Calcolo |
|--------|---------|
| **ENTRY** | key_level (ZGL o Wall più vicino) |
| **STOP** | key_level ± 50% della distanza dal key level |
| **TARGET** | ZGL o Wall opposto |
| **R:R** | \|target − entry\| / \|stop − entry\| |

---

## 3. Time Urgency (ScalpingPanel)

### Session Phase

| Fase | Orario ET | Colore | Significato |
|------|-----------|--------|-------------|
| **EARLY RTH** | 09:30–11:00 | Grigio | Range-bound, volatilità bassa |
| **MID RTH** | 11:00–14:00 | Giallo | Fase intermedia |
| **POWER HOUR** | 14:00–16:00 | Rosso | Theta crush accelerato, volatilità massima |

### Countdown
Minuti rimanenti fino alle 16:00 ET (chiusura mercato / expiry 0DTE).

### Theta Burn
```
Θ/min = ATM_average_theta / 390
```
(dove 390 = minuti in un giorno di trading RTH)

Segnale `ACCELERATING` quando ET ≥ 14:00 (theta crush impatta significativamente il prezzo).

---

## 4. SkewGauge

### Cos'è
Misura lo **skew ATM** — la differenza tra IV delle put e IV delle call at-the-money.

### Calcolo
```
skew = put_IV − call_IV
```

Per ogni strike ATM ± 5%, si prende il **minimo skew** (il più negativo = put più care relative alle call = downside risk più elevato).

### Soglia
```
SKEW_THRESHOLD = 3%
```

Se skew < −3% → **PUT** (downside risk elevato)
Se skew > +3% → **CALL** (upside risk elevato)
Altrimenti → **NEUTRAL**

### Interpretazione

| Skew | Contesto | Trading |
|------|---------|---------|
| **> −5%** | Skew normale | Condizioni equilibrate, reversal possibili |
| **−5% a −20%** | Skew elevato | Fear in aumento, cautela su long |
| **< −20%** | HIGH RISK | Fear estremo — continuation ribasso probabile, evitare reversal long |

> **Regola:** Più lo skew è negativo, meno probabile è un reversal bullish (smart money si è già posizionato short con puts costose).

---

## 5. Flow Concentration

### Cos'è
Aggregazione del flusso opzioni per strike, mostrato come linea orizzontale sul chart.

### Calcolo
```sql
SELECT strike, option_type, SUM(trade_premium) AS total_premium
FROM options_flow
WHERE underlying = 'SPX' AND time > NOW() − INTERVAL '60 min'
GROUP BY strike, option_type
```

Ogni livello mostra:
- **strike** → tradotto in future price
- **call_premium / put_premium** — somma del premium weighted per strike
- **dominant** — call o put a seconda di quale ha più premium

### Visualizzazione Chart
- Linee **arancioni** = call concentration (resistance, smart money selling calls)
- Linee **blu** = put concentration (support, smart money buying puts)
- Spessore linea = dimensione del premium (più spesso = più istituzionale)

---

## 6. Momentum Score

### Cos'è
Score composito 0–100 per il momentum a breve termine (9:30–16:00 ET).

### 5 Componenti

| Componente | Peso | Cosa Misura |
|------------|------|-------------|
| **Flow Velocity** | 35% | Drift 1min vs 5min — accelerazione o decelerazione |
| **Price Action** | 25% | Z-score 20-tick — overextension dal prezzo medio |
| **GEX Positioning** | 20% | Distanza dal ZGL — più vicino = più probabile reversal |
| **Volume Ratio** | 10% | Call volume vs put volume ratio — estremi segnalano capitolazione |
| **Theta Effect** | 10% | Accelerazione theta basata su ora ET |

### Interpretazione

| Score | Significato |
|-------|-------------|
| **> 60** | Momentum bullish |
| **40–60** | Neutrale |
| **< 40** | Momentum bearish |

---

## 7. Greeks (da ORATS / Tradier)

### Cos'è
I greci vengono da ORATS via Tradier per ogni contratto options.

### Derivative di First Order

| Greco | Simbolo | Definizione | Applicazione |
|-------|---------|------------|-------------|
| **Delta** | Δ | Variazione prezzo option per $1 variazione underlying | Sensitività al prezzo; ATM ≈ 0.50 |
| **Theta** | Θ | Decadimento temporale giornaliero ($/giorno) | Theta è negativo sempre (option perde valore col tempo); 0DTE accelera dopo 14:00 ET |
| **Vega** | ν | Variazione prezzo option per 1% variazione IV | Sensitività alla volatilità; long option = long vega |

### Derivative di Second Order

| Greco | Simbolo | Definizione | Applicazione |
|-------|---------|------------|-------------|
| **Gamma** | Γ | Variazione delta per $1 variazione underlying | Accelerazione del delta; ATM gamma massima |
| **Charm** | — | Variazione theta nel tempo | Misura theta decay acceleration |

### Aggregazioni per Strike

| Metrica | Calcolo |
|---------|---------|
| **Total Gamma** | Σ Gamma per tutti i contratti ATM |
| **Net Delta Exposure** | Σ (Delta × Open_Interest) — indica posizionamento netto dealers |
| **Avg Theta** | Media theta dei contratti ATM |
| **ATM IV** | IV a strike più vicino al spot |
| **Skew** | put_IV − call_IV per ogni strike |

---

## 8. OI Delta Tracker

### Cos'è
Open Interest delta — variazione di open interest negli ultimi 30 minuti per ogni strike.

### Calcolo
```sql
snapshot OI_current − OI_30min_ago
```

### Componenti

| Campo | Significato |
|-------|-------------|
| **oi_delta** | Variazione netta OI (posizioni aperte − chiuse) |
| **oi_delta_block** | OI delta da block trades (>200 contratti) |
| **oi_delta_retail** | OI delta da retail trades (≤200 contratti) |

### Interpretazione

| Condizione | Significato |
|------------|-------------|
| **Block OI delta > Retail OI delta** | Smart money (istituzionali) dominano il flusso |
| **Put OI delta in aumento** | Sottovalutazione del rischio ribasso; players si coprono |
| **Call OI delta in aumento** | FOMO / speculazione rialzista |

---

## 9. Dark Pool DIX

### Cos'è
Dark Pool Index — misura la percentuale di volume che transita nei dark pool (internalization) rispetto al volume totale.

### Interpretazione

| DIX | Contesto |
|-----|----------|
| **> 0.45** | HIGH — dealers internalizzano molto volume = price action compressa (potential squeeze) |
| **0.30–0.45** | NEUTRAL |
| **< 0.30** | DealersExternalizzazione = price action più liquida e direzionale |

---

## 10. Alert Engine

### Regole di Alert

| Regola | Trigger | Logica |
|--------|---------|--------|
| **ZGL Proximity** | Price entro 3 pts dallo ZGL | Vicino ZGL in short gamma = probabilità pinning/reversal alta |
| **Flow Spike** | \|call_premium − put_premium\| > $5M net | Spike direzionale = probabilmente smart money |
| **Reversal Confluence** | Confluence ≥ 70% | Segnale forte = alert con soglia 70/85 |

### Filtri
- **Cooldown:** 300 secondi tra alert dello stesso tipo
- **Wall proximity:** Disabilitata (era troppo rumorosa)

---

## 11. Opzioni Flow (Smart Money)

### Dati Grezzi
Ogni trade opzione arriva da Tradier WebSocket con:
- `symbol` — es. SPXW260330C05800000
- `price` — premium per contratto
- `size` — numero di contratti
- `bid / ask` —NBBO al momento del trade

### 4 Filtri Applicati

| Filtro | Soglia | Razionale |
|--------|--------|-----------|
| **Spread Neutrality** | spread > $0.50 → trade ignorato se mid-zone | Wide spread = bid/ask too wide = probably not directional |
| **OTM Filter** | Ignora opzioni ITM (delta ≈ 1) | ITM options aggiungono rumore, non signal |
| **Block Discount** | Log dampening per size > 200 | Block trades istituzionali hanno too much weight altrimenti |
| **Urgency Weight** | 1.5× per at-bid/ask, 0.8× per mid | Aggressive execution = stronger signal |

### Premium Weighted
```
raw_premium = price × size × 100
weighted_premium = raw_premium × block_weight × urgency_weight × distance_weight
```

---

## 12. Tabella Riassuntiva Segnali

| Signal | Fonte | Timeframe | Uso |
|--------|-------|-----------|-----|
| **Reversal Confluence** | 5 componenti | 5–15 min | Entry direction + levels |
| **Momentum Score** | 5 componenti | 5–15 min | Confirm/reject reversal |
| **SkewGauge** | Vol surface | 15 min | Filtro contestuale (se < −20% → no long) |
| **ZGL Proximity Alert** | GEX Profile | Real-time | Preavviso zona reversal |
| **Flow Spike Alert** | Options flow | Real-time | Spike direzionale smart money |
| **Session Phase** | Time | Continuo | Contesto volatilità attesa |
| **DIX** | Dark pool | 15 min | Squeeze risk detection |

---

## Glossario

| Termine | Definizione |
|---------|-------------|
| **0DTE** | Opzioni che scadono lo stesso giorno (zero days to expiration) |
| **ATM** | At The Money — strike più vicino al prezzo spot |
| **OTM** | Out of The Money — strike sopra (call) o sotto (put) il spot |
| **ITM** | In The Money — strike sotto (call) o sopra (put) il spot |
| **Gamma** | Second-order greek — quanto cambia il delta al cambiare del prezzo |
| **Theta** | Decadimento temporale — quanto perde valore l'opzione ogni giorno |
| **Vega** | Sensitività all'IV — quanto cambia il prezzo se IV cambia 1% |
| **Delta** | Sensitività al prezzo — quanto cambia il prezzo option per $1 di variazione underlying |
| **Short Gamma** | Dealers hanno gamma negativo (devono buy high / sell low per hedgiary) |
| **Long Gamma** | Dealers hanno gamma positivo (forniscono liquidity, mean-reversion atteso) |
| **ZGL** | Zero Gamma Level — strike dove gamma cumulativa è più negativa |
| **Call Wall** | Strike con gamma positiva massima (resistance) |
| **Put Wall** | Strike con gamma negativa massima (support) |
| **Smart Money** | Istituzionali che operano con size grande (block trades) |
| **Retail** | Trader individuali con size piccola |
| **DIX** | Dark Pool Index — % volume nei dark pool |
| **ORATS** | Options Research and Trading Services — fornitore di dati greeks |
| **RTH** | Regular Trading Hours — 09:30–16:00 ET |
