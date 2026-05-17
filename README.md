# Discord AI Signal Executor 🤖📈

> [!WARNING]
> **DEVELOPMENT PHASE & PERSONAL USE ONLY**
> Bot ini masih dalam tahap **pengembangan aktif (Development Phase)** dan dirancang **khusus untuk penggunaan pribadi**. Terdapat risiko *bug* atau kegagalan eksekusi yang dapat menyebabkan kerugian finansial jika digunakan pada akun Live tanpa pengawasan. Pengembang tidak bertanggung jawab atas kerugian apa pun. Gunakan dengan risiko Anda sendiri!

> [!CAUTION]
> **SELFBOT & DISCORD ToS NOTICE**
> Proyek ini menggunakan **Discord selfbot (user token automation)** untuk membaca pesan. Metode ini **tidak sesuai** dengan Discord Terms of Service dan berisiko menyebabkan pembatasan atau penangguhan akun. Hardening pada listener hanya mengurangi footprint request, **bukan** membuat metode ini menjadi ToS-compliant. Jika ingin pendekatan yang sesuai kebijakan Discord, gunakan **official Discord Bot account + Bot API**.

Bot otomatis yang mendengarkan sinyal *trading* dari *channel* Discord tertentu, menggunakan kecerdasan buatan (**Google Gemini AI**) untuk membaca dan memahami gambar/teks sinyal, lalu mengeksekusi pesanan tersebut secara otomatis di bursa kripto **Bitget** (mendukung Limit & Market order, otomatis menghitung ukuran posisi berdasarkan persentase risiko, dan memasang Stop Loss).

## 🌟 Fitur Utama

* **Discord Self-Bot:** Memantau pesan secara *real-time* dari *channel* spesifik.
* **AI Signal Parsing:** Menggunakan Gemini 2.5 Flash untuk memahami teks sinyal maupun gambar/screenshot. Bisa membedakan *Market Order* (eksekusi langsung) dan *Limit Order* (mengantre).
* **Smart Risk Management:** Menghitung jumlah Lot (ukuran koin) secara otomatis berdasarkan jarak Stop Loss dan persentase risiko dari total saldo akun Anda (misalnya 5% per trade).
* **Automated Execution:** Integrasi CCXT ke Bitget API (Hedge Mode didukung penuh).

## 🧠 Atur Rules AI Parser

Rules untuk interpretasi sinyal AI **tidak diatur dari `.env`**, tetapi langsung di kode:

- File: `src/ai_parser.py`
- Fungsi: `parse_signal_with_ai(...)`
- Bagian prompt: blok teks pada bagian `Rules:`

Jika Anda ingin mengubah perilaku parser (misalnya prioritas CLOSE, cara baca kutipan/reply, atau aturan TP/SL), edit bagian `Rules:` di file tersebut.

## 📋 Persyaratan Sistem

* Python 3.10+
* Akun Discord (untuk mendapatkan User Token)
* API Key Google Gemini (Gratis dari Google AI Studio)
* API Key Bitget (Sangat disarankan menggunakan Bitget **Demo/Testnet** terlebih dahulu)

## 🚀 Cara Instalasi

1. **Clone Repository ini**

   ```bash
   git clone https://github.com/BlackUppsss/Discord-AI-Bot-Signal-Executor.git
   cd Discord-AI-Bot-Signal-Executor
   ```
2. **Buat Virtual Environment (Sangat Disarankan)**

   ```bash
   python -m venv venv
   # Di Windows:
   venv\Scripts\activate
   # Di Mac/Linux:
   source venv/bin/activate
   ```
3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```
4. **Konfigurasi Environment (.env)**

   * Salin file contoh environment yang disediakan:
     ```bash
     copy .env.example .env
     ```
   * Buka file `.env` di teks editor Anda dan isi semua kunci rahasia (Token Discord, API Key Gemini, Bitget API).
   * **PENTING:** Atur `RISK_PERCENTAGE` sesuai gaya *trading* Anda (Default: 5%).

## ▶️ Cara Menjalankan Bot

Jika Anda menggunakan Windows, cukup klik ganda file:

```bash
run.bat
```

Atau jalankan secara manual melalui terminal:

```bash
python listener.py
```

Bot akan mencetak log ke terminal bahwa ia siap mendengarkan sinyal!

## ⚙️ Mode Demo vs Live (Lewat `.env`)

- Gunakan `BITGET_SANDBOX=true` untuk **Demo/Paper Trading** (default, lebih aman).
- Gunakan `BITGET_SANDBOX=false` untuk **Live/Real Trading**.
- WebSocket harga publik akan ikut otomatis:
  - Demo: `wss://wspap.bitget.com/v2/ws/public`
  - Live: `wss://ws.bitget.com/v2/ws/public`
- Jika diperlukan, Anda bisa override manual dengan `BITGET_WS_PUBLIC_URL` di `.env`.

> [!WARNING]
> Pastikan API key juga sesuai mode. Jangan gunakan API key live saat `BITGET_SANDBOX=true`, dan jangan gunakan API key demo saat `BITGET_SANDBOX=false`.

## 💻 Spesifikasi Server & Penggunaan Resource

Bot ini dirancang sangat ringan dan efisien menggunakan `asyncio` dan *Websocket Multiplexing*.

* **RAM Minimum:** 512 MB (Penggunaan normal hanya berkisar 80 - 150 MB).
* **CPU Minimum:** 1 vCPU (Sangat ringan, beban CPU biasanya < 5%).
* **Jaringan:** Stabil. Disarankan dijalankan di VPS (Virtual Private Server) agar bisa memantau *market* dan Websocket 24/7 tanpa gangguan.

## 🤖 Estimasi Penggunaan API Gemini (Tier Gratis)

Bot ini menggunakan Google Gemini AI API (Tier Gratis) untuk menerjemahkan sinyal teks dan membaca gambar *screenshot*.

* **Limit Resmi Google:** 15 Request / menit dan 1.500 Request / hari.
* **Konsumsi Sinyal Teks:** ~100 hingga 300 token per pesan.
* **Konsumsi Sinyal Gambar:** ~258 token untuk gambar + prompt.
* **Total Maksimal per Eksekusi:** ~1.500 Token.

**Kesimpulan:** Selama grup sinyal Discord Anda tidak membanjiri dengan 15 sinyal per menit atau melebihi 1.500 sinyal dalam satu hari, bot ini akan beroperasi dengan sangat mulus dan **100% aman dalam kuota gratis Gemini**.

---

### 🛑 Disclaimer

Proyek ini dibuat untuk tujuan edukasi dan eksperimen teknologi integrasi AI dengan *crypto trading*. Selalu lakukan pengujian ekstensif menggunakan akun DEMO / TESTNET sebelum mempertimbangkan penggunaan uang sungguhan. Cryptocurrency sangat fluktuatif, *trade safely!*
