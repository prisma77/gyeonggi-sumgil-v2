"""Find an enclosing cycle on sourced pedestrian edges; no routing API calls."""
import argparse
import heapq
import json
import math
from pathlib import Path

from prepare_site import draft, network
from probe import inside, meters
from validate_lap import inspect_lap, intersection, projected


def plan(source, water_id, start_node, reviewed=False):
    coordinates, edges, ways = network(source)
    target = next(e for e in source["osm"]["elements"] if e["type"] == "way" and e["id"] == water_id)
    boundary = [(p["lon"], p["lat"]) for p in target["geometry"]]
    origin = tuple(sum(p[i] for p in boundary[:-1]) / (len(boundary) - 1) for i in (0, 1))
    if not inside(origin, boundary):
        raise ValueError("Target mean is outside water; an independently reviewed interior point is needed")
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
    queue, distance, previous = [(0, start_node, 0)], {(start_node, 0): 0}, {}
    goal = None
    while queue:
        total, node, turn = heapq.heappop(queue)
        if total != distance[(node, turn)]:
            continue
        if node == start_node and abs(turn) == 1:
            goal = (node, turn)
            break
        for neighbor, length, lift in adjacency.get(node, []):
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
        for j in range(i + 3, len(chain)):
            if chain[j] != node:
                continue
            ring = chain[i:j + 1]
            if inspect_lap([[coordinates[n] for n in ring]], boundary)["status"] == "PASS_GEOMETRY_ONLY":
                candidates.append(ring)
    if not candidates:
        raise ValueError("No simple source ring enclosing the complete water boundary")
    cycle = min(candidates, key=lambda ns: sum(meters(coordinates[a], coordinates[b]) for a, b in zip(ns, ns[1:])))
    selection = {"name": "호수 외곽 보행망 순환 비교", "shape": "lake_loop", "water_way_id": water_id,
                 "node_ids": cycle, "notes": ["Existing directed source edges only; source geometry pass is not current access proof."]}
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--water-way", type=int, required=True)
    parser.add_argument("--start-node", type=int, required=True)
    parser.add_argument("--review-source-inputs", action="store_true",
                        help="Explicitly acknowledge independent input review; never approves current access")
    args = parser.parse_args()
    result = plan(json.loads(args.source.read_text(encoding="utf-8")), args.water_way, args.start_node,
                  reviewed=args.review_source_inputs)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"source_network_length_m": result["source_network_length_m"],
                      "sample_node_ids": result["sample_node_ids"]}))
