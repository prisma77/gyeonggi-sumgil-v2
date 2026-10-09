"""Time-targeted prefixes of one sourced, bidirectional river walking corridor."""
import copy
import hashlib
import math

from prepare_site import network
from probe import meters, point
from select_waypoints import select_minimum
from select_network_anchors import select_network_anchors

TIME_TOLERANCE = 0.25  # Explicit experiment policy, not provider accuracy or safety.
SOURCE_SHAPE_TOLERANCE_M = 5.0  # Source simplification policy, not route/snapping accuracy.
TURNPOINT_SEPARATION_M = 75.0  # Source arclength, not straight-line distance.


def plan(site, source, duration_minutes, walking_speed_kmh, distance_range_m=None):
    if (type(duration_minutes) is not int or not 1 <= duration_minutes <= 120 or
            isinstance(walking_speed_kmh, bool) or not isinstance(walking_speed_kmh, (int, float)) or
            not math.isfinite(walking_speed_kmh) or not 2 <= walking_speed_kmh <= 6):
        raise ValueError("Explicit minutes (1..120) and assumed walking speed (2..6 km/h) required")
    if distance_range_m is not None and (
            not isinstance(distance_range_m, (list, tuple)) or len(distance_range_m) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in distance_range_m) or
            not 0 < distance_range_m[0] <= distance_range_m[1] <= 20000):
        raise ValueError("Finite ordered explicit distance bounds required")
    if site.get("shape") != "river_out_and_back" or site.get("walk_points_reviewed") is not True:
        raise ValueError("Reviewed river source input required")
    coordinates, edges, ways = network(source)
    nodes = site.get("source_node_ids", [])
    reference = [point(p) for p in site.get("reference_walkway", [])]
    if (site.get("walk_source") != source["source"] or not 2 <= len(nodes) <= 200 or
            len(set(nodes)) != len(nodes) or len(set(reference)) != len(nodes) or
            len(reference) != len(nodes) or
            any(n not in coordinates or coordinates[n] != p for n, p in zip(nodes, reference)) or
            point(site["walk_points"][0]) != reference[0]):
        raise ValueError("Complete original node sequence and unchanged departure required")
    if any((a, b) not in edges or (b, a) not in edges for a, b in zip(nodes, nodes[1:])):
        raise ValueError("Same-corridor return needs both original walking directions")
    lengths = [0.0]
    for a, b in zip(reference, reference[1:]):
        lengths.append(lengths[-1] + meters(a, b))
    estimates = [2 * length / (walking_speed_kmh * 1000 / 60) for length in lengths]
    eligible = sorted((i for i in range(1, len(nodes))
                       if abs(estimates[i] - duration_minutes) / duration_minutes <= TIME_TOLERANCE and
                       (distance_range_m is None or distance_range_m[0] <= lengths[i] * 2 <= distance_range_m[1])),
                      key=lambda i: (abs(estimates[i] - duration_minutes), i))
    result = dict(status="TARGET_OUTSIDE_AVAILABLE_SOURCE_RANGE", candidates=[],
                  requested_duration_minutes=duration_minutes, assumed_walking_speed_kmh=walking_speed_kmh,
                  time_tolerance_fraction=TIME_TOLERANCE,
                  available_estimated_minutes=[round(estimates[1], 2), round(estimates[-1], 2)],
                  source_outbound_length_m=round(lengths[-1], 1),
                  turnpoint_separation_m=TURNPOINT_SEPARATION_M,
                  distance_range_m=distance_range_m,
                  source=copy.deepcopy(source["source"]), walking_access="UNVERIFIED")
    for i in eligible:
        if distance_range_m is not None and any(abs(lengths[i] - lengths[len(c["source_node_ids"]) - 1]) < TURNPOINT_SEPARATION_M
               for c in result["candidates"]):
            continue
        # Reserve return anchors too: A -> B -> R -> B -> A uses five
        # requested vias, without adding a new loop or fabricated coordinate.
        budget = 3 if distance_range_m is not None else 5
        selection = (select_network_anchors(nodes[:i + 1], coordinates, edges, ways, budget)
                     if distance_range_m is not None else
                     select_minimum(reference[:i + 1], SOURCE_SHAPE_TOLERANCE_M, budget))
        if distance_range_m is not None:
            selection.update(source_shape_tolerance_m=SOURCE_SHAPE_TOLERANCE_M,
                             source_shape_tolerance_exceeded=selection["max_chord_deviation_m"] > SOURCE_SHAPE_TOLERANCE_M,
                             maximum_vias=5)
        if selection is None:
            continue
        candidate = copy.deepcopy(site)
        prefix, via = nodes[:i + 1], selection["indices"]
        turnpoint_via_index = len(via) - 1
        if distance_range_m is not None:
            via = [*via, *reversed(via[:-1])]
        candidate.update(source_node_ids=prefix, sample_node_ids=prefix,
                         walk_points=reference[:i + 1], reference_walkway=reference[:i + 1],
                         reference_segments=[], selected_via_indices=via)
        candidate["via_sequence_policy"] = "MIRRORED_SOURCE_OUT_AND_BACK" if distance_range_m is not None else "OUTBOUND_ONLY"
        candidate.pop("via_sample_indices", None)
        candidate.pop("input_validation", None)
        candidate.pop("input_change", None)
        candidate["source_network_length_m"] = round(lengths[i], 1)
        candidate["river_candidate"] = dict(
            requested_duration_minutes=duration_minutes, assumed_walking_speed_kmh=walking_speed_kmh,
            time_tolerance_fraction=TIME_TOLERANCE, source_expected_roundtrip_m=round(lengths[i] * 2, 1),
            distance_range_m=distance_range_m,
            source_estimated_minutes=round(estimates[i], 2),
            source_time_error_fraction=round(abs(estimates[i] - duration_minutes) / duration_minutes, 4),
            departure_node_id=prefix[0], turnpoint_node_id=prefix[-1],
            via_node_ids=[prefix[j] for j in via], waypoint_selection=selection,
            via_sequence_policy=candidate["via_sequence_policy"], turnpoint_via_index=turnpoint_via_index,
            estimate_basis="SOURCE_LENGTH_AND_ASSUMED_SPEED; NOT_API_TIME",
            status="SOURCE_CANDIDATE_ONLY; CURRENT_ACCESS_UNVERIFIED")
        result["candidates"].append(candidate)
        if len(result["candidates"]) == 3:
            break
    if result["candidates"]:
        result["status"] = "SOURCE_CANDIDATES_ONLY"
    elif eligible:
        result["status"] = "INSUFFICIENT_WAYPOINT_BUDGET"
    return result


def candidate_id(base_id, candidate):
    data = candidate["river_candidate"]
    identity = f"{base_id}:{data['requested_duration_minutes']}:{data['assumed_walking_speed_kmh']}:{data['turnpoint_node_id']}:{data['via_node_ids']}:{data.get('distance_range_m')}"
    return "river-c-" + hashlib.sha256(identity.encode()).hexdigest()[:16]


def inspect_target(inspection, candidate):
    target = candidate["requested_duration_minutes"] * 60
    actual = inspection.get("time_s")
    if not isinstance(actual, (int, float)) or not math.isfinite(actual) or actual <= 0:
        return dict(status="NOT_EVALUATED", requested_time_s=target, failures=[])
    error = abs(actual - target) / target
    return dict(status="PASS_API_TIME_ONLY" if error <= candidate["time_tolerance_fraction"] else "FAIL",
                requested_time_s=target, actual_api_time_s=actual,
                difference_s=round(actual - target, 1), time_error_fraction=round(error, 4),
                tolerance_fraction=candidate["time_tolerance_fraction"],
                failures=[] if error <= candidate["time_tolerance_fraction"] else ["TARGET_DURATION_MISMATCH"])


def compare_distance(inspection, candidate):
    """Different source/provider lengths are a review signal, not proven detours."""
    expected = candidate["source_expected_roundtrip_m"]
    geometry, reported = inspection.get("geometry_distance_m"), inspection.get("distance_m")
    if geometry is None or reported is None:
        return dict(status="NOT_EVALUATED", unresolved=["SOURCE_API_DISTANCE_UNAVAILABLE"])
    difference = geometry - expected
    review_threshold = max(30.0, expected * 0.05)
    return dict(status="REVIEW_REQUIRED" if abs(difference) > review_threshold else "WITHIN_TRIAL_THRESHOLD",
                source_expected_roundtrip_m=expected, api_reported_distance_m=reported,
                api_geometry_distance_m=geometry, reported_minus_source_m=round(reported - expected, 1),
                geometry_minus_source_m=round(difference, 1), review_threshold_m=round(review_threshold, 1),
                scope="DIFFERENT_DATASETS; NOT_PROOF_OF_UNNECESSARY_DETOUR",
                unresolved=["SOURCE_API_DISTANCE_DIFFERENCE_REVIEW_REQUIRED"] if abs(difference) > review_threshold else [])


def inspect_distance(inspection, candidate):
    bounds = candidate.get("distance_range_m")
    if bounds is None:
        return dict(status="NOT_REQUESTED", failures=[], unresolved=[])
    actual = inspection.get("distance_m")
    if type(actual) not in (int, float) or not math.isfinite(actual) or actual <= 0:
        return dict(status="NOT_EVALUATED", distance_range_m=bounds, failures=[],
                    unresolved=["TARGET_DISTANCE_UNAVAILABLE"])
    passed = bounds[0] <= actual <= bounds[1]
    return dict(status="PASS_API_DISTANCE_ONLY" if passed else "FAIL",
                distance_range_m=bounds, actual_api_distance_m=actual,
                failures=[] if passed else ["TARGET_DISTANCE_MISMATCH"], unresolved=[])
