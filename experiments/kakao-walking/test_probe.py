"""Synthetic safety regressions only. No network calls or real course evidence."""
import copy
import unittest
from pathlib import Path

from probe import Client, cases, inspect, lake_topology_diagnostics, load_site, meters, ordered_visits, point, repeated_edge_diagnostics, source_ok


def response(paths):
    legs = []
    for path in paths:
        length = sum(meters(a, b) for a, b in zip(path, path[1:]))
        legs.append({"properties": {"distance": length, "time": length},
                     "steps": [{"path": {"points": path}}]})
    return {"status": "OK", "route": {"properties": {
        "totalDistance": sum(leg["properties"]["distance"] for leg in legs),
        "totalTime": sum(leg["properties"]["time"] for leg in legs)}, "legs": legs}}


class GeometrySafetyTests(unittest.TestCase):
    # Deliberately synthetic boxes, not coordinates of a park or a walking course.
    loop = [(127.0, 37.0), (127.002, 37.0), (127.002, 37.002),
            (127.0, 37.002), (127.0, 37.0)]
    water = [(127.0005, 37.0005), (127.0015, 37.0005),
             (127.0015, 37.0015), (127.0005, 37.0015)]

    def test_same_point_is_not_a_successful_loop(self):
        result = inspect({"status": "SAME_POINT"}, self.loop[0], self.loop[0], "lake_loop")
        self.assertEqual("NOT_EVALUATED", result["geometry_check"])

    def test_reversed_waypoints_on_one_long_segment_do_not_pass(self):
        self.assertFalse(ordered_visits([(self.loop[0], self.loop[1])],
                                        [self.loop[1], self.loop[0]]))

    def test_real_return_segment_can_visit_points_in_reverse_direction(self):
        self.assertTrue(ordered_visits([(self.loop[0], self.loop[1]), (self.loop[1], self.loop[0])],
                                       [self.loop[1], self.loop[0]]))

    def test_out_and_back_has_no_water_winding(self):
        path = [self.loop[0], self.loop[1], self.loop[0]]
        diagnostics = lake_topology_diagnostics(path, self.water)
        self.assertEqual({"0": diagnostics["lake_water_grid_samples"]}, diagnostics["lake_water_grid_winding_counts"])

    def test_two_laps_are_distinct_from_one_lap(self):
        path = self.loop + self.loop[1:]
        diagnostics = lake_topology_diagnostics(path, self.water)
        self.assertEqual({"2": diagnostics["lake_water_grid_samples"]}, diagnostics["lake_water_grid_winding_counts"])

    def test_open_path_is_not_closed_for_topology_sampling(self):
        diagnostics = lake_topology_diagnostics(self.loop[:-1], self.water)
        self.assertEqual("NOT_EVALUATED_OPEN_GEOMETRY", diagnostics["lake_topology_sampling"])

    def test_reversed_traversal_counts_as_repetition(self):
        diagnostics = repeated_edge_diagnostics([self.loop[:2], list(reversed(self.loop[:2]))])
        self.assertEqual(0.5, diagnostics["exact_edge_retraced_fraction"])

    def test_step_gap_does_not_create_a_repeated_edge(self):
        diagnostics = repeated_edge_diagnostics([self.loop[:2], self.loop[2:4]])
        self.assertEqual(0, diagnostics["exact_edge_retraced_fraction"])

    def test_http_success_without_geometry_is_rejected(self):
        result = inspect({"status": "OK", "route": {}}, self.loop[0], self.loop[0])
        self.assertIn("INVALID_RESPONSE_SCHEMA", result["failures"])

    def test_disconnected_steps_are_not_joined_into_a_route(self):
        first, second = self.loop[:2], self.loop[2:4]
        result = inspect(response([first, second]), first[0], second[-1])
        self.assertIn("DISCONNECTED_STEPS", result["failures"])

    def test_missing_geometry_in_one_step_is_rejected(self):
        payload = response([self.loop])
        payload["route"]["legs"][0]["steps"].append({"path": {"points": []}})
        result = inspect(payload, self.loop[0], self.loop[0])
        self.assertEqual("FAIL", result["geometry_check"])

    def test_distance_claim_disagrees_with_line(self):
        payload = response([self.loop])
        payload["route"]["properties"]["totalDistance"] = 5000
        result = inspect(payload, self.loop[0], self.loop[0])
        self.assertIn("GEOMETRY_DISTANCE_MISMATCH", result["failures"])

    def test_closed_out_and_back_is_not_a_lake_lap(self):
        path = [self.loop[0], self.loop[1], self.loop[0]]
        result = inspect(response([path]), path[0], path[-1], "lake_loop", self.loop, self.water)
        self.assertIn("LAP_DEGENERATE_GEOMETRY", result["failures"])

    def test_small_step_gap_does_not_get_an_invented_enclosure(self):
        second = [(self.loop[2][0] + 0.000001, self.loop[2][1]), *self.loop[3:]]
        result = inspect(response([self.loop[:3], second]), self.loop[0], self.loop[0], "lake_loop", self.loop, self.water)
        self.assertIn("LAP_DISCONNECTED_GEOMETRY", result["unresolved"])
        self.assertEqual("NOT_EVALUATED_DISCONNECTED_GEOMETRY", result["lake_topology_sampling"])
        self.assertNotIn("water_boundary_outside_fraction", result)

    def test_small_endpoint_gap_does_not_get_a_winding_measurement(self):
        path = self.loop[:-1] + [(self.loop[0][0] + 0.000001, self.loop[0][1])]
        result = inspect(response([path]), path[0], path[-1], "lake_loop", self.loop, self.water)
        self.assertIn("LAP_OPEN_GEOMETRY", result["unresolved"])
        self.assertEqual("NOT_EVALUATED_OPEN_GEOMETRY", result["lake_topology_sampling"])

    def test_outer_road_loop_is_not_accepted_for_enclosing_lake(self):
        outer = [(126.998, 36.998), (127.004, 36.998), (127.004, 37.004),
                 (126.998, 37.004), (126.998, 36.998)]
        result = inspect(response([outer]), outer[0], outer[0], "lake_loop", self.loop, self.water)
        self.assertIn("OUTSIDE_REFERENCE_WALKWAY", result["failures"])

    def test_outbound_leg_on_parallel_road_is_rejected(self):
        reference = self.loop[:2]
        road = [(x, y + 0.001) for x, y in reference]
        result = inspect(response([road]), road[0], road[-1], reference=reference)
        self.assertIn("OUTSIDE_REFERENCE_WALKWAY", result["failures"])

    def test_missing_boundary_stays_unknown(self):
        result = inspect(response([self.loop]), self.loop[0], self.loop[0], "lake_loop", self.loop)
        self.assertEqual("INCOMPLETE", result["geometry_check"])
        self.assertIn("TARGET_WATER_BOUNDARY_MISSING", result["unresolved"])

    def test_reference_network_does_not_invent_a_connector(self):
        reference_segments = [(self.loop[0], self.loop[1]), (self.loop[2], self.loop[3])]
        connector = [self.loop[1], self.loop[2]]
        result = inspect(response([connector]), connector[0], connector[-1],
                         reference_segments=reference_segments)
        self.assertIn("OUTSIDE_REFERENCE_WALKWAY", result["failures"])

    def test_empty_network_segments_keep_the_curated_reference_line(self):
        result = inspect(response([self.loop[:2]]), self.loop[0], self.loop[1],
                         reference=self.loop[:2], reference_segments=[])
        self.assertEqual(1.0, result["reference_coverage"])
        self.assertEqual("PASS", result["geometry_check"])

    def test_leg_partition_is_not_assumed_to_equal_waypoint_count(self):
        result = inspect(response([self.loop[:3]]), self.loop[0], self.loop[2], via=[self.loop[1]])
        self.assertIn("LEG_WAYPOINT_ALIGNMENT_REQUIRES_REVIEW", result["unresolved"])
        self.assertEqual("INCOMPLETE", result["geometry_check"])

    def test_waypoint_leg_boundaries_follow_requested_order(self):
        result = inspect(response([self.loop[:2], self.loop[1:3]]), self.loop[0], self.loop[2], via=[self.loop[1]])
        self.assertEqual("PASS_WITHIN_30M", result["waypoint_order_check"])

    def test_unaligned_leg_boundary_requires_review(self):
        result = inspect(response([self.loop[:3], self.loop[2:]]), self.loop[0], self.loop[-1], via=[self.loop[1]])
        self.assertIn("LEG_WAYPOINT_ALIGNMENT_REQUIRES_REVIEW", result["unresolved"])

    def test_geometric_lap_does_not_claim_field_walkability(self):
        result = inspect(response([self.loop]), self.loop[0], self.loop[0], "lake_loop", self.loop, self.water)
        self.assertEqual([], result["failures"])
        self.assertEqual("INCOMPLETE", result["geometry_check"])
        self.assertEqual("UNVERIFIED", result["walking_access"])

    def test_closed_reference_cannot_prove_a_unique_river_turnpoint(self):
        path = [self.loop[0], self.loop[1], self.loop[0]]
        result = inspect(response([path]), path[0], path[-1], "river_out_and_back", path)
        self.assertEqual([], result["failures"])
        self.assertIn("RIVER_PROGRESS_AMBIGUOUS", result["unresolved"])

    def test_coordinate_order_nan_and_boolean_rejected(self):
        for value in ([37, 127], [float("nan"), 37], [True, 37]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                point(value)

    def test_negative_and_boolean_distance_rejected(self):
        for invalid in (-1, True):
            payload = copy.deepcopy(response([self.loop]))
            payload["route"]["properties"]["totalDistance"] = invalid
            self.assertEqual("FAIL", inspect(payload, self.loop[0], self.loop[0])["geometry_check"])


class ExecutionSafetyTests(unittest.TestCase):
    def test_source_without_usage_terms_is_not_approved(self):
        source = {"url": "https://www.openstreetmap.org/", "retrieved_at": "2026-10-08"}
        self.assertFalse(source_ok(source))
        source["license"] = "ODbL 1.0; attribution required"
        self.assertTrue(source_ok(source))

    def test_call_budget_blocks_before_network(self):
        with self.assertRaises(RuntimeError):
            Client("synthetic-not-a-real-key", 0).get("/unused", {})

    def test_empty_template_cannot_trigger_live_probe(self):
        with self.assertRaises(ValueError):
            load_site(Path(__file__).with_name("site.template.json"))

    def test_six_waypoints_only_in_explicit_limit_case(self):
        points = [(127 + i / 1000, 37) for i in range(8)]
        matrix = cases(points, "lake_loop")
        self.assertEqual(["via_6"], [name for name, _, _, via, _ in matrix if len(via) > 5])
        same = next(c for c in matrix if c[0] == "same_point_via_5")
        self.assertEqual(same[1], same[2])


if __name__ == "__main__":
    unittest.main()
