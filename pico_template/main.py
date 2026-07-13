import urequests
import time
import ujson
from machine import Pin

# --- CORE SETTINGS ---
TABLE_ID = "Table_1"
SERVER_URL = "http://192.168.1.100:5000"  # Replace with your actual Pi 4B IP address

# --- HARDWARE SETUP ---
# Initialize the touch sensor on GPIO 15 as an input
touch_sensor = Pin(15, Pin.IN)

def send_event(event_type: str, payload: dict) -> bool:
    """Sends structured data payloads to the main Solaria hub."""
    url = f"{SERVER_URL}/{event_type}"
    headers = {'content-type': 'application/json'}
    data = ujson.dumps(payload)
    
    try:
        response = urequests.post(url, data=data, headers=headers)
        response.close()
        return True
    except Exception as e:
        print("Network connection trace failure:", e)
        return False

# Self-register with server upon power-up initialization
send_event("register_table", {"table_id": TABLE_ID})

print(f"[{TABLE_ID}] Ready. Monitoring touch sensor on GP15.")

# Track the current state to prevent spamming the server
assistance_active = False

while True:
    # touch_sensor.value() returns 1 when touched, 0 when not touched
    current_touch_state = touch_sensor.value()
    
    # If the sensor is touched AND we haven't already called for help
    if current_touch_state == 1 and not assistance_active:
        print(f"[{TABLE_ID}] Touch detected! Requesting assistance...")
        
        # Send the alert to the Solaria terminal dashboard
        success = send_event("request_assistance", {"table_id": TABLE_ID, "needs_help": True})
        
        if success:
            assistance_active = True
            
        # 2-second cooldown so a lingering finger doesn't trigger multiple times
        time.sleep(2) 
        
    # Optional Reset Logic: 
    # If you want the customer to be able to "cancel" the call by touching it again,
    # you can listen for another touch event here to send "needs_help": False.
    # For now, we will leave it so the manager clears it from the central dashboard.

    # A tiny sleep to prevent the while loop from maxing out the Pico's processor
    time.sleep(0.1)
