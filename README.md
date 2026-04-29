# Discord AI Signal Executor 🤖📈

> [!WARNING]
> **DEVELOPMENT PHASE & PERSONAL USE ONLY**
> Bot ini masih dalam tahap **pengembangan aktif (Development Phase)** dan dirancang **khusus untuk penggunaan pribadi**. Terdapat risiko *bug* atau kegagalan eksekusi yang dapat menyebabkan kerugian finansial jika digunakan pada akun Live tanpa pengawasan. Pengembang tidak bertanggung jawab atas kerugian apa pun. Gunakan dengan risiko Anda sendiri!

Bot otomatis yang mendengarkan sinyal *trading* dari *channel* Discord tertentu, menggunakan kecerdasan buatan (**Google Gemini AI**) untuk membaca dan memahami gambar/teks sinyal, lalu mengeksekusi pesanan tersebut secara otomatis di bursa kripto **Bitget** (mendukung Limit & Market order, otomatis menghitung ukuran posisi berdasarkan persentase risiko, dan memasang Stop Loss).

## 🌟 Fitur Utama

* **Discord Self-Bot:** Memantau pesan secara *real-time* dari *channel* spesifik.
* **AI Signal Parsing:** Menggunakan Gemini 2.5 Flash untuk memahami teks sinyal maupun gambar/screenshot. Bisa membedakan *Market Order* (eksekusi langsung) dan *Limit Order* (mengantre).
* **Smart Risk Management:** Menghitung jumlah Lot (ukuran koin) secara otomatis berdasarkan jarak Stop Loss dan persentase risiko dari total saldo akun Anda (misalnya 5% per trade).
* **Automated Execution:** Integrasi CCXT ke Bitget API (Hedge Mode didukung penuh).

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

---

### 🛑 Disclaimer

Proyek ini dibuat untuk tujuan edukasi dan eksperimen teknologi integrasi AI dengan *crypto trading*. Selalu lakukan pengujian ekstensif menggunakan akun DEMO / TESTNET sebelum mempertimbangkan penggunaan uang sungguhan. Cryptocurrency sangat fluktuatif, *trade safely!*
