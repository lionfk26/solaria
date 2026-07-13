from flask import Flask, request, jsonify
import curses
import threading
import json
import os
import shutil
import time
from datetime import datetime
from typing import Dict, Any

app = Flask(__name__)

# Core state and thread synchronization
data_lock = threading.Lock()
tables_status: Dict[str, Dict[str, Any]] = {}
flash_log = "No board connected yet."

# Configuration paths for USB auto-flashing
PICO_TEMPLATE_DIR = os.path.expanduser("~/solaria/pico_template")
MNT_TARGET = "/media/pi/RPI-RP2"  # Default mount path for Raspberry Pi OS

def flash_connected_pico() -> None:
    """Monitors USB subsystem for raw Pico 2W boards and flashes them sequentially."""
    global flash_log
    while True:
        if os.path.exists(MNT_TARGET):
            flash_log = "⚡ Pico detected! Injecting custom profile..."
            try:
                # 1. Determine next table ID sequentially
                with data_lock:
                    next_num = len(tables_status) + 1
                    assigned_id = f"Table_{next_num}"
                
                # 2. Copy the boilerplate startup sequence
                shutil.copy(os.path.join(PICO_TEMPLATE_DIR, "boot.py"), MNT_TARGET)
                
                # 3. Read and modify the runtime template dynamically
                with open(os.path.join(PICO_TEMPLATE_DIR, "main.py"), "r") as f:
                    main_code = f.read()
                
                # Replace the generic variable with the concrete assigned number
                modified_code = main_code.replace('TABLE_ID = "Table_1"', f'TABLE_ID = "{assigned_id}"')
                
                # Write the customized code to the device root
                with open(os.path.join(MNT_TARGET, "main.py"), "w") as f:
                    f.write(modified_code)
                
                flash_log = f"✅ Flashed successfully as {assigned_id}! Safe to unplug."
                
                # Log the unit instantly in the terminal panel index
                with data_lock:
                    tables_status[assigned_id] = {"status": "Flashed / Offline", "assistance": False, "orders": []}
                
                # Cooldown period to give user time to unplug the device
                time.sleep(10)
            except Exception as e:
                flash_log = f"❌ Flash failure: {str(e)}"
        else:
            flash_log = "🔌 Awaiting Pico 2W (Hold BOOTSEL button while plugging USB)..."
            
        time.sleep(2)

def update_terminal(stdscr) -> None:
    """Renders the custom system interface in the terminal emulator window."""
    curses.curs_set(0)
    stdscr.clear()

    while True:
        stdscr.erase()
        
        # Frame Layout Header
        stdscr.addstr(0, 0, "==========================================================", curses.A_BOLD)
        stdscr.addstr(1, 0, "                SOLARIA TERMINAL DASHBOARD                ", curses.A_BOLD)
        stdscr.addstr(2, 0, f" Status: Active | Clock Check: {datetime.now().strftime('%H:%M:%S')}")
        stdscr.addstr(3, 0, "==========================================================", curses.A_BOLD)
        
        # Hardware Integration Block
        stdscr.addstr(5, 0, "--- Hardware Flasher Link ---", curses.A_UNDERLINE)
        stdscr.addstr(6, 2, flash_log)
        stdscr.addstr(7, 0, "-----------------------------")

        # Live Network Nodes Index
        row = 9
        with data_lock:
            if not tables_status:
                stdscr.addstr(row, 2, "Waiting for Pico endpoints to establish handshake...", curses.A_BLINK)
            else:
                for table_id, info in tables_status.items():
                    status = info.get('status', 'Offline')
                    help_str = "⚠️  NEEDS HELP" if info.get('assistance') else "Clear"
                    orders = ", ".join(info.get('orders', [])) or "None"
                    
                    # Inverse video styling context if table signals for support
                    attr = curses.A_REVERSE if info.get('assistance') else curses.A_NORMAL
                    
                    stdscr.addstr(row, 2, f"[{table_id}]", curses.A_BOLD | attr)
                    stdscr.addstr(row, 18, f"Status: {status}")
                    stdscr.addstr(row, 38, f"Assistance: {help_str}", attr)
                    stdscr.addstr(row + 1, 4, f"Orders: {orders}")
                    row += 3
        
        stdscr.refresh()
        time.sleep(0.5)

# --- REST ENDPOINTS FOR PICOS ---
@app.route('/register_table', methods=['POST'])
def register() -> Any:
    data = request.json or {}
    table_id = data.get('table_id')
    if table_id:
        with data_lock:
            if table_id not in tables_status:
                tables_status[table_id] = {"status": "Online", "assistance": False, "orders": []}
            else:
                tables_status[table_id]['status'] = "Online"
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 400

@app.route('/request_assistance', methods=['POST'])
def assistance() -> Any:
    data = request.json or {}
    table_id = data.get('table_id')
    needs_help = data.get('needs_help', False)
    if table_id:
        with data_lock:
            if table_id in tables_status:
                tables_status[table_id]['assistance'] = needs_help
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 400

@app.route('/new_order', methods=['POST'])
def order() -> Any:
    data = request.json or {}
    table_id = data.get('table_id')
    items = data.get('items', [])
    if table_id and isinstance(items, list):
        with data_lock:
            if table_id in tables_status:
                tables_status[table_id]['orders'].extend(items)
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 400

def run_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Prevent server console dumps from corrupting UI text
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Thread 1: Spin up REST routing listening matrix
    api_thread = threading.Thread(target=run_flask, daemon=True)
    api_thread.start()
    
    # Thread 2: Start background file watcher for hardware link
    flasher_thread = threading.Thread(target=flash_connected_pico, daemon=True)
    flasher_thread.start()
    
    # Main Thread: Execute Curses terminal wrapper dashboard layout
    curses.wrapper(update_terminal)
