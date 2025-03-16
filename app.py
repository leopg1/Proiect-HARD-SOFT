from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

# Configurare baza de date SQLite
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "rfid.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Inițializare SQLAlchemy
db = SQLAlchemy(app)

# Definirea modelului bazei de date
class RFIDEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfid_code = db.Column(db.String(50), unique=True, nullable=False)
    led_status = db.Column(db.String(10), nullable=False)  # "led1", "led2", "none"

class LEDStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    active_led = db.Column(db.String(10), nullable=False, default="none")  # Poate fi "LED1", "LED2" sau "none"



# Creare baza de date
#la pornirea serverului, daca tabelul LEDSTatus este gol, se adauga un rand cu active_led="none"
with app.app_context():
    db.create_all()
    if not LEDStatus.query.first():
        db.session.add(LEDStatus(active_led="none"))
        db.session.commit()

#aceasta initializare asigura ca la inceput niciun LED nu este aprins

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Serverul Flask funcționează!"})

@app.route("/rfid", methods=["POST"])
def receive_rfid():
    data = request.get_json()

    if not data or "rfid_code" not in data:
        return jsonify({"error": "Lipsește RFID code"}), 400

    rfid_code = data["rfid_code"]

    # Mapează RFID-uri la LED-uri (GPIO-uri)
    led_mapping = {
        "423423": "LED1",
        "2312345": "LED2"
    }

    # Determinăm LED-ul activ pe baza RFID-ului scanat
    led_status = led_mapping.get(rfid_code, "none")

    # Actualizăm baza de date pentru a seta doar un LED activ la un moment dat
    led_record = LEDStatus.query.first()
    led_record.active_led = led_status
    db.session.commit()

    # Adăugăm RFID-ul în baza de date (istoric)
    new_entry = RFIDEntry(rfid_code=rfid_code, led_status=led_status)
    db.session.add(new_entry)
    db.session.commit()

    return jsonify({"rfid_code": rfid_code, "led_status": led_status}), 200
# primeste rfid code si daca este in baza de date seteaza LED ul corespunzator daca nu este cunoscut seteaza none
# si apoi actualizeaza LEDStatus in baza de date



#Returnează istoricul RFID-urilor
@app.route("/history", methods=["GET"])
def get_history():
    entries = RFIDEntry.query.all()
    history = [{"id": entry.id, "rfid_code": entry.rfid_code} for entry in entries]
    return jsonify(history), 200

#returnare led aprins
@app.route("/led_status", methods=["GET"])
def get_led_status():
    led_record = LEDStatus.query.first()
    return jsonify({"active_led": led_record.active_led}), 200


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
