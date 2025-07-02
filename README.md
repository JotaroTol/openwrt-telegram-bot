# OpenWrt Telegram Bot 🤖📡

---

[![GitHub license](https://img.shields.io/github/license/JotaroTol/openwrt-telegram-bot.svg)](https://github.com/JotaroTol/openwrt-telegram-bot/blob/master/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/JotaroTol/openwrt-telegram-bot.svg?style=social)](https://github.com/JotaroTol/openwrt-telegram-bot/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/JotaroTol/openwrt-telegram-bot.svg?style=social)](https://github.com/JotaroTol/openwrt-telegram-bot/network/members)

Bot Telegram berbasis Python ini dirancang khusus untuk berjalan di router **OpenWrt** (telah diuji pada firmware STB B860H v2 JotaroNet). Tujuannya adalah memonitor berbagai statistik penting router Anda, melacak perangkat yang terhubung, dan mengirimkan **notifikasi real-time** langsung ke obrolan Telegram Anda.

---

## ✨ Fitur Utama

Nikmati pemantauan router yang cerdas dengan fitur-fitur ini:

* **📊 Status Router Komprehensif:** Dapatkan gambaran lengkap kondisi router Anda, termasuk:
    * Status Internet (UP/DOWN)
    * Uptime Router
    * Jumlah Disconnect Internet
    * IP Gateway Modem & IP Lokal STB
    * Status NAS & Sisa Ruang Penyimpanan
    * Suhu CPU & Penggunaan CPU
    * Statistik Penggunaan Data Harian (Upload/Download)
* **📶 Informasi Modem Detail:** Pantau kesehatan koneksi seluler Anda:
    * Nama Operator Seluler
    * Kekuatan Sinyal (Visual & Deskripsi)
    * Teknologi Jaringan (misalnya 4G/LTE)
    * Jenis Modem yang Terdeteksi
    *(Membutuhkan skrip `3ginfo-lite` yang kompatibel)*
* **📱 Deteksi Perangkat Tersambung Cerdas:** Ketahui siapa yang terhubung ke jaringan Anda:
    * Identifikasi perangkat berdasarkan **Hostname, IP, dan MAC Address**.
    * **Notifikasi otomatis** saat perangkat baru terhubung.
    * **Notifikasi otomatis** saat perangkat terputus (dengan *grace period* untuk menghindari notifikasi berlebihan).
* **💬 Perintah Telegram Interaktif:** Kontrol dan dapatkan info langsung dari Telegram:
    * Kirim `/start` untuk ringkasan status router.
    * Kirim `/devices` untuk daftar detail perangkat yang terhubung.
* **🚨 Notifikasi Proaktif:** Selalu update dengan perubahan penting:
    * Notifikasi saat status koneksi internet berubah.
    * Notifikasi saat perangkat terhubung atau terputus.

---

## 🚀 Prasyarat Instalasi

Sebelum memulai, pastikan router OpenWrt Anda memenuhi syarat berikut:

* **Router OpenWrt** dengan firmware yang mendukung Python 3 dan paket yang diperlukan.
* **Akses SSH** ke router Anda.
* **Koneksi Internet Aktif** di router (untuk mengunduh paket).
* **Python 3** dan **pip** terinstal di OpenWrt.
* **Paket Python `requests`** terinstal.
* **Skrip `3ginfo-lite`** di `/usr/share/3ginfo-lite/3ginfo.sh` (Opsional, bot akan membuat *placeholder* jika tidak ada).
* **Vnstat** terinstal dan dikonfigurasi pada *interface* utama (Opsional, untuk statistik data harian).

---

## 🛠️ Panduan Instalasi (Otomatis)

Kami telah menyertakan skrip instalasi otomatis (`install.sh`) untuk pengalaman yang lebih mulus. Cukup ikuti langkah-langkah di **Terminal SSH router OpenWrt** Anda:

1.  **Unduh dan Beri Izin Eksekusi Skrip Instalasi:**

    ```bash
    cd /tmp
    wget https://raw.githubusercontent.com/JotaroTol/openwrt-telegram-bot/master/install.sh -O install.sh
    chmod +x install.sh
    ./install.sh
    ```

2.  **Jalankan Skrip Instalasi:**

    ```bash
    ./install.sh
    ```

3.  **Ikuti Petunjuk di Layar:**
    Skrip akan memandu Anda melalui konfigurasi penting seperti **Token Bot Telegram**, **Chat ID Telegram**, dan nama *interface* jaringan (`PING_INTERFACE`, `MAIN_IFACE`, `LAN_IFACE`) yang relevan dengan setup router Anda.

Setelah instalasi selesai, layanan bot Telegram akan otomatis dimulai dan siap digunakan.

---

## ⚙️ Konfigurasi (Setelah Instalasi Otomatis)

Jika Anda perlu mengubah pengaturan setelah instalasi, edit file `openwrt-telegram-updater.py` secara langsung di router Anda:

```bash
vi /opt/openwrt-telegram-bot/openwrt-telegram-updater.py
