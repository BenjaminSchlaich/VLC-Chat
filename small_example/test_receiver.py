
import time
import sys
import serial


PORT = "/dev/cu.usbmodem14101"
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
   byte = s.read(1) #read one byte (blocks until data available or timeout reached)  
   val = chr(byte[0])  
   if val=='\n': #if termination character reached  
     print (message) #print message  
     message = "" #reset message  
   else:  
     message = message + val #concatenate the message  
 except serial.SerialException:  
   continue #on timeout try to read again  
 except KeyboardInterrupt:  
   sys.exit() #on ctrl-c terminate program
