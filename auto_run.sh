#!/bin/bash

# Navigate to operational space
cd /home/pi/solaria

echo "Initializing network checking mechanisms..."
# Check target host route loop definitions
while ! ping -c 1 -W 1 github.com &> /dev/null; do
    sleep 2
done
echo "Network connection validated successfully!"

echo "Syncing system data files with GitHub origin repository..."
# Align file state with target master definitions safely
git fetch --all
git pull origin main

echo "Evaluating software dependencies..."
source venv/bin/activate
pip install -r requirements.txt

echo "Booting Solaria Central System Engines..."
python3 app.py
