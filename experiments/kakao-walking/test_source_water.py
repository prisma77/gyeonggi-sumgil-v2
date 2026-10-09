"""Exact multipolygon member provenance and unsupported boundary regressions."""
import copy
import unittest

from audit_inputs import audit_inputs
from plan_source_cycle import interior_reference, plan
from probe import inside
from source_water import outer_boundary
from test_source_cycle import fixture


def relation_fixture():
    data = fixture()
    outer = next(e for e in data["osm"]["elements"] if e["id"] == 99)
    outer["tags"].clear()
    data["osm"]["elements"].append({"type": "relation", "id": 999,
        "tags": {"type": "multipolygon", "natural": "water"},
        "members": [{"type": "way", "ref": 99, "role": "outer"}, {"type": "way", "ref": 98, "role": "inner"}]})
    return data


class WaterSourceTests(unittest.TestCase):
    def test_relation_uses_exact_untagged_outer_member_geometry(self):
        data = relation_fixture()
        boundary, reference = outer_boundary(data, relation_id=999)
        way = next(e for e in data["osm"]["elements"] if e["id"] == 99)
        self.assertEqual([(p["lon"], p["lat"]) for p in way["geometry"]], boundary)
        self.assertEqual(99, reference["outer_way_id"])
        self.assertEqual([98], reference["inner_way_ids"])
        self.assertIn("INNER_AREAS_NOT_MODELED", reference["scope"])
        self.assertEqual({}, way["tags"])

    def test_multiple_outer_ways_stop_without_fictitious_connectors(self):
        data = relation_fixture()
        data["osm"]["elements"][-1]["members"].append({"type": "way", "ref": 97, "role": "outer"})
        with self.assertRaises(ValueError):
            outer_boundary(data, relation_id=999)

    def test_missing_or_open_outer_stops(self):
        for missing in (True, False):
            data = relation_fixture()
            if missing:
                data["osm"]["elements"] = [e for e in data["osm"]["elements"] if e["id"] != 99]
            else:
                outer = next(e for e in data["osm"]["elements"] if e["id"] == 99)
                outer["nodes"][-1] = 101
            with self.assertRaises(ValueError):
                outer_boundary(data, relation_id=999)

    def test_relation_provenance_is_audited_without_becoming_access_approval(self):
        data = relation_fixture()
        site = plan(data, None, 0, water_relation_id=999)
        self.assertEqual(999, site["water_relation_id"])
        self.assertNotIn("water_way_id", site)
        result = audit_inputs(site, data)
        self.assertEqual([], result["failures"])
        self.assertIn("WATER_INNER_AREAS_NOT_MODELED", result["unresolved"])
        self.assertEqual("UNVERIFIED", result["walking_access"])
        changed = copy.deepcopy(site)
        changed["water_boundary_reference"]["outer_way_id"] = 98
        self.assertIn("INPUT_WATER_BOUNDARY_SOURCE_MISMATCH", audit_inputs(changed, data)["failures"])

    def test_concave_polygon_mean_on_land_gets_an_analysis_only_interior_reference(self):
        shape = [(0, 0), (10, 0), (10, 10), (8, 10), (8, 2), (2, 2), (2, 10), (0, 10), (0, 0)]
        self.assertFalse(inside((5, 5.5), shape))
        original = list(shape)
        self.assertTrue(inside(interior_reference(shape), shape))
        self.assertEqual(original, shape)


if __name__ == "__main__":
    unittest.main()
