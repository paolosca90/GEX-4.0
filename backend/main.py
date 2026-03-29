from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from greeks_service import GreeksService
from alert_engine import AlertEngine
from darkpool_analyzer import DarkPoolAnalyzer
from reversal_engine import ReversalEngine
from oi_tracker import OITracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gex_backend")

app = FastAPI(title="GEX & Options Flow Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:5173", "http://127.0.0.1:5173"],  # Dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────── DB Pool ────────────────────────────
db_pool = None
greeks_service = None
alert_engine = None
darkpool_analyzer = None
reversal_engine = None
oi_tracker = None

@app.on_event("startup")
async def startup_event():
    global db_pool
    from db import init_db, get_db_pool
    try:
        await init_db()
        db_pool = await get_db_pool()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Could not init DB: {e}")

    # Start the background tick broadcaster
    asyncio.create_task(broadcast_ticks())
    asyncio.create_task(broadcast_flow_ticks())
    # Start the GEX calculation engine
    from gex_calculator import start_gex_engine
    asyncio.create_task(start_gex_engine())

    # Initialize institutional MVP services
    global greeks_service, alert_engine, darkpool_analyzer, reversal_engine, oi_tracker
    greeks_service = GreeksService(db_pool)
    alert_engine = AlertEngine(db_pool, broadcast_fn=manager.broadcast)
    darkpool_analyzer = DarkPoolAnalyzer(db_pool)
    reversal_engine = ReversalEngine(db_pool)
    oi_tracker = OITracker(db_pool)
    asyncio.create_task(darkpool_analyzer.update_daily())
    asyncio.create_task(broadcast_reversal_signals())
    asyncio.create_task(snapshot_oi_every_30min())


# ──────────────────────────── WebSocket Manager ────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message)
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_text(payload)
            except Exception as e:
                logger.warning(f"Failed to send to client, removing: {e}")
                dead.append(conn)
        for d in dead:
            self.disconnect(d)

manager = ConnectionManager()


# ──────────────────────────── Background Tick Broadcaster ─────────────────
last_broadcast_time = None

async def broadcast_ticks():
    """Poll DB for new ticks every 500ms and broadcast to all WS clients."""
    global last_broadcast_time, db_pool
    await asyncio.sleep(2)  # wait for startup

    last_broadcast_time = datetime.now(timezone.utc)

    while True:
        try:
            if db_pool and manager.active_connections:
                rows = await db_pool.fetch('''
                    SELECT time, symbol, price, volume 
                    FROM futures_ticks 
                    WHERE time > $1
                    ORDER BY time ASC
                    LIMIT 50
                ''', last_broadcast_time)

                for row in rows:
                    msg = {
                        "type": "tick",
                        "symbol": row["symbol"],
                        "price": float(row["price"]),
                        "volume": int(row["volume"]),
                        "time": row["time"].isoformat(),
                    }
                    await manager.broadcast(msg)
                    if alert_engine:
                        await alert_engine.evaluate_tick(row["symbol"], float(row["price"]))
                    last_broadcast_time = row["time"]

        except Exception as e:
            logger.error(f"Broadcast error: {e}")

        await asyncio.sleep(0.5)


# ──────────────────────────── Background Flow Tick Broadcaster ─────────────────
last_flow_broadcast_time = None

async def broadcast_flow_ticks():
    """Poll DB for new options flow ticks every 2s and broadcast to all WS clients."""
    global last_flow_broadcast_time, db_pool
    await asyncio.sleep(3)  # wait for startup

    last_flow_broadcast_time = datetime.now(timezone.utc)

    while True:
        try:
            if db_pool and manager.active_connections:
                rows = await db_pool.fetch('''
                    SELECT
                        time,
                        underlying,
                        call_premium,
                        put_premium,
                        call_volume,
                        put_volume,
                        net_drift
                    FROM options_flow_ticks
                    WHERE time > $1
                    ORDER BY time ASC
                    LIMIT 20
                ''', last_flow_broadcast_time)

                for row in rows:
                    msg = {
                        "type": "flow_tick",
                        "symbol": row["underlying"],
                        "time": row["time"].isoformat(),
                        "call_premium": float(row["call_premium"] or 0),
                        "put_premium": float(row["put_premium"] or 0),
                        "call_volume": int(row["call_volume"] or 0),
                        "put_volume": int(row["put_volume"] or 0),
                        "net_drift": float(row["net_drift"] or 0),
                    }
                    await manager.broadcast(msg)
                    if alert_engine:
                        await alert_engine.evaluate_flow(
                            row["underlying"],
                            float(row["net_drift"] or 0),
                            float(row["call_premium"] or 0),
                            float(row["put_premium"] or 0)
                        )
                    last_flow_broadcast_time = row["time"]

        except Exception as e:
            logger.error(f"Flow broadcast error: {e}")

        await asyncio.sleep(2)


# ──────────────────────────── Background Reversal Signal Broadcaster ─────────────────
async def _fetch_price_and_signal(underlying: str, futures_sym: str):
    """Fetch latest price and compute reversal signal for one underlying."""
    price_row = await db_pool.fetchrow('''
        SELECT price FROM futures_ticks
        WHERE symbol = $1 AND time > NOW() - INTERVAL '5 minutes'
        ORDER BY time DESC LIMIT 1
    ''', futures_sym)
    if not price_row:
        return None
    current_price = float(price_row["price"])
    signal = await reversal_engine.get_reversal_signal(underlying, futures_sym, current_price)
    return {"type": "reversal_signal", **signal}


async def broadcast_reversal_signals():
    """Compute and broadcast reversal signals every 5 seconds."""
    global reversal_engine, db_pool
    await asyncio.sleep(5)  # wait for startup

    while True:
        try:
            if db_pool and reversal_engine and manager.active_connections:
                # Parallel DB query + signal computation for both underlyings
                results = await asyncio.gather(
                    _fetch_price_and_signal("SPX", "US500-F"),
                    _fetch_price_and_signal("QQQ", "NAS100-F"),
                )
                for signal in results:
                    if signal is None:
                        continue
                    await manager.broadcast(signal)
                    # Fire alert if confluence > 70 and direction is not NEUTRAL
                    if alert_engine and signal["confluence"] >= 70 and signal["direction"] != "NEUTRAL":
                        await alert_engine.fire_reversal_alert(signal)
        except Exception as e:
            logger.error(f"Reversal broadcast error: {e}")
        await asyncio.sleep(5)


async def snapshot_oi_every_30min():
    """Snapshot OI every 30 minutes during RTH (9:30-16:00 ET)."""
    global oi_tracker, db_pool
    await asyncio.sleep(10)  # wait for startup

    while True:
        try:
            now_et = datetime.now(timezone(timedelta(hours=-5)))
            hour = now_et.hour
            # Only run during RTH: 9:30-16:00 ET (14:30-20:00 UTC)
            if 14 <= hour < 20 and oi_tracker and db_pool:
                await oi_tracker.snapshot_and_store("SPX")
                await oi_tracker.snapshot_and_store("QQQ")
                logger.info("OI snapshot completed for SPX and QQQ")
        except Exception as e:
            logger.error(f"OI snapshot error: {e}")
        await asyncio.sleep(1800)  # 30 minutes


# ──────────────────────────── REST Endpoints ────────────────────────────
@app.get("/")
def read_root():
    return {"status": "ok", "message": "GEX Backend is running"}


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    db_ok = False
    try:
        if db_pool:
            await db_pool.fetchval("SELECT 1")
            db_ok = True
    except Exception:
        pass
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check - returns 503 if not ready to serve traffic."""
    if not db_pool:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database not ready")
    return {"ready": True}


@app.post("/api/ingest/tick")
async def ingest_tick(data: dict):
    """
    Ingest a real-time tick from Sierra Chart.
    Payload: {"symbol": "ES", "price": 5100.25, "volume": 10}
    """
    if not db_pool:
        return {"status": "error", "message": "DB not connected"}
    
    symbol = data.get("symbol")
    price = data.get("price")
    volume = data.get("volume", 0)

    # Map SC symbols back to our DB nomenclature if necessary
    # e.g. ESM24 -> US500-F
    symbol_map = {
        "ES": "US500-F",
        "NQ": "NAS100-F",
        "SPX": "SPX",
        "QQQ": "QQQ"
    }
    mapped_symbol = symbol_map.get(symbol, symbol)

    try:
        await db_pool.execute('''
            INSERT INTO futures_ticks (time, symbol, price, volume)
            VALUES (NOW(), $1, $2, $3)
        ''', mapped_symbol, float(price), int(volume))
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/symbols")
async def get_symbols():
    """Return list of active symbols with latest price and tick count."""
    if not db_pool:
        return {"symbols": []}
    rows = await db_pool.fetch('''
        SELECT symbol, 
               COUNT(*) as tick_count,
               MAX(price) as last_price,
               MAX(time) as last_tick
        FROM futures_ticks
        WHERE time > NOW() - INTERVAL '1 hour'
        GROUP BY symbol
        ORDER BY symbol
    ''')
    return {"symbols": [dict(r) for r in rows]}


@app.get("/api/flow")
async def get_options_flow(
    symbols: str = Query("SPX,QQQ", description="Comma-separated list of underlyings"),
    limit: int = Query(50, description="Max ticks to return per symbol"),
):
    """Return latest options flow ticks for Smart Money Power Meter."""
    if not db_pool:
        return {"flow": [], "message": "DB not connected"}

    symbol_list = [s.strip().upper() for s in symbols.split(",")]

    rows = await db_pool.fetch('''
        SELECT
            EXTRACT(EPOCH FROM time) as epoch,
            time,
            underlying,
            call_premium,
            put_premium,
            call_volume,
            put_volume,
            net_drift
        FROM options_flow_ticks
        WHERE underlying = ANY($1)
        ORDER BY time DESC
        LIMIT $2
    ''', symbol_list, limit * len(symbol_list))

    flow_data = []
    for r in rows:
        flow_data.append({
            "epoch": float(r["epoch"]),
            "time": r["time"].isoformat(),
            "underlying": r["underlying"],
            "call_premium": float(r["call_premium"] or 0),
            "put_premium": float(r["put_premium"] or 0),
            "call_volume": int(r["call_volume"] or 0),
            "put_volume": int(r["put_volume"] or 0),
            "net_drift": float(r["net_drift"] or 0),
        })

    return {"flow": flow_data}


@app.get("/api/flow/{symbol}")
async def get_options_flow_by_symbol(
    symbol: str,
    limit: int = Query(50, description="Max ticks to return"),
):
    """Return latest options flow ticks for a single underlying."""
    if not db_pool:
        return {"flow": [], "message": "DB not connected"}

    symbol = symbol.upper()

    rows = await db_pool.fetch('''
        SELECT
            EXTRACT(EPOCH FROM time) as epoch,
            time,
            underlying,
            call_premium,
            put_premium,
            call_volume,
            put_volume,
            net_drift
        FROM options_flow_ticks
        WHERE underlying = $1
        ORDER BY time DESC
        LIMIT $2
    ''', symbol, limit)

    flow_data = []
    for r in rows:
        flow_data.append({
            "epoch": float(r["epoch"]),
            "time": r["time"].isoformat(),
            "underlying": r["underlying"],
            "call_premium": float(r["call_premium"] or 0),
            "put_premium": float(r["put_premium"] or 0),
            "call_volume": int(r["call_volume"] or 0),
            "put_volume": int(r["put_volume"] or 0),
            "net_drift": float(r["net_drift"] or 0),
        })

    return {"flow": flow_data}


@app.get("/api/flow/concentration/{underlying}")
async def get_flow_concentration(
    underlying: str,
    bars: int = Query(5, description="Top N levels per side"),
    lookback_minutes: int = Query(60, description="Lookback window in minutes"),
):
    """
    Aggregate options_flow by strike to find concentration levels.
    Returns top call and put concentration levels where institutional flow is heaviest.
    Not true darkpool — aggregates our Tradier flow data by strike.
    """
    if not db_pool:
        return {"error": "DB not connected"}

    underlying = underlying.upper()
    if underlying not in ("SPX", "QQQ"):
        return {"error": "Invalid underlying"}

    try:
        rows = await db_pool.fetch('''
            SELECT
                strike,
                option_type,
                SUM(trade_premium) AS total_premium,
                SUM(trade_size) AS total_volume,
                COUNT(*) AS trade_count
            FROM options_flow
            WHERE underlying = $1
              AND time > NOW() - make_interval(mins => $2)
            GROUP BY strike, option_type
            ORDER BY strike
        ''', underlying, lookback_minutes)
    except Exception as e:
        logger.error(f"Flow concentration query error: {e}")
        return {"underlying": underlying, "concentration": [], "updated_at": None, "error": str(e)}

    if not rows:
        return {"underlying": underlying, "concentration": [], "updated_at": None}

    # Aggregate by strike
    strike_data: dict[float, dict] = {}
    for r in rows:
        strike = float(r["strike"])
        opt_type = r["option_type"].upper()
        premium = float(r["total_premium"] or 0)
        volume = int(r["total_volume"] or 0)

        if strike not in strike_data:
            strike_data[strike] = {"call_premium": 0.0, "put_premium": 0.0, "call_volume": 0, "put_volume": 0}

        if opt_type == "CALL":
            strike_data[strike]["call_premium"] += premium
            strike_data[strike]["call_volume"] += volume
        else:
            strike_data[strike]["put_premium"] += premium
            strike_data[strike]["put_volume"] += volume

    # Build concentration list
    concentration = []
    for strike, data in strike_data.items():
        call_p = data["call_premium"]
        put_p = data["put_premium"]
        net = call_p - put_p
        if call_p > 0 or put_p > 0:
            concentration.append({
                "strike": strike,
                "call_premium": round(call_p, 0),
                "put_premium": round(put_p, 0),
                "net_premium": round(net, 0),
                "call_volume": data["call_volume"],
                "put_volume": data["put_volume"],
                "dominant": "call" if call_p > put_p else "put",
            })

    # Sort by absolute premium and take top N per side
    call_sorted = sorted([c for c in concentration if c["dominant"] == "call"],
                         key=lambda x: x["call_premium"], reverse=True)[:bars]
    put_sorted = sorted([c for c in concentration if c["dominant"] == "put"],
                        key=lambda x: x["put_premium"], reverse=True)[:bars]

    # Merge, sort by strike
    all_levels = sorted(call_sorted + put_sorted, key=lambda x: x["strike"])

    return {
        "underlying": underlying,
        "concentration": all_levels,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/candles/{symbol}")
async def get_candles(
    symbol: str,
    interval: str = Query("1m", description="Candle interval: 1m, 5m, 15m"),
    limit: int = Query(500, description="Max candles to return"),
):
    """Aggregate ticks into OHLCV candles from the database."""
    if not db_pool:
        return {"candles": []}

    # Map interval string to minutes
    interval_mins = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
    mins = interval_mins.get(interval, 1)
    td = timedelta(minutes=mins)

    rows = await db_pool.fetch('''
        SELECT 
            time_bucket($1, time) AS bucket,
            (array_agg(price ORDER BY time ASC))[1] AS open,
            MAX(price) AS high,
            MIN(price) AS low,
            (array_agg(price ORDER BY time DESC))[1] AS close,
            SUM(volume) AS volume
        FROM futures_ticks
        WHERE symbol = $2
          AND time > NOW() - INTERVAL '72 hours'
        GROUP BY bucket
        ORDER BY bucket DESC
        LIMIT $3
    ''', td, symbol, limit)

    candles = []
    for r in reversed(rows):
        candles.append({
            "time": int(r["bucket"].timestamp()),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": int(r["volume"] or 0),
        })

    return {"candles": candles, "symbol": symbol, "interval": interval}


@app.get("/api/levels/previous-day")
async def get_previous_day_levels(
    symbol: str = Query(..., description="Symbol like US500-F or NAS100-F"),
):
    """
    Get previous trading day's high, low, and close for a symbol.
    Used for key S/R levels on the chart.
    """
    if not db_pool:
        return {"high": None, "low": None, "close": None}

    # Get previous trading day (skip weekends)
    today = datetime.now(timezone.utc).date()
    prev_day = today - timedelta(days=1)
    while prev_day.weekday() >= 5:  # Skip Sat/Sun
        prev_day -= timedelta(days=1)

    # Query for previous day HLC using time_bucket
    rows = await db_pool.fetch('''
        SELECT
            time_bucket('1 day', time) AS bucket,
            MAX(price) AS high,
            MIN(price) AS low,
            (array_agg(price ORDER BY time DESC))[1] AS close
        FROM futures_ticks
        WHERE symbol = $1
          AND time >= $2::date
          AND time < $3::date
        GROUP BY bucket
    ''', symbol, prev_day, today)

    if not rows:
        return {"high": None, "low": None, "close": None, "date": str(prev_day)}

    r = rows[0]
    return {
        "high": float(r["high"]),
        "low": float(r["low"]),
        "close": float(r["close"]),
        "date": str(prev_day),
    }


@app.get("/api/levels/initial-balance")
async def get_initial_balance(
    symbol: str = Query(..., description="Symbol like US500-F or NAS100-F"),
):
    """
    Get today's Initial Balance (first 1.5 hours of RTH: 09:30-11:00 ET).
    Returns high, low of the IB window.
    """
    if not db_pool:
        return {"high": None, "low": None}

    # RTH starts at 14:30 UTC (09:30 ET)
    # IB window is first 1.5 hours = 90 minutes
    rth_start = datetime.now(timezone.utc).replace(hour=14, minute=30, second=0, microsecond=0)
    ib_end = rth_start + timedelta(minutes=90)

    rows = await db_pool.fetch('''
        SELECT MAX(price) AS high, MIN(price) AS low
        FROM futures_ticks
        WHERE symbol = $1
          AND time >= $2
          AND time <= $3
    ''', symbol, rth_start, ib_end)

    if not rows:
        return {"high": None, "low": None, "start": str(rth_start), "end": str(ib_end)}

    r = rows[0]
    return {
        "high": float(r["high"]) if r["high"] else None,
        "low": float(r["low"]) if r["low"] else None,
        "start": str(rth_start),
        "end": str(ib_end),
    }


@app.get("/api/levels/reliability")
async def get_level_reliability(
    underlying: str = Query(..., description="Underlying: SPX or QQQ"),
    limit: int = Query(10, description="Max levels to return"),
):
    """
    Get historical reliability stats for GEX levels.
    Returns bounce rate based on recent interactions.
    """
    if not db_pool:
        return {"levels": []}

    rows = await db_pool.fetch('''
        SELECT
            level_price,
            COUNT(*) as touch_count,
            SUM(CASE WHEN bounce_result = 'BOUNCED' THEN 1 ELSE 0 END) as bounce_count,
            AVG(gex_magnitude) as avg_gex
        FROM gex_level_interactions
        WHERE underlying = $1
          AND time > NOW() - INTERVAL '7 days'
        GROUP BY level_price
        ORDER BY avg_gex DESC
        LIMIT $2
    ''', underlying.upper(), limit)

    result = []
    for row in rows:
        touch_count = row['touch_count']
        bounce_count = row['bounce_count'] or 0
        reliability = (bounce_count / touch_count * 100) if touch_count > 0 else 0

        result.append({
            "level_price": float(row["level_price"]),
            "touch_count": touch_count,
            "bounce_count": bounce_count,
            "reliability": round(reliability, 1),
            "avg_gex": float(row["avg_gex"]),
        })

    return {"levels": result, "underlying": underlying.upper()}


def get_next_trading_day():
    """
    Get the next trading day. Always skips weekends.
    Market is closed Sat/Sun, so we always return the next Monday
    regardless of whether it's before or after market close.
    """
    est = timezone(timedelta(hours=-5))
    now_est = datetime.now(est)
    target = now_est.date()
    # Skip weekend days
    while target.weekday() >= 5:
        target += timedelta(days=1)
    return target


async def get_dynamic_offset(underlying: str):
    """
    Calculate dynamic offset for translating strike to future price.

    For SPX: offset = US500-F - US500 (additive)
    For QQQ: ratio = NAS100-F / QQQ (multiplicative, since QQQ strikes are in QQQ points)

    Returns (offset, multiplier) tuple.
    """
    if not db_pool:
        return (0.0, 1.0)

    # Map underlying to future and spot/index symbols
    symbol_map = {
        'SPX': ('US500-F', 'SPX', 'US500', 'additive'),         # ES future - SPX index (Tradier real spot) - Fallback: cTrader US500
        'QQQ': ('NAS100-F', 'QQQ', 'NAS100', 'multiplicative'),  # NQ future / QQQ ratio - Fallback: cTrader NAS100
    }

    if underlying not in symbol_map:
        return (0.0, 1.0)

    future_sym, spot_sym, fallback_spot_sym, mode = symbol_map[underlying]

    try:
        # Get latest future price (last 24h to ensure fresh data)
        future_row = await db_pool.fetchrow('''
            SELECT price FROM futures_ticks
            WHERE symbol = $1 AND time > NOW() - INTERVAL '24 hours'
            ORDER BY time DESC LIMIT 1
        ''', future_sym)

        # Get latest spot/index price from Tradier ingestion (try strictly fresh = 5 minutes)
        # If Tradier is dead, we want to immediately fallback, hence the 5-minute constraint.
        spot_row = await db_pool.fetchrow('''
            SELECT price FROM futures_ticks
            WHERE symbol = $1 AND time > NOW() - INTERVAL '5 minutes'
            ORDER BY time DESC LIMIT 1
        ''', spot_sym)

        if future_row:
            future_price = float(future_row['price'])
            spot_price = None
            source_sym = spot_sym

            if spot_row:
                spot_price = float(spot_row['price'])
            else:
                # For multiplicative mode (QQQ): we need QQQ spot, NOT NAS100-CFD.
                # If QQQ fresh (5min) is unavailable, try to get ANY QQQ from last 24h.
                # The cTrader NAS100-CFD is NOT a valid substitute for QQQ in multiplicative mode.
                if mode == 'multiplicative':
                    any_qqq_row = await db_pool.fetchrow('''
                        SELECT price FROM futures_ticks
                        WHERE symbol = $1 AND time > NOW() - INTERVAL '24 hours'
                        ORDER BY time DESC LIMIT 1
                    ''', spot_sym)
                    if any_qqq_row:
                        spot_price = float(any_qqq_row['price'])
                        source_sym = spot_sym
                        logger.debug(f"Using stale QQQ price {spot_price} for {underlying} multiplier")
                if spot_price is None:
                    # Fallback to cTrader Cash CFD spot (only for additive mode, e.g. SPX)
                    fallback_row = await db_pool.fetchrow('''
                        SELECT price FROM futures_ticks
                        WHERE symbol = $1 AND time > NOW() - INTERVAL '24 hours'
                        ORDER BY time DESC LIMIT 1
                    ''', fallback_spot_sym)
                    if fallback_row:
                        spot_price = float(fallback_row['price'])
                        source_sym = fallback_spot_sym
                        logger.debug(f"Using fallback cTrader Spot {fallback_spot_sym} for {underlying}")

            if spot_price is not None:
                if mode == 'additive':
                    offset = future_price - spot_price
                    # Calculate exactly: US500-F - SPX = Offset
                    logger.info(f"Dynamic offset for {underlying}: {future_sym}({future_price:.2f}) - {source_sym}({spot_price:.2f}) = +{offset:.2f} (additive)")
                    return (offset, 1.0)
                else:  # multiplicative
                    ratio = future_price / spot_price
                    logger.info(f"Dynamic ratio for {underlying}: {future_sym}({future_price:.2f}) / {source_sym}({spot_price:.2f}) = x{ratio:.4f} (multiplicative)")
                    return (0.0, ratio)
            else:
                logger.warning(f"Missing BOTH Tradier Spot and Fallback Spot for {underlying}")
        else:
            logger.warning(f"Missing Future price data for {underlying}")
    except Exception as e:
        logger.error(f"Error calculating offset: {e}")

    # Hardcoded fallback for QQQ when all data is stale (e.g., weekend with no QQQ data).
    # NAS100-F / QQQ ≈ 41.4 (e.g., 23274 / 562 ≈ 41.4)
    if underlying == 'QQQ':
        logger.warning(f"Using hardcoded QQQ ratio 41.4 as last resort")
        return (0.0, 41.4)

    return (0.0, 1.0)


@app.get("/api/gex/latest")
async def get_gex_latest(underlying: str = Query(None, description="Filter by underlying (SPX, QQQ)")):
    """
    Return the latest GEX profile.
    - Before 16:30 EST: show today's 0DTE
    - After 16:30 EST: show next trading day's 0DTE
    - Apply dynamic offset (Future - Spot) to strikes
    """
    if not db_pool:
        return {"gex": [], "message": "DB not connected"}

    # Determine target date based on market hours
    target_date = get_next_trading_day()
    
    # Check if we specifically lack data for target_date
    check_query = "SELECT 1 FROM gex_profile WHERE target_date = $1 LIMIT 1"
    if not await db_pool.fetchval(check_query, target_date):
        # Fallback: try to find the closest available date
        # First try dates <= target_date (past or today)
        fallback_row = await db_pool.fetchrow('''
            SELECT MAX(target_date) as max_date
            FROM gex_profile
            WHERE target_date <= $1
        ''', target_date)
        if fallback_row and fallback_row['max_date']:
            logger.info(f"No GEX for {target_date}, falling back to {fallback_row['max_date']}")
            target_date = fallback_row['max_date']
        else:
            # If no past data, try to find the next available date (e.g., weekend -> Monday)
            fallback_row = await db_pool.fetchrow('''
                SELECT MIN(target_date) as min_date
                FROM gex_profile
                WHERE target_date > $1
            ''', target_date)
            if fallback_row and fallback_row['min_date']:
                logger.info(f"No GEX for {target_date}, using next available: {fallback_row['min_date']}")
                target_date = fallback_row['min_date']

    # Build query with optional underlying filter
    if underlying:
        rows = await db_pool.fetch('''
            SELECT strike, total_gex, underlying, target_date
            FROM gex_profile
            WHERE target_date = $1 AND underlying = $2
            ORDER BY strike ASC
        ''', target_date, underlying.upper())
    else:
        rows = await db_pool.fetch('''
            SELECT strike, total_gex, underlying, target_date
            FROM gex_profile
            WHERE target_date = $1
            ORDER BY underlying, strike ASC
        ''', target_date)

    if not rows:
        return {"gex": [], "message": f"No GEX data available for {target_date}"}

    # Get underlying from first row
    row_underlying = rows[0]["underlying"]

    # Calculate dynamic offset (returns offset, multiplier)
    offset, multiplier = await get_dynamic_offset(row_underlying)

    # Calculate future price: strike * multiplier + offset
    gex_data = [
        {
            "strike": float(r["strike"]),
            "gex": float(r["total_gex"]),
            "futurePrice": float(r["strike"]) * multiplier + offset,
        }
        for r in rows
        if r["underlying"] == row_underlying  # Only return data for one underlying
    ]

    # Calculate key levels
    # 1. Zero Gamma Level (ZGL): price where cumulative GEX is minimized
    sorted_levels = sorted(gex_data, key=lambda x: x["futurePrice"])
    cumulative = 0
    min_cumulative = float("inf")
    zgl = sorted_levels[len(sorted_levels) // 2]["futurePrice"]
    for level in sorted_levels:
        cumulative += level["gex"]
        if cumulative < min_cumulative:
            min_cumulative = cumulative
            zgl = level["futurePrice"]

    # 2. Call Wall: maximum positive gex
    call_levels = [level for level in gex_data if level["gex"] > 0]
    if call_levels:
        call_wall_level = max(call_levels, key=lambda x: x["gex"])
        call_wall = {
            "price": call_wall_level["futurePrice"],
            "gex": call_wall_level["gex"],
            "label": "Call Wall",
            "type": "call"
        }
    else:
        call_wall = None

    # 3. Put Wall: minimum (most negative) gex
    put_levels = [level for level in gex_data if level["gex"] < 0]
    if put_levels:
        put_wall_level = min(put_levels, key=lambda x: x["gex"])
        put_wall = {
            "price": put_wall_level["futurePrice"],
            "gex": put_wall_level["gex"],
            "label": "Put Wall",
            "type": "put"
        }
    else:
        put_wall = None

    # 4. Top Call GEX #2: second-highest positive gex
    if len(call_levels) >= 2:
        sorted_calls = sorted(call_levels, key=lambda x: x["gex"], reverse=True)
        top_call_level = sorted_calls[1]
        top_call = {
            "price": top_call_level["futurePrice"],
            "gex": top_call_level["gex"],
            "label": f"Call {top_call_level['strike']}",
            "type": "call"
        }
    else:
        top_call = None

    # 5. Top Put GEX #2: second-most-negative gex
    if len(put_levels) >= 2:
        sorted_puts = sorted(put_levels, key=lambda x: x["gex"])
        top_put_level = sorted_puts[1]
        top_put = {
            "price": top_put_level["futurePrice"],
            "gex": top_put_level["gex"],
            "label": f"Put {top_put_level['strike']}",
            "type": "put"
        }
    else:
        top_put = None

    key_levels = {
        "zgl": {"price": zgl, "label": "ZGL", "type": "zero_gamma"},
        "call_wall": call_wall,
        "put_wall": put_wall,
        "top_call": top_call,
        "top_put": top_put,
    }

    # Update alert engine GEX cache
    if alert_engine:
        alert_engine.update_gex_cache(row_underlying, gex_data)

    # Update reversal engine GEX cache
    if reversal_engine:
        reversal_engine.update_gex_cache(row_underlying, gex_data)

    # ALWAYS compute fresh offset from current futures prices (ignore stored offset)
    fresh_offset, fresh_multiplier = await get_dynamic_offset(row_underlying)
    # Clamp to reasonable range to detect stale data (if offset > 100 it's obviously wrong)
    if abs(fresh_offset) > 100 or fresh_multiplier <= 0:
        logger.warning(f"Stale offset detected for {row_underlying}: offset={fresh_offset}, mult={fresh_multiplier}")

    return {
        "gex": gex_data,
        "key_levels": key_levels,
        "target_date": str(target_date),
        "underlying": row_underlying,
        "offset": fresh_offset,
        "multiplier": fresh_multiplier,
    }


@app.get("/api/gex/spx/latest")
async def get_gex_spx_latest():
    """SPX GEX endpoint."""
    return await get_gex_latest(underlying="SPX")


@app.get("/api/gex/qqq/latest")
async def get_gex_qqq_latest():
    """QQQ GEX endpoint."""
    return await get_gex_latest(underlying="QQQ")


# ──────────────────────────── Market Watch Options Metrics ────────────────────────────
@app.get("/api/market-watch")
async def get_market_watch():
    """
    Return options metrics for multiple underlyings (SPY, QQQ, USO, etc.)
    Similar to ThinkOrSwim Market Watch tab showing:
    - VOL: Total options volume
    - IV: Implied volatility (ATM)
    - IV Rank: Where current IV sits in 52-week range
    - IV Percentile: Percentage of days with lower IV
    - ATM Call/Put: ATM strike prices
    - Prob. OTM: Probability of expiring out of the money
    - Cost: Current underlying price
    """
    if not db_pool:
        return {"symbols": [], "message": "DB not connected"}

    # Underlyings to track (can be extended)
    underlyings = ['SPX', 'QQQ']

    result = []

    for underlying in underlyings:
        try:
            # Get current spot price
            spot_row = await db_pool.fetchrow('''
                SELECT price FROM futures_ticks
                WHERE symbol = $1 AND time > NOW() - INTERVAL '5 minutes'
                ORDER BY time DESC LIMIT 1
            ''', underlying)

            # Map to futures for price if no spot
            if not spot_row:
                if underlying == 'SPX':
                    spot_row = await db_pool.fetchrow('''
                        SELECT price FROM futures_ticks
                        WHERE symbol = 'US500-F' AND time > NOW() - INTERVAL '5 minutes'
                        ORDER BY time DESC LIMIT 1
                    ''')
                elif underlying == 'QQQ':
                    spot_row = await db_pool.fetchrow('''
                        SELECT price FROM futures_ticks
                        WHERE symbol = 'NAS100-F' AND time > NOW() - INTERVAL '5 minutes'
                        ORDER BY time DESC LIMIT 1
                    ''')

            current_price = float(spot_row['price']) if spot_row else None

            # Get today's options volume from flow ticks
            vol_row = await db_pool.fetchrow('''
                SELECT
                    COALESCE(SUM(call_volume), 0) + COALESCE(SUM(put_volume), 0) as total_volume
                FROM options_flow_ticks
                WHERE underlying = $1
                  AND time > NOW() - INTERVAL '24 hours'
            ''', underlying)

            total_volume = int(vol_row['total_volume']) if vol_row else 0

            # Get ATM strike (round to nearest 5 for SPX, 1 for QQQ)
            if current_price:
                if underlying == 'SPX':
                    atm_strike = round(current_price / 5) * 5
                else:  # QQQ
                    atm_strike = round(current_price)
            else:
                atm_strike = None

            # Simulate IV data (in production, this would come from options pricing)
            # Using realistic IV values based on typical market conditions
            iv = 15.5 if underlying == 'SPX' else 18.2
            iv_rank = 25.0 if underlying == 'SPX' else 32.0
            iv_percentile = 18.5 if underlying == 'SPX' else 22.0

            # Calculate Prob. OTM using delta approximation
            # Assuming ATM delta = 0.50, each 10% OTM ~ 10 delta points
            prob_otm_call = 50.0 + (iv * 0.3)  # Simplified
            prob_otm_put = 50.0 - (iv * 0.3)

            result.append({
                "symbol": underlying,
                "vol": total_volume,
                "iv": round(iv, 2),
                "iv_rank": round(iv_rank, 1),
                "iv_percentile": round(iv_percentile, 2),
                "atm_call": atm_strike,
                "atm_put": atm_strike,
                "prob_otm_call": round(prob_otm_call, 1),
                "prob_otm_put": round(prob_otm_put, 1),
                "cost": round(current_price, 2) if current_price else None,
            })

        except Exception as e:
            logger.error(f"Error getting market watch for {underlying}: {e}")
            result.append({
                "symbol": underlying,
                "vol": 0,
                "iv": None,
                "iv_rank": None,
                "iv_percentile": None,
                "atm_call": None,
                "atm_put": None,
                "prob_otm_call": None,
                "prob_otm_put": None,
                "cost": None,
            })

    return {"symbols": result}


# ──────────────────────────── Momentum & Zone Alert Endpoints ────────────────────────────
@app.get("/api/momentum/{underlying}")
async def get_momentum_score(
    underlying: str,
    futures_symbol: str = Query(None, description="Futures symbol: US500-F or NAS100-F"),
):
    """
    Return composite momentum score for scalp tool (9:30-11:30 EST).
    Components: Flow Velocity (35%), Price Action (25%), GEX Positioning (20%),
                Volume Ratio (10%), Theta Effect (10%)
    Score 0-100: >60 bullish reversal, <40 bearish reversal, 40-60 neutral.
    """
    if not db_pool:
        return {"error": "DB not connected"}

    underlying = underlying.upper()
    if futures_symbol:
        futures_symbol = futures_symbol.upper()
    else:
        futures_symbol = 'US500-F' if underlying == 'SPX' else 'NAS100-F'

    try:
        # Get current price
        price_row = await db_pool.fetchrow('''
            SELECT price FROM futures_ticks
            WHERE symbol = $1 AND time > NOW() - INTERVAL '5 minutes'
            ORDER BY time DESC LIMIT 1
        ''', futures_symbol)

        current_price = float(price_row['price']) if price_row else 0.0

        # Import and use FlowAnalyzer
        from flow_analyzer import FlowAnalyzer
        analyzer = FlowAnalyzer(db_pool)
        score = await analyzer.calculate_composite_score(underlying, futures_symbol, current_price)

        return {
            "underlying": underlying,
            "futures_symbol": futures_symbol,
            "current_price": current_price,
            "timestamp": datetime.now().isoformat(),
            **score
        }

    except Exception as e:
        logger.error(f"Momentum score error: {e}", exc_info=True)
        return {"error": str(e)}


@app.get("/api/momentum/zone-alert/{underlying}")
async def get_zone_alert(
    underlying: str,
    futures_symbol: str = Query(None, description="Futures symbol: US500-F or NAS100-F"),
):
    """
    Return zone proximity alert for UI arrows.
    Checks if price is near a high-probability reversal zone.
    Returns signal direction and strength for arrow display.
    """
    if not db_pool:
        return {"error": "DB not connected"}

    underlying = underlying.upper()
    if futures_symbol:
        futures_symbol = futures_symbol.upper()
    else:
        futures_symbol = 'US500-F' if underlying == 'SPX' else 'NAS100-F'

    try:
        # Get current price
        price_row = await db_pool.fetchrow('''
            SELECT price FROM futures_ticks
            WHERE symbol = $1 AND time > NOW() - INTERVAL '5 minutes'
            ORDER BY time DESC LIMIT 1
        ''', futures_symbol)

        current_price = float(price_row['price']) if price_row else 0.0

        if current_price == 0:
            return {"in_zone": False, "signal": "NEUTRAL", "reason": "No price data"}

        # Import and use FlowAnalyzer
        from flow_analyzer import FlowAnalyzer
        analyzer = FlowAnalyzer(db_pool)
        alert = await analyzer.get_zone_proximity_alert(underlying, futures_symbol, current_price)

        return {
            "underlying": underlying,
            "futures_symbol": futures_symbol,
            "current_price": current_price,
            "timestamp": datetime.now().isoformat(),
            **alert
        }

    except Exception as e:
        logger.error(f"Zone alert error: {e}", exc_info=True)
        return {"in_zone": False, "signal": "NEUTRAL", "error": str(e)}


# ──────────────────────────── Reversal Signal Endpoint ────────────────────────────
@app.get("/api/reversal/{underlying}")
async def get_reversal_signal(
    underlying: str,
    futures_symbol: str = Query(None, description="Futures symbol: US500-F or NAS100-F"),
):
    """
    Return composite reversal confluence signal for 0DTE scalping.
    Score 0-100: >70 = high-probability reversal, 40-60 = neutral.
    Components: GEX Proximity, Flow Divergence, Price Extension, Trap Signal, Gamma Regime.
    """
    if not db_pool:
        return {"error": "DB not connected"}

    underlying = underlying.upper()
    if futures_symbol:
        futures_symbol = futures_symbol.upper()
    else:
        futures_symbol = 'US500-F' if underlying == 'SPX' else 'NAS100-F'

    try:
        price_row = await db_pool.fetchrow('''
            SELECT price FROM futures_ticks
            WHERE symbol = $1 AND time > NOW() - INTERVAL '5 minutes'
            ORDER BY time DESC LIMIT 1
        ''', futures_symbol)

        current_price = float(price_row['price']) if price_row else 0.0

        if current_price == 0:
            return {"confluence": 0, "direction": "NEUTRAL", "error": "No price data"}

        signal = await reversal_engine.get_reversal_signal(underlying, futures_symbol, current_price)
        return signal

    except Exception as e:
        logger.error(f"Reversal signal error: {e}", exc_info=True)
        return {"confluence": 0, "direction": "NEUTRAL", "error": str(e)}


# ──────────────────────────── Greeks Endpoints ────────────────────────────
@app.get("/api/greeks/{underlying}")
async def get_greeks(underlying: str):
    """Return chain Greeks ATM +/-5% with IV data from ORATS."""
    if not greeks_service:
        return {"error": "Greeks service not initialized"}
    return await greeks_service.get_chain_greeks(underlying.upper())


@app.get("/api/greeks/summary/{underlying}")
async def get_greeks_summary(underlying: str):
    """Return aggregated Greeks summary per expiry."""
    if not greeks_service:
        return {"error": "Greeks service not initialized"}
    return await greeks_service.get_greeks_summary(underlying.upper())


@app.get("/api/volatility/surface")
async def get_volatility_surface_endpoint(underlying: str = Query(..., description="Underlying: SPX or QQQ")):
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


# ──────────────────────────── Alert Endpoints ────────────────────────────
@app.get("/api/alerts")
async def get_alerts(limit: int = Query(100, description="Max alerts to return")):
    """Return recent alerts."""
    if not alert_engine:
        return {"alerts": []}
    alerts = await alert_engine.get_recent_alerts(limit)
    return {"alerts": alerts}


@app.get("/api/alerts/config")
async def get_alert_config():
    """Return current alert configuration."""
    if not alert_engine:
        return {"config": {}}
    return {"config": alert_engine.config}


@app.put("/api/alerts/config")
async def update_alert_config(config: dict):
    """Update alert configuration."""
    if not alert_engine:
        return {"error": "Alert engine not initialized"}
    for key, value in config.items():
        if key in alert_engine.config:
            alert_engine.config[key] = value
    return {"config": alert_engine.config}


# ──────────────────────────── Dark Pool Endpoints ────────────────────────────
@app.get("/api/darkpool/dix/{underlying}")
async def get_darkpool_dix(underlying: str):
    """Return latest DIX score for underlying."""
    if not darkpool_analyzer:
        return {"error": "Dark pool analyzer not initialized"}
    return await darkpool_analyzer.get_dix(underlying.upper())


@app.get("/api/darkpool/history/{underlying}")
async def get_darkpool_history(
    underlying: str,
    days: int = Query(30, description="Days of history"),
):
    """Return historical DIX data."""
    if not darkpool_analyzer:
        return {"history": []}
    data = await darkpool_analyzer.get_history(underlying.upper(), days)
    return {"history": data}


# ──────────────────────────── OI Buildup Endpoint ────────────────────────────
@app.get("/api/oi/buildup/{underlying}")
async def get_oi_buildup(underlying: str):
    """Return top 3 calls + top 3 puts per OI delta."""
    if not oi_tracker:
        return {"error": "OI tracker not initialized", "calls": [], "puts": []}
    underlying = underlying.upper()
    if underlying not in ("SPX", "QQQ"):
        return {"error": "Invalid underlying", "calls": [], "puts": []}
    try:
        return oi_tracker.get_buildup(underlying)
    except Exception as e:
        logger.error(f"OI buildup error: {e}")
        return {"error": str(e), "calls": [], "puts": []}


# ──────────────────────────── WebSocket Endpoint ────────────────────────────
@app.websocket("/ws/market_data")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep alive — read client pings or messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
