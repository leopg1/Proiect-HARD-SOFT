from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "supersecretkey"  # Cheie secretă pentru sesiuni
socketio = SocketIO(app, cors_allowed_origins="*")


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

class RFIDHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfid_code = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())  # Ora scanării
    scan_count = db.Column(db.Integer, nullable=False, default=1)

class RFIDTags(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfid_code = db.Column(db.String(50), unique=True, nullable=False)
    tag_type = db.Column(db.String(20), nullable=False)  # "login" sau "led"


class LEDStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    active_led = db.Column(db.String(10), nullable=False, default="none")  # Poate fi "LED1", "LED2" sau "none"



# Creare baza de date
#la pornirea serverului, daca tabelul LEDSTatus este gol, se adauga un rand cu active_led="none"
with app.app_context():
    db.create_all()

    # Adăugăm RFID-urile predefinite pentru login și LED-uri
    predefined_tags = [
        {"rfid_code": "154410945857", "tag_type": "login"},  # RFID pentru conectare
        {"rfid_code": "977790505602", "tag_type": "led"},  # 🔄 Nou RFID pentru LED1
        {"rfid_code": "223247207766", "tag_type": "led"}  # 🔄 Nou RFID pentru LED2
    ]

    for tag in predefined_tags:
        existing_tag = RFIDTags.query.filter_by(rfid_code=tag["rfid_code"]).first()
        if not existing_tag:
            db.session.add(RFIDTags(rfid_code=tag["rfid_code"], tag_type=tag["tag_type"]))

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

    # Căutăm RFID-ul în tabela `RFIDTags`
    tag_entry = RFIDTags.query.filter_by(rfid_code=rfid_code).first()

    if tag_entry:
        if tag_entry.tag_type == "led":
            # Mapează RFID la LED-uri
            led_mapping = {
                "977790505602": "LED1",
                "223247207766": "LED2"
            }
            led_status = led_mapping.get(rfid_code, "none")

            # Dezactivăm LED-ul precedent înainte de a aprinde altul
            led_record = LEDStatus.query.first()
            if led_record:
                led_record.active_led = "none"
                db.session.commit()

            # Aprindem LED-ul corespunzător
            led_record.active_led = led_status
            db.session.commit()

            # Trimitem update către WebSockets (pentru dashboard)
            socketio.emit("led_status_update", {"active_led": led_status})

            response = {
                "rfid_code": rfid_code,
                "tag_type": "led",
                "led_status": led_status
            }

        elif tag_entry.tag_type == "login":
            # ✅ SALVĂM RFID-UL DE LOGIN ÎN ISTORIC
            session["logged_in"] = True

            # Trimitem un mesaj WebSocket pentru redirecționare
            socketio.emit("redirect_to_dashboard", {"redirect": "/dashboard"})

            response = {
                "rfid_code": rfid_code,
                "tag_type": "login",
                "message": "Autentificare reușită"
            }

    else:
        # Dacă RFID-ul nu este cunoscut, îl salvăm în istoric
        response = {
            "rfid_code": rfid_code,
            "tag_type": "unknown",
            "message": "Tag necunoscut"
        }

    # ✅ MODIFICĂM ACEST COD PENTRU A INCLUDE ȘI RFID-URILE DE LOGIN
    history_entry = RFIDHistory.query.filter_by(rfid_code=rfid_code).first()

    if history_entry:
        history_entry.scan_count += 1  # ✅ Incrementăm numărul de scanări pentru TOATE RFID-urile
    else:
        history_entry = RFIDHistory(rfid_code=rfid_code, scan_count=1)
        db.session.add(history_entry)

    db.session.commit()

    # ✅ Trimitem actualizare istoric prin WebSockets
    history_entries = RFIDHistory.query.order_by(RFIDHistory.timestamp.desc()).all()
    history_data = [
        {
            "id": entry.id,
            "rfid_code": entry.rfid_code,
            "scan_count": entry.scan_count,
            "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }
        for entry in history_entries
    ]
    socketio.emit("history_update", history_data)

    return jsonify(response), 200



#Returnează istoricul RFID-urilor
@app.route("/history", methods=["GET"])
def get_history():
    entries = RFIDHistory.query.order_by(RFIDHistory.timestamp.desc()).all()
    history = [
        {
            "id": entry.id,
            "rfid_code": entry.rfid_code,
            "scan_count": entry.scan_count,
            "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }
        for entry in entries
    ]

    return jsonify(history), 200

#returnare led aprins
@app.route("/led_status", methods=["GET"])
def get_led_status():
    led_record = LEDStatus.query.first()
    return jsonify({"active_led": led_record.active_led}), 200

@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    rfid_code = data.get("rfid_code")

    # Verifică dacă RFID-ul este un tag de login
    tag = RFIDTags.query.filter_by(rfid_code=rfid_code, tag_type="login").first()

    if tag:
        session["logged_in"] = True

        # ✅ Salvăm în istoricul scanărilor și tag-urile de login
        history_entry = RFIDHistory.query.filter_by(rfid_code=rfid_code).first()
        if history_entry:
            history_entry.scan_count += 1  # ✅ Incrementăm numărul de scanări
        else:
            history_entry = RFIDHistory(rfid_code=rfid_code, scan_count=1)
            db.session.add(history_entry)

        db.session.commit()

        # ✅ Trimitem update către WebSockets pentru dashboard
        history_entries = RFIDHistory.query.order_by(RFIDHistory.timestamp.desc()).all()
        history_data = [
            {
                "id": entry.id,
                "rfid_code": entry.rfid_code,
                "scan_count": entry.scan_count,
                "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            }
            for entry in history_entries
        ]
        socketio.emit("history_update", history_data)

        # ✅ Trimite un eveniment WebSocket pentru redirecționare
        socketio.emit("redirect_to_dashboard", {"redirect": "/dashboard"})

        return jsonify({"message": "Autentificare reușită!", "redirect": "/dashboard"}), 200
    else:
        return jsonify({"error": "Tag RFID invalid!"}), 401

#################################################
# Pagină Dashboard (momentan doar afișare)
@app.route("/dashboard", methods=["GET"])
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("dashboard.html")

@socketio.on("request_history_update")
def send_history_update():
    """Trimite istoricul actualizat către toți clienții conectați"""
    history_entries = RFIDHistory.query.order_by(RFIDHistory.timestamp.desc()).all()
    history_data = [
        {
            "id": entry.id,
            "rfid_code": entry.rfid_code,
            "scan_count": entry.scan_count,
            "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }
        for entry in history_entries
    ]
    socketio.emit("history_update", history_data)

@socketio.on("request_led_status")
def send_led_status():
    """Trimite starea LED-ului activ către toți clienții conectați"""
    led_record = LEDStatus.query.first()
    socketio.emit("led_status_update", {"active_led": led_record.active_led})

##########################################


@app.route("/scan_rfid", methods=["POST"])
def scan_rfid():
    data = request.get_json()
    rfid_code = data.get("rfid_code")

    # Verifică dacă tag-ul este înregistrat în baza de date
    tag_entry = RFIDTags.query.filter_by(rfid_code=rfid_code).first()

    if not tag_entry:
        return jsonify({"error": "Tag RFID necunoscut"}), 400

    # Dacă este un tag de login, îl trimitem către /api/login
    if tag_entry.tag_type == "login":
        return redirect(url_for("api_login"), code=307)  # Trimite același request către /api/login

    # Dacă este un tag de LED, îl trimitem către /rfid
    elif tag_entry.tag_type == "led":
        return redirect(url_for("receive_rfid"), code=307)  # Trimite același request către /rfid

    return jsonify({"error": "Tip RFID necunoscut"}), 400


@app.route("/clear_history", methods=["POST"])
def clear_history():
    """Șterge istoricul scanărilor RFID"""
    try:
        db.session.query(RFIDHistory).delete()  # Șterge toate înregistrările
        db.session.commit()

        # Trimitem update către WebSockets pentru a actualiza UI-ul
        socketio.emit("history_update", [])

        return jsonify({"message": "Istoricul a fost șters!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
