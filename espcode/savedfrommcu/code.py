import adafruit_minimqtt.adafruit_minimqtt as MQTT
import board
import espcamera
import binascii
import struct
import gc
import io
import ulab.numpy as np
import socketpool
import wifi
import alarm
import digitalio
import time
import microcontroller
from analogio import AnalogIn

#setting up ins and outs
#pir = digitalio.DigitalInOut(board.SDA)
led = digitalio.DigitalInOut(board.SCL)
led.direction = digitalio.Direction.OUTPUT
batADC = AnalogIn(board.BAT_ADC)
boardled = digitalio.DigitalInOut(board.LED)
boardled.direction = digitalio.Direction.OUTPUT
boardled.value = True

#setting up the battery methods
def get_batt(bat):
    return (3.3*bat.value/65535) #lets see which cell i use in the end, normally 3.7V

#setting up alarms
pir_alarm = alarm.pin.PinAlarm(microcontroller.pin.GPIO4, value=True)
normal_alarm = alarm.time.TimeAlarm(monotonic_time = time.monotonic() + 86400)

#setting up the camera
cam = espcamera.Camera(
    data_pins=board.D,
    pixel_clock_pin=board.PCLK,
    vsync_pin=board.VSYNC,
    href_pin=board.HREF,
    i2c=board.SSCB_I2C(),
    external_clock_pin=board.XCLK,
    reset_pin=board.RESET,
    pixel_format=espcamera.PixelFormat.GRAYSCALE,
    frame_size=espcamera.FrameSize.VGA,
    grab_mode=espcamera.GrabMode.LATEST
    )
cam.reconfigure()

#bitmap 
def bitmap_to_bmp_bytes(bitmap):
    width = bitmap.width
    height = bitmap.height
    row_size = (width + 3) & ~3 
    pixel_data_size = row_size * height #raw "size"

    palette_size = 256 * 4 #three for R, G and B and another one for stuff we dont care about
    dib_header_size = 40 #NT convention size thats the shortest for modern compat
    file_header_size = 14
    pixel_data_offset = file_header_size + dib_header_size + palette_size
    file_size = pixel_data_offset + pixel_data_size #total real size for the file

    buf = bytearray(file_size) #inits an array the size of the whole
    pos = 0

    def write(data):
        nonlocal pos #avoids getting pos overwritten by lower level context (with callers)
        buf[pos:pos + len(data)] = data
        pos += len(data)
    #I is unsigned int, H is unsigned short, i is signed int, < is little endian
    #following descriptions come from wikipedia
    write(b"BM") #NT format bitmap
    write(struct.pack("<I", file_size))
    write(struct.pack("<HH", 0, 0)) #dont care
    write(struct.pack("<I", pixel_data_offset)) #offset til image data
    write(struct.pack("<I", dib_header_size))
    write(struct.pack("<i", width))
    write(struct.pack("<i", height))
    write(struct.pack("<H", 1)) #one color plane
    write(struct.pack("<H", 8)) #8bpp 
    write(struct.pack("<I", 0)) #no compression
    write(struct.pack("<I", pixel_data_size)) #size of raw file
    write(struct.pack("<i", 2835)) #basic 72DPI info
    write(struct.pack("<i", 2835)) #idem
    write(struct.pack("<I", 256)) #256 "colour" palette
    write(struct.pack("<I", 256)) #all colors are important but could also be zero
    
    entry = bytearray(4)
    for i in range(256): #palette data
        entry[0] = entry[1] = entry[2] = i #everything the same because of grayscale
        entry[3] = 0 #we dont care about this
        write(entry)

    #fills up bottom up per every scanline
    row_buf = bytearray(row_size) 
    for y in range(height - 1, -1, -1):
        for x in range(width):
            row_buf[x] = bitmap[x, y] & 0xFF #and hex FF for capping to 8b
        write(row_buf)

    return buf

#mqtt
pool = socketpool.SocketPool(wifi.radio)

photo_topic = "gallery/images"
sys_topic = "esp/system"
batt_topic = "esp/battery"

#callbacks
def connect(mqtt_client, userdata, flags, rc):
    print("Connected to MQTT Broker!")
    print(f"Flags: {flags}\n RC: {rc}")
    
def publish(mqtt_client, userdata, topic, pid):
    print(f"Published to {topic} with PID {pid}")

mqtt_client = MQTT.MQTT(
    broker="192.168.64.1",
    username="esp",
    password="microcontroller",
    port=1883,
    socket_pool=pool
)


mqtt_client.on_connect = connect
mqtt_client.on_publish = publish


#actual program functions
def onwake():
    print(wifi.radio.connected)
    while (wifi.radio.connected == False):
        time.sleep(1)
        i = i+1
        boardled.value = not boardled.value
        if (i == 50): #timeout réseau
            networkalarm = alarm.time.TimeAlarm(monotonic_time = time.monotonic() + 3600)
            alarm.exit_and_deep_sleep_until_alarms(networkalarm)
    try:
        mqtt_client.connect()
    except (ValueError, RuntimeError,MQTT.MMQTTException) as ex:
        boardled.value = not boardled.value
        time.sleep(1)
        boardled.value = not boardled.value
        mqtt_client.reconnect()
    print("waiting for interruption...")
    time.sleep(5)
    mqtt_client.publish(sys_topic,"ESP working and connected")
    mqtt_client.publish(batt_topic,get_batt(batADC))
    cam.deinit()
    normal_alarm = alarm.time.TimeAlarm(monotonic_time = time.monotonic() + 86400) #redefining it here to get the freshest time
    alarm.exit_and_deep_sleep_until_alarms(normal_alarm,pir_alarm)

    
def onPIR():
    for x in range(2):
        bitmap = cam.take(0.5) #throwing away the first two
    led.value = True #turning on the LED
    for x in range(5): #attempting to take the picture
        bitmap=cam.take(1)
        if (type(bitmap) != 'None'):
            break
    led.value = False #turning off the LED
    print("converting")
    bmpbytes = bitmap_to_bmp_bytes(bitmap)
    i = 0
    while (wifi.radio.connected == False):
        time.sleep(1)
        i = i+1
        boardled.value = not boardled.value
        if (i == 50): #timeout réseau
            networkalarm = alarm.time.TimeAlarm(monotonic_time = time.monotonic() + 3600)
            alarm.exit_and_deep_sleep_until_alarms(networkalarm)
    try:
        mqtt_client.connect()
    except (ValueError, RuntimeError,MQTT.MMQTTException) as ex:
        boardled.value = not boardled.value
        time.sleep(1)
        boardled.value = not boardled.value
        mqtt_client.reconnect()
    mqtt_client.publish(photo_topic, bytes(bmpbytes))
    mqtt_client.publish(batt_topic,get_batt(batADC))
    cam.deinit()
    normal_alarm = alarm.time.TimeAlarm(monotonic_time = time.monotonic() + 300) #sleeping for 5 minutes
    alarm.exit_and_deep_sleep_until_alarms(normal_alarm)
if isinstance(alarm.wake_alarm, alarm.pin.PinAlarm):
    onPIR()
elif isinstance(alarm.wake_alarm, alarm.time.TimeAlarm):
    onwake()
else:
    print("Hello!! Reached the end of my program at init.")
    print("waiting for interruption...")
    time.sleep(5)
    print("Deiniting the camera")
    cam.deinit()
    print("Goodnight!")
    alarm.exit_and_deep_sleep_until_alarms(pir_alarm, normal_alarm)
    #testcamera()
