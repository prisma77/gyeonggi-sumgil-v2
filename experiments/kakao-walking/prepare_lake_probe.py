"""Select existing shoreline walking nodes to test an API, not generate a lap."""
import argparse
import json
from pathlib import Path

from prepare_site import network
from probe import meters, point


def prepare(source, water_id):
    coordinates, edges, _ = network(source)
    water = next(e for e in source["osm"]["elements"] if e["type"] == "way" and e["id"] == water_id)
    if water.get("tags", {}).get("natural") != "water" or water["nodes"][0] != water["nodes"][-1]:
        raise ValueError("A closed source water way is required")
    boundary = [point([p["lon"], p["lat"]]) for p in water["geometry"]]
    distances = [0.0]
    for a, b in zip(boundary, boundary[1:]):
        distances.append(distances[-1] + meters(a, b))
    selected, offsets = [], []
    for i in range(8):
        index = min(range(len(boundary) - 1), key=lambda j: abs(distances[j] - distances[-1] * i / 8))
        node = min((n for n in coordinates if n not in selected),
                   key=lambda n: meters(coordinates[n], boundary[index]))
        offset = meters(coordinates[node], boundary[index])
        if offset > 75:
            raise ValueError("No sourced pedestrian candidate near a target shoreline sector")
        selected.append(node)
        offsets.append(round(offset, 1))
    # Preserve individual real edges. Never connect separate ways by proximity.
    segments = [[coordinates[a], coordinates[b]] for a, b in edges if a < b or (b, a) not in edges]
    provenance = dict(source["source"])
    return {"name": f"Lake OSM water way {water_id}", "shape": "lake_loop",
            "walk_source": provenance, "walk_points_reviewed": False,
            "walk_points": [coordinates[n] for n in selected], "sample_node_ids": selected,
            "reference_walkway": [], "reference_segments": segments,
            "reference_scope": "AVAILABLE_SOURCE_NETWORK; NOT_A_CONFIRMED_TARGET_LAP",
            "water_source": provenance, "water_boundary": boundary, "water_way_id": water_id,
            "shoreline_offset_m": offsets,
            "review": {"status": "DRAFT_API_INPUT_ONLY", "walking_access": "UNVERIFIED",
                       "field_check": "NOT_EXECUTED", "closed_walkway_found": False,
                       "warnings": ["WAYPOINTS_DO_NOT_PROVE_A_LAP", "CURRENT_ACCESS_AND_BARRIERS_NOT_CHECKED",
                                    "REFERENCE_NETWORK_MAY_INCLUDE_ALTERNATIVE_PARK_PATHS"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--water-way", type=int, required=True)
    args = parser.parse_args()
    site = prepare(json.loads(args.source.read_text(encoding="utf-8")), args.water_way)
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
