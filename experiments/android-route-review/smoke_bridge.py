"""Explicit one-request debug smoke test; never writes route data or prints keys."""
import argparse
import json
from urllib.request import Request, urlopen
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", required=True, choices=("river", "lake", "lake-comparison"))
    parser.add_argument("--mode", default="SHORTEST", choices=("SHORTEST", "BROAD_FIRST", "ACCESSIBLE"))
    args = parser.parse_args()
    request = Request("http://127.0.0.1:8769/route",
                      data=json.dumps(dict(id=args.route, mode=args.mode)).encode("utf-8"),
                      headers={"Content-Type": "application/json", "X-Review-Client": "android-route-review"})
    with urlopen(request, timeout=35) as reply:
        data = reply.read(8_000_001)
        if len(data) > 8_000_000 or reply.headers.get("Cache-Control") != "no-store":
            raise ValueError("Invalid delivery")
        result = json.loads(data)
    if result["id"] != args.route or result["mode"] != args.mode:
        raise ValueError("Response identity changed")
    inspection = result["inspection"]
    paths = result["paths"]
    if paths and (len(paths) != inspection["step_count"] or sum(map(len, paths)) != inspection["coordinate_count"]):
        raise ValueError("Geometry delivery mismatch")
    print(json.dumps(dict(http_status=result["http_status"], api_status=inspection["api_status"],
                         source_id=result["id"], paths=len(paths),
                         coordinates=sum(map(len, paths)), distance_m=inspection.get("distance_m"),
                         time_s=inspection.get("time_s"),
                         geometry_check=inspection["geometry_check"], failures=inspection.get("failures"),
                         unresolved=inspection.get("unresolved"),
                         recommendation_quality=result["recommendation_quality"],
                         calls_sent=result["calls_sent"], no_store=True), ensure_ascii=True))
    return 0 if result["http_status"] == 200 and inspection["api_status"] == "OK" and paths else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError):
        print("Smoke failed; no retry and no raw response logged.", file=sys.stderr)
        sys.exit(2)
