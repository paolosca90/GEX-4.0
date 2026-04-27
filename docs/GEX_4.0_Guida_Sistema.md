# GEX 4.0 — Guida Completa del Sistema di Trading

**Versione:** 4.0 | **Data:** Aprile 2026
**Dashboard:** http://137.220.63.222

---

## 1. Panoramica del Sistema

GEX 4.0 è un sistema di monitoraggio real-time della **Gamma Exposure (GEX)** per futures su S&P 500 (ES) e Nasdaq 100 (NQ). Il sistema integra:

- **Candlestick charts** in tempo reale con livelli GEX sovrapposti
- **GEX Profile** — distribuzione completa dell'esposizione gamma per ogni strike
- **Smart Money Power Meter** — flusso opzioni netto (call vs put) in tempo reale
- **Momentum Score** — punteggio composito 0-100 per la direzione del mercato
- **Zone Alerts** — segnali di ipercomprato/ipervenduto basati sulla prossimità ai livelli GEX

---

## 2. Architettura Tecnica

### 2.1 Stack

```
Frontend:  React + Vite + TypeScript + LightweightCharts
Backend:   FastAPI (Python) + Uvicorn + WebSocket
Database:  PostgreSQL + TimescaleDB (hypertable per time-series)
Data:      cTrader OpenAPI (futures ticks) + Tradier API (opzioni)
VPS:       Vultr 137.220.63.222 (Ubuntu, nginx reverse proxy)
```

### 2.2 Flussi Dati

```
cTrader OpenAPI
      │
      ▼
ctrader_openapi_daemon.py ──► futures_ticks (hypertable)
                                    │
                                    ▼
                            WebSocket broadcast (/ws/market_data)
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
            LightweightChart                  SmartMoneyBox
            (candlestick + GEX)               (power meter)

Tradier API ──► gex_calculator.py ──► gex_profile ──► GEX bars + Key Levels
Tradier WS  ──► options_flow_daemon ──► options_flow_ticks ──► Power Meter
```

### 2.3 Database — Tabelle Principali

| Tabella | Tipo | Contenuto |
|---------|------|-----------|
| `futures_ticks` | hypertable | Tick price/volume per US500-F, NAS100-F |
| `options_flow` | hypertable | Singole operazioni opzioni (Tradier WS) |
| `options_flow_ticks` | hypertable | Flow aggregato a 2 secondi con EMA drift |
| `options_flow_1m` | hypertable | Flow aggregato a 1 minuto |
| `gex_profile` | normale | GEX per strike (calcolato giornalmente 16:30 EST) |
| `gex_level_interactions` | hypertable | Storico bounce/rimbalzo ai livelli GEX |

### 2.4 API Endpoints Principali

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| WS | `/ws/market_data` | Broadcast real-time ticks + flow |
| GET | `/api/candles/{symbol}` | OHLCV 1m/5m/15m |
| GET | `/api/gex/latest` | GEX profile + key levels (ZGL, CW, PW) |
| GET | `/api/flow/{symbol}` | Flow opzioni per underlying |
| GET | `/api/momentum/{underlying}` | Momentum Score composito |
| GET | `/api/momentum/zone-alert/{underlying}` | Segnale zona ipercomprato/ipervenduto |

---

## 3. La Teoria della GEX

### 3.1 Cos'è la Gamma Exposure

La **Gamma Exposure (GEX)** misura quanto rapidamente i market maker devono comprare/vendere il sottostante per coprire le loro posizioni in opzioni al variare del prezzo.

```
GEX per strike = Gamma(strike) × Open Interest(strike) × 100 × Spot Price
```

- **GEX positivo** (call): i market maker devono comprare futures quando il prezzo sale
- **GEX negativo** (put): i market maker devono vendere futures quando il prezzo scende
- **Zero Gamma Level (ZGL)**: il prezzo dove la somma cumulativa della GEX è minima

### 3.2 Perché la GEX Causa Reverals

Quando il prezzo si avvicina a un **Zero Gamma Level (ZGL)**:

1. I market maker hanno posizioni gamma elevate vicino a quel livello
2. Devono fare hedging attivo per mantenere delta-neutral
3. L'azione di hedging crea **pressione direzionale** che respinge il prezzo lontano dallo ZGL
4. Più il prezzo è vicino allo ZGL, più la pressione è forte

**Regola empirica:**
- Prezzo **sopra ZGL** → bias ribassista (MM vendono per copertura)
- Prezzo **sotto ZGL** → bias rialzista (MM comprano per copertura)

### 3.3 Call Wall e Put Wall

| Livello | Significato | Effetto sul prezzo |
|---------|-------------|-------------------|
| **Call Wall** | Strike con massimo GEX positivo | Resistenze dinamiche — il prezzo fatica a salire oltre |
| **Put Wall** | Strike con massimo GEX negativo (in valore assoluto) | Supporti dinamici — il prezzo rimbalza su questo livello |
| **Zero Gamma (ZGL)** | Livello dove GEX cumulativa = 0 | Punto di equilibrio — trigger per reversal |

---

## 4. Come Leggere il Dashboard

### 4.1 Layout Principale

```
┌─────────────────────────────────────────────────────────────────┐
│ [ES/S&P 500 Chart]           │ [GEX Profile]  │ [Smart Money]  │
│                               │                │  Power Meter   │
│  Candlestick + GEX lines     │  GEX bars      │                │
│  (ZGL, CW, PW, OI)          │  (call/put)    │  Net Flow      │
│                               │                │  Drift EMA     │
├─────────────────────────────────────────────────────────────────┤
│ [Scalping Panel]            [SkewGauge]         [GreeksPanel]  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 I Livelli Chiave sul Chart

Ogni livello è disegnato come linea orizzontale con etichetta prezzo:

| Colore | Livello | Significato |
|--------|---------|-------------|
| **Giallo** | 0GEX (ZGL) | Zero Gamma — reversal point |
| **Verde** | CW (Call Wall) | Massima pressione di acquisto opzioni |
| **Rosso** | PW (Put Wall) | Massima pressione di vendita opzioni |
| **Verde tratteggiato** | Top Call | Altre resistenze call |
| **Rosso tratteggiato** | Top Put | Altri supporti put |
| **Arancione** | CALL ZONE | Cluster di flow call concentrato |
| **Blu** | PUT ZONE | Cluster di flow put concentrato |
| **Verde chiaro** | OI Buildup (call) | Accumulo open interest call |
| **Rosso chiaro** | OI Buildup (put) | Accumulo open interest put |

### 4.3 GEX Profile (sidebar)

- **Barre verdi** (a destra): GEX positivo (call gamma)
- **Barre rosse** (a destra): GEX negativo (put gamma)
- **Zero GEX** (etichetta gialla): il Gamma Flip — prezzo di equilibrio

Il profilo mostra dove si concentra la "pressione" dei market maker.

### 4.4 Smart Money Power Meter

| Metrica | Descrizione |
|---------|-------------|
| **Net Flow** | Flusso netto call - put (in $) ultimi 5 min |
| **Drift** | EMA(120s) del net flow — direzione trend |
| **Sentinels** | Numero di block trades (>$50K) rilevati |
| **Reg M** | Tick indicator per Regulation M |

---

## 5. La Strategia di Trading

### 5.1 Setup Base — Reversal alla GEX

**Precondizioni:**
1. Il prezzo è **vicino** a un livello GEX chiave (ZGL, CW, PW) — entro 0.3%
2. Il **Momentum Score** è < 30 (ribasso) o > 70 (rialzo)
3. C'è **convergenza** tra più indicatori (flow + GEX + price action)

**Bias Rialzista (Long):**
- Prezzo vicino al **Put Wall** (supporto put gamma)
- Momentum Score < 30
- Net Flow positivo con drift in salita
- Trigger: candle di **rientro** dopo pullback al PW

**Bias Ribassista (Short):**
- Prezzo vicino al **Call Wall** (resistenza call gamma)
- Momentum Score > 70
- Net Flow negativo con drift in discesa
- Trigger: candle di **rientro** dopo rialzo al CW

### 5.2 Momentum Score — I 5 Componenti

Il Momentum Score (0-100) è un composito di:

| Componente | Peso | Descrizione |
|------------|------|-------------|
| **Flow Velocity** | 35% | EMA del net flow call-put a 5 min |
| **Price Action** | 25% | Rendimento a 15 min normalizzato |
| **GEX Positioning** | 20% | Distanza prezzo da ZGL (in sigma) |
| **Volume Ratio** | 10% | Volume attuale vs media 5 min |
| **Theta Effect** | 10% | Decadimento temporale opzioni |

**Interpretazione:**
- Score **< 20**: ipervenduto estremo — inversione rialzista probabile
- Score **20-40**: bias rialzista — cerca long
- Score **40-60**: neutrale — no posizioni directional
- Score **60-80**: bias ribassista — cerca short
- Score **> 80**: ipercomprato estremo — inversione ribassista probabile

### 5.3 Zone Alerts — Segnali di Warning

```
⚠️ ZONE ALERT: QQQ
───────────────────────
Direction: bearish
Current Price: 26881.80
Nearest Zone: 26905.92 (ZGL)
Distance: +0.09%  ← SOGLIA 0.5%
Action: REDUCE LONG
───────────────────────
```

**Logica:**
- Distance < 0.2% da ZGL → **reversal imminente**
- Distance < 0.5% da CW/PW → **consolidamento** — no entry directional
- Distance > 1% da qualsiasi livello → mercato libero, no resistenze

### 5.4 Gestione del Rischio

**Stop Loss:**
- Sempre **oltre il livello GEX** che ha innescato il trade
- Esempio: long da 7120 con PW a 7115 → stop sotto 7115

**Take Profit:**
- Al **prossimo livello GEX** significativo
- R:R minimo **3:1**

**Position Sizing:**
```
Size = (Account × 1%) / (Entry - Stop) × Contract Multiplier
```

Per ES (50$ per punto):
- Conto $50,000, rischio 1% = $500
- Distanza stop = 5 punti ES → Size = $500 / (5 × $50) = **2 contratti**

### 5.5 Cosa Evitare

1. **Non tradare in direzione opposta a un Call/Put Wall forte**
   — MM difendono questi livelli attivamente

2. **Non entrare se il prezzo è tra due livelli GEX vicini**
   — il mercato è in consolidamento, aspetta il breakout

3. **Non ignorare il Momentum Score**
   — Score < 30 + prezzo vicino PW = setup rialzista ad alta probabilità

4. **Non aggiungere a posizioni in perdita**
   — la GEX non è ancora girata a tuo favore

---

## 6. Simulazione di Trading — Esempi Pratici

### Esempio 1: Long su ES al Put Wall

**Scenario:**
- ES (US500-F): 7166
- ZGL: 7170
- Put Wall: 7115
- Momentum Score: 28 (bias rialzista)
- Net Flow: +$2.3M (positivo)
- Drift: in salita da 10 min

**Azione:**
1. Aspetta pullback verso **7115-7120**
2. Entra long a **7118** (sopra PW)
3. Stop loss: **7108** (sotto PW, 10 punti = $500)
4. Take profit: **7155** (primo target = 3:1, chiude metà)
5. Secondo target: **7170** (ZGL)

**Risk/Reward:**
- Rischio: 10 punti × $50 = **$500**
- Reward 1: 37 punti × $50 = **$1,850** (3.7:1)
- Reward 2: 52 punti × $50 = **$2,600** (5.2:1)

---

### Esempio 2: Short su NQ al Call Wall

**Scenario:**
- NQ (NAS100-F): 26853
- ZGL: 26906
- Call Wall: 26864
- Momentum Score: 75 (bias ribassista)
- Net Flow: -$1.8M (negativo)

**Azione:**
1. Aspetta rally verso **26864-26870**
2. Entra short a **26865**
3. Stop loss: **26910** (sopra ZGL, 45 punti)
4. Take profit 1: **26750** (chiude metà)
5. Secondo target: **26650** (livello strutturale)

---

## 7. Glossario

| Termine | Definizione |
|---------|------------|
| **GEX** | Gamma Exposure — misura della pressione di hedging dei market maker |
| **ZGL** | Zero Gamma Level — strike dove la GEX cumulativa è zero |
| **Call Wall** | Strike con massimo GEX positivo — resistenza dinamica |
| **Put Wall** | Strike con massimo GEX negativo — supporto dinamico |
| **0DTE** | Opzioni con scadenza lo stesso giorno (zero days to expiration) |
| **Delta** | Sensibilità del prezzo dell'opzione al sottostante |
| **Gamma** | Variazione del delta al variare del prezzo del sottostante |
| **Open Interest** | Numero contratti opzioni aperti |
| **Smart Money** | Flussi opzioni istituzionali (block trades) |
| **Flow Velocity** | Tasso di variazione del net flow nel tempo |
| **Momentum Score** | Punteggio composito 0-100 per directional bias |

---

## 8. Link e Riferimenti

- **Dashboard:** http://137.220.63.222
- **Backend API:** http://137.220.63.222:8000
- **WebSocket:** ws://137.220.63.222:8000/ws/market_data
- **cTrader:** OpenAPI per futures real-time
- **Tradier:** API per opzioni SPX/QQQ e flusso

### Credenziali VPS
```
Host: 137.220.63.222
SSH:  root / [password in password manager]
```

---

*Questa guida è stata generata per scopi educativi. Il trading di opzioni e futures comporta rischi significativi di perdita. Nessuna garanzia di profitto.*
