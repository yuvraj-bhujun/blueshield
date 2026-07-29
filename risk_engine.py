"""
risk_engine.py

All geospatial calculations for BlueShield AI.
"""

import math
import geopandas as gpd
from shapely.geometry import Point, LineString

from data_loader import (
    reef_union,
    reef_metric,
    get_last_positions
)

# ==========================================================
# CRS
# ==========================================================

METRIC_CRS = "EPSG:32740"

# ==========================================================
# SHIPPING LANE
# (Replace later with a real shipping lane dataset)
# ==========================================================

shipping_lane = LineString([
    (57.20, -19.80),
    (57.45, -20.00),
    (57.75, -20.15),
    (58.00, -20.35),
    (58.25, -20.55)
])

shipping_lane = (
    gpd.GeoSeries(
        [shipping_lane],
        crs="EPSG:4326"
    )
    .to_crs(METRIC_CRS)
    .iloc[0]
)

# ==========================================================
# Point conversion
# ==========================================================

def point_to_metric(lat, lon):

    point = (
        gpd.GeoSeries(
            [Point(lon, lat)],
            crs="EPSG:4326"
        )
        .to_crs(METRIC_CRS)
        .iloc[0]
    )

    return point


# ==========================================================
# Current reef distance
# ==========================================================

def reef_distance(lat, lon):

    point = point_to_metric(lat, lon)

    distance = point.distance(reef_union)

    return distance / 1000


# ==========================================================
# Is vessel inside reef?
# ==========================================================

def inside_reef(lat, lon):

    point = point_to_metric(lat, lon)

    return reef_union.contains(point)


# ==========================================================
# Reef distance history
# ==========================================================

def reef_distance_history(ship):

    history = []

    for p in get_last_positions(ship):

        d = reef_distance(
            p["lat"],
            p["lon"]
        )

        history.append(round(d, 3))

    return history


# ==========================================================
# Trend
# ==========================================================

def reef_trend(history):

    if len(history) < 2:

        return "Unknown"

    if history[-1] < history[0]:

        return "Approaching"

    if history[-1] > history[0]:

        return "Moving Away"

    return "Stable"


# ==========================================================
# Closing speed
# ==========================================================

def closing_speed(history):

    if len(history) < 2:

        return 0

    total = history[0] - history[-1]

    hours = len(history) - 1

    return round(total / hours, 2)


# ==========================================================
# ETA
# ==========================================================

def eta_to_reef(ship):

    history = reef_distance_history(ship)

    trend = reef_trend(history)

    if trend != "Approaching":

        return None

    latest = history[-1]

    speed = ship.get("Speed", ship.get("speed"))

    if speed is None or speed <= 0:

        return None

    eta = latest / (speed * 1.852)

    return round(eta, 2)


# ==========================================================
# Shipping lane deviation
# ==========================================================

def lane_deviation(lat, lon):

    point = point_to_metric(lat, lon)

    distance = point.distance(shipping_lane)

    return round(distance / 1000, 2)


# ==========================================================
# Risk Score
# ==========================================================

def enrich_ship_with_risk(ship):
    """Return a ship payload that preserves the original data and adds reef-focused analysis."""
    latest = ship["track"][-1]

    current_distance = reef_distance(latest["lat"], latest["lon"])
    history = reef_distance_history(ship)
    trend = reef_trend(history)

    enriched = dict(ship)
    enriched["reef_analysis"] = {
        "closest_reef_distance_km": round(current_distance, 2),
        "reef_history_km": history,
        "reef_trend": trend,
        "closing_speed_km_per_hour": closing_speed(history),
        "eta_hours_to_reef": eta_to_reef(ship),
    }
    return enriched


# The old calculate_risk function has been removed.
# The vessel flow now uses enrich_ship_with_risk() and sends the enriched
# payload directly to the Gemma model for collision-risk prediction.