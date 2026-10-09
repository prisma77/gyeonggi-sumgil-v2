"""Conservative single-ring geometry checks; never create or repair a route."""
import math

from probe import inside, meters

EPS = 1e-7  # Numerical comparisons in the local projection; not a snapping radius.
NUMERIC_JOIN_M = 0.001  # 1 mm analysis tolerance; source/API paths are never altered.


def analysis_ring(paths):
    """Endpoint equivalence for geometry analysis only, never returned as a route."""
    if not paths or any(len(p) < 2 for p in paths):
        return None
    if any(meters(a[-1], b[0]) > NUMERIC_JOIN_M for a, b in zip(paths, paths[1:])):
        return None
    if meters(paths[0][0], paths[-1][-1]) > NUMERIC_JOIN_M:
        return None
    ring = list(paths[0])
    for step in paths[1:]:
        ring.extend(step[1:])
    ring[-1] = ring[0]
    return clean(ring)


def clean(points):
    result = []
    for p in points:
        if not result or p != result[-1]:
            result.append(p)
    return result


def projected(points, origin):
    sx = 111_195 * math.cos(math.radians(origin[1]))
    return [((p[0] - origin[0]) * sx, (p[1] - origin[1]) * 111_195) for p in points]


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(p, a, b):
    return (abs(cross(a, b, p)) <= EPS and
            min(a[0], b[0]) - EPS <= p[0] <= max(a[0], b[0]) + EPS and
            min(a[1], b[1]) - EPS <= p[1] <= max(a[1], b[1]) + EPS)


def intersection(a, b, c, d):
    if (max(a[0], b[0]) + EPS < min(c[0], d[0]) or
            max(c[0], d[0]) + EPS < min(a[0], b[0]) or
            max(a[1], b[1]) + EPS < min(c[1], d[1]) or
            max(c[1], d[1]) + EPS < min(a[1], b[1])):
        return None
    values = (cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b))
    if all(abs(v) <= EPS for v in values):
        axis = 0 if abs(a[0] - b[0]) >= abs(a[1] - b[1]) else 1
        overlap = min(max(a[axis], b[axis]), max(c[axis], d[axis])) - max(min(a[axis], b[axis]), min(c[axis], d[axis]))
        return "OVERLAP" if overlap > EPS else "TOUCH" if overlap >= -EPS else None
    if ((values[0] > EPS and values[1] < -EPS or values[0] < -EPS and values[1] > EPS) and
            (values[2] > EPS and values[3] < -EPS or values[2] < -EPS and values[3] > EPS)):
        return "CROSS"
    return "TOUCH" if any((on_segment(c, a, b), on_segment(d, a, b), on_segment(a, c, d), on_segment(b, c, d))) else None


def non_simple_count(ring):
    edges = list(zip(ring, ring[1:]))
    count = 0
    for i, (a, b) in enumerate(edges):
        for j in range(i + 1, len(edges)):
            kind = intersection(a, b, *edges[j])
            adjacent = j == i + 1 or i == 0 and j == len(edges) - 1
            if kind and (not adjacent or kind != "TOUCH"):
                count += 1
    return count


def inspect_lap(paths, water):
    result = {"status": "INCOMPLETE", "scope": "GEOMETRY_ONLY; CURRENT_ACCESS_UNVERIFIED; ORIGINAL_ROUTE_UNCHANGED",
              "numeric_join_tolerance_m": NUMERIC_JOIN_M,
              "failures": [], "unresolved": []}
    if not paths or any(len(p) < 2 for p in paths):
        result["unresolved"].append("LAP_GEOMETRY_MISSING")
        return result
    gaps = [(index, a[-1], b[0]) for index, (a, b) in enumerate(zip(paths, paths[1:])) if a[-1] != b[0]]
    result["step_join_mismatch_count"] = len(gaps)
    result["step_join_mismatches"] = [dict(after_step=index + 1, gap_m=meters(a, b)) for index, a, b in gaps]
    result['max_step_join_gap_m'] = max((meters(a, b) for _, a, b in gaps), default=0.0)
    result["endpoint_gap_m"] = meters(paths[0][0], paths[-1][-1])
    result["numeric_join_equivalence_count"] = sum(meters(a, b) <= NUMERIC_JOIN_M for _, a, b in gaps)
    if any(meters(a, b) > NUMERIC_JOIN_M for _, a, b in gaps):
        result["unresolved"].append("LAP_DISCONNECTED_GEOMETRY")
        return result  # No fictitious lines between real steps.
    if result["endpoint_gap_m"] > NUMERIC_JOIN_M:
        result["unresolved"].append("LAP_OPEN_GEOMETRY")
        return result  # Only <=1 mm numerical equivalence is used in analysis.
    route = analysis_ring(paths)
    if len(route) < 4 or len(set(route[:-1])) < 3:
        result["status"] = "FAIL"
        result["failures"].append("LAP_DEGENERATE_GEOMETRY")
        return result
    if len(water) < 3:
        result["unresolved"].append("TARGET_WATER_BOUNDARY_MISSING")
        return result
    target = clean(water)
    if target[0] != target[-1]:
        target.append(target[0])  # Boundary polygon representation, never a route connector.
    route_xy, water_xy = projected(route, route[0]), projected(target, route[0])
    if len(water_xy) < 4 or len(set(water_xy[:-1])) < 3 or non_simple_count(water_xy):
        result["unresolved"].append("TARGET_WATER_INVALID_GEOMETRY")
        return result
    area = sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(water_xy, water_xy[1:])) / 2
    if abs(area) <= EPS:
        result["unresolved"].append("TARGET_WATER_INVALID_GEOMETRY")
        return result
    count = non_simple_count(route_xy)
    result["non_simple_intersection_count"] = count
    if count:
        result["unresolved"].append("LAP_NON_SIMPLE_GEOMETRY")
        return result  # Access stems, shared bridges and repeated laps need separate analysis.
    area = sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(route_xy, route_xy[1:])) / 2
    if abs(area) <= EPS:
        result["status"] = "FAIL"
        result["failures"].append("LAP_DEGENERATE_GEOMETRY")
        return result
    outside = sum(not inside(p, route_xy) and not any(on_segment(p, a, b) for a, b in zip(route_xy, route_xy[1:]))
                  for p in water_xy[:-1])
    crossings = contacts = 0
    for c, d in zip(water_xy, water_xy[1:]):
        kinds = {intersection(a, b, c, d) for a, b in zip(route_xy, route_xy[1:])}
        crossings += "CROSS" in kinds
        contacts += bool(kinds & {"TOUCH", "OVERLAP"})
    result.update(water_boundary_edge_count=len(water_xy) - 1, outside_water_vertex_count=outside,
                  crossing_water_edge_count=crossings, contacting_water_edge_count=contacts)
    if outside or crossings:
        result["status"] = "FAIL"
        result["failures"].append("TARGET_WATER_NOT_ENCLOSED")
    elif contacts:
        result["unresolved"].append("TARGET_WATER_BOUNDARY_CONTACT_REQUIRES_REVIEW")
    else:
        result.update(status="PASS_GEOMETRY_ONLY", winding="+1" if area > 0 else "-1")
    return result
