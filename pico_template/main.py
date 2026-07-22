import network
import socket
import time
from machine import Pin

# Hardware Pin Assignments
SCK_PIN = 16
WS_PIN = 17
SD_PIN = 18

BCLK_PIN = 20
LRC_PIN = 21
DIN_PIN = 22

touch_sensor = Pin(15, Pin.IN)

# Network values injected automatically during auto-flash
WIFI_SSID = ''
WIFI_PASS = ''
TABLE_ID = ''
SERVER_IP = ''
PORT = 5000

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to network...')
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            time.sleep(1)
    print('Network config:', wlan.ifconfig())

def stream_audio(action="ORDER"):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((SERVER_IP, PORT))
        s.send(f"{TABLE_ID}|{action}|".encode('utf-8'))
        time.sleep(2)
        s.close()
    except Exception as e:
        print("Socket error:", e)

def main():
    if not WIFI_SSID:
        print("Awaiting configuration payload from Solaria...")
        return
        
    connect_wifi()
    print(f"[{TABLE_ID}] Ready.")
    
    button_pressed = False
    
    while True:
        if touch_sensor.value() == 1 and not button_pressed:
            button_pressed = True
            stream_audio("ORDER")
            time.sleep(1)
        elif touch_sensor.value() == 0:
            button_pressed = False
            
        time.sleep(0.1)

if __name__ == "__main__":
    main()
