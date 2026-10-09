"""Explicit lap plans across selection and routing; synthetic metrics, no live calls."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'kakao-walking'
sys.path.insert(0, str(ROOT))

from bridge import ReviewService
from plan_source_cycle import plan
from prepare_site import network
from selected_network import SelectedNetwork, lake_walk_options, targets
from test_bridge import FakeClient
from test_probe import response
from test_source_cycle import fixture
from walk_plan_policy import make_walk_plan


class Places:
    def __init__(self, place):
        self.place = place

    def resolve(self, identifier):
        if identifier != self.place['id']:
            raise ValueError('Unknown selected place')
        return dict(self.place)


class Source:
    calls, limit = 0, 1

    def __init__(self, data):
        self.data = data

    def fetch(self, centre):
        self.calls += 1
        return copy.deepcopy(self.data)


class RepeatIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.source = fixture()
        self.base = plan(self.source, 99, 0)
        self.place = dict(id='synthetic-park', name='시험공원', x=127, y=37)
        self.target = targets(self.source, self.place, 'lake_loop')[0]
        self.places = Places(self.place)

    def planner(self, available):
        """Geometry stays one sourced ring; lengths are explicit mocked planner estimates."""
        def generate(source, water_id, start, distance_m, **kwargs):
            sites = []
            for target, length in available.items():
                if distance_m == target:
                    site = copy.deepcopy(self.base)
                    site.update(source_network_length_m=length,
                                walk_source=source['source'], water_source=source['source'])
                    sites.append(site)
            return dict(candidates=sites,
                        search=dict(method='SYNTHETIC_SEARCH; NOT_EXHAUSTIVE',
                                    requested_distance_m=distance_m, attempts=1,
                                    distinct_cycles_examined=len(sites), limit_reached=False),
                        status='SOURCE_CANDIDATES_ONLY' if sites else 'SOURCE_CYCLE_DISTANCE_NOT_FOUND')
        return generate

    def options(self, distance, repeats, available):
        with patch('selected_network.lake_plan_multiple', side_effect=self.planner(available)) as planner:
            result = lake_walk_options(self.source, self.target, 0, distance, repeats)
        return result, planner

    def test_ten_km_unavailable_single_lap_offers_explicit_five_km_twice(self):
        original = copy.deepcopy(self.source)
        result, planner = self.options(10000, True, {5000: 5000})
        self.assertEqual('SOURCE_CANDIDATES_ONLY', result['status'])
        self.assertEqual(1, len(result['candidates']))
        site = result['candidates'][0]
        self.assertEqual(2, site['walk_plan']['lap_count'])
        self.assertEqual(10000, site['walk_plan']['source_total_distance_m'])
        self.assertEqual([4500, 5500], site['distance_conditions']['distance_range_m'])
        self.assertEqual(self.base['source_node_ids'], site['source_node_ids'])
        self.assertEqual(self.base['reference_walkway'], site['reference_walkway'])
        self.assertEqual(original, self.source)
        self.assertEqual(10000, planner.call_args_list[0].args[3])
        self.assertIn(2, result['lap_search']['examined_lap_counts'])

    def test_disabled_repeat_does_not_silently_substitute_a_shorter_lap(self):
        result, planner = self.options(10000, False, {5000: 5000})
        self.assertEqual([], result['candidates'])
        self.assertEqual(1, planner.call_count)
        self.assertEqual([1], result['lap_search']['examined_lap_counts'])

    def test_blank_distance_preserves_one_lap_even_if_repeat_option_is_on(self):
        result, planner = self.options(None, True, {None: 1900})
        self.assertEqual(1, planner.call_count)
        self.assertIsNone(planner.call_args.args[3])
        walk_plan = result['candidates'][0]['walk_plan']
        self.assertEqual(1, walk_plan['lap_count'])
        self.assertIsNone(walk_plan['requested_total_distance_m'])

    def test_available_single_lap_has_priority_over_repeat_fallback(self):
        result, planner = self.options(10000, True, {10000: 10000, 5000: 5000})
        self.assertEqual(1, planner.call_count)
        self.assertTrue(result['candidates'])
        self.assertTrue(all(s['walk_plan']['lap_count'] == 1 for s in result['candidates']))

    def test_two_km_floor_does_not_accept_an_eighteen_hundred_metre_source_lap(self):
        result, _ = self.options(2000, False, {2000: 1800})
        self.assertEqual([], result['candidates'])

    def test_shared_search_deadline_stops_fallback_without_partial_success(self):
        with patch('selected_network.time.monotonic', side_effect=[0, 1, 21]), \
                patch('selected_network.lake_plan_multiple', side_effect=self.planner({})) as planner:
            result = lake_walk_options(self.source, self.target, 0, 10000, True)
        self.assertEqual(1, planner.call_count)
        self.assertEqual('SOURCE_CYCLE_SEARCH_LIMIT_REACHED', result['status'])
        self.assertEqual([], result['candidates'])
        self.assertTrue(result['lap_search']['limit_reached'])
        self.assertEqual(20, result['lap_search']['total_time_limit_seconds'])

    def test_nonboolean_repeat_and_out_of_range_total_are_rejected_before_search(self):
        service = SelectedNetwork(self.places, Source(self.source))
        acquired = service.acquire(dict(place_id=self.place['id'], shape='lake_loop'))
        request = dict(place_id=self.place['id'], target_id=acquired['targets'][0]['id'], distance_m=10000)
        with patch('selected_network.lake_plan_multiple') as planner:
            for value in (None, 0, 1, 'true', [], {}):
                with self.subTest(repeat=value), self.assertRaises(ValueError):
                    service.candidates(dict(request, allow_repeated_laps=value))
            for distance in (1999, 20001, True, '10000'):
                with self.subTest(distance=distance), self.assertRaises(ValueError):
                    service.candidates(dict(request, distance_m=distance))
        self.assertEqual(0, planner.call_count)

    def test_old_three_key_request_and_new_twenty_km_repeat_contract(self):
        service = SelectedNetwork(self.places, Source(self.source))
        acquired = service.acquire(dict(place_id=self.place['id'], shape='lake_loop'))
        request = dict(place_id=self.place['id'], target_id=acquired['targets'][0]['id'], distance_m=None)
        with patch('selected_network.lake_plan_multiple', side_effect=self.planner({None: 2100, 5000: 5000})):
            single, meta = service.candidates(request)
            repeated, total_meta = service.candidates(dict(request, distance_m=20000, allow_repeated_laps=True))
        self.assertEqual(1, single[0]['walk_plan']['lap_count'])
        self.assertEqual(4, repeated[0]['walk_plan']['lap_count'])
        self.assertEqual(20000, repeated[0]['walk_plan']['source_total_distance_m'])
        self.assertEqual(0, meta['routing_calls_sent'])
        self.assertEqual(0, total_meta['routing_calls_sent'])
        self.assertEqual([], repeated[0]['input_validation']['failures'])

    def test_selected_repeat_profile_exposes_plan_without_spending_route_calls(self):
        client = FakeClient(response([self.base['reference_walkway']]))
        service = ReviewService({}, client, self.places, Source(self.source))
        acquired = service.acquire_place(dict(place_id=self.place['id'], shape='lake_loop'))
        request = dict(place_id=self.place['id'], target_id=acquired['targets'][0]['id'],
                       distance_m=10000, allow_repeated_laps=True)
        with patch('selected_network.lake_plan_multiple', side_effect=self.planner({5000: 5000})):
            result = service.place_candidates(request)
        self.assertEqual(0, client.calls)
        profile = result['candidates'][0]
        self.assertEqual(2, profile['walk_plan']['lap_count'])
        self.assertEqual('SOURCE_PROPOSAL_ONLY', profile['walk_plan']['status'])
        self.assertIn('2바퀴', profile['label'])
        self.assertNotIn('paths', profile)

    @staticmethod
    def valid_inspection(distance):
        return dict(distance_m=distance, geometry_check='PASS', failures=[], unresolved=[],
                    lap_validation=dict(status='PASS_GEOMETRY_ONLY', failures=[], unresolved=[]))

    def routing_service(self, laps=2, target=10000, source_length=5000, split=False):
        site = copy.deepcopy(self.base)
        site.update(walk_plan=make_walk_plan(target, laps, source_length),
                    distance_conditions=dict(distance_range_m=[max(2000, target*.9)/laps, target*1.1/laps]),
                    input_validation=dict(failures=[]), _source_data=self.source)
        if split:
            # Two original provider requests cover one base circuit, regardless of lap count.
            coordinates, _, _ = network(self.source)
            ids = list(range(12))
            site.update(sample_node_ids=ids, walk_points=[coordinates[n] for n in ids])
            site['lake_route_parts'] = [[0,1,2,3,4,5,6], [6,7,8,9,10,11,0]]
            site['route_request_count'] = 2
        client = FakeClient(response([site['reference_walkway']]))
        client.limit = 2 if split else 1
        return ReviewService({'explicit-repeat': ('Synthetic repeat', site)}, client), site

    def test_repeat_route_uses_one_base_response_and_actual_api_total(self):
        service, site = self.routing_service()
        inspection = self.valid_inspection(4900)
        with patch('bridge.probe.inspect', return_value=inspection):
            result = service.route(dict(id='explicit-repeat', mode='SHORTEST'))
        self.assertEqual(1, service.client.calls)
        self.assertEqual(1, result['route_request_count'])
        self.assertEqual(1, len(result['paths']))
        self.assertEqual(site['reference_walkway'], result['paths'][0])
        checked = result['inspection']['walk_plan_validation']
        self.assertEqual(9800, checked['estimated_total_distance_m'])
        self.assertEqual('PASS_GEOMETRY_AND_DISTANCE_ONLY', checked['status'])
        self.assertEqual('UNVERIFIED', checked['walking_access'])
        self.assertEqual(site['walk_plan'], result['walk_plan'])

    def test_split_base_route_uses_two_requests_not_four_for_two_laps(self):
        service, site = self.routing_service(split=True)
        actual_paths = []

        def get(endpoint, params):
            service.client.calls += 1
            path = [(params['start_x'], params['start_y']), (params['end_x'], params['end_y'])]
            actual_paths.append(path)
            return 200, response([path]), .1

        service.client.get = get
        with patch('bridge.probe.inspect', return_value=self.valid_inspection(4900)):
            result = service.route(dict(id='explicit-repeat', mode='SHORTEST'))
        self.assertEqual(2, service.client.calls)
        self.assertEqual(2, result['route_request_count'])
        self.assertEqual(actual_paths, result['paths'])
        self.assertEqual(9800, result['inspection']['walk_plan_validation']['estimated_total_distance_m'])
        self.assertEqual(2, result['walk_plan']['lap_count'])

    def test_actual_repeat_total_still_fails_the_two_km_minimum(self):
        service, _ = self.routing_service(target=2000, source_length=1050)
        with patch('bridge.probe.inspect', return_value=self.valid_inspection(950)):
            result = service.route(dict(id='explicit-repeat', mode='SHORTEST'))
        checked = result['inspection']['walk_plan_validation']
        self.assertEqual('FAIL', checked['status'])
        self.assertEqual(1900, checked['estimated_total_distance_m'])
        self.assertIn('MIN_WALK_DISTANCE_NOT_REACHED', checked['failures'])
        self.assertEqual('FAIL', result['inspection']['geometry_check'])

    def test_repeat_plan_does_not_promote_a_base_with_repetition_or_crossing_defects(self):
        service, _ = self.routing_service(target=6000, source_length=3000)
        inspection = self.valid_inspection(2785)
        inspection.update(geometry_check='INCOMPLETE', exact_edge_retraced_distance_m=416,
                          unresolved=['REPETITION_AND_TOPOLOGY_REVIEW_REQUIRED'])
        inspection['lap_validation'].update(status='INCOMPLETE', unresolved=['LAP_NON_SIMPLE_GEOMETRY'])
        with patch('bridge.probe.inspect', return_value=inspection):
            result = service.route(dict(id='explicit-repeat', mode='SHORTEST'))
        checked = result['inspection']['walk_plan_validation']
        self.assertEqual('INCOMPLETE', checked['status'])
        self.assertEqual(5570, checked['estimated_total_distance_m'])
        self.assertIn('REPETITION_AND_TOPOLOGY_REVIEW_REQUIRED', checked['unresolved'])
        self.assertIn('LAP_NON_SIMPLE_GEOMETRY', checked['unresolved'])
        self.assertEqual('INCOMPLETE', result['inspection']['geometry_check'])
        self.assertEqual(1, service.client.calls)


if __name__ == '__main__':
    unittest.main()
