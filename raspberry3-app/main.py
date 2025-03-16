import requests
import time
from mfrc522 import SimpleMFRC522

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
        else:
            print(f"⚠️ Eroare API: {data}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Eroare conexiune API: {e}")

print("📡 Aștept citiri de la RFID... Apropie un card!")

try:
    while True:
        # Citește un card RFID
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
    pass
