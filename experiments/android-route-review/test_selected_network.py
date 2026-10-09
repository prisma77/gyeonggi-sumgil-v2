"""Source/identity/topology boundaries; synthetic geometry and licensed fixtures, no live calls."""
import copy
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'kakao-walking'
sys.path.insert(0, str(ROOT))

from selected_network import SelectedNetwork, targets, build_candidates, restricted_source
from prepare_site import network
from bridge import ReviewService, load_catalog
from probe import meters, routing_inputs
from test_bridge import FakeClient
from test_probe import response


def fixture(name):
    return json.loads((ROOT / 'sources' / f'{name}.osm.json').read_text(encoding='utf-8-sig'))


class Places:
    def __init__(self, place): self.place = place
    def resolve(self, identifier):
        if identifier != self.place['id']: raise ValueError('Unknown selection')
        return dict(self.place)


class Source:
    def __init__(self, data): self.data, self.calls, self.limit = data, 0, 1
    def fetch(self, centre):
        if self.calls == self.limit: raise RuntimeError('Budget')
        self.calls += 1
        self.centre = centre
        return copy.deepcopy(self.data)


class SelectedNetworkTests(unittest.TestCase):
    def setUp(self):
        self.source = fixture('misa-walkways')
        park = next(e for e in self.source['osm']['elements'] if e['type'] == 'way' and e.get('tags', {}).get('name') == '미사호수공원')
        self.place = dict(id='selected-poi', name='미사호수공원', x=sum(p['lon'] for p in park['geometry'])/len(park['geometry']),
                          y=sum(p['lat'] for p in park['geometry'])/len(park['geometry']))
        self.places, self.provider = Places(self.place), Source(self.source)
        self.service = SelectedNetwork(self.places, self.provider)

    def acquired(self):
        return self.service.acquire(dict(place_id=self.place['id'], shape='lake_loop'))

    def test_unknown_place_or_arbitrary_coordinate_cannot_acquire(self):
        for req in [dict(place_id='wrong', shape='lake_loop'), dict(place_id=self.place['id'], shape='lake_loop', x=127),
                    dict(place_id=self.place['id'], shape='arbitrary')]:
            with self.assertRaises(ValueError): self.service.acquire(req)
        self.assertEqual(0, self.provider.calls)

    def test_source_uses_selected_public_poi_not_user_gps_or_profile(self):
        result = self.acquired()
        self.assertEqual([self.place['x'], self.place['y']], self.provider.centre)
        self.assertEqual(0, result['routing_calls_sent'])
        self.assertEqual('NOT_ACCEPTED', result['recommendation_quality'])
        self.assertTrue(result['targets'])
        self.assertTrue(all(t['match'] == 'NEARBY_UNNAMED_REQUIRES_CONFIRMATION' for t in result['targets']))

    def test_target_confirmation_is_required_and_expired_source_blocked(self):
        result = self.acquired()
        with self.assertRaises(ValueError):
            self.service.candidates(dict(place_id=self.place['id'], target_id='invented', distance_m=None))
        self.service.prepared['expires'] = time.monotonic()-1
        with self.assertRaises(ValueError):
            self.service.candidates(dict(place_id=self.place['id'], target_id=result['targets'][0]['id'], distance_m=None))

    def test_one_lap_is_not_default_distance_and_original_source_is_unchanged(self):
        original = copy.deepcopy(self.source)
        result = self.acquired()
        sites, meta = self.service.candidates(dict(place_id=self.place['id'], target_id=result['targets'][0]['id'], distance_m=None))
        self.assertTrue(sites)
        self.assertIsNone(meta['distance_m'])
        site = sites[0]
        self.assertEqual([], site['input_validation']['failures'])
        self.assertEqual(self.place['id'], site['selected_place_id'])
        self.assertEqual(self.source, original)
        raw_coords, raw_edges, _ = network(self.source)
        start, end, via, _ = routing_inputs(site)
        self.assertEqual(start, end); self.assertLessEqual(len(via), 5)
        self.assertTrue(all(p in raw_coords.values() for p in [start, *via]))
        self.assertTrue(all(edge in raw_edges for edge in zip(site['source_node_ids'], site['source_node_ids'][1:])))

    def test_three_km_lake_not_extended_with_repetitions(self):
        result = self.acquired()
        sites, meta = self.service.candidates(dict(place_id=self.place['id'], target_id=result['targets'][0]['id'], distance_m=3000))
        self.assertEqual([], sites)
        self.assertEqual('SOURCE_LAP_DISTANCE_MISMATCH', meta['status'])

    def test_invalid_distance_and_changed_place_are_rejected(self):
        result = self.acquired(); req = dict(place_id=self.place['id'], target_id=result['targets'][0]['id'], distance_m=None)
        for value in [True, float('nan'), 499, 5001, '3000']:
            with self.assertRaises(ValueError): self.service.candidates(dict(req, distance_m=value))
        self.places.place = dict(self.place, name='Another park')
        with self.assertRaises(ValueError): self.service.candidates(req)

    def test_named_water_at_other_place_is_not_silently_substituted(self):
        source = copy.deepcopy(self.source)
        for e in source['osm']['elements']:
            if e.get('tags', {}).get('natural') == 'water': e['tags']['name'] = 'Different lake'
        self.assertEqual([], targets(source, self.place, 'lake_loop'))

    def test_no_network_and_disconnection_do_not_insert_connector(self):
        target = self.acquired()['targets'][0]
        source = copy.deepcopy(self.source)
        source['osm']['elements'] = [e for e in source['osm']['elements'] if not e.get('tags', {}).get('highway')]
        _, sites, status = build_candidates(source, target, self.place, 'lake_loop', None)
        self.assertEqual([], sites); self.assertEqual('NO_USABLE_OR_BOUNDED_WALK_NETWORK', status)

    def test_edge_filter_only_removes_source_edges_and_preserves_raw_tags(self):
        target = self.acquired()['targets'][0]
        filtered = restricted_source(self.source, target, 'lake_loop')
        self.assertEqual(self.source['osm'], filtered['osm'])
        coords, edges, _ = network(filtered); raw_coords, raw_edges, _ = network(self.source)
        self.assertTrue(edges); self.assertTrue(set(edges) <= set(raw_edges))
        self.assertTrue(all(raw_coords[n] == p for n, p in coords.items()))

    def test_river_exact_name_preserved_bidirectional_anchors_distance(self):
        source = fixture('osan-walkways')
        base = json.loads((ROOT / 'drafts/osan.probe.json').read_text(encoding='utf-8-sig'))
        x, y = base['walk_points'][0]; place = dict(id='river', name='오산천', x=x, y=y)
        service = SelectedNetwork(Places(place), Source(source))
        result = service.acquire(dict(place_id='river', shape='river_out_and_back'))
        target = result['targets'][0]
        with self.assertRaises(ValueError): service.candidates(dict(place_id='river', target_id=target['id'], distance_m=None))
        sites, meta = service.candidates(dict(place_id='river', target_id=target['id'], distance_m=2500))
        self.assertEqual('SOURCE_CANDIDATES_ONLY', meta['status']); self.assertTrue(sites)
        for site in sites:
            start, end, via, _ = routing_inputs(site)
            self.assertEqual(start, end); self.assertLessEqual(len(via), 5)
            self.assertEqual(via, list(reversed(via)))
            self.assertTrue(2250 <= site['river_candidate']['source_expected_roundtrip_m'] <= 2750)

    def test_selected_profile_reaches_route_and_wrong_distance_fails(self):
        client = FakeClient(response([[(127, 37), (127.001, 37)]]))
        service = ReviewService(load_catalog(Path(__file__).with_name('catalog.json')), client, self.places, self.provider)
        acquired = service.acquire_place(dict(place_id=self.place['id'], shape='lake_loop'))
        generated = service.place_candidates(dict(place_id=self.place['id'], target_id=acquired['targets'][0]['id'], distance_m=1850))
        profile = generated['candidates'][0]
        site = service.profiles[profile['id']][1]
        # Synthetic provider follows the exact sourced cycle but deliberately reports wrong distance.
        client.payload = response([site['reference_walkway']])
        client.payload['route']['properties']['totalDistance'] = 400
        result = service.route(dict(id=profile['id'], mode='SHORTEST'))
        self.assertEqual(self.place['id'], result['selected_place_id'])
        self.assertIn('TARGET_DISTANCE_MISMATCH', result['inspection']['failures'])
        self.assertEqual('NOT_ACCEPTED', result['recommendation_quality'])
        self.assertTrue(result['inspection']['water_overlap_evidence']['bridge_source_available'])
        self.assertIn('CURRENT_ACCESS_UNVERIFIED', result['inspection']['water_overlap_evidence']['bridge_evidence'])
        self.assertEqual(1, client.calls)

    def test_river_oneway_barrier_or_conditional_access_cannot_be_returned(self):
        coords = [[127+i*.0001, 37] for i in range(101)]
        nodes = list(range(101))
        footway = dict(type='way', id=1, nodes=nodes, geometry=[dict(lon=x, lat=y) for x,y in coords], tags={'highway':'footway'})
        river = dict(type='way', id=2, nodes=[201,202], geometry=[dict(lon=127,lat=36.9998), dict(lon=127.01,lat=36.9998)],
                     tags={'waterway':'stream','name':'시험하천'})
        source = dict(source=dict(url='https://example.org/source',retrieved_at='2026-10-09T00:00:00Z',license='ODbL 1.0'),
                      osm=dict(elements=[footway,river]))
        place = dict(id='river',name='시험하천',x=127,y=37)
        target = targets(source,place,'river_out_and_back')[0]
        _, sites, _ = build_candidates(source,target,place,'river_out_and_back',1000)
        self.assertTrue(sites)
        for tags in [{'oneway:foot':'yes'}, {'foot:conditional':'no @ (night)'}]:
            restricted = copy.deepcopy(source);restricted['osm']['elements'][0]['tags'].update(tags)
            _, sites, _ = build_candidates(restricted,target,place,'river_out_and_back',1000)
            self.assertEqual([],sites)
        restricted = copy.deepcopy(source)
        restricted['osm']['elements'].append(dict(type='node',id=20,lon=coords[20][0],lat=37,tags={'barrier':'gate'}))
        _, sites, _ = build_candidates(restricted,target,place,'river_out_and_back',1000)
        self.assertEqual([],sites)

    def test_old_generated_profile_is_revoked_before_acquiring_another_source(self):
        client = FakeClient(response([[(127,37),(127.001,37)]]))
        service = ReviewService(load_catalog(Path(__file__).with_name('catalog.json')),client,self.places,self.provider)
        acquired = service.acquire_place(dict(place_id=self.place['id'],shape='lake_loop'))
        generated = service.place_candidates(dict(place_id=self.place['id'],target_id=acquired['targets'][0]['id'],distance_m=None))
        cid = generated['candidates'][0]['id']
        with self.assertRaises(RuntimeError): service.acquire_place(dict(place_id=self.place['id'],shape='lake_loop'))
        with self.assertRaises(ValueError): service.route(dict(id=cid,mode='SHORTEST'))
        self.assertEqual(0,client.calls)

    def test_fresh_source_survives_old_search_expiry_but_new_search_revokes(self):
        self.places.generation = 1
        acquired = self.acquired()
        self.places.resolve = lambda _: (_ for _ in ()).throw(ValueError('Search expired'))
        sites, _ = self.service.candidates(dict(place_id=self.place['id'],target_id=acquired['targets'][0]['id'],distance_m=None))
        self.assertTrue(sites)
        self.places.generation += 1
        with self.assertRaises(ValueError):
            self.service.ensure_current(self.place['id'],sites[0]['selected_source_id'])


if __name__ == '__main__': unittest.main()
