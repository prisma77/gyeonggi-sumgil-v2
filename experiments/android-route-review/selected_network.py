"""Bounded, transient selected-place OSM acquisition and source-only planning."""
import copy
from datetime import datetime, timezone
import heapq
import math
import secrets
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from prepare_site import network, eligible
from plan_source_cycle import plan as lake_plan
from source_water import outer_boundary
from probe import point, meters, segment_distance, inside
from select_network_anchors import select_network_anchors
from validate_lap import projected, intersection
from audit_inputs import audit_inputs

ENDPOINT = "https://overpass-api.de/api/interpreter"


class OverpassSource:
    def __init__(self, limit=4):
        self.calls, self.limit = 0, limit

    def fetch(self, centre):
        x, y = point(centre)
        if not (124 <= x <= 132 and 33 <= y <= 39):
            raise ValueError("Korean MVP extent required")
        if self.calls >= self.limit:
            raise RuntimeError("Source acquisition budget exhausted")
        dy = 1800 / 111195
        dx = dy / math.cos(math.radians(y))
        bbox = f"{y-dy:.7f},{x-dx:.7f},{y+dy:.7f},{x+dx:.7f}"
        # Full geometries and exact referenced nodes; no cropped or invented connectors.
        query = (f'[out:json][timeout:20][maxsize:33554432];('
                 f'way[highway]({bbox});way[natural=water]({bbox});'
                 f'way[waterway~"^(river|stream)$"]({bbox});'
                 f'way[leisure=park]({bbox});relation[natural=water]({bbox});'
                 f'node[barrier]({bbox}););(._;>;);out body geom;')
        self.calls += 1
        try:
            req = Request(ENDPOINT, data=urlencode({'data': query}).encode(),
                          headers={'User-Agent': 'GyeonggiSumgilRebootResearch/0.2',
                                   'Content-Type': 'application/x-www-form-urlencoded'})
            with urlopen(req, timeout=28) as response:
                raw = response.read(16_000_001)
            if len(raw) > 16_000_000:
                raise ValueError("Source size limit")
            data = json.loads(raw)
            if not isinstance(data.get('elements'), list) or data.get('remark') or len(data['elements']) > 60000:
                raise ValueError("Incomplete or oversized source")
        except (OSError, ValueError, TimeoutError):
            raise RuntimeError("Source acquisition failed; no retry or fallback") from None
        return dict(source=dict(url=ENDPOINT, retrieved_at=datetime.now(timezone.utc).isoformat(),
                                license='ODbL 1.0', license_url='https://www.openstreetmap.org/copyright',
                                attribution='© OpenStreetMap contributors',
                                osm_timestamp=data.get('osm3s', {}).get('timestamp_osm_base'),
                                scope='SELECTED_PUBLIC_POI_BBOX_1800M; NOT_USER_GPS'), osm=data)


def geometry(element):
    return [point([p['lon'], p['lat']]) for p in element.get('geometry', [])]


def line_offset(p, paths):
    return min((segment_distance(p, a, b) for path in paths for a, b in zip(path, path[1:])), default=math.inf)


def compact(name):
    return ''.join(name.split())


def targets(source, place, shape):
    centre, name = point([place['x'], place['y']]), compact(place['name'])
    result, river_ways = [], []
    for e in source['osm']['elements']:
        tags = e.get('tags', {})
        if shape == 'river_out_and_back':
            if (e['type'] == 'way' and tags.get('waterway') in ('river', 'stream')
                    and compact(tags.get('name', '')) == name and len(geometry(e)) >= 2):
                river_ways.append(e)
            continue
        if tags.get('natural') != 'water' or e['type'] not in ('way', 'relation'):
            continue
        try:
            boundary, _ = outer_boundary(source, e['id'] if e['type'] == 'way' else None,
                                         e['id'] if e['type'] == 'relation' else None)
        except (ValueError, KeyError, TypeError):
            continue
        offset = line_offset(centre, [boundary])
        named = compact(tags.get('name', '')) == name
        # Unnamed water is a candidate for explicit map confirmation, NEVER a name match.
        if offset > 350 or (not named and tags.get('name')):
            continue
        result.append(dict(kind=e['type'], osm_id=e['id'], name=tags.get('name') or '이름 없는 수역',
                           match='EXACT_NAME_AND_PROXIMITY' if named else 'NEARBY_UNNAMED_REQUIRES_CONFIRMATION',
                           poi_offset_m=round(offset, 1), paths=[boundary]))
    if shape == 'river_out_and_back' and river_ways:
        paths = [geometry(e) for e in river_ways]
        offset = line_offset(centre, paths)
        if offset <= 350:
            result.append(dict(kind='river_ways', osm_id=[e['id'] for e in river_ways], name=place['name'],
                               match='EXACT_NAME_AND_PROXIMITY', poi_offset_m=round(offset, 1), paths=paths))
    # A relation and its outer way represent one feature, not alternative lakes.
    relation_outers = {m['ref'] for e in source['osm']['elements'] if e['type'] == 'relation'
                       and any(t['kind'] == 'relation' and t['osm_id'] == e['id'] for t in result)
                       for m in e.get('members', []) if m.get('role') == 'outer' and m['type'] == 'way'}
    result = [t for t in result if not (t['kind'] == 'way' and t['osm_id'] in relation_outers)]
    return sorted(result, key=lambda t: (t['match'] != 'EXACT_NAME_AND_PROXIMITY', t['poi_offset_m']))[:5]


def restricted_source(source, target, shape):
    result = copy.deepcopy(source)
    barriers = {e['id'] for e in source['osm']['elements'] if e['type'] == 'node' and e.get('tags', {}).get('barrier')}
    water_lines = target['paths']
    boundary = water_lines[0] if shape == 'lake_loop' else None
    origin = water_lines[0][0]
    projected_water = [projected(p, origin) for p in water_lines]
    excluded, allowed = 0, set()
    for e in result['osm']['elements']:
        tags = e.get('tags', {})
        if e['type'] != 'way' or not eligible(tags):
            continue
        points = geometry(e)
        way_bad = (len(points) != len(e.get('nodes', [])) or len(points) < 2 or
               tags.get('tunnel', 'no') != 'no' or
               any('conditional' in k for k in tags))
        corridor = 180 if shape == 'lake_loop' else 100
        # Every vertex and sampled edge must remain near the confirmed target.
        for na, nb, a, b in zip(e.get('nodes', []), e.get('nodes', [])[1:], points, points[1:]):
            bad = way_bad or na in barriers or nb in barriers
            samples = [a, b, ((a[0]+b[0])/2, (a[1]+b[1])/2)]
            if any(line_offset(p, water_lines) > corridor or (boundary and inside(p, boundary)) for p in samples):
                bad = True
            line = projected([a, b], origin)
            if any(intersection(*line, c, d) in ('CROSS', 'OVERLAP')
                   for path in projected_water for c, d in zip(path, path[1:])):
                bad = True
            if bad:
                excluded += 1
            else:
                allowed.update(((na, nb), (nb, na)))
    # Keep source coordinates and tags intact. The graph intersects this derived filter with
    # real source edges and their foot directions; it can never add an edge.
    result['source_edge_allowlist'] = sorted(allowed)
    result['source'] = dict(source['source'], eligibility_policy='EXCLUDE_BARRIERS_TUNNELS_CONDITIONAL_WATER_CROSSING_OUTSIDE_CORRIDOR',
                            excluded_edge_count=excluded, corridor_m=180 if shape == 'lake_loop' else 100)
    return result


def build_candidates(source, target, place, shape, distance_m):
    coords, edges, _ = network(source)
    segments = sum(max(0, len(p)-1) for p in target['paths'])
    if not segments or segments > 1500 or len(edges)*segments > 4_000_000:
        return source, [], 'SOURCE_ANALYSIS_LIMIT_REACHED'
    source = restricted_source(source, target, shape)
    coords, edges, ways = network(source)
    if not coords or len(coords) > 10000 or len(edges) > 30000:
        return source, [], 'NO_USABLE_OR_BOUNDED_WALK_NETWORK'
    centre = point([place['x'], place['y']])
    start = min(coords, key=lambda n: meters(centre, coords[n]))
    if meters(centre, coords[start]) > 500:
        return source, [], 'NO_NEARBY_SOURCE_ENTRY'
    bounds = [distance_m * .9, distance_m * 1.1] if distance_m is not None else None
    if shape == 'lake_loop':
        try:
            site = lake_plan(source, target['osm_id'] if target['kind'] == 'way' else None, start,
                             water_relation_id=target['osm_id'] if target['kind'] == 'relation' else None)
        except (ValueError, KeyError, TypeError):
            return source, [], 'NO_COMPLETE_ENCLOSING_SOURCE_CYCLE'
        if bounds and not bounds[0] <= site['source_network_length_m'] <= bounds[1]:
            return source, [], 'SOURCE_LAP_DISTANCE_MISMATCH'
        sites = [site]
    else:
        adjacency = {}
        for a, b in edges:
            if (b, a) in edges:
                adjacency.setdefault(a, []).append((b, meters(coords[a], coords[b])))
        queue, distances, previous = [(0, start)], {start: 0}, {}
        while queue:
            length, node = heapq.heappop(queue)
            if length != distances[node] or length > bounds[1] / 2:
                continue
            for nxt, edge_len in adjacency.get(node, []):
                new = length + edge_len
                if new < distances.get(nxt, math.inf) and new <= bounds[1] / 2:
                    distances[nxt], previous[nxt] = new, node
                    heapq.heappush(queue, (new, nxt))
        endpoints = sorted((n for n, length in distances.items() if bounds[0] <= 2*length <= bounds[1]),
                           key=lambda n: abs(distances[n]*2-distance_m))
        sites, ends = [], []
        for end in endpoints:
            if any(meters(coords[end], coords[other]) < 75 for other in ends):
                continue
            chain = [end]
            while chain[-1] != start:
                chain.append(previous[chain[-1]])
            chain.reverse()
            if not 2 <= len(chain) <= 200:
                continue
            selection = select_network_anchors(chain, coords, edges, ways, 3)
            outbound = selection['indices']
            via = [*outbound, *reversed(outbound[:-1])]
            if not outbound or outbound[-1] != len(chain)-1 or len(via) > 5:
                continue
            path = [coords[n] for n in chain]
            expected = round(2*distances[end], 1)
            site = dict(name=place['name'], shape=shape, walk_source=source['source'], water_source={}, water_boundary=[],
                        walk_points_reviewed=False, source_node_ids=chain, sample_node_ids=chain,
                        walk_points=path, reference_walkway=path, reference_segments=[], source_way_ids=[],
                        source_network_length_m=round(distances[end], 1), selected_via_indices=via,
                        via_sequence_policy='MIRRORED_SOURCE_OUT_AND_BACK',
                        river_candidate=dict(source_expected_roundtrip_m=expected, distance_range_m=bounds,
                                             distance_only=True, source_estimated_minutes=round(expected/(4000/60), 1),
                                             assumed_walking_speed_kmh=4, departure_node_id=start, turnpoint_node_id=end,
                                             turnpoint_via_index=len(outbound)-1, via_node_ids=[chain[i] for i in via],
                                             waypoint_selection=selection))
            sites.append(site); ends.append(end)
            if len(sites) == 3:
                break
        if not sites:
            return source, [], 'SOURCE_ROUNDTRIP_DISTANCE_UNAVAILABLE'
    accepted = []
    for site in sites:
        site.update(name=place['name'], distance_conditions=dict(distance_range_m=bounds),
                    selected_place_id=place['id'], selected_place_name=place['name'],
                    confirmed_target=dict(kind=target['kind'], osm_id=target['osm_id'], match=target['match']),
                    departure_scope='SOURCE_WALK_NODE; USER_HOME_ACCESS_NOT_INCLUDED',
                    input_review_policy='AUTOMATED_SOURCE_AUDIT_ONLY; CURRENT_ACCESS_UNVERIFIED')
        site['input_validation'] = audit_inputs(site, source)
        if not site['input_validation']['failures']:
            site['walk_points_reviewed'] = True
            site['_source_data'] = source
            accepted.append(site)
    return source, accepted, 'SOURCE_CANDIDATES_ONLY' if accepted else 'SOURCE_AUDIT_FAILED'


class SelectedNetwork:
    def __init__(self, places, source_provider):
        self.places, self.provider = places, source_provider
        self.prepared = None

    def acquire(self, request):
        if not isinstance(request, dict) or set(request) != {'place_id', 'shape'} or request['shape'] not in ('lake_loop', 'river_out_and_back'):
            raise ValueError('Explicit selected place and shape required')
        place = self.places.resolve(request['place_id'])
        self.prepared = None
        source = self.provider.fetch([place['x'], place['y']])
        options = targets(source, place, request['shape'])
        for target in options:
            target['id'] = secrets.token_hex(12)
        self.prepared = dict(place=place, shape=request['shape'], source=source, targets=options, expires=time.monotonic()+600,
                             id=secrets.token_hex(12), search_generation=getattr(self.places, 'generation', None))
        return dict(place_id=place['id'], status='TARGET_CONFIRMATION_REQUIRED' if options else 'NO_MATCHED_TARGET',
                    targets=options, source=source['source'], routing_calls_sent=0,
                    source_calls_sent=self.provider.calls, source_call_limit=self.provider.limit,
                    recommendation_quality='NOT_ACCEPTED')

    def ensure_current(self, place_id, source_id=None):
        data = self.prepared
        if (not data or time.monotonic() > data['expires'] or place_id != data['place']['id'] or
                (source_id is not None and source_id != data['id'])):
            raise ValueError('Prepared selected source expired or changed')
        # A fresh acquisition has its own ten-minute lease. A new search revokes it, but
        # expiring the earlier search while acquiring source must not invalidate fresh source.
        if data['search_generation'] is not None:
            if getattr(self.places, 'generation', None) != data['search_generation']:
                raise ValueError('Place search changed; source confirmation revoked')
        elif self.places.resolve(place_id) != data['place']:
            raise ValueError('Selected place changed')
        return data

    def candidates(self, request):
        if not isinstance(request, dict) or set(request) != {'place_id', 'target_id', 'distance_m'}:
            raise ValueError('Confirmed target and explicit distance state required')
        data = self.ensure_current(request['place_id'])
        place = data['place']
        target = next((t for t in data['targets'] if t['id'] == request['target_id']), None)
        if target is None:
            raise ValueError('Explicit target confirmation required')
        distance = request['distance_m']
        if distance is not None and (type(distance) not in (int, float) or not math.isfinite(distance) or not 500 <= distance <= 5000):
            raise ValueError('Distance 500..5000m required')
        if data['shape'] == 'river_out_and_back' and distance is None:
            raise ValueError('River distance required; never replace one lap with default distance')
        source, sites, status = build_candidates(data['source'], target, place, data['shape'], distance)
        for site in sites:
            site['selected_source_id'] = data['id']
        return sites, dict(place_id=place['id'], status=status, source=source['source'], candidates=[],
                           distance_m=distance, routing_calls_sent=0, recommendation_quality='NOT_ACCEPTED')
