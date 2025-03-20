from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from sqlalchemy import text
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
    user_name = db.Column(db.String(50), nullable=True)  #  ADĂUGAT user_name

class RFIDTags(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfid_code = db.Column(db.String(50), unique=True, nullable=False)
    tag_type = db.Column(db.String(20), nullable=False)  # "login" sau "led"
    user_name = db.Column(db.String(50), nullable=True)  #  ADĂUGAT user_name


class LEDStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    active_led = db.Column(db.String(10), nullable=False, default="none")  # Poate fi "LED1", "LED2" sau "none"

class MotorState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    motor1 = db.Column(db.String(10), nullable=False, default="oprit")
    motor2 = db.Column(db.String(10), nullable=False, default="oprit")


class DutyCycle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    motor1 = db.Column(db.Integer, nullable=False, default=0)  # Duty Cycle pentru motor 1
    motor2 = db.Column(db.Integer, nullable=False, default=0)  # Duty Cycle pentru motor 2



# Creare baza de date
#la pornirea serverului, daca tabelul LEDSTatus este gol, se adauga un rand cu active_led="none"
with app.app_context():
    db.create_all()

    # ✅ Adăugăm manual coloana `user_name` în `rfid_tags` dacă nu există deja
    try:
        # Interogăm baza de date pentru a verifica dacă `user_name` există
        existing_columns = db.session.execute(text("PRAGMA table_info(rfid_tags);")).fetchall()
        column_names = [column[1] for column in existing_columns]
        led_record = LEDStatus.query.first()
        if not led_record:
            led_record = LEDStatus(active_led="none")
            db.session.add(led_record)
            db.session.commit()
        if not MotorState.query.first():
            db.session.add(MotorState(motor1="oprit", motor2="oprit"))
            db.session.commit()
        if "user_name" not in column_names:
            db.session.execute(text("ALTER TABLE rfid_tags ADD COLUMN user_name VARCHAR(50) DEFAULT 'Unknown';"))
            db.session.commit()
            print("✅ Coloana `user_name` a fost adăugată cu succes!")
        else:
            print("ℹ️ Coloana `user_name` există deja. Nu a fost necesară nicio modificare.")

    except Exception as e:
        print(f"❌ Eroare la adăugarea coloanei user_name: {e}")

    #  Adăugăm RFID-urile predefinite pentru login și LED-uri
    predefined_tags = [
        {"rfid_code": "154410945857", "tag_type": "login", "user_name": "Leonard Pădurean"},
        {"rfid_code": "977790505602", "tag_type": "led", "user_name": None},
        {"rfid_code": "223247207766", "tag_type": "led", "user_name": None}
    ]

    for tag in predefined_tags:
        existing_tag = RFIDTags.query.filter_by(rfid_code=tag["rfid_code"]).first()
        if not existing_tag:
            db.session.add(RFIDTags(rfid_code=tag["rfid_code"], tag_type=tag["tag_type"], user_name=tag["user_name"]))
        else:
            #  Dacă RFID-ul există deja, dar nu are nume, actualizăm
            if existing_tag.user_name is None:
                existing_tag.user_name = tag["user_name"]
    
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

            # Verificăm dacă există deja un LED activ
            led_record = LEDStatus.query.first()
            if not led_record:
                led_record = LEDStatus(active_led="none")
                db.session.add(led_record)
                db.session.commit()

            # Dezactivăm LED-ul precedent
            led_record.active_led = "none"
            db.session.commit()

            # Aprindem LED-ul corespunzător
            led_record.active_led = led_status
            db.session.commit()

            #  Salvăm în istoricul scanărilor
            history_entry = RFIDHistory.query.filter_by(rfid_code=rfid_code).first()
            if history_entry:
                history_entry.scan_count += 1  #  Incrementăm numărul de scanări
            else:
                history_entry = RFIDHistory(rfid_code=rfid_code, scan_count=1)
                db.session.add(history_entry)

            db.session.commit()

            #  Trimitem update către WebSockets (pentru dashboard)
            socketio.emit("led_status_update", {"active_led": led_status})

            #  Trimitem actualizare istoric prin WebSockets
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

            return jsonify({
                "rfid_code": rfid_code,
                "tag_type": "led",
                "led_status": led_status
            }), 200

        if tag_entry.tag_type == "login":
            session["logged_in"] = True
            session["user_name"] = tag_entry.user_name  

            #  Salvăm în istoricul scanărilor și tag-urile de login
            history_entry = RFIDHistory.query.filter_by(rfid_code=rfid_code).first()
            if history_entry:
                history_entry.scan_count += 1  #  Incrementăm numărul de scanări
            else:
                history_entry = RFIDHistory(
                    rfid_code=rfid_code,
                    scan_count=1,
                    user_name=tag_entry.user_name  #  Salvăm numele utilizatorului
                )
                db.session.add(history_entry)

            db.session.commit()
        

            #  Trimitem update către WebSockets pentru dashboard cu user_name
            history_entries = db.session.query(
                RFIDHistory.id,
                RFIDHistory.rfid_code,
                RFIDHistory.scan_count,
                RFIDHistory.timestamp,
                RFIDTags.user_name
            ).outerjoin(RFIDTags, RFIDHistory.rfid_code == RFIDTags.rfid_code) \
            .order_by(RFIDHistory.timestamp.desc()).all()

            history_data = [
                {
                    "id": entry.id,
                    "rfid_code": entry.rfid_code,
                    "scan_count": entry.scan_count,
                    "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "user_name": entry.user_name if entry.user_name else "Tag necunoscut"
                }
                for entry in history_entries
            ]
            socketio.emit("history_update", history_data)

            #  Trimitem un mesaj WebSocket pentru redirecționare și afișare nume
            socketio.emit("redirect_to_dashboard", {
                "redirect": "/dashboard",
                "user_name": tag_entry.user_name
            })

            return jsonify({
                "rfid_code": rfid_code,
                "tag_type": "login",
                "message": f"Autentificare reușită! Welcome, {tag_entry.user_name}!"
            }), 200
    else:
        # Dacă RFID-ul nu este cunoscut, îl salvăm în istoric
        history_entry = RFIDHistory.query.filter_by(rfid_code=rfid_code).first()
        if history_entry:
            history_entry.scan_count += 1  #  Incrementăm numărul de scanări
        else:
            history_entry = RFIDHistory(
                rfid_code=rfid_code,
                scan_count=1
            )
            db.session.add(history_entry)

        #  Salvăm `user_name` în istoric
        if tag_entry:
            history_entry.user_name = tag_entry.user_name if tag_entry.user_name else "Tag necunoscut"
        else:
            history_entry.user_name = "Tag necunoscut"  #  Dacă nu există tag_entry, setăm direct "Tag necunoscut"
        db.session.commit()
        #  Trimitem actualizare istoric prin WebSockets
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

        return jsonify({
            "rfid_code": rfid_code,
            "tag_type": "unknown",
            "message": "Tag necunoscut"
        }), 400


#Endpoint pentru setarea directiei motoarelor
@app.route("/set_motors", methods=["POST"])
def set_motors():
    """Setează direcția motoarelor și trimite update prin WebSockets"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request invalid, trebuie să conțină JSON"}), 400

    motor_state = MotorState.query.first()

    if not motor_state:
        return jsonify({"error": "Nu există stare inițială a motoarelor"}), 500

    # Actualizăm motorul doar dacă există în request
    if "motor1" in data:
        if data["motor1"] in ["inainte", "inapoi", "oprit"]:
            motor_state.motor1 = data["motor1"]
        else:
            return jsonify({"error": "Stare invalidă pentru motor1!"}), 400

    if "motor2" in data:
        if data["motor2"] in ["inainte", "inapoi", "oprit"]:
            motor_state.motor2 = data["motor2"]
        else:
            return jsonify({"error": "Stare invalidă pentru motor2!"}), 400

    db.session.commit()

    # ✅ Emitere WebSocket pentru update instantaneu
    socketio.emit("motor_status_update", {
        "motor1": motor_state.motor1,
        "motor2": motor_state.motor2
    })

    return jsonify({
        "message": "Starea motoarelor a fost actualizată!",
        "motor1": motor_state.motor1,
        "motor2": motor_state.motor2
    }), 200


@app.route("/motor_status", methods=["GET"])
def motor_status():
    motor_state = MotorState.query.first()
    return jsonify({
        "motor1": motor_state.motor1,
        "motor2": motor_state.motor2
    })

@app.route("/motoare", methods=["GET"])
def motoare():
    return render_template("motoare.html")


@socketio.on("request_motor_status")
def send_motor_status():
    """Trimite starea motoarelor către toți clienții conectați"""
    motor_state = MotorState.query.first()
    socketio.emit("motor_status_update", {
        "motor1": motor_state.motor1,
        "motor2": motor_state.motor2
    })


@app.route("/set_duty_cycle", methods=["POST"])
def set_duty_cycle():
    data = request.get_json()

    # Verificăm dacă datele sunt corecte
    if not data:
        return jsonify({"error": "Date invalide!"}), 400

    # Citim valorile trimise pentru motor1 și motor2
    motor1_duty = data.get("motor1")
    motor2_duty = data.get("motor2")

    # Verificăm dacă valorile sunt între 0 și 100%
    if motor1_duty is not None:
        motor1_duty = max(0, min(100, motor1_duty))  # Limităm între 0-100

    if motor2_duty is not None:
        motor2_duty = max(0, min(100, motor2_duty))

    # Căutăm dacă avem deja valori salvate în baza de date
    duty_record = DutyCycle.query.first()

    if duty_record:
        if motor1_duty is not None:
            duty_record.motor1 = motor1_duty
        if motor2_duty is not None:
            duty_record.motor2 = motor2_duty
    else:
        duty_record = DutyCycle(motor1=motor1_duty or 0, motor2=motor2_duty or 0)
        db.session.add(duty_record)

    db.session.commit()

    # Emitere update prin WebSockets către toate paginile conectate
    socketio.emit("duty_cycle_update", {"motor1": duty_record.motor1, "motor2": duty_record.motor2})

    return jsonify({
        "message": "Duty cycle setat!",
        "duty_cycle": {
            "motor1": duty_record.motor1,
            "motor2": duty_record.motor2
        }
    }), 200


@app.route("/get_duty_cycle", methods=["GET"])
def get_duty_cycle():
    duty_record = DutyCycle.query.first()

    if duty_record:
        return jsonify({
            "motor1": duty_record.motor1,
            "motor2": duty_record.motor2
        }), 200
    else:
        return jsonify({
            "motor1": 0,
            "motor2": 0
        }), 200


#Returnează istoricul RFID-urilor
@app.route("/history", methods=["GET"])
def get_history():
    # Folosim un JOIN pentru a obține și numele utilizatorului asociat fiecărui RFID
    history_entries = db.session.query(
        RFIDHistory.id,
        RFIDHistory.rfid_code,
        RFIDHistory.scan_count,
        RFIDHistory.timestamp,
        RFIDTags.user_name
    ).outerjoin(RFIDTags, RFIDHistory.rfid_code == RFIDTags.rfid_code) \
    .order_by(RFIDHistory.timestamp.desc()).all()

    history_data = [
        {
            "id": entry.id,
            "rfid_code": entry.rfid_code,
            "scan_count": entry.scan_count,
            "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "user_name": entry.user_name if entry.user_name else "Tag necunoscut"
        }
        for entry in history_entries
    ]

    return jsonify(history_data), 200

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
        session["user_name"] = tag.user_name  #  Stocăm numele utilizatorului în sesiune

        #  Salvăm în istoricul scanărilor și tag-urile de login
        history_entry = RFIDHistory.query.filter_by(rfid_code=rfid_code).first()
        if history_entry:
            history_entry.user_name = tag.user_name  # ✅ Adăugăm numele în istoricul scanărilor
        else:
            history_entry = RFIDHistory(rfid_code=rfid_code, scan_count=1, user_name=tag.user_name)
            db.session.add(history_entry)

        db.session.commit()

        #  Trimitem update către WebSockets pentru dashboard
        history_entries = db.session.query(
            RFIDHistory.id,
            RFIDHistory.rfid_code,
            RFIDHistory.scan_count,
            RFIDHistory.timestamp,
            RFIDTags.user_name
        ).outerjoin(RFIDTags, RFIDHistory.rfid_code == RFIDTags.rfid_code) \
        .order_by(RFIDHistory.timestamp.desc()).all()

        history_data = [
            {
                "id": entry.id,
                "rfid_code": entry.rfid_code,
                "scan_count": entry.scan_count,
                "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "user_name": entry.user_name if entry.user_name else "Tag necunoscut"
            }
            for entry in history_entries
        ]
        socketio.emit("history_update", history_data)

        #  Trimite un eveniment WebSocket pentru redirecționare și afișare nume
        socketio.emit("redirect_to_dashboard", {
            "redirect": "/dashboard",
            "user_name": tag.user_name  #  Trimite numele utilizatorului în WebSocket
        })

        return jsonify({
            "message": f"Autentificare reușită! Welcome, {tag.user_name}!",
            "redirect": "/dashboard",
            "user_name": tag.user_name
        }), 200
    else:
        return jsonify({"error": "Tag RFID invalid!"}), 401


#################################################
# Pagină Dashboard (momentan doar afișare)
@app.route("/dashboard", methods=["GET"])
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    user_name = session.get("user_name", "User")  #  Preluăm numele utilizatorului
    return render_template("dashboard.html", user_name=user_name)

@socketio.on("request_history_update")
def send_history_update():
    history_entries = db.session.query(
        RFIDHistory.id,
        RFIDHistory.rfid_code,
        RFIDHistory.scan_count,
        RFIDHistory.timestamp,
        RFIDHistory.user_name  #  Folosim user_name direct din RFIDHistory
    ).order_by(RFIDHistory.timestamp.desc()).all()

    history_data = [
        {
            "id": entry.id,
            "rfid_code": entry.rfid_code,
            "scan_count": entry.scan_count,
            "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "user_name": entry.user_name if entry.user_name else "Tag necunoscut"  #  Afișează "Tag necunoscut" dacă user_name nu există
        }
        for entry in history_entries
    ]

    socketio.emit("history_update", history_data)

@socketio.on("request_led_status")
def send_led_status():
    """Trimite starea LED-ului activ către toți clienții conectați"""
    led_record = LEDStatus.query.first()
    if led_record:
        socketio.emit("led_status_update", {"active_led": led_record.active_led})

##########################################


@app.route("/scan_rfid", methods=["POST"])
def scan_rfid():
    data = request.get_json()
    rfid_code = data.get("rfid_code")

    if not rfid_code:
        return jsonify({"error": "Lipsește RFID code"}), 400

    # Verificăm dacă tag-ul există în baza de date
    tag_entry = RFIDTags.query.filter_by(rfid_code=rfid_code).first()

    #  Salvăm RFID-ul în istoric înainte de orice altă acțiune
    history_entry = RFIDHistory.query.filter_by(rfid_code=rfid_code).first()
    if history_entry:
        history_entry.scan_count += 1  #  Incrementăm numărul de scanări
    else:
        history_entry = RFIDHistory(rfid_code=rfid_code, scan_count=1)
        db.session.add(history_entry)

    db.session.commit()

    #  Emitere WebSocket pentru actualizarea istoricului
    history_entries = db.session.query(
        RFIDHistory.id,
        RFIDHistory.rfid_code,
        RFIDHistory.scan_count,
        RFIDHistory.timestamp,
        RFIDTags.user_name
    ).outerjoin(RFIDTags, RFIDHistory.rfid_code == RFIDTags.rfid_code) \
    .order_by(RFIDHistory.timestamp.desc()).all()

    history_data = [
        {
            "id": entry.id,
            "rfid_code": entry.rfid_code,
            "scan_count": entry.scan_count,
            "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "user_name": entry.user_name if entry.user_name else "Tag necunoscut"
        }
        for entry in history_entries
    ]
    socketio.emit("history_update", history_data)

    # ✅ După salvare, redirecționăm către endpoint-ul corect
    if tag_entry:
        if tag_entry.tag_type == "login":
            return redirect(url_for("api_login"), code=307)  # Trimite același request către /api/login
        elif tag_entry.tag_type == "led":
            return redirect(url_for("receive_rfid"), code=307)  # Trimite același request către /rfid
    else:
        return jsonify({"error": "Tag RFID necunoscut"}), 400


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
#
#
### COD CREEARE ADMINISTRATOR
@app.route("/api/create_admin", methods=["POST"])
def create_admin():
    """Adaugă un nou administrator în baza de date cu Tag Type = 'login'"""
    data = request.get_json()
    rfid_code = data.get("rfid_code")
    user_name = data.get("user_name")

    if not rfid_code or not user_name:
        return jsonify({"error": "Lipsește RFID code sau numele utilizatorului"}), 400

    # Verificăm dacă RFID-ul există deja
    existing_tag = RFIDTags.query.filter_by(rfid_code=rfid_code).first()
    if existing_tag:
        return jsonify({"error": "Acest RFID este deja înregistrat!"}), 409

    # Creăm un nou admin cu tag_type = "login"
    new_admin = RFIDTags(rfid_code=rfid_code, tag_type="login", user_name=user_name)
    db.session.add(new_admin)
    db.session.commit()

    return jsonify({
        "message": f"Administrator {user_name} creat cu succes!",
        "rfid_code": rfid_code,
        "tag_type": "login",
        "user_name": user_name
    }), 201


##### Afisare administratori curenti
@app.route("/api/get_admins", methods=["GET"])
def get_admins():
    """Returnează toți administratorii (Tag Type = 'login')"""
    admins = RFIDTags.query.filter_by(tag_type="login").all()

    admin_list = [{"rfid_code": admin.rfid_code, "user_name": admin.user_name} for admin in admins]

    return jsonify(admin_list), 200


if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
 