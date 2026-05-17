import discord
import os
import time
import asyncio
from collections import defaultdict
from collections import deque
from dotenv import load_dotenv
import ai_parser
import trading

load_dotenv()

USER_TOKEN = os.getenv('DISCORD_USER_TOKEN')
TARGET_CHANNEL_IDS = [
    c.strip() for c in os.getenv('TARGET_CHANNEL_IDS', os.getenv('TARGET_CHANNEL_ID', '')).split(',') if c.strip()
]

NO_IMAGE_CHANNEL_IDS = [
    c.strip() for c in os.getenv('NO_IMAGE_CHANNEL_IDS', '').split(',') if c.strip()
]

READ_ATTACHMENTS = os.getenv('READ_ATTACHMENTS', 'false').lower() == 'true'
FETCH_REPLY_CONTEXT = os.getenv('FETCH_REPLY_CONTEXT', 'false').lower() == 'true'
MAX_CONCURRENT_SIGNALS = int(os.getenv('MAX_CONCURRENT_SIGNALS', '1'))

TRUSTED_AUTHORS = [
    a.strip() for a in os.getenv('TRUSTED_AUTHOR_IDS', '').split(',') if a.strip()
]

SIGNAL_KEYWORDS = [
    'long', 'short', 'buy', 'sell', 'entry', 'sl', 'tp', 'stop',
    'cancel', 'close', 'tutup', 'batal', 'open', 'market', 'limit',
    'leverage', 'pindah', 'move', 'geser', 'take profit', 'exit',
    'keluar', 'hapus', 'cmp', 'btc', 'eth', 'sol', 'usdt', 'be', 'scalp', 'swing', 'spot'
]

COOLDOWN_SEC = float(os.getenv('MESSAGE_COOLDOWN_SEC', '3'))
last_call_time: dict[int, float] = defaultdict(float)
_processed_message_ids = deque(maxlen=5000)
_processed_message_ids_set = set()

LOG_FILE = "dummy_signals.txt"
MAX_LOG_SIZE = 5 * 1024 * 1024

def rotate_log():
    """Rotasi log jika melebihi MAX_LOG_SIZE."""
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
        old = f"{LOG_FILE}.old"
        if os.path.exists(old):
            os.remove(old)
        os.rename(LOG_FILE, old)
        print(f"📄 Log dirotasi: {LOG_FILE} → {old}")

class SignalListener(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.signal_semaphore = asyncio.Semaphore(max(1, MAX_CONCURRENT_SIGNALS))

    async def on_ready(self):
        print(f'[INFO] Berhasil login sebagai: {self.user.name}')
        print(f'Mendengarkan Sinyal di channel dengan ID: {TARGET_CHANNEL_IDS}...')
        if TRUSTED_AUTHORS:
            print(f'🔒 Hanya menerima sinyal dari: {TRUSTED_AUTHORS}')
        else:
            print(f'⚠️ PERINGATAN: Tidak ada filter author — semua orang bisa trigger bot!')

    async def on_message(self, message):
        if str(message.channel.id) not in TARGET_CHANNEL_IDS:
            return

        if message.id in _processed_message_ids_set:
            return
        _processed_message_ids.append(message.id)
        _processed_message_ids_set.add(message.id)
        if len(_processed_message_ids_set) > _processed_message_ids.maxlen:
            while len(_processed_message_ids_set) > _processed_message_ids.maxlen:
                old_id = _processed_message_ids.popleft()
                _processed_message_ids_set.discard(old_id)

        if TRUSTED_AUTHORS and str(message.author.id) not in TRUSTED_AUTHORS:
            return

        now = time.time()
        if now - last_call_time[message.channel.id] < COOLDOWN_SEC:
            return
        last_call_time[message.channel.id] = now

        content = message.content
        
        if FETCH_REPLY_CONTEXT and message.reference and message.reference.message_id:
            try:
                replied_msg = await message.channel.fetch_message(message.reference.message_id)
                content = f"[MEMBALAS PESAN SEBELUMNYA (Konteks Koin)]:\n{replied_msg.content}\n\n[PESAN BARU SAAT INI (Perintah Baru)]:\n{content}"
            except Exception:
                pass
        
        if message.embeds:
            for embed in message.embeds:
                if embed.title:
                    content += f"\nTitle: {embed.title}"
                if embed.description:
                    content += f"\nDescription: {embed.description}"
                for field in embed.fields:
                    content += f"\n{field.name}: {field.value}"

        image_bytes_list = []
        skip_image = str(message.channel.id) in NO_IMAGE_CHANNEL_IDS
        can_read_attachments = READ_ATTACHMENTS and not skip_image
        if message.attachments:
            content += "\n[GAMBAR/ATTACHMENT DITEMUKAN]:"
            for attachment in message.attachments:
                content += f"\n- {attachment.url}"
                if can_read_attachments and attachment.content_type and attachment.content_type.startswith('image/'):
                    img_data = await attachment.read()
                    image_bytes_list.append({
                        "mime_type": attachment.content_type,
                        "data": img_data
                    })

        if not content.strip():
            return

        content_lower = content.lower()
        has_keyword = any(kw in content_lower for kw in SIGNAL_KEYWORDS)
        has_image = len(image_bytes_list) > 0

        if not has_keyword and not has_image:
            print(f"ℹ️ Skip (tidak ada keyword sinyal): {content[:80]}...")
            return

        print("====================================")
        print(f"[SINYAL MASUK] DITERIMA dari {message.author}:")
        print(content)
        
        print("\n[AI GEMINI] Memproses sinyal di background... (pesan baru tetap diterima)")
        
        asyncio.create_task(self._process_signal(content, image_bytes_list, str(message.author)))

    async def _process_signal(self, content, image_bytes_list, author_name):
        """Proses sinyal di background agar on_message tidak terblokir."""
        async with self.signal_semaphore:
            try:
                bitget_context = await asyncio.to_thread(trading.get_account_context_summary)

                ai_result = await asyncio.to_thread(
                    ai_parser.parse_signal_with_ai, content, image_bytes_list, bitget_context
                )

                print("Hasil Analisa JSON:")
                print(ai_result)
                print("====================================\n")
            
                rotate_log()

                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"\n\n--- HASIL ANALISA LANGSUNG DARI DISCORD ({author_name}) ---\n")
                    f.write(f"[INPUT PESAN]:\n{content}\n")
                    f.write(f"[OUTPUT JSON GEMINI]:\n{ai_result}\n")
                    f.write("-" * 50)
                
                if "error" not in ai_result.lower():
                    trade_result = await asyncio.to_thread(trading.execute_trade, ai_result)
                    if trade_result:
                        import auto_be
                        if trade_result.get("action") == "OPEN":
                            asyncio.create_task(auto_be.price_monitor_task(
                                trade_result["symbol"],
                                trade_result["side"],
                                trade_result["entry_price"],
                                trade_result["sl_price"],
                                trade_result.get("order_type", "MARKET")
                            ))
                        elif trade_result.get("action") == "CLOSE":
                            auto_be.cancel_monitor(trade_result["symbol"])
            except Exception as e:
                print(f"🚨 [BACKGROUND ERROR] Gagal proses sinyal: {e}")

if __name__ == '__main__':
    if not USER_TOKEN or not TARGET_CHANNEL_IDS:
        print("❌ ERROR: Tolong isi DISCORD_USER_TOKEN dan TARGET_CHANNEL_IDS di file .env")
    else:
        if not ai_parser.setup_gemini():
            print("⚠️ PERINGATAN: GEMINI_API_KEY tidak ditemukan di .env. AI tidak akan berfungsi!")
        else:
            print("✅ Gemini AI berhasil terhubung.")
            
        print("Mencoba melakukan koneksi ke Discord...")
        client = SignalListener()
        client.run(USER_TOKEN)
