"""Select existing shoreline walking nodes to test an API, not generate a lap."""
import argparse
import json
from pathlib import Path

from prepare_site import network
from probe import meters, point
from source_water import outer_boundary


def prepare(source, water_id=None, relation_id=None, ground_only=False):
    coordinates, edges, ways = network(source)
    boundary, water_reference = outer_boundary(source, water_id, relation_id)
    allowed = set(coordinates)
    if ground_only:
        from probe import inside
        bridge_nodes = {n for way in ways.values() if way.get("tags", {}).get("bridge", "no") != "no" for n in way["nodes"]}
        allowed -= bridge_nodes
        allowed = {n for n in allowed if not inside(coordinates[n], boundary)}
    distances = [0.0]
    for a, b in zip(boundary, boundary[1:]):
        distances.append(distances[-1] + meters(a, b))
    selected, offsets = [], []
    for i in range(8):
        index = min(range(len(boundary) - 1), key=lambda j: abs(distances[j] - distances[-1] * i / 8))
        node = min((n for n in allowed if n not in selected),
                   key=lambda n: meters(coordinates[n], boundary[index]))
        offset = meters(coordinates[node], boundary[index])
        if offset > 75:
            raise ValueError("No sourced pedestrian candidate near a target shoreline sector")
        selected.append(node)
        offsets.append(round(offset, 1))
    # Preserve individual real edges. Never connect separate ways by proximity.
    segments = [[coordinates[a], coordinates[b]] for a, b in edges if a < b or (b, a) not in edges]
    provenance = dict(source["source"])
    result = {"name": f"Lake OSM water {'relation' if relation_id else 'way'} {relation_id or water_id}", "shape": "lake_loop",
            "walk_source": provenance, "walk_points_reviewed": False,
            "walk_points": [coordinates[n] for n in selected], "sample_node_ids": selected,
            "reference_walkway": [], "reference_segments": segments,
            "reference_scope": "AVAILABLE_SOURCE_NETWORK; NOT_A_CONFIRMED_TARGET_LAP",
            "water_source": provenance, "water_boundary": boundary, "water_boundary_reference": water_reference,
            "shoreline_offset_m": offsets,
            "review": {"status": "DRAFT_API_INPUT_ONLY", "walking_access": "UNVERIFIED",
                       "field_check": "NOT_EXECUTED", "closed_walkway_found": False,
                       "warnings": ["WAYPOINTS_DO_NOT_PROVE_A_LAP", "CURRENT_ACCESS_AND_BARRIERS_NOT_CHECKED",
                                    "REFERENCE_NETWORK_MAY_INCLUDE_ALTERNATIVE_PARK_PATHS"]}}
    result["water_relation_id" if relation_id is not None else "water_way_id"] = relation_id if relation_id is not None else water_id
    if water_reference["inner_way_ids"]:
        result["review"]["warnings"].append("WATER_INNER_AREAS_NOT_MODELED")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    water_group = parser.add_mutually_exclusive_group(required=True)
    water_group.add_argument("--water-way", type=int)
    water_group.add_argument("--water-relation", type=int)
    parser.add_argument("--ground-only", action="store_true")
    args = parser.parse_args()
    site = prepare(json.loads(args.source.read_text(encoding="utf-8")), args.water_way,
                   args.water_relation, args.ground_only)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(site, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"sample_node_ids": site["sample_node_ids"], "shoreline_offset_m": site["shoreline_offset_m"],
                      "reference_segments": len(site["reference_segments"]), "closed_walkway_found": False}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, StopIteration):
        print("Lake input preparation stopped. Inspect licensed source and target water geometry.")
        raise SystemExit(2)
