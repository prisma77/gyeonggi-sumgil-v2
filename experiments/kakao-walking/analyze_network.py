"""Inspect OSM topology offline; emit review candidates, never accepted courses."""
import argparse
import json
from collections import deque
from pathlib import Path

from prepare_site import network
from probe import inside, meters


def tree_path(tree, start, end):
    parents, queue = {start: None}, deque([start])
    while queue:
        node = queue.popleft()
        if node == end:
            result = [node]
            while parents[result[-1]] is not None:
                result.append(parents[result[-1]])
            return list(reversed(result))
        for neighbor in tree.get(node, []):
            if neighbor not in parents:
                parents[neighbor] = node
                queue.append(neighbor)
    return None


def enclosure_candidates(source, water_id):
    coordinates, edges, _ = network(source)
    target = next(e for e in source["osm"]["elements"] if e["type"] == "way" and e["id"] == water_id)
    water = [(p["lon"], p["lat"]) for p in target["geometry"]]
    tree, cycles = {}, []
    for a, b in sorted(edges):
        if a >= b or (b, a) not in edges:
            continue
        chain = tree_path(tree, a, b)
        if chain is None:
            tree.setdefault(a, []).append(b)
            tree.setdefault(b, []).append(a)
        else:
            polygon = [coordinates[n] for n in chain]
            if len(chain) >= 8 and all(inside(p, polygon) for p in water):
                nodes = chain + [a]
                cycles.append({"node_ids": nodes,
                               "source_network_length_m": round(sum(meters(coordinates[x], coordinates[y])
                                                                     for x, y in zip(nodes, nodes[1:])), 1)})
    return sorted(cycles, key=lambda c: c["source_network_length_m"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--water-way", type=int, required=True)
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    cycles = enclosure_candidates(source, args.water_way)
    print(json.dumps({"candidate_count": len(cycles), "status": "UNREVIEWED_SOURCE_TOPOLOGY",
                      "candidates": cycles}, ensure_ascii=True))


if __name__ == "__main__":
    main()
