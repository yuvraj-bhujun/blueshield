import geopandas as gpd
from shapely.geometry import Point



class ReefEngine:
    """
    Reef proximity engine.

    Usage:
        reef = ReefEngine("reefextent.gpkg")
        new_data = reef.process(ais_json)
    """

    def __init__(self, reef_file: str):

        # Load reef polygons
        self.reefs = gpd.read_file(reef_file)

        if self.reefs.empty:
            raise ValueError("reefextent.gpkg contains no geometries.")

        # Remember original CRS
        if self.reefs.crs is None:
            raise ValueError("reefextent.gpkg has no CRS defined.")

        # Project to metres
        self.reefs = self.reefs.to_crs(epsg=3857)

        # Spatial index
        self.sindex = self.reefs.sindex

    def _distance_to_nearest_reef(self, lat, lon):

    # Ship point
        point = gpd.GeoSeries(
            [Point(lon, lat)],
            crs="EPSG:4326"
        ).to_crs(epsg=3857).iloc[0]


    # Find nearest reef
        nearest = self.sindex.nearest(point)

    # Convert numpy result into integer index
        reef_idx = int(nearest[1][0])


        reef_geom = self.reefs.iloc[reef_idx].geometry

        distance_m = point.distance(reef_geom)

        return round(distance_m / 1000, 3), reef_idx

    def process(self, ais_json):
        """
        Appends nearest reef information.

        Input:
            AIS API dictionary

        Output:
            Same dictionary with added fields
        """

        if "data" not in ais_json:
            return ais_json

        for vessel in ais_json["data"]:

            lat = vessel.get("lat")
            lon = vessel.get("lng")

            if lat is None or lon is None:
                vessel["nearest_reef_distance_km"] = None
                vessel["nearest_reef_id"] = None
                continue

            try:
                distance, reef_id = self._distance_to_nearest_reef(lat, lon)

                vessel["nearest_reef_distance_km"] = distance
                vessel["nearest_reef_id"] = reef_id

    # Calculate time until reaching reef
                speed = vessel.get("speed", 0)

                if speed > 0:
                    vessel["time_to_reef_minutes"] = round((distance / (speed * 1.852)) * 60,1)
                else:
                    vessel["time_to_reef_minutes"] = None

            except Exception as e:
                print("REEF ERROR:", e)
                vessel["nearest_reef_distance_km"] = None
                vessel["nearest_reef_id"] = None
                vessel["time_to_reef_minutes"] = None

        return ais_json


if __name__ == "__main__":

    reef = ReefEngine("reefextent.gpkg")

    sample = {
        "status": "success",
        "duration": "0.004818390",
        "timestamp": "2026-07-28T18:53:11.979Z",
        "data": [
            {
                "vessel_name": "HABSHAN",
                "mmsi": 636021544,
                "imo": 9928011,
                "vtype": 8,
                "lat": -20.14716,
                "lng": 57.25835,
                "course": 265.1,
                "speed": 14.1,
                "nav_status": 0,
                "received": "2026-07-28T18:52:43Z"
            },
            {
                "vessel_name": "MARIGOULA",
                "mmsi": 538005001,
                "imo": 9617662,
                "vtype": 7,
                "lat": -20.16426,
                "lng": 57.42173,
                "course": 307.3,
                "speed": 5.5,
                "nav_status": 1,
                "received": "2026-07-28T18:51:42Z"
            }
        ]
    }

    result = reef.process(sample)

    from pprint import pprint
    pprint(result)