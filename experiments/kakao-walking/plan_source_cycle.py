"""Find an enclosing cycle on sourced pedestrian edges; no routing API calls."""
import argparse
import heapq
import json
import math
import time
from pathlib import Path

from prepare_site import draft, network
from probe import inside, meters
from validate_lap import inspect_lap, intersection, projected
from source_water import outer_boundary


def interior_reference(boundary):
    """Analytical winding origin only, never a walking coordinate or route vertex."""
    origin = tuple(sum(p[i] for p in boundary[:-1]) / (len(boundary) - 1) for i in (0, 1))
    if inside(origin, boundary):
        return origin
    # A concave polygon's mean can lie on land. Test exact interior scanline spans.
    levels = sorted({p[1] for p in boundary})
    candidates = []
    for low, high in zip(levels, levels[1:]):
        y = (low + high) / 2
        crossings = sorted(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                           for a, b in zip(boundary, boundary[1:]) if (a[1] > y) != (b[1] > y))
        if len(crossings) % 2:
            raise ValueError("Invalid source polygon scanline")
        for left, right in zip(crossings[::2], crossings[1::2]):
            candidate = ((left + right) / 2, y)
            if right > left and inside(candidate, boundary):
                candidates.append((right - left, candidate))
    if not candidates:
        raise ValueError("No interior reference for source polygon")
    return max(candidates)[1]


def cycle_graph(source, water_id, water_relation_id=None):
    coordinates, edges, ways = network(source)
    boundary, _ = outer_boundary(source, water_id, water_relation_id)
    origin = interior_reference(boundary)
    water_xy = projected(boundary, origin)
    angle = {n: math.atan2(p[1] - origin[1], (p[0] - origin[0]) * math.cos(math.radians(origin[1])))
             for n, p in coordinates.items()}
    adjacency = {}
    for a, b in edges:
        line = projected([coordinates[a], coordinates[b]], origin)
        if (inside(coordinates[a], boundary) or inside(coordinates[b], boundary) or
                any(intersection(*line, c, d) == "CROSS" for c, d in zip(water_xy, water_xy[1:]))):
            continue  # Geometric enclosure search; does not declare bridges unwalkable.
        delta = angle[b] - angle[a]
        lift = -1 if delta > math.pi else 1 if delta < -math.pi else 0
        adjacency.setdefault(a, []).append((b, meters(coordinates[a], coordinates[b]), lift))
    return coordinates, ways, boundary, adjacency


def find_cycle(coordinates, boundary, adjacency, start_node, banned=frozenset(), deadline=None):
    queue, distance, previous = [(0, start_node, 0)], {(start_node, 0): 0}, {}
    goal = None
    while queue:
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('Bounded cycle search exhausted')
        total, node, turn = heapq.heappop(queue)
        if total != distance[(node, turn)]:
            continue
        if node == start_node and abs(turn) == 1:
            goal = (node, turn)
            break
        for neighbor, length, lift in adjacency.get(node, []):
            if tuple(sorted((node, neighbor))) in banned:
                continue
            state = (neighbor, turn + lift)
            if abs(state[1]) > 1:
                continue
            proposed = total + length
            if proposed < distance.get(state, math.inf):
                distance[state], previous[state] = proposed, (node, turn)
                heapq.heappush(queue, (proposed, *state))
    if goal is None:
        raise ValueError("No enclosing source cycle found; never insert a connector")
    state, chain = goal, [goal[0]]
    while state != (start_node, 0):
        state = previous[state]
        chain.append(state[0])
    chain.reverse()
    candidates = []
    for i, node in enumerate(chain):
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('Bounded cycle validation exhausted')
        for j in range(i + 3, len(chain)):
            if chain[j] != node:
                continue
            ring = chain[i:j + 1]
            if inspect_lap([[coordinates[n] for n in ring]], boundary)["status"] == "PASS_GEOMETRY_ONLY":
                candidates.append(ring)
    if not candidates:
        raise ValueError("No simple source ring enclosing the complete water boundary")
    cycle = min(candidates, key=lambda ns: sum(meters(coordinates[a], coordinates[b]) for a, b in zip(ns, ns[1:])))
    return cycle


def cycle_draft(source, coordinates, ways, cycle, water_id, start_node, reviewed=False, water_relation_id=None):
    selection = {"name": "호수 외곽 보행망 순환 비교", "shape": "lake_loop",
                 "node_ids": cycle, "notes": ["Existing directed source edges only; source geometry pass is not current access proof."]}
    selection["water_relation_id" if water_relation_id is not None else "water_way_id"] = water_relation_id if water_relation_id is not None else water_id
    result = draft(source, selection)
    # Prefer ground nodes on this exact cycle, in the same order, without inventing coordinates.
    bridge_nodes = {n for way in ways.values() if way.get("tags", {}).get("bridge", "no") != "no" for n in way["nodes"]}
    ground = [n for n in cycle[:-1] if n not in bridge_nodes]
    if len(ground) < 8:
        raise ValueError("Insufficient distinct ground input nodes on source cycle")
    nearest = min(range(len(cycle) - 1), key=lambda i: meters(coordinates[cycle[i]], coordinates[start_node])
                  if cycle[i] not in bridge_nodes else math.inf)
    cycle = cycle[nearest:-1] + cycle[:nearest] + [cycle[nearest]]
    distances = [0.0]
    for a, b in zip(cycle, cycle[1:]):
        distances.append(distances[-1] + meters(coordinates[a], coordinates[b]))
    sampled, last_index = [], -1
    for sector in range(8):
        possible = [i for i in range(last_index + 1, len(cycle) - 1) if cycle[i] not in bridge_nodes]
        # Leave enough distinct ground nodes for all remaining sectors.
        possible = possible[:len(possible) - (7 - sector)]
        if not possible:
            raise ValueError("Insufficient ordered ground sector samples")
        index = min(possible, key=lambda i: abs(distances[i] - distances[-1] * sector / 8))
        sampled.append(cycle[index])
        last_index = index
    result.update(source_node_ids=cycle, sample_node_ids=sampled,
                  walk_points=[coordinates[n] for n in sampled], reference_walkway=[coordinates[n] for n in cycle],
                  reference_segments=[], walk_points_reviewed=reviewed,
                  input_change={"method": "ENCLOSING_SOURCE_CYCLE_GROUND_SECTORS",
                                "original_source_node": start_node, "alternative_start_node": cycle[0],
                                "scope": "EXPLICIT_SAME_PLACE_COMPARISON; NOT_AUTOMATIC_USER_REQUEST_SUBSTITUTION"})
    result["review"]["status"] = "SOURCE_GEOMETRY_CHECKED; CURRENT_ACCESS_UNVERIFIED"
    result["selection_notes"].append("Start explicitly moved to source cycle ground entry; no silently substituted user departure.")
    return result


def plan(source, water_id, start_node, reviewed=False, water_relation_id=None):
    coordinates, ways, boundary, adjacency = cycle_graph(source, water_id, water_relation_id)
    cycle = find_cycle(coordinates, boundary, adjacency, start_node)
    return cycle_draft(source, coordinates, ways, cycle, water_id, start_node, reviewed, water_relation_id)


def alternate_arc(adjacency, start, end, banned, forbidden, deadline, budget):
    """Shortest actual directed alternative; other cycle nodes may not be revisited."""
    queue, distances, previous = [(0, start)], {start: 0}, {}
    while queue:
        if time.monotonic() >= deadline or budget[0] <= 0:
            raise TimeoutError('Bounded arc search exhausted')
        budget[0] -= 1
        length, node = heapq.heappop(queue)
        if length != distances[node]:
            continue
        if node == end:
            path = [end]
            while path[-1] != start:
                path.append(previous[path[-1]])
            return path[::-1]
        for nxt, edge_length, _ in adjacency.get(node, []):
            if nxt in forbidden or tuple(sorted((node, nxt))) in banned:
                continue
            proposed = length + edge_length
            if proposed < distances.get(nxt, math.inf):
                distances[nxt], previous[nxt] = proposed, node
                heapq.heappush(queue, (proposed, nxt))
    return None


def distance_cycles(source, water_id, start, distance_m, maximum, relation,
                    coordinates, ways, boundary, adjacency, deadline, max_attempts, max_seconds):
    """Combine outward source arcs instead of repeatedly returning the shortest ring."""
    found, seen, lengths = [], set(), []
    attempts = path_attempts = serial = 0
    path_limit, work_limit = 256, 200_000
    budget = [work_limit]
    limited, stop = False, 'QUEUE_EMPTY'
    pending = []
    def admit(cycle):
        nonlocal serial
        signature = frozenset(tuple(sorted(edge)) for edge in zip(cycle, cycle[1:]))
        if signature in seen:
            return
        seen.add(signature)
        length = sum(meters(coordinates[a], coordinates[b]) for a, b in zip(cycle, cycle[1:]))
        lengths.append(length)
        if distance_m*.9 <= length <= distance_m*1.1:
            try:
                found.append(cycle_draft(source, coordinates, ways, cycle, water_id, start,
                                         water_relation_id=relation))
            except ValueError:
                pass
        serial += 1
        heapq.heappush(pending, (abs(length-distance_m), serial, length, cycle))
    if max_attempts == 0 or time.monotonic() >= deadline:
        limited, stop = True, 'ATTEMPT_LIMIT' if max_attempts == 0 else 'TIME_LIMIT'
    else:
        try:
            admit(find_cycle(coordinates, boundary, adjacency, start, deadline=deadline))
        except TimeoutError:
            limited, stop = True, 'TIME_LIMIT'
        except ValueError:
            pass
    while pending and not limited:
        if attempts >= max_attempts or time.monotonic() >= deadline:
            limited, stop = True, 'ATTEMPT_LIMIT' if attempts >= max_attempts else 'TIME_LIMIT'
            break
        _, _, old_length, cycle = heapq.heappop(pending)
        attempts += 1
        junctions = [0] + [i for i, n in enumerate(cycle[1:-1], 1)
                          if len({v for v, _, _ in adjacency.get(n, [])}) > 2] + [len(cycle)-1]
        intervals = list(zip(junctions, junctions[1:]))
        if len(intervals) > 24:
            intervals = [intervals[i*len(intervals)//24] for i in range(24)]
        nodes = set(cycle[:-1])
        for first, last in intervals:
            if path_attempts >= path_limit or time.monotonic() >= deadline:
                limited, stop = True, 'PATH_LIMIT' if path_attempts >= path_limit else 'TIME_LIMIT'
                break
            path_attempts += 1
            a, b = cycle[first], cycle[last]
            banned = {tuple(sorted(edge)) for edge in zip(cycle[first:last], cycle[first+1:last+1])}
            try:
                alternative = alternate_arc(adjacency, a, b, banned, nodes-{a, b}, deadline, budget)
            except TimeoutError:
                limited, stop = True, 'WORK_LIMIT' if budget[0] <= 0 else 'TIME_LIMIT'
                break
            if not alternative:
                continue
            candidate = cycle[:first] + alternative + cycle[last+1:]
            length = sum(meters(coordinates[x], coordinates[y]) for x, y in zip(candidate, candidate[1:]))
            # Only useful expansions of this ring; no artificial padding or repeated nodes.
            if length <= old_length+.001 or length > distance_m*1.1 or len(set(candidate[:-1])) != len(candidate)-1:
                continue
            if inspect_lap([[coordinates[n] for n in candidate]], boundary)['status'] != 'PASS_GEOMETRY_ONLY':
                continue
            if time.monotonic() >= deadline:
                limited, stop = True, 'TIME_LIMIT'
                break
            admit(candidate)
        # Finish the current bounded batch before ranking its eligible candidates.
    # Longer valid rings may retain the requested length better with only five vias.
    found.sort(key=lambda site: -site['source_network_length_m'])
    found = found[:8]
    from select_cycle_anchors import select_cycle_anchors
    anchored = []
    for candidate in found:
        try:
            selected = select_cycle_anchors(source,candidate['source_node_ids'],time_limit=max(0,deadline-time.monotonic()))
        except (ValueError,TimeoutError):
            limited, stop = True, 'ANCHOR_ANALYSIS_LIMIT'
            continue
        cycle = candidate['source_node_ids']
        if candidate['source_network_length_m']-selected['source_shortcut_loss_m'] < distance_m*.9:
            try:
                selected = select_cycle_anchors(source,cycle,maximum=11,time_limit=max(0,deadline-time.monotonic()))
            except (ValueError,TimeoutError):
                limited,stop = True,'ANCHOR_ANALYSIS_LIMIT'
                continue
            ids = [cycle[0]]+[cycle[i] for i in selected['indices']]
            candidate.update(sample_node_ids=ids,walk_points=[coordinates[n] for n in ids],
                             lake_route_parts=[[0,1,2,3,4,5,6],[6,7,8,9,10,11,0]],
                             route_request_count=2,cycle_anchor_selection=selected)
            anchored.append(candidate)
            continue
        ids = [cycle[0]]+[cycle[i] for i in selected['indices']]
        # Eight-node experiment schema is retained; actual vias are the five selected nodes.
        extras = [n for n in candidate['sample_node_ids'] if n not in ids][:2]
        if len(extras) != 2:
            limited,stop = True,'ANCHOR_ANALYSIS_LIMIT'
            continue
        candidate.update(sample_node_ids=ids+extras,walk_points=[coordinates[n] for n in ids+extras],
                         via_sample_indices=[1,2,3,4,5],cycle_anchor_selection=selected)
        anchored.append(candidate)
    anchored.sort(key=lambda site: abs(site['source_network_length_m']-
                                       site['cycle_anchor_selection']['source_shortcut_loss_m']-distance_m))
    found = anchored[:maximum]
    metadata = dict(method='BOUNDED_SOURCE_ARC_REPLACEMENT; NOT_EXHAUSTIVE', attempts=attempts,
                    attempt_limit=max_attempts, time_limit_seconds=max_seconds, limit_reached=limited,
                    stop_reason=stop, path_attempts=path_attempts, path_attempt_limit=path_limit,
                    work_count=work_limit-budget[0], work_limit=work_limit,
                    distinct_cycles_examined=len(seen), requested_distance_m=distance_m,
                    examined_distance_range_m=[round(min(lengths), 1), round(max(lengths), 1)] if lengths else None)
    for candidate in found:
        candidate['cycle_search'] = metadata
    return dict(candidates=found, search=metadata,
                status='SOURCE_CANDIDATES_ONLY' if found else 'SOURCE_CYCLE_SEARCH_LIMIT_REACHED' if limited
                else 'SOURCE_CYCLE_DISTANCE_NOT_FOUND' if lengths else 'NO_COMPLETE_ENCLOSING_SOURCE_CYCLE')


def plan_multiple(source, water_id, start_node, distance_m=None, maximum=3,
                  water_relation_id=None, max_attempts=24, max_seconds=10):
    """Bounded source arc or edge-exclusion search; never an exhaustive proof."""
    if (type(maximum) is not int or not 1 <= maximum <= 3 or
            type(max_attempts) is not int or not 0 <= max_attempts <= 48 or
            type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or not 0 <= max_seconds <= 30 or
            distance_m is not None and (type(distance_m) not in (int,float) or not math.isfinite(distance_m) or distance_m <= 0)):
        raise ValueError('Bounded source cycle search and finite distance required')
    deadline = time.monotonic()+max_seconds
    coordinates, ways, boundary, adjacency = cycle_graph(source, water_id, water_relation_id)
    if distance_m is not None:
        return distance_cycles(source, water_id, start_node, distance_m, maximum, water_relation_id,
                               coordinates, ways, boundary, adjacency, deadline, max_attempts, max_seconds)
    degree = {n: len({edge[0] for edge in outgoing}) for n, outgoing in adjacency.items()}
    pending = [(0.0, 0, frozenset())]
    visited_bans, seen_cycles = {frozenset()}, set()
    found, lengths, attempts, serial = [], [], 0, 0
    bounds = (distance_m*.9, distance_m*1.1) if distance_m is not None else None
    limited = False
    stop_reason = 'QUEUE_EMPTY'
    while pending:
        if attempts >= max_attempts or time.monotonic() >= deadline:
            limited = True
            stop_reason = 'ATTEMPT_LIMIT' if attempts >= max_attempts else 'TIME_LIMIT'
            break
        _, _, banned = heapq.heappop(pending)
        attempts += 1
        try:
            cycle = find_cycle(coordinates, boundary, adjacency, start_node, banned, deadline)
        except TimeoutError:
            limited = True
            stop_reason = 'TIME_LIMIT'
            break
        except ValueError:
            continue
        signature = frozenset(tuple(sorted(edge)) for edge in zip(cycle, cycle[1:]))
        if signature in seen_cycles:
            continue
        seen_cycles.add(signature)
        length = sum(meters(coordinates[a],coordinates[b]) for a,b in zip(cycle,cycle[1:]))
        lengths.append(length)
        if bounds is None or bounds[0] <= length <= bounds[1]:
            try:
                found.append(cycle_draft(source, coordinates, ways, cycle, water_id, start_node,
                                         water_relation_id=water_relation_id))
            except ValueError:
                pass  # A graph cycle still needs distinct original input nodes and source audit.
            if len(found) >= maximum:
                stop_reason = 'CANDIDATE_LIMIT'
                break
        # Branch choices and evenly spaced edges provide bounded alternatives, never connectors.
        choices = [i for i,n in enumerate(cycle[:-1]) if degree.get(n,0)>2]
        choices += [i* (len(cycle)-1)//12 for i in range(12)]
        choices = list(dict.fromkeys(choices))[:24]
        for index in choices:
            edge = tuple(sorted((cycle[index],cycle[index+1])))
            child = banned | {edge}
            if child in visited_bans:
                continue
            visited_bans.add(child); serial += 1
            priority = abs(length-distance_m) if distance_m is not None else length
            heapq.heappush(pending,(priority,serial,child))
    found.sort(key=lambda site: abs(site['source_network_length_m']-distance_m) if distance_m is not None else site['source_network_length_m'])
    metadata = dict(method='BOUNDED_SOURCE_EDGE_EXCLUSION; NOT_EXHAUSTIVE', attempts=attempts,
                    attempt_limit=max_attempts, time_limit_seconds=max_seconds, limit_reached=limited,
                    stop_reason=stop_reason,
                    distinct_cycles_examined=len(seen_cycles), requested_distance_m=distance_m,
                    examined_distance_range_m=[round(min(lengths),1),round(max(lengths),1)] if lengths else None)
    for candidate in found:
        candidate['cycle_search'] = metadata
    return dict(candidates=found, search=metadata,
                status='SOURCE_CANDIDATES_ONLY' if found else 'SOURCE_CYCLE_SEARCH_LIMIT_REACHED' if limited
                else 'SOURCE_CYCLE_DISTANCE_NOT_FOUND' if lengths and bounds else 'NO_COMPLETE_ENCLOSING_SOURCE_CYCLE')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    water_group = parser.add_mutually_exclusive_group(required=True)
    water_group.add_argument("--water-way", type=int)
    water_group.add_argument("--water-relation", type=int)
    parser.add_argument("--start-node", type=int, required=True)
    parser.add_argument("--review-source-inputs", action="store_true",
                        help="Explicitly acknowledge independent input review; never approves current access")
    args = parser.parse_args()
    result = plan(json.loads(args.source.read_text(encoding="utf-8")), args.water_way, args.start_node,
                  reviewed=args.review_source_inputs, water_relation_id=args.water_relation)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"source_network_length_m": result["source_network_length_m"],
                      "sample_node_ids": result["sample_node_ids"]}))
