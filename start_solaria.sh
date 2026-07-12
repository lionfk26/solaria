#!/bin/bash

# Define your desired credentials here
CORRECT_USER="admin"
CORRECT_PASS="solaria2026"

clear
echo "============================================="
echo "       SOLARIA CENTRAL MANAGEMENT SYSTEM      "
echo "============================================="
echo ""

# Loop until correct credentials are provided
while true; do
    read -p "Username: " input_user
    read -s -p "Password: " input_pass
    echo "" # Newline after hidden password entry

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
