"""Explicit park scenario: two access requests, then one user-triggered park request.

Provider geometry stays in RAM and is never cached. Access metrics are separate
from the requested park distance. This is a research runner, not an app geocoder.
"""
import argparse
from datetime import datetime, timezone
from http.server import HTTPServer
import json
from pathlib import Path

from bridge import ReviewService, load_catalog, make_handler, probe, scenario_conditions


def summarize_access(client, home, entry, label):
    start, end = (home, entry) if label == "outbound" else (entry, home)
    params = dict(start_x=start[0], start_y=start[1], end_x=end[0], end_y=end[1],
                  input_coord="WGS84", output_coord="WGS84", route_mode="SHORTEST")
    status, payload, _ = client.get("/v2/routing/walk", params)
    inspection = probe.inspect(payload, start, end)
    summary = dict(direction=label, http_status=status, inspection=inspection,
                   requested_at=datetime.now(timezone.utc).isoformat(),
                   address_scope="ADDRESS_GEOCODE; ACTUAL_BUILDING_EXIT_UNVERIFIED",
                   park_scope="SOURCE_LOOP_NODE; PUBLIC_ENTRANCE_UNVERIFIED")
    print(json.dumps(dict(access=summary), ensure_ascii=True), flush=True)
    return summary  # Metrics only. No response, provider coordinates or paths retained.


class ScenarioService(ReviewService):
    def __init__(self, profiles, client, access):
        super().__init__(profiles, client)
        self.access = access

    def route(self, request):
        result = super().route(request)
        result["access_summary"] = self.access
        print(json.dumps({k: result[k] for k in ("id", "mode", "http_status", "inspection",
                                                "requested_at", "calls_sent", "call_limit",
                                                "recommendation_quality")}, ensure_ascii=True), flush=True)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8769)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise ValueError("Invalid local port")
    profiles = load_catalog(args.catalog.resolve())
    if len(profiles) != 1:
        raise ValueError("One explicitly reviewed scenario profile required")
    _, site = next(iter(profiles.values()))
    scenario = scenario_conditions(site)
    if scenario is None or site["input_validation"]["failures"]:
        raise ValueError("Valid scenario and source audit required")
    key = probe.read_key()
    if not key:
        raise ValueError("Local REST key required")
    local = probe.Client(key, 1)
    status, payload, _ = local.get("/v2/local/search/address.json", {"query": scenario["departure_address"]})
    documents = payload.get("documents", [])
    if status != 200 or len(documents) != 1:
        raise ValueError("Address needs confirmation; no departure substitution")
    home = probe.point([float(documents[0]["x"]), float(documents[0]["y"])])
    entry = site["walk_points"][0]
    client = probe.Client(key, 3)
    # Bind before spending route calls; do not retry after a port/network failure.
    server = HTTPServer(("127.0.0.1", args.port), make_handler(ReviewService(profiles, client)))
    access = [summarize_access(client, home, entry, label) for label in ("outbound", "inbound")]
    server.RequestHandlerClass = make_handler(ScenarioService(profiles, client, access))
    print(f"Scenario bridge on {args.port}; walking calls 2/3; remaining park request requires explicit tap.", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        print("Scenario stopped: check address, reviewed source, local key and network. No retry.", flush=True)
        raise SystemExit(2)
