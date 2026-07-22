#!/bin/bash

# Ensure execution permissions on scripts
chmod +x *.sh 2>/dev/null

echo "================================================="
echo "   SOLARIA LOCAL AI SYSTEM - INITIALIZATION      "
echo "================================================="

# FIRST-RUN AUTO-SETUP
if [ ! -d "/home/fred/solaria/venv" ]; then
    echo "📦 [SETUP] First run detected! Starting zero-configuration setup..."
    echo "⚠️  [SETUP] Enter your Pi password if prompted to install core packages."
    
    sudo apt update
    sudo apt install git python3-venv python3-pip python3-dev build-essential wget unzip udisks2 -y
    
    echo "🧠 [SETUP] Fetching local offline AI models..."
    ./install_assets.sh
    
    echo "🐍 [SETUP] Building Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    
    echo "✅ [SETUP] System setup complete! Dropping to login..."
    echo "-------------------------------------------------"
fi

CORRECT_USER="admin"
CORRECT_PASS="solaria2026"

setup_wifi() {
    echo "--- TABLE ENDPOINT WI-FI SETUP ---"
    read -p "Enter Pub Wi-Fi SSID: " wifi_ssid
    read -p "Enter Pub Wi-Fi Password: " wifi_pass
    
    echo "$wifi_ssid" > /home/fred/solaria/wifi_ssid.txt
    echo "$wifi_pass" > /home/fred/solaria/wifi_pass.txt
    echo "✅ Wi-Fi credentials saved for next Pico flash."
}

# LOGIN & COMMAND LOOP
while true; do
    read -p "Username (or type 'wifi reset' / 'help'): " input_user
    
    if [ "$input_user" == "help" ]; then
        echo ""
        echo "================ SOLARIA HELP MENU ================"
        echo " * LOGIN: Enter 'admin' then your password."
        echo " * WI-FI: Type 'wifi reset' to change endpoint network."
        echo " * EXIT:  Press CTRL+C to close terminal."
        echo "==================================================="
        echo ""
        continue
    fi

    if [ "$input_user" == "wifi reset" ]; then
        echo ""
        setup_wifi
        continue
    fi

    read -s -p "Password: " input_pass
    echo ""

    if [ "$input_user" == "$CORRECT_USER" ] && [ "$input_pass" == "$CORRECT_PASS" ]; then
        echo "Authentication successful! Deploying Solaria..."
        break
    else
        echo "❌ Invalid credentials. Please try again."
        echo ""
    fi
done

cd /home/fred/solaria
./auto_run.sh
