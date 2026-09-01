import os
import threading
import paho.mqtt.client as mqtt
from flask import Flask, render_template
from database import db, ImageEntry #imports the data

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gallery.db'
app.config['UPLOAD_FOLDER'] = 'static/images/'
db.init_app(app)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

#MQTT 
def on_message(client, userdata, msg): #channel message handler
    try:
        if msg.topic == "gallery/images":
            filename = f"img_{msg.timestamp}_{msg.topic.replace('/', '_')}.jpg"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, "wb") as f:
                f.write(msg.payload)
            new_image = ImageEntry(filename=filename) #db entry,just the name (calls into database)
            with app.app_context():
                db.session.add(new_image)
                db.session.commit()
            print(f"Saved: {filename}")
        elif msg.topic == "esp/battery":
            payload_str = msg.payload.decode('utf-8') # Convert bytes to string
            battery_level = float(payload_str)       # Convert string to float
            
            with app.app_context():
                new_battery = BatteryStatus(level=battery_level)
                db.session.add(new_battery)
                db.session.commit()
            print(f"Battery updated: {battery_level}%")
    except Exception as e: #error handling
        print(f"Error saving image: {e}")

def start_mqtt(): #fires at start
    client = mqtt.Client()
    client.username_pw_set("pi","raspberry")
    client.on_message = on_message #defines handler
    client.connect("192.168.64.1", 1883, 60)
    client.subscribe("gallery/images")
    client.loop_forever()

#Web
@app.route('/')
def index():
    latest_battery = BatteryStatus.query.order_by(BatteryStatus.timestamp.desc()).first()
    images = ImageEntry.query.order_by(ImageEntry.timestamp.desc()).all() #looks for all images in the db
    return render_template('index.html', images=images, battery=latest_battery)

if __name__ == '__main__': 
    with app.app_context():
        db.create_all() #creates the tables

    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True) #nonblocking mqtt listener
    mqtt_thread.start()

    app.run(host='192.168.64.1', port=8080) #starts serving

@app.route('/clear-all', methods=['POST'])
def clear_all():
    folder = app.config['UPLOAD_FOLDER'] 
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path) #removes all images
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
    with app.app_context(): #removes the entries
        ImageEntry.query.delete()
        BatteryStatus.query.delete()
        db.session.commit()
            
    return redirect(url_for('index'))