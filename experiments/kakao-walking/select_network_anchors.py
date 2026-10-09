"""Screen source-node input ambiguity before choosing geometric anchors.

These anchors constrain a routing request; they never certify a provider path.
"""
from probe import meters
from select_waypoints import select, select_minimum


def select_network_anchors(nodes, coordinates, edges, ways, maximum=3):
    if not 2 <= len(nodes) <= 200 or not 1 <= maximum <= 3:
        raise ValueError("Bounded original source path and outbound anchor budget required")
    if len(set(nodes)) != len(nodes) or any(
            (a, b) not in edges or (b, a) not in edges for a, b in zip(nodes, nodes[1:])):
        raise ValueError("Simple bidirectional source path required")
    points = [coordinates[n] for n in nodes]
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + meters(a, b))
    signatures = []
    for a, b in zip(nodes, nodes[1:]):
        tags = [ways[w].get("tags", {}) for w in edges[a, b]]
        # Do not hide overlapping classifications behind an arbitrary way ID.
        signatures.append(tuple(sorted(set((t.get("highway", ""), t.get("bridge", "no"),
                                           t.get("tunnel", "no"), t.get("layer", "0")) for t in tags))))
    regions = []
    start = 0
    for i in range(1, len(signatures) + 1):
        if i == len(signatures) or signatures[i] != signatures[start]:
            regions.append(dict(start_index=start, end_index=i,
                                length_m=round(cumulative[i] - cumulative[start], 1),
                                contains_bridge=any(t[1] != "no" for t in signatures[start]),
                                contains_tunnel=any(t[2] != "no" for t in signatures[start]),
                                walking_classes=sorted(set(t[0] for t in signatures[start]))))
            start = i
    adjacency = {}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)
    junctions = [i for i, n in enumerate(nodes) if len(adjacency.get(n, ())) > 2]
    # Coordinates alone do not encode layer/link choice. Avoid placing optional
    # anchors directly on infrastructure, class transitions and junctions.
    # This is input screening, not a walkability guarantee or relaxed route test.
    clearance = 30.0
    boundaries = [r["start_index"] for r in regions[1:]]
    blocked = set()
    for i in range(1, len(nodes) - 1):
        near_choice = any(abs(cumulative[i] - cumulative[j]) <= clearance for j in [*junctions, *boundaries])
        near_structure = any(cumulative[r["start_index"]] - clearance <= cumulative[i] <= cumulative[r["end_index"]] + clearance
                             for r in regions if r["contains_bridge"] or r["contains_tunnel"])
        if near_choice or near_structure:
            blocked.add(i)
    allowed = [i for i in range(1, len(nodes)) if i not in blocked]
    chosen = select_minimum(points, 5.0, maximum, allowed)
    if chosen is None:
        chosen = select(points, maximum, allowed)
    return dict(chosen, policy="SOURCE_GEOMETRY_WITH_INPUT_AMBIGUITY_SCREENING",
                source_regions=regions, junction_source_indices=junctions,
                excluded_source_indices=sorted(blocked), input_clearance_m=clearance,
                departure_source_choice_unverified=(len(adjacency.get(nodes[0], ())) > 2 or
                                                    regions[0]["contains_bridge"] or regions[0]["contains_tunnel"]),
                turnpoint_source_choice_unverified=(regions[-1]["contains_bridge"] or regions[-1]["contains_tunnel"] or
                                                    any(abs(cumulative[-1] - cumulative[j]) <= clearance
                                                        for j in [*junctions, *boundaries])),
                scope="REQUEST_INPUT_SCREENING_ONLY; API_GEOMETRY_CHECK_REQUIRED")
