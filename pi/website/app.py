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
        filename = f"img_{msg.timestamp}_{msg.topic.replace('/', '_')}.jpg"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        # 2. Save the raw binary payload as an image file
        with open(filepath, "wb") as f:
            f.write(msg.payload)
        new_image = ImageEntry(filename=filename) #db entry,just the name (calls into database)
        with app.app_context():
            db.session.add(new_image)
            db.session.commit()
        print(f"Saved: {filename}")
    except Exception as e: #error handling
        print(f"Error saving image: {e}")

def start_mqtt(): #fires at start
    client = mqtt.Client()
    client.on_message = on_message #defines handler
    client.connect("localhost", 1883, 60)
    client.subscribe("gallery/images")
    client.loop_forever()

#Web
@app.route('/')
def index():
    images = ImageEntry.query.order_by(ImageEntry.timestamp.desc()).all() #looks for all images in the db
    return render_template('index.html', images=images)

if __name__ == '__main__': 
    with app.app_context():
        db.create_all() #creates the tables

    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True) #nonblocking mqtt listener
    mqtt_thread.start()

    app.run(host='0.0.0.0', port=8080) #starts serving
