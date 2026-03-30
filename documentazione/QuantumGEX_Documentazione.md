# QuantumGEX - Documentazione Tecnica

## Panoramica

**QuantumGEX** è un sistema completo per il monitoraggio in tempo reale del Gamma Exposure (GEX) sui mercati futures e opzioni. Il sistema integra:

- **Dati Real-time**: cTrader OpenAPI per futures SPX (ES) e NASDAQ (NQ)
- **Dati Storici**: Scaricamento candele M1 via OpenAPI
- **GEX Profile**: Visualizzazione dei livelli GEX per 0DTE
- **Offset Dinamico**: Traduzione automatica strike → future price

---

## Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + Vite)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Lightweight  │  │ GEX Profile  │  │  Price Display   │   │
│  │ Charts       │  │ (0DTE Bars)  │  │  (Live Ticks)    │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │ WebSocket + REST API
┌────────────────────────────▼────────────────────────────────┐
│                   BACKEND (FastAPI + Uvicorn)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ /api/candles │  │ /api/gex/*   │  │ /ws/market_data  │   │
│  │ OHLCV agg    │  │ GEX profile  │  │ Real-time ticks  │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│              DATABASE (PostgreSQL + TimescaleDB)             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ futures_ticks│  │ gex_profile  │  │ options_flow     │   │
│  │ (hypertable) │  │ (daily GEX)  │  │ (trade data)     │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                             ▲
┌────────────────────────────┴────────────────────────────────┐
│                    DATA DAEMONS                              │
│  ┌──────────────────────┐  ┌──────────────────────────────┐  │
│  │ ctrader_openapi_     │  │ ctrader_history.py           │  │
│  │ daemon.py (realtime) │  │ (historical candles M1)      │  │
│  └──────────────────────┘  └──────────────────────────────┘  │
│  ┌──────────────────────┐  ┌──────────────────────────────┐  │
│  │ tradier_ingestion_   │  │ gex_calculator.py            │  │
│  │ daemon.py (SPX/QQQ)  │  │ (offset calculation)         │  │
│  └──────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Componenti Backend

### 1. `main.py` - FastAPI Server

Endpoint principali:

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/candles/{symbol}` | GET | Candele OHLCV aggregate |
| `/api/gex/latest` | GET | GEX profile (auto underlying) |
| `/api/gex/spx/latest` | GET | SPX GEX con offset additivo |
| `/api/gex/qqq/latest` | GET | QQQ GEX con offset moltiplicativo |
| `/api/symbols` | GET | Lista simboli attivi |
| `/ws/market_data` | WebSocket | Real-time tick broadcast |

### 2. `ctrader_openapi_daemon.py` - Real-time Data

**Funzione**: Riceve tick real-time da cTrader OpenAPI

**Simboli monitorati**:
- `US500-F` (ES Futures)
- `NAS100-F` (NQ Futures)

**Formato prezzi**: 1/100000 di unità (diviso per 100000)

**Output**: Inserisce tick in `futures_ticks` table

### 3. `ctrader_history.py` - Historical Data

**Funzione**: Scarica candele storiche M1 (ultime 24h)

**Esecuzione**: Manuale o via cron

```bash
python3 ctrader_history.py
```

### 4. `gex_calculator.py` - Offset Calculation

**Funzione**: Calcola offset dinamico Future - Spot

---

## Offset Dinamico

### Formula SPX (Additivo)

```
futurePrice = strike + (US500-F - US500)
```

Esempio:
- US500-F = 6823.40
- US500 = 6817.00
- Offset = +6.40
- Strike 5800 → Future 5806.40

### Formula QQQ (Moltiplicativo)

```
futurePrice = strike × (NAS100-F / QQQ)
```

Esempio:
- NAS100-F = 25005
- QQQ = 608.91
- Ratio = 41.07
- Strike 600 → Future 24642

**Nota**: I strike QQQ nel database sono in punti QQQ (450-900), non NAS100.

---

## Logica 0DTE Post-16:30 EST

Dopo la chiusura del mercato USA (16:30 EST = 21:30 UTC), il sistema mostra automaticamente il prossimo giorno di trading.

```python
def get_next_trading_day():
    # Current time in EST
    now_est = datetime.now(timezone(timedelta(hours=-5)))
    market_close = now_est.replace(hour=16, minute=30)

    if now_est > market_close:
        next_day = now_est.date() + timedelta(days=1)
        # Skip weekends
        while next_day.weekday() >= 5:  # Sat=5, Sun=6
            next_day += timedelta(days=1)
        return next_day
    return now_est.date()
```

---

## API Response Examples

### SPX GEX
```json
{
  "target_date": "2026-03-06",
  "underlying": "SPX",
  "offset": 6.4,
  "multiplier": 1.0,
  "gex": [
    {"strike": 5750, "gex": 12345678, "futurePrice": 5756.4},
    {"strike": 5800, "gex": -8765432, "futurePrice": 5806.4}
  ]
}
```

### QQQ GEX
```json
{
  "target_date": "2026-03-06",
  "underlying": "QQQ",
  "offset": 0.0,
  "multiplier": 41.07,
  "gex": [
    {"strike": 595, "gex": -15200000, "futurePrice": 24434},
    {"strike": 600, "gex": -64400000, "futurePrice": 24642}
  ]
}
```

---

## Database Schema

### `futures_ticks` (TimescaleDB Hypertable)

| Colonna | Tipo | Descrizione |
|---------|------|-------------|
| time | TIMESTAMPTZ | Timestamp del tick |
| symbol | VARCHAR(20) | Simbolo (US500-F, NAS100-F, SPX, QQQ) |
| price | DOUBLE | Prezzo |
| volume | INT | Volume |

### `gex_profile`

| Colonna | Tipo | Descrizione |
|---------|------|-------------|
| calc_date | DATE | Data calcolo |
| target_date | DATE | Data scadenza (0DTE) |
| underlying | VARCHAR(10) | SPX o QQQ |
| strike | DOUBLE | Strike price |
| total_gex | DOUBLE | Gamma Exposure totale |
| translated_future_price | DOUBLE | Prezzo future (legacy) |

---

## Server Deployment

### Systemd Services

```bash
# Status
systemctl status gex_api
systemctl status ctrader_openapi
systemctl status gex_calculator
systemctl status gex_tradier

# Restart
systemctl restart gex_api
systemctl restart ctrader_openapi
```

### File Paths

| Componente | Path |
|------------|------|
| Backend | `/opt/gex_dashboard/backend/` |
| Frontend | `/opt/gex_dashboard/frontend/` |
| Logs | `journalctl -u gex_api` |

---

## Credenziali cTrader OpenAPI

**Account**: Pepperstone Live 1105672

| Parametro | Valore |
|-----------|--------|
| CLIENT_ID | `22265_zhq1ODwNJGQLvTNO1MpyWhSJRr6Nu4cn8UgWUyRtBT1XCkRjMh` |
| CLIENT_SECRET | `w3MVKpqteYiu1KyQDgQDdibCFHqEI6lZmGlHpqm6TB8iyKIcfl` |
| ACCESS_TOKEN | `GCAIGLs0fBqAMMKDLxM10WDkweZbh_xtX_W4CTX45jY` |
| Account ID | 24915432 |

**Endpoint**: `live.ctraderapi.com:5035`

---

## Troubleshooting

### Prezzi errati (es. 68221000 invece di 6822.1)

**Causa**: I prezzi cTrader OpenAPI sono in 1/100000 di unità.

**Soluzione**: Dividere per 100000

```python
price = raw_price / 100000
```

### GEX non mostrato

1. Verificare che ci siano dati per la data target:
```sql
SELECT * FROM gex_profile WHERE target_date = CURRENT_DATE;
```

2. Verificare che l'offset sia calcolato:
```bash
curl http://137.220.63.222:8000/api/gex/spx/latest | jq '.offset'
```

### Daemon non salva tick

1. Verificare connessione DB in logs:
```bash
journalctl -u ctrader_openapi -f
```

2. Verificare che psycopg2 sia installato:
```bash
pip install psycopg2-binary
```

---

## Manutenzione

### Aggiornamento dati storici

```bash
cd /opt/gex_dashboard/backend
source venv/bin/activate
python3 ctrader_history.py
```

### Rebuild frontend

```bash
cd /opt/gex_dashboard/frontend
npm run build
```

### Backup database

```bash
pg_dump -h localhost -U postgres gex_db > backup.sql
```

---

## Version History

| Versione | Data | Modifiche |
|----------|------|-----------|
| 4.0 | 2026-03-05 | Offset dinamico, logica post-16:30, cTrader OpenAPI |
| 3.x | 2026-03-03 | FIX API daemon, correzione prezzi |
| 2.x | 2026-02-28 | GEX profile, TimescaleDB |
| 1.x | 2026-02-20 | Versione iniziale |
