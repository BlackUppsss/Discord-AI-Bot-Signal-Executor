import os
import json
import time
from google import genai
from google.genai import types

MAX_RETRIES = 12
RETRY_WAIT_SEC = 180


def setup_gemini():
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return False
    return True


def parse_signal_with_ai(discord_text, image_bytes_list=None, bitget_context=""):
    """
    Kirim teks discord (dan gambar jika ada) ke Gemini API → return JSON sinyal.
    Non-blocking friendly — dipanggil via asyncio.to_thread() dari listener.py.
    """
    try:
        api_key = os.getenv('GEMINI_API_KEY')
        client = genai.Client(api_key=api_key)
        
        prompt = f"""Anda adalah parser sinyal trading. Ekstrak sinyal dari teks/gambar berikut ke JSON.

Teks Sinyal Discord:
\"\"\"{discord_text}\"\"\"

{bitget_context}

Rules:
- KUTIPAN (baris diawali "> " atau "[**Replying to") ATAU teks di bawah [MEMBALAS PESAN SEBELUMNYA]: Gunakan HANYA untuk mencari konteks nama Koin (symbol) atau arah (LONG/SHORT).
- BANTUAN KONTEKS: Jika pesan Discord menyuruh CLOSE/MOVE_SL/TP tapi tidak menyebutkan nama koin, Anda BOLEH menebak koin dari daftar Posisi Aktif Saat Ini di Bitget.
- Aksi utama (OPEN/CLOSE/CANCEL/MOVE_SL/TAKE_PROFIT) WAJIB diambil HANYA dari teks BARU di luar kutipan (contoh teks baru: "hit stoploss", "tutup"). Jangan jadikan isi kutipan sebagai perintah sinyal baru!
- is_signal: true HANYA jika ada perintah BUKA/TUTUP/BATALKAN/PINDAH SL/TAKE PROFIT yang BARU.
- Obrolan biasa, pamer profit, update harga → is_signal: false.

Output JSON:
{{
  "is_signal": bool,
  "action": "OPEN" | "CLOSE" | "CANCEL" | "MOVE_SL" | "TAKE_PROFIT" | null,
  "position_side": "LONG" | "SHORT" | "ALL" | null,
  "symbol": "BTCUSDT",
  "leverage": number | null,
  "entry_zone": [number],
  "take_profit": [number],
  "stop_loss": number | null,
  "order_type": "LIMIT" | "MARKET",
  "tp_percentage": number | null,
  "reason": "penjelasan singkat 1 kalimat"
}}

Panduan action:
- OPEN: Sinyal buka posisi baru (long/short).
- CLOSE: Perintah tutup posisi/cutloss ("close", "cut", "cutloss", "cl", "tutup", "keluar", "exit").
- CANCEL: Perintah batalkan order yang belum terisi ("cancel", "batal", "hapus order").
- MOVE_SL: Perintah pindahkan SL ("pindah SL", "SL ke ...", "geser SL", "SL baru", "move SL"). Isi stop_loss dengan harga SL baru.
- TAKE_PROFIT: Perintah ambil profit sebagian/penuh ("TP", "take profit", "ambil profit"). Isi tp_percentage (default 100).

order_type: "MARKET" jika "masuk sekarang/buy now/market/cmp/eksekusi instan". "LIMIT" jika ada harga entry yang antri.

Hasilkan HANYA JSON murni."""
        
        contents = [prompt]

        if image_bytes_list:
            for img_info in image_bytes_list:
                if isinstance(img_info, dict):
                    part = types.Part.from_bytes(
                        data=img_info["data"],
                        mime_type=img_info.get("mime_type", "image/png")
                    )
                else:
                    part = types.Part.from_bytes(data=img_info, mime_type="image/png")
                contents.append(part)
        
        models_to_try = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-pro']
        
        for attempt in range(MAX_RETRIES):
            for model_name in models_to_try:
                try:
                    print(f"🤖 AI ({model_name}) attempt {attempt+1}/{MAX_RETRIES}...")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                        )
                    )
                    
                    json_data = json.loads(response.text)
                    return json.dumps(json_data, indent=2)
                    
                except Exception as e:
                    error_str = str(e)
                    print(f"⚠️ {model_name}: {error_str}")
                    if any(code in error_str for code in ["429", "503", "404", "UNAVAILABLE", "NOT_FOUND", "RESOURCE_EXHAUSTED"]):
                        continue
                    else:
                        return f'{{"error": "AI gagal ({model_name}): {error_str}"}}'
            
            if attempt < MAX_RETRIES - 1:
                print(f"⏳ Semua model gagal. Menunggu retry attempt {attempt+2}/{MAX_RETRIES}...")
                elapsed = 0
                while elapsed < RETRY_WAIT_SEC:
                    remaining = RETRY_WAIT_SEC - elapsed
                    print(f"   ⏱️ {remaining} detik lagi...")
                    sleep_chunk = min(30, remaining)
                    time.sleep(sleep_chunk)
                    elapsed += sleep_chunk
                print(f"🔄 Memulai attempt {attempt+2}...")
        
        return '{"error": "Semua model AI gagal setelah semua retry. Sinyal dilewati."}'
        
    except Exception as e:
        return f'{{"error": "AI gagal: {str(e)}"}}'
