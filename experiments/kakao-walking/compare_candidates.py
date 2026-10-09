"""Hard validation before comparing observed candidate metrics; no AI scores."""
import math


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def assess(inspection, candidate, http_status=200):
    failures = list(inspection.get("failures", []))
    reviews = list(inspection.get("unresolved", []))
    if inspection.get("geometry_check") == "FAIL":
        failures.append("GEOMETRY_VALIDATION_FAILED")
    if http_status != 200 or inspection.get("api_status") != "OK":
        failures.append("PROVIDER_RESPONSE_NOT_OK")
    if not positive(inspection.get("distance_m")) or not positive(inspection.get("time_s")):
        reviews.append("OBSERVED_DISTANCE_OR_TIME_UNAVAILABLE")
    if inspection.get("geometry_check") != "PASS":
        reviews.append("GEOMETRY_NOT_VALIDATED")
    river_status = inspection.get("river_validation", {}).get("status")
    if river_status == "FAIL":
        failures.append("RIVER_SHAPE_VALIDATION_FAILED")
    if river_status != "PASS_GEOMETRY_ONLY":
        reviews.append("RIVER_SHAPE_NOT_VALIDATED")
    target = inspection.get("target_validation", {})
    if target.get("status") == "FAIL":
        failures.append("TARGET_DURATION_MISMATCH")
    if target.get("status") != "PASS_API_TIME_ONLY":
        reviews.append("TARGET_TIME_NOT_VALIDATED")
    distance = inspection.get("distance_validation", {})
    if distance.get("status") == "FAIL":
        failures.append("TARGET_DISTANCE_MISMATCH")
    expected_distance_status = "PASS_API_DISTANCE_ONLY" if candidate.get("distance_range_m") is not None else "NOT_REQUESTED"
    if distance.get("status") != expected_distance_status:
        reviews.append("TARGET_DISTANCE_NOT_VALIDATED")
    if inspection.get("source_distance_comparison", {}).get("status") != "WITHIN_TRIAL_THRESHOLD":
        reviews.append("SOURCE_DISTANCE_NOT_VALIDATED")
    status = "REJECTED" if failures else "REVIEW_REQUIRED" if reviews else "GEOMETRY_VALIDATED_ONLY"
    return dict(status=status, eligible_for_comparison=status == "GEOMETRY_VALIDATED_ONLY",
                failures=sorted(set(failures)), review_reasons=sorted(set(reviews)),
                walking_access="UNVERIFIED", recommendation_quality="NOT_ACCEPTED")


def trial_summary(identifier, mode, inspection, candidate, http_status=200):
    decision = assess(inspection, candidate, http_status)
    key = None
    expected = candidate.get("source_expected_roundtrip_m")
    target = candidate.get("requested_duration_minutes")
    geometry = inspection.get("geometry_distance_m")
    if decision["eligible_for_comparison"]:
        if not all(positive(v) for v in [expected, target, geometry]):
            decision.update(status="REVIEW_REQUIRED", eligible_for_comparison=False)
            decision["review_reasons"].append("COMPARISON_METRICS_UNAVAILABLE")
        else:
            # Explicit priority: requested time fit, then agreement between
            # datasets. Source difference is not a measured detour or safety score.
            key = [abs(inspection["time_s"] - target * 60) / (target * 60),
                   abs(geometry - expected) / expected]
    return dict(id=identifier, mode=mode, decision=decision, comparison_key=key)


def compare(trials, candidate_count):
    eligible = [t for t in trials if t["decision"]["eligible_for_comparison"]]
    winner = min(eligible, key=lambda t: (t["comparison_key"], t["id"]), default=None)
    return dict(status="VALIDATED_GEOMETRY_CANDIDATE_AVAILABLE" if winner else "NO_VALIDATED_CANDIDATE",
                best_candidate_id=winner["id"] if winner else None,
                tested_candidates=len(trials), source_candidates=candidate_count,
                untested_candidates=max(0, candidate_count - len(trials)), trials=trials,
                priority=["API_TIME_FIT", "SOURCE_API_GEOMETRY_LENGTH_AGREEMENT"],
                recommendation_quality="NOT_ACCEPTED", scope="CURRENT_GENERATION_AND_MODE; NOT_CURRENT_ACCESS_APPROVAL")
