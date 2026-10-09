"""Compile a reviewed node sequence into an UNAPPROVED OSM experiment draft."""
import argparse
import json
from pathlib import Path

from probe import inside, meters, point, source_ok
from source_water import outer_boundary


def eligible(tags):
    if tags.get("area") == "yes" or tags.get("foot") in ("no", "private", "use_sidepath"):
        return False
    explicit = tags.get("foot") in ("yes", "designated", "permissive")
    if tags.get("access") in ("no", "private") and not explicit:
        return False
    highway = tags.get("highway")
    return highway in ("footway", "path", "pedestrian", "steps") or highway == "cycleway" and explicit


def network(source):
    if not source_ok(source.get("source")):
        raise ValueError("Licensed source and retrieval timestamp required")
    coordinates, edges, ways = {}, {}, {}
    allowlist = source.get('source_edge_allowlist')
    allowed = None if allowlist is None else {tuple(edge) for edge in allowlist}
    for way in source["osm"]["elements"]:
        if way["type"] != "way" or not eligible(way.get("tags", {})):
            continue
        nodes, geometry = way.get("nodes", []), way.get("geometry", [])
        if len(nodes) != len(geometry) or len(nodes) < 2:
            raise ValueError("Incomplete source way geometry")
        for node, coordinate in zip(nodes, geometry):
            xy = point([coordinate["lon"], coordinate["lat"]])
            if node in coordinates and coordinates[node] != xy:
                raise ValueError("Inconsistent source coordinate for shared node")
            coordinates[node] = xy
        ways[way["id"]] = way
        for a, b in zip(nodes, nodes[1:]):
            directions = [(a, b), (b, a)]
            foot_direction = way.get("tags", {}).get("oneway:foot")
            if foot_direction in ("yes", "1", "true"):
                directions = [(a, b)]
            elif foot_direction == "-1":
                directions = [(b, a)]
            for edge in directions:
                if allowed is None or edge in allowed:
                    edges.setdefault(edge, []).append(way["id"])
    if allowed is not None:
        used = {n for edge in edges for n in edge}
        coordinates = {n: p for n, p in coordinates.items() if n in used}
        used_ways = {wid for ids in edges.values() for wid in ids}
        ways = {wid: w for wid, w in ways.items() if wid in used_ways}
    return coordinates, edges, ways


def sample_nodes(node_ids, coordinates, count=8):
    unique = node_ids[:-1] if node_ids[0] == node_ids[-1] else node_ids
    if len(set(unique)) < count or len(set(unique)) != len(unique):
        raise ValueError("Need at least 8 distinct nodes and no unexplained repetitions")
    distances = [0.0]
    for a, b in zip(unique, unique[1:]):
        distances.append(distances[-1] + meters(coordinates[a], coordinates[b]))
    indexes = []
    for i in range(count):
        lower = indexes[-1] + 1 if indexes else 0
        upper = len(unique) - (count - i)
        nearest = min(range(lower, upper + 1),
                      key=lambda j: abs(distances[j] - distances[-1] * i / (count - 1)))
        indexes.append(nearest)
    if len(set(indexes)) != count:
        raise ValueError("Source nodes cannot supply distinct spaced experiment points")
    return [unique[i] for i in indexes]


def draft(source, selection):
    coordinates, edges, ways = network(source)
    nodes = selection["node_ids"]
    shape = selection["shape"]
    if shape not in ("lake_loop", "river_out_and_back") or len(nodes) < 8:
        raise ValueError("Invalid shape or insufficient source nodes")
    selected_ways = []
    for edge in zip(nodes, nodes[1:]):
        if edge not in edges:
            raise ValueError("Sequence contains an unmapped or forbidden connector")
        selected_ways.append(edges[edge][0])
    if shape == "lake_loop" and nodes[0] != nodes[-1]:
        raise ValueError("A lake draft must close on the exact source node")
    if shape == "river_out_and_back" and nodes[0] == nodes[-1]:
        raise ValueError("A river draft specifies the outbound segment only")
    path = [coordinates[n] for n in nodes]
    water = []
    if shape == "lake_loop":
        water, water_reference = outer_boundary(source, selection.get("water_way_id"), selection.get("water_relation_id"))
        if not all(inside(p, path) for p in water):
            raise ValueError("Selected source sequence does not enclose target boundary")
    sampled = sample_nodes(nodes, coordinates)
    provenance = dict(source["source"])
    result = {"name": selection["name"], "shape": shape, "walk_source": provenance,
              "walk_points_reviewed": False, "walk_points": [coordinates[n] for n in sampled],
              "reference_walkway": path, "water_source": provenance if water else {},
              "water_boundary": water, "source_node_ids": nodes,
              "sample_node_ids": sampled, "source_way_ids": sorted(set(selected_ways)),
              "source_network_length_m": round(sum(meters(a, b) for a, b in zip(path, path[1:])), 1),
              "review": {"status": "DRAFT", "walking_access": "UNVERIFIED", "field_check": "NOT_EXECUTED",
                         "warnings": ["OSM_CONNECTION_IS_NOT_CURRENT_ACCESS_PROOF",
                                      "BARRIERS_AND_CONDITIONAL_ACCESS_NOT_CHECKED",
                                      "KAKAO_RESPONSE_NOT_TESTED",
                                      "SOURCE_NODE_SPACING_MAY_BE_UNEVEN"]},
              "selection_notes": selection.get("notes", [])}
    if water:
        key = "water_relation_id" if "water_relation_id" in selection else "water_way_id"
        result[key] = selection[key]
        result["water_boundary_reference"] = water_reference
        if water_reference["inner_way_ids"]:
            result["review"]["warnings"].append("WATER_INNER_AREAS_NOT_MODELED")
        result["review"]["warnings"].append("ENCLOSURE_CHECK_IS_NOT_FULL_TOPOLOGY_PROOF")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("selection", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = draft(json.loads(args.source.read_text(encoding="utf-8")),
                   json.loads(args.selection.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"draft": str(args.output), "source_nodes": len(result["source_node_ids"]),
                      "source_network_length_m": result["source_network_length_m"],
                      "live_probe_ready": False}, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        print("Draft preparation stopped: inspect source, selection, topology and new output path.")
        raise SystemExit(2)
