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

pir_alarm = alarm.pin.PinAlarm(microcontroller.pin.GPIO4, value=True)
normal_alarm = alarm.time.TimeAlarm(monotonic_time = time.monotonic() + 86400)

if isinstance(alarm.wake_alarm, alarm.pin.PinAlarm):
    print("PIR sleep working!")

print("hello!")
print("waiting for interruption...")
time.sleep(5)
print("going to sleep!")
alarm.exit_and_deep_sleep_until_alarms(pir_alarm)