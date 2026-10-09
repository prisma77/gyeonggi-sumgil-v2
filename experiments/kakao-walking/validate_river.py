"""Directional progress along a source corridor; no coordinate or path repair."""
import math

from probe import meters, segment_projection

JOIN_TOLERANCE_M = 0.001
CORRIDOR_M = 20.0
ENDPOINT_M = 30.0
BACKTRACK_BUDGET_M = 10.0


def inspect_river(paths, reference):
    result = dict(status="INCOMPLETE", failures=[], unresolved=[],
                  walking_access="UNVERIFIED", progress_model="NEAREST_SOURCE_ARCLENGTH",
                  corridor_tolerance_m=CORRIDOR_M, endpoint_tolerance_m=ENDPOINT_M,
                  backtrack_budget_m=BACKTRACK_BUDGET_M)
    if len(reference) < 2 or not paths:
        result["unresolved"].append("RIVER_REFERENCE_MISSING")
        return result
    gaps = [meters(a[-1], b[0]) for a, b in zip(paths, paths[1:])]
    joined = all(g <= JOIN_TOLERANCE_M for g in gaps)
    result.update(max_step_connection_difference_m=round(max(gaps, default=0), 6),
                  discontinuous_step_count=sum(g > JOIN_TOLERANCE_M for g in gaps))
    if not joined:
        result["unresolved"].append("RIVER_STEP_CONNECTION_REVIEW_REQUIRED")
        result["direction_check"] = "NOT_EVALUATED_STEP_CONNECTION"
    cumulative = [0.0]
    for a, b in zip(reference, reference[1:]):
        cumulative.append(cumulative[-1] + meters(a, b))
    if cumulative[-1] <= ENDPOINT_M * 2:
        result["unresolved"].append("RIVER_TOO_SHORT_FOR_DIRECTION_TOLERANCE")
        return result
    # Sample only returned segments for analysis; never join gaps or return these samples as a route.
    samples = []
    for path in paths:
        samples.append(path[0])  # Independent point checks; never bridge a seam.
        for a, b in zip(path, path[1:]):
            divisions = max(1, math.ceil(meters(a, b) / 10))
            if len(samples) + divisions > 10000:
                result["unresolved"].append("RIVER_ANALYSIS_LIMIT_REACHED")
                return result
            for i in range(1, divisions + 1):
                samples.append(tuple(a[j] + (b[j] - a[j]) * i / divisions for j in (0, 1)))
    progress, offsets, ambiguous, outside = [], [], False, set()
    for p in samples:
        options = []
        for i, (a, b) in enumerate(zip(reference, reference[1:])):
            offset, fraction = segment_projection(p, a, b)
            options.append((offset, cumulative[i] + fraction * (cumulative[i + 1] - cumulative[i]), i))
        offset, position, source_segment = min(options)
        if offset > CORRIDOR_M:
            outside.add(source_segment)
        if any(d <= offset + 1.0 and abs(s - position) > ENDPOINT_M for d, s, _ in options):
            ambiguous = True
        offsets.append(offset)
        progress.append(position)
    turnpoint_distance = min(meters(p, reference[-1]) for p in samples)
    result.update(source_outbound_length_m=round(cumulative[-1], 1), max_corridor_offset_m=round(max(offsets), 1),
                  turnpoint_min_distance_m=round(turnpoint_distance, 1),
                  off_corridor_source_segment_indices=sorted(outside))
    if max(offsets) > CORRIDOR_M:
        result["failures"].append("RIVER_OUTSIDE_SOURCE_CORRIDOR")
    if (progress[0] > ENDPOINT_M or progress[-1] > ENDPOINT_M or
            meters(paths[0][0], reference[0]) > ENDPOINT_M or
            meters(paths[-1][-1], reference[0]) > ENDPOINT_M):
        result["failures"].append("RIVER_DEPARTURE_OR_RETURN_MISMATCH")
    if cumulative[-1] - max(progress) > ENDPOINT_M or turnpoint_distance > ENDPOINT_M:
        result["failures"].append("RIVER_TURNPOINT_NOT_REACHED")
    if ambiguous:
        result["unresolved"].append("RIVER_PROGRESS_AMBIGUOUS")
    elif joined:
        result["direction_check"] = "EVALUATED_CONTINUOUS_GEOMETRY"
        turn = progress.index(max(progress))
        outbound = sum(max(0.0, a - b) for a, b in zip(progress[:turn], progress[1:turn + 1]))
        inbound = sum(max(0.0, b - a) for a, b in zip(progress[turn:], progress[turn + 1:]))
        result.update(outbound_backtrack_m=round(outbound, 1), inbound_backtrack_m=round(inbound, 1))
        if outbound + inbound > BACKTRACK_BUDGET_M:
            result["failures"].append("RIVER_UNNECESSARY_DIRECTION_REVERSAL")
    result["status"] = "FAIL" if result["failures"] else "INCOMPLETE" if result["unresolved"] else "PASS_GEOMETRY_ONLY"
    return result
