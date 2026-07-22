#!/bin/bash

# Security Fix: Use external config file rather than hardcoded plaintext
SEC_CONFIG=".solaria_sec"
WIFI_CONFIG="wifi_config.json"

if [ ! -f "$SEC_CONFIG" ]; then
    echo "CORRECT_USER=\"admin\"" > $SEC_CONFIG
    echo "CORRECT_PASS=\"solaria2026\"" >> $SEC_CONFIG
    chmod 600 $SEC_CONFIG # Make it readable only by owner
fi
source $SEC_CONFIG

clear
echo "============================================="
echo "       SOLARIA CENTRAL MANAGEMENT SYSTEM      "
echo "============================================="
echo ""

function setup_wifi() {
    echo "--- Network Configuration ---"
    read -p "Enter Restaurant Wi-Fi SSID (Name): " wifi_ssid
    read -p "Enter Wi-Fi Password: " wifi_pass
    echo "{\"ssid\": \"$wifi_ssid\", \"password\": \"$wifi_pass\"}" > $WIFI_CONFIG
    echo "✅ Wi-Fi credentials saved successfully!"
    echo "-----------------------------"
    echo ""
}

if [ ! -f "$WIFI_CONFIG" ]; then
    echo "First-time setup detected. Please configure the network."
    setup_wifi
fi

while true; do
    read -p "Username (or type 'wifi reset'): " input_user
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

cd /home/freddiespi/solaria
./auto_run.sh
