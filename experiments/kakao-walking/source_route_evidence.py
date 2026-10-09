"""Compare original API steps to eligible source edges; never create route geometry."""
from prepare_site import network
from probe import meters, samples, segment_projection
import math


def safe_network(source):
    # Candidate enclosure/corridor filtering is not the definition of all walkable source data.
    raw = {k: v for k, v in source.items() if k != 'source_edge_allowlist'}
    coordinates, edges, ways = network(raw)
    barriers = {e['id'] for e in source['osm']['elements']
                if e['type'] == 'node' and e.get('tags', {}).get('barrier')}
    allowed = {}
    for (a, b), ids in edges.items():
        if a in barriers or b in barriers:
            continue
        ids = [wid for wid in ids if ways[wid].get('tags', {}).get('tunnel', 'no') == 'no'
               and not any('conditional' in key for key in ways[wid].get('tags', {}))]
        if ids:
            allowed[a, b] = ids
    used = {n for edge in allowed for n in edge}
    return {n: p for n, p in coordinates.items() if n in used}, allowed, ways


def inspect_source_network(paths, source, tolerance=20, work_limit=2_000_000):
    result = dict(status='NOT_EVALUATED', scope='SOURCE_GEOMETRY_AND_FOOT_DIRECTION_ONLY; API_LAYER_AND_CURRENT_ACCESS_UNVERIFIED',
                  tolerance_m=tolerance, failures=[], unresolved=[], joins=[])
    if source is None:
        result['unresolved'] = ['SOURCE_WALK_NETWORK_MISSING']
        return result
    coords, edges, _ = safe_network(source)
    if not edges:
        result['unresolved'] = ['SOURCE_WALK_NETWORK_MISSING']
        return result
    segments = [(coords[a], coords[b],a,b) for a, b in edges]
    origin = next(iter(coords.values()))
    scale = 111195*math.cos(math.radians(origin[1]))
    def cell(p):
        return math.floor((p[0]-origin[0])*scale/50), math.floor((p[1]-origin[1])*111195/50)
    grid = {}
    cost = 0
    for a,b,na,nb in segments:
        low = cell((min(a[0],b[0])-tolerance/scale,min(a[1],b[1])-tolerance/111195))
        high = cell((max(a[0],b[0])+tolerance/scale,max(a[1],b[1])+tolerance/111195))
        cost += (high[0]-low[0]+1)*(high[1]-low[1]+1)
        if cost > work_limit:
            result['unresolved'] = ['SOURCE_NETWORK_ANALYSIS_LIMIT_REACHED']
            return result
        for x in range(low[0],high[0]+1):
            for y in range(low[1],high[1]+1):
                grid.setdefault((x,y),[]).append((a,b,na,nb))
    total = covered = 0.0
    for path in paths:
        for a, b in zip(path, path[1:]):
            length = meters(a, b)
            if not length:
                continue
            checks = list(samples(a, b))
            hits = 0
            for p in checks:
                nearby = grid.get(cell(p), [])
                cost += len(nearby)
                if cost > work_limit:
                    result['unresolved'] = ['SOURCE_NETWORK_ANALYSIS_LIMIT_REACHED']
                    return result
                if any(segment_projection(p, c, d)[0] <= tolerance and
                       (b[0]-a[0])*(d[0]-c[0]) + (b[1]-a[1])*(d[1]-c[1]) > 0
                       for c, d,_,_ in nearby):
                    hits += 1
            total += length
            covered += length*hits/len(checks)
    if not total:
        result['unresolved'] = ['SOURCE_NETWORK_GEOMETRY_MISSING']
        return result
    for index, (previous, following) in enumerate(zip(paths, paths[1:])):
        a, b = previous[-1], following[0]
        if meters(a, b) <= .001:
            continue
        undirected = {tuple(sorted((na,nb))) for _,_,na,nb in grid.get(cell(a),[])}
        cost += len(undirected)
        if cost > work_limit:
            result['unresolved'] = ['SOURCE_NETWORK_ANALYSIS_LIMIT_REACHED']
            return result
        matches = []
        for na, nb in undirected:
            da, ta = segment_projection(a, coords[na], coords[nb])
            db, tb = segment_projection(b, coords[na], coords[nb])
            if max(da, db) <= 2 and 0 < ta < 1 and 0 < tb < 1:
                matches.append((max(da, db), na, nb))
        matches.sort()
        unique = bool(matches) and (len(matches) == 1 or matches[1][0]-matches[0][0] > .2)
        result['joins'].append(dict(after_step=index+1, gap_m=meters(a, b),
                                    status='SAME_SOURCE_EDGE_NEARBY' if unique else 'SOURCE_CONNECTION_UNRESOLVED',
                                    route_geometry_unchanged=True))
    coverage = covered/total
    result.update(status='PASS_SOURCE_GEOMETRY_ONLY' if coverage >= .9 else 'FAIL_SOURCE_GEOMETRY',
                  coverage=round(coverage, 4), threshold=.9)
    if coverage < .9:
        result['failures'] = ['OUTSIDE_SOURCE_WALK_NETWORK_OR_FOOT_DIRECTION']
    return result
