"""Explain source-water overlaps without repairing a route or approving a bridge."""
from prepare_site import eligible
from probe import inside, point, samples, segment_distance


def inspect_water_overlap(paths, water, source=None):
    result = dict(scope='SAMPLED_API_GEOMETRY_VS_SOURCE_WATER; NOT_FIELD_OBSERVATION',
                  sample_spacing_max_m=10, status='NOT_EVALUATED', source_bridge_sample_tolerance_m=5,
                  bridge_evidence='SOURCE_TAGS_ONLY; CURRENT_ACCESS_UNVERIFIED', steps=[], unresolved=[])
    if len(water) < 3:
        result['unresolved'] = ['TARGET_WATER_BOUNDARY_MISSING']
        return result
    boundary = list(zip(water, water[1:] + water[:1]))
    bridges = []
    result['bridge_source_available'] = source is not None
    if source is not None:
        for way in source['osm']['elements']:
            tags = way.get('tags', {})
            if way['type'] == 'way' and eligible(tags) and tags.get('bridge', 'no') != 'no':
                geometry = [point([p['lon'], p['lat']]) for p in way.get('geometry', [])]
                bridges.extend(zip(geometry, geometry[1:]))
    if len(boundary)+len(bridges) > 5000:
        result['unresolved'] = ['WATER_OVERLAP_ANALYSIS_LIMIT_REACHED']
        return result
    total = matched = 0
    maximum = 0.0
    cost = 0
    for index, path in enumerate(paths):
        hits = bridge_hits = 0
        depth = 0.0
        for a, b in zip(path, path[1:]):
            for p in samples(a, b):
                cost += len(boundary)+len(bridges)
                if cost > 2_000_000:
                    result['unresolved'] = ['WATER_OVERLAP_ANALYSIS_LIMIT_REACHED']
                    return result  # No partial sample count is reported as a complete check.
                if not inside(p, water):
                    continue
                hits += 1
                depth = max(depth, min(segment_distance(p, c, d) for c, d in boundary))
                if any(segment_distance(p, c, d) <= 5 for c, d in bridges):
                    bridge_hits += 1
        if hits:
            result['steps'].append(dict(step=index+1, inside_source_water_samples=hits,
                                        near_source_bridge_samples=bridge_hits, max_inside_offset_m=round(depth, 3)))
            total += hits; matched += bridge_hits; maximum = max(maximum, depth)
    result.update(status='REVIEW_REQUIRED' if total else 'NO_SAMPLED_OVERLAP',
                  inside_source_water_samples=total, near_source_bridge_samples=matched,
                  max_inside_offset_m=round(maximum, 3))
    if total:
        result['unresolved'] = ['WATER_CROSSING_REQUIRES_BRIDGE_CHECK']
    return result
