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
# TESTING MODE
# Flip this back to False to restore the real 40/60/80
# thresholds below. While True, ANY score above 1 counts as
# "High" so it's easy to demo the alarm end-to-end.
# ==========================================================
TESTING_MODE = False

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

    speed = ship["Speed"]

    if speed <= 0:

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

def calculate_risk(ship):

    latest = ship["track"][-1]

    current_distance = reef_distance(
        latest["lat"],
        latest["lon"]
    )

    history = reef_distance_history(ship)

    trend = reef_trend(history)

    deviation = lane_deviation(
        latest["lat"],
        latest["lon"]
    )

    score = 0

    # ------------------------------------------------------

    if current_distance < 0.5:

        score += 50

    elif current_distance < 2:

        score += 40

    elif current_distance < 5:

        score += 25

    elif current_distance < 10:

        score += 15

    # ------------------------------------------------------

    if trend == "Approaching":

        score += 20

    # ------------------------------------------------------

    cargo = ship["Cargo"].lower()

    if "oil" in cargo:

        score += 15

    elif "coal" in cargo:

        score += 10

    elif "container" in cargo:

        score += 5

    # ------------------------------------------------------

    if ship["Draft"] > 12:

        score += 5

    # ------------------------------------------------------

    if deviation > 10:

        score += 10

    elif deviation > 5:

        score += 5

    # ------------------------------------------------------

    score = min(score, 100)

    if TESTING_MODE:

        # Demo/testing thresholds — anything above 1 trips "High" so the
        # alarm is easy to trigger. Set TESTING_MODE = False above to
        # restore the real thresholds below.
        if score > 1:

            level = "High"

        else:

            level = "Low"

    elif score >= 80:

        level = "Critical"

    elif score >= 60:

        level = "High"

    elif score >= 40:

        level = "Medium"

    else:

        level = "Low"

    return {

        "score": score,

        "level": level,

        "current_distance": round(current_distance, 2),

        "history": history,

        "trend": trend,

        "closing_speed": closing_speed(history),

        "eta": eta_to_reef(ship),

        "lane_deviation": deviation,

        "inside_reef": inside_reef(
            latest["lat"],
            latest["lon"]
        )

    }


# ==========================================================
# Ship-to-Ship Collision Risk
#
# Computes, for every pair of vessels currently on the live map,
# their Closest Point of Approach (CPA) — the smallest distance
# they will come to each other if both hold their current speed
# and heading — and the Time to CPA (TCPA). These two numbers are
# the standard maritime collision-avoidance metrics (same idea used
# by real ARPA/AIS collision-alarm systems on a ship's bridge).
#
# Each vessel is then given the risk of its single most dangerous
# encounter with any other vessel in the fleet, so the live map can
# colour/flag it accordingly.
# ==========================================================

EARTH_RADIUS_KM = 6371.0

# AIS uses 511 as "heading not available" — never treat it as a real bearing.
INVALID_HEADING = 511


def _latlng_to_local_xy_km(lat, lng, ref_lat, ref_lng):
    """Small-area equirectangular projection -> local (x=east, y=north) km."""

    x = math.radians(lng - ref_lng) * EARTH_RADIUS_KM * math.cos(math.radians(ref_lat))
    y = math.radians(lat - ref_lat) * EARTH_RADIUS_KM

    return x, y


def _velocity_vector_kmh(speed_knots, heading_deg):
    """Speed (knots) + heading (deg, 0=N clockwise) -> (vx, vy) in km/h."""

    speed_knots = speed_knots or 0

    # Near-stationary vessels (anchored/moored) or vessels broadcasting an
    # invalid AIS heading sentinel are treated as having no reliable
    # velocity vector, rather than risking a bogus heading skewing the CPA.
    if speed_knots < 0.2 or heading_deg is None or heading_deg >= INVALID_HEADING:
        return 0.0, 0.0

    speed_kmh = speed_knots * 1.852
    rad = math.radians(heading_deg % 360)

    vx = speed_kmh * math.sin(rad)
    vy = speed_kmh * math.cos(rad)

    return vx, vy


def compute_cpa(vessel_a, vessel_b):
    """
    Closest Point of Approach between two vessels.

    Each vessel is a dict with "lat", "lng", "speed" (knots) and
    "heading" (degrees). Returns (cpa_km, tcpa_hours):
      - cpa_km: the distance apart the two vessels will be at CPA
      - tcpa_hours: hours until that happens, or None if the vessels
        are not on a converging course (already moving apart)
    """

    ref_lat = (vessel_a["lat"] + vessel_b["lat"]) / 2
    ref_lng = (vessel_a["lng"] + vessel_b["lng"]) / 2

    ax, ay = _latlng_to_local_xy_km(vessel_a["lat"], vessel_a["lng"], ref_lat, ref_lng)
    bx, by = _latlng_to_local_xy_km(vessel_b["lat"], vessel_b["lng"], ref_lat, ref_lng)

    avx, avy = _velocity_vector_kmh(vessel_a.get("speed"), vessel_a.get("heading"))
    bvx, bvy = _velocity_vector_kmh(vessel_b.get("speed"), vessel_b.get("heading"))

    # Position and velocity of B relative to A.
    rx, ry = bx - ax, by - ay
    rvx, rvy = bvx - avx, bvy - avy

    current_distance_km = math.hypot(rx, ry)
    rel_speed_sq = rvx ** 2 + rvy ** 2

    if rel_speed_sq < 1e-6:
        # Both vessels effectively stationary relative to each other —
        # the gap between them isn't closing.
        return round(current_distance_km, 3), None

    tcpa_hours = -(rx * rvx + ry * rvy) / rel_speed_sq

    if tcpa_hours < 0:
        # CPA already happened — they're now diverging.
        return round(current_distance_km, 3), None

    cpa_x = rx + rvx * tcpa_hours
    cpa_y = ry + rvy * tcpa_hours
    cpa_km = math.hypot(cpa_x, cpa_y)

    return round(cpa_km, 3), round(tcpa_hours, 3)


def collision_risk_score(cpa_km, tcpa_hours):
    """Translate a CPA distance + time-to-CPA into a 0-100 risk score."""

    if tcpa_hours is None or tcpa_hours > 6:
        # Not on a converging course, or the encounter is too far in the
        # future to be actionable right now.
        return 0

    if cpa_km < 0.3:
        distance_score = 95
    elif cpa_km < 0.5:
        distance_score = 85
    elif cpa_km < 1.0:
        distance_score = 65
    elif cpa_km < 2.0:
        distance_score = 45
    elif cpa_km < 4.0:
        distance_score = 25
    elif cpa_km < 8.0:
        distance_score = 10
    else:
        distance_score = 0

    if tcpa_hours < 0.25:
        urgency = 1.0
    elif tcpa_hours < 1.0:
        urgency = 0.9
    elif tcpa_hours < 2.0:
        urgency = 0.75
    elif tcpa_hours < 4.0:
        urgency = 0.55
    else:
        urgency = 0.35

    return max(0, min(100, round(distance_score * urgency)))


def _collision_level(score):

    if score >= 70:
        return "High"

    if score >= 35:
        return "Medium"

    return "Low"


def calculate_collision_risk(vessel, other_vessels):
    """
    Collision risk for a single vessel against every other vessel
    currently on the map. Returns the vessel's single worst (highest
    score) encounter.

    "vessel" and each entry in "other_vessels" are dicts with at least
    "id", "lat", "lng", "speed" (knots) and "heading" (degrees).
    """

    best = {
        "score": 0,
        "level": "Low",
        "cpa_km": None,
        "tcpa_minutes": None,
        "target_id": None,
        "target_name": None,
    }

    for other in other_vessels:

        if other.get("id") == vessel.get("id"):
            continue

        cpa_km, tcpa_hours = compute_cpa(vessel, other)
        score = collision_risk_score(cpa_km, tcpa_hours)

        if score > best["score"]:
            best = {
                "score": score,
                "level": _collision_level(score),
                "cpa_km": cpa_km,
                "tcpa_minutes": round(tcpa_hours * 60, 1) if tcpa_hours is not None else None,
                "target_id": other.get("id"),
                "target_name": other.get("name"),
            }

    return best


def calculate_fleet_collision_risk(vessels):
    """
    Runs calculate_collision_risk() for every vessel against the rest
    of the fleet. Returns {vessel_id: risk_dict}, ready to be merged
    into the /api/vessels response for the live map.
    """

    return {
        v["id"]: calculate_collision_risk(v, vessels)
        for v in vessels
    }