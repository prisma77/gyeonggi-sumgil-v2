"""Independent synthetic source evidence; no coordinate repair or live requests."""
import copy
import unittest
from source_route_evidence import inspect_source_network
from probe import inspect
from test_probe import response
from test_sources import source, way


class SourceRouteTests(unittest.TestCase):
    path = [(127, 37), (127.001, 37)]

    def test_alternative_route_on_source_network_is_not_a_walkability_failure(self):
        reference = [(x, y+.001) for x, y in self.path]
        # Reversible linear shape used here to isolate course vs network checks;
        # a non-lap must still fail the independent lake topology check.
        route = [*self.path, self.path[0]]
        data = source([way(1, [1, 2], self.path)])
        result = inspect(response([route]), route[0], route[-1], 'lake_loop', reference,
                         [(127, 37.0001), (127.001, 37.0001), (127, 37.0002)], source=data)
        self.assertNotIn('OUTSIDE_REFERENCE_WALKWAY', result['failures'])
        self.assertIn('LAP_DEGENERATE_GEOMETRY', result['failures'])
        self.assertEqual('CHANGED', result['reference_course_check'])
        self.assertIn('ALTERNATE_SOURCE_WALKWAY_USED', result['notes'])

    def test_prohibited_or_wrong_direction_is_not_allowed_source_geometry(self):
        for tags in ({'foot': 'no'}, {'oneway:foot': '-1'}, {'access': 'private'}, {'access:conditional': 'no @ (winter)'}):
            with self.subTest(tags=tags):
                data = source([way(1, [1, 2], self.path, **tags)])
                result = inspect_source_network([self.path], data)
                self.assertNotEqual('PASS_SOURCE_GEOMETRY_ONLY', result['status'])

    def test_candidate_allowlist_is_not_all_walking_data(self):
        data = source([way(1, [1, 2], self.path)])
        data['source_edge_allowlist'] = []
        result = inspect_source_network([self.path], data)
        self.assertEqual('PASS_SOURCE_GEOMETRY_ONLY', result['status'])

    def test_analysis_limit_and_missing_source_do_not_pass(self):
        for data, budget in ((None, 2_000_000), (source([way(1, [1, 2], self.path)]), 1)):
            result = inspect_source_network([self.path], data, work_limit=budget)
            self.assertEqual('NOT_EVALUATED', result['status'])
            self.assertNotIn('coverage', result)

    def test_nearby_same_edge_gap_is_reported_but_not_repaired(self):
        data = source([way(1, [1, 2], self.path)])
        paths = [[self.path[0], (127.0005,37)], [(127.000505,37),self.path[1]]]
        original = copy.deepcopy((paths, data))
        result = inspect_source_network(paths, data)
        self.assertEqual('SAME_SOURCE_EDGE_NEARBY', result['joins'][0]['status'])
        self.assertEqual(original, (paths, data))

    def test_barrier_is_not_ignored(self):
        data = source([way(1, [1, 2], self.path), dict(type='node',id=1,tags={'barrier':'gate'})])
        self.assertNotEqual('PASS_SOURCE_GEOMETRY_ONLY', inspect_source_network([self.path], data)['status'])

    def test_spatial_index_preserves_local_matches_with_many_distant_edges(self):
        ways = [way(1,[1,2],self.path)]
        for i in range(1000):
            x=127.1+i*.00001
            ways.append(way(i+2,[i*2+3,i*2+4],[(x,37.1),(x+.000001,37.1)]))
        result=inspect_source_network([self.path],source(ways),work_limit=20000)
        self.assertEqual('PASS_SOURCE_GEOMETRY_ONLY',result['status'])
        self.assertEqual(1.0,result['coverage'])
