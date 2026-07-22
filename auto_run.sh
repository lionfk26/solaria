#!/bin/bash
cd /home/fred/solaria

# Attempt git update if internet is available
if ping -c 1 -W 1 github.com &> /dev/null; then
    echo "Syncing latest changes from GitHub..."
    git fetch --all
    git pull origin main
fi

source venv/bin/activate
python3 app.py
