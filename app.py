import re
import time
from flask import Flask, request, render_template, redirect, url_for, jsonify
import binascii
from flask_mqtt import Mqtt, ssl
from dotenv import load_dotenv
import os
from flask_pymongo import PyMongo
from bson import ObjectId
from datetime import date, datetime
from flask_mail import Mail, Message
import pandas as pd
from io import BytesIO
from time import sleep

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

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT'))
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')

mongodb_client = PyMongo(app)
db = mongodb_client.db
mail = Mail(app)

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

def calculate_attendance(threshold):
    users = fetch_mappings()
    attendance = []
    total = len(list(db.attendance.distinct("timestamp")))

    for u in users:
        user = u['user']
        address = u['address']
        
        hits = len(list(db.attendance.distinct("timestamp", {"address": address})))

        if total > 0:
            presence = 1 if (hits / total) > threshold else 0
        else:
            presence = -1
        
        attendance.append((user, hits, total, presence))
    
    attendance.sort()

    return attendance

def send_email(attendance, course, date, recipient):
    try:
        subject=f"Attendance {course} {date}"

        new_attendance = list()
        for x in attendance:
            if x[1] == 1:
                second_term = 'Present'
            elif x[1] == 0:
                second_term = 'Absent'
            else:
                second_term = 'N/A'
            new_attendance.append((x[0], second_term))

        msg = Message(subject=subject, sender=MAIL_USERNAME, recipients=[recipient])
        msg.body = f"""Please find attached the attendance report for {course} class conducted on {date}.\nShould you need any clarification or assistance, please feel free to reach out to us."""
        df = pd.DataFrame(new_attendance, columns=['User', 'Presence'])

        excel_buffer = BytesIO()
        df.to_excel(excel_buffer, index=False)

        excel_buffer.seek(0)

        msg.attach("attendance_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", excel_buffer.read())
        
        excel_buffer.close()

        mail.send(msg)
        sleep(1)

        return 0
    except Exception as e:
        print(e)
        return 1

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
    publish_result = mqtt_client.publish(send_topic, 'START', qos = 2)
    return jsonify({'code': publish_result[0]})

@app.route('/stop')
def stop():
    publish_result = mqtt_client.publish(send_topic, 'STOP', qos = 2)
    return jsonify({'code': publish_result[0]})

@app.route('/clear_attendance')
def clear_attendance():
    result = db.attendance.delete_many({})
    if result.deleted_count > 0:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False})

@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    course = request.form['course']
    date_of_attendance = request.form['date']
    threshold = float(request.form['threshold'])
    recipient = request.form['recipient']

    attendance = calculate_attendance(threshold)
    attendance = [(x[0], x[-1]) for x in attendance if x[-1] >= 0]
    attendance_dict = dict()
    for x in attendance:
        attendance_dict[x[0]] = x[1]
    
    date_of_attendance = datetime.strptime(date_of_attendance, '%Y-%m-%d')

    existing_row = db.course_attendance.find_one({'course_code': course})

    if existing_row:
        existing_row['attendance_by_date'].append({
            'date': date_of_attendance,
            'students': attendance
        })
        
        for x in attendance:
            if x[0] in existing_row['attendance'].keys():
                existing_row['attendance'][x[0]] += x[1]
            else:
                existing_row['attendance'][x[0]] = x[1]
        
        existing_row['classes'] += 1

        db.course_attendance.update_one(
            {'course_code': course},
            {'$set': existing_row}
        )
    else:
        final_row = {
            'course_code': course,
            'attendance_by_date': [
                {
                    'date': date_of_attendance,
                    'students': attendance_dict
                }
            ],
            'attendance': attendance_dict,
            'classes': 1
        }
        db.course_attendance.insert_one(final_row)

    send_email(attendance, course, date_of_attendance, recipient)

    return redirect('/')

@app.route('/attendance', methods=['GET'])
def attendance():
    attendance_by = request.args.get('attendance_by', type=str, default='NULL')
    filter = request.args.get('filter', type=str, default='NULL')
    options = list()
    if attendance_by == 'course':
        options = db.course_attendance.distinct('course_code')
    elif attendance_by == 'student':
        options = db.mappings.distinct('user')
    
    final_attendance = list()

    if attendance_by != 'NULL' and filter != 'NULL':
        if attendance_by == 'student':
            courses = list(db.course_attendance.find({}))
            for course in courses:
                attendance = course['attendance']
                if filter in attendance.keys():
                    course_name = course['course_code']
                    present = attendance[filter]
                    classes = course['classes']
                    absent = classes - present
                    percent = (present * 100)//classes
                    final_attendance.append((course_name, present, absent, classes, percent))
        elif attendance_by == 'course':
            course = db.course_attendance.find_one({'course_code': filter})
            attendance = course['attendance']
            classes = course['classes']
            for student in attendance:
                present = attendance[student]
                absent = classes - present
                percent = (present * 100)//classes
                final_attendance.append((student, present, absent, classes, percent))

    final_attendance.sort()
    return render_template('attendance.html', attendance_by=attendance_by, filter=filter, options=options, attendance=final_attendance)

@app.route('/')
def index():
    threshold = request.args.get('threshold', type=float, default=0.5)
    attendance = calculate_attendance(threshold)
    current_date = date.today().isoformat()

    return render_template('index.html', current_date=current_date, attendance=attendance)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
