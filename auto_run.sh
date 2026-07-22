#!/bin/bash
cd /home/fred/solaria

echo "Initializing network checking mechanisms..."
while ! ping -c 1 -W 1 github.com &> /dev/null; do
    sleep 2
done
echo "Network connection validated successfully!"

echo "Syncing system data files with GitHub origin repository..."
git fetch --all
git pull origin main

echo "Evaluating software dependencies..."
source venv/bin/activate
pip install -r requirements.txt

echo "Booting Solaria Central System Engines..."
python3 app.py
