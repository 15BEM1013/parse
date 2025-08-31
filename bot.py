import os
import re
import asyncio
from telethon import TelegramClient
from telethon.events import NewMessage
import ccxt
from telegram import Bot

# Telegram config
BOT_TOKEN = '7662307654:AAG5-juB1faNaFZfC8zjf4LwlZMzs6lEmtE'
CHAT_ID = '655537138'
API_ID = 20102847  # Your provided API ID
API_HASH = 'f273163ee37a3fff0e98a5e022ebc930'  # Your provided API hash
PHONE_NUMBER = '+919988143599'  # Your provided phone number

# CCXT Binance setup (read-only for price fetching)
exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY', ''),
    'secret': os.getenv('BINANCE_API_SECRET', ''),
    'enableRateLimit': True,
})

# Store simulated positions
open_positions = []  # [{'symbol': 'AXSUSDT', 'side': 'LONG', 'entry': float, 'quantity': float, 'tp': [float], 'sl': float, 'group': str}]

# Initialize Telethon client
client = TelegramClient('trading_bot_session', API_ID, API_HASH)

# Initialize Telegram bot for sending messages
bot = Bot(BOT_TOKEN)

# Parse signals from both groups
def parse_signal(message_text, group_name):
    signal = None
    if group_name == '@Official_GCR':
        # Example: "Coin #AXS/USDT Position: LONG Leverage: Cross35X Entries: 2.63 - 2.58 Targets: 🎯 2.68, 2.73, 2.78, 2.83, 2.88 Stop Loss: 2.53"
        match = re.search(r'Coin #(\w+/USDT)\s+Position:\s*(LONG|SHORT)\s+Leverage:.*Entries:\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s+Targets:.*?([\d\.]+(?:,\s*[\d\.]+)*)\s+Stop Loss:\s*(\d+\.?\d*)', message_text, re.IGNORECASE)
        if match:
            symbol = match.group(1).replace('/', '').upper()
            side = match.group(2).upper()
            entry_low = float(match.group(4))
            tp_list = [float(tp) for tp in match.group(5).split(',')]
            sl = float(match.group(6))
            signal = {'symbol': symbol, 'side': side, 'entry': entry_low, 'tp': tp_list, 'sl': sl}
    
    elif group_name == '@THE_WOLFREAL':
        # Example: "COIN NAME: M(USDT) LEVERAGE: 75x TRADE TYPE: LONG 📈 ENTRY PRICE (0.5570-0.5460) TAKE-PROFITS 1️⃣ 0.5660 2️⃣ 0.5800 3️⃣ 0.6000 STOP LOSS: 0.5300"
        match = re.search(r'COIN NAME:\s*(\w+)\(USDT\).*TRADE TYPE:\s*(LONG|SHORT).*ENTRY PRICE\s*\((\d+\.?\d*)-(\d+\.?\d*)\).*TAKE-PROFITS\s+1️⃣\s*(\d+\.?\d*)\s+2️⃣\s*(\d+\.?\d*)\s+3️⃣\s*(\d+\.?\d*)\s+STOP LOSS:\s*(\d+\.?\d*)', message_text, re.IGNORECASE)
        if match:
            symbol = match.group(1).upper() + 'USDT'
            side = match.group(2).upper()
            entry_low = float(match.group(4))
            tp_list = [float(match.group(i)) for i in range(5, 8)]
            sl = float(match.group(8))
            signal = {'symbol': symbol, 'side': side, 'entry': entry_low, 'tp': tp_list, 'sl': sl}
    
    return signal

# Simulate trade entry
async def simulate_entry(signal, group_name):
    try:
        ticker = exchange.fetch_ticker(signal['symbol'])
        current_price = ticker['last']
        
        # Enter if current price within 1% of signal entry
        if abs(current_price - signal['entry']) / signal['entry'] > 0.01:
            await bot.send_message(chat_id=CHAT_ID, text=f"[{group_name}] Ignoring {signal['side']} {signal['symbol']}: Entry {signal['entry']} too far from current {current_price}")
            return
        
        quantity = 0.001  # Fixed for sim
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
        
        message = f"[{group_name}] Simulated ENTRY: {signal['side']} {signal['symbol']} at {current_price}, Quantity: {quantity}, TP: {', '.join(map(str, signal['tp']))}, SL: {signal['sl']}"
        await bot.send_message(chat_id=CHAT_ID, text=message)
    
    except Exception as e:
        await bot.send_message(chat_id=CHAT_ID, text=f"[{group_name}] Error simulating entry for {signal['symbol']}: {str(e)}")

# Monitor positions for TP/SL
async def monitor_positions():
    while True:
        for pos in open_positions[:]:
            try:
                ticker = exchange.fetch_ticker(pos['symbol'])
                current_price = ticker['last']
                
                # Calculate PNL (spot-style)
                if pos['side'] == 'LONG':
                    pnl = (current_price - pos['entry']) * pos['quantity']
                    hit_tp = any(current_price >= tp for tp in pos['tp'])
                    hit_sl = current_price <= pos['sl']
                else:  # SHORT
                    pnl = (pos['entry'] - current_price) * pos['quantity']
                    hit_tp = any(current_price <= tp for tp in pos['tp'])
                    hit_sl = current_price >= pos['sl']
                
                if hit_tp or hit_sl:
                    close_price = current_price
                    message = f"[{pos['group']}] Simulated EXIT: {pos['side']} {pos['symbol']} at {close_price}, PNL: {pnl:.2f} USDT ({'TP' if hit_tp else 'SL'})"
                    await bot.send_message(chat_id=CHAT_ID, text=message)
                    open_positions.remove(pos)
                
            except Exception as e:
                await bot.send_message(chat_id=CHAT_ID, text=f"[{pos['group']}] Error monitoring {pos['symbol']}: {str(e)}")
        
        await asyncio.sleep(60)  # Check every minute

# Handle new messages
@client.on(NewMessage(chats=['@Official_GCR', '@THE_WOLFREAL']))
async def handle_message(event):
    message_text = event.message.text
    group_name = event.chat.username
    if message_text and group_name:
        signal = parse_signal(message_text, group_name)
        if signal:
            message = f"[{group_name}] Signal detected: {signal['side']} {signal['symbol']} at {signal['entry']}, TP: {', '.join(map(str, signal['tp']))}, SL: {signal['sl']}"
            await bot.send_message(chat_id=CHAT_ID, text=message)
            await simulate_entry(signal, group_name)

# Main function
async def main():
    # Start Telethon client
    await client.start(phone=PHONE_NUMBER)
    print("Telethon client started")
    
    # Notify CHAT_ID of startup
    await bot.send_message(chat_id=CHAT_ID, text="Trading bot started, monitoring @Official_GCR and @THE_WOLFREAL")
    
    # Start monitoring positions
    asyncio.create_task(monitor_positions())
    
    # Run client
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
