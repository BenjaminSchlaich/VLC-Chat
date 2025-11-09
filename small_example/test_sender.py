
import time

import serial


PORT = "/dev/cu.usbmodem14201"
BAUDRATE = 115200
TIMEOUT = None  # blocking mode


print(f"Opening serial port {PORT} @ {BAUDRATE} baud...")
s = serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT)
time.sleep(2)  # give the device some time to startup (2 seconds)

# Write to the device's serial port
s.write(str.encode("a[AB]\n"))  # set the device address to AB
time.sleep(0.1)  # wait for settings to be applied
s.write(str.encode("c[1,0,5]\n"))  # set number of retransmissions to 5
time.sleep(0.1)  # wait for settings to be applied
s.write(str.encode("c[2,0,7]\n"))  # set FEC threshold to 30 (payload >= 30)
time.sleep(0.1)  # wait for settings to be appliedstr.encode("a[AB]\n")


s.write(str.encode("m[hello world!\0,CD]\n"))  # send message to device with address CD
