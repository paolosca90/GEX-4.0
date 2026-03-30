import asyncio
import os
import json
import logging
from datetime import datetime
import websockets
import httpx
from db import get_db_pool

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("tradier_daemon")

TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "mVoOWSiu47rIQoSq2u2C0fZxOtwc")
TRADIER_WS_URL = "wss://ws.tradier.com/v1/markets/events"
TRADIER_REST_URL = "https://api.tradier.com/v1"

SYMBOLS = ["SPX", "QQQ"]

async def create_tradier_session():
    """Create a new streaming session with Tradier and return the session ID."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TRADIER_REST_URL}/markets/events/session",
            headers={
                "Authorization": f"Bearer {TRADIER_API_KEY}",
                "Accept": "application/json"
            }
        )
        if response.status_code == 200:
            return response.json()['stream']['sessionid']
        else:
            logger.error(f"Failed to create Tradier session: {response.text}")
            return None

async def tradier_ws_daemon():
    logger.info("Starting Tradier WebSocket Daemon...")
    db_pool = await get_db_pool()
    
    while True:
        session_id = await create_tradier_session()
        if not session_id:
            logger.error("Could not get session ID, retrying in 10s...")
            await asyncio.sleep(10)
            continue
            
        logger.info(f"Got session ID: {session_id}")
        
        try:
            async with websockets.connect(TRADIER_WS_URL) as ws:
                # Send Connection Payload
                payload = {
                    "events": ["summary", "trade", "quote"], # Request summary, trades and quotes
                    "sessionid": session_id,
                    "symbols": SYMBOLS,
                    "linebreak": True
                }
                logger.info(f"Sending payload: {payload}")
                await ws.send(json.dumps(payload))
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    typ = data.get('type')
                    if typ in ['trade', 'quote', 'summary']:
                        symbol = data.get('symbol')
                        
                        if typ == 'trade':
                            price = float(data.get('price', 0))
                            size = int(data.get('size', 0))
                        else:
                            price = float(data.get('last') or data.get('close') or data.get('prevClose') or 0)
                            size = 0
                        
                        # Note: This is where we insert Spot Price Trades into our system
                        if symbol in SYMBOLS and price > 0:
                            # We can store this or broadcast it to update the RealTime Offset
                            # Offset = Future (ES) - Spot (SPX)
                            logger.info(f"Tradier Spot {typ}: {symbol} @ {price}")
                            
                            await db_pool.execute('''
                                INSERT INTO futures_ticks (time, symbol, price, volume) 
                                VALUES (NOW(), $1, $2, $3)
                            ''', symbol, price, size)
                            
                    elif data.get('type') == 'error':
                        logger.error(f"Tradier WS Error: {data}")
                    
        except websockets.ConnectionClosed:
            logger.warning("Tradier WebSocket closed, reconnecting...")
        except Exception as e:
            logger.error(f"Tradier WebSocket exception: {e}")
            
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(tradier_ws_daemon())
