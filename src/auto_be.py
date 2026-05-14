import os
import asyncio
import ccxt.async_support as ccxt_async
import trading
from dotenv import load_dotenv

load_dotenv()

RR_TARGET = float(os.getenv("BE_RR_TRIGGER", "0.8"))
SANDBOX_MODE = os.getenv("BITGET_SANDBOX", "true").lower() == "true"
DEBUG_WS_PRICE = os.getenv("DEBUG_WS_PRICE", "true").lower() == "true"

_async_bitget = None
_active_monitors = {}

async def get_async_exchange():
    global _async_bitget
    if _async_bitget is None:
        api_key = os.getenv('BITGET_API_KEY')
        secret = os.getenv('BITGET_API_SECRET')
        password = os.getenv('BITGET_PASSPHRASE')
        
        if not api_key:
            return None
            
        _async_bitget = ccxt_async.bitget({
            'apiKey': api_key,
            'secret': secret,
            'password': password,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        if SANDBOX_MODE:
            _async_bitget.set_sandbox_mode(True)
    return _async_bitget

async def price_monitor_task(symbol_ccxt, side, entry_price, sl_price, order_type="MARKET"):
    exchange = await get_async_exchange()
    if not exchange:
        return

    _active_monitors[symbol_ccxt] = asyncio.current_task()

    side = side.upper()
    sl_dist = abs(entry_price - sl_price)
    
    is_filled = (order_type.upper() == "MARKET")
    
    if side == 'LONG':
        target_price = entry_price + (RR_TARGET * sl_dist)
    else:
        target_price = entry_price - (RR_TARGET * sl_dist)
        
    print(f"👀 [AUTO BE] WS Monitor {symbol_ccxt} {side}")
    print(f"   Entry: {entry_price} | SL: {sl_price} | BE Trigger ({RR_TARGET} RR): {target_price}")

    try:
        last_check_time = asyncio.get_event_loop().time()
        
        while True:
            ticker = await exchange.watch_ticker(symbol_ccxt)
            current_price = float(ticker['last'])
            
            if DEBUG_WS_PRICE:
                safe_symbol = symbol_ccxt.replace('/', '_').replace(':', '_')
                with open(f"live_price_{safe_symbol}.txt", "w", encoding="utf-8") as f:
                    f.write(f"[{symbol_ccxt}] Live Price: {current_price}")
            
            trigger_target = False
            trigger_sl = False
            
            if not is_filled:
                if side == 'LONG' and current_price <= entry_price:
                    print(f"✅ [AUTO BE] Order LIMIT LONG {symbol_ccxt} terjemput di harga {current_price}!")
                    is_filled = True
                elif side == 'SHORT' and current_price >= entry_price:
                    print(f"✅ [AUTO BE] Order LIMIT SHORT {symbol_ccxt} terjemput di harga {current_price}!")
                    is_filled = True
            
            if is_filled:
                if side == 'LONG':
                    if current_price >= target_price: trigger_target = True
                    if current_price <= sl_price: trigger_sl = True
                else:
                    if current_price <= target_price: trigger_target = True
                    if current_price >= sl_price: trigger_sl = True
            
            now = asyncio.get_event_loop().time()
            if now - last_check_time > 300:
                last_check_time = now
                pos = await asyncio.to_thread(trading.get_open_position, symbol_ccxt, side)
                
                if not pos or float(pos.get('contracts', 0)) <= 0:
                    if not is_filled:
                        pass
                    else:
                        print(f"🧹 [AUTO BE] Posisi {symbol_ccxt} sepertinya sudah ditutup manual. Monitor dibatalkan.")
                        break
                
            if trigger_target:
                pos = await asyncio.to_thread(trading.get_open_position, symbol_ccxt, side)
                if pos and float(pos.get('contracts', 0)) > 0:
                    print(f"🎯 [AUTO BE] {symbol_ccxt} mencapai target RR {RR_TARGET} ({current_price})!")
                    mock_data = {"position_side": side, "stop_loss": entry_price}
                    
                    await asyncio.to_thread(trading.handle_move_sl, mock_data, symbol_ccxt)
                else:
                    print(f"🛑 [AUTO BE] Target tersentuh tapi tidak ada posisi aktif {symbol_ccxt}. Monitor dibatalkan.")
                break
                
            if trigger_sl:
                pos = await asyncio.to_thread(trading.get_open_position, symbol_ccxt, side)
                if not pos or float(pos.get('contracts', 0)) <= 0:
                    print(f"💥 [AUTO BE] {symbol_ccxt} terkena SL awal ({current_price}). Monitor dibatalkan.")
                    break
                    
    except asyncio.CancelledError:
        print(f"⏹️ [AUTO BE] Task dibatalkan manual oleh sistem untuk {symbol_ccxt}.")
    except Exception as e:
        print(f"⚠️ [AUTO BE WS] Error: {e}")
    finally:
        if symbol_ccxt in _active_monitors:
            del _active_monitors[symbol_ccxt]

def cancel_monitor(symbol_ccxt):
    """Membatalkan (kill) task websocket yang sedang berjalan untuk koin tertentu."""
    task = _active_monitors.get(symbol_ccxt)
    if task and not task.done():
        print(f"🛑 [AUTO BE] Membatalkan paksa monitor WS untuk {symbol_ccxt} karena sinyal CLOSE.")
        task.cancel()
