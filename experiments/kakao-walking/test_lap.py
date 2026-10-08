"""Adversarial synthetic rings; no real coordinates or provider responses."""
import unittest

from probe import inside
from validate_lap import inspect_lap


def points(values):
    return [(127 + x / 100000, 37 + y / 100000) for x, y in values]


class LapTests(unittest.TestCase):
    ring = points([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    water = points([(2, 2), (8, 2), (8, 8), (2, 8)])

    def test_clockwise_and_counterclockwise_only_pass_geometry(self):
        for ring in (self.ring, list(reversed(self.ring))):
            result = inspect_lap([ring], self.water)
            self.assertEqual("PASS_GEOMETRY_ONLY", result["status"])
            self.assertIn("CURRENT_ACCESS_UNVERIFIED", result["scope"])

    def test_step_partition_does_not_change_ring(self):
        self.assertEqual("PASS_GEOMETRY_ONLY", inspect_lap([self.ring[:3], self.ring[2:]], self.water)["status"])

    def test_sub_metre_step_gap_is_not_bridged(self):
        second = [(self.ring[2][0] + 0.000001, self.ring[2][1]), *self.ring[3:]]
        result = inspect_lap([self.ring[:3], second], self.water)
        self.assertIn("LAP_DISCONNECTED_GEOMETRY", result["unresolved"])
        self.assertGreater(result["step_join_mismatches"][0]["gap_m"], 0)
        self.assertLess(result["step_join_mismatches"][0]["gap_m"], 1)

    def test_floating_point_endpoint_difference_is_reported_without_changing_source_route(self):
        second = [(self.ring[2][0] + 1e-12, self.ring[2][1]), *self.ring[3:]]
        original = list(second)
        result = inspect_lap([self.ring[:3], second], self.water)
        self.assertGreater(result["step_join_mismatches"][0]["gap_m"], 0)
        self.assertLess(result["step_join_mismatches"][0]["gap_m"], 0.001)
        self.assertEqual("PASS_GEOMETRY_ONLY", result["status"])
        self.assertEqual(1, result["numeric_join_equivalence_count"])
        self.assertEqual(original, second)

    def test_sub_metre_endpoint_gap_is_not_closed(self):
        ring = self.ring[:-1] + [(self.ring[0][0] + 0.000001, self.ring[0][1])]
        self.assertIn("LAP_OPEN_GEOMETRY", inspect_lap([ring], self.water)["unresolved"])

    def test_difference_above_one_millimetre_still_blocks_geometry_analysis(self):
        second = [(self.ring[2][0] + 2e-8, self.ring[2][1]), *self.ring[3:]]
        result = inspect_lap([self.ring[:3], second], self.water)
        self.assertGreater(result["step_join_mismatches"][0]["gap_m"], 0.001)
        self.assertIn("LAP_DISCONNECTED_GEOMETRY", result["unresolved"])

    def test_closed_out_and_back_is_not_a_lap(self):
        self.assertEqual("FAIL", inspect_lap([[self.ring[0], self.ring[1], self.ring[0]]], self.water)["status"])

    def test_two_laps_are_never_a_single_ring_pass(self):
        self.assertIn("LAP_NON_SIMPLE_GEOMETRY", inspect_lap([self.ring + self.ring[1:]], self.water)["unresolved"])

    def test_access_stem_needs_review_instead_of_silent_ring_repair(self):
        stem = points([(-2, 0)])[0]
        self.assertIn("LAP_NON_SIMPLE_GEOMETRY", inspect_lap([[stem, *self.ring, stem]], self.water)["unresolved"])

    def test_self_crossing_route_never_passes(self):
        ring = points([(0, 0), (10, 10), (0, 10), (10, 0), (0, 0)])
        self.assertIn("LAP_NON_SIMPLE_GEOMETRY", inspect_lap([ring], self.water)["unresolved"])

    def test_boundary_edges_crossing_a_thin_notch_are_detected(self):
        ring = points([(0, 0), (10, 0), (10, 10), (6.2, 10), (6.2, 2), (6, 2), (6, 10), (0, 10), (0, 0)])
        water = points([(1, 7), (9, 7), (9, 8), (1, 8)])
        checks = water + [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(water, water[1:] + water[:1])]
        self.assertTrue(all(inside(p, ring) for p in checks))
        result = inspect_lap([ring], water)
        self.assertEqual(0, result["outside_water_vertex_count"])
        self.assertGreater(result["crossing_water_edge_count"], 0)
        self.assertIn("TARGET_WATER_NOT_ENCLOSED", result["failures"])

    def test_outside_water_is_rejected(self):
        self.assertIn("TARGET_WATER_NOT_ENCLOSED", inspect_lap([self.ring], points([(9, 9), (12, 9), (12, 12), (9, 12)]))["failures"])

    def test_coincident_shoreline_requires_boundary_accuracy_review(self):
        self.assertIn("TARGET_WATER_BOUNDARY_CONTACT_REQUIRES_REVIEW", inspect_lap([self.ring], self.ring)["unresolved"])

    def test_invalid_water_ring_stays_unknown(self):
        water = points([(2, 2), (8, 8), (2, 8), (8, 2)])
        self.assertIn("TARGET_WATER_INVALID_GEOMETRY", inspect_lap([self.ring], water)["unresolved"])


if __name__ == "__main__":
    unittest.main()
