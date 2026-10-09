"""Synthetic graph checks; no paid requests or park-specific coordinates."""
import unittest
import copy

from plan_source_cycle import plan, plan_multiple, alternate_arc
import time
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

    def alternative_fixture(self):
        data = fixture()
        coords, _, _ = network(data)
        data['osm']['elements'].extend([
            way(2,[5,30,31,10],[coords[5],(127.0008,37),(127.0008,37.0005),coords[10]]),
            way(3,[15,32,33,0],[coords[15],(126.99965,37.0005),(126.99965,37),coords[0]])])
        return data

    def test_distance_search_finds_longer_real_cycles_and_preserves_source(self):
        data = self.alternative_fixture()
        original = copy.deepcopy(data)
        result = plan_multiple(data,99,0,distance_m=255)
        self.assertGreaterEqual(len(result['candidates']),2)
        coordinates,edges,_ = network(data)
        signatures = set()
        for site in result['candidates']:
            ids = site['source_node_ids']
            self.assertTrue(229.5 <= site['source_network_length_m'] <= 280.5)
            self.assertEqual(len(ids)-1,len(set(ids[:-1])))
            self.assertTrue(all(edge in edges for edge in zip(ids,ids[1:])))
            self.assertEqual('PASS_GEOMETRY_ONLY',inspect_lap([site['reference_walkway']],site['water_boundary'])['status'])
            signatures.add(frozenset(tuple(sorted(edge)) for edge in zip(ids,ids[1:])))
        self.assertEqual(len(result['candidates']),len(signatures))
        self.assertEqual(original,data)

    def test_impossible_target_is_not_filled_by_repeated_laps(self):
        result = plan_multiple(fixture(),99,0,distance_m=1000)
        self.assertEqual([],result['candidates'])
        self.assertIn(result['status'],('SOURCE_CYCLE_DISTANCE_NOT_FOUND','SOURCE_CYCLE_SEARCH_LIMIT_REACHED'))

    def test_search_limits_are_reported_and_not_success(self):
        result = plan_multiple(fixture(),99,0,distance_m=255,max_attempts=0)
        self.assertEqual('SOURCE_CYCLE_SEARCH_LIMIT_REACHED',result['status'])
        self.assertTrue(result['search']['limit_reached'])
        self.assertEqual(0,result['search']['attempts'])

    def test_none_distance_keeps_lap_semantics_and_returns_distinct_alternatives(self):
        result = plan_multiple(self.alternative_fixture(),99,0)
        self.assertIsNone(result['search']['requested_distance_m'])
        self.assertGreaterEqual(len(result['candidates']),2)
        self.assertEqual(min(c['source_network_length_m'] for c in result['candidates']),result['candidates'][0]['source_network_length_m'])

    def test_distance_search_combines_separate_arcs_without_extra_laps(self):
        data = fixture()
        c,_,_ = network(data)
        data['osm']['elements'].extend([
            way(2,[0,30,31,5],[c[0],(127,36.9996),(127.0005,36.9996),c[5]]),
            way(3,[5,32,33,10],[c[5],(127.0009,37),(127.0009,37.0005),c[10]]),
            way(4,[10,34,35,15],[c[10],(127.0005,37.0009),(127,37.0009),c[15]]),
            way(5,[15,36,37,0],[c[15],(126.9996,37.0005),(126.9996,37),c[0]])])
        original = copy.deepcopy(data)
        result = plan_multiple(data,99,0,390)
        self.assertTrue(result['candidates'])
        _,edges,_ = network(data)
        for site in result['candidates']:
            ids=site['source_node_ids']
            self.assertTrue(351 <= site['source_network_length_m'] <= 429)
            self.assertEqual(len(ids)-1,len(set(ids[:-1])))
            self.assertGreaterEqual(sum(n in ids for n in range(30,38)),4)
            self.assertTrue(all(edge in edges for edge in zip(ids,ids[1:])))
            self.assertEqual('PASS_GEOMETRY_ONLY',inspect_lap([site['reference_walkway']],site['water_boundary'])['status'])
        self.assertEqual(original,data)
        self.assertLessEqual(result['search']['path_attempts'],result['search']['path_attempt_limit'])

    def test_arc_search_does_not_revisit_forbidden_nodes_or_reverse_direction(self):
        adjacency={0:[(1,1,0),(2,2,0)],1:[(3,1,0)],2:[(3,2,0)],3:[]}
        self.assertEqual([0,2,3],alternate_arc(adjacency,0,3,set(),{1},time.monotonic()+1,[10]))
        self.assertIsNone(alternate_arc(adjacency,3,0,set(),set(),time.monotonic()+1,[10]))
        self.assertIsNone(alternate_arc(adjacency,0,3,{(0,2)},{1},time.monotonic()+1,[10]))

    def test_arc_search_work_and_time_limits_cannot_return_partial_path(self):
        adjacency={0:[(1,1,0)],1:[(2,1,0)],2:[]}
        for deadline,budget in [(time.monotonic()+1,[1]),(time.monotonic()-1,[100])]:
            with self.assertRaises(TimeoutError):
                alternate_arc(adjacency,0,2,set(),set(),deadline,budget)


if __name__ == "__main__":
    unittest.main()
