"""
monitor.py — Real-time Position Monitor dengan Auto-Move SL to Break Even
=========================================================================
Cara kerja:
1. Fetch semua posisi aktif dari Bitget via REST (saat startup & periodik).
2. Subscribe ke WebSocket ticker untuk semua symbol yang sedang ada posisi.
3. Setiap tick harga masuk, periksa apakah posisi sudah mencapai +0.80 RR.
4. Jika sudah, pindahkan Stop Loss ke harga entry (Break Even) via REST API.
5. Posisi yang sudah di-BE di-track agar tidak berulang kali di-update.

Dependency: ccxt.pro (included in ccxt, lihat requirements.txt)
Jalankan: python monitor.py  (paralel dengan listener.py)
"""

import os
import time
import asyncio
import ccxt.pro as ccxtpro
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Konfigurasi
# ─────────────────────────────────────────────
RR_TRIGGER      = float(os.getenv("BE_RR_TRIGGER", "0.80"))
POLL_INTERVAL   = int(os.getenv("POSITION_POLL_SEC", "30"))
SANDBOX_MODE    = os.getenv("BITGET_SANDBOX", "true").lower() == "true"

# ─────────────────────────────────────────────
# State global
# ─────────────────────────────────────────────
# Format: { "BTC/USDT:USDT_long": True, ... }
be_moved: dict[str, bool] = {}

# ─────────────────────────────────────────────
# Inisialisasi exchange (async)
# ─────────────────────────────────────────────
def build_exchange() -> ccxtpro.bitget:
    api_key  = os.getenv("BITGET_API_KEY")
    secret   = os.getenv("BITGET_API_SECRET")
    password = os.getenv("BITGET_PASSPHRASE")

    if not all([api_key, secret, password]):
        raise EnvironmentError("❌  BITGET_API_KEY / SECRET / PASSPHRASE belum diisi di .env!")

    exchange = ccxtpro.bitget({
        "apiKey":          api_key,
        "secret":          secret,
        "password":        password,
        "enableRateLimit": True,
        "options": {
            "defaultType": "swap",
        },
    })

    if SANDBOX_MODE:
        exchange.set_sandbox_mode(True)

    return exchange


# ─────────────────────────────────────────────
# Helper: Fetch semua posisi aktif
# ─────────────────────────────────────────────
async def fetch_open_positions(exchange: ccxtpro.bitget) -> list[dict]:
    """
    Kembalikan list posisi aktif dengan field yang kita butuhkan:
    { symbol, side, entry_price, sl_price, size, position_key }
    """
    raw = await exchange.fetch_positions()
    positions = []
    for p in raw:
        contracts = p.get("contracts") or p.get("contractSize") or 0
        if not contracts or float(contracts) == 0:
            continue

        entry = p.get("entryPrice") or p.get("info", {}).get("openPriceAvg")
        sl    = p.get("stopLossPrice") or p.get("info", {}).get("stopLossPrice")
        side  = p.get("side", "").lower()
        sym   = p.get("symbol")

        if not entry or not sl or not sym or not side:
            continue

        position_key = f"{sym}_{side}"

        positions.append({
            "symbol":       sym,
            "side":         side,
            "entry_price":  float(entry),
            "sl_price":     float(sl),
            "size":         float(contracts),
            "position_key": position_key,
            "raw":          p,
        })

    return positions


# ─────────────────────────────────────────────
# Helper: Cek apakah harga mencapai +RR trigger
# ─────────────────────────────────────────────
def check_rr_reached(pos: dict, current_price: float, rr_trigger: float = RR_TRIGGER) -> bool:
    entry = pos["entry_price"]
    sl    = pos["sl_price"]
    side  = pos["side"]

    risk = abs(entry - sl)
    if risk == 0:
        return False

    if side == "long":
        target_price = entry + (risk * rr_trigger)
        return current_price >= target_price
    else:
        target_price = entry - (risk * rr_trigger)
        return current_price <= target_price


# ─────────────────────────────────────────────
# Core: Pindahkan SL ke Break Even
# ─────────────────────────────────────────────
async def move_sl_to_be(exchange: ccxtpro.bitget, pos: dict):
    sym   = pos["symbol"]
    side  = pos["side"]
    entry = pos["entry_price"]
    sl    = pos["sl_price"]
    key   = pos["position_key"]

    print(f"\n🎯 [{sym} {side.upper()}] Mencapai +{RR_TRIGGER} RR!")
    print(f"   Entry: {entry}  |  SL Lama: {sl}  →  SL Baru (BE): {entry}")

    try:
        params = {
            "stopLoss": {
                "triggerPrice": entry,
            },
            "hedged":     True,
            "marginMode": "cross",
        }

        await exchange.edit_position(
            symbol = sym,
            side   = side,
            params = params,
        )
        be_moved[key] = True
        print(f"✅ SL berhasil dipindah ke BE ({entry}) untuk {sym} {side.upper()}")

    except AttributeError:
        print(f"⚠️  edit_position tidak tersedia, mencoba fallback...")
        await _fallback_set_sl(exchange, pos, new_sl=entry)

    except Exception as e:
        print(f"🚨 Gagal move SL ke BE untuk {key}: {e}")


async def _fallback_set_sl(exchange: ccxtpro.bitget, pos: dict, new_sl: float):
    """Fallback: set SL via create_order."""
    sym   = pos["symbol"]
    side  = pos["side"]
    key   = pos["position_key"]
    close_side = "sell" if side == "long" else "buy"

    try:
        params = {
            "stopLossPrice": new_sl,
            "hedged":        True,
            "reduceOnly":    True,
            "marginMode":    "cross",
        }
        await exchange.create_order(
            symbol = sym,
            type   = "market",
            side   = close_side,
            amount = pos["size"],
            params = params,
        )
        be_moved[key] = True
        print(f"✅ [Fallback] SL diatur ke BE ({new_sl}) untuk {sym} {side.upper()}")

    except Exception as e:
        print(f"🚨 [Fallback] Gagal: {e}")


# ─────────────────────────────────────────────
# Loop: WebSocket Ticker Watcher
# ─────────────────────────────────────────────
def supports_watch_tickers(exchange: ccxtpro.bitget) -> bool:
    return bool(getattr(exchange, "has", {}).get("watchTickers"))

async def watch_prices_loop(exchange: ccxtpro.bitget, positions_ref: list[dict]):
    """Subscribe ke ticker semua symbol yang aktif."""
    last_symbols = None
    last_print_time = 0.0

    while True:
        symbols = list({
            p["symbol"] for p in positions_ref
            if p["position_key"] not in be_moved
        })

        if not symbols:
            print("📭 Tidak ada posisi aktif yang belum BE. Menunggu...")
            await asyncio.sleep(POLL_INTERVAL)
            continue

        if symbols != last_symbols:
            print(f"📡 Mulai memantau WebSocket untuk: {symbols}")
            last_symbols = symbols

        try:
            if not supports_watch_tickers(exchange):
                raise ccxtpro.NotSupported(f"{exchange.id} watchTickers() tidak tersedia di ccxt.pro")

            tickers = await exchange.watch_tickers(symbols)

            for sym, ticker in tickers.items():
                current_price = ticker.get("last") or ticker.get("close")
                if not current_price:
                    continue

                # Heartbeat: print harga setiap 5 detik
                current_time = time.time()
                if current_time - last_print_time > 5:
                    print(f"⚡ [Live] {sym} : {current_price}")
                    last_print_time = current_time

                for pos in positions_ref:
                    if pos["symbol"] != sym:
                        continue
                    if pos["position_key"] in be_moved:
                        continue
                    if check_rr_reached(pos, float(current_price)):
                        await move_sl_to_be(exchange, pos)

        except ccxtpro.NetworkError as e:
            print(f"🔌 WebSocket terputus ({e}), reconnecting dalam 5 detik...")
            await asyncio.sleep(5)

        except ccxtpro.ExchangeError as e:
            print(f"⚠️ Exchange error: {e}")
            await asyncio.sleep(5)

        except Exception as e:
            print(f"🚨 Error: {e}")
            await asyncio.sleep(5)


# ─────────────────────────────────────────────
# Loop: Refresh Daftar Posisi Periodik
# ─────────────────────────────────────────────
async def fetch_positions_loop(exchange: ccxtpro.bitget, positions_ref: list[dict]):
    """Setiap POLL_INTERVAL detik, refresh daftar posisi aktif."""
    while True:
        try:
            new_positions = await fetch_open_positions(exchange)

            positions_ref.clear()
            positions_ref.extend(new_positions)

            # Bersihkan tracking untuk posisi yang sudah close
            active_keys = {p["position_key"] for p in new_positions}
            for key in list(be_moved.keys()):
                if key not in active_keys:
                    del be_moved[key]
                    print(f"🗑️  {key} sudah close, dihapus dari tracking BE.")

            if new_positions:
                print(f"\n📋 Posisi Aktif ({len(new_positions)}):")
                for p in new_positions:
                    be_tag = " ✅BE" if p["position_key"] in be_moved else ""
                    risk   = abs(p["entry_price"] - p["sl_price"])
                    print(
                        f"   {p['symbol']} {p['side'].upper()}{be_tag}"
                        f" | Entry: {p['entry_price']}"
                        f" | SL: {p['sl_price']}"
                        f" | Risk: {risk:.4f}"
                    )
            else:
                print("📭 Tidak ada posisi aktif saat ini.")

        except Exception as e:
            print(f"⚠️ Gagal refresh posisi: {e}")

        await asyncio.sleep(POLL_INTERVAL)


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────
async def main():
    exchange = build_exchange()

    print("=" * 50)
    print("🤖 MONITOR.PY — Auto Break-Even SL Manager")
    print(f"   RR Trigger  : +{RR_TRIGGER} RR → Move SL ke Entry")
    print(f"   Poll Interval: setiap {POLL_INTERVAL} detik")
    print(f"   Mode         : {'DEMO/SANDBOX' if SANDBOX_MODE else '⚠️  LIVE'}")
    print("=" * 50)

    print("⏳ Loading markets dari Bitget...")
    await exchange.load_markets()
    print("✅ Markets loaded.\n")

    shared_positions: list[dict] = []

    try:
        await asyncio.gather(
            fetch_positions_loop(exchange, shared_positions),
            watch_prices_loop(exchange, shared_positions),
        )
    finally:
        # Bersihkan koneksi WebSocket saat keluar
        await exchange.close()
        print("🔌 Koneksi exchange ditutup.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Monitor dihentikan oleh user.")
