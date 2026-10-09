"""Read-only Kakao walking spike. Responses are processed in memory, never cached."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
MODES = ("BROAD_FIRST", "SHORTEST", "ACCESSIBLE")
Point = tuple[float, float]  # longitude, latitude; WGS84


def read_key() -> str:
    value = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    if value:
        return value
    path = ROOT / "local.properties"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == "KAKAO_REST_API_KEY":
                return value.strip()
    return ""


def point(value: object) -> Point:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("Expected a WGS84 [longitude, latitude] pair")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
        raise ValueError("Coordinates must be finite numbers")
    x, y = map(float, value)
    if not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
        raise ValueError("Invalid WGS84 coordinates")
    return x, y


def meters(a: Point, b: Point) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 12_742_017.6 * math.asin(math.sqrt(min(1.0, h)))


def segment_projection(p: Point, a: Point, b: Point) -> tuple[float, float]:
    # Local projection for small walking areas, not a routing distance.
    scale_x = 111_195 * math.cos(math.radians(p[1]))
    ax, ay = (a[0] - p[0]) * scale_x, (a[1] - p[1]) * 111_195
    bx, by = (b[0] - p[0]) * scale_x, (b[1] - p[1]) * 111_195
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy))) if dx or dy else 0.0
    return math.hypot(ax + t * dx, ay + t * dy), t


def segment_distance(p: Point, a: Point, b: Point) -> float:
    return segment_projection(p, a, b)[0]


def ordered_visits(segments: list[tuple[Point, Point]], targets: list[Point], tolerance=30.0) -> bool:
    previous = 0.0
    for target in targets:
        offset, matches = 0.0, []
        for a, b in segments:
            length = meters(a, b)
            distance, fraction = segment_projection(target, a, b)
            progress = offset + fraction * length
            if distance <= tolerance and progress + tolerance >= previous:
                matches.append(progress)
            offset += length
        if not matches:
            return False
        previous = max(previous, min(matches))
    return True


def lake_topology_diagnostics(path: list[Point], water: list[Point], divisions=30) -> dict:
    """Sampled geometry diagnostics; no route creation or acceptance threshold."""
    if path[0] != path[-1]:
        return {"lake_topology_sampling": "NOT_EVALUATED_OPEN_GEOMETRY"}
    xmin, xmax = min(p[0] for p in water), max(p[0] for p in water)
    ymin, ymax = min(p[1] for p in water), max(p[1] for p in water)
    counts, enclosed, total = {}, 0, 0
    for i in range(divisions):
        for j in range(divisions):
            p = (xmin + (xmax - xmin) * (i + 0.5) / divisions,
                 ymin + (ymax - ymin) * (j + 0.5) / divisions)
            if not inside(p, water):
                continue
            total += 1
            enclosed += inside(p, path)
            angle = 0.0
            for a, b in zip(path, path[1:]):
                ax, ay, bx, by = a[0] - p[0], a[1] - p[1], b[0] - p[0], b[1] - p[1]
                angle += math.atan2(ax * by - ay * bx, ax * bx + ay * by)
            turns = round(angle / (2 * math.pi))
            counts[str(turns)] = counts.get(str(turns), 0) + 1
    return {"lake_topology_sampling": "DIAGNOSTIC_ONLY",
            "lake_water_grid_samples": total,
            "lake_water_grid_enclosed_fraction": round(enclosed / total, 4) if total else None,
            "lake_water_grid_winding_counts": counts}


def repeated_edge_diagnostics(paths: list[list[Point]]) -> dict:
    seen, repeated, total = set(), 0.0, 0.0
    for path in paths:
        for a, b in zip(path, path[1:]):
            length = meters(a, b)
            if not length:
                continue
            edge = tuple(sorted((tuple(round(x, 7) for x in a), tuple(round(x, 7) for x in b))))
            total += length
            if edge in seen:
                repeated += length
            seen.add(edge)
    return {"exact_edge_retraced_distance_m": round(repeated, 1),
            "exact_edge_retraced_fraction": round(repeated / total, 4) if total else 0,
            "repetition_diagnostic_scope": "LOWER_BOUND; DIFFERENT_VERTEX_SEGMENTATION_MAY_BE_MISSED"}


def inside(p: Point, polygon: list[Point]) -> bool:
    result = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]):
            crossing_x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if p[0] < crossing_x:
                result = not result
    return result


def samples(a: Point, b: Point):
    count = max(1, math.ceil(meters(a, b) / 10))
    for i in range(count):
        t = (i + 0.5) / count
        yield (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def corridor_coverage(path: list[Point], reference: list[Point], tolerance: float,
                      segments: list[tuple[Point, Point]] | None = None) -> float:
    segments = segments or list(zip(reference, reference[1:]))
    if not segments:
        return 0.0
    total = covered = 0.0
    for a, b in zip(path, path[1:]):
        length = meters(a, b)
        checks = list(samples(a, b))
        covered += length * sum(min(segment_distance(p, x, y) for x, y in segments) <= tolerance for p in checks) / len(checks)
        total += length
    return covered / total if total else 0.0


def number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Missing or invalid route distance/time")
    return float(value)


def inspect(payload: dict, start: Point, end: Point, shape: str = "point_to_point",
            reference: list[Point] | None = None, water: list[Point] | None = None,
            tolerance: float = 20.0, reference_segments: list[tuple[Point, Point]] | None = None,
            via: list[Point] | None = None, source: dict | None = None) -> dict:
    status = payload.get("status")
    result = {"api_status": status, "geometry_check": "NOT_EVALUATED",
              "walking_access": "UNVERIFIED", "field_check": "NOT_EXECUTED"}
    if status != "OK":
        return result
    failures, unknowns = [], []
    try:
        route = payload["route"]
        distance = number(route["properties"]["totalDistance"])
        duration = number(route["properties"]["totalTime"])
        legs = route["legs"]
        if not isinstance(legs, list) or not legs:
            raise ValueError("Missing legs")
        paths, leg_ends, leg_distance, leg_time = [], [], 0.0, 0.0
        for leg in legs:
            leg_distance += number(leg["properties"]["distance"])
            leg_time += number(leg["properties"]["time"])
            steps = leg["steps"]
            if not isinstance(steps, list) or not steps:
                raise ValueError("Missing steps")
            for step in steps:
                path = [point(p) for p in step["path"]["points"]]
                if len(path) < 2:
                    raise ValueError("Missing step geometry")
                paths.append(path)
            leg_ends.append(paths[-1][-1])
        seams = [meters(a[-1], b[0]) for a, b in zip(paths, paths[1:])]
        if any(gap > 10 for gap in seams):
            failures.append("DISCONNECTED_STEPS")
        # Preserve every step: do not insert an artificial connector across gaps.
        geometric_distance = sum(meters(a, b) for path in paths for a, b in zip(path, path[1:]))
        result.update(repeated_edge_diagnostics(paths))
        if distance <= 0 or duration <= 0 or geometric_distance <= 0:
            failures.append("ZERO_LENGTH_OR_TIME")
        if abs(distance - leg_distance) > max(2, distance * 0.01):
            failures.append("LEG_DISTANCE_MISMATCH")
        if abs(duration - leg_time) > max(2, duration * 0.01):
            failures.append("LEG_TIME_MISMATCH")
        if abs(distance - geometric_distance) > max(30, distance * 0.1):
            failures.append("GEOMETRY_DISTANCE_MISMATCH")
        if meters(start, paths[0][0]) > 30 or meters(end, paths[-1][-1]) > 30:
            failures.append("ENDPOINT_MISMATCH")
        path = [p for step in paths for p in step]
        if via:
            # Documentation does not promise one leg per waypoint; do not assume it.
            result["leg_count"] = len(leg_ends)
            if len(leg_ends) != len(via) + 1 or any(meters(target, observed) > 30
                                                       for target, observed in zip(via, leg_ends)):
                unknowns.append("LEG_WAYPOINT_ALIGNMENT_REQUIRES_REVIEW")
            ordered_segments = [(a, b) for step in paths for a, b in zip(step, step[1:])]
            result["waypoint_min_distance_m"] = [round(min(segment_distance(target, a, b)
                                                           for a, b in ordered_segments), 1) for target in via]
            if not ordered_visits(ordered_segments, via):
                failures.append("WAYPOINT_VISIT_OR_ORDER_MISMATCH")
            result["waypoint_order_check"] = "FAIL" if any(f.startswith("WAYPOINT_") for f in failures) else "PASS_WITHIN_30M"
        if shape in ("lake_loop", "river_out_and_back") and meters(path[0], path[-1]) > 30:
            failures.append("RETURN_NOT_CLOSED")
        if reference or reference_segments or shape != "point_to_point":
            if reference_segments or reference and len(reference) >= 2:
                # Per-step measurement excludes discontinuities from invented connectors.
                coverage = sum(corridor_coverage(p, reference or [], tolerance, reference_segments) * sum(meters(a, b) for a, b in zip(p, p[1:])) for p in paths) / geometric_distance if geometric_distance else 0
                result["reference_coverage"] = round(coverage, 4)
                if coverage < 0.9:
                    failures.append("OUTSIDE_REFERENCE_WALKWAY")
            else:
                unknowns.append("REFERENCE_WALKWAY_MISSING")
        if shape == "lake_loop":
            from validate_lap import analysis_ring, inspect_lap
            lap = inspect_lap(paths, water or [])
            result["lap_validation"] = lap
            failures.extend(lap["failures"])
            unknowns.extend(lap["unresolved"])
            if water and len(water) >= 3:
                ring = analysis_ring(paths)
                if ring is None:
                    result["lake_topology_sampling"] = ("NOT_EVALUATED_OPEN_GEOMETRY"
                        if "LAP_OPEN_GEOMETRY" in lap["unresolved"] else "NOT_EVALUATED_DISCONNECTED_GEOMETRY")
                else:
                    result.update(lake_topology_diagnostics(ring, water))
                # Legacy sampled diagnostics are only meaningful for a valid continuous ring.
                water_checks = water + [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(water, water[1:] + water[:1])]
                if "outside_water_vertex_count" in lap and not all(inside(p, ring) for p in water_checks):
                    excluded = [p for p in water_checks if not inside(p, ring)]
                    result["water_boundary_outside_fraction"] = round(len(excluded) / len(water_checks), 4)
                    result["max_outside_boundary_distance_m"] = round(max(min(segment_distance(p, a, b)
                                                                    for step in paths for a, b in zip(step, step[1:]))
                                                                for p in excluded), 1)
                from lake_evidence import inspect_water_overlap
                evidence = inspect_water_overlap(paths, water, source)
                result['water_overlap_evidence'] = evidence
                unknowns.extend(evidence['unresolved'])
        if shape == "river_out_and_back":
            from validate_river import inspect_river
            river = inspect_river(paths, reference or [])
            result["river_validation"] = river
            failures.extend(river["failures"])
            unknowns.extend(river["unresolved"])
        if shape == "lake_loop" and (result.get('exact_edge_retraced_distance_m', 0) > 0.001 or
                                      'LAP_NON_SIMPLE_GEOMETRY' in unknowns):
            unknowns.append("REPETITION_AND_TOPOLOGY_REVIEW_REQUIRED")
        result.update(distance_m=distance, time_s=duration, geometry_distance_m=round(geometric_distance, 1),
                      step_count=len(paths), coordinate_count=sum(map(len, paths)),
                      max_seam_gap_m=round(max(seams, default=0), 1))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        failures.append("INVALID_RESPONSE_SCHEMA")
    result.update(failures=failures, unresolved=unknowns,
                  geometry_check="FAIL" if failures else "INCOMPLETE" if unknowns else "PASS")
    return result


class Client:
    def __init__(self, key: str, limit: int):
        self.key, self.limit, self.calls = key, limit, 0

    def get(self, endpoint: str, params: dict) -> tuple[int, dict, float]:
        if self.calls >= self.limit:
            raise RuntimeError("Call budget exhausted; no automatic retry")
        self.calls += 1
        request = Request("https://dapi.kakao.com" + endpoint + "?" + urlencode(params),
                          headers={"Authorization": "KakaoAK " + self.key, "Accept": "application/json"})
        started = time.monotonic()
        try:
            with urlopen(request, timeout=25) as response:
                status, data = response.status, response.read(8_000_001)
        except HTTPError as error:
            # Do not print raw errors, URLs, request headers or provider contents.
            status, data = error.code, b"{}"
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("Network request failed; no automatic retry") from None
        if len(data) > 8_000_000:
            raise RuntimeError("Response exceeded size limit")
        try:
            body = json.loads(data)
        except (ValueError, UnicodeError):
            raise RuntimeError("Provider response is not JSON") from None
        if not isinstance(body, dict):
            raise RuntimeError("Provider response is not an object")
        return status, body, time.monotonic() - started


def source_ok(source: dict) -> bool:
    return (isinstance(source, dict)
            and urlparse(source.get("url", "")).scheme == "https"
            and bool(source.get("retrieved_at"))
            and bool(source.get("license")))


def load_site(path: Path) -> dict:
    site = json.loads(path.read_text(encoding="utf-8-sig"))
    if site.get("shape") not in ("lake_loop", "river_out_and_back"):
        raise ValueError("Unsupported site shape")
    if not source_ok(site.get("walk_source")):
        raise ValueError("Independent walkway source URL, retrieval date and usage terms are required")
    if site.get("walk_points_reviewed") is not True:
        raise ValueError("Review sourced walking points before a live probe")
    site["walk_points"] = [point(p) for p in site["walk_points"]]
    if len(site["walk_points"]) < 8 or len(set(site["walk_points"])) != len(site["walk_points"]):
        raise ValueError("At least 8 distinct sourced walking points are required for the limit experiment")
    site["reference_walkway"] = [point(p) for p in site.get("reference_walkway", [])]
    site["reference_segments"] = [(point(a), point(b)) for a, b in site.get("reference_segments", [])]
    if len(site["reference_walkway"]) < 2 and not site["reference_segments"]:
        raise ValueError("A sourced reference walkway is required")
    site["water_boundary"] = [point(p) for p in site.get("water_boundary", [])]
    if site["shape"] == "lake_loop" and (not source_ok(site.get("water_source")) or len(site["water_boundary"]) < 3):
        raise ValueError("A sourced lake boundary is required")
    cases(site["walk_points"], site["shape"], site.get("via_sample_indices"))
    return site


def routing_inputs(site):
    """One reviewed request; generated river candidates may need fewer than five vias."""
    points = [point(p) for p in site["walk_points"]]
    if "river_candidate" in site:
        indices = site.get("selected_via_indices")
        if (site["shape"] != "river_out_and_back" or not 2 <= len(points) <= 200 or
                not isinstance(indices, list) or not 1 <= len(indices) <= 5 or
                any(type(i) is not int or not 0 < i < len(points) for i in indices)):
            raise ValueError("Ordered original river via nodes including final turnpoint required")
        if site.get("via_sequence_policy") == "MIRRORED_SOURCE_OUT_AND_BACK":
            middle = len(indices) // 2
            outbound = indices[:middle + 1]
            if (len(indices) % 2 != 1 or outbound != sorted(set(outbound)) or
                    outbound[-1] != len(points) - 1 or indices[middle + 1:] != list(reversed(outbound[:-1])) or
                    site["river_candidate"].get("turnpoint_via_index") != middle):
                raise ValueError("One real turnpoint with matching outbound and return anchors required")
        elif sorted(set(indices)) != indices or indices[-1] != len(points) - 1:
            raise ValueError("Ordered outbound source nodes required")
        return points[0], points[0], [points[i] for i in indices], site["shape"]
    _, start, end, via, shape = next(c for c in cases(points, site["shape"], site.get("via_sample_indices"))
                                   if c[0] == "same_point_via_5")
    return start, end, via, shape


def cases(points: list[Point], shape: str, via_sample_indices=None) -> list[tuple]:
    if via_sample_indices is not None:
        if (not isinstance(via_sample_indices, list) or len(via_sample_indices) != 5 or
                any(type(i) is not int or not 0 < i < len(points) for i in via_sample_indices) or
                sorted(set(via_sample_indices)) != via_sample_indices or
                shape == "river_out_and_back" and via_sample_indices[-1] != len(points) - 1):
            raise ValueError("Five ordered distinct source sample indices required; river must include turnpoint")
    a = points[0]
    result = [("baseline", a, points[1], [], "point_to_point")]
    for n in (1, 3, 5, 6):
        result.append((f"via_{n}", a, points[n + 1], points[1:n + 1], "point_to_point"))
    result.append(("same_point_no_via", a, a, [], "point_to_point"))
    if via_sample_indices is not None:
        loop_via = [points[i] for i in via_sample_indices]
    elif shape == "lake_loop":
        loop_via = [points[i * len(points) // 6] for i in range(1, 6)]
    else:
        # Include the actual sourced turnpoint, not an arbitrary earlier point.
        loop_via = [points[round(i * (len(points) - 1) / 5)] for i in range(1, 6)]
    result.append(("same_point_via_5", a, a, loop_via, shape))
    if shape == "lake_loop":
        result.append(("same_point_reverse_via_5", a, a, list(reversed(loop_via)), shape))
    else:
        result.extend([("river_outbound", a, points[-1], [], "point_to_point"),
                       ("river_inbound", points[-1], a, [], "point_to_point")])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    search = sub.add_parser("search")
    search.add_argument("query")
    probe = sub.add_parser("probe")
    probe.add_argument("site", type=Path)
    probe.add_argument("--mode", choices=MODES, default="SHORTEST")
    probe.add_argument("--max-calls", type=int, default=12)
    probe.add_argument("--corridor-m", type=float, default=20)
    probe.add_argument("--case", help="Run exactly one named matrix case")
    args = parser.parse_args()
    key = read_key()
    if args.command == "preflight":
        print(json.dumps({"rest_key_configured": bool(key), "native_key_used_for_rest": False,
                          "network_calls": 0, "quota_and_activation": "NOT_VERIFIED"}))
        return 0 if key else 2
    if not key:
        print("KAKAO_REST_API_KEY is missing. No requests sent.", file=sys.stderr)
        return 2
    if args.command == "search":
        client = Client(key, 1)
        status, payload, elapsed = client.get("/v2/local/search/keyword.json", {"query": args.query, "size": 15})
        print(json.dumps({"http_status": status, "elapsed_s": round(elapsed, 2)}, ensure_ascii=False))
        if status != 200:
            return 3
        for candidate in payload.get("documents", []):
            # Transient display for human review; never select the first result automatically.
            print(json.dumps({k: candidate.get(k) for k in ("id", "place_name", "category_name", "address_name", "road_address_name", "place_url")}, ensure_ascii=True))
        return 0
    if not 1 <= args.max_calls <= 100 or not math.isfinite(args.corridor_m) or not 1 <= args.corridor_m <= 100:
        raise ValueError("Invalid call budget or corridor tolerance")
    site = load_site(args.site)
    client = Client(key, args.max_calls)
    matrix = cases(site["walk_points"], site["shape"], site.get("via_sample_indices"))
    if args.case:
        matrix = [case for case in matrix if case[0] == args.case]
        if not matrix:
            raise ValueError("Unknown matrix case")
    for label, start, end, via, shape in matrix:
        params = {"start_x": start[0], "start_y": start[1], "end_x": end[0], "end_y": end[1],
                  "input_coord": "WGS84", "output_coord": "WGS84", "route_mode": args.mode}
        if via:
            params.update(via_x=",".join(str(p[0]) for p in via), via_y=",".join(str(p[1]) for p in via))
        status, payload, elapsed = client.get("/v2/routing/walk", params)
        result = inspect(payload, start, end, shape, site["reference_walkway"], site["water_boundary"], args.corridor_m,
                         site["reference_segments"], via)
        result.update(case=label, via_count=len(via), mode=args.mode, http_status=status,
                      elapsed_s=round(elapsed, 2), calls_sent=client.calls, billing="CONSOLE_CHECK_REQUIRED",
                      recommendation_quality="NOT_ACCEPTED")
        if label == "via_6" and status == 200 and payload.get("status") == "OK":
            result["limit_observation"] = "ACCEPTED_OUTSIDE_DOCUMENTED_LIMIT; DO_NOT_RELY_ON_THIS"
        print(json.dumps(result, ensure_ascii=False))
        del payload
        if status != 200:
            # 400 for the intentional six-waypoint test may be expected.
            if label == "via_6" and status == 400:
                continue
            return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        # Error text only comes from local validation, not a provider response.
        print(f"Probe stopped: {type(error).__name__}. Check key, site input, network and call budget.", file=sys.stderr)
        sys.exit(2)
