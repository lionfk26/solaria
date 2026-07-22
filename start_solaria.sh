#!/usr/bin/env bash
#
# start_solaria.sh
# Interactive login/launcher shell for the Solaria restaurant ordering system.
#
#   - Prompts for a username/password before doing anything else.
#   - While at the login prompt, typing "help" shows a CLI cheat sheet.
#   - Typing "wifi reset" (as the username) walks through resetting the
#     Wi-Fi credentials that get flashed onto each table's Pico.
#   - On successful login, hands off to ./auto_run.sh.

set -u

SOLARIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SOLARIA_DIR}"

DEFAULT_USER="admin"
DEFAULT_PASS="solaria2026"

WIFI_SSID_FILE="${SOLARIA_DIR}/wifi_ssid.txt"
WIFI_PASS_FILE="${SOLARIA_DIR}/wifi_pass.txt"

BANNER='
   _____       _            _
  / ____|     | |          (_)
 | (___   ___ | | __ _ _ __ _  __ _
  \___ \ / _ \| |/ _` | `__| |/ _` |
  ____) | (_) | | (_| | |  | | (_| |
 |_____/ \___/|_|\__,_|_|  |_|\__,_|

      Local AI Restaurant Ordering System
'

print_help() {
    cat <<'EOF'

Solaria CLI Cheat Sheet
------------------------------------------------------------
  help          Show this cheat sheet.
  wifi reset    Reset the Wi-Fi SSID/password used when
                flashing new table Picos. You will be
                prompted for a new SSID and password.
  <username>    Enter your username to continue logging in.
  Ctrl+C        Abort at any time.

Once logged in, Solaria will:
  1. Check for an internet connection.
  2. Pull the latest code with git.
  3. Activate the Python virtual environment.
  4. Install/update Python dependencies.
  5. Launch the main Solaria dashboard (app.py).

Inside the dashboard:
  t             Cycle UI color theme.
  q             Quit the dashboard cleanly.
------------------------------------------------------------

EOF
}

do_wifi_reset() {
    echo
    echo "== Wi-Fi Reset =="
    read -rp "New Wi-Fi SSID: " new_ssid
    read -rsp "New Wi-Fi Password: " new_pass
    echo

    if [ -z "${new_ssid}" ]; then
        echo "SSID cannot be empty. Aborting Wi-Fi reset."
        return 1
    fi

    printf '%s' "${new_ssid}" > "${WIFI_SSID_FILE}"
    printf '%s' "${new_pass}" > "${WIFI_PASS_FILE}"
    chmod 600 "${WIFI_SSID_FILE}" "${WIFI_PASS_FILE}"

    echo "Wi-Fi credentials saved. New tables flashed from now on will use:"
    echo "  SSID: ${new_ssid}"
    echo
}

login_prompt() {
    while true; do
        echo "${BANNER}"
        read -rp "solaria login: " entered_user

        case "${entered_user}" in
            help)
                print_help
                continue
                ;;
            "wifi reset"|wifi)
                do_wifi_reset
                continue
                ;;
        esac

        read -rsp "Password: " entered_pass
        echo

        if [ "${entered_user}" = "${DEFAULT_USER}" ] && [ "${entered_pass}" = "${DEFAULT_PASS}" ]; then
            echo
            echo "Login OK. Starting Solaria..."
            sleep 1
            return 0
        else
            echo
            echo "Invalid credentials. Type 'help' for the cheat sheet, or try again."
            echo
        fi
    done
}

login_prompt

if [ ! -x "${SOLARIA_DIR}/auto_run.sh" ]; then
    chmod +x "${SOLARIA_DIR}/auto_run.sh" 2>/dev/null || true
fi

exec "${SOLARIA_DIR}/auto_run.sh"
