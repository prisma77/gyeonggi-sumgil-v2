"""Explicit walk totals and lap counts; never create or repair route geometry."""
import math


MIN_WALK_DISTANCE_M = 2000
MAX_TARGET_DISTANCE_M = 20000
MAX_LAPS = 10
DISTANCE_SCOPE = 'COURSE_ONLY; HOME_ACCESS_EXCLUDED'


def _positive(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _validate_request(target, lap_count):
    if type(lap_count) is not int or not 1 <= lap_count <= MAX_LAPS:
        raise ValueError('Explicit integer lap count 1..10 required')
    if target is None:
        if lap_count != 1:
            raise ValueError('One lap without a distance must remain one lap')
    elif (not _positive(target) or
          not MIN_WALK_DISTANCE_M <= target <= MAX_TARGET_DISTANCE_M):
        raise ValueError('Finite total walking target 2000..20000m required')


def distance_bounds(target, lap_count=1):
    """Base-course bounds derived from an explicit total, with a hard 2km floor."""
    _validate_request(target, lap_count)
    if target is None:
        raise ValueError('Explicit distance required for target bounds')
    return [max(MIN_WALK_DISTANCE_M, target * .9) / lap_count,
            target * 1.1 / lap_count]


def make_walk_plan(target_or_None, lap_count, source_base_m):
    """A source proposal is an estimate, including when its distance fits the goal."""
    _validate_request(target_or_None, lap_count)
    if not _positive(source_base_m) or not _positive(source_base_m * lap_count):
        raise ValueError('Finite positive source base and total distances required')
    return dict(requested_total_distance_m=target_or_None, lap_count=lap_count,
                source_base_distance_m=source_base_m,
                source_total_distance_m=source_base_m * lap_count,
                status='SOURCE_PROPOSAL_ONLY', distance_scope=DISTANCE_SCOPE)


def inspect_walk_plan(inspection, plan):
    """Validate one real lake lap first, then multiply its observed API distance.

    Repeating a validated base course is a stated walking plan, not extra provider
    geometry or proof of present access. A defect within that base remains a defect.
    """
    if not isinstance(inspection, dict) or not isinstance(plan, dict):
        raise ValueError('Inspection and explicit source walk plan required')
    target = plan.get('requested_total_distance_m')
    laps = plan.get('lap_count')
    proposal = make_walk_plan(target, laps, plan.get('source_base_distance_m'))
    if (plan.get('status') != proposal['status'] or
            plan.get('distance_scope') != DISTANCE_SCOPE or
            plan.get('source_total_distance_m') != proposal['source_total_distance_m']):
        raise ValueError('Unchanged explicit source proposal required')
    bounds = distance_bounds(target) if target is not None else [MIN_WALK_DISTANCE_M, None]
    failures = list(inspection.get('failures', []))
    unresolved = list(inspection.get('unresolved', []))
    geometry_status = inspection.get('geometry_check')
    if geometry_status == 'FAIL':
        failures.append('BASE_GEOMETRY_CHECK_FAILED')
    elif geometry_status != 'PASS':
        unresolved.append('BASE_GEOMETRY_CHECK_NOT_PASSED')
    lap = inspection.get('lap_validation') or {}
    failures.extend(lap.get('failures', []))
    unresolved.extend(lap.get('unresolved', []))
    if lap.get('status') == 'FAIL':
        failures.append('BASE_LAP_GEOMETRY_CHECK_FAILED')
    elif lap.get('status') != 'PASS_GEOMETRY_ONLY':
        unresolved.append('BASE_LAP_GEOMETRY_CHECK_NOT_PASSED')
    base = inspection.get('distance_m')
    total = base * laps if _positive(base) else None
    observed = _positive(total)
    if not observed:
        base, total = None, None
        unresolved.append('WALK_PLAN_API_DISTANCE_UNAVAILABLE')
    else:
        if total < MIN_WALK_DISTANCE_M:
            failures.append('MIN_WALK_DISTANCE_NOT_REACHED')
        if target is not None and not bounds[0] <= total <= bounds[1]:
            failures.append('WALK_PLAN_TARGET_DISTANCE_MISMATCH')
    status = ('NOT_EVALUATED' if not observed else 'FAIL' if failures else
              'INCOMPLETE' if unresolved else 'PASS_GEOMETRY_AND_DISTANCE_ONLY')
    return dict(status=status, failures=sorted(set(failures)), unresolved=sorted(set(unresolved)),
                lap_count=laps, base_api_distance_m=base, estimated_total_distance_m=total,
                total_distance_range_m=bounds, requested_total_distance_m=target,
                distance_scope=DISTANCE_SCOPE, walking_access='UNVERIFIED',
                estimate_basis='OBSERVED_API_BASE_DISTANCE_TIMES_EXPLICIT_LAPS')
