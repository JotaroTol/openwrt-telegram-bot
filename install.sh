#!/bin/sh

# Define constants
SCRIPT_NAME="openwrt-telegram-updater.py"
INSTALL_DIR="/opt/openwrt-telegram-bot"
PYTHON_SCRIPT_PATH="${INSTALL_DIR}/${SCRIPT_NAME}"
SYSTEMD_SERVICE_NAME="openwrt-telegram-bot"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service"
INITD_SERVICE_FILE="/etc/init.d/${SYSTEMD_SERVICE_NAME}" # For OpenWrt init.d

# Function to check for internet connectivity
check_internet() {
    ping -c 1 -W 3 8.8.8.8 > /dev/null 2>&1
    return $?
}

# Function to install opkg packages
install_opkg_packages() {
    echo "Updating package lists..."
    opkg update

    PACKAGES="python3 python3-pip python3-requests"
    
    # Check if 3ginfo-lite is needed/available and install if not already present
    if [ ! -f "/usr/share/3ginfo-lite/3ginfo.sh" ]; then
        echo "3ginfo-lite not found. Installing 3ginfo-lite if available in feeds..."
        opkg install 3ginfo-lite
        if [ $? -ne 0 ]; then
            echo "Warning: 3ginfo-lite package not found or failed to install. Modem features might not work."
            echo "Please install it manually if needed: opkg install 3ginfo-lite"
        fi
    fi

    echo "Installing required opkg packages: ${PACKAGES}..."
    opkg install ${PACKAGES}
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install one or more required opkg packages."
        echo "Please check your internet connection or package availability."
        exit 1
    fi
    echo "OPKG packages installed successfully."
}

# Function to install pip packages
install_pip_packages() {
    echo "Installing required Python packages using pip..."
    if ! python3 -m pip install requests; then
        echo "Error: Failed to install Python 'requests' package with pip."
        echo "Please ensure pip is working correctly."
        exit 1
    fi
    echo "Python packages installed successfully."
}

# Function to copy the Python script
copy_script() {
    echo "Creating installation directory ${INSTALL_DIR}..."
    mkdir -p "${INSTALL_DIR}"

    echo "Copying ${SCRIPT_NAME} to ${PYTHON_SCRIPT_PATH}..."
    cp "./${SCRIPT_NAME}" "${PYTHON_SCRIPT_PATH}"
    chmod +x "${PYTHON_SCRIPT_PATH}"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to copy the Python script."
        exit 1
    fi
    echo "Python script copied and made executable."
}

# Function to configure the script
configure_script() {
    echo ""
    echo "--- Konfigurasi Bot Telegram ---"
    echo "Silakan masukkan informasi berikut. Anda dapat mengosongkan beberapa nilai jika tidak yakin, dan mengeditnya nanti di ${PYTHON_SCRIPT_PATH}."
    echo ""

    # Backup the original script
    cp "${PYTHON_SCRIPT_PATH}" "${PYTHON_SCRIPT_PATH}.bak"

    # Prompt for TELEGRAM_BOT_TOKEN
    current_token=$(grep -oP 'TELEGRAM_BOT_TOKEN = "\K[^"]+' "${PYTHON_SCRIPT_PATH}" | head -n 1)
    if [ -z "$current_token" ] || [ "$current_token" = "7867980254:AAFFxIpIjE944ZAHlmIoppJh5Q2TUmzA-3A" ]; then
        read -p "Masukkan TELEGRAM_BOT_TOKEN Anda (Wajib): " TELEGRAM_BOT_TOKEN_INPUT
        if [ -z "$TELEGRAM_BOT_TOKEN_INPUT" ]; then
            echo "Peringatan: TELEGRAM_BOT_TOKEN tidak boleh kosong. Bot mungkin tidak berfungsi."
        fi
        sed -i "s|^TELEGRAM_BOT_TOKEN = \".*\"|TELEGRAM_BOT_TOKEN = \"${TELEGRAM_BOT_TOKEN_INPUT}\"|" "${PYTHON_SCRIPT_PATH}"
    else
        read -p "TELEGRAM_BOT_TOKEN saat ini adalah \"${current_token}\". Masukkan yang baru (kosongkan untuk tetap): " TELEGRAM_BOT_TOKEN_INPUT
        if [ -n "$TELEGRAM_BOT_TOKEN_INPUT" ]; then
            sed -i "s|^TELEGRAM_BOT_TOKEN = \".*\"|TELEGRAM_BOT_TOKEN = \"${TELEGRAM_BOT_TOKEN_INPUT}\"|" "${PYTHON_SCRIPT_PATH}"
        fi
    fi

    # Prompt for TELEGRAM_CHAT_ID
    current_chat_id=$(grep -oP 'TELEGRAM_CHAT_ID = "\K[^"]+' "${PYTHON_SCRIPT_PATH}" | head -n 1)
    if [ -z "$current_chat_id" ] || [ "$current_chat_id" = "943167718" ] || [ "$current_chat_id" = "YOUR_TELEGRAM_CHAT_ID" ]; then
        read -p "Masukkan TELEGRAM_CHAT_ID Anda (Wajib, dapatkan dari @userinfobot): " TELEGRAM_CHAT_ID_INPUT
        if [ -z "$TELEGRAM_CHAT_ID_INPUT" ]; then
            echo "Peringatan: TELEGRAM_CHAT_ID tidak boleh kosong. Notifikasi mungkin tidak terkirim."
        fi
        sed -i "s|^TELEGRAM_CHAT_ID = \".*\"|TELEGRAM_CHAT_ID = \"${TELEGRAM_CHAT_ID_INPUT}\"|" "${PYTHON_SCRIPT_PATH}"
    else
        read -p "TELEGRAM_CHAT_ID saat ini adalah \"${current_chat_id}\". Masukkan yang baru (kosongkan untuk tetap): " TELEGRAM_CHAT_ID_INPUT
        if [ -n "$TELEGRAM_CHAT_ID_INPUT" ]; then
            sed -i "s|^TELEGRAM_CHAT_ID = \".*\"|TELEGRAM_CHAT_ID = \"${TELEGRAM_CHAT_ID_INPUT}\"|" "${PYTHON_SCRIPT_PATH}"
        fi
    fi

    # Prompt for NAS_PATH
    current_nas_path=$(grep -oP 'NAS_PATH = "\K[^"]+' "${PYTHON_SCRIPT_PATH}" | head -n 1)
    read -p "Masukkan NAS_PATH (misal: /mnt/nas, saat ini: ${current_nas_path}): " NAS_PATH_INPUT
    if [ -n "$NAS_PATH_INPUT" ]; then
        sed -i "s|^NAS_PATH = \".*\"|NAS_PATH = \"${NAS_PATH_INPUT}\"|" "${PYTHON_SCRIPT_PATH}"
    fi

    # Prompt for PING_INTERFACE
    current_ping_interface=$(grep -oP 'PING_INTERFACE = "\K[^"]+' "${PYTHON_SCRIPT_PATH}" | head -n 1)
    read -p "Masukkan PING_INTERFACE (misal: wwan0, eth1.2, saat ini: ${current_ping_interface}): " PING_INTERFACE_INPUT
    if [ -n "$PING_INTERFACE_INPUT" ]; then
        sed -i "s|^PING_INTERFACE = \".*\"|PING_INTERFACE = \"${PING_INTERFACE_INPUT}\"|" "${PYTHON_SCRIPT_PATH}"
    fi

    # Prompt for LAN_IFACE
    current_lan_iface=$(grep -oP 'LAN_IFACE = "\K[^"]+' "${PYTHON_SCRIPT_PATH}" | head -n 1)
    read -p "Masukkan LAN_IFACE (misal: br-lan, saat ini: ${current_lan_iface}): " LAN_IFACE_INPUT
    if [ -n "$LAN_IFACE_INPUT" ]; then
        sed -i "s|^LAN_IFACE = \".*\"|LAN_IFACE = \"${LAN_IFACE_INPUT}\"|" "${PYTHON_SCRIPT_PATH}"
    fi

    # Prompt for MAIN_IFACE (for vnstat)
    current_main_iface=$(grep -oP 'MAIN_IFACE = "\K[^"]+' "${PYTHON_SCRIPT_PATH}" | head -n 1)
    read -p "Masukkan MAIN_IFACE (untuk statistik vnstat, misal: wwan0, br-lan, saat ini: ${current_main_iface}): " MAIN_IFACE_INPUT
    if [ -n "$MAIN_IFACE_INPUT" ]; then
        sed -i "s|^MAIN_IFACE = \".*\"|MAIN_IFACE = \"${MAIN_IFACE_INPUT}\"|" "${PYTHON_SCRIPT_PATH}"
    fi

    echo "Konfigurasi disimpan. Anda dapat mengeditnya kapan saja di ${PYTHON_SCRIPT_PATH}."
}

# Function to create an init.d service script for OpenWrt
create_initd_service() {
    echo "Creating init.d service script for ${SYSTEMD_SERVICE_NAME}..."
    cat << EOF > "${INITD_SERVICE_FILE}"
#!/bin/sh /etc/rc.common

START=95
STOP=05

USE_PROCD=1
PROG="${PYTHON_SCRIPT_PATH}"
LOG_FILE="/var/log/${SYSTEMD_SERVICE_NAME}.log" # Log file for stdout/stderr

start_service() {
    echo "Starting OpenWrt Telegram Bot..."
    procd_open_instance
    procd_set_param command "\${PROG}"
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_set_param file "\${LOG_FILE}" # Redirect stdout/stderr to a log file
    procd_set_param respawn 3600 5 2 # Respawn if crashes: 5 times in 3600 secs, wait 2 secs
    procd_set_param limits nofile=1024 # Example: set open file limits
    procd_close_instance
}

stop_service() {
    echo "Stopping OpenWrt Telegram Bot..."
    killall ${SCRIPT_NAME} > /dev/null 2>&1
}

reload_service() {
    stop_service
    start_service
}
EOF
    chmod +x "${INITD_SERVICE_FILE}"
    /etc/init.d/${SYSTEMD_SERVICE_NAME} enable
    echo "Init.d service created and enabled."
}

# Main installation logic
echo "--- Memulai Instalasi OpenWrt Telegram Bot ---"

# Check for internet connection
echo "Memeriksa koneksi internet..."
if ! check_internet; then
    echo "Error: Tidak ada koneksi internet. Pastikan router Anda terhubung ke internet sebelum melanjutkan."
    exit 1
fi
echo "Koneksi internet terdeteksi."

# Install dependencies
install_opkg_packages
install_pip_packages

# Copy the script
copy_script

# Configure the script
configure_script

# Create and enable init.d service
create_initd_service

echo ""
echo "--- Instalasi Selesai! ---"
echo "OpenWrt Telegram Bot telah berhasil diinstal dan dikonfigurasi."
echo "Bot akan otomatis dimulai saat router boot."
echo "Untuk memulai bot sekarang, jalankan: /etc/init.d/${SYSTEMD_SERVICE_NAME} start"
echo "Untuk melihat log, Anda bisa menjalankan: tail -f /var/log/${SYSTEMD_SERVICE_NAME}.log"
echo "Anda bisa mengedit konfigurasi lebih lanjut di: ${PYTHON_SCRIPT_PATH}"
echo "-----------------------------------"
