"""Loopback-only debug bridge. No key, provider response or route file is served."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import sys

EXPERIMENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENTS / "kakao-walking"))
import probe
from audit_inputs import audit_inputs


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
        site["input_validation"] = audit_inputs(site, json.loads(source_path.read_text(encoding="utf-8-sig")))
        profiles[identifier] = (entry["label"], site)
    if not profiles:
        raise ValueError("Empty catalog")
    return profiles


class ReviewService:
    def __init__(self, profiles, client):
        self.profiles, self.client = profiles, client

    def catalog(self):
        # Independent OSM inputs only. No routing requests, no Kakao response cache.
        return {"profiles": [dict(id=identifier, label=label, name=site["name"],
                                 shape=site["shape"], source=site["walk_source"],
                                 input_change=site.get("input_change"),
                                 input_validation=site["input_validation"],
                                 start=site["walk_points"][0])
                             for identifier, (label, site) in self.profiles.items()],
                "calls_sent": self.client.calls, "call_limit": self.client.limit}

    def route(self, request):
        if not isinstance(request, dict) or set(request) != {"id", "mode"}:
            raise ValueError("Only explicit id and mode accepted")
        identifier, mode = request["id"], request["mode"]
        if not isinstance(identifier, str) or identifier not in self.profiles or mode not in probe.MODES:
            raise ValueError("Unknown profile or mode")
        _, site = self.profiles[identifier]
        if site["input_validation"]["failures"]:
            raise ValueError("Source input validation failed; no routing request sent")
        _, start, end, via, shape = next(case for case in probe.cases(site["walk_points"], site["shape"])
                                        if case[0] == "same_point_via_5")
        params = dict(start_x=start[0], start_y=start[1], end_x=end[0], end_y=end[1],
                      input_coord="WGS84", output_coord="WGS84", route_mode=mode,
                      via_x=",".join(str(p[0]) for p in via),
                      via_y=",".join(str(p[1]) for p in via))
        status, payload, elapsed = self.client.get("/v2/routing/walk", params)
        result = probe.inspect(payload, start, end, shape, site["reference_walkway"],
                               site["water_boundary"], 20, site["reference_segments"], via)
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
        return dict(id=identifier, mode=mode, http_status=status, inspection=result,
                    paths=paths, start=start, end=end, via=via,
                    source=site["walk_source"], water_source=site.get("water_source"),
                    input_validation=site["input_validation"],
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
            if self.path != "/route":
                self.reply(404, {"error": "NOT_FOUND"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 1024 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Invalid body")
                request = json.loads(self.rfile.read(size))
                self.reply(200, service.route(request))
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
    args = parser.parse_args()
    if not 1 <= args.max_calls <= 20 or not 1024 <= args.port <= 65535:
        raise ValueError("Invalid limits")
    key = probe.read_key()
    if not key:
        raise ValueError("REST key missing")
    service = ReviewService(load_catalog(args.catalog.resolve()), probe.Client(key, args.max_calls))
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
