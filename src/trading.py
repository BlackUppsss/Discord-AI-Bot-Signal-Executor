import os
import ccxt
import json
from dotenv import load_dotenv

load_dotenv()

SANDBOX_MODE = os.getenv("BITGET_SANDBOX", "true").lower() == "true"

def bitget_futures_config(api_key, secret, password):
    return {
        'apiKey': api_key,
        'secret': secret,
        'password': password,
        'enableRateLimit': True,
        'has': {
            'fetchCurrencies': False,
        },
        'options': {
            'defaultType': 'swap',
            'defaultSubType': 'linear',
            'fetchMarkets': {
                'types': ['swap'],
            },
        },
    }

def patch_usdt_futures_market_loader(exchange):
    original = exchange.publicMixGetV2MixMarketContracts

    def usdt_futures_only(params={}):
        product_type = params.get('productType')
        if product_type == 'USDT-FUTURES':
            return original(params)
        return {'code': '00000', 'msg': 'success', 'data': []}

    exchange.publicMixGetV2MixMarketContracts = usdt_futures_only
    print("[TRADING] Bitget market loader restricted to productType=USDT-FUTURES")

def synthetic_usdt_swap_market(symbol_ccxt):
    base = symbol_ccxt.split('/')[0]
    market_id = f"{base}USDT"
    return {
        'id': market_id,
        'symbol': symbol_ccxt,
        'base': base,
        'quote': 'USDT',
        'settle': 'USDT',
        'baseId': base,
        'quoteId': 'USDT',
        'settleId': 'USDT',
        'type': 'swap',
        'spot': False,
        'margin': False,
        'swap': True,
        'future': False,
        'option': False,
        'active': True,
        'contract': True,
        'linear': True,
        'inverse': False,
        'contractSize': 1,
        'precision': {'amount': 0.000001, 'price': 0.000001},
        'limits': {'amount': {'min': None, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': None, 'max': None}},
        'info': {'symbol': market_id, 'symbolType': 'perpetual'},
    }

def ensure_usdt_swap_market(symbol_ccxt):
    if not bitget:
        return
    existing = getattr(bitget, 'markets', None) or {}
    markets = list(existing.values())
    if symbol_ccxt not in existing:
        markets.append(synthetic_usdt_swap_market(symbol_ccxt))
        bitget.set_markets(markets)
        print(f"[TRADING] Seeded USDT-FUTURES market metadata for {symbol_ccxt}")

def init_bitget():
    api_key = os.getenv('BITGET_API_KEY')
    secret = os.getenv('BITGET_API_SECRET')
    password = os.getenv('BITGET_PASSPHRASE')
    
    if not api_key or not secret or not password:
        return None
        
    exchange = ccxt.bitget(bitget_futures_config(api_key, secret, password))
    patch_usdt_futures_market_loader(exchange)
    
    if SANDBOX_MODE:
        exchange.set_sandbox_mode(True)
    print(
        "[TRADING] Bitget futures-only config | "
        f"fetchCurrencies={exchange.has.get('fetchCurrencies')} | "
        f"fetchMarkets.types={exchange.options.get('fetchMarkets', {}).get('types')}"
    )
    print(f"🔌 Bitget mode: {'DEMO/SANDBOX' if SANDBOX_MODE else '⚠️ LIVE'}")
    
    print("[TRADING] Skip startup load_markets; market metadata is seeded per USDT-FUTURES symbol.")
    
    return exchange

bitget = init_bitget()

MAX_POSITION_PCT = float(os.getenv('MAX_POSITION_PCT', '50'))
def to_ccxt_symbol(raw_symbol):
    """BTCUSDT -> BTC/USDT:USDT (aman untuk edge case seperti USTCUSDT)"""
    if not raw_symbol:
        return None
    sym = raw_symbol.upper().strip()
    if not sym.endswith("USDT"):
        sym += "USDT"
    idx = sym.rfind("USDT")
    coin = sym[:idx]
    if not coin:
        return None
    return f"{coin}/USDT:USDT"

def get_account_context_summary():
    """Mengambil ringkasan semua posisi aktif untuk dikirim ke AI sebagai konteks."""
    if not bitget:
        return "Info: Bitget belum terhubung."
    
    try:
        positions = bitget.fetch_positions()
        active_pos = []
        for p in positions:
            contracts = float(p.get('contracts', 0) or 0)
            if contracts > 0:
                sym = p.get('symbol', 'UNKNOWN')
                side = p.get('side', 'UNKNOWN')
                entry = p.get('entryPrice', 0)
                active_pos.append(f"- {sym} ({side}) | Entry Price: {entry}")
        
        if not active_pos:
            return "Info: Saat ini TIDAK ADA posisi yang terbuka (kosong)."
        
        return "Info Posisi Aktif Saat Ini di Bitget:\n" + "\n".join(active_pos)
    except Exception as e:
        return f"Info: Gagal mengecek posisi Bitget ({e})"


def get_open_position(symbol_ccxt, side=None):
    """
    Cek apakah sudah ada posisi aktif untuk symbol ini.
    Return dict posisi jika ada, None jika tidak.
    """
    try:
        positions = bitget.fetch_positions([symbol_ccxt])
        for p in positions:
            contracts = float(p.get('contracts', 0) or 0)
            if contracts <= 0:
                continue
            pos_side = (p.get('side') or '').lower()
            if side and pos_side != side.lower():
                continue
            return p
        return None
    except Exception as e:
        print(f"⚠️ Gagal cek posisi aktif: {e}")
        return None


def get_open_orders(symbol_ccxt, side=None):
    """
    Cek apakah ada pending limit orders untuk symbol ini.
    Return list of orders.
    """
    try:
        orders = bitget.fetch_open_orders(symbol_ccxt)
        if side:
            target_side = 'buy' if side.upper() == 'LONG' else 'sell'
            orders = [o for o in orders if o.get('side') == target_side]
        return orders
    except Exception as e:
        print(f"⚠️ Gagal cek open orders: {e}")
        return []

def calculate_position_size(symbol, entry_price, sl_price):
    try:
        balance = bitget.fetch_balance()
        total_equity = balance.get('USDT', {}).get('total', 0)
        
        if total_equity <= 0:
            print("❌ [RISK] Saldo USDT kosong.")
            return 0
            
        risk_percentage = float(os.getenv('RISK_PERCENTAGE', '5'))
        risk_amount = total_equity * (risk_percentage / 100)
        sl_distance = abs(entry_price - sl_price) / entry_price
        
        if sl_distance == 0:
            print("❌ [RISK] Jarak SL 0%.")
            return 0
            
        position_size_usdt = risk_amount / sl_distance
        
        max_allowed = total_equity * (MAX_POSITION_PCT / 100)
        if position_size_usdt > max_allowed:
            print(f"⚠️ Size {position_size_usdt:.2f} USDT melebihi {MAX_POSITION_PCT}% equity. Dicap ke {max_allowed:.2f} USDT.")
            position_size_usdt = max_allowed
        
        position_size_coin = position_size_usdt / entry_price
        
        min_notional = float(os.getenv('MIN_ORDER_USDT', '5'))
        if position_size_usdt < min_notional:
            print(f"❌ Order terlalu kecil: ${position_size_usdt:.2f} < ${min_notional}")
            return 0
        
        print(f"💰 Equity: {total_equity:.2f} USDT | Risk: {risk_amount:.2f} USDT ({risk_percentage}%)")
        print(f"📐 SL Distance: {sl_distance*100:.2f}% | Size: {position_size_coin:.4f} {symbol.split('/')[0]}")
        
        return position_size_coin
        
    except Exception as e:
        print(f"❌ [RISK ERROR] {e}")
        return 0


def validate_side(data):
    """Return side string atau None jika invalid."""
    side = data.get("position_side")
    if not side:
        print("❌ position_side tidak ditemukan di sinyal.")
        return None
    return side.upper()


def expand_sides(side):
    """'ALL' -> ['long', 'short'], 'LONG' -> ['long'], dll."""
    if side == 'ALL':
        return ['long', 'short']
    return [side.lower()]


def validate_sl(side, entry_price, sl_price):
    """Pastikan SL masuk akal — LONG: SL < entry, SHORT: SL > entry."""
    if side.upper() == 'LONG' and sl_price >= entry_price:
        print(f"❌ SL ({sl_price}) >= Entry ({entry_price}) untuk LONG? Tidak valid!")
        return False
    if side.upper() == 'SHORT' and sl_price <= entry_price:
        print(f"❌ SL ({sl_price}) <= Entry ({entry_price}) untuk SHORT? Tidak valid!")
        return False
    return True

def handle_open(data, symbol_ccxt):
    side = validate_side(data)
    if not side:
        return
    ensure_usdt_swap_market(symbol_ccxt)
    
    order_type_str = data.get("order_type", "LIMIT").upper()
    
    existing_pos = get_open_position(symbol_ccxt, side)
    if existing_pos:
        contracts = existing_pos.get('contracts', 0)
        entry = existing_pos.get('entryPrice', '?')
        print(f"⛔ SKIP — Sudah ada posisi {side} {symbol_ccxt} (size: {contracts}, entry: {entry})")
        return
    
    existing_orders = get_open_orders(symbol_ccxt, side)
    if existing_orders:
        print(f"⛔ SKIP — Sudah ada {len(existing_orders)} pending order {side} {symbol_ccxt}")
        for o in existing_orders:
            print(f"   Order #{o.get('id')} | {o.get('type')} @ {o.get('price')} | size: {o.get('amount')}")
        return
    
    if order_type_str == "MARKET":
        print("ℹ️ MARKET order: Mengambil harga aktual...")
        ticker = bitget.fetch_ticker(symbol_ccxt)
        entry_price = float(ticker['last'])
        print(f"📊 Harga saat ini: {entry_price}")
    else:
        entry_zones = data.get("entry_zone", [])
        if not entry_zones:
            print("❌ Tidak ada harga entry untuk LIMIT order.")
            return
        entry_price = float(entry_zones[0])
    
    sl_price = data.get("stop_loss")
    if not sl_price:
        print("❌ Tidak ada SL. Eksekusi dibatalkan demi keamanan!")
        return
    sl_price = float(sl_price)
    
    if not validate_sl(side, entry_price, sl_price):
        return
    
    size_coin = calculate_position_size(symbol_ccxt, entry_price, sl_price)
    if size_coin <= 0:
        return
    formatted_size = float(bitget.amount_to_precision(symbol_ccxt, size_coin))
    
    leverage = int(data.get("leverage") or os.getenv("DEFAULT_LEVERAGE", "20"))
    try:
        bitget.set_leverage(leverage, symbol_ccxt)
        print(f"⚙️ Leverage: {leverage}x")
    except Exception as e:
        print(f"⚠️ Gagal set leverage: {e}")
    
    order_side = 'buy' if side == 'LONG' else 'sell'
    params = {
        'stopLoss': {'triggerPrice': sl_price},
        'hedged': True,
        'marginMode': 'cross',
    }
    
    take_profits = data.get("take_profit", [])
    if take_profits:
        params['takeProfit'] = {'triggerPrice': float(take_profits[0])}
    
    print(f"\n🚀 {order_type_str} {order_side.upper()} {symbol_ccxt} | Size: {formatted_size} | Entry: {entry_price} | SL: {sl_price}")
    
    if order_type_str == "MARKET":
        order = bitget.create_order(
            symbol=symbol_ccxt, type='market', side=order_side,
            amount=formatted_size, params=params
        )
    else:
        order = bitget.create_order(
            symbol=symbol_ccxt, type='limit', side=order_side,
            amount=formatted_size, price=entry_price, params=params
        )
    
    print(f"✅ ORDER BERHASIL! ID: {order.get('id')}")
    return {
        "action": "OPEN",
        "symbol": symbol_ccxt,
        "side": side,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "order_type": order_type_str
    }


def handle_close(data, symbol_ccxt):
    side = validate_side(data)
    if not side:
        return
    
    closed_any = False
    for s in expand_sides(side):
        pos = get_open_position(symbol_ccxt, s)
        if not pos:
            print(f"📭 Tidak ada posisi {s.upper()} {symbol_ccxt} untuk ditutup.")
            continue
        
        contracts = float(pos.get('contracts', 0))
        close_side = 'sell' if s == 'long' else 'buy'
        
        print(f"🔻 Menutup {s.upper()} {symbol_ccxt} (size: {contracts})...")
        
        order = bitget.create_order(
            symbol=symbol_ccxt, type='market', side=close_side,
            amount=contracts,
            params={'hedged': True, 'reduceOnly': True, 'marginMode': 'cross'}
        )
        print(f"✅ Posisi {s.upper()} ditutup! ID: {order.get('id')}")
        closed_any = True
    
    if not closed_any:
        print(f"📭 Tidak ada posisi aktif {symbol_ccxt} untuk ditutup.")


def handle_cancel(data, symbol_ccxt):
    side = validate_side(data)
    if not side:
        return
    
    orders = get_open_orders(symbol_ccxt, side if side != 'ALL' else None)
    
    if not orders:
        print(f"📭 Tidak ada pending order {symbol_ccxt} untuk dibatalkan.")
        return
    
    print(f"🗑️ Membatalkan {len(orders)} pending order {symbol_ccxt}...")
    for o in orders:
        try:
            bitget.cancel_order(o['id'], symbol_ccxt)
            print(f"   ✅ Order #{o['id']} dibatalkan ({o.get('side')} @ {o.get('price')})")
        except Exception as e:
            print(f"   ❌ Gagal cancel #{o['id']}: {e}")


def handle_move_sl(data, symbol_ccxt):
    side = validate_side(data)
    if not side:
        return
    
    new_sl = data.get("stop_loss")
    if not new_sl:
        print("❌ Tidak ada harga SL baru yang diberikan.")
        return
    new_sl = float(new_sl)
    
    for s in expand_sides(side):
        pos = get_open_position(symbol_ccxt, s)
        if not pos:
            print(f"📭 Tidak ada posisi {s.upper()} {symbol_ccxt} untuk update SL.")
            continue
        
        old_sl = pos.get('stopLossPrice') or pos.get('info', {}).get('stopLossPrice', '?')
        print(f"🔧 Memindahkan SL {s.upper()} {symbol_ccxt}: {old_sl} → {new_sl}")
        
        try:
            params = {
                'stopLoss': {'triggerPrice': new_sl},
                'hedged': True,
                'marginMode': 'cross',
            }
            
            take_profits = data.get("take_profit", [])
            if take_profits:
                params['takeProfit'] = {'triggerPrice': float(take_profits[0])}
            
            bitget.edit_position(
                symbol=symbol_ccxt,
                side=s,
                params=params,
            )
            print(f"✅ SL {s.upper()} berhasil dipindah ke {new_sl}")
            
        except (AttributeError, ccxt.NotSupported):
            print(f"⚠️ Fallback: edit_position tidak tersedia...")
            try:
                contracts = float(pos.get('contracts', 0))
                close_side = 'sell' if s == 'long' else 'buy'
                bitget.create_order(
                    symbol=symbol_ccxt, type='market', side=close_side,
                    amount=contracts,
                    params={
                        'stopLossPrice': new_sl,
                        'hedged': True,
                        'reduceOnly': True,
                        'marginMode': 'cross',
                    }
                )
                print(f"✅ [Fallback] SL diatur ke {new_sl}")
            except Exception as e2:
                print(f"🚨 Gagal update SL: {e2}")
                
        except Exception as e:
            print(f"🚨 Gagal update SL: {e}")


def handle_take_profit(data, symbol_ccxt):
    side = validate_side(data)
    if not side:
        return
    ensure_usdt_swap_market(symbol_ccxt)
    
    tp_percentage = data.get("tp_percentage", 100)
    
    for s in expand_sides(side):
        pos = get_open_position(symbol_ccxt, s)
        if not pos:
            print(f"📭 Tidak ada posisi {s.upper()} {symbol_ccxt} untuk TP.")
            continue
        
        contracts = float(pos.get('contracts', 0))
        close_amount = contracts * (tp_percentage / 100)
        close_amount = float(bitget.amount_to_precision(symbol_ccxt, close_amount))
        close_side = 'sell' if s == 'long' else 'buy'
        
        print(f"💰 TP {s.upper()} {symbol_ccxt}: Menutup {tp_percentage}% ({close_amount} dari {contracts})...")
        
        order = bitget.create_order(
            symbol=symbol_ccxt, type='market', side=close_side,
            amount=close_amount,
            params={'hedged': True, 'reduceOnly': True, 'marginMode': 'cross'}
        )
        print(f"✅ TP berhasil! ID: {order.get('id')}")

def execute_trade(signal_json):
    if not bitget:
        print("⚠️ API Key Bitget belum disetting di .env. Skip.")
        return
        
    try:
        data = json.loads(signal_json)
        
        if not data.get("is_signal"):
            return
            
        action = (data.get("action") or "").upper()
        symbol_ccxt = to_ccxt_symbol(data.get("symbol"))
        
        if not symbol_ccxt:
            print("❌ Symbol tidak ditemukan di sinyal.")
            return
        
        ensure_usdt_swap_market(symbol_ccxt)
        print(f"\n{'='*50}")
        print(f"📨 Action: {action} | Symbol: {symbol_ccxt} | Side: {data.get('position_side')}")
        print(f"{'='*50}")
        
        if action == "OPEN":
            return handle_open(data, symbol_ccxt)
        elif action == "CLOSE":
            handle_close(data, symbol_ccxt)
            return {"action": "CLOSE", "symbol": symbol_ccxt}
        elif action == "CANCEL":
            handle_cancel(data, symbol_ccxt)
            return {"action": "CANCEL", "symbol": symbol_ccxt}
        elif action == "MOVE_SL":
            handle_move_sl(data, symbol_ccxt)
        elif action == "TAKE_PROFIT":
            handle_take_profit(data, symbol_ccxt)
        else:
            print(f"⚠️ Action '{action}' tidak dikenali. Skip.")
            
        return None
        
    except Exception as e:
        print(f"🚨 [TRADE ERROR] {e}")
