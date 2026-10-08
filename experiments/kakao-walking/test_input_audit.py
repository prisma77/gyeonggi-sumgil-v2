"""Synthetic provenance/access/connectivity regressions; no network calls."""
import copy
import unittest

from audit_inputs import audit_inputs
from test_lap import points


class InputAuditTests(unittest.TestCase):
    def setUp(self):
        walk = points([(0, 0), (5, 0), (10, 0), (10, 5), (10, 10), (5, 10), (0, 10), (0, 5)])
        self.source = {"source": {"url": "https://source.example/", "license": "synthetic", "retrieved_at": "2026-10-08"},
                       "osm": {"elements": [{"type": "way", "id": 1, "nodes": list(range(8)) + [0],
                                             "geometry": [{"lon": x, "lat": y} for x, y in walk + walk[:1]],
                                             "tags": {"highway": "footway", "foot": "designated"}}]}}
        self.site = {"shape": "river_out_and_back", "walk_source": copy.deepcopy(self.source["source"]),
                     "walk_points": walk, "sample_node_ids": list(range(8))}

    def test_source_connection_does_not_claim_current_access(self):
        result = audit_inputs(self.site, self.source)
        self.assertEqual("SOURCE_MATCHED_REVIEW_REQUIRED", result["status"])
        self.assertEqual("REACHABLE_IN_SOURCE_ONLY", result["network_sequence"])
        self.assertEqual("UNVERIFIED", result["walking_access"])

    def test_nearby_unsourced_coordinate_is_blocked(self):
        x, y = self.site["walk_points"][2]
        self.site["walk_points"][2] = (x + 0.000001, y)
        self.assertEqual("FAIL", audit_inputs(self.site, self.source)["status"])

    def test_source_metadata_mismatch_is_blocked(self):
        self.site["walk_source"]["retrieved_at"] = "different"
        self.assertIn("INPUT_SOURCE_METADATA_MISMATCH", audit_inputs(self.site, self.source)["failures"])

    def test_forbidden_source_way_is_not_eligible(self):
        self.source["osm"]["elements"][0]["tags"]["foot"] = "no"
        self.assertIn("INPUT_POINT_NOT_AN_ELIGIBLE_SOURCE_NODE", audit_inputs(self.site, self.source)["failures"])

    def test_bridge_and_conditional_tags_stay_unverified(self):
        self.source["osm"]["elements"][0]["tags"].update(bridge="yes", **{"foot:conditional": "no @ (night)"})
        result = audit_inputs(self.site, self.source)
        self.assertTrue(result["points"][4]["bridge_tagged"])
        self.assertIn("INPUT_BRIDGE_CURRENT_ACCESS_UNVERIFIED", result["unresolved"])
        self.assertIn("INPUT_CONDITIONAL_ACCESS_REQUIRES_REVIEW", result["unresolved"])

    def test_one_way_foot_requires_actual_return_connectivity(self):
        way = self.source["osm"]["elements"][0]
        way["nodes"] = way["nodes"][:-1]
        way["geometry"] = way["geometry"][:-1]
        way["tags"]["oneway:foot"] = "yes"
        self.assertIn("INPUT_SEQUENCE_NOT_CONNECTED_IN_SOURCE", audit_inputs(self.site, self.source)["failures"])

    def test_same_coordinates_with_distinct_nodes_do_not_create_a_connector(self):
        way = self.source["osm"]["elements"][0]
        split = copy.deepcopy(way)
        split.update(id=2, nodes=[99, *way["nodes"][4:-1]], geometry=way["geometry"][3:-1])
        way.update(nodes=way["nodes"][:4], geometry=way["geometry"][:4])
        self.source["osm"]["elements"].append(split)
        self.assertEqual("FAIL", audit_inputs(self.site, self.source)["network_sequence"])

    def test_missing_water_provenance_is_not_a_lake_validation(self):
        self.site["shape"] = "lake_loop"
        self.assertIn("INPUT_WATER_BOUNDARY_SOURCE_MISMATCH", audit_inputs(self.site, self.source)["failures"])

    def test_draft_input_can_be_audited_without_becoming_approved(self):
        self.site["walk_points_reviewed"] = False
        self.assertEqual("SOURCE_MATCHED_REVIEW_REQUIRED", audit_inputs(self.site, self.source)["status"])
        self.assertFalse(self.site["walk_points_reviewed"])

    def test_missing_sample_points_are_rejected_before_building_a_request(self):
        self.site["walk_points"] = self.site["walk_points"][:3]
        self.site["sample_node_ids"] = self.site["sample_node_ids"][:3]
        self.assertEqual("FAIL", audit_inputs(self.site, self.source)["status"])


if __name__ == "__main__":
    unittest.main()
