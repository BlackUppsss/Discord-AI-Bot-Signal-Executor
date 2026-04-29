import os
import ccxt
import json
from dotenv import load_dotenv

load_dotenv()

# Inisialisasi CCXT Bitget Testnet (Demo)
def init_bitget():
    api_key = os.getenv('BITGET_API_KEY')
    secret = os.getenv('BITGET_API_SECRET')
    password = os.getenv('BITGET_PASSPHRASE')
    
    if not api_key or not secret or not password:
        return None
        
    exchange = ccxt.bitget({
        'apiKey': api_key,
        'secret': secret,
        'password': password,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap', # Setup untuk USDT-M Futures
        }
    })
    
    exchange.set_sandbox_mode(True) # Wajib agar masuk ke Testnet / Demo
    return exchange

bitget = init_bitget()

def calculate_position_size(symbol, entry_price, sl_price):
    try:
        # 1. Ambil saldo (Total Equity)
        balance = bitget.fetch_balance()
        # Saldo USDT di Bitget Futures Demo
        total_equity = balance.get('USDT', {}).get('total', 0)
        
        if total_equity <= 0:
            print("❌ [RISK] Saldo USDT kosong atau gagal ditarik.")
            return 0
            
        # 2. Ambil persentase risiko dari .env (default 5%)
        risk_percentage = float(os.getenv('RISK_PERCENTAGE', '5'))
        risk_amount = total_equity * (risk_percentage / 100)
        
        # 3. Hitung persentase jarak SL
        sl_distance = abs(entry_price - sl_price) / entry_price
        
        if sl_distance == 0:
            print("❌ [RISK] Jarak SL 0%, tidak bisa menghitung position size.")
            return 0
            
        # 4. Hitung position size dalam USDT, lalu konversi ke Coin/Base Asset
        position_size_usdt = risk_amount / sl_distance
        position_size_coin = position_size_usdt / entry_price
        
        print(f"💰 Equity: {total_equity:.2f} USDT | Risk: {risk_amount:.2f} USDT ({risk_percentage}%)")
        print(f"📐 SL Distance: {sl_distance*100:.2f}%")
        print(f"⚖️ Calculated Size: {position_size_usdt:.2f} USDT ({position_size_coin:.4f} {symbol.split('/')[0]})")
        
        return position_size_coin
        
    except Exception as e:
        print(f"❌ [RISK ERROR] Gagal menghitung position size: {e}")
        return 0

def execute_trade(signal_json):
    if not bitget:
        print("⚠️ API Key Bitget belum disetting di .env. Skip eksekusi.")
        return
        
    try:
        data = json.loads(signal_json)
        
        if not data.get("is_signal"):
            return # Abaikan jika bukan sinyal
            
        action = data.get("action")
        side = data.get("position_side")
        
        if action != "OPEN":
            print(f"ℹ️ Action '{action}' saat ini belum di-support untuk Auto-Trade.")
            return
            
        # Format Symbol (Misal BTCUSDT -> BTC/USDT:USDT untuk ccxt futures linear)
        symbol = data.get("symbol")
        if not symbol: return
        
        if not symbol.endswith("USDT"):
            symbol += "USDT"
            
        # Ubah ke format CCXT: BTCUSDT -> BTC/USDT:USDT
        coin = symbol.replace("USDT", "")
        symbol_ccxt = f"{coin}/USDT:USDT"
        
        order_type_str = data.get("order_type", "LIMIT").upper()
        
        if order_type_str == "MARKET":
            print("ℹ️ Sinyal MARKET: Mengambil harga aktual dari Bitget untuk kalkulasi risiko yang akurat...")
            bitget.load_markets()
            ticker = bitget.fetch_ticker(symbol_ccxt)
            entry_price = float(ticker['last'])
            print(f"📊 Harga Market saat ini di Bitget: {entry_price}")
        else:
            entry_zones = data.get("entry_zone", [])
            if not entry_zones:
                print("❌ Tidak ada harga entry untuk LIMIT order. Batal eksekusi.")
                return
            entry_price = float(entry_zones[0])
        
        sl_price = data.get("stop_loss")
        if not sl_price:
            print("❌ Tidak ada Stop Loss (SL). Eksekusi dibatalkan demi keamanan!")
            return
        sl_price = float(sl_price)
        
        print(f"\n🚀 [BITGET DEMO] Bersiap Eksekusi {side} {symbol_ccxt}...")
        
        # Load markets untuk mendapatkan informasi batas desimal (precision) koin
        bitget.load_markets()
        
        # Hitung ukuran posisi (Lot) berdasarkan risk
        size_coin = calculate_position_size(symbol_ccxt, entry_price, sl_price)
        if size_coin <= 0:
            return
            
        # Format ukuran sesuai desimal yang diizinkan oleh Bitget
        formatted_size = float(bitget.amount_to_precision(symbol_ccxt, size_coin))
        
        # --- PENGATURAN LEVERAGE (MARGIN KECIL, SIZE BESAR) ---
        leverage = data.get("leverage")
        if not leverage:
            # Jika sinyal tidak menyebutkan leverage, gunakan default dari .env (misal 20x)
            leverage = int(os.getenv("DEFAULT_LEVERAGE", "20"))
        else:
            leverage = int(leverage)
            
        try:
            # Set leverage di Bitget
            bitget.set_leverage(leverage, symbol_ccxt)
            print(f"⚙️ Leverage diatur ke {leverage}x (Margin yang ditahan akan jauh lebih kecil!)")
        except Exception as e:
            print(f"⚠️ Gagal mengatur leverage: {e}")
            
        # Arah Trade
        order_side = 'buy' if side == 'LONG' else 'sell'
        
        # Pengaturan Stop Loss dan Take Profit bawaan order
        params = {
            'stopLoss': {
                'triggerPrice': sl_price,
            },
            'hedged': True,          # CCXT Bitget v2 WAJIB menggunakan ini untuk Hedge Mode
            'marginMode': 'cross'    # CCXT otomatis mengubah ini jadi 'crossed'
        }
        
        take_profits = data.get("take_profit", [])
        if take_profits:
            params['takeProfit'] = {
                'triggerPrice': float(take_profits[0]),
            }
            
        # Eksekusi Order sesuai tipe
        if order_type_str == "MARKET":
            print(f"⏳ Mengirim MARKET order {order_side.upper()} sejumlah {formatted_size} koin ke exchange...")
            order = bitget.create_order(
                symbol=symbol_ccxt,
                type='market',
                side=order_side,
                amount=formatted_size,
                params=params
            )
        else:
            print(f"⏳ Mengirim LIMIT order {order_side.upper()} sejumlah {formatted_size} koin di harga {entry_price} ke exchange...")
            order = bitget.create_order(
                symbol=symbol_ccxt,
                type='limit',
                side=order_side,
                amount=formatted_size,
                price=entry_price,
                params=params
            )
        
        print(f"✅ ORDER BERHASIL DIEKSEKUSI!")
        print(f"📄 Order ID: {order.get('id')}")
        
    except Exception as e:
        print(f"🚨 [TRADE ERROR] Eksekusi gagal: {e}")
