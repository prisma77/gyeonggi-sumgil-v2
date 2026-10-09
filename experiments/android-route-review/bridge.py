"""Loopback-only debug bridge. No key, provider response or route file is served."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
from pathlib import Path
import re
import sys

EXPERIMENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENTS / "kakao-walking"))
import probe
from audit_inputs import audit_inputs
from plan_river_candidates import candidate_id, compare_distance, inspect_distance, inspect_target, plan
from compare_candidates import compare, trial_summary
from place_search import PlaceSearchService


def scenario_conditions(site):
    scenario = site.get("request_scenario")
    if scenario is None:
        return None
    if not isinstance(scenario, dict):
        raise ValueError("Invalid request scenario")
    bounds, target = scenario.get("distance_range_m"), scenario.get("requested_park_distance_m")
    if (not isinstance(bounds, list) or len(bounds) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in [*bounds, target]) or
            not 0 < bounds[0] <= target <= bounds[1] <= 20000 or
            scenario.get("distance_scope") != "PARK_WALK_ONLY; HOME_ACCESS_SEPARATE" or
            any(not isinstance(scenario.get(k), str) or not scenario[k].strip()
                for k in ("requested_place", "departure_address"))):
        raise ValueError("Explicit park distance and separate home access required")
    return scenario


def load_catalog(path):
    entries = json.loads(path.read_text(encoding="utf-8-sig"))
    profiles = {}
    for entry in entries:
        identifier = entry["id"]
        if not re.fullmatch(r"[a-z0-9-]{1,40}", identifier) or identifier in profiles:
            raise ValueError("Invalid profile id")
        site_path = (path.parent / entry["site"]).resolve()
        if not site_path.is_relative_to(EXPERIMENTS):
            raise ValueError("Site must be inside experiments")
        source_path = (path.parent / entry["source_file"]).resolve()
        if not source_path.is_relative_to(EXPERIMENTS):
            raise ValueError("Source must be inside experiments")
        site = probe.load_site(site_path)
        source = json.loads(source_path.read_text(encoding="utf-8-sig"))
        site["input_validation"] = audit_inputs(site, source)
        site["_source_data"] = source
        profiles[identifier] = (entry["label"], site)
    if not profiles:
        raise ValueError("Empty catalog")
    return profiles


class ReviewService:
    def __init__(self, profiles, client, place_search=None):
        self.base_profiles, self.profiles, self.client = dict(profiles), dict(profiles), client
        self.place_search = place_search
        self.trials = {}  # Metrics/decisions only: never store provider paths or responses.
        self.generated_ids = set()

    @staticmethod
    def profile(identifier, label, site):
        return dict(id=identifier, label=label, name=site["name"], shape=site["shape"],
                    source=site["walk_source"], input_change=site.get("input_change"),
                    input_validation=site["input_validation"], start=site["walk_points"][0],
                    request_scenario=scenario_conditions(site),
                    river_candidate=site.get("river_candidate"), base_profile_id=site.get("base_profile_id", identifier))

    def catalog(self):
        # Independent OSM inputs only. No routing requests, no Kakao response cache.
        return {"profiles": [self.profile(identifier, label, site)
                             for identifier, (label, site) in self.base_profiles.items()],
                "calls_sent": self.client.calls, "call_limit": self.client.limit,
                "place_calls_sent": self.place_search.client.calls if self.place_search else 0,
                "place_call_limit": self.place_search.client.limit if self.place_search else 0}

    def candidates(self, request):
        required = {"id", "duration_minutes", "walking_speed_kmh"}
        if not isinstance(request, dict) or not required <= set(request) or set(request) - required - {"distance_range_m"}:
            raise ValueError("Explicit base profile, duration and assumed speed required")
        identifier = request["id"]
        if not isinstance(identifier, str) or identifier not in self.base_profiles:
            raise ValueError("Known original source profile required")
        label, site = self.base_profiles[identifier]
        if site["input_validation"]["failures"]:
            raise ValueError("Source audit failed")
        # Source candidates only; never cache a provider response or send a routing call here.
        source = site["_source_data"]
        clean_site = {k: v for k, v in site.items() if k != "_source_data"}
        result = plan(clean_site, source, request["duration_minutes"], request["walking_speed_kmh"], request.get("distance_range_m"))
        self.profiles = dict(self.base_profiles)  # Bound temporary source candidates to one generation.
        self.trials = {}
        self.generated_ids = set()
        exported = []
        for candidate in result["candidates"]:
            candidate["base_profile_id"] = identifier
            candidate["input_validation"] = audit_inputs(candidate, source)
            if candidate["input_validation"]["failures"]:
                raise ValueError("Generated source candidate failed audit")
            cid = candidate_id(identifier, candidate)
            meta = candidate["river_candidate"]
            title = f"{label} · 반환점 후보 · 원본 예상 {meta['source_estimated_minutes']:.1f}분"
            self.profiles[cid] = (title, candidate)
            self.generated_ids.add(cid)
            exported.append(self.profile(cid, title, candidate))
        result["candidates"] = exported
        result.update(calls_sent=self.client.calls, call_limit=self.client.limit, routing_calls_sent=0,
                      recommendation_quality="NOT_ACCEPTED")
        return result

    def route(self, request):
        if not isinstance(request, dict) or set(request) != {"id", "mode"}:
            raise ValueError("Only explicit id and mode accepted")
        identifier, mode = request["id"], request["mode"]
        if not isinstance(identifier, str) or identifier not in self.profiles or mode not in probe.MODES:
            raise ValueError("Unknown profile or mode")
        _, site = self.profiles[identifier]
        if site["input_validation"]["failures"]:
            raise ValueError("Source input validation failed; no routing request sent")
        scenario = scenario_conditions(site)
        start, end, via, shape = probe.routing_inputs(site)
        params = dict(start_x=start[0], start_y=start[1], end_x=end[0], end_y=end[1],
                      input_coord="WGS84", output_coord="WGS84", route_mode=mode,
                      via_x=",".join(str(p[0]) for p in via),
                      via_y=",".join(str(p[1]) for p in via))
        status, payload, elapsed = self.client.get("/v2/routing/walk", params)
        result = probe.inspect(payload, start, end, shape, site["reference_walkway"],
                               site["water_boundary"], 20, site["reference_segments"], via)
        candidate = site.get("river_candidate")
        distance_conditions = candidate if candidate else scenario
        if distance_conditions:
            distance = inspect_distance(result, distance_conditions)
            result["distance_validation"] = distance
            result.setdefault("failures", []).extend(distance["failures"])
            result.setdefault("unresolved", []).extend(distance["unresolved"])
            if distance["failures"]:
                result["geometry_check"] = "FAIL"
            elif distance["unresolved"] and result["geometry_check"] == "PASS":
                result["geometry_check"] = "INCOMPLETE"
        if candidate:
            target = inspect_target(result, candidate)
            result["target_validation"] = target
            result.setdefault("failures", []).extend(target["failures"])
            if target["failures"]:
                result["geometry_check"] = "FAIL"
            comparison = compare_distance(result, candidate)
            result["source_distance_comparison"] = comparison
            result.setdefault("unresolved", []).extend(comparison["unresolved"])
            if comparison["unresolved"] and result["geometry_check"] == "PASS":
                result["geometry_check"] = "INCOMPLETE"
        candidate_comparison = None
        if candidate and identifier in self.generated_ids:
            self.trials[identifier, mode] = trial_summary(identifier, mode, result, candidate, status)
            candidate_comparison = compare([trial for (cid, trial_mode), trial in self.trials.items()
                                            if trial_mode == mode and cid in self.generated_ids], len(self.generated_ids))
        paths = []
        # Retain each real step separately: never connect missing/gapped steps.
        if status == 200 and payload.get("status") == "OK" and "INVALID_RESPONSE_SCHEMA" not in result.get("failures", []):
            try:
                paths = [[probe.point(p) for p in step["path"]["points"]]
                         for leg in payload["route"]["legs"] for step in leg["steps"]]
                if not paths or any(len(p) < 2 for p in paths):
                    raise ValueError("Empty geometry")
            except (KeyError, TypeError, ValueError):
                paths = []
        return dict(id=identifier, mode=mode, shape=shape, http_status=status, inspection=result,
                    paths=paths, start=start, end=end, via=via,
                    source=site["walk_source"], water_source=site.get("water_source"),
                    input_validation=site["input_validation"],
                    river_candidate=candidate,
                    request_scenario=scenario,
                    candidate_comparison=candidate_comparison,
                    requested_at=datetime.now(timezone.utc).isoformat(), elapsed_s=round(elapsed, 2),
                    calls_sent=self.client.calls, call_limit=self.client.limit,
                    recommendation_quality="NOT_ACCEPTED", billing="CONSOLE_CHECK_REQUIRED")


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(35)
            super().setup()

        def log_message(self, *_):
            pass  # Never log request bodies, provider URLs or coordinates.

        def reply(self, status, body):
            data = json.dumps(body, ensure_ascii=True, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def allowed(self):
            # Also reject browser cross-origin requests; no CORS/preflight support.
            return (self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                    and not self.headers.get("Origin")
                    and self.headers.get("X-Review-Client") == "android-route-review")

        def do_GET(self):
            if not self.allowed():
                self.reply(403, {"error": "LOCAL_CLIENT_REQUIRED"})
            elif self.path == "/profiles":
                self.reply(200, service.catalog())
            else:
                self.reply(404, {"error": "NOT_FOUND"})

        def do_POST(self):
            if not self.allowed():
                self.reply(403, {"error": "LOCAL_CLIENT_REQUIRED"})
                return
            if self.path not in ("/route", "/river-candidates", "/places"):
                self.reply(404, {"error": "NOT_FOUND"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 1024 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Invalid body")
                request = json.loads(self.rfile.read(size))
                if self.path == "/places":
                    if service.place_search is None:
                        raise RuntimeError("Place search unavailable")
                    result = service.place_search.search(request)
                else:
                    result = service.route(request) if self.path == "/route" else service.candidates(request)
                self.reply(200, result)
            except (ValueError, TypeError, KeyError, UnicodeError):
                self.reply(400, {"error": "INVALID_REVIEW_REQUEST"})
            except (RuntimeError, OSError):
                self.reply(503, {"error": "BUDGET_OR_NETWORK_FAILURE_NO_RETRY"})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).with_name("catalog.json"))
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--max-calls", type=int, default=6)
    parser.add_argument("--max-search-calls", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.max_calls <= 20 or not 1 <= args.max_search_calls <= 30 or not 1024 <= args.port <= 65535:
        raise ValueError("Invalid limits")
    key = probe.read_key()
    if not key:
        raise ValueError("REST key missing")
    service = ReviewService(load_catalog(args.catalog.resolve()), probe.Client(key, args.max_calls),
                            PlaceSearchService(probe.Client(key, args.max_search_calls)))
    server = HTTPServer(("127.0.0.1", args.port), make_handler(service))
    server.timeout = 1
    print(f"Loopback review bridge on port {args.port}; limit {args.max_calls}; no response persistence.", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError, KeyError, TypeError):
        print("Bridge stopped: check local key, catalog and port. No raw errors logged.", file=sys.stderr)
        sys.exit(2)
