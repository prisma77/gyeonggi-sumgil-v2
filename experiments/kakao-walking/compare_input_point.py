"""Create an explicit alternative input using an existing OSM pedestrian node."""
import argparse
import json
from collections import deque
from pathlib import Path

from prepare_site import network
from probe import meters, point


def alternative(source, site, index, max_move=100):
    coordinates, edges, ways = network(source)
    original = site["sample_node_ids"][index]
    if point(site["walk_points"][index]) != coordinates[original]:
        raise ValueError("Input point does not match its original source node")
    adjacency = {}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)
    reachable, queue = {original}, deque([original])
    while queue:
        for node in adjacency.get(queue.popleft(), []):
            if node not in reachable:
                reachable.add(node)
                queue.append(node)
    allowed_nodes = set()
    for way in ways.values():
        tags = way["tags"]
        if tags.get("foot") in ("yes", "designated", "permissive") and tags.get("bridge", "no") == "no":
            allowed_nodes.update(way["nodes"])
    excluded = set(site["sample_node_ids"])
    candidates = (allowed_nodes & reachable) - excluded
    if not candidates:
        raise ValueError("No explicit pedestrian ground node in the same source component")
    selected = min(candidates, key=lambda n: meters(coordinates[original], coordinates[n]))
    moved = meters(coordinates[original], coordinates[selected])
    if moved > max_move:
        raise ValueError("Alternative exceeds the declared input-change limit")
    result = json.loads(json.dumps(site))
    result["sample_node_ids"][index] = selected
    result["walk_points"][index] = coordinates[selected]
    result["walk_points_reviewed"] = False
    result["review"]["status"] = "ALTERNATIVE_INPUT_DRAFT"
    result["input_change"] = {"index": index, "original_source_node": original,
                              "alternative_source_node": selected, "source_offset_m": round(moved, 1),
                              "method": "NEAREST_EXPLICIT_PEDESTRIAN_NON_BRIDGE_NODE_IN_SAME_SOURCE_COMPONENT",
                              "scope": "CONTROLLED_EXPERIMENT; NOT_AUTOMATIC_USER_REQUEST_SUBSTITUTION"}
    # Old shoreline offsets describe the original input; do not mislabel them.
    result.pop("shoreline_offset_m", None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("site", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--max-move", type=float, default=100)
    args = parser.parse_args()
    if not 0 <= args.index < 8 or not 0 < args.max_move <= 100:
        raise ValueError("Invalid source point index or declared change limit")
    result = alternative(json.loads(args.source.read_text(encoding="utf-8")),
                         json.loads(args.site.read_text(encoding="utf-8")), args.index, args.max_move)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result["input_change"]))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, IndexError):
        print("Alternative input preparation stopped; no substitution or live request performed.")
        raise SystemExit(2)
