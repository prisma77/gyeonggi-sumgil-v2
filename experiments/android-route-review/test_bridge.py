"""Synthetic boundary tests: no Kakao calls and no recommendation quality claims."""
import copy
from http.server import HTTPServer
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from bridge import ReviewService, load_catalog, make_handler, probe
from test_probe import response


class FakeClient:
    calls = 0
    limit = 1

    def __init__(self, payload):
        self.payload = payload

    def get(self, endpoint, params):
        if self.calls >= self.limit:
            raise RuntimeError("Budget exhausted")
        self.calls += 1
        self.params = params
        return 200, copy.deepcopy(self.payload), 0.1


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(Path(__file__).with_name("catalog.json"))
        points = self.catalog["river"][1]["walk_points"]
        self.client = FakeClient(response([points, list(reversed(points))]))
        self.service = ReviewService(self.catalog, self.client)

    def split_site(self):
        from test_source_cycle import fixture
        from plan_source_cycle import plan_multiple
        data=fixture();site=plan_multiple(data,99,0,200)['candidates'][0]
        from prepare_site import network
        coords,_,_=network(data)
        ids=list(range(12))
        site.update(sample_node_ids=ids,walk_points=[coords[n] for n in ids],
                    lake_route_parts=[[0,1,2,3,4,5,6],[6,7,8,9,10,11,0]],
                    input_validation={'failures':[]},_source_data=data,route_request_count=2)
        self.service.profiles['split']=('Synthetic split request',site)
        return site

    def test_split_budget_reserved_before_any_provider_call(self):
        self.split_site()
        with self.assertRaises(RuntimeError):self.service.route({'id':'split','mode':'SHORTEST'})
        self.assertEqual(0,self.client.calls)

    def test_two_request_sum_and_original_steps_with_five_vias_each(self):
        self.split_site();self.client.limit=2
        captured=[]
        def get(endpoint,params):
            captured.append(params);self.client.calls+=1
            start=(params['start_x'],params['start_y']);end=(params['end_x'],params['end_y'])
            return 200,response([[start,end]]),.1
        self.client.get=get
        result=self.service.route({'id':'split','mode':'SHORTEST'})
        self.assertEqual(2,result['route_request_count']);self.assertEqual(2,self.client.calls)
        self.assertEqual(2,len(result['paths']))
        self.assertEqual(result['paths'][0][-1],result['paths'][1][0])
        self.assertTrue(all(len(p['via_x'].split(','))==5 for p in captured))
        self.assertEqual(11,len(result['via']))
        self.assertAlmostEqual(sum(probe.meters(*p) for p in result['paths']),result['inspection']['distance_m'],places=1)

    def test_failed_second_request_discards_partial_paths(self):
        self.split_site();self.client.limit=2
        def get(endpoint,params):
            self.client.calls+=1
            return (200,self.client.payload,.1) if self.client.calls==1 else (503,{'status':'ERROR'},.1)
        self.client.get=get
        result=self.service.route({'id':'split','mode':'SHORTEST'})
        self.assertEqual([],result['paths']);self.assertEqual(2,self.client.calls)
        self.assertEqual('NOT_EVALUATED',result['inspection']['geometry_check'])

    def test_catalog_is_not_a_paid_route_lookup(self):
        data = self.service.catalog()
        self.assertEqual(8, len(data["profiles"]))
        self.assertEqual(0, self.client.calls)
        self.assertNotIn("paths", json.dumps(data))

    def test_duration_candidates_do_not_spend_route_calls_and_stay_source_only(self):
        result = self.service.candidates(dict(id="river-long", duration_minutes=10, walking_speed_kmh=4))
        self.assertEqual(3, len(result["candidates"]))
        self.assertEqual(0, self.client.calls)
        self.assertEqual(0, result["routing_calls_sent"])
        self.assertEqual(8, len(self.service.catalog()["profiles"]))

        self.assertEqual("NOT_ACCEPTED", result["recommendation_quality"])
        profile = result["candidates"][0]
        self.assertNotIn("paths", profile)
        self.assertEqual("river-long", profile["base_profile_id"])
        data = self.service.route(dict(id=profile["id"], mode="SHORTEST"))
        self.assertEqual(1, self.client.calls)
        self.assertEqual(self.catalog["river-long"][1]["walk_points"][0], data["start"])
        self.assertEqual(data["start"], data["end"])
        self.assertIn("target_validation", data["inspection"])
        self.assertIn("source_distance_comparison", data["inspection"])
        self.assertEqual(2, len(data["via"]))
        self.assertEqual(data["river_candidate"]["via_node_ids"][-1], data["river_candidate"]["turnpoint_node_id"])

    def test_distance_bounds_reach_provider_response_validation(self):
        result = self.service.candidates(dict(id="river-extended", duration_minutes=38,
                                             walking_speed_kmh=4, distance_range_m=[2000, 3000]))
        self.assertEqual(0, self.client.calls)
        self.assertTrue(result["candidates"])
        data = self.service.route(dict(id=result["candidates"][0]["id"], mode="SHORTEST"))
        self.assertEqual("FAIL", data["inspection"]["distance_validation"]["status"])
        self.assertIn("TARGET_DISTANCE_MISMATCH", data["inspection"]["failures"])
        self.assertEqual("NOT_ACCEPTED", data["recommendation_quality"])
        self.assertLessEqual(len(data["via"]), 5)
        comparison = data["candidate_comparison"]
        self.assertEqual("NO_VALIDATED_CANDIDATE", comparison["status"])
        self.assertIsNone(comparison["best_candidate_id"])
        self.assertEqual(1, comparison["tested_candidates"])
        self.assertGreater(comparison["untested_candidates"], 0)
        self.assertNotIn("paths", json.dumps(comparison))
        self.service.candidates(dict(id="river-extended", duration_minutes=38,
                                     walking_speed_kmh=4, distance_range_m=[2000, 3000]))
        self.assertEqual({}, self.service.trials)

    def test_park_scenario_does_not_include_home_access_in_park_distance(self):
        site = self.catalog["lake"][1]
        scenario = dict(requested_place="Test park", departure_address="Test home",
                        requested_park_distance_m=3000, distance_range_m=[2850, 3150],
                        distance_scope="PARK_WALK_ONLY; HOME_ACCESS_SEPARATE")
        site["request_scenario"] = scenario
        self.client.payload["route"]["properties"]["totalDistance"] = 1800
        data = self.service.route(dict(id="lake", mode="SHORTEST"))
        self.assertEqual(scenario, data["request_scenario"])
        self.assertEqual([2850, 3150], data["inspection"]["distance_validation"]["distance_range_m"])
        self.assertIn("TARGET_DISTANCE_MISMATCH", data["inspection"]["failures"])
        self.assertEqual("FAIL", data["inspection"]["geometry_check"])
        self.assertEqual("NOT_ACCEPTED", data["recommendation_quality"])

    def test_invalid_park_distance_scope_or_bounds_are_blocked_before_call(self):
        site = self.catalog["lake"][1]
        valid = dict(requested_place="Test park", departure_address="Test home",
                     requested_park_distance_m=3000, distance_range_m=[2850, 3150],
                     distance_scope="PARK_WALK_ONLY; HOME_ACCESS_SEPARATE")
        for change in (dict(distance_scope="HOME_AND_PARK"), dict(distance_range_m=[3150, 2850]),
                       dict(requested_park_distance_m=True), dict(distance_range_m=[float("nan"), 3150]),
                       dict(distance_range_m=None)):
            site["request_scenario"] = dict(valid, **change)
            with self.assertRaises(ValueError):
                self.service.route(dict(id="lake", mode="SHORTEST"))
        self.assertEqual(0, self.client.calls)

    def test_out_of_range_target_and_invalid_candidate_requests_make_no_calls(self):
        result = self.service.candidates(dict(id="river-long", duration_minutes=30, walking_speed_kmh=4))
        self.assertEqual([], result["candidates"])
        for request in [dict(id="lake", duration_minutes=10, walking_speed_kmh=4),
                        dict(id="river-long", duration_minutes=True, walking_speed_kmh=4),
                        dict(id="river-long", duration_minutes=10, walking_speed_kmh=4, start=[127, 37])]:
            with self.assertRaises(ValueError):
                self.service.candidates(request)
        self.assertEqual(0, self.client.calls)

    def test_generated_source_candidates_are_bounded_and_old_ids_are_invalidated(self):
        first = self.service.candidates(dict(id="river-long", duration_minutes=10, walking_speed_kmh=4))
        cid = first["candidates"][0]["id"]
        self.service.candidates(dict(id="river-long", duration_minutes=12, walking_speed_kmh=4))
        self.assertLessEqual(len(self.service.profiles), 11)
        with self.assertRaises(ValueError):
            self.service.route(dict(id=cid, mode="SHORTEST"))
        self.assertEqual(0, self.client.calls)

    def test_custom_source_selection_reaches_request_without_arbitrary_coordinates(self):
        site = self.catalog["sindae-north"][1]
        data = self.service.route(dict(id="sindae-north", mode="SHORTEST"))
        self.assertEqual(site["walk_points"][7], data["via"][-1])
        self.assertEqual(5, len(data["via"]))
        self.assertEqual(1, self.client.calls)

    def test_invalid_or_arbitrary_coordinate_request_is_blocked_before_call(self):
        for request in [dict(id="unknown", mode="SHORTEST"), dict(id="river", mode="INVALID"),
                        dict(id="river", mode="SHORTEST", start=[127, 37]), {}, None]:
            with self.assertRaises(ValueError):
                self.service.route(request)
        self.assertEqual(0, self.client.calls)

    def test_failed_source_input_is_blocked_before_a_paid_call(self):
        self.catalog["river"][1]["input_validation"]["failures"].append("INPUT_POINT_NOT_AN_ELIGIBLE_SOURCE_NODE")
        with self.assertRaises(ValueError):
            self.service.route(dict(id="river", mode="SHORTEST"))
        self.assertEqual(0, self.client.calls)

    def test_source_audit_survives_catalog_and_response_without_becoming_approval(self):
        catalog = self.service.catalog()["profiles"]
        audit = next(p for p in catalog if p["id"] == "lake")["input_validation"]
        point4 = next(p for p in audit["points"] if p["label"] == "4")
        self.assertEqual(7853789387, point4["source_node_id"])
        self.assertTrue(point4["bridge_tagged"])
        self.assertEqual("UNVERIFIED", audit["walking_access"])
        data = self.service.route(dict(id="river", mode="SHORTEST"))
        self.assertIn("input_validation", data)
        self.assertEqual("NOT_ACCEPTED", data["recommendation_quality"])

    def test_route_steps_keep_separation_and_same_point_via_five(self):
        data = self.service.route(dict(id="river", mode="SHORTEST"))
        self.assertEqual(2, len(data["paths"]))
        self.assertEqual(5, len(data["via"]))
        self.assertEqual(data["start"], data["end"])
        self.assertEqual("NOT_ACCEPTED", data["recommendation_quality"])
        self.assertEqual(1, self.client.calls)
        self.assertEqual(self.client.params["start_x"], self.client.params["end_x"])

    def test_failure_is_not_cached_and_does_not_retry(self):
        self.client.payload = {"status": "ROUTE_RESULT_NOT_FOUND"}
        data = self.service.route(dict(id="river", mode="ACCESSIBLE"))
        self.assertEqual([], data["paths"])
        self.assertEqual("NOT_ACCEPTED", data["recommendation_quality"])
        with self.assertRaises(RuntimeError):
            self.service.route(dict(id="river", mode="SHORTEST"))
        self.assertEqual(1, self.client.calls)

    def test_malformed_geometry_is_never_drawn(self):
        self.client.payload = {"status": "OK", "route": {}}
        data = self.service.route(dict(id="river", mode="SHORTEST"))
        self.assertEqual([], data["paths"])
        self.assertIn("INVALID_RESPONSE_SCHEMA", data["inspection"]["failures"])

    def test_http_disallows_browser_origin_and_enforces_no_store(self):
        server = HTTPServer(("127.0.0.1", 0), make_handler(self.service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/profiles"
            headers = {"X-Review-Client": "android-route-review"}
            with urlopen(Request(url, headers=headers), timeout=2) as result:
                self.assertEqual("no-store", result.headers["Cache-Control"])
            with self.assertRaises(HTTPError) as raised:
                urlopen(Request(url, headers={**headers, "Origin": "http://outside.example"}), timeout=2)
            self.assertEqual(403, raised.exception.code)
            self.assertEqual(0, self.client.calls)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == "__main__":
    unittest.main()
