#!/usr/bin/env python3
"""
cTrader OpenAPI daemon for real-time futures data.
Uses ProtoOASpotEvent for bid/ask quotes (prices in 1/100000 of unit).
For candlestick charts, also subscribes to live trendbars.

Documentation: https://help.ctrader.com/open-api/messages/
"""
import logging
import psycopg2
from datetime import datetime, timezone
from twisted.internet import reactor, defer, threads
from ctrader_open_api import Client, Protobuf, TcpProtocol, EndPoints
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATrendbarPeriod

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ctrader_openapi_daemon")

# Credentials - Pepperstone Live 1105672
CLIENT_ID = "22265_zhq1ODwNJGQLvTNO1MpyWhSJRr6Nu4cn8UgWUyRtBT1XCkRjMh"
CLIENT_SECRET = "w3MVKpqteYiu1KyQDgQDdibCFHqEI6lZmGlHpqm6TB8iyKIcfl"
ACCESS_TOKEN = "GCAIGLs0fBqAMMKDLxM10WDkweZbh_xtX_W4CTX45jY"

# Live endpoint
HOST = EndPoints.PROTOBUF_LIVE_HOST
PORT = EndPoints.PROTOBUF_PORT

# Database connection
DB_DSN = "postgresql://postgres:gex_super_secret_db_pass@137.220.63.222:5432/gex_db"

# Target futures symbols
TARGET_SYMBOLS = ["US500-F", "NAS100-F"]

# Global state
client = None
account_id = None
symbols_info = {}  # id -> name


def store_tick_sync(symbol: str, price: float):
    """Store a tick in the database using psycopg2 (synchronous)."""
    try:
        conn = psycopg2.connect(DB_DSN)
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO futures_ticks (time, symbol, price, volume)
            VALUES (NOW(), %s, %s, 0)
        ''', (symbol, price))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Tick: {symbol} @ {price:.2f}")
    except Exception as e:
        logger.error(f"DB error: {e}")


def on_message_received(c, message):
    """Handle incoming messages from cTrader."""
    try:
        # Extract the actual message from ProtoMessage wrapper
        msg = Protobuf.extract(message)
        msg_type = msg.DESCRIPTOR.name if hasattr(msg, 'DESCRIPTOR') else 'Unknown'

        # Handle Spot Events (bid/ask quotes)
        # Prices are in 1/100000 of unit
        if msg_type == 'ProtoOASpotEvent':
            symbol_id = msg.symbolId
            symbol_name = symbols_info.get(symbol_id)

            if not symbol_name:
                return

            # Use ask price (what buyers pay) if available, otherwise bid
            price = None
            if msg.HasField('ask') and msg.ask > 0:
                price = msg.ask / 100000
            elif msg.HasField('bid') and msg.bid > 0:
                price = msg.bid / 100000

            if price and price > 0:
                # Store in DB (run in thread to not block reactor)
                threads.deferToThread(store_tick_sync, symbol_name, price)

    except Exception as e:
        logger.error(f"Message handler error: {e}")


def main():
    global client, account_id, symbols_info

    def on_connect(_):
        logger.info(f"Connecting to {HOST}:{PORT}...")
        new_client = Client(HOST, PORT, TcpProtocol)
        new_client.setMessageReceivedCallback(on_message_received)
        new_client.startService()
        return new_client

    def on_client_ready(c):
        global client
        client = c
        logger.info("Connected! Authenticating application...")
        req = ProtoOAApplicationAuthReq()
        req.clientId = CLIENT_ID
        req.clientSecret = CLIENT_SECRET
        return client.send(req)

    def on_app_auth(res):
        logger.info("Application authenticated")
        logger.info("Getting accounts...")
        req = ProtoOAGetAccountListByAccessTokenReq()
        req.accessToken = ACCESS_TOKEN
        return client.send(req)

    def on_accounts(res):
        global account_id
        msg = Protobuf.extract(res)
        logger.info(f"Got accounts: {len(msg.ctidTraderAccount)}")

        # Find Pepperstone Live account (1105672)
        for acc in msg.ctidTraderAccount:
            live_status = 'Live' if acc.isLive else 'Demo'
            logger.info(f"  Account: {acc.ctidTraderAccountId} ({live_status})")
            if acc.isLive and '1105672' in str(acc.ctidTraderAccountId):
                account_id = acc.ctidTraderAccountId
                break

        if not account_id:
            for acc in msg.ctidTraderAccount:
                if acc.isLive:
                    account_id = acc.ctidTraderAccountId
                    break

        if not account_id:
            account_id = msg.ctidTraderAccount[0].ctidTraderAccountId

        logger.info(f"Using account: {account_id}")

        req = ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = account_id
        req.accessToken = ACCESS_TOKEN
        return client.send(req)

    def on_account_auth(res):
        logger.info("Account authorized! Getting symbols...")
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = account_id
        return client.send(req)

    def on_symbols(res):
        global symbols_info
        msg = Protobuf.extract(res)

        for sym in msg.symbol:
            name = sym.symbolName.upper()
            if name in TARGET_SYMBOLS:
                symbols_info[sym.symbolId] = sym.symbolName
                logger.info(f"Symbol: {sym.symbolName} -> ID:{sym.symbolId}")

        # Subscribe to spot prices
        req = ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = account_id
        for sym_id in symbols_info.keys():
            req.symbolId.append(sym_id)
            logger.info(f"Subscribing to spot events for ID {sym_id}")

        d = client.send(req)
        d.addCallback(on_spots_subscribed)
        d.addErrback(lambda f: logger.error(f"Subscribe spots error: {f}"))
        return d

    def on_spots_subscribed(res):
        logger.info("Subscribed to spot events")

        # Request 24h of historical M1 trendbars for each symbol
        dl = []
        for sym_id, sym_name in symbols_info.items():
            # Request historical backfill (last 24 hours = 1440 minutes)
            req = ProtoOAGetTrendbarsReq()
            req.ctidTraderAccountId = account_id
            req.symbolId = sym_id
            req.period = ProtoOATrendbarPeriod.M1
            req.fromTimestamp = int((datetime.now(timezone.utc).timestamp() - 86400) * 1000)
            req.toTimestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
            req.count = 1440  # Max 1440 M1 bars in 24h

            d = client.send(req)
            d.addCallback(lambda r, n=sym_name: on_historical_trendbars(n, r))
            d.addErrback(lambda f, n=sym_name: logger.error(f"Historical backfill error for {n}: {f}"))
            dl.append(d)
            logger.info(f"Requested 24h historical M1 trendbars for {sym_name}")

        # Also subscribe to live M1 trendbars
        for sym_id, sym_name in symbols_info.items():
            req = ProtoOASubscribeLiveTrendbarReq()
            req.ctidTraderAccountId = account_id
            req.symbolId = sym_id
            req.period = ProtoOATrendbarPeriod.M1

            d = client.send(req)
            d.addCallback(lambda r, n=sym_name: logger.info(f"Subscribed to live M1 trendbars for {n}"))
            d.addErrback(lambda f, n=sym_name: logger.error(f"Live trendbar sub error for {n}: {f}"))
            dl.append(d)

        return defer.DeferredList(dl)

    def on_historical_trendbars(symbol_name, res):
        """Handle historical M1 trendbars response from cTrader."""
        try:
            msg = Protobuf.extract(res)
            if not hasattr(msg, 'trendbar') or not msg.trendbar:
                logger.info(f"No historical trendbars returned for {symbol_name}")
                return

            logger.info(f"Received {len(msg.trendbar)} historical M1 bars for {symbol_name}")

            conn = psycopg2.connect(DB_DSN)
            cur = conn.cursor()

            inserted = 0
            prev_close_int = None  # store in raw 1/100000 units for next iteration
            for bar in msg.trendbar:
                # bar.utcTimestampInMinutes = Unix timestamp in minutes
                # bar.low = absolute low price in 1/100000 units
                # bar.deltaOpen/deltaClose/deltaHigh = deltas in 1/100000 units from prev bar's close
                ts = datetime.fromtimestamp(bar.utcTimestampInMinutes * 60, tz=timezone.utc)

                if prev_close_int is None:
                    # First bar: deltas are relative to some base we don't have.
                    # Use low as base for all values (conservative estimate)
                    open_px = bar.low / 100000
                    close_px = (bar.low + bar.deltaClose) / 100000
                    high_px = (bar.low + bar.deltaHigh) / 100000
                else:
                    open_px = (prev_close_int + bar.deltaOpen) / 100000
                    close_px = (prev_close_int + bar.deltaClose) / 100000
                    high_px = (prev_close_int + bar.deltaHigh) / 100000

                prev_close_int = bar.low + bar.deltaClose  # close in raw units for next bar

                # Store mid price (OHLCV aggregation is best-effort from raw ticks)
                mid_price = (open_px + close_px) / 2

                cur.execute('''
                    INSERT INTO futures_ticks (time, symbol, price, volume)
                    VALUES (%s, %s, %s, 0)
                    ON CONFLICT DO NOTHING
                ''', (ts, symbol_name, mid_price))

                inserted += 1

            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"Inserted {inserted} historical ticks for {symbol_name}")

        except Exception as e:
            logger.error(f"Error processing historical trendbars for {symbol_name}: {e}", exc_info=True)

    def on_error(failure):
        logger.error(f"Error: {failure}")
        reactor.stop()

    # Chain callbacks
    d = defer.Deferred()
    d.addCallback(on_connect)
    d.addCallback(on_client_ready)
    d.addCallback(on_app_auth)
    d.addCallback(on_accounts)
    d.addCallback(on_account_auth)
    d.addCallback(on_symbols)
    d.addErrback(on_error)

    # Trigger the chain
    reactor.callLater(0.5, d.callback, None)

    logger.info("Starting cTrader OpenAPI daemon...")
    reactor.run()


if __name__ == "__main__":
    main()
