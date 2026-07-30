"""
ais_updater.py

Background poller for the live MyShipTracking feed. Runs once immediately
on startup (so the map/report/alert pipeline has real data as soon as the
app boots) and then every UPDATE_INTERVAL seconds after that.

get_latest_vessels() is what the rest of the app (app.py) reads from —
it's always the most recent successful poll, normalized + with track
history attached by services/vessel_memory.py.
"""

import os
import threading
import time

from services.myshiptracking import get_live_vessels
from services.vessel_memory import update_tracks, attach_tracks


latest_vessels = []
latest_update_at = None
last_error = None

# 60s by default so the demo/live map feels responsive; override with
# AIS_POLL_INTERVAL_SECONDS if the upstream API needs a gentler polling rate.
UPDATE_INTERVAL = int(os.environ.get("AIS_POLL_INTERVAL_SECONDS", "60"))


def update_ais():

    global latest_vessels, latest_update_at, last_error

    while True:

        try:

            print("Updating AIS positions...")

            vessels = get_live_vessels()

            update_tracks(vessels)

            vessels = attach_tracks(vessels)

            latest_vessels = vessels
            latest_update_at = time.time()
            last_error = None

            print("Updated vessels:", len(vessels))

        except Exception as e:

            last_error = str(e)

            print("AIS update error:", e)

        time.sleep(UPDATE_INTERVAL)


def start_ais_updater():

    thread = threading.Thread(
        target=update_ais,
        daemon=True,
        name="ais-updater",
    )

    thread.start()


def get_latest_vessels():
    """Most recent successful poll of the live MyShipTracking feed.

    Returns an empty list if the feed hasn't returned usable data yet
    (e.g. no API key configured, or the very first poll hasn't landed) —
    callers should fall back to the simulated demo fleet in that case.
    """

    return latest_vessels


def get_ais_status():
    """Small status summary for banners / the alert monitor page."""

    return {
        "configured": True,
        "vessel_count": len(latest_vessels),
        "last_update_at": latest_update_at,
        "seconds_since_update": round(time.time() - latest_update_at, 1) if latest_update_at else None,
        "error": last_error,
    }
