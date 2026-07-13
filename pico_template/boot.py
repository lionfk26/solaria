import network
import time

# --- NETWORK CONFIGURATION ---
WIFI_SSID = "Your_Restaurant_WiFi"
WIFI_PASSWORD = "Your_WiFi_Password"

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to Wi-Fi...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        timeout = 0
        while not wlan.isconnected() and timeout < 15:
            time.sleep(1)
            timeout += 1
            
    if wlan.isconnected():
        print("Network connection established. Local IP:", wlan.ifconfig()[0])
    else:
        print("Wi-Fi connection failed.")

connect_wifi()
