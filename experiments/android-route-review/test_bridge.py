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

    def test_catalog_is_not_a_paid_route_lookup(self):
        data = self.service.catalog()
        self.assertEqual(3, len(data["profiles"]))
        self.assertEqual(0, self.client.calls)
        self.assertNotIn("paths", json.dumps(data))

    def test_invalid_or_arbitrary_coordinate_request_is_blocked_before_call(self):
        for request in [dict(id="unknown", mode="SHORTEST"), dict(id="river", mode="INVALID"),
                        dict(id="river", mode="SHORTEST", start=[127, 37]), {}, None]:
            with self.assertRaises(ValueError):
                self.service.route(request)
        self.assertEqual(0, self.client.calls)

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
