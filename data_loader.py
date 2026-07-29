"""
data_loader.py

Loads all datasets required by BlueShield AI.

Datasets are loaded once when Flask starts so they do not need to
be re-read for every API request.
"""

import geopandas as gpd

# ==========================================================
# DATASET PATHS
# ==========================================================

SHIPS_PATH = "static/data/ships.json"

REEF_EXTENT_PATH = "reefextent.gpkg"
BENTHIC_PATH = "benthic.gpkg"


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
    """
    Returns a ship by MMSI.
    """
    return None


def get_latest_position(ship):

    return ship["track"][-1]


def get_last_positions(ship, n=5):

    return ship["track"][-n:]