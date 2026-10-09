"""Explain source-water overlaps without repairing a route or approving a bridge."""
from prepare_site import eligible
from probe import inside, point, samples, segment_distance
from source_route_evidence import safe_network


def inspect_water_overlap(paths, water, source=None):
    result = dict(scope='SAMPLED_API_GEOMETRY_VS_SOURCE_WATER; NOT_FIELD_OBSERVATION',
                  sample_spacing_max_m=10, status='NOT_EVALUATED', source_bridge_sample_tolerance_m=5,
                  bridge_evidence='SOURCE_TAGS_ONLY; CURRENT_ACCESS_UNVERIFIED', steps=[], unresolved=[])
    if len(water) < 3:
        result['unresolved'] = ['TARGET_WATER_BOUNDARY_MISSING']
        return result
    boundary = list(zip(water, water[1:] + water[:1]))
    bridges = []
    connected_bridges = []
    result['bridge_source_available'] = source is not None
    if source is not None:
        try:
            coords, edges, ways = safe_network(source)
        except (KeyError, TypeError, ValueError):
            coords, edges, ways = {}, {}, {}
        neighbors = {}
        bridge_edges = {}
        for a, b in edges:
            neighbors.setdefault(a, set()).add(b)
            neighbors.setdefault(b, set()).add(a)
            for wid in edges[a, b]:
                bridge_edges.setdefault(wid, []).append((coords[a], coords[b]))
        for way in source['osm']['elements']:
            tags = way.get('tags', {})
            if way['type'] == 'way' and eligible(tags) and tags.get('bridge', 'no') != 'no':
                geometry = [point([p['lon'], p['lat']]) for p in way.get('geometry', [])]
                bridges.extend(zip(geometry, geometry[1:]))
                nodes = way.get('nodes', [])
                try:
                    above_water_layer = int(tags.get('layer', '')) > 0
                except (ValueError, TypeError):
                    above_water_layer = False
                if (len(nodes) == len(geometry) and len(nodes) >= 2 and above_water_layer
                        and len(neighbors.get(nodes[0], ())) >= 2 and len(neighbors.get(nodes[-1], ())) >= 2
                        and not inside(geometry[0], water) and not inside(geometry[-1], water)):
                    connected_bridges.extend(bridge_edges.get(way['id'], []))
    if len(boundary)+len(bridges)+len(connected_bridges) > 5000:
        result['unresolved'] = ['WATER_OVERLAP_ANALYSIS_LIMIT_REACHED']
        return result
    total = matched = connected = 0
    maximum = 0.0
    cost = 0
    for index, path in enumerate(paths):
        hits = bridge_hits = connected_hits = 0
        depth = 0.0
        for a, b in zip(path, path[1:]):
            for p in samples(a, b):
                cost += len(boundary)+len(bridges)+len(connected_bridges)
                if cost > 2_000_000:
                    result['unresolved'] = ['WATER_OVERLAP_ANALYSIS_LIMIT_REACHED']
                    return result  # No partial sample count is reported as a complete check.
                if not inside(p, water):
                    continue
                hits += 1
                depth = max(depth, min(segment_distance(p, c, d) for c, d in boundary))
                if any(segment_distance(p, c, d) <= 5 for c, d in bridges):
                    bridge_hits += 1
                if any(segment_distance(p, c, d) <= 5 and
                       (b[0]-a[0])*(d[0]-c[0]) + (b[1]-a[1])*(d[1]-c[1]) > 0 for c, d in connected_bridges):
                    connected_hits += 1
        if hits:
            result['steps'].append(dict(step=index+1, inside_source_water_samples=hits,
                                        near_source_bridge_samples=bridge_hits, max_inside_offset_m=round(depth, 3)))
            total += hits; matched += bridge_hits; connected += connected_hits; maximum = max(maximum, depth)
    result.update(status=('SOURCE_BRIDGE_MATCHED_GEOMETRY_ONLY' if total == connected else 'REVIEW_REQUIRED') if total else 'NO_SAMPLED_OVERLAP',
                  inside_source_water_samples=total, near_source_bridge_samples=matched,
                  connected_source_bridge_samples=connected, unmatched_water_samples=total-connected,
                  max_inside_offset_m=round(maximum, 3))
    if total > connected:
        result['unresolved'] = ['WATER_CROSSING_REQUIRES_BRIDGE_CHECK']
    if connected:
        result['notes'] = ['SOURCE_BRIDGE_MATCH_CURRENT_ACCESS_AND_API_LAYER_UNVERIFIED']
    return result
