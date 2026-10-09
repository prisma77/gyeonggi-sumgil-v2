"""Duration, source fidelity and geometric direction regressions; no API calls."""
import copy
from itertools import combinations
import json
from pathlib import Path
import unittest

from audit_inputs import audit_inputs
from plan_river_candidates import candidate_id, compare_distance, inspect_distance, inspect_target, plan
from probe import meters, routing_inputs, segment_distance
from select_waypoints import select, select_minimum
from select_network_anchors import select_network_anchors
from prepare_site import network
from validate_river import inspect_river


class WaypointSelectionTests(unittest.TestCase):
    def test_restricted_inputs_keep_all_original_bends_in_the_error_measurement(self):
        points = [(127 + i * .0002, 37 + y * .0001) for i, y in enumerate([0, 0, 3, 3, 0, 0, 2, 0, 0])]
        allowed = [2, 5, 7, 8]
        chosen = select(points, 3, allowed)
        errors = []
        for pair in combinations(allowed[:-1], 2):
            indexes = [0, *pair, 8]
            errors.append(max((segment_distance(p, points[a], points[b])
                               for a, b in zip(indexes, indexes[1:]) for p in points[a + 1:b]), default=0))
        self.assertAlmostEqual(min(errors), chosen["max_chord_deviation_m"])
        self.assertTrue(set(chosen["indices"]) <= set(allowed))
        with self.assertRaises(ValueError):
            select(points, 3, [2, 5, 7])
    def test_straight_corridor_only_needs_the_turnpoint(self):
        points = [(127 + i * .001, 37) for i in range(11)]
        self.assertEqual([10], select_minimum(points)["indices"])

    def test_right_angle_requires_a_bend_and_turnpoint_without_filling_five(self):
        points = [(127, 37), (127.001, 37), (127.002, 37), (127.002, 37.001), (127.002, 37.002)]
        self.assertGreater(select(points, 1)["max_chord_deviation_m"], 5)
        self.assertEqual([2, 4], select_minimum(points)["indices"])

    def test_insufficient_budget_does_not_relax_source_shape_tolerance(self):
        points = [(127, 37), (127.001, 37), (127.001, 37.001)]
        self.assertIsNone(select_minimum(points, maximum=1))
        for bad in [[], [(127, 37)]]:
            with self.assertRaises(ValueError):
                select_minimum(bad)

    def test_bend_error_matches_exhaustive_source_node_selection(self):
        points = [(127 + i * .0002, 37 + y * .0001) for i, y in enumerate([0, 0, 3, 3, 0, 0, 2, 0, 0])]
        chosen = select(points, 3)
        errors = []
        for middle in combinations(range(1, len(points) - 1), 2):
            indices = [0, *middle, len(points) - 1]
            errors.append(max((segment_distance(p, points[a], points[b]) for a, b in zip(indices, indices[1:])
                               for p in points[a + 1:b]), default=0))
        self.assertAlmostEqual(min(errors), chosen["max_chord_deviation_m"])
        self.assertEqual(3, len(chosen["indices"]))
        self.assertEqual(len(points) - 1, chosen["indices"][-1])

    def test_straight_corridor_tie_uses_even_source_intervals(self):
        points = [(127 + i * .001, 37) for i in range(11)]
        result = select(points)
        self.assertEqual([2, 4, 6, 8, 10], result["indices"])

    def test_short_source_uses_fewer_vias_without_inventing_points(self):
        self.assertEqual([1], select([(127, 37), (127.001, 37)])["indices"])
        with self.assertRaises(ValueError):
            select([(127, 37)])
        with self.assertRaises(ValueError):
            select([(127, 37), (127.001, 37)], 6)


class RiverCandidateTests(unittest.TestCase):
    def setUp(self):
        directory = Path(__file__).parent
        self.site = json.loads((directory / "drafts/river-long.probe.json").read_text(encoding="utf-8-sig"))
        self.source = json.loads((directory / "sources/river-walkways.osm.json").read_text(encoding="utf-8-sig"))

    def test_time_target_preserves_departure_source_edges_and_exact_return_node(self):
        original = copy.deepcopy(self.site)
        result = plan(self.site, self.source, 10, 4)
        self.assertEqual("SOURCE_CANDIDATES_ONLY", result["status"])
        self.assertEqual(3, len(result["candidates"]))
        errors = [c["river_candidate"]["source_time_error_fraction"] for c in result["candidates"]]
        self.assertEqual(sorted(errors), errors)
        for candidate in result["candidates"]:
            count = len(candidate["source_node_ids"])
            self.assertEqual(self.site["source_node_ids"][:count], candidate["source_node_ids"])
            self.assertEqual([tuple(p) for p in self.site["reference_walkway"][:count]], candidate["reference_walkway"])
            self.assertEqual([], audit_inputs(candidate, self.source)["failures"])
            start, end, via, _ = routing_inputs(candidate)
            self.assertEqual(start, end)
            self.assertEqual(tuple(self.site["walk_points"][0]), start)
            self.assertEqual(tuple(candidate["reference_walkway"][-1]), via[-1])
            self.assertLessEqual(len(via), 5)
        self.assertEqual(original, self.site)

    def test_insufficient_length_returns_no_silent_shorter_course(self):
        result = plan(self.site, self.source, 30, 4)
        self.assertEqual("TARGET_OUTSIDE_AVAILABLE_SOURCE_RANGE", result["status"])
        self.assertEqual([], result["candidates"])
        self.assertLess(result["available_estimated_minutes"][-1], 16)

    def test_short_source_or_conflicting_time_never_substitutes_sub_two_km_candidate(self):
        self.assertEqual([], plan(self.site, self.source, 12, 4, [2000, 3000])["candidates"])
        directory = Path(__file__).parent
        site = json.loads((directory / "drafts/river-extended.probe.json").read_text(encoding="utf-8"))
        source = json.loads((directory / "sources/river-extended-walkways.osm.json").read_text(encoding="utf-8"))
        self.assertEqual([], plan(site, source, 10, 4, [2000, 3000])["candidates"])
        candidates = plan(site, source, 38, 4, [2000, 3000])["candidates"]
        self.assertTrue(candidates)
        lengths = [c["source_network_length_m"] for c in candidates]
        self.assertTrue(all(abs(a - b) >= 75 for a, b in combinations(lengths, 2)))
        for candidate in candidates:
            self.assertEqual(self.site["source_node_ids"][0], candidate["source_node_ids"][0])
            self.assertEqual(len(candidate["source_node_ids"]), len(set(candidate["source_node_ids"])))
            self.assertEqual([], audit_inputs(candidate, source)["failures"])
            meta = candidate["river_candidate"]
            self.assertTrue(2000 <= meta["source_expected_roundtrip_m"] <= 3000)
            self.assertLessEqual(len(meta["via_node_ids"]), 5)
            self.assertTrue(meta["waypoint_selection"]["source_shape_tolerance_exceeded"])
            self.assertEqual(5, meta["waypoint_selection"]["source_shape_tolerance_m"])
            via = candidate["selected_via_indices"]
            middle = meta["turnpoint_via_index"]
            self.assertEqual(len(candidate["reference_walkway"]) - 1, via[middle])
            self.assertEqual(via[:middle], list(reversed(via[middle + 1:])))
            start, end, requested, _ = routing_inputs(candidate)
            self.assertEqual(start, end)
            self.assertEqual(requested[:middle], list(reversed(requested[middle + 1:])))
            tampered = copy.deepcopy(candidate)
            tampered["selected_via_indices"][-1] += 1
            with self.assertRaises(ValueError):
                routing_inputs(tampered)

    def test_network_anchors_avoid_infrastructure_inputs_without_changing_the_walkway(self):
        directory = Path(__file__).parent
        site = json.loads((directory / "drafts/river-extended.probe.json").read_text(encoding="utf-8"))
        source = json.loads((directory / "sources/river-extended-walkways.osm.json").read_text(encoding="utf-8"))
        coords, edges, ways = network(source)
        selected = select_network_anchors(site["source_node_ids"], coords, edges, ways)
        indexes = selected["indices"]
        self.assertEqual(len(site["source_node_ids"]) - 1, indexes[-1])
        self.assertTrue(selected["excluded_source_indices"])
        self.assertTrue(all(i not in selected["excluded_source_indices"] for i in indexes[:-1]))
        self.assertTrue(all(not any(w.get("tags", {}).get("bridge") == "yes" for w in ways.values()
                                   if site["source_node_ids"][i] in w["nodes"]) for i in indexes[:-1]))
        self.assertEqual(30, selected["input_clearance_m"])
        removed = dict(edges)
        removed.pop((site["source_node_ids"][2], site["source_node_ids"][1]))
        with self.assertRaises(ValueError):
            select_network_anchors(site["source_node_ids"], coords, removed, ways)

    def test_junction_selection_uses_graph_ids_in_a_different_synthetic_network(self):
        coords = {100 + i: (126 + i * .001, 36) for i in range(11)}
        nodes = list(coords)
        coords[999] = (126.003, 36.001)
        edges = {}
        for a, b in [*zip(nodes, nodes[1:]), (103, 999)]:
            edges[a, b] = [77]; edges[b, a] = [77]
        ways = {77: {"tags": {"highway": "footway"}}}
        result = select_network_anchors(nodes, coords, edges, ways)
        self.assertIn(3, result["junction_source_indices"])
        self.assertNotIn(3, result["indices"])
        self.assertEqual(10, result["indices"][-1])
        self.assertLessEqual(len(result["indices"]), 3)
        for branch in [1000, 1001]:
            coords[branch] = (126.01, 36.001)
            edges[110, branch] = [77]; edges[branch, 110] = [77]
        endpoint_junction = select_network_anchors(nodes, coords, edges, ways)
        self.assertEqual(10, endpoint_junction["indices"][-1])
        self.assertTrue(endpoint_junction["turnpoint_source_choice_unverified"])

    def test_real_provider_distance_is_validated_independently_of_source_estimate(self):
        candidate = {"distance_range_m": [2000, 3000], "source_expected_roundtrip_m": 2500}
        for length in [913, 1999.9, 3000.1]:
            self.assertEqual(["TARGET_DISTANCE_MISMATCH"], inspect_distance({"distance_m": length}, candidate)["failures"])
        for length in [2000, 2500, 3000]:
            self.assertEqual("PASS_API_DISTANCE_ONLY", inspect_distance({"distance_m": length}, candidate)["status"])
        for length in [None, float("nan"), True]:
            self.assertEqual("NOT_EVALUATED", inspect_distance({"distance_m": length}, candidate)["status"])
        for bounds in [[3000, 2000], [True, 3000], [0, 3000], [2000, float("inf")]]:
            with self.assertRaises(ValueError):
                plan(self.site, self.source, 38, 4, bounds)

    def test_short_time_can_use_fewer_than_eight_original_nodes(self):
        candidate = plan(self.site, self.source, 5, 4)["candidates"][0]
        self.assertLess(len(candidate["source_node_ids"]), 8)
        self.assertEqual([], audit_inputs(candidate, self.source)["failures"])

    def test_invalid_targets_unknown_speed_and_unreviewed_source_are_blocked(self):
        for duration, speed in [(0, 4), (True, 4), (10.5, 4), (10, 0), (10, True), (10, float("nan"))]:
            with self.assertRaises(ValueError):
                plan(self.site, self.source, duration, speed)
        self.site["walk_points_reviewed"] = False
        with self.assertRaises(ValueError):
            plan(self.site, self.source, 10, 4)

    def test_unmapped_reference_and_oneway_return_are_not_candidates(self):
        self.site["reference_walkway"][1][0] += .001
        with self.assertRaises(ValueError):
            plan(self.site, self.source, 10, 4)
        self.setUp()
        for way in self.source["osm"]["elements"]:
            if way.get("id") in self.site["source_way_ids"] and way["type"] == "way":
                way["tags"]["oneway:foot"] = "yes"
        with self.assertRaises(ValueError):
            plan(self.site, self.source, 10, 4)

    def test_tampered_generated_return_direction_fails_source_audit(self):
        candidate = plan(self.site, self.source, 10, 4)["candidates"][0]
        candidate["source_node_ids"] = list(reversed(candidate["source_node_ids"]))
        self.assertIn("RIVER_SOURCE_CORRIDOR_NOT_BIDIRECTIONAL", audit_inputs(candidate, self.source)["failures"])

    def test_actual_api_time_is_checked_independently_of_source_estimate(self):
        meta = plan(self.site, self.source, 10, 4)["candidates"][0]["river_candidate"]
        self.assertEqual("PASS_API_TIME_ONLY", inspect_target({"time_s": 720}, meta)["status"])
        self.assertEqual(["TARGET_DURATION_MISMATCH"], inspect_target({"time_s": 1000}, meta)["failures"])
        self.assertEqual("NOT_EVALUATED", inspect_target({}, meta)["status"])

    def test_real_source_candidate_uses_two_required_vias_not_five(self):
        candidate = plan(self.site, self.source, 12, 4)["candidates"][0]
        self.assertEqual([7, 14], candidate["selected_via_indices"])
        self.assertGreater(select(candidate["reference_walkway"], 1)["max_chord_deviation_m"], 5)
        self.assertLessEqual(candidate["river_candidate"]["waypoint_selection"]["max_chord_deviation_m"], 5)

    def test_same_turnpoint_with_different_vias_has_distinct_input_identity(self):
        candidate = plan(self.site, self.source, 12, 4)["candidates"][0]
        alternative = copy.deepcopy(candidate)
        alternative["river_candidate"]["via_node_ids"].insert(0, self.site["source_node_ids"][3])
        self.assertNotEqual(candidate_id("river-long", candidate), candidate_id("river-long", alternative))

    def test_source_api_distance_difference_is_review_not_proven_detour(self):
        meta = plan(self.site, self.source, 12, 4)["candidates"][0]["river_candidate"]
        result = compare_distance({"distance_m": 920, "geometry_distance_m": 880}, meta)
        self.assertEqual("REVIEW_REQUIRED", result["status"])
        self.assertEqual(113.1, result["reported_minus_source_m"])
        self.assertIn("NOT_PROOF", result["scope"])
        self.assertEqual("NOT_EVALUATED", compare_distance({}, meta)["status"])


class RiverDirectionTests(unittest.TestCase):
    reference = [(127 + i * .001, 37) for i in range(11)]

    def test_actual_outbound_and_return_pass_geometry_only(self):
        result = inspect_river([self.reference, list(reversed(self.reference))], self.reference)
        self.assertEqual("PASS_GEOMETRY_ONLY", result["status"])
        self.assertEqual("UNVERIFIED", result["walking_access"])
        self.assertEqual(0, result["outbound_backtrack_m"])
        self.assertEqual(0, result["inbound_backtrack_m"])

    def test_returning_to_start_without_reaching_requested_turnpoint_fails(self):
        short = self.reference[:5]
        result = inspect_river([short, list(reversed(short))], self.reference)
        self.assertIn("RIVER_TURNPOINT_NOT_REACHED", result["failures"])

    def test_extra_lap_and_outbound_backtracking_fail(self):
        for path in [self.reference + self.reference[-2::-1] + self.reference[1:] + self.reference[-2::-1],
                     self.reference[:6] + self.reference[3:] + self.reference[-2::-1]]:
            self.assertIn("RIVER_UNNECESSARY_DIRECTION_REVERSAL", inspect_river([path], self.reference)["failures"])

    def test_off_corridor_detour_is_not_hidden_by_overall_coverage(self):
        path = [self.reference[0], (self.reference[5][0], 37.001), self.reference[-1], self.reference[0]]
        self.assertIn("RIVER_OUTSIDE_SOURCE_CORRIDOR", inspect_river([path], self.reference)["failures"])

    def test_step_gap_is_held_without_creating_or_changing_geometry(self):
        paths = [self.reference, [(127.01001, 37), *self.reference[-2::-1]]]
        original = copy.deepcopy(paths)
        result = inspect_river(paths, self.reference)
        self.assertEqual("INCOMPLETE", result["status"])
        self.assertIn("RIVER_STEP_CONNECTION_REVIEW_REQUIRED", result["unresolved"])
        self.assertEqual(original, paths)

    def test_gap_does_not_hide_a_separate_off_corridor_detour(self):
        paths = [self.reference[:6], [(127.00501, 37), (127.006, 37.001),
                                     self.reference[-1], *self.reference[-2::-1]]]
        original = copy.deepcopy(paths)
        result = inspect_river(paths, self.reference)
        self.assertEqual("FAIL", result["status"])
        self.assertIn("RIVER_STEP_CONNECTION_REVIEW_REQUIRED", result["unresolved"])
        self.assertIn("RIVER_OUTSIDE_SOURCE_CORRIDOR", result["failures"])
        self.assertGreater(result["max_corridor_offset_m"], 20)
        self.assertGreater(result["max_step_connection_difference_m"], .001)
        self.assertTrue(result["off_corridor_source_segment_indices"])
        self.assertNotIn("outbound_backtrack_m", result)
        self.assertEqual(original, paths)

    def test_parallel_source_arms_make_progress_ambiguous(self):
        reference = [(127, 37), (127.01, 37), (127.01, 37.00005), (127, 37.00005)]
        path = [(127, 37.000025), (127.01, 37.000025), (127, 37.000025)]
        self.assertIn("RIVER_PROGRESS_AMBIGUOUS", inspect_river([path], reference)["unresolved"])

    def test_cumulative_small_direction_reversals_do_not_reset_budget(self):
        # Two separate 6m reversals together exceed the 10m trial budget.
        dx = .0000676
        path = [self.reference[0], self.reference[3], (self.reference[3][0] - dx, 37),
                self.reference[6], (self.reference[6][0] - dx, 37), self.reference[-1], self.reference[0]]
        self.assertIn("RIVER_UNNECESSARY_DIRECTION_REVERSAL", inspect_river([path], self.reference)["failures"])


if __name__ == "__main__":
    unittest.main()
