#!/bin/bash

# Solaria Launcher Dashboard
echo "================================================="
echo "   SOLARIA LOCAL AI SYSTEM - INITIALIZATION      "
echo "================================================="

CORRECT_USER="test"
CORRECT_PASS="test"

setup_wifi() {
    echo "--- TABLE ENDPOINT WI-FI SETUP ---"
    read -p "Enter Pub Wi-Fi SSID: " wifi_ssid
    read -p "Enter Pub Wi-Fi Password: " wifi_pass
    
    # Save to a temporary config file that app.py can read during flashing
    echo "$wifi_ssid" > /home/fred/solaria/wifi_ssid.txt
    echo "$wifi_pass" > /home/fred/solaria/wifi_pass.txt
    echo "✅ Wi-Fi credentials saved for next Pico flash."
}

while true; do
    read -p "Username (or type 'wifi reset' / 'help'): " input_user
    
    # HELP MENU COMMAND
    if [ "$input_user" == "help" ]; then
        echo ""
        echo "================ SOLARIA HELP MENU ================"
        echo " * LOGIN: Enter 'admin' then your password."
        echo " * WI-FI: Type 'wifi reset' to change endpoint network."
        echo " * EXIT: Press CTRL+C to close the terminal."
        echo "==================================================="
        echo ""
        continue
    fi

    # WI-FI RESET COMMAND
    if [ "$input_user" == "wifi reset" ]; then
        echo ""
        setup_wifi
        continue
    fi

    # STANDARD LOGIN
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

# Launch the main system
cd /home/fred/solaria
./auto_run.sh
