import os
import json
from google import genai
from google.genai import types

def setup_gemini():
    # Dengan library baru, kita hanya perlu cek apakah API Key ada di environment
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return False
    return True

def parse_signal_with_ai(discord_text, image_bytes_list=None):
    """
    Mengirim teks discord (dan gambar jika ada) ke Gemini API dan memintanya mengembalikan format JSON.
    """
    try:
        # Inisialisasi client Google GenAI terbaru
        api_key = os.getenv('GEMINI_API_KEY')
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Anda adalah asisten trading profesional. Tugas Anda adalah mengekstrak sinyal trading dari teks dan/atau gambar (jika ada) berikut menjadi format JSON yang valid.
        Teks Sinyal:
        \"\"\"{discord_text}\"\"\"
        
        Aturan Output JSON:
        1. Harus berupa objek JSON tunggal.
        2. "is_signal": boolean. (HANYA set true jika teks atau gambar berisi perintah BUKA, TUTUP, atau BATALKAN posisi yang BARU. Jika teks hanya berisi obrolan, pamer profit, atau update harga seperti "mulai gerak", set false).
        3. PERHATIKAN KUTIPAN (REPLY): Jika ada baris yang diawali dengan tanda "> " atau "[**Replying to", itu adalah kutipan pesan lama. JANGAN mengekstrak sinyal dari dalam kutipan tersebut! Evaluasi HANYA teks baru yang ditulis pengirim di luar kutipan (dan evaluasi gambar jika dilampirkan). Jika teks baru bukan sebuah sinyal/perintah, maka is_signal = false.
        4. "action": string ("OPEN", "CLOSE", "CANCEL", atau null jika bukan sinyal).
        5. "position_side": string ("LONG", "SHORT", "ALL", atau null).
        6. "symbol": string (misal "BTCUSDT", gabungkan koin dan pair tanpa garis miring).
        7. "leverage": number (angka saja, atau null).
        8. "entry_zone": array of numbers (contoh: [64000, 64200], atau kosong []).
        9. "take_profit": array of numbers (semua target TP, contoh: [65000, 66000], atau kosong []).
        10. "stop_loss": number (atau null).
        11. "order_type": string ("LIMIT" atau "MARKET"). Jika sinyal menyuruh "masuk sekarang", "buy now", "market", "cmp" (current market price), eksekusi instan, maka MARKET. Jika hanya ada angka entry yang jauh, antri, atau ada kata "limit", maka LIMIT.
        12. "reason": string (Berikan penjelasan SINGKAT 1 kalimat mengapa Anda menyimpulkan ini adalah sinyal (is_signal: true) atau bukan sinyal (is_signal: false)).
        
        Hasilkan HANYA format JSON murni.
        """
        
        contents = [prompt]
        # Jika ada gambar, konversi bytes ke format Part milik google.genai
        if image_bytes_list:
            for img_bytes in image_bytes_list:
                # Kita set image/png sebagai default aman, Gemini bisa membaca strukturnya
                part = types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                contents.append(part)
        
        # Eksekusi dengan model flash
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        # Coba parse untuk memastikan itu valid JSON sebelum direturn
        json_data = json.loads(response.text)
        return json.dumps(json_data, indent=4)
        
    except Exception as e:
        return f'{{"error": "Gagal memproses dengan AI: {str(e)}" }}'
