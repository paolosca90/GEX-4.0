# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GEX Dashboard 4.0 is a real-time options gamma exposure monitoring system. It displays:
- **Futures candlestick charts** (ES/NQ) with real-time ticks via cTrader OpenAPI
- **GEX Profile** (0DTE gamma exposure levels) from Tradier API
- **Smart Money Power Meter** (net call/put flow and drift) from Tradier WebSocket
- **Momentum Score** (composite reversal signal with 5 components)
- **Zone Alerts** (proximity to high-probability reversal zones)

## Build Commands

### Frontend (React + Vite + TypeScript)
```bash
cd frontend
npm install
npm run dev      # Development server
npm run build    # Production build to frontend/dist/
```

### Backend (FastAPI + Python)
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn asyncpg psycopg2-binary websockets httpx python-dotenv ctrader-open-api twisted
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Project Structure

```
GEX 4.0/
├── CLAUDE.md
├── .deploy_vps.py                 # Full deploy (tar + SSH + systemd + nginx)
├── .deploy_frontend.py            # Frontend-only deploy
├── backend/
│   ├── main.py                    # FastAPI server (REST + WebSocket + broadcast)
│   ├── db.py                      # Database connection and schema (6 tables)
│   ├── ctrader_openapi_daemon.py  # Real-time futures ticks via cTrader OpenAPI
│   ├── ctrader_ingestion_daemon.py# cTrader ingestion (Twisted)
│   ├── options_flow_daemon.py     # Options flow from Tradier WS (EMA, OTM filter, bulk INSERT)
│   ├── gex_calculator.py          # Daily GEX profile calculation
│   ├── tradier_ingestion_daemon.py# SPX/QQQ spot prices from Tradier
│   └── flow_analyzer.py           # Momentum score composito (5 components)
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── App.tsx                 # Main React component, WebSocket, ChartPanel
        ├── App.css                 # Styles
        ├── main.tsx                # Entry point
        ├── index.css               # Global styles
        └── components/
            ├── LightweightChart.tsx # Candlestick chart with GEX overlays + heatmap
            ├── GexProfile.tsx       # GEX bars aligned to chart price axis
            └── SmartMoneyBox.tsx    # Draggable power meter overlay
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  FRONTEND (React + Vite)                    │
│  App.tsx → ChartPanel → [LightweightChart, SmartMoneyBox]  │
└───────────────────────────┬─────────────────────────────────┘
                            │ WebSocket (/ws/market_data) + REST API
┌───────────────────────────▼─────────────────────────────────┐
│                BACKEND (FastAPI + Uvicorn)                  │
│  main.py: REST endpoints + WebSocket broadcast              │
│  flow_analyzer.py: Momentum score engine                    │
└───────────────────────────┬─────────────────────────────────┘
                            │ asyncpg
┌───────────────────────────▼─────────────────────────────────┐
│           DATABASE (PostgreSQL + TimescaleDB)               │
│  Tables: futures_ticks, gex_profile, options_flow,         │
│          options_flow_ticks, options_flow_1m,               │
│          gex_level_interactions                             │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                     DATA DAEMONS                            │
│  ctrader_openapi_daemon.py → Real-time futures ticks       │
│  ctrader_ingestion_daemon.py→ cTrader ingestion (Twisted)  │
│  options_flow_daemon.py    → Options flow from Tradier WS  │
│  gex_calculator.py         → Daily GEX profile calculation │
│  tradier_ingestion_daemon.py → SPX/QQQ spot prices         │
└─────────────────────────────────────────────────────────────┘
```

## Key Data Flows

1. **Futures Ticks**: cTrader OpenAPI → `ctrader_openapi_daemon.py` → `futures_ticks` table → WebSocket broadcast
2. **GEX Profile**: Tradier API → `gex_calculator.py` (runs at 16:30 EST) → `gex_profile` table → `/api/gex/latest`
3. **Options Flow**: Tradier WebSocket → `options_flow_daemon.py` → `options_flow_ticks` + `options_flow_1m` tables → WebSocket broadcast
4. **Momentum Score**: `flow_analyzer.py` → composite of flow velocity (35%), price action (25%), GEX positioning (20%), volume ratio (10%), theta effect (10%)

## Symbol Mapping

| Chart Symbol (Futures) | Underlying (GEX/Flow) |
|------------------------|----------------------|
| US500-F                | SPX                  |
| NAS100-F               | QQQ                  |

The frontend maps futures symbols to underlyings for GEX and Smart Money data.

## GEX Offset Calculation

The system translates strike prices to future prices:
- **SPX (Additive)**: `futurePrice = strike + (US500-F - SPX)`
- **QQQ (Multiplicative)**: `futurePrice = strike × (NAS100-F / QQQ)`

Computed dynamically in `main.py:get_dynamic_offset()` with fallback to cTrader cash CFD if Tradier spot is stale (>5min).

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/candles/{symbol}` | OHLCV candles (1m, 5m, 15m) |
| GET | `/api/gex/latest` | GEX profile with dynamic offset |
| GET | `/api/gex/spx/latest` | SPX GEX |
| GET | `/api/gex/qqq/latest` | QQQ GEX |
| GET | `/api/flow` | Options flow ticks |
| GET | `/api/flow/{symbol}` | Flow per underlying |
| GET | `/api/symbols` | Active symbols with latest price |
| GET | `/api/market-watch` | Options metrics (IV, volume, ATM) |
| GET | `/api/momentum/{underlying}` | Composite momentum score (0-100) |
| GET | `/api/momentum/zone-alert/{underlying}` | Zone proximity alert + direction |
| GET | `/api/levels/previous-day` | Previous day HLC |
| GET | `/api/levels/initial-balance` | IB (09:30-11:00 ET) |
| GET | `/api/levels/reliability` | GEX level bounce reliability |
| POST | `/api/ingest/tick` | Tick ingestion (Sierra Chart) |
| WS | `/ws/market_data` | Real-time tick + flow broadcast |

## Database Schema

- `futures_ticks` (hypertable): time, symbol, price, volume
- `options_flow` (hypertable): individual option trades with sentiment, strike, weights
- `options_flow_ticks` (hypertable): 2-second aggregated flow (1m sums + 5m EMA drift)
- `options_flow_1m` (hypertable): 1-minute aggregated flow
- `gex_profile`: calc_date, target_date, underlying, strike, total_gex, translated_future_price
- `gex_level_interactions` (hypertable): historical level touches and bounce results

## Options Flow Algorithm

The `options_flow_daemon.py` applies these filters/weights:
1. **OTM Filter**: Ignores ITM options (delta ≈ 1, adds noise)
2. **Block Trade Discount**: Logarithmic dampening for trades >200 contracts
3. **Urgency Weight**: 1.5x aggressive (at bid/ask), 0.8x mid-leaning
4. **Distance-to-Spot**: Linear dropoff from ATM (1.0) to 10% OTM (0.1)
5. **EMA Time Decay**: tau=120s for 5m net drift calculation
6. **Spread Neutrality**: Wide spread (> $0.50) mid-zone trades → NONE

## Deployment (Vultr VPS)

Server: `137.220.63.222` (see deploy scripts for credentials)

```bash
# Systemd services on VPS
systemctl status gex_api gex_ctrader gex_tradier

# Quick frontend deploy
cd frontend && npm run build
scp dist/* root@137.220.63.222:/opt/gex_dashboard/frontend/dist/

# Full deploy
python3 .deploy_vps.py
```

## cTrader OpenAPI Price Format

Prices from cTrader are in 1/100000 of a unit. Always divide by 100000:
```python
price = raw_price / 100000
```

## 0DTE Date Logic

After 16:30 EST (market close), the system automatically shows the next trading day's 0DTE options. See `main.py:get_next_trading_day()`.
