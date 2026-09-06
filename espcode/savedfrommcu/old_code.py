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

#setting up the battery methods
def get_batt(bat):
    return (bat.value * 3) / 65535 #lets see which cell i use in the end

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
    pixel_format=espcamera.PixelFormat.RGB565,
    frame_size=espcamera.FrameSize.R96X96,
    grab_mode=espcamera.GrabMode.LATEST
    )
cam.reconfigure()

#debug
#throwing away bad frames and running the first frames
# print("getting ready")
# for x in range(5):
#     bitmap = cam.take(0.5)
#     print(type(bitmap))
# print("cheese")
# #bitmap=cam.take(1)
# for x in range(5):
#     bitmap=cam.take(1)
#     print(type(bitmap))
#     if (type(bitmap) != 'None'):
#         break

#Gemma generated YUYV422 conversion:
def YUYVtoBMP_24bit(bitmap):
    width = bitmap.width
    height = bitmap.height
    raw = np.frombuffer(bitmap, dtype=np.uint8)
    print("size difference between buffer and raw",raw.size, width*height*2)
    header_size = 54
    pixel_bytes_per_row = width * 3
    padding_bytes = (4 - (pixel_bytes_per_row % 4)) % 4
    bytes_per_row = pixel_bytes_per_row + padding_bytes
    total_size = header_size + (height * bytes_per_row)

    try:
        buf = bytearray(total_size)
    except MemoryError:
        print("Memory Error: Image too large for available RAM")
        return None

    struct.pack_into("<2sIHHI", buf, 0, b"BM", total_size, 0, 0, header_size)
    struct.pack_into("<IiiHHiiiiii", buf, header_size,
                      40, width, height, 1, 24, 0, 0, 2835, 2835, 0, 0)

    raw = np.frombuffer(bitmap, dtype=np.uint8)  # length = width*height*2

    # Split out Y0,U,Y1,V groups (4 bytes -> 2 pixels)
    Y0 = raw[0::4]
    U  = raw[1::4]
    Y1 = raw[2::4]
    V  = raw[3::4]

    n_pairs = width * height // 2
    Yfull = np.zeros(width * height, dtype=np.uint8)
    Ufull = np.zeros(width * height, dtype=np.uint8)
    Vfull = np.zeros(width * height, dtype=np.uint8)

    Yfull[0::2] = Y0
    Yfull[1::2] = Y1
    Ufull[0::2] = U
    Ufull[1::2] = U
    Vfull[0::2] = V
    Vfull[1::2] = V

    # BT.601, do the math in float to avoid ulab's int16 overflow
    Cf = Yfull - 16.0
    Df = Ufull - 128.0
    Ef = Vfull - 128.0

    R = (298.0 * Cf + 409.0 * Ef) / 256.0
    G = (298.0 * Cf - 100.0 * Df - 208.0 * Ef) / 256.0
    B = (298.0 * Cf + 516.0 * Df) / 256.0

    # clip to 0-255 (use np.clip if your ulab build has it; else this manual version always works)
    R = R * (R > 0)
    G = G * (G > 0)
    B = B * (B > 0)
    R = R - (R - 255) * (R > 255)
    G = G - (G - 255) * (G > 255)
    B = B - (B - 255) * (B > 255)

    R8 = np.array(R,dtype=np.uint8)
    G8 = np.array(G,dtype=np.uint8)
    B8 = np.array(B,dtype=np.uint8)

    for y in range(height):
        row_off = header_size + y * bytes_per_row
        row_start = y * width
        for x in range(width):
            idx = row_off + x * 3
            buf[idx]     = int(B8[row_start + x])
            buf[idx + 1] = int(G8[row_start + x])
            buf[idx + 2] = int(R8[row_start + x])

    del raw, Yfull, Ufull, Vfull, Cf, Df, Ef, R, G, B, R8, G8, B8
    gc.collect()
    print("buffer length:",len(buf), "expected length", total_size) 
    return buf
#Gemma generated RGB565 conversion function
def RGB565toBMP_memory_16bit(bitmap):
    """
    Transforms an RGB565 array to a BMP byte buffer using a list of chunks.
    This is often more 'stable' on fragmented memory than large pre-allocation.
    """
    # 1. Calculate Dimensions (Strictly for 16-bit / 2 bytes per pixel)
    width = bitmap.width
    height = bitmap.height
    pixel_bytes_per_row = width * 2
    padding_bytes = (4 - (pixel_bytes_per_row % 4)) % 4
    bytes_per_row = pixel_bytes_per_row + padding_bytes
    # Header size for a standard BI_RGB header is 54 bytes
    header_size = 54
    filesize = header_size + (height * bytes_per_row)
    # 2. Build the Header as a single bytes object
    header = bytearray()
    # File Header
    header.extend(b"BM")                          # Signature
    header.extend(struct.pack("<I", filesize))     # Filesize
    header.extend(b"\x00\x00\x00\x00")             # Reserved
    header.extend(struct.pack("<I", header_size))  # Offset
    # DIB Header (BITMAPINFOHEADER)
    header.extend(struct.pack("<I", 40))           # Header size
    header.extend(struct.pack("<I", width))        # Width
    header.extend(struct.pack("<I", height))       # Height
    header.extend(struct.pack("<H", 1))            # Planes
    header.extend(struct.pack("<H", 16))           # Bits per pixel (16)
    header.extend(struct.pack("<I", 0))            # Compression (0 = BI_RGB)
    header.extend(struct.pack("<I", 0))            # Image size
    header.extend(struct.pack("<i", 2835))         # X pixels per meter
    header.extend(struct.pack("<i", 2835))         # Y pixels per meter
    header.extend(struct.pack("<I", 0))            # Color used
    header.extend(struct.pack("<I", 0))            # Important colors
    # 3. Build the Pixel Data using a list of rows (to avoid large contiguous allocation)
    pixel_chunks = []
    
    # Get a view of your numpy array
    pixels = np.frombuffer(bitmap, dtype=np.uint16)
    pixels.byteswap(inplace=True) #Doing this to solve the endianness bullshit
    for y in range(height):
        start = y * width * 2
        end = start + (width * 2)
        
        # Extract the row and convert to bytes
        row_data = pixels[start:end].tobytes()
        pixel_chunks.append(row_data)
        
        # Add padding for this specific row if necessary
        if padding_bytes > 0:
            pixel_chunks.append(b"\x00" * padding_bytes)
    # 4. Join everything together at the very end
    # We use b"".join() because we are joining bytes, not strings!
    return header + b"".join(pixel_chunks)

#Gemma generated RGB565 with 24 bit bitmap handling to try and solve that colour banding
def RGB565toBMP_24bit(bitmap):
    """
    Transforms an RGB565 array into a standard 24-bit BMP.
    Fixed: Corrected indexing logic for uint16 source array.
    """
    width = bitmap.width
    height = bitmap.height
    print("Dimension calc")
    # 1. Calculate Dimensions (3 bytes per pixel for 24-bit)
    pixel_bytes_per_row = width * 3
    padding_bytes = (4 - (pixel_bytes_per_row % 4)) % 4
    bytes_per_row = pixel_bytes_per_row + padding_bytes
    header_size = 54 
    total_size = header_size + (height * bytes_per_row)
    # 2. Pre-allocate the buffer
    print("Buffer Prealloc")
    try:
        buf = bytearray(total_size)
    except MemoryError:
        print("Memory Error: Image too large for available RAM")
        return None
    # 3. Write File Header (BITMAPFILEHEADER)
    print("Header setup")
    struct.pack_into("<2sIHHI", buf, 0, b"BM", total_size, 0, 0, header_size)
    # 4. Write DIB Header (BITMAPINFOHEADER) - Standard 24-bit
    struct.pack_into("<IiiHHiiiiii", buf, header_size, 
                     40, width, height, 1, 24, 0, 0, 2835, 2835, 0, 0)
    # 5. Convert and Write Pixel Data (RGB565 -> RGB888)
    pixels = np.frombuffer(bitmap, dtype=np.uint.u16).byteswap()
    
    buf_offset = header_size
    print("Pixel data printing")
    for y in range(height):
        print("working on row ",y)
        # CORRECTED: The start index in a uint16 array is simply (row * width)
        row_start_in_pixels = y * width 
        
        # The start index in the bytearray buffer
        row_start_in_buf = buf_offset + ((height - 1 - y) * bytes_per_row)
        
        for x in range(width):
            # Get the single uint16 pixel
            p = pixels[row_start_in_pixels + x]
            
            # Extract R, G, B components from RGB565
            r_5bit = (p >> 11) & 0x1F
            g_6bit = (p >> 5) & 0x3F
            b_5bit = p & 0x1F
            # Scale to 8-bit (0-255)
            r_8bit = (r_5bit * 255) // 31
            g_8bit = (g_6bit * 255) // 63
            b_8bit = (b_5bit * 255) // 31
            # Write to buffer in BGR order (BMP standard)
            idx = row_start_in_buf + (x * 3)
            buf[idx]     = b_8bit  # Blue
            buf[idx + 1] = g_8bit  # Green
            buf[idx + 2] = r_8bit  # Red
    # Clean up to free RAM for MQTT/Base64 steps
    print("done")
    del pixels
    gc.collect()
    
    return buf

#DEBUG FOR RUNNING WITHOUT SLEEP
#bmpbytes = RGB565toBMP_memory_16bit(bitmap)
#bmpbytes = RGB565toBMP_24bit(bitmap)


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

#DEBUG:
#print(f"Attempting to connect to {mqtt_client.broker}")
#mqtt_client.connect()
#print(f"Publishing to {mqtt_topic}")
#mqtt_client.publish(mqtt_topic, bytes(bmpbytes))


#actual program functions
def onwake():
    print(wifi.radio.connected)
    while (wifi.radio.connected == False):
        time.sleep(1)
    mqtt_client.connect()
    print("waiting for interruption...")
    time.sleep(5)
    mqtt_client.publish(sys_topic,"ESP working and connected")
    mqtt_client.publish(batt_topic,get_batt(batADC))
    normal_alarm = alarm.time.TimeAlarm(monotonic_time = time.monotonic() + 30) #redefining it here to get the freshest time
    #alarm.exit_and_deep_sleep_until_alarms(normal_alarm)
    alarm.exit_and_deep_sleep_until_alarms(normal_alarm)

def onPIR():
    for x in range(2):
        bitmap = cam.take(0.5) #throwing away the first two
    led.value = True #turning on the LED
    for x in range(5): #attempting to take the picture
        bitmap=cam.take(1)
        if (type(bitmap) != 'None'):
            break
    led.value = False #turning off the LED
    bmpbytes = RGB565toBMP_24bit(bitmap)
    while (wifi.radio.connected == False):
        time.sleep(1)
    mqtt_client.connect()
    mqtt_client.publish(photo_topic, bytes(bmpbytes))
    mqtt_client.publish(batt_topic,get_batt(batADC))
    normal_alarm = alarm.time.TimeAlarm(monotonic_time = time.monotonic() + 300)
    alarm.exit_and_deep_sleep_until_alarms(normal_alarm) #not redefining the time because 24h might not have passed
    #alarm.exit_and_deep_sleep_until_alarms(normal_alarm)
#handling wake
    
def testcamera():
    for x in range(2):
        bitmap = cam.take(0.5) #throwing away the first two
    led.value = True #turning on the LED
    for x in range(5): #attempting to take the picture
        bitmap=cam.take(1)
        if (type(bitmap) != 'None'):
            break
    led.value = False #turning off the LED
    print("converting")
    bmpbytes = YUYVtoBMP_24bit(bitmap)
    while (wifi.radio.connected == False):
        time.sleep(1)
    mqtt_client.connect()
    mqtt_client.publish(photo_topic, bytes(bmpbytes))
    mqtt_client.publish(batt_topic,get_batt(batADC))
    onwake()
    #normal_alarm = alarm.time.TimeAlarm(monotonic_time = time.monotonic() + 60)
    #alarm.exit_and_deep_sleep_until_alarms(normal_alarm)
if isinstance(alarm.wake_alarm, alarm.pin.PinAlarm):
    onPIR()
elif isinstance(alarm.wake_alarm, alarm.time.TimeAlarm):
    onwake()
else:
    print("Hello!! Reached the end of my program at init. Starting onwake now...")
    testcamera()

