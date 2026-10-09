"""Audit independent source nodes and directed connectivity, without routing calls."""
import argparse
from collections import deque
import json
from pathlib import Path

from prepare_site import network
from probe import inside, point, routing_inputs
from source_water import outer_boundary


def audit_inputs(site, source):
    coordinates, edges, ways = network(source)
    failures, warnings = [], ["CURRENT_ACCESS_AND_NODE_BARRIERS_UNVERIFIED"]
    if site["walk_source"] != source["source"]:
        failures.append("INPUT_SOURCE_METADATA_MISMATCH")
    ids = site.get("sample_node_ids", [])
    points = [point(p) for p in site["walk_points"]]
    minimum_points = 2 if "river_candidate" in site else 8
    if site.get("shape") not in ("lake_loop", "river_out_and_back") or len(points) < minimum_points or len(set(points)) != len(points):
        failures.append("INPUT_SHAPE_OR_SAMPLE_COUNT_INVALID")
    if len(ids) != len(points) or any(n not in coordinates or coordinates[n] != p for n, p in zip(ids, points)):
        failures.append("INPUT_POINT_NOT_AN_ELIGIBLE_SOURCE_NODE")
    water = [point(p) for p in site.get("water_boundary", [])]
    if site["shape"] == "lake_loop":
        try:
            boundary, reference = outer_boundary(source, site.get("water_way_id"), site.get("water_relation_id"))
            matched = (water == boundary and site.get("water_source") == source["source"] and
                       ("water_boundary_reference" not in site or site["water_boundary_reference"] == reference))
            if reference["inner_way_ids"]:
                warnings.append("WATER_INNER_AREAS_NOT_MODELED")
        except (ValueError, KeyError, TypeError):
            matched = False
        if not matched:
            failures.append("INPUT_WATER_BOUNDARY_SOURCE_MISMATCH")
    result = dict(status="FAIL" if failures else "SOURCE_MATCHED_REVIEW_REQUIRED", failures=failures,
                  unresolved=warnings, walking_access="UNVERIFIED", points=[], network_sequence="NOT_EVALUATED")
    if failures:
        return result
    start, _, via, _ = routing_inputs(site)
    if "river_candidate" in site:
        source_nodes = site.get("source_node_ids", [])
        if (source_nodes != ids or [point(p) for p in site.get("reference_walkway", [])] != points or
                any((a, b) not in edges or (b, a) not in edges for a, b in zip(ids, ids[1:]))):
            failures.append("RIVER_SOURCE_CORRIDOR_NOT_BIDIRECTIONAL")
            result["status"] = "FAIL"
    indexes = [points.index(p) for p in [start, *via]]
    adjacency = {}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)

    def reachable(a, b):
        seen, queue = {a}, deque([a])
        while queue:
            current = queue.popleft()
            if current == b:
                return True
            for n in adjacency.get(current, []):
                if n not in seen:
                    seen.add(n)
                    queue.append(n)
        return False

    requested = [ids[i] for i in indexes]
    missing = [i for i, (a, b) in enumerate(zip(requested, requested[1:] + requested[:1])) if not reachable(a, b)]
    result["network_sequence"] = "FAIL" if missing else "REACHABLE_IN_SOURCE_ONLY"
    result["unreachable_leg_indices"] = missing
    if missing:
        failures.append("INPUT_SEQUENCE_NOT_CONNECTED_IN_SOURCE")
        result["status"] = "FAIL"
    for label, index in zip(["S", "1", "2", "3", "4", "5"], indexes):
        node = ids[index]
        attached = [w for w in ways.values() if node in w["nodes"]]
        tagged_bridge = any(w.get("tags", {}).get("bridge", "no") != "no" for w in attached)
        conditional = any("conditional" in key for w in attached for key in w.get("tags", {}))
        result["points"].append(dict(label=label, sample_index=index, source_node_id=node,
                                     source_way_ids=sorted(w["id"] for w in attached),
                                     source_match=True, bridge_tagged=tagged_bridge,
                                     explicit_foot_access=any(w.get("tags", {}).get("foot") in ("yes", "designated", "permissive") for w in attached),
                                     conditional_access_tagged=conditional,
                                     within_source_water=inside(coordinates[node], water) if water else None))
    if any(p["bridge_tagged"] for p in result["points"]):
        warnings.append("INPUT_BRIDGE_CURRENT_ACCESS_UNVERIFIED")
    if any(p["conditional_access_tagged"] for p in result["points"]):
        warnings.append("INPUT_CONDITIONAL_ACCESS_REQUIRES_REVIEW")
    if any(p["within_source_water"] and not p["bridge_tagged"] for p in result["points"]):
        warnings.append("INPUT_WITHIN_WATER_WITHOUT_BRIDGE_TAG_REQUIRES_REVIEW")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    # Offline audit is available before human review; it cannot authorize a live probe.
    result = audit_inputs(json.loads(args.site.read_text(encoding="utf-8-sig")), json.loads(args.source.read_text(encoding="utf-8-sig")))
    print(json.dumps(result, ensure_ascii=True))  # Source IDs and checks only; no route coordinates.
    return 2 if result["failures"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        print("Source input audit stopped: inspect source and site schema. No network request sent.")
        raise SystemExit(2)
