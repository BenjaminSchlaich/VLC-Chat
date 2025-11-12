
import time
import sys
import serial


PORT = "/dev/cu.usbmodem14201"
BAUDRATE = 115200
TIMEOUT = None  # blocking mode


print(f"Opening serial port {PORT} @ {BAUDRATE} baud...")
s = serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT)
time.sleep(2)  # give the device some time to startup (2 seconds)

s.write(str.encode("a[CD]\n"))

#read from the device’s serial port (should be done in a separate program):  
message = ""  
while True: #while not terminated  
  try:  
    line_bytes = s.readline()
    # line = line_bytes.decode("utf-8", errors="ignore")
    # print(line)
  except serial.SerialException:  
    continue #on timeout try to read again  
  except KeyboardInterrupt:  
    sys.exit() #on ctrl-c terminate program
  except Exception:
    print("Illegal input")
