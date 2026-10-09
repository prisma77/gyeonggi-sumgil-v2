"""Resolve exact OSM outer geometry; never fabricate a water feature or connector."""
from probe import point


def outer_boundary(source, way_id=None, relation_id=None):
    if (way_id is None) == (relation_id is None):
        raise ValueError("Exactly one source water way or relation required")
    elements = {(e["type"], e["id"]): e for e in source["osm"]["elements"]}
    if relation_id is not None:
        target = elements.get(("relation", relation_id))
        if not target or target.get("tags", {}).get("natural") != "water" or target["tags"].get("type") != "multipolygon":
            raise ValueError("Source water multipolygon required")
        outers = [m for m in target["members"] if m["role"] == "outer"]
        if len(outers) != 1 or outers[0]["type"] != "way":
            raise ValueError("Multiple or split outer rings require separate support")
        outer_id = outers[0]["ref"]
        reference = {"type": "relation", "id": relation_id, "outer_way_id": outer_id,
                     "inner_way_ids": [m["ref"] for m in target["members"] if m["type"] == "way" and m["role"] == "inner"],
                     "scope": "OUTER_EXTENT_ONLY; INNER_AREAS_NOT_MODELED"}
    else:
        target = elements.get(("way", way_id))
        if not target or target.get("tags", {}).get("natural") != "water":
            raise ValueError("Source water way required")
        outer_id = way_id
        reference = {"type": "way", "id": way_id, "outer_way_id": way_id, "inner_way_ids": [],
                     "scope": "SOURCE_SINGLE_OUTER_RING"}
    outer = elements.get(("way", outer_id))
    if (not outer or len(outer.get("nodes", [])) < 4 or outer["nodes"][0] != outer["nodes"][-1]
            or len(outer["nodes"]) != len(outer.get("geometry", []))):
        raise ValueError("Complete closed source outer way required; never close missing geometry")
    boundary = [point([p["lon"], p["lat"]]) for p in outer["geometry"]]
    if boundary[0] != boundary[-1]:
        raise ValueError("Closed source node has inconsistent geometry")
    return boundary, reference
