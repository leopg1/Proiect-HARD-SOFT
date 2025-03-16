import requests
import time
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522

# Configurare GPIO pentru LED-uri
LED1 = 17  # GPIO pentru LED1
LED2 = 27  # GPIO pentru LED2

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED1, GPIO.OUT)
GPIO.setup(LED2, GPIO.OUT)

# **Forțăm LED-urile să fie stinse la pornire**
GPIO.output(LED1, GPIO.LOW)
GPIO.output(LED2, GPIO.LOW)

# Configurare cititor RFID
reader = SimpleMFRC522()

# URL-ul API-ului
API_URL = "http://192.168.111.164:5000/rfid"

def send_rfid_to_server(rfid_code):
    """Trimite un request POST cu RFID-ul citit"""
    payload = {"rfid_code": rfid_code}
    
    try:
        response = requests.post(API_URL, json=payload)
        data = response.json()

        if response.status_code == 200:
            print(f"✅ Răspuns API: {data}")

            led_status = data.get("led_status", "none")

            # **Aprinde doar LED-ul corespunzător, stinge celălalt**
            if led_status == "LED1":
                GPIO.output(LED1, GPIO.HIGH)
                GPIO.output(LED2, GPIO.LOW)
                print("💡 LED1 APRINS! (LED2 STINS)")

            elif led_status == "LED2":
                GPIO.output(LED1, GPIO.LOW)
                GPIO.output(LED2, GPIO.HIGH)
                print("💡 LED2 APRINS! (LED1 STINS)")

            else:
                GPIO.output(LED1, GPIO.LOW)
                GPIO.output(LED2, GPIO.LOW)
                print("💡 LEDURILE STINSE!")

        else:
            print(f"⚠️ Eroare API: {data}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Eroare conexiune API: {e}")

print("📡 Aștept citiri de la RFID... Apropie un card!")

try:
    while True:
        # **Forțăm LED-urile să fie stinse înainte de a începe o nouă citire**
        GPIO.output(LED1, GPIO.LOW)
        GPIO.output(LED2, GPIO.LOW)

        print("\n📌 Scanează un card...")
        rfid_code, _ = reader.read()
        rfid_code = str(rfid_code).strip()  # Convertim la string și eliminăm spațiile
        
        print(f"🔍 Card citit: {rfid_code}")

        # Trimite POST către server
        send_rfid_to_server(rfid_code)

        # Pauză pentru a evita citiri multiple la aceeași scanare
        time.sleep(2)

except KeyboardInterrupt:
    print("\n❌ Oprire script RFID.")
finally:
    GPIO.cleanup()  # Resetare GPIO la ieșirea din program
