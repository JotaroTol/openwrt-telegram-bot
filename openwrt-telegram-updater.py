#!/usr/bin/python3
import time
import os
import sys
import json
import subprocess
import requests
import re

# --- KONFIGURASI TELEGRAM BOT ---
TELEGRAM_BOT_TOKEN = "7867980254:AAFFxIpIjE944ZAHlmIoppJh5Q2TUmzA-3A"
TELEGRAM_CHAT_ID = "943167718" # Chat ID untuk notifikasi perangkat tersambung

# --- KONFIGURASI SISTEM STB ---
POLLING_INTERVAL_SECS = 3
INTERNET_CHECK_INTERVAL_SECS = 5
DEVICE_CHECK_INTERVAL_SECS = 10 # Interval diperpanjang sedikit untuk stabilitas
REQUEST_TIMEOUT_SECS = 10
DISCONNECT_GRACE_PERIOD_SECS = 20 # Periode tenggang (detik) sebelum menyatakan perangkat terputus

LAST_STATUS_FILE = "/tmp/inet_last_status.log"
DOWN_COUNT_FILE = "/tmp/inet_down_count.log"
CONNECTED_DEVICES_FILE = "/tmp/connected_devices.json" # File untuk menyimpan daftar perangkat tersambung

PING_TARGET = "www.gstatic.com"
NAS_PATH = "/mnt/nas"
PING_INTERFACE = "utun"
LAN_IFACE = "br-lan"
MAIN_IFACE = "br-lan"

# --- PATH KE SKRIP 3ginfo-lite ---
# Pastikan jalur ini sesuai dengan lokasi skrip shell Anda.
TG_3GINFO_LITE_SCRIPT = "/usr/share/3ginfo-lite/3ginfo.sh"

# --- Variabel Global untuk Debounce Perangkat Terputus ---
# Menyimpan perangkat yang saat ini hilang, menunggu konfirmasi terputus
# Format: {mac_address: {'device_info': {...}, 'timestamp': waktu_hilang_pertama}}
_stale_devices_awaiting_disconnection = {}


# --- Fungsi Pembantu ---
def format_uptime(seconds):
    """Mengubah detik menjadi format uptime yang mudah dibaca (hari, jam, menit)."""
    if not seconds: return "0m"
    days = seconds // 86400
    seconds %= 86400
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    result = ""
    if days > 0: result += f"{days}h "
    if hours > 0: result += f"{hours}j "
    result += f"{minutes}m"
    return result.strip()

def format_bytes_to_mb_gb(b):
    """Mengubah byte menjadi MB atau GB."""
    if not b: return "0 MB"
    b = float(b)
    if b >= 1073741824: return f"{b / 1073741824:.2f} GB"
    else: return f"{b / 1048576:.0f} MB"

def read_file_content(filepath, default_value=0, type_func=int):
    """Membaca konten dari file, mengembalikan nilai default jika file tidak ada atau error."""
    try:
        with open(filepath, 'r') as f:
            return type_func(f.read().strip())
    except (FileNotFoundError, ValueError):
        return default_value

def write_file_content(filepath, value):
    """Menulis konten ke file."""
    try:
        with open(filepath, 'w') as f:
            f.write(str(value))
    except IOError as e:
        print(f"Error writing to {filepath}: {e}", file=sys.stderr)

def run_cmd(cmd):
    """Menjalankan perintah shell dan mengembalikan outputnya."""
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.PIPE).strip()
    except subprocess.CalledProcessError as e:
        return ""
    except FileNotFoundError:
        return ""

def escape_markdown_v2(text):
    """
    Mengescape karakter khusus untuk MarkdownV2 di Telegram.
    Lihat: https://core.telegram.org/bots/api#markdownv2-style
    """
    chars_to_escape = '_*[]()~`>#+-=|{}.!\\' 
    escaped_text = ""
    for char in text:
        if char in chars_to_escape:
            escaped_text += '\\' + char
        else:
            escaped_text += char
    return escaped_text

def send_telegram_message(chat_id, message):
    """Mengirim pesan ke bot Telegram."""
    if not chat_id or chat_id == "YOUR_TELEGRAM_CHAT_ID":
        print("Error: TELEGRAM_CHAT_ID not configured. Cannot send proactive message.", file=sys.stderr)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "MarkdownV2"
    }
    print(f"\n--- DEBUG: Attempting to send message to Telegram ---", file=sys.stderr)
    print(f"Chat ID: {chat_id}", file=sys.stderr)
    print(f"Message Content (raw):\n{payload['text']}\n", file=sys.stderr)
    print(f"---------------------------------------------------\n", file=sys.stderr)

    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECS)
        response.raise_for_status()
        print(f"Message sent to Telegram chat ID {chat_id} successfully.")
    except requests.exceptions.Timeout:
        print(f"Error sending message to Telegram: Request timed out after {REQUEST_TIMEOUT_SECS} seconds.", file=sys.stderr)
    except requests.exceptions.RequestException as e:
        print(f"Error sending message to Telegram: {e}. Full response: {e.response.text if e.response else 'N/A'}", file=sys.stderr)

def get_connected_devices():
    """
    Mendapatkan daftar perangkat yang *dikenal* (dari DHCP leases dengan hostname valid)
    DAN *aktif* (dikonfirmasi oleh ARP/Wi-Fi station).
    Perangkat 'Unknown' atau yang tidak memiliki lease DHCP tidak akan ditampilkan.
    """
    final_connected_devices = []
    
    # 1. Baca informasi DHCP leases untuk semua perangkat yang dikenal (dengan hostname)
    dhcp_leases_path = "/tmp/dhcp.leases"
    dhcp_known_devices_by_mac = {} 
    if os.path.exists(dhcp_leases_path):
        current_time = int(time.time())
        try:
            with open(dhcp_leases_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        lease_timestamp = int(parts[0])
                        mac_address = parts[1].lower()
                        ip_address_from_lease = parts[2]
                        hostname = parts[3]
                        
                        if hostname and hostname != '*' and hostname.lower() != 'unknown':
                            remaining_lease_seconds = lease_timestamp - current_time
                            formatted_lease_time = format_uptime(max(0, remaining_lease_seconds))
                            
                            dhcp_known_devices_by_mac[mac_address] = {
                                "hostname": hostname,
                                "ip": ip_address_from_lease,
                                "mac": mac_address, 
                                "lease_time": formatted_lease_time
                            }
        except Exception as e:
            print(f"Error reading dhcp.leases for known devices: {e}", file=sys.stderr)

    # 2. Kumpulkan semua MAC yang saat ini aktif di jaringan (dari ARP & Wi-Fi station)
    active_macs_from_network = set()
    
    # Dari ip neigh show (ARP cache - hanya 'REACHABLE' atau 'PERMANENT')
    arp_neigh_output = run_cmd("ip neigh show")
    for line in arp_neigh_output.splitlines():
        match = re.search(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+dev\s+\S+\s+lladdr\s+([0-9a-fA-F:]+)\s+(?:reachable|permanent)', line, re.IGNORECASE)
        if match:
            mac_address = match.group(2).lower()
            active_macs_from_network.add(mac_address)

    # Dari iw dev (Wi-Fi connected stations - untuk AP interfaces)
    iw_dev_output = run_cmd("iw dev")
    for iface_line in iw_dev_output.splitlines():
        if "Interface" in iface_line:
            iface_name = iface_line.split("Interface")[1].strip()
            if "type AP" in run_cmd(f"iw dev {iface_name} info 2>/dev/null"):
                station_dump_output = run_cmd(f"iw dev {iface_name} station dump 2>/dev/null")
                for station_line in station_dump_output.splitlines():
                    if 'Station' in station_line:
                        try:
                            mac_address = station_line.split('Station')[1].strip().split(' ')[0].lower()
                            active_macs_from_network.add(mac_address)
                        except IndexError:
                            pass

    # 3. Gabungkan: hanya sertakan perangkat yang dikenal (dari DHCP) DAN aktif (dari ARP/Wi-Fi)
    for mac_address, dhcp_info in dhcp_known_devices_by_mac.items():
        if mac_address in active_macs_from_network:
            final_connected_devices.append(dhcp_info)
    
    def sort_key(d):
        ip_str = d['ip']
        if ip_str == 'N/A': 
            return (0, 0, 0, 0)
        try:
            return tuple(map(int, ip_str.split('.')))
        except ValueError:
            return (0, 0, 0, 0)
    
    final_connected_devices.sort(key=sort_key)

    return final_connected_devices

def csq_to_bars(csq_value):
    """Mengkonversi nilai CSQ (0-31) menjadi 5 bar ASCII bertingkat dan teks deskripsi."""
    
    num_bars = 0
    description = "Tidak terdeteksi"
    bar_string_visual = "[     ]"

    try:
        csq_int = int(str(csq_value).strip())
    except (ValueError, TypeError):
        csq_int = -1
    
    if csq_int < 0 or csq_int == 99:
        num_bars = 0
        description = "Tidak ada sinyal"
    elif csq_int <= 6:
        num_bars = 1
        description = "Buruk"
    elif csq_int <= 12:
        num_bars = 2
        description = "Sedang"
    elif csq_int <= 18:
        num_bars = 3
        description = "Cukup Baik"
    elif csq_int <= 25:
        num_bars = 4
        description = "Bagus"
    else: # csq_int <= 31
        num_bars = 5
        description = "Sangat Bagus"
        
    tier_chars = ["▃", "▅", "▆", "▇", "▉"]
    empty_char = " "
    
    bar_string = ""
    for i in range(5):
        if i < num_bars:
            bar_string += tier_chars[i]
        else:
            bar_string += empty_char
            
    bar_string_visual = f"[{bar_string}]"
            
    return bar_string_visual, description


def get_modem_info():
    """Mengambil informasi modem dari skrip 3ginfo-lite."""
    modem_info = {
        "operator_name": "N/A",
        "signal_bars": "[     ]",
        "signal_description": "Tidak terdeteksi",
        "csq": "N/A",
        "modem_type": "N/A",
        "modem_technology": "N/A"
    }
    
    if not os.path.exists(TG_3GINFO_LITE_SCRIPT):
        print(f"Error: 3ginfo-lite script not found at {TG_3GINFO_LITE_SCRIPT}", file=sys.stderr)
        return modem_info

    try:
        cmd_output = run_cmd(TG_3GINFO_LITE_SCRIPT)
        
        if cmd_output:
            data = json.loads(cmd_output)
            
            modem_info["operator_name"] = data.get("operator_name", "N/A")
            modem_info["modem_type"] = data.get("modem", "N/A")
            modem_info["modem_technology"] = data.get("mode", "N/A")
            
            csq_raw = data.get("csq")
            modem_info["csq"] = csq_raw if csq_raw is not None else "N/A"
            
            modem_info["signal_bars"], modem_info["signal_description"] = csq_to_bars(csq_raw)

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from 3ginfo-lite script: {e}. Output was: {repr(cmd_output)}", file=sys.stderr)
    except Exception as e:
        print(f"Error running 3ginfo-lite script or processing its output: {e}", file=sys.stderr)
    
    return modem_info


def get_stb_full_status():
    """Mengumpulkan semua informasi status STB."""
    current_internet_status = "DOWN"
    if os.system(f"ping -c 1 -W 2 -I {PING_INTERFACE} {PING_TARGET} > /dev/null 2>&1") == 0:
        current_internet_status = "UP"
    
    down_count = read_file_content(DOWN_COUNT_FILE)
    
    uptime_seconds = read_file_content("/proc/uptime", default_value="0", type_func=lambda x: int(float(x.split()[0])))
    server_uptime = format_uptime(uptime_seconds)

    gateway_ip = run_cmd("route -n | awk '/^0.0.0.0/ {print $2}' | head -n 1")
    
    local_ip = ""
    temp_lan_iface = LAN_IFACE
    if not run_cmd(f"ip addr show {temp_lan_iface}"):
        temp_lan_iface = "eth1"
    
    local_ip_output = run_cmd(f"ifconfig {temp_lan_iface} | awk -F'[: ]+' '/inet addr/ {{print $4}}'")
    if local_ip_output:
        local_ip = local_ip_output

    nas_status = "Not Mounted"
    nas_free_space_mb = 0
    if os.system(f"mount | grep -q '{NAS_PATH}'") == 0:
        nas_status = "Mounted"
        df_output = run_cmd(f"df -m '{NAS_PATH}' | awk 'NR==2 {{print $4}}'")
        if df_output:
            nas_free_space_mb = int(df_output)

    cpu_temp_raw = read_file_content("/sys/class/thermal/thermal_zone0/temp")
    cpu_temp_c = round(cpu_temp_raw / 1000.0, 1)

    cpu_line1 = run_cmd("grep 'cpu ' /proc/stat")
    time.sleep(1) # Tunggu sebentar untuk mengukur penggunaan CPU
    cpu_line2 = run_cmd("grep 'cpu ' /proc/stat")

    def parse_cpu_stats(line):
        parts = line.split()
        return [int(parts[i]) for i in [1,2,3,4,5,6,7,8,9,10]]

    cpu_usage_percent = 0
    if cpu_line1 and cpu_line2:
        try:
            stats1 = parse_cpu_stats(cpu_line1)
            stats2 = parse_cpu_stats(cpu_line2)

            idle1 = stats1[3] + stats1[4]
            total1 = sum(stats1)

            idle2 = stats2[3] + stats2[4]
            total2 = sum(stats2)

            if (total2 - total1) > 0:
                cpu_usage_percent = int(100 * (total2 - total1 - (idle2 - idle1)) / (total2 - total1))
        except IndexError:
            pass


    daily_rx_bytes = 0
    daily_tx_bytes = 0
    try:
        vnstat_json_str = run_cmd(f"vnstat --json d 1 -i {MAIN_IFACE}")
        if vnstat_json_str:
            vnstat_data = json.loads(vnstat_json_str)
            daily_rx_bytes = vnstat_data['interfaces'][0]['traffic']['day'][0]['rx']
            daily_tx_bytes = vnstat_data['interfaces'][0]['traffic']['day'][0]['tx']
    except Exception as e:
        print(f"Error getting vnstat data: {e}", file=sys.stderr)
        pass
    
    daily_total_rx = format_bytes_to_mb_gb(daily_rx_bytes)
    daily_total_tx = format_bytes_to_mb_gb(daily_tx_bytes)

    connected_devices = get_connected_devices()
    total_connected_devices = len(connected_devices)

    # --- Ambil informasi modem ---
    modem_info = get_modem_info()
    operator_name = modem_info["operator_name"]
    signal_bars = modem_info["signal_bars"]
    signal_description = modem_info["signal_description"]
    modem_type = modem_info["modem_type"]
    modem_technology = modem_info["modem_technology"]

    message = (
        f"🛜 *Status STB B860H v2 JotaroNet:*\n\n"
        f"❗ Operator: `{escape_markdown_v2(operator_name)}`\n"
        f"📶 Sinyal: `{escape_markdown_v2(signal_bars)} {escape_markdown_v2(signal_description)}`\n"
        f"📡 Teknologi: `{escape_markdown_v2(modem_technology)}`\n"
        f"📱 Modem: `{escape_markdown_v2(modem_type)}`\n"
        f"🌐 Internet: `{escape_markdown_v2(current_internet_status)}`\n"
        f"⬆️ Uptime: `{escape_markdown_v2(server_uptime)}`\n"
        f"⬇️ Down Count: `{escape_markdown_v2(str(down_count))}`\n"
        f"🚪 Gateway Modem: `{escape_markdown_v2(gateway_ip)}`\n"
        f"🏠 Gateway STB: `{escape_markdown_v2(local_ip)}`\n"
        f"🔗 Perangkat Tersambung: `{escape_markdown_v2(str(total_connected_devices))}`\n"
        f"💾 Status NAS: `{escape_markdown_v2(nas_status)}`\n"
        f"📦 NAS Sisa: `{escape_markdown_v2(str(nas_free_space_mb))} MB`\n"
        f"🌡️ CPU Temp: `{escape_markdown_v2(str(cpu_temp_c))}°C`\n"
        f"📊 Pemakaian CPU: `{escape_markdown_v2(str(cpu_usage_percent))}%`\n"
        f"📈 Upload Harian: `{escape_markdown_v2(daily_total_rx)}`\n"
        f"📉 Download Harian: `{escape_markdown_v2(daily_total_tx)}`"
    )
    return message, current_internet_status, down_count

def check_internet_status_and_notify():
    """Memeriksa status internet dan mengirim notifikasi jika ada perubahan."""
    last_status_recorded = read_file_content(LAST_STATUS_FILE, default_value="UNKNOWN", type_func=str)
    down_count = read_file_content(DOWN_COUNT_FILE)

    current_status = "DOWN"
    try:
        if os.system(f"ping -c 1 -W 5 -I {PING_INTERFACE} {PING_TARGET} > /dev/null 2>&1") == 0:
            current_status = "UP"
    except Exception as e:
        print(f"Error during ping check: {e}", file=sys.stderr)
        current_status = "DOWN"
        
    if last_status_recorded == "UP" and current_status == "DOWN":
        down_count += 1
        write_file_content(DOWN_COUNT_FILE, down_count)
        print("Internet status changed to DOWN. Notification functionality removed.")
    elif last_status_recorded == "DOWN" and current_status == "UP":
        print("Internet status changed to UP. Notification functionality removed.")
        
    write_file_content(LAST_STATUS_FILE, current_status)

def load_connected_devices_state():
    """Memuat daftar perangkat yang tersambung sebelumnya dari file."""
    if os.path.exists(CONNECTED_DEVICES_FILE):
        try:
            with open(CONNECTED_DEVICES_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error loading connected devices state: {e}", file=sys.stderr)
            return []
    return []

def save_connected_devices_state(devices):
    """Menyimpan daftar perangkat yang tersambung saat ini ke file."""
    try:
        with open(CONNECTED_DEVICES_FILE, 'w') as f:
            json.dump(devices, f, indent=4) # Menambahkan indent untuk keterbacaan
    except IOError as e:
        print(f"Error saving connected devices state: {e}", file=sys.stderr)

def check_new_device_connection_and_notify():
    """Memeriksa perangkat baru yang tersambung dan mengirim notifikasi."""
    global _stale_devices_awaiting_disconnection # Deklarasikan penggunaan variabel global
    current_time = int(time.time())

    previous_devices = load_connected_devices_state()
    current_devices = get_connected_devices()

    previous_macs = {d['mac'] for d in previous_devices}
    current_macs = {d['mac'] for d in current_devices}

    # --- Debugging Status Perangkat ---
    # print(f"DEBUG: Previous MACs: {previous_macs}", file=sys.stderr)
    # print(f"DEBUG: Current MACs: {current_macs}", file=sys.stderr)
    # print(f"DEBUG: Stale devices awaiting disconnection (before processing): {_stale_devices_awaiting_disconnection}", file=sys.stderr)
    # --- Akhir Debugging ---

    # 1. Deteksi Perangkat yang Potensi Tersambung Baru (muncul di current_macs tapi tidak di previous_macs)
    #    dan Filter jika mereka baru saja terputus (ada di _stale_devices_awaiting_disconnection)
    potentially_new_device_macs = current_macs - previous_macs
    
    actual_new_device_macs_to_notify = set()
    for device_mac in potentially_new_device_macs:
        if device_mac in _stale_devices_awaiting_disconnection:
            # Perangkat ini muncul kembali sebelum periode tenggang putus koneksi berakhir.
            # Hapus dari _stale_devices_awaiting_disconnection dan JANGAN notifikasi sebagai "baru".
            del _stale_devices_awaiting_disconnection[device_mac]
            print(f"DEBUG: Device {device_mac} reconnected quickly (was stale), skipping 'new device' notification.", file=sys.stderr)
        else:
            # Ini adalah perangkat yang benar-benar baru (belum pernah terlihat atau sudah lama hilang)
            actual_new_device_macs_to_notify.add(device_mac)

    if actual_new_device_macs_to_notify:
        print(f"DEBUG: Truly new device MACs to notify: {actual_new_device_macs_to_notify}", file=sys.stderr)
        for device_mac in actual_new_device_macs_to_notify:
            new_device = next((d for d in current_devices if d['mac'] == device_mac), None)
            if new_device:
                notification_message = (
                    f"🎉 *Perangkat Tersambung Baru\\!* 🎉\n\n"
                    f"Nama Perangkat: `{escape_markdown_v2(new_device.get('hostname', 'N/A'))}`\n"
                    f"IP: `{escape_markdown_v2(new_device.get('ip', 'N/A'))}`\n"
                    f"MAC: `{escape_markdown_v2(new_device.get('mac', 'N/A'))}`\n"
                    f"Lease: `{escape_markdown_v2(new_device.get('lease_time', 'N/A'))}`"
                )
                send_telegram_message(TELEGRAM_CHAT_ID, notification_message)
    
    # 2. Deteksi Perangkat yang Potensi Terputus (ada di previous_macs tapi tidak di current_macs)
    #    dan Pindahkan ke daftar grace period jika belum ada
    just_disappeared_macs = previous_macs - current_macs
    for device_mac in just_disappeared_macs:
        if device_mac not in _stale_devices_awaiting_disconnection:
            # Ambil info perangkat dari previous_devices
            info_for_stale = next((d for d in previous_devices if d['mac'] == device_mac), None)
            if info_for_stale:
                _stale_devices_awaiting_disconnection[device_mac] = {
                    'device_info': info_for_stale,
                    'timestamp': current_time
                }
                print(f"DEBUG: Device {device_mac} (Hostname: {info_for_stale.get('hostname', 'N/A')}) entered grace period.", file=sys.stderr)

    # 3. Proses Perangkat di Daftar Grace Period
    #    Kirim notifikasi putus jika periode tenggang habis, atau hapus jika sudah kembali
    macs_to_remove_from_stale = []
    for device_mac, stale_info in _stale_devices_awaiting_disconnection.items():
        if device_mac not in current_macs: # Masih tidak ada di current_macs
            if (current_time - stale_info['timestamp']) >= DISCONNECT_GRACE_PERIOD_SECS:
                # Periode tenggang habis, nyatakan terputus
                disconnected_device = stale_info['device_info']
                print(f"DEBUG: Device {device_mac} (Hostname: {disconnected_device.get('hostname', 'N/A')}) disconnected after grace period.", file=sys.stderr)
                notification_message = (
                    f"🔌 *Perangkat Terputus\\!* 🔌\n\n"
                    f"Nama Perangkat: `{escape_markdown_v2(disconnected_device.get('hostname', 'N/A'))}`\n"
                    f"IP: `{escape_markdown_v2(disconnected_device.get('ip', 'N/A'))}`\n"
                    f"MAC: `{escape_markdown_v2(disconnected_device.get('mac', 'N/A'))}`"
                )
                send_telegram_message(TELEGRAM_CHAT_ID, notification_message)
                macs_to_remove_from_stale.append(device_mac)
        # else: (Kondisi ini sudah ditangani di bagian 1: actual_new_device_macs_to_notify)
        #       Perangkat muncul kembali di current_macs, batalkan status stale
        #       macs_to_remove_from_stale.append(device_mac) # Ini sudah dilakukan di bagian 1
            
    # Hapus perangkat dari _stale_devices_awaiting_disconnection yang sudah diproses
    # (baik karena notifikasi putus dikirim, atau karena kembali dalam periode tenggang)
    for mac in macs_to_remove_from_stale:
        del _stale_devices_awaiting_disconnection[mac]

    # Simpan status perangkat saat ini untuk perbandingan selanjutnya
    save_connected_devices_state(current_devices)


# --- Loop Utama Bot Polling ---
last_update_id = 0
last_internet_check_time = 0
last_device_check_time = 0

# Inisialisasi awal connected_devices.json saat bot pertama kali dijalankan
if not os.path.exists(CONNECTED_DEVICES_FILE):
    print("Initializing connected devices file...", file=sys.stderr)
    initial_devices = get_connected_devices()
    save_connected_devices_state(initial_devices)
    print("Connected devices file initialized with initial devices.", file=sys.stderr)


try:
    while True:
        if time.time() - last_internet_check_time >= INTERNET_CHECK_INTERVAL_SECS:
            check_internet_status_and_notify()
            last_internet_check_time = time.time()

        if time.time() - last_device_check_time >= DEVICE_CHECK_INTERVAL_SECS:
            check_new_device_connection_and_notify()
            last_device_check_time = time.time()

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        params = {"offset": last_update_id + 1, "timeout": POLLING_INTERVAL_SECS}
        
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECS)
            response.raise_for_status()
            updates = response.json().get("result", [])

            for update in updates:
                last_update_id = update["update_id"]
                if "message" in update:
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "")

                    print(f"Received message from chat ID {chat_id}: {text}")

                    if text == "/start":
                        status_message, _, _ = get_stb_full_status()
                        send_telegram_message(chat_id, status_message)
                    elif text == "/devices":
                        devices = get_connected_devices()
                        if devices:
                            device_list_message = "🛜 *Perangkat Tersambung:*\n\n"
                            for i, device in enumerate(devices):
                                device_list_message += (
                                    f"*{i+1}\\. Hostname:* `{escape_markdown_v2(device['hostname'])}`\n"
                                    f"    🌐 *IP:* `{escape_markdown_v2(device['ip'])}`\n"
                                    f"    📡 *MAC:* `{escape_markdown_v2(device['mac'])}`\n"
                                    f"    ⏳* Lease:* `{escape_markdown_v2(device['lease_time'])}`\n\n"
                                )
                            send_telegram_message(chat_id, device_list_message)
                        else:
                            send_telegram_message(chat_id, escape_markdown_v2("Tidak ada perangkat yang tersambung ditemukan\\."))
                    else:
                        send_telegram_message(chat_id, escape_markdown_v2("Maaf, saya hanya mengerti perintah /start dan /devices."))

        except requests.exceptions.Timeout:
            print(f"Error fetching updates from Telegram: Request timed out after {REQUEST_TIMEOUT_SECS} seconds.", file=sys.stderr)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching updates from Telegram: {e}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from Telegram response: {e}", file=sys.stderr)

except KeyboardInterrupt:
    print("Telegram bot updater stopped by user.")
except Exception as e:
    print(f"Telegram bot updater encountered an error: {e}", file=sys.stderr)
