"""Optional bridge from a Linux SocketCAN interface to the cockpit API.

Demo frame contract (not a BMW DBC):
  0x100: uint16 little-endian speed in 0.1 km/h
  0x101: uint8 gear (0=P, 1=R)
  0x102: uint8 driver door (0=closed, 1=open)
"""

import json
import socket
import struct
import sys
from urllib.request import Request, urlopen

API = "http://127.0.0.1:8765/api/events"
FRAME = struct.Struct("=IB3x8s")


def decode(frame: bytes):
    can_id, length, data = FRAME.unpack(frame)
    can_id &= 0x1FFFFFFF
    if can_id == 0x100 and length >= 2:
        return "speed_set", int.from_bytes(data[:2], "little") // 10
    if can_id == 0x101 and length >= 1:
        return ("gear_set", "R" if data[0] == 1 else "P") if data[0] in (0, 1) else None
    if can_id == 0x102 and length >= 1:
        return ("door_set", bool(data[0])) if data[0] in (0, 1) else None
    return None


def send(event: str, value=None):
    body = json.dumps({"event": event, "value": value}).encode()
    request = Request(API, body, {"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=2) as response:
        return json.load(response)


def main():
    interface = sys.argv[1] if len(sys.argv) > 1 else "vcan0"
    can = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    can.bind((interface,))
    print(f"Reading demo CAN frames from {interface}", flush=True)
    while True:
        decoded = decode(can.recv(FRAME.size))
        if decoded:
            event, value = decoded
            print(event, value, flush=True)
            send(event, value)


if __name__ == "__main__":
    main()
