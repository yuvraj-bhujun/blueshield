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
"""

import math
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from gemma_engine import generate_vessel_reasoning
from risk_engine import calculate_risk

import ais_feed

app = Flask(__name__)

# =====================================================
# Load historical AIS vessels
# =====================================================

SHIPS_FILE = Path("static/data/ships.json")

REEFS = [
    {
        "id": "reef-blue-bay",
        "name": "Blue Bay Reef",
        "lat": -20.446,
        "lng": 57.713,
        "health": 91
    },
    {
        "id": "reef-pointe-esny",
        "name": "Pointe d'Esny Reef",
        "lat": -20.430,
        "lng": 57.734,
        "health": 74
    }
]

with open(SHIPS_FILE, "r", encoding="utf-8") as f:
    SHIPS = json.load(f)

ais_feed.start()

from ais_updater import start_ais_updater

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
# Lightweight "AI" — rule-based stand-ins for Gemma 4 / YOLOv11 inference
# ---------------------------------------------------------------------------

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
    speed, cargo sensitivity, and simplified weather into a single 0-100 score."""
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
# API routes — Coast Guard
# ---------------------------------------------------------------------------



from flask import jsonify
import geopandas as gpd

BENTHIC_PATH = r"C:\Users\yuvra\Downloads\Mauritian-Exclusive-Economic-Zone-20230309200653 (1)\Benthic-Map\benthic.gpkg"

coral_layer = None


@app.route("/api/coral")
def get_coral():

    global coral_layer

    if coral_layer is None:

        coral_layer = gpd.read_file(BENTHIC_PATH)

        # Keep only coral polygons
        coral_layer = coral_layer[
            coral_layer["class"] == "Coral/Algae"
        ]

        coral_layer = coral_layer.to_crs(epsg=4326)

    return jsonify(coral_layer.__geo_interface__)

def _drift(v):
    """Nudge a demo vessel slightly each poll so the dashboard feels live."""
    v["lat"] += math.sin(time.time() / 20 + hash(v["id"]) % 10) * 0.002
    v["lng"] += math.cos(time.time() / 25 + hash(v["id"]) % 10) * 0.002
    v["speed"] = max(0, v["speed"] + random.uniform(-0.3, 0.3))
    return v

from flask import jsonify
import geopandas as gpd

REEF_PATH = "reefextent.gpkg"
reef_data = gpd.read_file(REEF_PATH)
reef_data = reef_data.to_crs(epsg=4326)

def get_ship(mmsi):

    for ship in SHIPS:

        if ship["MMSI"] == str(mmsi):
            return ship

    return None

def get_latest_position(ship):

    return ship["track"][-1]

def get_last_positions(ship):

    return ship["track"][-5:]

from shapely.geometry import Point

reef_union = reef_data.geometry.union_all()

def nearest_reef_distance(lat, lon):

    point = gpd.GeoSeries(
        [Point(lon, lat)],
        crs="EPSG:4326"
    ).to_crs(32740)

    reef = gpd.GeoSeries(
        [reef_union],
        crs="EPSG:4326"
    ).to_crs(32740)

    distance = point.iloc[0].distance(reef.iloc[0])

    return distance / 1000


@app.route("/api/reef_extent")
def reef_extent():

    global reef_data

    if reef_data is None:

        reef_data = gpd.read_file(REEF_PATH)

        reef_data = reef_data.to_crs(epsg=4326)

    return jsonify(reef_data.__geo_interface__)


from flask import jsonify
import json

from ais_updater import get_latest_vessels
from ais_updater import get_latest_vessels


@app.route("/api/vessels")
# def vessels():

#     ships = get_latest_vessels()

#     output = []


#     for ship in ships:


#         # temporarily use simple risk
#         # because risk_engine still expects old format

#         risk = {
#             "score": 0,
#             "level": "Monitoring"
#         }


#         output.append({

#             "id": ship["mmsi"],

#             "name": ship.get(
#                 "vessel_name",
#                 "Unknown"
#             ),

#             "lat": ship["lat"],

#             "lng": ship["lng"],

#             "speed": ship.get(
#                 "speed",
#                 0
#             ),

#             "heading": ship.get(
#                 "course",
#                 0
#             ),

#             "type": ship.get(
#                 "vtype",
#                 "Unknown"
#             ),

#             "risk": {

#                 "score": risk["score"],

#                 "level": risk["level"]

#             },


#             "source":"MyShipTracking AIS"

#         })


#     return jsonify({

#         "vessels": output,

#         "ais_status": {

#             "connected": True,

#             "vessel_count": len(output)

#         }

#     })

def vessels():

    ships = [
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
        },
        {
            "vessel_name": "KOTA NABIL",
            "mmsi": 565795000,
            "imo": 9356830,
            "vtype": 7,
            "lat": -20.1947,
            "lng": 57.25442,
            "course": 249.9,
            "speed": 13.6,
            "nav_status": 0,
            "received": "2026-07-29T14:42:52Z"
        },
        {
            "vessel_name": "MARIANNE K.",
            "mmsi": 244456000,
            "imo": 1112472,
            "vtype": 7,
            "lat": -20.14518,
            "lng": 57.35515,
            "course": 252.8,
            "speed": 10.6,
            "nav_status": 0,
            "received": "2026-07-29T14:45:11Z"
        },
        {
            "vessel_name": "RUEY I SHYANG NO.8",
            "mmsi": 416002632,
            "imo": None,
            "vtype": 10,
            "lat": -20.18074,
            "lng": 57.25965,
            "course": 257,
            "speed": 8.2,
            "nav_status": 15,
            "received": "2026-07-29T14:45:14Z"
        },
        {
            "vessel_name": "RUEY I SHYANG NO.7",
            "mmsi": 416002764,
            "imo": None,
            "vtype": 10,
            "lat": -20.22139,
            "lng": 57.27803,
            "course": 223.4,
            "speed": 8.4,
            "nav_status": 15,
            "received": "2026-07-29T14:44:54Z"
        },
        {
            "vessel_name": "NEPTUN",
            "mmsi": 219032574,
            "imo": None,
            "vtype": 9,
            "lat": -20.36586,
            "lng": 57.35961,
            "course": 511,
            "speed": 0.2,
            "nav_status": 1,
            "received": "2026-07-29T14:45:07Z"
        },
        {
            "vessel_name": "KNIGHT & RAYE",
            "mmsi": 232042080,
            "imo": None,
            "vtype": 9,
            "lat": -20.39055,
            "lng": 57.34115,
            "course": 511,
            "speed": 0,
            "nav_status": 15,
            "received": "2026-07-29T14:44:24Z"
        },
        {
            "vessel_name": "SOUL OF SEA",
            "mmsi": 601142800,
            "imo": None,
            "vtype": 9,
            "lat": -20.36498,
            "lng": 57.3649,
            "course": 511,
            "speed": 0,
            "nav_status": 15,
            "received": "2026-07-29T14:37:18Z"
        },
        {
            "vessel_name": "SEA SPIRIT III",
            "mmsi": 645648000,
            "imo": None,
            "vtype": 9,
            "lat": -20.36589,
            "lng": 57.36681,
            "course": 511,
            "speed": 0.1,
            "nav_status": 15,
            "received": "2026-07-29T14:35:26Z"
        }
    ]


    # Convert AIS format to frontend format
    vessels = []

    for ship in ships:

        vessels.append({

            "id": ship["mmsi"],

            "name": ship["vessel_name"],

            "lat": ship["lat"],

            "lng": ship["lng"],

            "speed": ship["speed"],

            "heading": ship["course"],

            "type": ship["vtype"],

            # Temporary values
            "in_eez": True,

            "risk": {
                "score": 0,
                "level": "Monitoring"
            },

            "source": "live"

        })


    return jsonify({

        "vessels": vessels,

        "ais_status": {

            "connected": True,

            "vessel_count": len(vessels)

        }

    })

@app.route("/api/vessel/<mmsi>")
def vessel(mmsi):
    
    print("REQUEST RECEIVED:", mmsi)
    ship = get_ship(mmsi)

    if ship is None:
        return jsonify({
            "error":"Ship not found"
        }),404


    risk = calculate_risk(ship)


    gemma_response = generate_vessel_reasoning(
        ship,
        risk
    )


    return jsonify({

        "vessel":{
            "MMSI":ship["MMSI"],
            "IMO":ship["IMO"],
            "VesselName":ship["VesselName"],
            "VesselType":ship["VesselType"],
            "Flag":ship["Flag"],
            "Destination":ship["Destination"],
            "Cargo":ship["Cargo"],
            "Length":ship["Length"],
            "Draft":ship["Draft"],
            "Speed":ship["Speed"],
            "Heading":ship["Heading"],
            "position":get_latest_position(ship),
            "track":ship["track"]
        },

        "risk":risk,

        "gemma_reasoning":gemma_response

    })

@app.route("/api/ais-status")
def api_ais_status():
    return jsonify(ais_feed.get_status())



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

@app.route("/monitor")
def monitor():
    return render_template("alert_monitor.html")


@app.route("/api/gemma")
def api_gemma():

    # take first vessel for demo
    ship = ships[0]

    risk = calculate_risk(ship)

    report = generate_vessel_reasoning(
        ship,
        risk
    )

    alert = "no"

    if risk["level"] in ["High", "Critical"]:
        alert = "yes"


    return jsonify({
        "alert": alert,
        "risk": risk,
        "report": report
    })
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
