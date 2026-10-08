"""Synthetic graph checks; no paid requests or park-specific coordinates."""
import unittest

from plan_source_cycle import plan
from prepare_site import network
from test_sources import source, way
from validate_lap import inspect_lap


def fixture(stem=False, split=False, reverse_only=False):
    # Twenty distinct nodes around a square, plus the closing source node.
    xy = [(i, 0) for i in range(5)] + [(5, i) for i in range(5)] + [(5 - i, 5) for i in range(5)] + [(0, 5 - i) for i in range(5)]
    positions = [(127 + x / 10000, 37 + y / 10000) for x, y in xy]
    nodes = list(range(20)) + [0]
    coordinates = positions + [positions[0]]
    tags = {"oneway:foot": "-1"} if reverse_only else {}
    walks = [way(1, nodes, coordinates, **tags)]
    if split:
        walks = [way(1, nodes[:11], coordinates[:11]),
                 way(2, [30] + nodes[11:], [coordinates[10]] + coordinates[11:])]
    water = way(99, [100, 101, 102, 103, 100],
                [(127.0001, 37.0001), (127.0004, 37.0001), (127.0004, 37.0004), (127.0001, 37.0004), (127.0001, 37.0001)], natural="water")
    water["tags"].pop("highway")
    if stem:
        walks.append(way(3, [50, 0], [(126.9999, 37), positions[0]]))
    return source(walks + [water])


class SourceCycleTests(unittest.TestCase):
    def test_cycle_uses_only_real_directed_edges_and_encloses_whole_water(self):
        data = fixture()
        result = plan(data, 99, 0)
        coordinates, edges, _ = network(data)
        self.assertTrue(all((a, b) in edges for a, b in zip(result["source_node_ids"], result["source_node_ids"][1:])))
        self.assertEqual(8, len(set(result["sample_node_ids"])))
        self.assertEqual("PASS_GEOMETRY_ONLY", inspect_lap([result["reference_walkway"]], result["water_boundary"])["status"])
        self.assertEqual("UNVERIFIED", result["review"]["walking_access"])
        self.assertFalse(result["walk_points_reviewed"])

    def test_access_stem_is_excluded_and_changed_departure_is_explicit(self):
        result = plan(fixture(stem=True), 99, 50)
        self.assertNotIn(50, result["source_node_ids"])
        self.assertEqual(50, result["input_change"]["original_source_node"])
        self.assertNotEqual(50, result["input_change"]["alternative_start_node"])

    def test_identical_coordinates_do_not_join_disconnected_source_node_ids(self):
        with self.assertRaises(ValueError):
            plan(fixture(split=True), 99, 0)

    def test_reverse_only_source_uses_allowed_direction(self):
        data = fixture(reverse_only=True)
        result = plan(data, 99, 0)
        _, edges, _ = network(data)
        self.assertTrue(all((a, b) in edges for a, b in zip(result["source_node_ids"], result["source_node_ids"][1:])))


if __name__ == "__main__":
    unittest.main()
