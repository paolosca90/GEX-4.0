import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "gex_super_secret_db_pass")
DB_HOST = os.getenv("DB_HOST", "137.220.63.222") # Vultr VPS
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "gex_db")

DSN = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

async def get_db_pool():
    return await asyncpg.create_pool(dsn=DSN)

async def init_db():
    print("Initialize database schema if not exists...")
    conn = await asyncpg.connect(dsn=DSN)
    
    # Create extension for TimescaleDB if not exists
    await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    
    # 1. Table for Futures Ticks
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS futures_ticks (
            time TIMESTAMPTZ NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            volume INT NOT NULL
        );
    """)
    try:
        await conn.execute("SELECT create_hypertable('futures_ticks', 'time', if_not_exists => TRUE);")
    except Exception as e:
        print(f"Hypertable futures_ticks notice: {e}")

    # 2. Table for Options Flow (Net Flow / Net Drift analysis)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS options_flow (
            time TIMESTAMPTZ NOT NULL,
            underlying VARCHAR(10) NOT NULL,
            option_symbol VARCHAR(50) NOT NULL,
            expiration DATE NOT NULL,
            strike DOUBLE PRECISION NOT NULL,
            option_type VARCHAR(4) NOT NULL,  -- CALL or PUT
            trade_price DOUBLE PRECISION NOT NULL,
            trade_size INT NOT NULL,
            trade_premium DOUBLE PRECISION NOT NULL,
            sentiment VARCHAR(10) NOT NULL, -- BUY, SELL, NONE
            is_0dte BOOLEAN NOT NULL
        );
    """)
    try:
        await conn.execute("SELECT create_hypertable('options_flow', 'time', if_not_exists => TRUE);")
    except Exception as e:
        print(f"Hypertable options_flow notice: {e}")

    # Add oi_delta column to options_flow
    await conn.execute("""
        ALTER TABLE options_flow ADD COLUMN IF NOT EXISTS oi_delta INTEGER;
        COMMENT ON COLUMN options_flow.oi_delta IS 'Delta OI session-over-session for this strike, set on insert from batch OI snapshot';
    """)

    # 3. Table for Daily GEX Profile
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS gex_profile (
            calc_date DATE NOT NULL,
            target_date DATE NOT NULL,
            underlying VARCHAR(10) NOT NULL,
            strike DOUBLE PRECISION NOT NULL,
            total_gex DOUBLE PRECISION NOT NULL,
            translated_future_price DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (calc_date, target_date, underlying, strike)
        );
    """)

    # 4. Table for Options Flow Ticks (2-second intervals)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS options_flow_ticks (
            time TIMESTAMPTZ NOT NULL,
            underlying VARCHAR(10) NOT NULL,
            call_premium DOUBLE PRECISION NOT NULL,
            put_premium DOUBLE PRECISION NOT NULL,
            call_volume INT NOT NULL,
            put_volume INT NOT NULL,
            net_drift DOUBLE PRECISION NOT NULL
        );
    """)
    try:
        await conn.execute("SELECT create_hypertable('options_flow_ticks', 'time', if_not_exists => TRUE);")
    except Exception as e:
        print(f"Hypertable options_flow_ticks notice: {e}")

    # 5. Table for Options Flow 1m (1-minute intervals)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS options_flow_1m (
            time TIMESTAMPTZ NOT NULL,
            underlying VARCHAR(10) NOT NULL,
            call_premium DOUBLE PRECISION NOT NULL,
            put_premium DOUBLE PRECISION NOT NULL,
            call_volume INT NOT NULL,
            put_volume INT NOT NULL,
            net_drift DOUBLE PRECISION NOT NULL
        );
    """)
    try:
        await conn.execute("SELECT create_hypertable('options_flow_1m', 'time', if_not_exists => TRUE);")
    except Exception as e:
        print(f"Hypertable options_flow_1m notice: {e}")

    # 6. Table for GEX Level Interactions (for historical reliability)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS gex_level_interactions (
            id BIGSERIAL PRIMARY KEY,
            time TIMESTAMPTZ NOT NULL,
            underlying VARCHAR(10) NOT NULL,
            level_price DOUBLE PRECISION NOT NULL,
            touch_price DOUBLE PRECISION NOT NULL,
            direction VARCHAR(10) NOT NULL,  -- 'TOUCH', 'BOUNCE', 'BREAK'
            gex_magnitude DOUBLE PRECISION NOT NULL,
            bounce_result VARCHAR(10),  -- 'BOUNCED', 'BROKE', NULL
            UNIQUE(time, underlying, level_price)
        );
    """)
    try:
        await conn.execute("SELECT create_hypertable('gex_level_interactions', 'time', if_not_exists => TRUE);")
    except Exception as e:
        print(f"Hypertable gex_level_interactions notice: {e}")

    # 7. Table for Alerts (real-time signals)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id BIGSERIAL PRIMARY KEY,
            time TIMESTAMPTZ NOT NULL,
            underlying VARCHAR(10) NOT NULL,
            alert_type VARCHAR(30) NOT NULL,
            severity VARCHAR(10) NOT NULL,
            direction VARCHAR(10),
            trigger_price DOUBLE PRECISION,
            level_price DOUBLE PRECISION,
            message TEXT,
            metadata JSONB
        );
    """)
    try:
        await conn.execute("SELECT create_hypertable('alerts', 'time', if_not_exists => TRUE);")
    except Exception as e:
        print(f"Hypertable alerts notice: {e}")

    # 8. Table for Dark Pool Daily (DIX indicator)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS darkpool_daily (
            date DATE NOT NULL,
            underlying VARCHAR(10) NOT NULL,
            short_volume BIGINT,
            total_volume BIGINT,
            short_ratio DOUBLE PRECISION,
            dix DOUBLE PRECISION,
            dark_volume_estimate BIGINT,
            updated_at TIMESTAMPTZ,
            PRIMARY KEY (date, underlying)
        );
    """)

    # 9. Table for OI Snapshots (30-min intervals)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS oi_snapshots (
            time TIMESTAMPTZ NOT NULL,
            underlying VARCHAR(10) NOT NULL,
            strike DOUBLE PRECISION NOT NULL,
            oi_total INTEGER NOT NULL,
            oi_delta INTEGER NOT NULL,
            oi_delta_retail INTEGER NOT NULL DEFAULT 0,
            oi_delta_block INTEGER NOT NULL DEFAULT 0,
            side VARCHAR(4) NOT NULL,
            PRIMARY KEY (time, underlying, strike)
        );
    """)
    try:
        await conn.execute("SELECT create_hypertable('oi_snapshots', 'time', if_not_exists => TRUE);")
    except Exception as e:
        print(f"Hypertable oi_snapshots notice: {e}")

    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_oi_snapshots_underlying_strike
        ON oi_snapshots (underlying, strike, time DESC);
    """)

    await conn.close()
    print("Database initialization complete.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
