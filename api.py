"""
api.py

All Flask API endpoints.
"""

from flask import jsonify, request

from app import app

from data_loader import (
    SHIPS,
    get_ship,
    get_latest_position,
    reef_gdf,
    benthic_gdf
)

from risk_engine import (
    calculate_risk
)


@app.route("/api/coral")
def coral():

    return jsonify(
        benthic_gdf[
            benthic_gdf["class"] == "Coral/Algae"
        ].__geo_interface__
    )

@app.route("/api/reef_extent")
def reef_extent():

    return jsonify(
        reef_gdf.__geo_interface__
    )