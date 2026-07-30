"""
data_loader.py

Loads all datasets required by BlueShield AI.

Datasets are loaded once when Flask starts so they do not need to
be re-read for every API request.

NOTE: paths are relative to this file's directory (the blueshield-ai/
project root), so the app runs on any machine as long as ships.json,
reefextent.gpkg and benthic.gpkg ship alongside the code — no more
hardcoded C:\\Users\\... paths.
"""

import json
from pathlib import Path

import geopandas as gpd

# ==========================================================
# DATASET PATHS
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent

SHIPS_PATH = BASE_DIR / "static" / "data" / "ships.json"
REEF_EXTENT_PATH = BASE_DIR / "reefextent.gpkg"
BENTHIC_PATH = BASE_DIR / "benthic.gpkg"


# ==========================================================
# LOAD SHIPS (historical / demo track data)
# ==========================================================

print("Loading ships...")

with open(SHIPS_PATH, "r", encoding="utf-8") as f:
    SHIPS = json.load(f)

print(f"{len(SHIPS)} ships loaded.")


# ==========================================================
# LOAD REEF EXTENT
# ==========================================================

print("Loading reef extent...")

reef_gdf = gpd.read_file(REEF_EXTENT_PATH)
reef_gdf = reef_gdf.to_crs(4326)

# Metric CRS for accurate distance calculations
reef_metric = reef_gdf.to_crs(32740)

# Merge all reef polygons into one geometry
reef_union = reef_metric.geometry.unary_union

print(f"{len(reef_gdf)} reef polygons loaded.")


# ==========================================================
# LOAD BENTHIC MAP
# ==========================================================

print("Loading benthic map...")

benthic_gdf = gpd.read_file(BENTHIC_PATH)
benthic_gdf = benthic_gdf.to_crs(4326)

print(f"{len(benthic_gdf)} benthic polygons loaded.")


# ==========================================================
# HELPER FUNCTIONS
# ==========================================================

def get_ship(mmsi):
    """Returns a demo/historical ship record by MMSI (static/data/ships.json)."""

    for ship in SHIPS:
        if str(ship.get("MMSI", ship.get("mmsi"))) == str(mmsi):
            return ship

    return None


def get_latest_position(ship):
    return ship["track"][-1]


def get_last_positions(ship, n=5):
    return ship["track"][-n:]
