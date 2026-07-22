#!/usr/bin/env python3
"""
Solaria - Local AI Restaurant Ordering System
Main server application.

Runs three concurrent pieces of work:
  1. Auto-flasher thread: watches for a Pico W in BOOTSEL mode mounted at
     /media/fred/RPI-RP2 and flashes it with the table firmware, baking in
     Wi-Fi credentials and a table ID.
  2. TCP audio engine thread: listens on port 5000 for table audio/control
     streams, runs offline STT/TTS, and manages a two-step order flow
     (proposal -> confirmation).
  3. Curses dashboard: renders server status, logs, and table state, and
     lets the operator cycle UI themes / quit cleanly.

A lightweight Flask control interface is exposed on port 5001 for anything
that wants to peek at order state over HTTP (e.g. a kitchen screen).
"""

import curses
import json
import os
import shutil
import socket
import struct
import subprocess
import threading
import time
import collections
from datetime import datetime

try:
    from vosk import Model as VoskModel, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

# --------------------------------------------------------------------------
# Paths / constants
# --------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PICO_TEMPLATE_DIR = os.path.join(BASE_DIR, "pico_template")
MENU_PATH = os.path.join(BASE_DIR, "menu.json")
WIFI_SSID_PATH = os.path.join(BASE_DIR, "wifi_ssid.txt")
WIFI_PASS_PATH = os.path.join(BASE_DIR, "wifi_pass.txt")
VOSK_MODEL_DIR = os.path.join(BASE_DIR, "models", "vosk", "vosk-model-small-en-us-0.15")

PICO_MOUNT_TARGET = "/media/fred/RPI-RP2"

AUDIO_PORT = 5000
CONTROL_PORT = 5001
AUDIO_SAMPLE_RATE = 16000

MAX_LOG_LINES = 200

# --------------------------------------------------------------------------
# Shared application state (protected by STATE_LOCK)
# --------------------------------------------------------------------------

STATE_LOCK = threading.RLock()

APP_STATE = {
    "flash_log": collections.deque(maxlen=MAX_LOG_LINES),
    "ai_log": collections.deque(maxlen=MAX_LOG_LINES),
    "tables": {},          # table_id -> table state dict
    "next_table_num": 1,
    "server_ip": "0.0.0.0",
    "running": True,
}


def log_flash(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    with STATE_LOCK:
        APP_STATE["flash_log"].append(f"[{ts}] {msg}")


def log_ai(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    with STATE_LOCK:
        APP_STATE["ai_log"].append(f"[{ts}] {msg}")


def get_table(table_id):
    with STATE_LOCK:
        if table_id not in APP_STATE["tables"]:
            APP_STATE["tables"][table_id] = {
                "table_id": table_id,
                "pending_order": [],
                "confirmed_order": [],
                "last_seen": time.time(),
                "status": "idle",   # idle | listening | proposing | confirmed
            }
        return APP_STATE["tables"][table_id]


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def load_menu():
    """
    Load menu.json and flatten it into a list of matchable items.

    Supports the current Solaria format:
        { "restaurant": ..., "menus": { "main_menu": { "<category>": [ {name, price, tags}, ... ] } } }

    and, for backward compatibility, the older flat format:
        { "items": [ {id, name, price, aliases, ...}, ... ] }
    """
    try:
        with open(MENU_PATH, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log_ai(f"Failed to load menu.json: {exc}")
        return []

    # Legacy flat format.
    if "items" in data:
        return data["items"]

    items = []
    menus = data.get("menus", {})
    for menu_name, categories in menus.items():
        for category, entries in categories.items():
            for entry in entries:
                name = entry.get("name", "").strip()
                if not name:
                    continue
                slug = name.lower()
                for ch in " &/-'’":
                    slug = slug.replace(ch, "_")
                slug = "_".join(filter(None, slug.split("_")))
                items.append({
                    "id": slug,
                    "name": name,
                    "category": category,
                    "menu": menu_name,
                    "price": entry.get("price", 0.0),
                    "tags": entry.get("tags", []),
                    "aliases": entry.get("aliases", []),
                })

    if not items:
        log_ai("menu.json parsed but produced no items - check its structure.")

    return items


def _normalize_for_matching(text):
    """Lowercase and fold '&'/'and' and '-' so spoken text matches written menu names."""
    text = text.lower().replace("&", " and ").replace("-", " ")
    return " ".join(text.split())


def match_menu_item(text, menu_items):
    """
    Small keyword matcher: text -> best matching menu item, or None.

    Checks the most specific (longest) names first so e.g. "Fish & Chips"
    wins over a generic "Chips" side when both would technically match.
    """
    text_l = _normalize_for_matching(text)
    candidates = []
    for item in menu_items:
        names = [item["name"]] + item.get("aliases", [])
        for name in names:
            name_l = _normalize_for_matching(name)
            if name_l in text_l:
                candidates.append((len(name_l), item))
                break
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


# --------------------------------------------------------------------------
# 1. Auto-flasher thread
# --------------------------------------------------------------------------

def read_wifi_credentials():
    ssid, password = None, None
    if os.path.exists(WIFI_SSID_PATH):
        with open(WIFI_SSID_PATH, "r") as f:
            ssid = f.read().strip()
    if os.path.exists(WIFI_PASS_PATH):
        with open(WIFI_PASS_PATH, "r") as f:
            password = f.read().strip()
    return ssid, password


def next_table_id():
    with STATE_LOCK:
        n = APP_STATE["next_table_num"]
        APP_STATE["next_table_num"] += 1
    return f"Table_{n}"


def flash_pico(mount_path, table_id):
    """Copy pico_template/* onto the mounted Pico and inject config."""
    log_flash(f"Pico detected at {mount_path}. Flashing as {table_id}...")

    # Copy microdot.py and main.py to the device.
    for fname in ("microdot.py", "main.py"):
        src = os.path.join(PICO_TEMPLATE_DIR, fname)
        dst = os.path.join(mount_path, fname)
        if not os.path.exists(src):
            log_flash(f"ERROR: missing template file {src}")
            return False
        shutil.copyfile(src, dst)
        log_flash(f"Copied {fname} -> {dst}")

    # Inject Wi-Fi + table config directly into the on-device main.py by
    # appending generated constants the firmware imports at boot.
    ssid, password = read_wifi_credentials()
    if not ssid:
        log_flash("WARNING: no wifi_ssid.txt found, flashing with blank Wi-Fi config.")
    ssid = ssid or ""
    password = password or ""

    config_block = (
        "\n\n# --- Injected by Solaria auto-flasher, do not edit by hand ---\n"
        f"WIFI_SSID = {ssid!r}\n"
        f"WIFI_PASSWORD = {password!r}\n"
        f"TABLE_ID = {table_id!r}\n"
        "SERVER_HOST = None  # filled in by DHCP/mDNS discovery on first boot\n"
        f"SERVER_PORT = {AUDIO_PORT}\n"
        "# --- end injected config ---\n"
    )

    dst_main = os.path.join(mount_path, "main.py")
    try:
        with open(dst_main, "a") as f:
            f.write(config_block)
    except OSError as exc:
        log_flash(f"ERROR appending config to main.py: {exc}")
        return False

    log_flash(f"Injected Wi-Fi + TABLE_ID={table_id} into main.py")

    try:
        subprocess.run(["sync"], check=True)
        log_flash("sync complete.")
    except (OSError, subprocess.CalledProcessError) as exc:
        log_flash(f"WARNING: sync failed: {exc}")

    get_table(table_id)["status"] = "idle"
    log_flash(f"Flash complete for {table_id}. Safe to unplug.")
    return True


def auto_flasher_thread():
    seen_mount = False
    log_flash("Auto-flasher watching for Pico at " + PICO_MOUNT_TARGET)
    while APP_STATE["running"]:
        mounted = os.path.isdir(PICO_MOUNT_TARGET) and os.path.ismount(PICO_MOUNT_TARGET)
        if mounted and not seen_mount:
            seen_mount = True
            table_id = next_table_id()
            try:
                flash_pico(PICO_MOUNT_TARGET, table_id)
            except Exception as exc:  # noqa: BLE001 - keep the thread alive
                log_flash(f"ERROR during flash: {exc}")
        elif not mounted:
            seen_mount = False
        time.sleep(1.5)


# --------------------------------------------------------------------------
# 2. TCP audio engine thread
#
# Wire protocol (simple line-based framing over TCP so this can be driven
# by netcat or the Pico's raw socket client):
#
#   Client -> Server:  HELLO <table_id>\n
#   Client -> Server:  AUDIO <byte_length>\n<raw PCM16LE 16kHz mono bytes>
#                                            (Pico streams raw mic audio;
#                                             server runs Vosk STT on it)
#   Client -> Server:  SPEECH <text>\n      (already-transcribed utterance,
#                                             for testing without a mic/Vosk)
#   Client -> Server:  CONFIRM\n
#   Client -> Server:  CANCEL\n
#
#   Server -> Client:  PROPOSAL <json order>\n
#   Server -> Client:  CONFIRMED <json order>\n
#   Server -> Client:  SAY <text to speak>\n
#   Server -> Client:  ERROR <text>\n
# --------------------------------------------------------------------------

_VOSK_MODEL = None
_VOSK_LOCK = threading.Lock()


def get_vosk_recognizer():
    """Lazily load the Vosk model once and return a fresh recognizer."""
    global _VOSK_MODEL
    if not VOSK_AVAILABLE:
        return None
    with _VOSK_LOCK:
        if _VOSK_MODEL is None:
            if not os.path.isdir(VOSK_MODEL_DIR):
                log_ai(f"Vosk model not found at {VOSK_MODEL_DIR}. Run install_assets.sh.")
                return None
            log_ai("Loading Vosk model (first use)...")
            _VOSK_MODEL = VoskModel(VOSK_MODEL_DIR)
            log_ai("Vosk model loaded.")
    return KaldiRecognizer(_VOSK_MODEL, AUDIO_SAMPLE_RATE)


def transcribe_pcm16(pcm_bytes):
    """Run raw 16kHz mono PCM16LE audio through Vosk and return best text."""
    recognizer = get_vosk_recognizer()
    if recognizer is None:
        return ""
    recognizer.AcceptWaveform(pcm_bytes)
    result = json.loads(recognizer.FinalResult())
    return result.get("text", "")


def handle_table_connection(conn, addr, menu_items):
    conn_file = conn.makefile("rwb")
    table_id = f"unknown@{addr[0]}"
    try:
        while APP_STATE["running"]:
            raw = conn_file.readline()
            if not raw:
                break
            try:
                line = raw.decode("utf-8", errors="ignore").strip()
            except UnicodeDecodeError:
                continue
            if not line:
                continue

            if line.startswith("HELLO "):
                table_id = line[len("HELLO "):].strip() or table_id
                table = get_table(table_id)
                table["last_seen"] = time.time()
                table["status"] = "listening"
                log_ai(f"{table_id} connected from {addr[0]}")
                continue

            table = get_table(table_id)
            table["last_seen"] = time.time()

            if line.startswith("AUDIO "):
                # Raw-audio path: table streams PCM16LE mono 16kHz samples,
                # server transcribes locally with Vosk. Frame is:
                #   AUDIO <byte_length>\n<raw bytes>
                try:
                    n_bytes = int(line[len("AUDIO "):].strip())
                except ValueError:
                    conn_file.write(b"ERROR Bad AUDIO frame length.\n")
                    conn_file.flush()
                    continue
                pcm_bytes = conn_file.read(n_bytes)
                utterance = transcribe_pcm16(pcm_bytes)
                if not utterance:
                    conn_file.write(b"SAY Sorry, I didn't catch that. Please try again.\n")
                    conn_file.flush()
                    log_ai(f"{table_id}: audio frame produced no transcription")
                    continue
                log_ai(f"{table_id} (audio) heard: \"{utterance}\"")
                item = match_menu_item(utterance, menu_items)
                if item:
                    table["pending_order"].append(item)
                    table["status"] = "proposing"
                    proposal = json.dumps(table["pending_order"])
                    conn_file.write(f"PROPOSAL {proposal}\n".encode("utf-8"))
                    conn_file.write(
                        f"SAY Adding {item['name']}. Say confirm to place the order, "
                        f"or keep ordering.\n".encode("utf-8")
                    )
                    conn_file.flush()
                    log_ai(f"{table_id} proposal updated: +{item['name']}")
                else:
                    conn_file.write(
                        b"SAY Sorry, I didn't catch an item on the menu. Please try again.\n"
                    )
                    conn_file.flush()
                    log_ai(f"{table_id}: no menu match for \"{utterance}\"")

            elif line.startswith("SPEECH "):
                utterance = line[len("SPEECH "):].strip()
                log_ai(f"{table_id} said: \"{utterance}\"")
                item = match_menu_item(utterance, menu_items)
                if item:
                    table["pending_order"].append(item)
                    table["status"] = "proposing"
                    proposal = json.dumps(table["pending_order"])
                    conn_file.write(f"PROPOSAL {proposal}\n".encode("utf-8"))
                    conn_file.write(
                        f"SAY Adding {item['name']}. Say confirm to place the order, "
                        f"or keep ordering.\n".encode("utf-8")
                    )
                    conn_file.flush()
                    log_ai(f"{table_id} proposal updated: +{item['name']}")
                else:
                    conn_file.write(
                        b"SAY Sorry, I didn't catch an item on the menu. Please try again.\n"
                    )
                    conn_file.flush()
                    log_ai(f"{table_id}: no menu match for \"{utterance}\"")

            elif line.strip() == "CONFIRM":
                if table["pending_order"]:
                    table["confirmed_order"].extend(table["pending_order"])
                    table["pending_order"] = []
                    table["status"] = "confirmed"
                    confirmed = json.dumps(table["confirmed_order"])
                    conn_file.write(f"CONFIRMED {confirmed}\n".encode("utf-8"))
                    conn_file.write(b"SAY Order confirmed. Thank you!\n")
                    conn_file.flush()
                    log_ai(f"{table_id} order CONFIRMED ({len(table['confirmed_order'])} items)")
                else:
                    conn_file.write(b"ERROR Nothing to confirm yet.\n")
                    conn_file.flush()

            elif line.strip() == "CANCEL":
                cleared = len(table["pending_order"])
                table["pending_order"] = []
                table["status"] = "idle"
                conn_file.write(b"SAY Pending order cleared.\n")
                conn_file.flush()
                log_ai(f"{table_id} cleared {cleared} pending item(s)")

            else:
                conn_file.write(f"ERROR Unknown command: {line}\n".encode("utf-8"))
                conn_file.flush()

    except (OSError, ConnectionError) as exc:
        log_ai(f"Connection error with {table_id}: {exc}")
    finally:
        try:
            conn_file.close()
        except OSError:
            pass
        conn.close()
        log_ai(f"{table_id} disconnected")


def audio_engine_thread():
    menu_items = load_menu()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", AUDIO_PORT))
    server.listen(8)
    server.settimeout(1.0)
    log_ai(f"TCP audio engine listening on port {AUDIO_PORT}")

    while APP_STATE["running"]:
        try:
            conn, addr = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(
            target=handle_table_connection,
            args=(conn, addr, menu_items),
            daemon=True,
        ).start()

    server.close()


# --------------------------------------------------------------------------
# Control interface (Flask, port 5001) - optional HTTP view of order state
# --------------------------------------------------------------------------

def control_interface_thread():
    try:
        from flask import Flask, jsonify
    except ImportError:
        log_ai("Flask not installed; control interface disabled.")
        return

    flask_app = Flask("solaria_control")

    @flask_app.route("/status")
    def status():
        with STATE_LOCK:
            tables = {
                tid: {
                    "status": t["status"],
                    "pending_order": t["pending_order"],
                    "confirmed_order": t["confirmed_order"],
                    "last_seen": t["last_seen"],
                }
                for tid, t in APP_STATE["tables"].items()
            }
        return jsonify({"tables": tables})

    @flask_app.route("/menu")
    def menu():
        return jsonify(load_menu())

    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    log_ai(f"Control interface listening on port {CONTROL_PORT}")
    flask_app.run(host="0.0.0.0", port=CONTROL_PORT, debug=False, use_reloader=False)


# --------------------------------------------------------------------------
# 3. Curses dashboard
# --------------------------------------------------------------------------

THEMES = [
    {
        "name": "Default",
        "pairs": {
            "header": (curses.COLOR_BLACK, curses.COLOR_CYAN),
            "border": (curses.COLOR_CYAN, curses.COLOR_BLACK),
            "text": (curses.COLOR_WHITE, curses.COLOR_BLACK),
            "accent": (curses.COLOR_YELLOW, curses.COLOR_BLACK),
            "good": (curses.COLOR_GREEN, curses.COLOR_BLACK),
            "warn": (curses.COLOR_RED, curses.COLOR_BLACK),
        },
    },
    {
        "name": "Matrix Green",
        "pairs": {
            "header": (curses.COLOR_BLACK, curses.COLOR_GREEN),
            "border": (curses.COLOR_GREEN, curses.COLOR_BLACK),
            "text": (curses.COLOR_GREEN, curses.COLOR_BLACK),
            "accent": (curses.COLOR_WHITE, curses.COLOR_BLACK),
            "good": (curses.COLOR_GREEN, curses.COLOR_BLACK),
            "warn": (curses.COLOR_RED, curses.COLOR_BLACK),
        },
    },
    {
        "name": "Ocean Blue",
        "pairs": {
            "header": (curses.COLOR_WHITE, curses.COLOR_BLUE),
            "border": (curses.COLOR_BLUE, curses.COLOR_BLACK),
            "text": (curses.COLOR_CYAN, curses.COLOR_BLACK),
            "accent": (curses.COLOR_WHITE, curses.COLOR_BLACK),
            "good": (curses.COLOR_GREEN, curses.COLOR_BLACK),
            "warn": (curses.COLOR_MAGENTA, curses.COLOR_BLACK),
        },
    },
    {
        "name": "High-Contrast Yellow",
        "pairs": {
            "header": (curses.COLOR_BLACK, curses.COLOR_YELLOW),
            "border": (curses.COLOR_YELLOW, curses.COLOR_BLACK),
            "text": (curses.COLOR_YELLOW, curses.COLOR_BLACK),
            "accent": (curses.COLOR_WHITE, curses.COLOR_BLACK),
            "good": (curses.COLOR_WHITE, curses.COLOR_BLACK),
            "warn": (curses.COLOR_RED, curses.COLOR_BLACK),
        },
    },
]

PAIR_IDS = {"header": 1, "border": 2, "text": 3, "accent": 4, "good": 5, "warn": 6}


def apply_theme(theme_idx):
    theme = THEMES[theme_idx]
    for name, pair_id in PAIR_IDS.items():
        fg, bg = theme["pairs"][name]
        curses.init_pair(pair_id, fg, bg)
    return theme["name"]


def draw_box(win, y, x, h, w, title=""):
    win.attron(curses.color_pair(PAIR_IDS["border"]))
    win.hline(y, x, curses.ACS_HLINE, w)
    win.hline(y + h - 1, x, curses.ACS_HLINE, w)
    win.vline(y, x, curses.ACS_VLINE, h)
    win.vline(y, x + w - 1, curses.ACS_VLINE, h)
    win.addch(y, x, curses.ACS_ULCORNER)
    win.addch(y, x + w - 1, curses.ACS_URCORNER)
    win.addch(y + h - 1, x, curses.ACS_LLCORNER)
    win.addch(y + h - 1, x + w - 1, curses.ACS_LRCORNER)
    win.attroff(curses.color_pair(PAIR_IDS["border"]))
    if title:
        win.attron(curses.color_pair(PAIR_IDS["accent"]) | curses.A_BOLD)
        win.addstr(y, x + 2, f" {title} ")
        win.attroff(curses.color_pair(PAIR_IDS["accent"]) | curses.A_BOLD)


def safe_addstr(win, y, x, text, attr=0):
    max_y, max_x = win.getmaxyx()
    if y < 0 or y >= max_y or x < 0 or x >= max_x:
        return
    try:
        win.addstr(y, x, text[: max(0, max_x - x - 1)], attr)
    except curses.error:
        pass


def curses_main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(300)
    curses.start_color()
    curses.use_default_colors()

    theme_idx = 0
    theme_name = apply_theme(theme_idx)

    APP_STATE["server_ip"] = get_local_ip()

    while APP_STATE["running"]:
        stdscr.erase()
        max_y, max_x = stdscr.getmaxyx()

        # --- Header -----------------------------------------------------
        header_text = " SOLARIA :: Local AI Restaurant Ordering System "
        stdscr.attron(curses.color_pair(PAIR_IDS["header"]) | curses.A_BOLD)
        stdscr.addstr(0, 0, header_text.ljust(max_x))
        stdscr.attroff(curses.color_pair(PAIR_IDS["header"]) | curses.A_BOLD)

        with STATE_LOCK:
            ip = APP_STATE["server_ip"]
            flash_lines = list(APP_STATE["flash_log"])[-200:]
            ai_lines = list(APP_STATE["ai_log"])[-200:]
            tables = dict(APP_STATE["tables"])

        info_line = (
            f" IP: {ip}   Audio Port: {AUDIO_PORT}   Control Port: {CONTROL_PORT}"
            f"   Theme: {theme_name} (press 't')   Quit: 'q' "
        )
        safe_addstr(stdscr, 1, 0, info_line.ljust(max_x), curses.color_pair(PAIR_IDS["text"]))

        top = 3
        bottom_h = max_y - top
        left_w = max_x // 2
        right_w = max_x - left_w

        # --- Left column: Auto-flash log + AI log split top/bottom -----
        flash_h = bottom_h // 2
        ai_h = bottom_h - flash_h

        draw_box(stdscr, top, 0, flash_h, left_w, "Auto-Flash Log")
        for i, line in enumerate(flash_lines[-(flash_h - 2):]):
            safe_addstr(stdscr, top + 1 + i, 2, line, curses.color_pair(PAIR_IDS["text"]))

        draw_box(stdscr, top + flash_h, 0, ai_h, left_w, "AI Log")
        for i, line in enumerate(ai_lines[-(ai_h - 2):]):
            safe_addstr(stdscr, top + flash_h + 1 + i, 2, line, curses.color_pair(PAIR_IDS["text"]))

        # --- Right column: table status ---------------------------------
        draw_box(stdscr, top, left_w, bottom_h, right_w, "Table Status")
        row = top + 1
        if not tables:
            safe_addstr(stdscr, row, left_w + 2, "No tables connected yet.",
                        curses.color_pair(PAIR_IDS["text"]))
        for tid, t in sorted(tables.items()):
            if row >= top + bottom_h - 1:
                break
            status = t["status"]
            status_pair = PAIR_IDS["good"] if status == "confirmed" else (
                PAIR_IDS["warn"] if status == "proposing" else PAIR_IDS["text"]
            )
            safe_addstr(stdscr, row, left_w + 2, f"{tid} [{status}]",
                        curses.color_pair(status_pair) | curses.A_BOLD)
            row += 1
            pending_names = ", ".join(i["name"] for i in t["pending_order"]) or "-"
            confirmed_names = ", ".join(i["name"] for i in t["confirmed_order"]) or "-"
            safe_addstr(stdscr, row, left_w + 4, f"Pending:   {pending_names}",
                        curses.color_pair(PAIR_IDS["accent"]))
            row += 1
            safe_addstr(stdscr, row, left_w + 4, f"Confirmed: {confirmed_names}",
                        curses.color_pair(PAIR_IDS["good"]))
            row += 2

        stdscr.refresh()

        try:
            key = stdscr.getch()
        except curses.error:
            key = -1

        if key in (ord("q"), ord("Q")):
            APP_STATE["running"] = False
            break
        elif key in (ord("t"), ord("T")):
            theme_idx = (theme_idx + 1) % len(THEMES)
            theme_name = apply_theme(theme_idx)


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------

def main():
    threading.Thread(target=auto_flasher_thread, daemon=True).start()
    threading.Thread(target=audio_engine_thread, daemon=True).start()
    threading.Thread(target=control_interface_thread, daemon=True).start()

    try:
        curses.wrapper(curses_main)
    finally:
        APP_STATE["running"] = False


if __name__ == "__main__":
    main()
