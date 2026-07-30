"""
services/myshiptracking.py

Pulls the live vessel feed from MyShipTracking's "vessels in zone" API,
scoped to a bounding box around Mauritius.

Expected response shape for each vessel (this is exactly what BlueShield's
risk/report/map pipeline is built around — see ais_updater.py and
app.py's normalize_live_ship()):

    {
        "vessel_name": "CMA CGM HONG KONG",
        "mmsi": 249174000,
        "imo": 9218686,
        "vtype": 7,
        "lat": -20.18132,
        "lng": 57.14769,
        "course": 72.3,
        "speed": 14.9,
        "nav_status": 0,
        "received": "2026-07-29T14:45:06Z"
    }

If the API key isn't configured, the request fails, or the response
isn't valid JSON, this fails quietly and returns an empty list —
ais_updater.py / app.py fall back to the simulated demo fleet so the
site never shows a blank map.
"""

import os

import requests

API_KEY = os.environ.get("MYSHIPTRACKING_API_KEY", "x48UtXu2y%6lbmQieD7ve%tOwbaQaMeKDh...")

BASE_URL = "https://api.myshiptracking.com/api/v2"

# Bounding box around Mauritius' EEZ — matches the 350km demo geo-fence
# used elsewhere in the app.
DEFAULT_PARAMS = {
    "minlon": "57.0",
    "maxlon": "58.3",
    "minlat": "-20.8",
    "maxlat": "-19.6",
    "minutesBack": "60",
    "response": "simple",
}

REQUIRED_FIELDS = ("mmsi", "lat", "lng")


def _looks_valid(vessel):
    """Basic sanity check so one malformed record doesn't crash the pipeline."""
    return (
        isinstance(vessel, dict)
        and all(field in vessel and vessel[field] is not None for field in REQUIRED_FIELDS)
    )


def get_live_vessels():
    """
    Fetches the current vessel positions in the Mauritius zone.

    Returns a list of vessel dicts in the format documented above, or an
    empty list if the live feed isn't reachable right now.
    """

    url = f"{BASE_URL}/vessel/zone"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        response = requests.get(url, headers=headers, params=DEFAULT_PARAMS, timeout=10)
    except requests.RequestException as e:
        print(f"[myshiptracking] request failed: {e}")
        return []

    if response.status_code != 200:
        print(f"[myshiptracking] non-200 status: {response.status_code} — {response.text[:200]}")
        return []

    try:
        data = response.json()
    except ValueError:
        print("[myshiptracking] response was not valid JSON")
        return []

    # The API can return either {"data": [...]} or a bare list depending on
    # endpoint/plan — handle both so a format tweak upstream doesn't silently
    # zero out the fleet.
    vessels = data.get("data", []) if isinstance(data, dict) else data

    if not isinstance(vessels, list):
        print(f"[myshiptracking] unexpected payload shape: {type(vessels)}")
        return []

    clean_vessels = [v for v in vessels if _looks_valid(v)]

    print(f"[myshiptracking] {len(clean_vessels)}/{len(vessels)} vessels usable")

    return clean_vessels
