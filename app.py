from flask import Flask, jsonify, request, send_from_directory, render_template
from flask_cors import CORS
import os
import psutil
from datetime import datetime
import serial
import time
import sqlite3
import threading

from usb_connection import usb_bp, start_usb_scanner

app = Flask(__name__, static_folder='static', static_url_path='/static', template_folder='templates')
CORS(app)

# Register USB camera blueprint
app.register_blueprint(usb_bp)

# Configuration
UPLOAD_FOLDER = 'uploads'
SERIAL_PORT = '/dev/ttyUSB1'  # Change to /dev/ttyUSB0 if USB1 fails
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('flood_project.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sms_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            phone_number TEXT,
            message TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

# --- 2. SMS LISTENER (Background Thread) ---
def sms_listener():
    print(f"Checking GSM Module on {SERIAL_PORT}...")
    try:
        # timeout=1 prevents the "infinite loading" issue
        ser = serial.Serial(SERIAL_PORT, 9600, timeout=1)
        ser.write(b'AT+CMGF=1\r') 
        time.sleep(1)
        print("GSM Listener Thread Started successfully.")
        
        while True:
            if ser.in_waiting > 0:
                incoming = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                print(f"Received: {incoming}")
                
                if "FLOOD" in incoming.upper():
                    conn = sqlite3.connect('flood_project.db')
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO sms_history (phone_number, message, status) VALUES (?, ?, ?)",
                        ("Remote Sender", incoming.strip(), "Critical")
                    )
                    conn.commit()
                    conn.close()
                    print("DATABASE UPDATED WITH NEW ALERT!")
            time.sleep(2)
    except Exception as e:
        print(f"SMS Thread Error (GSM not found or busy): {e}")

# --- 3. FLASK ROUTES ---

@app.route('/')
def index():
    # Looks for Dashboard.html in the 'templates' folder
    return render_template('Dashboard.html')

@app.route('/monitoring')
def monitoring():
    return render_template('Monitoring.html')

@app.route('/history')
def history():
    return render_template('History.html')

@app.route('/system')
def system():
    return render_template('System.html')

@app.route('/settings')
def settings():
    return render_template('Settings.html')

@app.route('/dashboard')
def dashboard():
    return render_template('Dashboard.html')

@app.route('/api/flood-status', methods=['GET'])
def get_status():
    cpu_usage = psutil.cpu_percent(interval=None)
    return jsonify({
        "location": "San Juan River",
        "status": "Normal",
        "confidence": "92%",
        "timestamp": datetime.now().strftime("%I:%M %p"),
        "cpu": f"{cpu_usage}%",
        "system_status": "Online"
    })

@app.route('/get_sms_history')
def get_sms_history():
    try:
        conn = sqlite3.connect('flood_project.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, phone_number, message, status FROM sms_history ORDER BY id DESC LIMIT 10")
        rows = cursor.fetchall()
        conn.close()
        return jsonify({"history": [dict(row) for row in rows]})
    except Exception as e:
        return jsonify({"history": [], "error": str(e)})

@app.route('/api/upload', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({"result": "No image", "confidence": "0%"})
    file = request.files['image']
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    return jsonify({"result": "Analysis Complete", "confidence": "95%", "status": "Success"})

@app.route('/send_manual_sms', methods=['POST'])
def send_manual_sms():
    try:
        ser = serial.Serial(SERIAL_PORT, 9600, timeout=1)
        ser.write(b'AT+CMGF=1\r')
        time.sleep(1)
        ser.write(b'AT+CMGS="+639763622520"\r')
        time.sleep(1)
        ser.write(b'Manual Alert: San Juan River level is rising!\x1a')
        ser.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# --- 4. START EVERYTHING ---
if __name__ == '__main__':
    init_db()
    
    # Start SMS listener in background
    thread = threading.Thread(target=sms_listener, daemon=True)
    thread.start()
    
    # Start USB camera scanner
    start_usb_scanner()
    
    # Run server
    print("Dashboard starting at http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)