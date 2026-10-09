"""Synthetic topology regressions; actual source fixtures only test readiness gates."""
import json
import unittest
from pathlib import Path

from prepare_site import draft, eligible, network, sample_nodes
from prepare_lake_probe import prepare
from probe import cases, load_site


def source(ways):
    return {"source": {"url": "https://www.openstreetmap.org/", "retrieved_at": "2026-10-08",
                       "license": "ODbL 1.0; SYNTHETIC TEST FIXTURE"}, "osm": {"elements": ways}}


def way(identifier, nodes, coordinates, **tags):
    return {"type": "way", "id": identifier, "nodes": nodes,
            "geometry": [{"lon": x, "lat": y} for x, y in coordinates],
            "tags": {"highway": "footway", **tags}}


class SourceTopologyTests(unittest.TestCase):
    def test_steps_are_pedestrian_edges_but_access_restrictions_still_apply(self):
        self.assertTrue(eligible({"highway": "steps"}))
        self.assertFalse(eligible({"highway": "steps", "foot": "no"}))
        self.assertFalse(eligible({"highway": "steps", "access": "private"}))

    def test_cycleway_without_pedestrian_permission_is_excluded(self):
        self.assertFalse(eligible({"highway": "cycleway"}))
        self.assertFalse(eligible({"highway": "cycleway", "foot": "no"}))
        self.assertTrue(eligible({"highway": "cycleway", "foot": "designated"}))

    def test_area_boundary_is_not_a_walking_line(self):
        self.assertFalse(eligible({"highway": "footway", "area": "yes"}))

    def test_explicit_foot_permission_overrides_generic_access(self):
        self.assertFalse(eligible({"highway": "footway", "access": "no"}))
        self.assertTrue(eligible({"highway": "footway", "access": "no", "foot": "yes"}))
        self.assertFalse(eligible({"highway": "footway", "access": "yes", "foot": "private"}))

    def test_nearby_or_identical_coordinates_do_not_create_a_connector(self):
        data = source([way(1, [1, 2], [(127, 37), (127.001, 37)]),
                       way(2, [3, 4], [(127.001, 37), (127.002, 37)])])
        _, edges, _ = network(data)
        self.assertNotIn((2, 3), edges)

    def test_disagreement_on_shared_node_geometry_stops_import(self):
        data = source([way(1, [1, 2], [(127, 37), (127.001, 37)]),
                       way(2, [2, 3], [(127.001, 37.001), (127.002, 37)])])
        with self.assertRaises(ValueError):
            network(data)

    def test_pedestrian_oneway_is_respected(self):
        data = source([way(1, [1, 2], [(127, 37), (127.001, 37)], **{"oneway:foot": "yes"})])
        _, edges, _ = network(data)
        self.assertIn((1, 2), edges)
        self.assertNotIn((2, 1), edges)

    def test_sampler_uses_distinct_source_nodes_despite_uneven_spacing(self):
        nodes = list(range(12))
        coordinates = {n: (127 + (0.001 if n else 0) + n * 0.000001, 37) for n in nodes}
        sampled = sample_nodes(nodes, coordinates)
        self.assertEqual(8, len(set(sampled)))
        self.assertEqual(nodes[0], sampled[0])
        self.assertEqual(nodes[-1], sampled[-1])
        self.assertTrue(all(n in coordinates for n in sampled))

    def test_draft_cannot_include_unmapped_shortcut(self):
        nodes = list(range(9))
        data = source([way(1, nodes, [(127 + n * 0.001, 37) for n in nodes])])
        selection = {"name": "Synthetic river", "shape": "river_out_and_back", "node_ids": nodes[:4] + nodes[5:]}
        with self.assertRaises(ValueError):
            draft(data, selection)

    def test_river_loop_experiment_includes_actual_turnpoint(self):
        points = [(127 + n * 0.001, 37) for n in range(8)]
        matrix = cases(points, "river_out_and_back")
        closed = next(c for c in matrix if c[0] == "same_point_via_5")
        self.assertEqual(points[-1], closed[3][-1])

    def test_explicit_lake_indices_preserve_selected_original_source_points(self):
        points = [(127 + n * 0.001, 37) for n in range(8)]
        case = next(c for c in cases(points, "lake_loop", [1, 2, 4, 5, 7]) if c[0] == "same_point_via_5")
        self.assertEqual([points[i] for i in [1, 2, 4, 5, 7]], case[3])
        self.assertEqual(case[1], case[2])

    def test_custom_waypoints_reject_duplicates_wrong_order_and_missing_river_turnpoint(self):
        points = [(127 + n * 0.001, 37) for n in range(8)]
        for indices in [[1, 2, 3, 4, 5, 6], [1, 2, 2, 4, 7], [2, 1, 3, 4, 7], [True, 2, 3, 4, 7], [0, 2, 3, 4, 7], [1, 2, 3, 4, 8]]:
            with self.assertRaises(ValueError):
                cases(points, "lake_loop", indices)
        with self.assertRaises(ValueError):
            cases(points, "river_out_and_back", [1, 2, 3, 4, 6])

    def test_real_source_draft_remains_blocked_before_review(self):
        path = Path(__file__).with_name("drafts") / "river.site.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(data["walk_points_reviewed"])
        self.assertEqual("UNVERIFIED", data["review"]["walking_access"])
        with self.assertRaises(ValueError):
            load_site(path)

    def test_lake_without_nearby_source_walkways_does_not_invent_points(self):
        water = way(99, [20, 21, 22, 20], [(127.5, 37.5), (127.501, 37.5),
                                        (127.5, 37.501), (127.5, 37.5)], natural="water")
        water["tags"].pop("highway")
        data = source([water, way(1, list(range(9)), [(127 + n * 0.001, 37) for n in range(9)])])
        with self.assertRaises(ValueError):
            prepare(data, 99)

    def test_open_water_geometry_is_not_used_as_lake_boundary(self):
        water = way(99, [20, 21, 22], [(127, 37), (127.001, 37), (127, 37.001)], natural="water")
        with self.assertRaises(ValueError):
            prepare(source([water]), 99)


if __name__ == "__main__":
    unittest.main()
