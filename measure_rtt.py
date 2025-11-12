

import csv
import time
import serial


PORT = "/dev/cu.usbmodem14101"
BAUDRATE = 115200
TIMEOUT = 2  # blocking mode


print(f"Opening serial port {PORT} @ {BAUDRATE} baud...")
s = serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT)
time.sleep(2)  # give the device some time to startup (2 seconds)

# Write to the device's serial port
s.write(str.encode("a[AB]\n"))  # set the device address to AB
time.sleep(0.1)  # wait for settings to be applied
s.write(str.encode("c[1,0,5]\n"))  # set number of retransmissions to 5
time.sleep(0.1)  # wait for settings to be applied
s.write(str.encode("c[2,0,7]\n"))  # set logging level
time.sleep(0.1)  # wait for settings to be appliedstr.encode("a[AB]\n")
s.write(str.encode("c[0,2,5]\n"))  # set channel busy threshold
time.sleep(0.1)  # wait for settings to be appliedstr.encode("a[AB]\n")
s.write(str.encode("c[0,1,1]\n"))  # set forward error correction
time.sleep(0.1)  # wait for settings to be appliedstr.encode("a[AB]\n")

##############################################################################

# INSERT MEASUREMENT CODE HERE
DEST_ADDR = "CD"
MESSAGE_SIZES = [1, 100, 180]
NUM_MEASUREMENTS = 20

def read_line():
    buffer = ""
    while True:
        byte = s.read(1)
        if not byte:
            continue
        char = byte.decode("utf-8", errors="ignore")
        if char == "\n":
            return buffer
        buffer += char

# pending = []

for size in MESSAGE_SIZES:
    rtts = []
    message = "X" * size
    print(f"Measuring RTT for payload size {size} bytes...")
    for i in range(NUM_MEASUREMENTS):
        payload = f"m[{message}\0,{DEST_ADDR}]"
        send_time = time.perf_counter()
        s.write(str.encode(payload + "\n"))
        # pending.append(send_time)

        while True:
            line_bytes = s.readline()
            recv_time = time.perf_counter()
            if not line_bytes:
                print("Timeout for ack %d" % i)
                break
            try:
                line = line_bytes.decode("utf-8", errors="ignore")
                if line.startswith("s[R,A"):
                    # if pending:
                        # send_time = pending.pop(0)
                        rtts.append(recv_time - send_time)
                        break
            except Exception:
                print("illegal input received for ack %d" % i)
            

    print(f"Measured RTTs for size {size}: {rtts[-NUM_MEASUREMENTS:]}")
    filename = f"rtt_{size}.csv"
    with open(filename, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["measurement_index", "rtt_seconds"])
        for idx, rtt in enumerate(rtts):
            writer.writerow([idx, rtt])
    print(f"Wrote {len(rtts)} measurements to {filename}")
