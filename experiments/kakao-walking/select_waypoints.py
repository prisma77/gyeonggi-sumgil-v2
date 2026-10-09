"""Choose original nodes with a bounded minimax error; chords are analysis only."""
import math

from probe import meters, segment_distance


def select(points, maximum=5, allowed_indices=None):
    if not 2 <= len(points) <= 200 or not 1 <= maximum <= 5:
        raise ValueError("Two to 200 source nodes and at most five via points required")
    allowed = set(range(1, len(points))) if allowed_indices is None else set(allowed_indices)
    if (not allowed or len(points) - 1 not in allowed or
            any(type(i) is not int or not 0 < i < len(points) for i in allowed)):
        raise ValueError("Original eligible indices including the unchanged turnpoint required")
    count = min(maximum, len(allowed))
    distance = [0.0]
    for a, b in zip(points, points[1:]):
        distance.append(distance[-1] + meters(a, b))
    errors = {(i, j): max((segment_distance(p, points[i], points[j])
                          for p in points[i + 1:j]), default=0.0)
              for i in range(len(points) - 1) for j in range(i + 1, len(points))}

    def solve(limit=None):
        costs, previous = {(0, 0): 0.0}, {}
        for used in range(1, count + 1):
            for end in range(used, len(points)):
                if end not in allowed:
                    continue
                for start in range(used - 1, end):
                    if (used - 1, start) not in costs:
                        continue
                    if limit is not None and errors[start, end] > limit + 1e-7:
                        continue
                    edge = errors[start, end] if limit is None else distance[end] - distance[start]
                    cost = max(costs[used - 1, start], edge)
                    if cost < costs.get((used, end), float("inf")):
                        costs[used, end], previous[used, end] = cost, start
        return costs, previous

    optimal_error = solve()[0][count, len(points) - 1]
    # Among minimax-error solutions, minimize the longest unsampled source interval.
    costs, previous = solve(optimal_error)
    end, indices = len(points) - 1, []
    for used in range(count, 0, -1):
        indices.append(end)
        end = previous[used, end]
    return dict(indices=list(reversed(indices)), max_chord_deviation_m=optimal_error,
                max_source_interval_m=round(costs[count, len(points) - 1], 3))


def select_minimum(points, tolerance_m=5.0, maximum=5, allowed_indices=None):
    """Use the fewest real via nodes meeting an explicit source-shape tolerance."""
    if (not 2 <= len(points) <= 200 or not math.isfinite(tolerance_m) or tolerance_m < 0 or
            not 1 <= maximum <= 5):
        raise ValueError("Bounded source nodes, finite tolerance and at most five vias required")
    for count in range(1, min(maximum, len(points) - 1) + 1):
        selected = select(points, count, allowed_indices)
        if selected["max_chord_deviation_m"] <= tolerance_m:
            return dict(selected, policy="MINIMUM_VIAS_WITHIN_SOURCE_SHAPE_TOLERANCE",
                        source_shape_tolerance_m=tolerance_m, maximum_vias=maximum)
    return None
