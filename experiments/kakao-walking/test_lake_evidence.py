"""Synthetic source comparisons: never network calls or field access proof."""
import copy
import unittest

from lake_evidence import inspect_water_overlap


class WaterEvidenceTests(unittest.TestCase):
    water = [(127, 37), (127.001, 37), (127.001, 37.001), (127, 37.001)]
    crossing = [(126.9999, 37.0005), (127.0011, 37.0005)]

    def source(self, tags=None):
        return {"osm": {"elements": [{"type": "way", "id": 1,
            "tags": tags or {"highway": "footway", "bridge": "yes"},
            "geometry": [{"lon": x, "lat": y} for x, y in self.crossing]}]}}

    def test_inside_water_without_source_keeps_bridge_unknown(self):
        result = inspect_water_overlap([self.crossing], self.water)
        self.assertEqual("REVIEW_REQUIRED", result["status"])
        self.assertFalse(result["bridge_source_available"])
        self.assertGreater(result["inside_source_water_samples"], 0)
        self.assertGreater(result["max_inside_offset_m"], 0)
        self.assertEqual(1, result["steps"][0]["step"])
        self.assertIn("WATER_CROSSING_REQUIRES_BRIDGE_CHECK", result["unresolved"])

    def test_matching_source_bridge_does_not_approve_water_crossing(self):
        paths, source = [self.crossing], self.source()
        original = copy.deepcopy((paths, source))
        result = inspect_water_overlap(paths, self.water, source)
        self.assertEqual(result["inside_source_water_samples"], result["near_source_bridge_samples"])
        self.assertIn("CURRENT_ACCESS_UNVERIFIED", result["bridge_evidence"])
        self.assertEqual("REVIEW_REQUIRED", result["status"])
        self.assertEqual(["WATER_CROSSING_REQUIRES_BRIDGE_CHECK"], result["unresolved"])
        self.assertEqual(original, (paths, source))

    def test_prohibited_bridge_is_not_walking_bridge_evidence(self):
        for restriction in ({"foot": "no"}, {"access": "private"}):
            with self.subTest(restriction=restriction):
                source = self.source({"highway": "footway", "bridge": "yes", **restriction})
                result = inspect_water_overlap([self.crossing], self.water, source)
                self.assertEqual(0, result["near_source_bridge_samples"])
                self.assertEqual("REVIEW_REQUIRED", result["status"])

    def test_absent_bridge_and_absent_source_are_distinct(self):
        result = inspect_water_overlap([self.crossing], self.water, {"osm": {"elements": []}})
        self.assertTrue(result["bridge_source_available"])
        self.assertEqual(0, result["near_source_bridge_samples"])

    def test_outside_water_means_no_sampled_overlap_only(self):
        path = [(127, 36.999), (127.001, 36.999)]
        result = inspect_water_overlap([path], self.water)
        self.assertEqual("NO_SAMPLED_OVERLAP", result["status"])
        self.assertEqual([], result["unresolved"])
        self.assertEqual(0, result["inside_source_water_samples"])
        self.assertIn("NOT_FIELD_OBSERVATION", result["scope"])

    def test_missing_boundary_is_not_reported_as_no_overlap(self):
        result = inspect_water_overlap([self.crossing], [])
        self.assertEqual("NOT_EVALUATED", result["status"])
        self.assertNotIn("inside_source_water_samples", result)

    def test_edge_limit_returns_unknown_without_partial_counts(self):
        result = inspect_water_overlap([self.crossing], self.water * 1251)
        self.assertEqual(["WATER_OVERLAP_ANALYSIS_LIMIT_REACHED"], result["unresolved"])
        self.assertNotIn("inside_source_water_samples", result)

    def test_work_limit_does_not_misreport_partial_check_as_complete(self):
        result = inspect_water_overlap([self.crossing] * 51, self.water * 1000)
        self.assertEqual("NOT_EVALUATED", result["status"])
        self.assertEqual(["WATER_OVERLAP_ANALYSIS_LIMIT_REACHED"], result["unresolved"])
        self.assertNotIn("inside_source_water_samples", result)


if __name__ == "__main__":
    unittest.main()
