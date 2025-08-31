import os
import re
import asyncio
from telethon import TelegramClient
from telethon.events import NewMessage
import ccxt.async_support as ccxt_async
from telegram import Bot
import socks
from aiohttp_socks import ProxyConnector
from aiohttp import ClientSession
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram config
BOT_TOKEN = os.getenv('BOT_TOKEN', '7662307654:AAG5-juB1faNaFZfC8zjf4LwlZMzs6lEmtE')
CHAT_ID = os.getenv('CHAT_ID', '655537138')
API_ID = int(os.getenv('TELEGRAM_API_ID', 20102847))
API_HASH = os.getenv('TELEGRAM_API_HASH', 'f273163ee37a3fff0e98a5e022ebc930')
PHONE_NUMBER = os.getenv('TELEGRAM_PHONE', '+919988143599')

# All 10 proxies from your list (SOCKS5 assumed)
PROXIES = [
    {'ip': '23.95.150.145', 'port': 6114, 'username': 'vjautpgi', 'password': 'rfvep83upfiy', 'location': 'US Buffalo'},
    {'ip': '198.23.239.134', 'port': 6540, 'username': 'vjautpgi', 'password': 'rfvep83upfiy', 'location': 'US Buffalo'},
    {'ip': '45.38.107.97', 'port': 6014, 'username': 'vjautpgi', 'password': 'rfvep83upfiy', 'location': 'UK London'},
    {'ip': '107.172.163.27', 'port': 6543, 'username': 'vjautpgi', 'password': 'rfvep83upfiy', 'location': 'US Bloomingdale'},
    {'ip': '64.137.96.74', 'port': 6641, 'username': 'vjautpgi', 'password': 'rfvep83upfiy', 'location': 'Spain Madrid'},
    {'ip': '45.43.186.39', 'port': 6257, 'username': 'vjautpgi', 'password': 'rfvep83upfiy', 'location': 'Spain Madrid'},
    {'ip': '154.203.43.247', 'port': 5536, 'username': 'vjautpgi', 'password': 'rfvep83upfiy', 'location': 'Japan Chiyoda City'},
    {'ip': '216.10.27.159', 'port': 6837, 'username': 'vjautpgi', 'password': 'rfvep83upfiy', 'location': 'US Dallas'},
    {'ip': '136.0.207.84', 'port': 6661, 'username': 'vjautpgi', 'password': 'rfvep83upfiy', 'location': 'US Orem'},
    {'ip': '142.147.128.93', 'port': 6593, 'username': 'vjautpgi', 'password': 'rfvep83upfiy', 'location': 'Unknown'},
]

# Global proxy index for cycling
current_proxy_index = int(os.getenv('PROXY_LIST_INDEX', 0)) % len(PROXIES)

def get_current_proxy():
    global current_proxy_index
    proxy = PROXIES[current_proxy_index]
    proxy_url = f"socks5://{proxy['username']}:{proxy['password']}@{proxy['ip']}:{proxy['port']}"
    return proxy, proxy_url

def next_proxy():
    global current_proxy_index
    current_proxy_index = (current_proxy_index + 1) % len(PROXIES)
    return get_current_proxy()

# Create CCXT exchange with current proxy
async def create_exchange():
    proxy, proxy_url = get_current_proxy()
    config = {
        'enableRateLimit': True,
        'apiKey': os.getenv('BINANCE_API_KEY', ''),
        'secret': os.getenv('BINANCE_API_SECRET', ''),
    }
    if proxy_url:
        try:
            connector = ProxyConnector.from_url(proxy_url)
            session = ClientSession(connector=connector)
            config['session'] = session
        except Exception as e:
            print(f"Proxy setup failed for {proxy['ip']}:{proxy['port']}: {e}")
            await bot.send_message(chat_id=CHAT_ID, text=f"Proxy setup failed: {proxy['ip']}:{proxy['port']} ({proxy['location']}) - {e}")
            # Switch to next proxy
            next_proxy()
            return await create_exchange()  # Recursive retry
    exchange = ccxt_async.binance(config)
    return exchange

# Store simulated positions
open_positions = []

# Initialize Telethon with first proxy (for Telegram stability)
proxy_telethon = None
if PROXIES:
    first_proxy = PROXIES[0]
    proxy_telethon = {
        'proxy_type': socks.SOCKS5,
        'addr': first_proxy['ip'],
        'port': first_proxy['port'],
        'username': first_proxy['username'],
        'password': first_proxy['password']
    }
client = TelegramClient('trading_bot_session', API_ID, API_HASH, proxy=proxy_telethon)
bot = Bot(BOT_TOKEN)

# Parse signals (unchanged)
def parse_signal(message_text, group_name):
    signal = None
    if group_name == '@Official_GCR':
        match = re.search(r'Coin #(\w+/USDT)\s+Position:\s*(LONG|SHORT)\s+Leverage:.*Entries:\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s+Targets:.*?([\d\.]+(?:,\s*[\d\.]+)*)\s+Stop Loss:\s*(\d+\.?\d*)', message_text, re.IGNORECASE)
        if match:
            symbol = match.group(1).replace('/', '').upper()
            side = match.group(2).upper()
            entry_low = float(match.group(4))
            tp_list = [float(tp.strip()) for tp in match.group(5).split(',') if tp.strip()]
            sl = float(match.group(6))
            signal = {'symbol': symbol, 'side': side, 'entry': entry_low, 'tp': tp_list, 'sl': sl}
    elif group_name == '@THE_WOLFREAL':
        match = re.search(r'COIN NAME:\s*(\w+)\(USDT\).*TRADE TYPE:\s*(LONG|SHORT).*ENTRY PRICE\s*\((\d+\.?\d*)-(\d+\.?\d*)\).*TAKE-PROFITS\s+1️⃣\s*(\d+\.?\d*)\s+2️⃣\s*(\d+\.?\d*)\s+3️⃣\s*(\d+\.?\d*)\s+STOP LOSS:\s*(\d+\.?\d*)', message_text, re.IGNORECASE)
        if match:
            symbol = match.group(1).upper() + 'USDT'
            side = match.group(2).upper()
            entry_low = float(match.group(4))
            tp_list = [float(match.group(i)) for i in range(5, 8)]
            sl = float(match.group(8))
            signal = {'symbol': symbol, 'side': side, 'entry': entry_low, 'tp': tp_list, 'sl': sl}
    return signal

# Simulate trade entry with proxy cycling
async def simulate_entry(signal, group_name, exchange):
    global current_proxy_index
    try:
        ticker = await exchange.fetch_ticker(signal['symbol'])
        current_price = ticker['last']
        
        if abs(current_price - signal['entry']) / signal['entry'] > 0.01:
            await bot.send_message(chat_id=CHAT_ID, text=f"[{group_name}] Ignoring {signal['side']} {signal['symbol']}: Entry {signal['entry']} too far from current {current_price}")
            return
        
        quantity = 0.001
        position = {
            'symbol': signal['symbol'],
            'side': signal['side'],
            'entry': current_price,
            'quantity': quantity,
            'tp': signal['tp'],
            'sl': signal['sl'],
            'group': group_name
        }
        open_positions.append(position)
        
        proxy, _ = get_current_proxy()
        message = f"[{group_name}] Simulated ENTRY (Proxy: {proxy['ip']}:{proxy['port']} {proxy['location']}): {signal['side']} {signal['symbol']} at {current_price}, Quantity: {quantity}, TP: {', '.join(map(str, signal['tp']))}, SL: {signal['sl']}"
        await bot.send_message(chat_id=CHAT_ID, text=message)
    
    except Exception as e:
        proxy, _ = get_current_proxy()
        await bot.send_message(chat_id=CHAT_ID, text=f"[{group_name}] Error with proxy {proxy['ip']}:{proxy['port']} ({proxy['location']}): {str(e)}. Switching proxy...")
        print(f"Error with proxy {proxy['ip']}:{proxy['port']}: {e}")
        # Close current exchange session if exists
        if hasattr(exchange, 'session') and exchange.session:
            await exchange.session.close()
        # Switch to next proxy and retry
        next_proxy()
        new_exchange = await create_exchange()
        await simulate_entry(signal, group_name, new_exchange)  # Retry

# Monitor positions with proxy cycling
async def monitor_positions(exchange):
    global current_proxy_index
    while True:
        for pos in open_positions[:]:
            try:
                ticker = await exchange.fetch_ticker(pos['symbol'])
                current_price = ticker['last']
                
                if pos['side'] == 'LONG':
                    pnl = (current_price - pos['entry']) * pos['quantity']
                    hit_tp = any(current_price >= tp for tp in pos['tp'])
                    hit_sl = current_price <= pos['sl']
                else:
                    pnl = (pos['entry'] - current_price) * pos['quantity']
                    hit_tp = any(current_price <= tp for tp in pos['tp'])
                    hit_sl = current_price >= pos['sl']
                
                if hit_tp or hit_sl:
                    close_price = current_price
                    proxy, _ = get_current_proxy()
                    message = f"[{pos['group']}] Simulated EXIT (Proxy: {proxy['ip']}:{proxy['port']} {proxy['location']}): {pos['side']} {pos['symbol']} at {close_price}, PNL: {pnl:.2f} USDT ({'TP' if hit_tp else 'SL'})"
                    await bot.send_message(chat_id=CHAT_ID, text=message)
                    open_positions.remove(pos)
                
            except Exception as e:
                proxy, _ = get_current_proxy()
                print(f"Monitor error with proxy {proxy['ip']}:{proxy['port']}: {e}")
                # Switch proxy on error
                next_proxy()
                new_exchange = await create_exchange()
                await monitor_positions(new_exchange)  # Restart monitor with new exchange
                return  # Exit current loop after switch
        
        await asyncio.sleep(60)

# Handle new messages (pass exchange)
@client.on(NewMessage(chats=['@Official_GCR', '@THE_WOLFREAL']))
async def handle_message(event):
    message_text = event.message.text
    group_name = event.chat.username
    if message_text and group_name:
        signal = parse_signal(message_text, group_name)
        if signal:
            message = f"[{group_name}] Signal detected: {signal['side']} {signal['symbol']} at {signal['entry']}, TP: {', '.join(map(str, signal['tp']))}, SL: {signal['sl']}"
            await bot.send_message(chat_id=CHAT_ID, text=message)
            exchange = await create_exchange()
            await simulate_entry(signal, group_name, exchange)

# Main function
async def main():
    exchange = await create_exchange()
    try:
        await client.start(phone=PHONE_NUMBER)
        print("Telethon client started")
        proxy, _ = get_current_proxy()
        await bot.send_message(chat_id=CHAT_ID, text=f"Trading bot started, monitoring @Official_GCR and @THE_WOLFREAL using proxy {proxy['ip']}:{proxy['port']} ({proxy['location']})")
        asyncio.create_task(monitor_positions(exchange))
        await client.run_until_disconnected()
    except Exception as e:
        await bot.send_message(chat_id=CHAT_ID, text=f"Startup error: {e}. Falling back to no proxy.")
        print(f"Startup error: {e}")
    finally:
        if hasattr(exchange, 'session') and exchange.session:
            await exchange.session.close()

if __name__ == '__main__':
    asyncio.run(main())
