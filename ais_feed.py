"""
Live vessel positions via AISStream.io (https://aisstream.io) — a free,
real-time AIS data stream delivered over WebSocket. No paid plan required:
sign up for a free account to get an API key.

This module runs a background thread with its own asyncio event loop that
stays connected to the stream, filtered to a bounding box around Mauritius,
and keeps an in-memory cache of the most recent position report per vessel
(MMSI). The Flask app polls that cache synchronously via get_live_vessels().

If AISSTREAM_API_KEY isn't set, or the connection can't be made (e.g. no
network access, key not yet activated), this fails quietly: get_status()
reports why, and the app falls back to the simulated fleet only.

Message format reference (aisstream.io/documentation):
  subscribe ->  {"APIKey": ..., "BoundingBoxes": [[[lat,lon],[lat,lon]]],
                 "FilterMessageTypes": ["PositionReport"]}
  receive   ->  {"MessageType": "PositionReport",
                 "MetaData": {"MMSI":.., "ShipName":.., "latitude":.., "longitude":..},
                 "Message": {"PositionReport": {"UserID":.., "Sog":.., "Cog":..,
                                                 "TrueHeading":.., "Latitude":.., "Longitude":..}}}
"""

import asyncio
import json
import os
import threading
import time

try:
    import websockets
except ImportError:  # pragma: no cover - handled gracefully at runtime
    websockets = None

AISSTREAM_API_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()
AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"

# Generous bounding box around Mauritius, comfortably covering the demo
# 350km EEZ circle used elsewhere in the app. [lat, lon] corners.
BOUNDING_BOXES = [
    [[-90.0, -180.0], [90.0, 180.0]]
]

MAX_VESSEL_AGE_SECONDS = 900  # drop stale contacts after 15 min of silence

_lock = threading.Lock()
_live_vessels = {}  # mmsi (str) -> normalized vessel dict
_status = {
    "configured": bool(AISSTREAM_API_KEY and websockets is not None),
    "connected": False,
    "last_message_at": None,
    "error": None if AISSTREAM_API_KEY else "AISSTREAM_API_KEY not set — showing simulated fleet only.",
    "vessel_count": 0,
}


def _normalize(meta, pos):
    mmsi = pos.get("UserID") or meta.get("MMSI")
    name = (meta.get("ShipName") or "").strip() or f"MMSI {mmsi}"
    lat = pos.get("Latitude", meta.get("latitude"))
    lon = pos.get("Longitude", meta.get("longitude"))
    speed = pos.get("Sog") or 0.0
    heading = pos.get("TrueHeading")
    if heading is None or heading == 511:  # 511 = "not available" in AIS spec
        heading = pos.get("Cog") or 0.0
    return {
        "id": f"AIS-{mmsi}",
        "mmsi": mmsi,
        "name": name,
        "type": "AIS contact (live)",
        "cargo": "Unknown",
        "lat": lat,
        "lng": lon,
        "speed": float(speed),
        "heading": float(heading),
        "registered": True,
        "source": "live",
        "updated_at": time.time(),
    }


async def _listen():
    subscribe_message = {
        "APIKey": AISSTREAM_API_KEY,
        "BoundingBoxes": BOUNDING_BOXES,
        "FilterMessageTypes": ["PositionReport"],
    }

    print("=" * 60)
    print("Connecting to AISStream...")
    print("Subscription:")
    print(json.dumps(subscribe_message, indent=2))
    print("=" * 60)

    async with websockets.connect(
        AISSTREAM_URL,
        open_timeout=15,
        ping_interval=20
    ) as ws:

        print("✅ Connected to AISStream")

        await ws.send(json.dumps(subscribe_message))
        print("✅ Subscription sent")

        with _lock:
            _status["connected"] = True
            _status["error"] = None

        try:
            first = await asyncio.wait_for(ws.recv(), timeout=15)
            print("\n========== FIRST MESSAGE ==========")
            print(first)
            print("===================================\n")

            try:
                msg = json.loads(first)

                if msg.get("MessageType") == "PositionReport":
                    meta = msg.get("MetaData") or {}
                    pos = (msg.get("Message") or {}).get("PositionReport") or {}

                    if pos.get("UserID") is not None:
                        vessel = _normalize(meta, pos)

                        with _lock:
                            _live_vessels[str(vessel["mmsi"])] = vessel
                            _status["connected"] = True
                            _status["last_message_at"] = time.time()
                            _status["vessel_count"] = len(_live_vessels)

            except Exception as e:
                print("Error processing first message:", e)

        except asyncio.TimeoutError:
            print("⚠ No AIS messages received within 15 seconds.")

        async for raw in ws:

            print("\nRAW MESSAGE:")
            print(raw)
            print("-" * 60)

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                print("Invalid JSON received.")
                continue

            if msg.get("MessageType") != "PositionReport":
                print("Ignoring:", msg.get("MessageType"))
                continue

            meta = msg.get("MetaData") or {}
            pos = (msg.get("Message") or {}).get("PositionReport") or {}

            if pos.get("UserID") is None:
                print("Position report without UserID.")
                continue

            vessel = _normalize(meta, pos)

            with _lock:
                _live_vessels[str(vessel["mmsi"])] = vessel
                _status["connected"] = True
                _status["last_message_at"] = time.time()
                _status["vessel_count"] = len(_live_vessels)

            print(f"✅ Stored vessel {vessel['mmsi']} ({vessel['name']})")

def _run_loop():
    if not AISSTREAM_API_KEY or websockets is None:
        with _lock:
            _status["error"] = (
                "websockets package not installed" if websockets is None
                else "AISSTREAM_API_KEY not set — showing simulated fleet only."
            )
        return

    backoff = 5
    while True:
        try:
            asyncio.run(_listen())
            backoff = 5  # reset after a clean connection
        except Exception as e:
            with _lock:
                _status["connected"] = False
                _status["error"] = f"{type(e).__name__}: {e}"
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)


_started = False


def start():
    """Idempotent — safe to call more than once (e.g. under the Flask reloader)."""
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_run_loop, daemon=True, name="aisstream-listener")
    t.start()


def get_live_vessels(max_age_seconds=MAX_VESSEL_AGE_SECONDS):
    now = time.time()
    with _lock:
        return [dict(v) for v in _live_vessels.values() if now - v["updated_at"] <= max_age_seconds]


def get_vessel(vessel_id, max_age_seconds=MAX_VESSEL_AGE_SECONDS):
    mmsi = str(vessel_id).replace("AIS-", "")
    now = time.time()
    with _lock:
        v = _live_vessels.get(mmsi)
    if not v or now - v["updated_at"] > max_age_seconds:
        return None
    return dict(v)


def get_status():
    now = time.time()
    with _lock:
        s = dict(_status)
        s["vessel_count"] = len(_live_vessels)
    if s["last_message_at"]:
        s["seconds_since_last_message"] = round(now - s["last_message_at"], 1)
    else:
        s["seconds_since_last_message"] = None
    return s
