import os
import asyncio
import json
import contextlib
import websockets
import trading
from dotenv import load_dotenv

load_dotenv()

RR_TARGET = float(os.getenv("BE_RR_TRIGGER", "0.8"))
DEBUG_WS_PRICE = os.getenv("DEBUG_WS_PRICE", "true").lower() == "true"
DEBUG_WS_RAW = os.getenv("DEBUG_WS_RAW", "false").lower() == "true"
WS_RECONNECT_DELAY_SEC = float(os.getenv("WS_RECONNECT_DELAY_SEC", "5"))
WS_RECEIVE_TIMEOUT_SEC = float(os.getenv("WS_RECEIVE_TIMEOUT_SEC", "45"))
WS_TEXT_PING_INTERVAL_SEC = float(os.getenv("WS_TEXT_PING_INTERVAL_SEC", "25"))
SANDBOX_MODE = os.getenv("BITGET_SANDBOX", "true").lower() == "true"

BITGET_WS_LIVE_PUBLIC_URL = "wss://ws.bitget.com/v2/ws/public"
BITGET_WS_DEMO_PUBLIC_URL = "wss://wspap.bitget.com/v2/ws/public"


def _resolve_ws_public_url():
    override = os.getenv("BITGET_WS_PUBLIC_URL", "").strip()
    if override:
        return override
    return BITGET_WS_DEMO_PUBLIC_URL if SANDBOX_MODE else BITGET_WS_LIVE_PUBLIC_URL


BITGET_WS_PUBLIC_URL = _resolve_ws_public_url()

_active_monitors = {}


def _symbol_to_inst_id(symbol_ccxt):
    """BTC/USDT:USDT -> BTCUSDT"""
    return symbol_ccxt.split("/")[0] + "USDT"


async def _ws_ticker_stream(inst_id):
    """
    Generator async: sambungkan ke Bitget public WS, subscribe ticker,
    dan yield harga setiap kali ada update.
    Otomatis handle ping/pong dari server Bitget.
    """
    subscribe_msg = json.dumps({
        "op": "subscribe",
        "args": [{
            "instType": "USDT-FUTURES",
            "channel": "ticker",
            "instId": inst_id
        }]
    })

    async def _bitget_text_ping_loop(ws_conn, inst):
        while True:
            await asyncio.sleep(WS_TEXT_PING_INTERVAL_SEC)
            await ws_conn.send("ping")
            if DEBUG_WS_RAW:
                print(f"[AUTO BE WS RAW] text ping sent for {inst}")

    ws = None
    keepalive_task = None
    try:
        async with websockets.connect(
            BITGET_WS_PUBLIC_URL,
            open_timeout=30,
            close_timeout=10,
            ping_interval=None,
            ping_timeout=None,
            max_queue=32,
            compression=None,
        ) as ws:
            await ws.send(subscribe_msg)
            keepalive_task = asyncio.create_task(_bitget_text_ping_loop(ws, inst_id))
            print(f"[AUTO BE WS] Terhubung & subscribe ticker {inst_id} ke {BITGET_WS_PUBLIC_URL}")

            while True:
                try:
                    text = await asyncio.wait_for(ws.recv(), timeout=WS_RECEIVE_TIMEOUT_SEC)
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Tidak ada data WS > {WS_RECEIVE_TIMEOUT_SEC:g}s")

                if DEBUG_WS_RAW:
                    print(f"[AUTO BE WS RAW] {text}")

                if text == "ping":
                    await ws.send("pong")
                    continue

                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    continue

                if data.get("event") == "subscribe":
                    print(f"[AUTO BE WS] Subscribe dikonfirmasi oleh server untuk {inst_id}")
                    continue
                if data.get("event") == "error":
                    print(f"[AUTO BE WS] Error dari server: {data}")
                    raise RuntimeError(f"Bitget WS error: {data}")

                ticker_list = data.get("data")
                if ticker_list and isinstance(ticker_list, list):
                    for tick in ticker_list:
                        last_price = tick.get("lastPr") or tick.get("last")
                        if last_price is None:
                            continue
                        try:
                            yield float(last_price)
                        except (TypeError, ValueError):
                            continue
    except asyncio.CancelledError:
        print(f"[AUTO BE WS] Task monitor dibatalkan, menutup koneksi WS {inst_id}.")
        raise
    except websockets.exceptions.ConnectionClosedOK as e:
        print(f"[AUTO BE WS] Koneksi WS ditutup normal ({inst_id}): {e}")
    except websockets.exceptions.ConnectionClosedError as e:
        raise RuntimeError(f"Koneksi WS terputus tidak normal ({inst_id}): {e}") from e
    finally:
        if keepalive_task:
            keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive_task


async def price_monitor_task(symbol_ccxt, side, entry_price, sl_price, order_type="MARKET"):
    side = side.upper()
    monitor_key = f"{symbol_ccxt}:{side}"
    _active_monitors[monitor_key] = asyncio.current_task()

    sl_dist = abs(entry_price - sl_price)
    is_filled = (order_type.upper() == "MARKET")
    inst_id = _symbol_to_inst_id(symbol_ccxt)

    if side == "LONG":
        target_price = entry_price + (RR_TARGET * sl_dist)
    else:
        target_price = entry_price - (RR_TARGET * sl_dist)

    print(f"[AUTO BE] WebSocket Price Monitor {symbol_ccxt} {side}")
    print(f"[AUTO BE] Mode: {'DEMO/SANDBOX' if SANDBOX_MODE else 'LIVE'} | WS: {BITGET_WS_PUBLIC_URL}")
    print(f"   Entry: {entry_price} | SL: {sl_price} | BE Trigger ({RR_TARGET} RR): {target_price}")

    retry_count = 0
    max_retries = 10

    try:
        while retry_count < max_retries:
            try:
                last_check_time = asyncio.get_event_loop().time()

                async for current_price in _ws_ticker_stream(inst_id):
                    retry_count = 0

                    if DEBUG_WS_PRICE:
                        safe_symbol = symbol_ccxt.replace("/", "_").replace(":", "_")
                        with open(f"live_price_{safe_symbol}.txt", "w", encoding="utf-8") as f:
                            f.write(f"[{symbol_ccxt}] Live Price: {current_price}")

                    trigger_target = False
                    trigger_sl = False

                    if not is_filled:
                        if side == "LONG" and current_price <= entry_price:
                            print(f"[AUTO BE] Order LIMIT LONG {symbol_ccxt} terjemput di harga {current_price}.")
                            is_filled = True
                        elif side == "SHORT" and current_price >= entry_price:
                            print(f"[AUTO BE] Order LIMIT SHORT {symbol_ccxt} terjemput di harga {current_price}.")
                            is_filled = True

                    if is_filled:
                        if side == "LONG":
                            if current_price >= target_price:
                                trigger_target = True
                            if current_price <= sl_price:
                                trigger_sl = True
                        else:
                            if current_price <= target_price:
                                trigger_target = True
                            if current_price >= sl_price:
                                trigger_sl = True

                    now = asyncio.get_event_loop().time()
                    if now - last_check_time > 300:
                        last_check_time = now
                        pos = await asyncio.to_thread(trading.get_open_position, symbol_ccxt, side)
                        if not pos or float(pos.get("contracts", 0)) <= 0:
                            if not is_filled:
                                pass
                            else:
                                print(f"[AUTO BE] Posisi {symbol_ccxt} sudah ditutup manual. Monitor dibatalkan.")
                                return

                    if trigger_target:
                        pos = await asyncio.to_thread(trading.get_open_position, symbol_ccxt, side)
                        if pos and float(pos.get("contracts", 0)) > 0:
                            print(f"[AUTO BE] {symbol_ccxt} mencapai target RR {RR_TARGET} ({current_price}).")
                            mock_data = {"position_side": side, "stop_loss": entry_price}
                            await asyncio.to_thread(trading.handle_move_sl, mock_data, symbol_ccxt)
                        else:
                            print(f"[AUTO BE] Target tersentuh tapi tidak ada posisi aktif {symbol_ccxt}. Monitor dibatalkan.")
                        return

                    if trigger_sl:
                        pos = await asyncio.to_thread(trading.get_open_position, symbol_ccxt, side)
                        if not pos or float(pos.get("contracts", 0)) <= 0:
                            print(f"[AUTO BE] {symbol_ccxt} terkena SL awal ({current_price}). Monitor dibatalkan.")
                            return

                if is_filled:
                    pos = await asyncio.to_thread(trading.get_open_position, symbol_ccxt, side)
                    if not pos or float(pos.get("contracts", 0)) <= 0:
                        print(f"[AUTO BE WS] Posisi {symbol_ccxt} sudah tidak ada. Stop reconnect monitor.")
                        return

                retry_count += 1
                delay = min(WS_RECONNECT_DELAY_SEC * retry_count, 60)
                print(f"[AUTO BE WS] Koneksi terputus untuk {inst_id}; retry {retry_count}/{max_retries} dalam {delay:g}s...")
                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                if is_filled:
                    pos = await asyncio.to_thread(trading.get_open_position, symbol_ccxt, side)
                    if not pos or float(pos.get("contracts", 0)) <= 0:
                        print(f"[AUTO BE WS] Posisi {symbol_ccxt} sudah tidak ada setelah error WS. Stop reconnect monitor.")
                        return
                retry_count += 1
                delay = min(WS_RECONNECT_DELAY_SEC * retry_count, 60)
                print(f"[AUTO BE WS] Error ({type(e).__name__}: {e}); retry {retry_count}/{max_retries} dalam {delay:g}s...")
                await asyncio.sleep(delay)

        print(f"[AUTO BE WS] Gagal terhubung setelah {max_retries} retry. Monitor {symbol_ccxt} dihentikan.")

    except asyncio.CancelledError:
        print(f"[AUTO BE] Task dibatalkan manual oleh sistem untuk {symbol_ccxt}.")
    except Exception as e:
        print(f"[AUTO BE] Error: {e}")
    finally:
        if monitor_key in _active_monitors:
            del _active_monitors[monitor_key]


def cancel_monitor(symbol_ccxt, side=None):
    """Batalkan monitor untuk symbol (semua side) atau symbol+side tertentu."""
    keys = []
    if side:
        keys = [f"{symbol_ccxt}:{side.upper()}"]
    else:
        prefix = f"{symbol_ccxt}:"
        keys = [k for k in _active_monitors.keys() if k.startswith(prefix)]

    for key in keys:
        task = _active_monitors.get(key)
        if task and not task.done():
            print(f"[AUTO BE] Membatalkan monitor harga untuk {key} karena sinyal CLOSE.")
            task.cancel()
