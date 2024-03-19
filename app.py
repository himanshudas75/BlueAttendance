import re
import time
import sqlite3
from flask import Flask, request, render_template, redirect, url_for, jsonify
import binascii
from flask_mqtt import Mqtt, ssl
from dotenv import load_dotenv
import os

load_dotenv()
app = Flask(__name__)

THRESHOLD=0.5

app.config['MQTT_BROKER_URL'] = os.getenv('MQTT_BROKER_URL')
app.config['MQTT_BROKER_PORT'] = int(os.getenv('MQTT_BROKER_PORT'))
app.config['MQTT_USERNAME'] = os.getenv('MQTT_USERNAME')  # Set this item when you need to verify username and password
app.config['MQTT_PASSWORD'] = os.getenv('MQTT_PASSWORD')  # Set this item when you need to verify username and password
app.config['MQTT_KEEPALIVE'] = 5  # Set KeepAlive time in seconds
app.config['MQTT_TLS_ENABLED'] = True  # If your server supports TLS, set it True
app.config['MQTT_TLS_VERSION'] = ssl.PROTOCOL_TLS

recv_topic = 'blue_attendance'
send_topic = 'blue_config'

mqtt_client = Mqtt(app)

@mqtt_client.on_connect()
def handle_connect(client, userdata, flags, rc):
   if rc == 0:
       print('Connected successfully')
       mqtt_client.subscribe(recv_topic)
   else:
       print('Bad connection. Code:', rc)

# Function to insert data into SQLite database
def insert_data(address, timestamp):
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("INSERT INTO devices (address, timestamp) VALUES (?, ?)", (address, timestamp))
    conn.commit()
    conn.close()

@mqtt_client.on_message()
def handle_mqtt_message(client, userdata, message):
    hex_encoded_data = message.payload.decode()
    if hex_encoded_data:
        try:
            decoded_data = binascii.unhexlify(hex_encoded_data)
            decoded_data_str = decoded_data.decode('utf-8')
            bluetooth_addresses = re.findall(r'\+INQ:([\w:]+),', decoded_data_str)
            timestamp = int(time.time())
            for address in bluetooth_addresses:
                print(f"Bluetooth address: {address} Timestamp: {timestamp}")
                insert_data(address, timestamp)
        except (binascii.Error, UnicodeDecodeError):
            print("Invalid data received.")
    else:
        print("No data received.")

@mqtt_client.on_log()
def on_log(client, userdata, level, buf):
    print("Log: ", buf)

def create_db_tables():
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS devices
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, address TEXT, timestamp INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mappings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, address TEXT)''')
    conn.commit()
    conn.close()

# Function to insert data into mappings table
def insert_mapping(user, address):
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("INSERT INTO mappings (user, address) VALUES (?, ?)", (user, address))
    conn.commit()
    conn.close()

# Function to fetch all mappings from the mappings table
def fetch_mappings():
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("SELECT * FROM mappings")
    mappings = c.fetchall()
    conn.close()
    return mappings

# Function to update mapping in the mappings table
def update_mapping(id, user, address):
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("UPDATE mappings SET user = ?, address = ? WHERE id = ?", (user, address, id))
    conn.commit()
    conn.close()

# Function to delete mapping in the mappings table
def delete_mapping(id):
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("DELETE FROM mappings WHERE id = ?", (id,))
    conn.commit()
    conn.close()

@app.route('/mapping', methods=['GET', 'POST'])
def mapping():
    if request.method == 'GET':
        mappings = fetch_mappings()
        return render_template('mapping.html', mappings=mappings)
    elif request.method == 'POST':
        form_type = request.form['form_type']
        if form_type == 'add':
            user = request.form['user']
            address = request.form['address']
            insert_mapping(user, address)
        elif form_type == 'edit':
            id = request.form['id']
            user = request.form['user']
            address = request.form['address']
            update_mapping(id, user, address)
        elif form_type == 'delete':
            id = request.form['id']
            delete_mapping(id)
        return redirect(url_for('mapping'))
    return "Invalid request", 400

@app.route('/start')
def start():
    publish_result = mqtt_client.publish(send_topic, 'START')
    return jsonify({'code': publish_result[0]})

@app.route('/stop')
def stop():
    publish_result = mqtt_client.publish(send_topic, 'STOP')
    return jsonify({'code': publish_result[0]})

@app.route('/clear_attendance')
def clear_attendance():
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("DELETE FROM devices")
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/')
def index():
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()

    c.execute("SELECT id, user FROM mappings")
    users = c.fetchall()
    
    c.execute("SELECT COUNT(DISTINCT timestamp) FROM devices")
    total = c.fetchone()[0]

    attendance = []
    threshold = request.args.get('threshold', type=float, default=0.5)

    for id, user_name in users:
        c.execute("SELECT COUNT(DISTINCT timestamp) FROM devices WHERE address IN (SELECT address FROM mappings WHERE id = ?)", (id,))
        hits = c.fetchone()[0]
        if total > 0:
            presence = "Present" if (hits / total) > threshold else "Absent"
        else:
            presence = "N/A"
        attendance.append((user_name, hits, total, presence))

    conn.close()

    return render_template('index.html', attendance=attendance)

if __name__ == '__main__':
    create_db_tables()
    app.run(host='0.0.0.0', debug=True)
