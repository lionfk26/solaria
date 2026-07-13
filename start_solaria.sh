#!/bin/bash

# Define your desired credentials here
CORRECT_USER="admin"
CORRECT_PASS="solaria2026"
WIFI_CONFIG="wifi_config.json"

clear
echo "============================================="
echo "       SOLARIA CENTRAL MANAGEMENT SYSTEM      "
echo "============================================="
echo ""

# --- WI-FI SETUP WIZARD ---
function setup_wifi() {
    echo "--- Network Configuration ---"
    read -p "Enter Restaurant Wi-Fi SSID (Name): " wifi_ssid
    read -p "Enter Wi-Fi Password: " wifi_pass
    
    # Save as a JSON file for the Python app to read later
    echo "{\"ssid\": \"$wifi_ssid\", \"password\": \"$wifi_pass\"}" > $WIFI_CONFIG
    
    echo "✅ Wi-Fi credentials saved successfully!"
    echo "-----------------------------"
    echo ""
}

# Check if this is the very first time booting Solaria
if [ ! -f "$WIFI_CONFIG" ]; then
    echo "First-time setup detected. Please configure the network for the tables."
    setup_wifi
fi

# --- AUTHENTICATION LOOP ---
while true; do
    read -p "Username (or type 'wifi reset'): " input_user
    
    # Check if the user wants to edit the Wi-Fi credentials
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

# Navigate to app folder, activate environment, and run
cd /home/pi/solaria
source venv/bin/activate
python3 app.py
