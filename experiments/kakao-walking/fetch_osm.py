"""One read-only Overpass request; save licensed OSM source, never Kakao data."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://overpass-api.de/api/interpreter"
ROOT = Path(__file__).resolve().parent


def fetch(query_path: Path, output: Path) -> dict:
    query = query_path.read_text(encoding="utf-8-sig")
    if "[timeout:" not in query or "[out:json]" not in query:
        raise ValueError("Explicit JSON output and server timeout required")
    output = output.resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        raise ValueError("Use a new output file inside the experiment folder")
    request = Request(ENDPOINT + "?" + urlencode({"data": query}),
                      headers={"User-Agent": "GyeonggiSumgilRebootResearch/0.1"})
    with urlopen(request, timeout=50) as response:
        raw = response.read(16_000_001)
    if len(raw) > 16_000_000:
        raise ValueError("Response exceeds research size limit")
    data = json.loads(raw)
    if not isinstance(data.get("elements"), list) or data.get("remark"):
        raise ValueError("Incomplete Overpass response; no data saved")
    result = {"source": {"url": ENDPOINT, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                         "license": "ODbL 1.0", "attribution": "© OpenStreetMap contributors",
                         "license_url": "https://www.openstreetmap.org/copyright",
                         "query": query}, "osm": data}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        data = fetch(args.query, args.output)
    except (OSError, ValueError, HTTPError, URLError) as error:
        print(json.dumps({"source_fetch": "FAILED", "error_type": type(error).__name__,
                          "http_status": getattr(error, "code", None),
                          "automatic_retry": False}))
        return 2
    print(json.dumps({"element_count": len(data["elements"]),
                      "osm_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
                      "targets": [{"type": e["type"], "id": e["id"],
                                   "tags": e.get("tags", {}),
                                   "geometry_points": len(e.get("geometry", []))}
                                  for e in data["elements"]]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
