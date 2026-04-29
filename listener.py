import discord
import os
import json
from dotenv import load_dotenv
import ai_parser
import trading

# Load konfigurasi dari file .env
load_dotenv()

USER_TOKEN = os.getenv('DISCORD_USER_TOKEN')
TARGET_CHANNEL_ID = os.getenv('TARGET_CHANNEL_ID')

# Menggunakan discord.py-self khusus untuk User Account
class SignalListener(discord.Client):
    async def on_ready(self):
        print(f'[INFO] Berhasil login sebagai: {self.user.name}')
        print(f'Mendengarkan Sinyal di channel dengan ID: {TARGET_CHANNEL_ID}...')

    async def on_message(self, message):
        # Abaikan pesan jika channel tidak sesuai dengan yang kita targetkan
        if str(message.channel.id) != str(TARGET_CHANNEL_ID):
            return

        # Konversi pesan mentah (termasuk embed jika ada) menjadi string sederhana
        content = message.content
        
        # Jika pemberi sinyal (biasanya bot lain) mengirim dalam bentuk 'Embed' kotak khusus
        if message.embeds:
            for embed in message.embeds:
                if embed.title:
                    content += f"\nTitle: {embed.title}"
                if embed.description:
                    content += f"\nDescription: {embed.description}"
                for field in embed.fields:
                    content += f"\n{field.name}: {field.value}"

        image_bytes_list = []
        # Jika ada gambar atau file attachment
        if message.attachments:
            content += "\n[GAMBAR/ATTACHMENT DITEMUKAN]:"
            for attachment in message.attachments:
                content += f"\n- {attachment.url}"
                # Jika itu adalah file gambar, kita unduh ke memori (bytes) untuk dikirim ke Gemini
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    img_data = await attachment.read()
                    image_bytes_list.append({
                        "mime_type": attachment.content_type,
                        "data": img_data
                    })

        # Jika ada teks dari pesan, maka cetak
        if content.strip():
            print("====================================")
            print(f"[SINYAL MASUK] DITERIMA dari {message.author}:")
            print(content)
            
            print("\n[AI GEMINI] Memproses sinyal... mohon tunggu...")
            ai_result = ai_parser.parse_signal_with_ai(content, image_bytes_list)
            print("Hasil Analisa JSON:")
            print(ai_result)
            print("====================================\n")
            
            # Simpan output Gemini ke dalam file txt seperti yang diminta
            with open("dummy_signals.txt", "a", encoding="utf-8") as f:
                f.write(f"\n\n--- HASIL ANALISA LANGSUNG DARI DISCORD ({message.author}) ---\n")
                f.write(f"[INPUT PESAN]:\n{content}\n")
                f.write(f"[OUTPUT JSON GEMINI]:\n{ai_result}\n")
                f.write("-" * 50)
                
            # Eksekusi trading otomatis di Bitget jika AI merespon JSON yang valid
            if "error" not in ai_result.lower():
                trading.execute_trade(ai_result)

if __name__ == '__main__':
    if not USER_TOKEN or not TARGET_CHANNEL_ID:
        print("❌ ERROR: Tolong isi DISCORD_USER_TOKEN dan TARGET_CHANNEL_ID di file .env")
    else:
        # Inisialisasi API Key Gemini
        if not ai_parser.setup_gemini():
            print("⚠️ PERINGATAN: GEMINI_API_KEY tidak ditemukan di .env. AI tidak akan berfungsi!")
        else:
            print("✅ Gemini AI berhasil terhubung.")
            
        print("Mencoba melakukan koneksi ke Discord...")
        # Inisialisasi dan jalankan Client
        client = SignalListener()
        client.run(USER_TOKEN)
