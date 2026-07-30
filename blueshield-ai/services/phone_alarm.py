"""
services/phone_alarm.py

Sends a UDP broadcast on the local network so any listening phone/app
(e.g. a small receiver app on a Coast Guard officer's phone) can pick up
a high/critical-risk alarm signal, in addition to the in-browser alarm.mp3.

This only works for devices on the SAME local subnet as the machine
running this Flask app (phones on a different Wi-Fi/VLAN, or anything
over the public internet, will never receive it).
"""

import socket

# Set this to your LAN's broadcast address (e.g. 10.171.135.255 for a
# 10.171.135.0/24 subnet). Leaving it out and only using 255.255.255.255
# is usually fine too, since most routers/switches forward the limited
# broadcast address to the whole local subnet.
SUBNET_BROADCAST_ADDR = "10.171.135.255"
GLOBAL_BROADCAST_ADDR = "255.255.255.255"
BROADCAST_PORT = 8080


def trigger_all_phones_broadcast(message: bytes = b"ALARM", port: int = BROADCAST_PORT):
    """Fire-and-forget UDP broadcast to every device on the local network."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    try:
        print("🚨 Sending UDP broadcast alarm to devices on the local network...")
        sock.sendto(message, (SUBNET_BROADCAST_ADDR, port))
        sock.sendto(message, (GLOBAL_BROADCAST_ADDR, port))
        print("✅ Broadcast signal sent!")
        return True
    except OSError as e:
        # Broadcast can fail (e.g. permission or network restrictions in a
        # container/cloud host) — don't let that crash the request that
        # triggered it.
        print(f"⚠️ Broadcast failed: {e}")
        return False
    finally:
        sock.close()


if __name__ == "__main__":
    trigger_all_phones_broadcast()