import re
import time
from flask import Flask, request, render_template, redirect, url_for, jsonify
import binascii
from flask_mqtt import Mqtt, ssl
from dotenv import load_dotenv
import os
from flask_pymongo import PyMongo
from bson import ObjectId

load_dotenv()
app = Flask(__name__)

THRESHOLD=0.5

MONGO_URI = os.getenv('MONGO_URI')

app.config['MQTT_BROKER_URL'] = os.getenv('MQTT_BROKER_URL')
app.config['MQTT_BROKER_PORT'] = int(os.getenv('MQTT_BROKER_PORT'))
app.config['MQTT_USERNAME'] = os.getenv('MQTT_USERNAME')  # Set this item when you need to verify username and password
app.config['MQTT_PASSWORD'] = os.getenv('MQTT_PASSWORD')  # Set this item when you need to verify username and password
app.config['MQTT_KEEPALIVE'] = 5  # Set KeepAlive time in seconds
app.config['MQTT_TLS_ENABLED'] = True  # If your server supports TLS, set it True
app.config['MQTT_TLS_VERSION'] = ssl.PROTOCOL_TLS

app.config["MONGO_URI"] = MONGO_URI
mongodb_client = PyMongo(app)
db = mongodb_client.db

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
    db.attendance.insert_one({
        'address': address.strip(),
        'timestamp': timestamp
    })

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

# Function to insert data into mappings table
def insert_mapping(user, address):
    db.mappings.insert_one({
        'user': user.strip(),
        'address': address.strip()
    })

# Function to fetch all mappings from the mappings table
def fetch_mappings():
    mappings = list(db.mappings.find())
    result = list()
    for row in mappings:
        row['_id'] = str(row['_id'])
        result.append(row)
    return result

# Function to update mapping in the mappings table
def update_mapping(id, user, address):
    db.mappings.update_one({
        {'_id': ObjectId(id)},
        {
            'user': user,
            'address': address
        }
    })

# Function to delete mapping in the mappings table
def delete_mapping(id):
    db.mappings.delete_one({
        '_id': ObjectId(id)
    })

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
    result = db.attendance.delete_many({})
    if result.deleted_count > 0:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False})

@app.route('/')
def index():
    users = fetch_mappings()
    total = len(list(db.attendance.distinct("timestamp")))

    attendance = []
    threshold = request.args.get('threshold', type=float, default=0.5)

    for u in users:
        user = u['user']
        address = u['address']
        
        hits = len(list(db.attendance.distinct("timestamp", {"address": address})))

        if total > 0:
            presence = "Present" if (hits / total) > threshold else "Absent"
        else:
            presence = "N/A"
        attendance.append((user, hits, total, presence))

    return render_template('index.html', attendance=attendance)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
