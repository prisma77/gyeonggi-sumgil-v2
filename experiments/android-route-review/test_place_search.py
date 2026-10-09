"""Search-selection boundaries, with synthetic provider documents and no live requests."""
import copy
import unittest
from place_search import PlaceSearchService


def document(identifier="1", category="여행 > 공원", name="중앙공원", distance="100"):
    return dict(id=identifier, category_name=category, place_name=name, distance=distance,
                address_name="시험 지역", x="127", y="37")


class FakeClient:
    def __init__(self, documents=None, limit=12, status=200):
        self.calls, self.limit, self.requests, self.status = 0, limit, [], status
        self.documents = [document()] if documents is None else documents

    def get(self, endpoint, params):
        self.calls += 1; self.requests.append((endpoint, params))
        return self.status, dict(meta=dict(is_end=True), documents=copy.deepcopy(self.documents)), 0


class PlaceSearchTests(unittest.TestCase):
    origin = dict(x=127, y=37, accuracy_m=10, age_ms=1000)

    def test_no_location_nearby_makes_no_provider_request(self):
        client = FakeClient()
        with self.assertRaises(ValueError): PlaceSearchService(client).search(dict(query="", location=None))
        self.assertEqual(0, client.calls)

    def test_stale_or_inaccurate_origin_is_rejected_before_provider(self):
        for fields in (dict(age_ms=120001), dict(accuracy_m=151), dict(x=True)):
            client = FakeClient()
            with self.assertRaises(ValueError): PlaceSearchService(client).search(dict(query="", location=self.origin | fields))
            self.assertEqual(0, client.calls)

    def test_nearby_bounds_all_keywords_and_deduplicates_without_selection(self):
        client = FakeClient()
        result = PlaceSearchService(client).search(dict(query="", location=self.origin))
        self.assertEqual(["공원", "호수", "하천"], [p[1]["query"] for p in client.requests])
        self.assertTrue(all(p[1]["radius"] == 3000 and p[1]["sort"] == "distance" for p in client.requests))
        self.assertEqual(1, len(result["candidates"]))
        self.assertNotIn("selected", result)
        self.assertEqual(0, result["route_calls_sent"])

    def test_explicit_far_place_keeps_query_and_has_no_nearby_radius(self):
        client = FakeClient()
        PlaceSearchService(client).search(dict(query="부산 중앙공원", location=self.origin))
        self.assertEqual("부산 중앙공원", client.requests[0][1]["query"])
        self.assertNotIn("radius", client.requests[0][1])

    def test_named_search_without_location_does_not_invent_distance(self):
        client = FakeClient()
        result = PlaceSearchService(client).search(dict(query="중앙공원", location=None))
        self.assertNotIn("x", client.requests[0][1])
        self.assertIsNone(result["candidates"][0]["distance_m"])
        self.assertFalse(result["location_used"])

    def test_parking_and_cafe_with_park_names_are_not_walk_candidates(self):
        client = FakeClient([document("1", "교통 > 주차장", "중앙공원 주차장"),
                             document("2", "음식점 > 카페", "중앙공원 카페"), document("3")])
        result = PlaceSearchService(client).search(dict(query="중앙공원", location=None))
        self.assertEqual(["3"], [p["id"] for p in result["candidates"]])

    def test_same_names_are_returned_as_separate_candidates(self):
        client = FakeClient([document("1"), document("2")])
        result = PlaceSearchService(client).search(dict(query="중앙공원", location=self.origin))
        self.assertEqual(2, len(result["candidates"]))

    def test_empty_results_do_not_trigger_a_current_location_substitution(self):
        client = FakeClient([])
        result = PlaceSearchService(client).search(dict(query="없는 공원", location=self.origin))
        self.assertEqual([], result["candidates"])
        self.assertEqual(1, client.calls)

    def test_insufficient_budget_is_rejected_before_any_partial_request(self):
        client = FakeClient(limit=2)
        with self.assertRaises(RuntimeError): PlaceSearchService(client).search(dict(query="", location=self.origin))
        self.assertEqual(0, client.calls)

    def test_http_error_has_no_retry_or_fallback(self):
        client = FakeClient(status=401)
        with self.assertRaises(RuntimeError): PlaceSearchService(client).search(dict(query="중앙공원", location=self.origin))
        self.assertEqual(1, client.calls)

    def test_provider_fuzzy_results_cannot_override_explicit_region(self):
        wrong = document("1"); wrong["address_name"] = "경기 부천시 중동"
        right = document("2"); right["address_name"] = "부산 중구 대청동"
        client = FakeClient([wrong, right])
        result = PlaceSearchService(client).search(dict(query="부산 중앙공원", location=self.origin))
        self.assertEqual(["2"], [p["id"] for p in result["candidates"]])

    def test_provider_fuzzy_results_must_keep_requested_park_name(self):
        client = FakeClient([document("1", name="화명생태공원 중앙광장"), document("2", name="중앙공원")])
        result = PlaceSearchService(client).search(dict(query="중앙공원", location=None))
        self.assertEqual(["2"], [p["id"] for p in result["candidates"]])


if __name__ == "__main__": unittest.main()
