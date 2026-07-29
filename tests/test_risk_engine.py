import unittest

from risk_engine import enrich_ship_with_risk


class RiskEngineTests(unittest.TestCase):
    def test_enrich_ship_with_risk_keeps_original_data_and_adds_analysis(self):
        ship = {
            "vessel_name": "Test Vessel",
            "mmsi": 123456789,
            "cargo": "Container",
            "draft": 8.5,
            "track": [
                {"lat": -19.0, "lon": 58.0, "time": "2026-07-28T00:00:00Z"},
                {"lat": -19.2, "lon": 57.9, "time": "2026-07-28T01:00:00Z"},
            ],
        }

        enriched = enrich_ship_with_risk(ship)

        self.assertEqual(enriched["vessel_name"], "Test Vessel")
        self.assertEqual(enriched["mmsi"], 123456789)
        self.assertIn("reef_analysis", enriched)
        self.assertIn("closest_reef_distance_km", enriched["reef_analysis"])
        self.assertIn("reef_trend", enriched["reef_analysis"])
        self.assertEqual(enriched["track"], ship["track"])


if __name__ == "__main__":
    unittest.main()
