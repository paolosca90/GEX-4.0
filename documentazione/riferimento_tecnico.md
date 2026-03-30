# QuantumGEX: Riferimento Tecnico e Troubleshooting

Questo documento funge da guida definitiva per comprendere l'architettura del sistema, il flusso dei dati e le procedure di intervento in caso di bug o interruzioni del servizio. 

---

## 🏗️ Architettura del Sistema

Il sistema è diviso in tre blocchi principali che devono comunicare correttamente tra loro:

### 1. Backend (FastAPI) - `backend/main.py`
È il cuore del sistema. Gestisce:
- **WebSocket (`/ws/market_data`)**: Distribuisce i tick dei futures e i flussi opzioni al frontend in tempo reale.
- **REST API**: Fornisce i dati storici delle candele e l'ultimo profilo GEX calcolato.
- **Logica di Roll 0DTE**: Determina automaticamente se mostrare la scadenza odierna o quella successiva (post 16:30 EST).

### 2. Ingestion Daemons (Python)
Processi in background che alimentano il database:
- `ctrader_openapi_daemon.py`: Riceve prezzi FX/Futures da cTrader.
- `options_flow_daemon.py`: Riceve lo streaming dei trade sulle opzioni da Tradier WebSocket.
- `gex_calculator.py`: Calcola i livelli di Gamma Exposure ogni giorno.
- `tradier_ingestion_daemon.py`: Monitora il prezzo spot di SPX/QQQ per calcolare gli offset.

### 3. Frontend (React + Vite) - `frontend/src/`
Visualizza i dati:
- `LightweightChart.tsx`: Rendering dei grafici e dei livelli GEX.
- `SmartMoneyBox.tsx`: Gestisce la logica delle Dual Bars (Premium vs Volume), l'indicatore EMA Drift 5m numerico e visuale (Conviction Gauge), e i segnali di allarme avanzati (incluso il controllo divergenze Vol/Drift).

---

## 🧠 Algoritmi Principali 

### Power Meter (Smart Money Box)
Il calcolo direzionale dello "Smart Money" nel `options_flow_daemon.py` e `flow_analyzer.py` utilizza 4 filtri avanzati:
1. **EMA Time Decay (`τ=120s`)**: Il Net Drift a 5 minuti usa un decadimento esponenziale. Le trade recenti pesano esponenzialmente di più rispetto alle trade vecchie.
2. **Block Trade Discounting**: Trades enormi (`size > 200`) vengono smorzati logaritmicamente per filtrare operazioni di puro hedging.
3. **Urgency & Distance Weighting**: Esecuzioni aggressive al Bid/Ask moltiplicano il peso x1.5. Le opzioni lontane dallo Spot (basso delta) hanno un peso ridotto.
4. **Spread Neutrality**: Se un'opzione ha uno spread esteso (`> $0.50`), i trade centrali vengono scartati. Solo i trade nel 25% vicino a Bid o Ask sono considerati.

---

## 🔄 Flusso dei Dati e Componenti Critici

| Dato | Sorgente | Componente Backend | Tabella DB |
| :--- | :--- | :--- | :--- |
| **Futures Tick** | cTrader OpenAPI | `ctrader_openapi_daemon.py` | `futures_ticks` |
| **GEX Profile** | Tradier API | `gex_calculator.py` | `gex_profile` |
| **Options Flow** | Tradier WS | `options_flow_daemon.py` | `options_flow_ticks` |
| **Spot Price** | Tradier API | `tradier_ingestion_daemon.py` | `futures_ticks` |

---

## 🛠️ Guida al Troubleshooting (Dove intervenire?)

### 1. Il grafico dei prezzi non si muove (o è "Frozen")
- **Controllo**: Verifica i log di `ctrader_openapi_daemon.py`.
- **Causa comune**: Token cTrader scaduto o connessione socket interrotta.
- **Intervento**: Riavvia il servizio `gex_ctrader` sul VPS.

### 2. I livelli GEX (barre orizzontali) mancano o sono errati
- **Controllo**: Esegui `SELECT * FROM gex_profile WHERE target_date = CURRENT_DATE;`.
- **Causa comune**: Il calcolatore GEX non è partito alle 16:30 EST o c'è un errore di offset (prezzo Spot vs Future).
- **Intervento**: Controlla `gex_calculator.py` e la logica di `get_dynamic_offset()` in `main.py`.

### 3. Smart Money Box non mostra segnali o barre fisse al 50%
- **Controllo**: Verifica il flusso WebSocket nel browser (Tab Network -> WS).
- **Causa comune**: `options_flow_daemon.py` non sta inviando tick di tipo `flow_tick`.
- **Intervento**: Verifica le credenziali Tradier e se il mercato USA è aperto.

### 4. Errore di connessione al Database
- **Controllo**: `journalctl -u gex_api -f`.
- **Causa comune**: Troppe connessioni aperte o servizio Postgres fermo.
- **Intervento**: Verifica `backend/db.py` e assicurati che il connection pool sia gestito correttamente.

---

## 🚀 Procedure di Emergenza sul VPS

Se il sistema è completamente offline, segui questo ordine di riavvio:

1. **Database**: `systemctl restart postgresql`
2. **API Centrale**: `systemctl restart gex_api`
3. **Daemons di Ingestione**: 
   - `systemctl restart gex_ctrader`
   - `systemctl restart gex_tradier`
   - `systemctl restart gex_calculator`

---

## 📝 Note sullo Sviluppo Futuro
- **Aggiunta Simboli**: Modificare la mappa in `CLAUDE.md` e aggiungere il monitoraggio in `ctrader_openapi_daemon.py`.
- **Nuovi Segnali**: La logica dei segnali è interamente contenuta in `SmartMoneyBox.tsx:processTick()`.
