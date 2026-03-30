import asyncio
import os
import ssl
import time
import logging
from typing import Optional
from datetime import datetime, timezone
import simplefix
from db import get_db_pool

# Configuration — Pepperstone Live
CTRADER_HOST = os.getenv("CTRADER_HOST", "live-uk-eqx-01.p.c-trader.com")
CTRADER_PORT = int(os.getenv("CTRADER_PORT", "5211"))
SENDER_COMP_ID = os.getenv("SENDER_COMP_ID", "live.pepperstone.1105672")
TARGET_COMP_ID = os.getenv("TARGET_COMP_ID", "cServer")
SENDER_SUB_ID = os.getenv("SENDER_SUB_ID", "QUOTE")
USERNAME = os.getenv("CTRADER_USERNAME", "1105672")
PASSWORD = os.getenv("CTRADER_PASSWORD", "782789Pao!")

# Symbols — Pepperstone cTrader naming: US500-F (SP500), NAS100-F (Nasdaq), plus Cash CFDs
SYMBOLS = ["US500-F", "NAS100-F", "US500", "NAS100"]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FIXClient:
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.msg_seq_num = 1
        self.logged_in = False
        self.parser = simplefix.FixParser()

    def create_message(self, msg_type):
        msg = simplefix.FixMessage()
        msg.append_pair(8, "FIX.4.4")
        msg.append_pair(35, msg_type)
        msg.append_pair(49, SENDER_COMP_ID)
        msg.append_pair(50, SENDER_SUB_ID)
        msg.append_pair(56, TARGET_COMP_ID)
        msg.append_pair(57, SENDER_SUB_ID)  # TargetSubID — cServer expects this to be 'QUOTE'
        msg.append_pair(34, self.msg_seq_num)
        
        # UTCTimestamp FIX 4.4 format: YYYYMMDD-HH:MM:SS
        t = datetime.now(timezone.utc).strftime("%Y%m%d-%H:%M:%S")
        msg.append_pair(52, t)
        
        self.msg_seq_num += 1
        return msg

    async def send_message(self, msg):
        if self.writer is None:
            return
        buffer = msg.encode()
        printable_buffer = buffer.replace(b'\x01', b'|').decode()
        logging.info(f"Sending: {printable_buffer}")
        self.writer.write(buffer)
        await self.writer.drain()

    async def logon(self):
        msg = self.create_message("A") # Logon
        msg.append_pair(98, "0") # EncryptMethod (None)
        msg.append_pair(108, "30") # HeartBtInt
        msg.append_pair(141, "Y") # ResetSeqNumFlag
        msg.append_pair(553, USERNAME) # Username
        msg.append_pair(554, PASSWORD) # Password
        await self.send_message(msg)

    async def request_security_list(self):
        """Send Security List Request (msg type x) to get symbol catalog with numeric IDs."""
        msg = self.create_message("x") # Security List Request
        msg.append_pair(320, "SEC_LIST_REQ") # SecurityReqID
        msg.append_pair(559, "0") # SecurityListRequestType (0 = All Securities)
        await self.send_message(msg)
        logging.info("Sent Security List Request to discover numeric symbol IDs")

    async def handle_security_list(self, msg):
        """Parse Security List Response to find numeric IDs for our target symbols."""
        raw = msg.encode()
        raw_readable = raw.replace(b'\x01', b'|').decode(errors='replace')
        
        # Write the FULL response to a file for inspection
        with open("/tmp/ctrader_security_list.txt", "w") as f:
            f.write(raw_readable)
        logging.info(f"Full Security List written to /tmp/ctrader_security_list.txt ({len(raw_readable)} chars)")
        
        # Parse all symbol entries: tag 55 = numeric ID, tag 1007 = symbol name
        import re
        # Each symbol block: 55=<id>\x011007=<name>
        pairs = re.findall(r'55=(\d+)\|1007=([^|]+)', raw_readable)
        
        symbol_map = {}
        for sym_id, name in pairs:
            # Search for our target instruments
            name_upper = name.upper()
            if any(k in name_upper for k in ['US500', 'NAS100', 'US100', 'SP500', 'NASDAQ']):
                logging.info(f"*** MATCHED: {name} -> numeric ID: {sym_id} ***")
                symbol_map[name] = sym_id
        
        if symbol_map:
            logging.info(f"Symbol map: {symbol_map}")
            # Subscribe using numeric IDs - TRADES only
            for name, sym_id in symbol_map.items():
                req_msg = self.create_message("V")
                req_msg.append_pair(262, f"REQ_{sym_id}_{name}")
                req_msg.append_pair(263, "1")
                req_msg.append_pair(264, "1")
                req_msg.append_pair(265, "1")
                req_msg.append_pair(267, "1")  # NoMDEntryTypes
                req_msg.append_pair(269, "2")  # MDEntryType: Trade
                req_msg.append_pair(146, "1")
                req_msg.append_pair(55, sym_id)  # Use NUMERIC ID here
                await self.send_message(req_msg)
                logging.info(f"Subscribed to {name} with numeric ID {sym_id}")
        else:
            logging.warning("No US500/NAS100 symbols found in security list!")
            # Dump first 20 symbol pairs for debugging
            for sym_id, name in pairs[:20]:
                logging.info(f"  Available: {name} = {sym_id}")

    async def subscribe_market_data(self):
        for req_id, symbol in enumerate(SYMBOLS, 1):
            msg = self.create_message("V") # Market Data Request
            msg.append_pair(262, f"REQ_{req_id}_{symbol}") # MDReqID
            msg.append_pair(263, "1") # SubscriptionRequestType (1 = Snapshot + Updates)
            msg.append_pair(264, "1") # MarketDepth (1 = Top of Book)
            msg.append_pair(265, "1") # MDUpdateType (1 = Incremental)
            
            # Request TRADES only (not bid/ask quotes)
            msg.append_pair(267, "1") # NoMDEntryTypes
            msg.append_pair(269, "2") # MDEntryType: Trade
            
            # Related Sym
            msg.append_pair(146, "1") # NoRelatedSym
            msg.append_pair(55, symbol) # Symbol

            await self.send_message(msg)
            logging.info(f"Subscribed to Market Data for {symbol}")

    async def handle_message(self, msg):
        msg_type = msg.get(35).decode()
        
        if msg_type == "A": # Logon answer
            self.logged_in = True
            logging.info("Successful Logon to cTrader FIX API.")
            # First request the security list to discover numeric symbol IDs
            await self.request_security_list()
            
        elif msg_type == "0": # Heartbeat
            pass # Server heartbeat
            
        elif msg_type == "1": # Test Request
            test_req_id = msg.get(112)
            hb = self.create_message("0")
            if test_req_id:
                hb.append_pair(112, test_req_id.decode())
            await self.send_message(hb)

        elif msg_type == "y": # Security List Response
            await self.handle_security_list(msg)
            
        elif msg_type == "W" or msg_type == "X": # Market Data Full Refresh / Incremental
            await self.process_market_data(msg)
            
        elif msg_type == "Y": # Market Data Request Reject
            reason = msg.get(58)
            reason_str = reason.decode() if reason else "No reason"
            req_id = msg.get(262)
            req_id_str = req_id.decode() if req_id else "?"
            logging.error(f"Market Data Request REJECTED! ReqID: {req_id_str} Reason: {reason_str}")
            
        elif msg_type == "3": # Reject
            reason = msg.get(58) # Text field
            reason_str = reason.decode() if reason else "No reason"
            ref_tag = msg.get(371) # RefTagID
            ref_tag_str = ref_tag.decode() if ref_tag else "?"
            logging.error(f"Message Rejected! RefTag: {ref_tag_str} Reason: {reason_str}")
            
        elif msg_type == "5": # Logout
            reason = msg.get(58) # Text field with rejection reason
            reason_str = reason.decode() if reason else "No reason provided"
            logging.warning(f"Logout received from server. Reason: {reason_str}")
            self.logged_in = False
        
        else:
            # Log any unknown message type for debugging
            raw = msg.encode().replace(b'\x01', b'|')
            logging.info(f"Unknown msg type={msg_type}: {raw.decode()}")

    # Map cTrader numeric IDs to readable names (discovered from Security List)
    SYMBOL_NAME_MAP = {
        "10013": "US500",
        "10014": "NAS100", 
        "11374": "NAS100-F",
        "11375": "US500-F",
    }

    async def process_market_data(self, msg):
        symbol = msg.get(55)
        if not symbol: return
        symbol_id = symbol.decode()
        
        # Map numeric ID to readable name
        symbol_name = self.SYMBOL_NAME_MAP.get(symbol_id, symbol_id)
        
        price_bytes = msg.get(270)
        size_bytes = msg.get(271)
        
        if price_bytes:
            price = float(price_bytes.decode())
            size = int(size_bytes.decode()) if size_bytes else 0
            
            await self.db_pool.execute('''
                INSERT INTO futures_ticks (time, symbol, price, volume) 
                VALUES (NOW(), $1, $2, $3)
            ''', symbol_name, price, size)
            
            logging.info(f"Tick: {symbol_name} @ {price} x{size}")

    async def connect(self):
        context = ssl.create_default_context()
        # cTrader requires ssl for port 5211
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        logging.info(f"Connecting to {CTRADER_HOST}:{CTRADER_PORT}...")
        self.reader, self.writer = await asyncio.open_connection(
            CTRADER_HOST, CTRADER_PORT, ssl=context
        )
        
        await self.logon()

        # Keep connection alive and read messages
        while True:
            try:
                if self.reader is None:
                    break
                
                data = await self.reader.read(4096)
                if not data:
                    logging.warning("Connection lost.")
                    break
                    
                self.parser.append_buffer(data)
                
                while True:
                    msg = self.parser.get_message()
                    if msg is None:
                        break
                    # logging.debug(f"Received: {msg.encode().replace(b'\x01', b'|')}")
                    await self.handle_message(msg)
                    
            except Exception as e:
                logging.error(f"Error reading socket: {e}")
                break

async def main():
    pool = await get_db_pool()
    while True:
        client = FIXClient(pool)
        try:
            await client.connect()
        except Exception as e:
            logging.error(f"Connection failed: {e}")
            
        logging.info("Reconnecting in 5 seconds...")
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
