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

cam = espcamera.Camera(
    data_pins=board.D,
    pixel_clock_pin=board.PCLK,
    vsync_pin=board.VSYNC,
    href_pin=board.HREF,
    i2c=board.SSCB_I2C(),
    external_clock_pin=board.XCLK,
    reset_pin=board.RESET,
    pixel_format=espcamera.PixelFormat.RGB565,
    frame_size=espcamera.FrameSize.VGA,
    grab_mode=espcamera.GrabMode.LATEST
    )

cam.reconfigure()
print("getting ready")
for x in range(5):
    bitmap = cam.take(0.5)
    print(type(bitmap))
print("cheese")
#bitmap=cam.take(1)
for x in range(5):
    bitmap=cam.take(1)
    print(type(bitmap))
    if (type(bitmap) != 'NoneType'):
        break



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
    struct.pack_into("<4sI2xI", buf, 0, b"BM", total_size, header_size)
    # 4. Write DIB Header (BITMAPINFOHEADER) - Standard 24-bit
    struct.pack_into("<IiiHHiiiiii", buf, header_size, 
                     40, width, height, 1, 24, 0, 0, 2835, 2835, 0, 0)
    # 5. Convert and Write Pixel Data (RGB565 -> RGB888)
    pixels = np.frombuffer(bitmap, dtype=np.uint16)
    
    buf_offset = header_size
    print("Pixel data printing")
    for y in range(height):
        print("working on row ",y)
        # CORRECTED: The start index in a uint16 array is simply (row * width)
        row_start_in_pixels = y * width 
        
        # The start index in the bytearray buffer
        row_start_in_buf = buf_offset + (y * bytes_per_row)
        
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

#bmpbytes = RGB565toBMP_memory_16bit(bitmap)
bmpbytes = RGB565toBMP_24bit(bitmap)


#mqtt
pool = socketpool.SocketPool(wifi.radio)

mqtt_topic = "test/topic"

#callbacks
def connect(mqtt_client, userdata, flags, rc):
    print("Connected to MQTT Broker!")
    print(f"Flags: {flags}\n RC: {rc}")
    
def publish(mqtt_client, userdata, topic, pid):
    print(f"Published to {topic} with PID {pid}")

mqtt_client = MQTT.MQTT(
    broker="192.168.16.244",
    username="esp",
    password="mqtt",
    port=1883,
    socket_pool=pool
)

mqtt_client.on_connect = connect
mqtt_client.on_publish = publish
print(f"Attempting to connect to {mqtt_client.broker}")
mqtt_client.connect()
print(f"Publishing to {mqtt_topic}")
mqtt_client.publish(mqtt_topic, bytes(bmpbytes))

#TODO enable deep sleep 