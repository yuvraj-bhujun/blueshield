from flask import Flask, render_template, jsonify, request, redirect, url_for
from extensions import db, migrate
from config import Config
import services.ais_feed as ais_feed
import services.ais_updater as ais_updater
from services.risk_engine import calculate_risk
from services.gemma_engine import generate_vessel_reasoning
from services.data_loader import get_ship, get_latest_position
from services.classifiers import classify_report
from models import Incident, CoralSample

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
migrate.init_app(app, db)

# Start AIS background threads (optional – comment out if not using)
# ais_feed.start()
# ais_updater.start_ais_updater()

# ----------------------------------------------------------------------
# DEMO DATA
# ----------------------------------------------------------------------

DUMMY_VESSELS = [
    {
        "id": "SIM-001",
        "name": "MV Ocean Trader",
        "lat": -20.30,
        "lng": 57.50,
        "speed": 14.2,
        "heading": 245,
        "type": "Cargo",
        "cargo": "Containers",
        "risk": {"score": 65, "level": "Medium"},
        "source": "simulated",
        "in_eez": True,
        "mmsi": "636019876"
    },
    {
        "id": "SIM-002",
        "name": "MV Coral Express",
        "lat": -20.45,
        "lng": 57.75,
        "speed": 8.5,
        "heading": 190,
        "type": "Bulk Carrier",
        "cargo": "Coal",
        "risk": {"score": 82, "level": "High"},
        "source": "simulated",
        "in_eez": True,
        "mmsi": "538009876"
    },
    {
        "id": "SIM-003",
        "name": "Reef Guardian",
        "lat": -20.40,
        "lng": 57.60,
        "speed": 5.0,
        "heading": 120,
        "type": "Research",
        "cargo": "Equipment",
        "risk": {"score": 25, "level": "Low"},
        "source": "simulated",
        "in_eez": True,
        "mmsi": "205987654"
    }
]

REEFS = [
    {"id": "reef-blue-bay", "name": "Blue Bay Reef", "lat": -20.446, "lng": 57.713, "health": 91},
    {"id": "reef-pointe-esny", "name": "Pointe d'Esny Reef", "lat": -20.430, "lng": 57.734, "health": 74}
]
MPAS = [
    {"id": "mpa-blue-bay", "name": "Blue Bay Marine Park", "lat": -20.446, "lng": 57.713, "radius_km": 3.2}
]

INCIDENTS = [
    {"id": "INC-1042", "type": "Oil Spill", "lat": -20.430, "lng": 57.734, "confidence": 91,
     "authority": "National Coast Guard", "status": "Under Review",
     "reported_at": "2026-07-29T10:00:00", "description": "Sheen visible near Pointe d'Esny"}
]

# ----------------------------------------------------------------------
# PAGE ROUTES – all pages referenced in the templates
# ----------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/coastguard")
def coastguard_page():
    return render_template("coastguard.html")

@app.route("/map")
def map_page():
    return render_template("map.html")

@app.route("/report")
def report_page():
    # Stub – you can later create report.html
    return "<h1>Report Page (coming soon)</h1><p><a href='/'>Back to home</a></p>"

@app.route("/ngo")
def ngo_page():
    # Stub – you can later create ngo.html
    return "<h1>NGO Portal (coming soon)</h1><p><a href='/'>Back to home</a></p>"

@app.route("/wakashio")
def wakashio_page():
    # Stub – you can later create wakashio.html
    return "<h1>Wakashio Replay (coming soon)</h1><p><a href='/'>Back to home</a></p>"

# ----------------------------------------------------------------------
# API ROUTES (Coast Guard needs these)
# ----------------------------------------------------------------------

@app.route("/api/vessels")
def api_vessels():
    vessels = DUMMY_VESSELS
    return jsonify({
        "vessels": vessels,
        "ais_status": {"connected": True, "vessel_count": len(vessels)}
    })

@app.route("/api/reefs")
def api_reefs():
    return jsonify({"reefs": REEFS, "mpas": MPAS})

@app.route("/api/incidents")
def api_incidents():
    return jsonify({"incidents": INCIDENTS})

@app.route("/api/vessel/<mmsi>")
def vessel_detail(mmsi):
    vessel = next((v for v in DUMMY_VESSELS if v["mmsi"] == mmsi), None)
    if not vessel:
        return jsonify({"error": "Vessel not found"}), 404

    risk = {
        "score": vessel["risk"]["score"],
        "level": vessel["risk"]["level"],
        "current_distance": 4.2,
        "trend": "Approaching",
        "closing_speed": 2.5,
        "eta": 1.8,
        "lane_deviation": 6.3,
        "inside_reef": False
    }
    gemma_response = f"AI analysis for {vessel['name']}: Currently holding course at {vessel['speed']} knots. Risk level {risk['level']} due to proximity to reef ({risk['current_distance']} km) and lane deviation."

    return jsonify({
        "vessel": {
            "MMSI": vessel["mmsi"],
            "VesselName": vessel["name"],
            "VesselType": vessel["type"],
            "Cargo": vessel["cargo"],
            "Speed": vessel["speed"],
            "Heading": vessel["heading"],
            "Destination": "Port Louis",
            "Flag": "Mauritius",
            "Draft": 10,
            "Length": 200,
            "track": [{"lat": vessel["lat"], "lon": vessel["lng"]}]
        },
        "risk": risk,
        "gemma_reasoning": gemma_response
    })

@app.route("/api/ais-status")
def api_ais_status():
    return jsonify({"configured": True, "connected": True, "vessel_count": len(DUMMY_VESSELS)})

# ----------------------------------------------------------------------
# RUN
# ----------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)