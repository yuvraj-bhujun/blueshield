"""
BlueShield AI — Maritime Domain Awareness Platform (Flask edition)
--------------------------------------------------------------
A hackathon-grade prototype demonstrating AI-assisted geo-fencing,
route-deviation detection, environmental risk scoring, and citizen /
NGO / Coast Guard collaboration for Mauritius' EEZ.

All "AI" logic here is transparent, rule-based Python standing in for
Gemma 4 + YOLOv11 inference so the demo runs with zero external
dependencies or API keys. Swap `classify_report()`, `score_vessel()`
and `explain_vessel()` for real model calls when wiring up Gemma.

---------------------------------------------------------------------------
LIVE VESSEL DATA FLOW (read this before touching /api/vessels)
---------------------------------------------------------------------------
1. services/myshiptracking.get_live_vessels() polls the MyShipTracking
   "vessels in zone" API and returns a list of dicts shaped like:

       {"vessel_name": "...", "mmsi": 249174000, "imo": 9218686,
        "vtype": 7, "lat": -20.18, "lng": 57.15, "course": 72.3,
        "speed": 14.9, "nav_status": 0, "received": "2026-07-29T14:45:06Z"}

2. ais_updater.py polls that function on a background thread every
   AIS_POLL_INTERVAL_SECONDS, records a position history per MMSI via
   services/vessel_memory.py, and exposes the latest normalized batch
   through ais_updater.get_latest_vessels().

3. get_active_fleet() below reads from get_latest_vessels(). If the
   live feed hasn't returned anything yet (no API key, upstream down,
   still booting), it falls back to FALLBACK_FLEET — the same static
   demo vessels used before — so the map/report/alert never go blank.

4. normalize_live_ship() converts one fleet record (+ its position
   history) into the shape risk_engine.calculate_risk() expects
   (MMSI/VesselName/Cargo/Draft/Speed/track[...]), which is also what
   gemma_engine.generate_vessel_reasoning() reads to build the report.

5. /api/vessels, /api/vessel/<mmsi> and /api/alert-status (the "signal"
   that drives the alarm on /monitor) all read from the SAME fleet, so
   the map pins, the executive report and the high-risk alarm can never
   drift out of sync with each other.
---------------------------------------------------------------------------
"""

import math
import random
import threading
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, render_template, request, send_file

from gemma_engine import generate_vessel_reasoning
from risk_engine import calculate_risk, calculate_fleet_collision_risk
from services.speech import english_to_mauritian_creole_speech
from services.phone_alarm import trigger_all_phones_broadcast
from services.email_alert import send_risk_alert_email
from data_loader import reef_gdf, benthic_gdf, reef_union

import ais_feed
from ais_updater import start_ais_updater, get_latest_vessels, get_ais_status

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Vessel type labels (AIS "vtype" -> human readable)
# ---------------------------------------------------------------------------

VESSEL_TYPE_LABELS = {
    7: "Cargo Vessel",
    9: "Pleasure Craft / Support Vessel",
    10: "Fishing Vessel",
}


def vessel_type_label(vtype):
    return VESSEL_TYPE_LABELS.get(vtype, "Unknown Vessel Type")


# Cargo/flag/destination/draft/length aren't part of the live AIS zone feed,
# so we infer sensible per-vtype defaults — this is what makes sure Gemma's
# report prompt (and the reef-grounding risk score, which factors in cargo
# and draft) never comes back full of "Unknown".
VTYPE_PROFILE_DEFAULTS = {
    7:  {"cargo": "Containerized / Bulk Cargo", "draft": 11.0, "length": 200, "flag": "Unknown", "destination": "Port Louis, Mauritius"},
    9:  {"cargo": "None (Pleasure Craft)", "draft": 2.8, "length": 18, "flag": "Mauritius", "destination": "Coastal Waters"},
    10: {"cargo": "Fresh/Frozen Fish Catch", "draft": 4.5, "length": 45, "flag": "Unknown", "destination": "Port Louis Fishing Port"},
}
DEFAULT_PROFILE = {"cargo": "Unknown", "draft": 6.0, "length": 60, "flag": "Unknown", "destination": "Unknown"}


# ---------------------------------------------------------------------------
# Fallback fleet — used only when the live MyShipTracking feed hasn't
# returned any vessels yet (missing API key, upstream outage, first few
# seconds after boot). Same shape as the live feed so downstream code
# doesn't need to special-case it.
# ---------------------------------------------------------------------------

FALLBACK_FLEET = [
    {"vessel_name": "CMA CGM HONG KONG", "mmsi": 249174000, "imo": 9218686, "vtype": 7,
     "lat": -20.18132, "lng": 57.14769, "course": 72.3, "speed": 14.9, "nav_status": 0,
     "received": "2026-07-29T14:45:06Z"},
    {"vessel_name": "KOTA NABIL", "mmsi": 565795000, "imo": 9356830, "vtype": 7,
     "lat": -20.1947, "lng": 57.25442, "course": 249.9, "speed": 13.6, "nav_status": 0,
     "received": "2026-07-29T14:42:52Z"},
    {"vessel_name": "MARIANNE K.", "mmsi": 244456000, "imo": 1112472, "vtype": 7,
     "lat": -20.14518, "lng": 57.35515, "course": 252.8, "speed": 10.6, "nav_status": 0,
     "received": "2026-07-29T14:45:11Z"},
    {"vessel_name": "RUEY I SHYANG NO.8", "mmsi": 416002632, "imo": None, "vtype": 10,
     "lat": -20.18074, "lng": 57.25965, "course": 257, "speed": 8.2, "nav_status": 15,
     "received": "2026-07-29T14:45:14Z"},
    {"vessel_name": "RUEY I SHYANG NO.7", "mmsi": 416002764, "imo": None, "vtype": 10,
     "lat": -20.22139, "lng": 57.27803, "course": 223.4, "speed": 8.4, "nav_status": 15,
     "received": "2026-07-29T14:44:54Z"},
    {"vessel_name": "NEPTUN", "mmsi": 219032574, "imo": None, "vtype": 9,
     "lat": -20.36586, "lng": 57.35961, "course": 511, "speed": 0.2, "nav_status": 1,
     "received": "2026-07-29T14:45:07Z"},
    {"vessel_name": "KNIGHT & RAYE", "mmsi": 232042080, "imo": None, "vtype": 9,
     "lat": -20.39055, "lng": 57.34115, "course": 511, "speed": 0, "nav_status": 15,
     "received": "2026-07-29T14:44:24Z"},
    {"vessel_name": "SOUL OF SEA", "mmsi": 601142800, "imo": None, "vtype": 9,
     "lat": -20.36498, "lng": 57.3649, "course": 511, "speed": 0, "nav_status": 15,
     "received": "2026-07-29T14:37:18Z"},
    {"vessel_name": "SEA SPIRIT III", "mmsi": 645648000, "imo": None, "vtype": 9,
     "lat": -20.36589, "lng": 57.36681, "course": 511, "speed": 0.1, "nav_status": 15,
     "received": "2026-07-29T14:35:26Z"},
]

REEFS = [
    {"id": "reef-blue-bay", "name": "Blue Bay Reef", "lat": -20.446, "lng": 57.713, "health": 91},
    {"id": "reef-pointe-esny", "name": "Pointe d'Esny Reef", "lat": -20.430, "lng": 57.734, "health": 74},
]

ais_feed.start()
start_ais_updater()

# ---------------------------------------------------------------------------
# Reference geography — Mauritius EEZ (simplified), reefs, MPAs, shipping lane
# ---------------------------------------------------------------------------

MAURITIUS_CENTER = (-20.348, 57.552)

MPAS = [
    {"id": "mpa-blue-bay", "name": "Blue Bay Marine Park (MPA)", "lat": -20.4460, "lng": 57.7130, "radius_km": 3.2},
    {"id": "mpa-balaclava", "name": "Balaclava Marine Park (MPA)", "lat": -20.0680, "lng": 57.3610, "radius_km": 4.0},
]

SHIPPING_LANE = [
    (-19.60, 58.10), (-19.95, 57.95), (-20.20, 57.80), (-20.55, 57.65), (-20.90, 57.50),
]

EEZ_RADIUS_KM = 350  # simplified circular approximation around Mauritius for demo geo-fencing

WAKASHIO_TRACK = [
    {"t": 0, "lat": -19.70, "lng": 58.25, "speed": 13.5, "heading": 245},
    {"t": 1, "lat": -19.95, "lng": 58.05, "speed": 13.2, "heading": 240},
    {"t": 2, "lat": -20.15, "lng": 57.90, "speed": 12.6, "heading": 235},
    {"t": 3, "lat": -20.28, "lng": 57.82, "speed": 11.4, "heading": 228},
    {"t": 4, "lat": -20.36, "lng": 57.78, "speed": 9.8,  "heading": 220},
    {"t": 5, "lat": -20.395,"lng": 57.755,"speed": 7.6,  "heading": 212},
    {"t": 6, "lat": -20.415,"lng": 57.742,"speed": 5.1,  "heading": 205},
    {"t": 7, "lat": -20.428,"lng": 57.7355,"speed": 2.0, "heading": 198},
    {"t": 8, "lat": -20.4310,"lng": 57.7350,"speed": 0.0, "heading": 190},
]
# ---------------------------------------------------------------------------
# In-memory "database" (resets on restart — fine for a demo)
# ---------------------------------------------------------------------------

INCIDENTS = [
    {"id": "INC-1042", "type": "Oil Spill", "lat": -20.430, "lng": 57.734, "confidence": 91,
     "authority": "National Coast Guard", "status": "Under Review",
     "reported_at": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
     "description": "Sheen visible on water surface near Pointe d'Esny, strong fuel odour reported."},
    {"id": "INC-1041", "type": "Damaged Coral", "lat": -20.446, "lng": 57.716, "confidence": 84,
     "authority": "Ministry of Blue Economy", "status": "Assigned to NGO",
     "reported_at": (datetime.now(timezone.utc) - timedelta(days=1, hours=3)).isoformat(),
     "description": "Anchor drag marks across staghorn coral colony in Blue Bay."},
    {"id": "INC-1039", "type": "Abandoned Fishing Net", "lat": -20.28, "lng": 57.38, "confidence": 77,
     "authority": "Fisheries Department", "status": "Resolved",
     "reported_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
     "description": "Ghost net entangled on reef edge, approx. 40m long."},
]

CORAL_SAMPLES = [
    {"id": "CS-301", "site": "Pointe d'Esny", "bleaching_pct": 18, "score": 74, "note": "Early-stage bleaching on branching coral, otherwise stable.", "submitted": "2 days ago"},
    {"id": "CS-298", "site": "Blue Bay", "bleaching_pct": 4, "score": 91, "note": "Vibrant coverage, high fish biodiversity observed.", "submitted": "5 days ago"},
    {"id": "CS-290", "site": "Flic en Flac", "bleaching_pct": 31, "score": 58, "note": "Algae overgrowth on 30% of surveyed transect.", "submitted": "1 week ago"},
]


# ---------------------------------------------------------------------------
# Reef / lane geometry helpers (backed by data_loader's already-loaded
# GeoDataFrames — no more per-request file reads, no more hardcoded
# C:\Users\... paths)
# ---------------------------------------------------------------------------

import geopandas as gpd
from shapely.geometry import Point

_reef_union_metric_series = gpd.GeoSeries([reef_union], crs="EPSG:32740")


def nearest_reef_distance(lat, lng):
    """Distance in km from (lat, lng) to the nearest reef polygon."""
    point = gpd.GeoSeries([Point(lng, lat)], crs="EPSG:4326").to_crs(32740)
    distance = point.iloc[0].distance(_reef_union_metric_series.iloc[0])
    return distance / 1000


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_to_nearest_reef_km(lat, lng):
    return nearest_reef_distance(lat, lng)


def distance_to_lane_km(lat, lng):
    return min(haversine_km(lat, lng, p[0], p[1]) for p in SHIPPING_LANE)


def in_eez(lat, lng):
    return haversine_km(lat, lng, *MAURITIUS_CENTER) <= EEZ_RADIUS_KM


# ---------------------------------------------------------------------------
# Live fleet plumbing
# ---------------------------------------------------------------------------

def get_active_fleet():
    """
    The single source of truth for "what vessels exist right now".

    Prefers the live MyShipTracking feed; falls back to the static demo
    fleet if the feed is empty (not configured / upstream down / still
    booting) so the map, the vessel report and the alert signal never go
    blank. Each vessel dict is tagged with "_source" so downstream code
    can label live vs. simulated contacts.

    The guaranteed high-risk demo vessel (MMSI 999999999, "MV WAKASHIO TEST
    (ALERT)") is ALWAYS merged in regardless of which fleet is active. It
    used to live only in FALLBACK_FLEET, which meant testing the alarm was
    a coin-flip: it worked whenever the live feed hadn't responded yet, and
    silently stopped the moment the live feed came online (even with real
    but low-risk vessels), since that switched get_active_fleet() away from
    FALLBACK_FLEET entirely and the test vessel went with it.
    """
    demo_alert_vessel = next((v for v in FALLBACK_FLEET if v["mmsi"] == 999999999), None)

    live = get_latest_vessels()
    if live:
        for v in live:
            v.setdefault("_source", "live")
        if demo_alert_vessel and not any(v.get("mmsi") == 999999999 for v in live):
            live = [dict(demo_alert_vessel, _source="simulated")] + live
        return live

    return [dict(v, _source="simulated") for v in FALLBACK_FLEET]


def find_in_fleet(mmsi):
    fleet = get_active_fleet()
    target = str(mmsi)
    return next((s for s in fleet if str(s.get("mmsi")) == target), None)


def normalize_live_ship(ship):
    """
    Converts one live/fallback AIS record (+ any position history attached
    by services/vessel_memory.py) into the vessel_data shape risk_engine.
    calculate_risk() and gemma_engine.generate_vessel_reasoning() expect:

        MMSI, IMO, VesselName, VesselType, Flag, Destination, Cargo,
        Length, Draft, Speed, Heading, track: [{lat, lon, speed, heading}, ...]
    """
    vtype = ship.get("vtype")
    profile = VTYPE_PROFILE_DEFAULTS.get(vtype, DEFAULT_PROFILE)

    lat = ship.get("lat")
    lng = ship.get("lng")
    speed = ship.get("speed", 0) or 0
    heading = ship.get("course", 0) or 0

    # services/vessel_memory.py attaches "track": [{"lat","lng","speed","course","time"}, ...]
    # (oldest -> newest) once the live feed has been polled a couple of
    # times. risk_engine expects "lon" (not "lng") on each point, and at
    # least the current position as the final entry.
    history = ship.get("track") or []
    track = [
        {"lat": p.get("lat"), "lon": p.get("lng"), "speed": p.get("speed", 0), "heading": p.get("course", 0)}
        for p in history
        if p.get("lat") is not None and p.get("lng") is not None
    ]

    current_point = {"lat": lat, "lon": lng, "speed": speed, "heading": heading}
    if not track or track[-1]["lat"] != lat or track[-1]["lon"] != lng:
        track.append(current_point)
    if not track:
        track = [current_point]

    return {
        "MMSI": ship.get("mmsi"),
        "IMO": ship.get("imo") if ship.get("imo") else "Not available",
        "VesselName": ship.get("vessel_name", "Unknown"),
        "VesselType": vessel_type_label(vtype),
        "Flag": profile["flag"],
        "Destination": profile["destination"],
        "Cargo": profile["cargo"],
        "Length": profile["length"],
        "Draft": profile["draft"],
        "Speed": speed,
        "Heading": heading,
        "track": track,
        "_source": ship.get("_source", "live"),
    }


# ---------------------------------------------------------------------------
# Lightweight "AI" — rule-based stand-ins for Gemma 4 / YOLOv11 inference
# (used by the Wakashio replay demo and citizen-report classifier)
# ---------------------------------------------------------------------------

REPORT_KEYWORDS = {
    "Oil Spill": (["oil", "spill", "sheen", "fuel", "slick"], "National Coast Guard"),
    "Illegal Dumping": (["dump", "waste", "garbage", "trash", "debris"], "Ministry of Environment"),
    "Dead Marine Animal": (["dead", "carcass", "stranded", "washed up"], "Fisheries Department"),
    "Abandoned Fishing Net": (["net", "ghost net", "entangled", "fishing gear"], "Fisheries Department"),
    "Damaged Coral": (["coral", "bleach", "broken reef", "anchor damage"], "Ministry of Blue Economy"),
    "Suspicious Vessel": (["vessel", "ship", "boat", "tanker", "anchored"], "National Coast Guard"),
}


def classify_report(description: str):
    """Rule-based text classifier standing in for Gemma's multimodal reasoning."""
    text = (description or "").lower()
    best_type, best_authority, best_hits = "Suspicious Vessel", "National Coast Guard", 0
    for label, (keywords, authority) in REPORT_KEYWORDS.items():
        hits = sum(1 for k in keywords if k in text)
        if hits > best_hits:
            best_type, best_authority, best_hits = label, authority, hits
    base_confidence = 62 + best_hits * 9
    confidence = min(97, base_confidence + random.randint(-4, 6))
    if best_hits == 0:
        confidence = random.randint(48, 60)
    return {"category": best_type, "confidence": confidence, "authority": best_authority}


def score_vessel(v):
    """Environmental Risk Engine — combines distance to reef, route deviation,
    speed, cargo sensitivity, and simplified weather into a single 0-100 score.
    (Used by the standalone Wakashio replay, which has its own scripted track.)"""
    reef_dist = distance_to_nearest_reef_km(v["lat"], v["lng"])
    lane_dist = distance_to_lane_km(v["lat"], v["lng"])
    deviation_km = 0 if v.get("on_lane") else round(lane_dist, 1)

    reef_factor = max(0, 40 - reef_dist) / 40 * 45          # closer to reef -> higher
    deviation_factor = min(deviation_km, 60) / 60 * 25       # bigger deviation -> higher
    speed_factor = 10 if v["speed"] < 3 and reef_dist < 25 else (5 if v["speed"] < 6 else 0)
    cargo_factor = 15 if "oil" in v["cargo"].lower() or "fuel" in v["cargo"].lower() else 0
    registry_factor = 5 if not v.get("registered", True) else 0
    weather_factor = 5 if v["id"] in ("MV-NORDLYS",) else 0  # demo: simulate high-wind zone

    score = reef_factor + deviation_factor + speed_factor + cargo_factor + registry_factor + weather_factor
    score = max(4, min(99, round(score)))

    if score >= 75:
        level = "High"
    elif score >= 40:
        level = "Medium"
    else:
        level = "Low"

    return {
        "score": score, "level": level, "reef_distance_km": round(reef_dist, 1),
        "deviation_km": deviation_km,
    }


def explain_vessel(v, risk):
    """Explainable AI narrative — the Gemma-style reasoning trace."""
    reasons = []
    if risk["deviation_km"] > 5:
        reasons.append(f"deviated roughly {risk['deviation_km']} km from the established shipping corridor")
    else:
        reasons.append("is holding close to the designated shipping lane")
    if risk["reef_distance_km"] < 15:
        reasons.append(f"is approaching a reef system only {risk['reef_distance_km']} km away")
    if v["speed"] < 6:
        reasons.append(f"has reduced speed to {v['speed']} knots, unusual for open water")
    if "oil" in v["cargo"].lower() or "fuel" in v["cargo"].lower():
        reasons.append("is carrying heavy fuel oil, raising spill severity if grounding occurs")
    if not v.get("registered", True):
        reasons.append("does not match a registered vessel profile in the regional AIS database")

    narrative = "The vessel " + ", and ".join(reasons) + "."
    recommendation = (
        "Dispatch patrol for visual confirmation" if risk["level"] == "High" else
        "Continue monitoring" if risk["level"] == "Medium" else
        "No action required"
    )
    return {"narrative": narrative, "recommendation": recommendation}


def grounding_prediction(v, risk):
    reef_dist = risk["reef_distance_km"]
    speed = max(v["speed"], 0.5)
    eta_hours = round(reef_dist / speed, 1) if risk["level"] != "Low" else None
    probability = min(96, max(3, risk["score"] - 5 + random.randint(-3, 3)))
    return {"probability": probability, "eta_hours": eta_hours}


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/report")
def report_page():
    return render_template("report.html")


@app.route("/map")
def map_page():
    return render_template("map.html")


@app.route("/ngo")
def ngo_page():
    return render_template("ngo.html")


@app.route("/coastguard")
def coastguard_page():
    return render_template("coastguard.html")


@app.route("/wakashio")
def wakashio_page():
    return render_template("wakashio.html")


@app.route("/monitor")
def monitor_page():
    """Standalone high-risk alert monitor — polls /api/alert-status and
    sounds static/sounds/alarm.mp3 when a vessel's risk probability goes High/Critical."""
    return render_template("alert_monitor.html")


# ---------------------------------------------------------------------------
# API routes — public
# ---------------------------------------------------------------------------

@app.route("/api/reefs")
def api_reefs():
    return jsonify({"reefs": REEFS, "mpas": MPAS})


@app.route("/api/incidents", methods=["GET"])
def api_incidents():
    return jsonify({"incidents": sorted(INCIDENTS, key=lambda i: i["reported_at"], reverse=True)})


@app.route("/api/report", methods=["POST"])
def api_submit_report():
    data = request.get_json(force=True, silent=True) or {}
    description = data.get("description", "")
    lat = float(data.get("lat", MAURITIUS_CENTER[0]))
    lng = float(data.get("lng", MAURITIUS_CENTER[1]))

    result = classify_report(description)
    incident = {
        "id": f"INC-{random.randint(2000, 9999)}",
        "type": result["category"],
        "lat": lat, "lng": lng,
        "confidence": result["confidence"],
        "authority": result["authority"],
        "status": "Under Review",
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "description": description or "No description provided.",
    }
    INCIDENTS.insert(0, incident)
    return jsonify({"incident": incident, "ai": result})


@app.route("/api/marine-education", methods=["POST"])
def api_marine_education():
    """Very small canned Q&A demo standing in for Gemma multimodal reasoning."""
    data = request.get_json(force=True, silent=True) or {}
    question = (data.get("question") or "").lower()

    if "healthy" in question or "coral" in question:
        answer = ("Healthy coral shows bright, saturated colour and a rough, branching or "
                   "boulder-like texture. Pale, white, or fuzzy-looking coral usually signals "
                   "bleaching or algae overgrowth — worth logging as a report if you spot it.")
    elif "fish" in question or "species" in question:
        answer = ("Reef fish ID depends on body shape, colour banding, and fin pattern — "
                   "for a confident species match, a clear side-profile photo helps most. "
                   "Try the Coral Health Monitoring uploader on the NGO portal for a full analysis.")
    elif "safe" in question or "beach" in question:
        answer = ("Check the Coastal Hazard Map for active incidents near your beach first. "
                   "No nearby reports plus calm, clear water is generally a good sign — when in "
                   "doubt, ask a lifeguard or coast guard post.")
    else:
        answer = ("Good question — for the fullest answer, upload a photo through the Report "
                   "or Coral Health tools so the vision model has something to reason over.")

    return jsonify({"answer": answer})


@app.route("/api/speech/creole", methods=["POST"])
def generate_creole_audio():
    data = request.json
    english_text = data.get(
        "text",
        ""
    )

    vessel_id = data.get(
        "vessel_id",
        ""
    )

    audio_path = english_to_mauritian_creole_speech(

        english_text=english_text,

        cache_key=vessel_id

    )

    return send_file(
        audio_path,
        mimetype="audio/wav"
    )


# ---------------------------------------------------------------------------
# API routes — NGO
# ---------------------------------------------------------------------------

@app.route("/api/coral-samples")
def api_coral_samples():
    return jsonify({"samples": CORAL_SAMPLES})


@app.route("/api/coral-upload", methods=["POST"])
def api_coral_upload():
    data = request.get_json(force=True, silent=True) or {}
    site = data.get("site", "Unnamed Site")
    bleaching_pct = random.randint(2, 45)
    score = max(20, 100 - bleaching_pct * 2 - random.randint(0, 10))
    note = (
        "Minimal stress signs, reef structure intact." if score > 80 else
        "Moderate bleaching detected, recommend follow-up survey in 2 weeks." if score > 55 else
        "Significant bleaching/algae overgrowth — flagged as restoration priority."
    )
    sample = {
        "id": f"CS-{random.randint(300, 999)}", "site": site, "bleaching_pct": bleaching_pct,
        "score": score, "note": note, "submitted": "just now",
    }
    CORAL_SAMPLES.insert(0, sample)
    return jsonify({"sample": sample})


@app.route("/api/ngo-report")
def api_ngo_report():
    """Auto-generated weekly summary — canned but data-driven."""
    avg_health = round(sum(r["health"] for r in REEFS) / len(REEFS))
    worst = min(REEFS, key=lambda r: r["health"])
    open_incidents = [i for i in INCIDENTS if i["status"] != "Resolved"]
    summary = (
        f"Average reef health across monitored sites is {avg_health}/100 this week. "
        f"{worst['name']} needs the most attention at {worst['health']}/100 and is "
        f"recommended as the top restoration priority. {len(open_incidents)} incident "
        f"report(s) remain open, including {open_incidents[0]['type'].lower()} near "
        f"{'the coastline' if open_incidents else 'no active site'}."
        if open_incidents else
        f"Average reef health across monitored sites is {avg_health}/100 this week, with "
        f"{worst['name']} as the top restoration priority. No incident reports are currently open."
    )
    return jsonify({
        "summary": summary,
        "avg_health": avg_health,
        "priority_site": worst["name"],
        "open_incidents": len(open_incidents),
    })


# ---------------------------------------------------------------------------
# API routes — Coast Guard / geospatial
# ---------------------------------------------------------------------------

@app.route("/api/coral")
def get_coral():
    coral_only = benthic_gdf[benthic_gdf["class"] == "Coral/Algae"]
    return jsonify(coral_only.__geo_interface__)


@app.route("/api/reef_extent")
def reef_extent():
    return jsonify(reef_gdf.__geo_interface__)

@app.route("/api/test-trigger-alarm", methods=["POST", "GET"])
def test_trigger_alarm():
    """Forces a high-risk test vessel into the fallback fleet to trip the alarm."""
    test_vessel = {
        "vessel_name": "MV CRITICAL ALERT (DEMO)",
        "mmsi": 999999999,
        "imo": 9999999,
        "vtype": 7,
        "lat": -20.4310,
        "lng": 57.7350,
        "course": 210,
        "speed": 14.0,
        "nav_status": 0,
        "received": datetime.now(timezone.utc).isoformat(),
    }

    # Append to FALLBACK_FLEET if not present
    if not any(v["mmsi"] == 999999999 for v in FALLBACK_FLEET):
        FALLBACK_FLEET.insert(0, test_vessel)

    return jsonify(
        {
            "status": "success",
            "message": "High-risk vessel inserted! Alarm triggered.",
            "test_vessel": test_vessel,
        }
    )


def get_worst_fleet_risk():
    """
    Scans the whole active fleet and returns (worst_ship, worst_risk) — the
    single vessel_data + calculate_risk() pair with the highest score right
    now. Shared by /api/alert-status and /api/trigger-alarm so they can
    never disagree about which vessel is currently tripping the alarm.
    Returns (None, None) if the fleet is empty or every risk calc failed.
    """
    fleet = get_active_fleet()

    worst_ship = None
    worst_risk = None

    for ship in fleet:
        try:
            vessel_data = normalize_live_ship(ship)
            risk = calculate_risk(vessel_data)
        except Exception as e:
            print(f"[get_worst_fleet_risk] risk calc failed for {ship.get('mmsi')}: {e}")
            continue

        if worst_risk is None or risk["score"] > worst_risk["score"]:
            worst_ship, worst_risk = vessel_data, risk

    return worst_ship, worst_risk


# Tracks which vessels we've ALREADY emailed about during their current
# High/Critical episode, so each episode only sends one email — not one
# every 5-second poll. Cleared automatically the moment that vessel drops
# back to Low/Medium, so the NEXT time it crosses into High/Critical it
# emails again. This matches the exact same alert condition the alarm uses
# (risk["level"] in ("High", "Critical")).
_vessels_already_emailed = set()  # {mmsi, ...}


def maybe_send_alarm_email(vessel, risk, gemma_text=None):
    """
    Sends the risk-alert email for `vessel` exactly once per High/Critical
    episode — the same trip condition as the audible alarm. Runs the SMTP
    call in a background thread so a slow mail server never delays the API
    response that triggered it.

    If gemma_text isn't already available, it's generated here — but ONLY
    right before we actually send, so the local Gemma model isn't hit on
    every single alarm poll.
    """
    mmsi = vessel.get("MMSI")
    is_high = risk.get("level") in ("High", "Critical")

    if not is_high:
        # Not currently in an alarm state — reset so the next time this
        # vessel crosses into High/Critical, it emails again.
        _vessels_already_emailed.discard(mmsi)
        return False

    if mmsi in _vessels_already_emailed:
        # Already emailed for this ongoing episode — stay quiet.
        return False

    _vessels_already_emailed.add(mmsi)

    print(
        f"[alarm-email] {vessel.get('VesselName')} (MMSI {mmsi}) crossed into "
        f"{risk.get('level')} risk (score {risk.get('score')}/100) — dispatching alert email now.",
        flush=True,
    )

    if gemma_text is None:
        gemma_text = generate_vessel_reasoning(vessel, risk)

    threading.Thread(
        target=send_risk_alert_email,
        args=(vessel, risk, gemma_text),
        daemon=True,
    ).start()
    return True


@app.route("/api/trigger-alarm", methods=["POST"])
def trigger_alarm():
    """
    Called by coastguard.js the moment it sees a High/Critical-risk vessel
    in /api/vessels. Fires the LAN UDP broadcast (services/phone_alarm.py)
    so phones on the same network can sound their own alarm, alongside the
    in-browser alarm.mp3 — and, subject to the cooldown above, emails the
    Coast Guard/NGO list (services/email_alert.py) with the Gemma executive
    report for whichever vessel is currently the fleet's worst offender.
    """
    threading.Thread(target=trigger_all_phones_broadcast, daemon=True).start()

    worst_ship, worst_risk = get_worst_fleet_risk()

    email_dispatched = False
    if worst_ship is not None:
        print(
            f"[trigger-alarm] worst vessel: {worst_ship.get('VesselName')} "
            f"(MMSI {worst_ship.get('MMSI')}) — level={worst_risk.get('level')} "
            f"score={worst_risk.get('score')}",
            flush=True,
        )
        if worst_risk["level"] in ("High", "Critical"):
            email_dispatched = maybe_send_alarm_email(worst_ship, worst_risk)
    else:
        print("[trigger-alarm] no vessels in active fleet — nothing to email.", flush=True)

    return jsonify({
        "status": "ok",
        "message": "Broadcast alarm dispatched.",
        "email_dispatched": email_dispatched,
    })


# ---------------------------------------------------------------------------
# API routes — live vessel fleet (map pins, vessel detail report, and the
# high-risk alert signal all read from get_active_fleet() so they can never
# drift out of sync with each other)
# ---------------------------------------------------------------------------

@app.route("/api/vessels")
def vessels():
    fleet = get_active_fleet()

    vessels_out = []
    for ship in fleet:
        # Reef-grounding risk (distance/trend/cargo/lane-deviation) — the
        # SAME calculate_risk() call used by /api/vessel/<mmsi> and
        # /api/alert-status, so the badge shown here, the detail report,
        # and the alarm trigger all agree on one vessel's risk. This is
        # what coastguard.js reads (v.risk.level / v.risk.score) to decide
        # whether to sound alarm.mp3.
        try:
            vessel_data = normalize_live_ship(ship)
            grounding_risk = calculate_risk(vessel_data)
        except Exception as e:
            print(f"[/api/vessels] risk calc failed for {ship.get('mmsi')}: {e}")
            grounding_risk = {"score": 0, "level": "Low"}

        vessels_out.append({
            "id": ship.get("mmsi"),
            "name": ship.get("vessel_name", "Unknown"),
            "lat": ship.get("lat"),
            "lng": ship.get("lng"),
            "speed": ship.get("speed", 0) or 0,
            "heading": ship.get("course", 0) or 0,
            "type": vessel_type_label(ship.get("vtype")),
            "in_eez": in_eez(ship["lat"], ship["lng"]) if ship.get("lat") is not None else False,
            "source": ship.get("_source", "live"),
            "risk": grounding_risk,
        })

    # Ship-to-ship collision risk (CPA/TCPA) — computed pairwise across the
    # live fleet. Kept separate from "risk" (reef-grounding) so the alarm
    # logic never gets the two signals mixed up; exposed here in case the
    # UI wants to show a collision warning alongside the grounding badge.
    collision_risk = calculate_fleet_collision_risk(vessels_out)

    for v in vessels_out:
        v["collision"] = collision_risk[v["id"]]

    return jsonify({
        "vessels": vessels_out,
        "ais_status": {
            "connected": any(v["source"] == "live" for v in vessels_out),
            "vessel_count": len(vessels_out),
        },
    })


@app.route("/api/vessel/<mmsi>")
def vessel(mmsi):
    print("REQUEST RECEIVED:", mmsi)

    ship = find_in_fleet(mmsi)

    if ship is None:
        print("SHIP NOT FOUND")
        return jsonify({"error": "Ship not found"}), 404

    vessel_data = normalize_live_ship(ship)

    # Reef-grounding risk assessment (distance/trend/ETA to the nearest
    # reef) — this is what feeds the executive report prompt below, and
    # what /api/alert-status uses to decide whether this vessel's
    # grounding probability is "High" enough to trip the alarm.
    risk = calculate_risk(vessel_data)

    # Click-to-analyse: this is the call that sends the prompt built in
    # gemma_engine.generate_vessel_reasoning() to Gemma and gets back the
    # executive report paragraph shown when a card is opened.
    gemma_response = generate_vessel_reasoning(vessel_data, risk)

    return jsonify({
        "vessel": vessel_data,
        "risk": risk,
        "gemma_reasoning": gemma_response,
    })


@app.route("/api/ais-status")
def api_ais_status():
    status = ais_feed.get_status()
    status["myshiptracking"] = get_ais_status()
    return jsonify(status)


# ---------------------------------------------------------------------------
# API routes — the high-risk "signal"
#
# /monitor + static/js/script.js poll this every few seconds and sound
# static/sounds/alarm.mp3 when alert == "yes". A vessel trips the alert
# when its reef-grounding risk probability (risk_engine.calculate_risk,
# same score shown on the vessel detail card) reaches High/Critical.
# Gemma's narrative report is only generated for the triggering vessel
# (not the whole fleet) so a 5-second poll doesn't hammer the local model.
# ---------------------------------------------------------------------------

@app.route("/api/alert-status")
def api_alert_status():
    worst_ship, worst_risk = get_worst_fleet_risk()

    if worst_risk is None:
        return jsonify({"alert": "no", "risk": None, "vessel": None, "report": None})

    is_high = worst_risk["level"] in ("High", "Critical")

    report = None
    if is_high:
        # Only call the (comparatively slow) local Gemma model for the
        # vessel that's actually tripping the alarm.
        report = generate_vessel_reasoning(worst_ship, worst_risk)
        print(
            f"[alert-status] {worst_ship.get('VesselName')} (MMSI {worst_ship.get('MMSI')}) "
            f"is {worst_risk.get('level')} — checking whether to email.",
            flush=True,
        )
        # Email the Coast Guard/NGO list with that same report (only once
        # per ongoing episode — see maybe_send_alarm_email).
        maybe_send_alarm_email(worst_ship, worst_risk, gemma_text=report)

    return jsonify({
        "alert": "yes" if is_high else "no",
        "risk": worst_risk,
        "vessel": {
            "mmsi": worst_ship["MMSI"],
            "name": worst_ship["VesselName"],
        },
        "report": report,
    })


@app.route("/api/gemma")
def api_gemma():
    """Back-compat alias for /api/alert-status (same "signal" contract:
    {"alert": "yes"|"no", "risk": {...}, "report": "..."})."""
    return api_alert_status()


@app.route("/api/geofence-check", methods=["POST"])
def api_geofence_check():
    """AI Geo-Fencing evaluation for a single point crossing a boundary."""
    data = request.get_json(force=True, silent=True) or {}
    lat, lng = float(data.get("lat")), float(data.get("lng"))
    reef_dist = distance_to_nearest_reef_km(lat, lng)
    lane_dist = distance_to_lane_km(lat, lng)
    inside = in_eez(lat, lng)
    mpa_hit = next((m for m in MPAS if haversine_km(lat, lng, m["lat"], m["lng"]) <= m["radius_km"]), None)
    return jsonify({
        "in_eez": inside,
        "near_mpa": mpa_hit["name"] if mpa_hit else None,
        "reef_distance_km": round(reef_dist, 1),
        "lane_deviation_km": round(lane_dist, 1),
    })


@app.route("/api/wakashio-track")
def api_wakashio_track():
    return jsonify({"track": WAKASHIO_TRACK, "reef": REEFS[0]})


@app.route("/api/wakashio-step/<int:t>")
def api_wakashio_step(t):
    t = max(0, min(t, len(WAKASHIO_TRACK) - 1))
    point = WAKASHIO_TRACK[t]
    fake_vessel = {
        "id": "MV-WAKASHIO-DEMO", "name": "MV Kaiyo (simulated)", "type": "Bulk Carrier",
        "cargo": "Heavy Fuel Oil / Ballast", "lat": point["lat"], "lng": point["lng"],
        "speed": point["speed"], "heading": point["heading"], "on_lane": t < 3, "registered": True,
    }
    risk = score_vessel(fake_vessel)
    explanation = explain_vessel(fake_vessel, risk)
    prediction = grounding_prediction(fake_vessel, risk)
    return jsonify({
        "point": point, "vessel": fake_vessel, "risk": risk,
        "explanation": explanation, "prediction": prediction,
        "in_eez": in_eez(point["lat"], point["lng"]),
        "final": t == len(WAKASHIO_TRACK) - 1,
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)