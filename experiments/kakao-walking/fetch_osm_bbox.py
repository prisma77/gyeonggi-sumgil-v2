"""Read a small OSM map extract around a sourced water boundary, once."""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def fetch(source_path, water_id, output, margin=150):
    if output.exists() or not output.resolve().is_relative_to(Path(__file__).resolve().parent):
        raise ValueError("New output inside the experiment folder required")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    water = next(e for e in source["osm"]["elements"] if e["type"] == "way" and e["id"] == water_id)
    geometry = water["geometry"]
    latitude = sum(p["lat"] for p in geometry) / len(geometry)
    dy = margin / 111195
    dx = dy / math.cos(math.radians(latitude))
    bbox = [min(p["lon"] for p in geometry) - dx, min(p["lat"] for p in geometry) - dy,
            max(p["lon"] for p in geometry) + dx, max(p["lat"] for p in geometry) + dy]
    url = "https://api.openstreetmap.org/api/0.6/map.json?" + urlencode({"bbox": ",".join(map(str, bbox))})
    with urlopen(Request(url, headers={"User-Agent": "GyeonggiSumgilRebootResearch/0.1",
                                      "Accept": "application/json"}), timeout=40) as response:
        raw = response.read(16_000_001)
    if len(raw) > 16_000_000:
        raise ValueError("Source size limit exceeded")
    data = json.loads(raw)
    nodes = {e["id"]: e for e in data["elements"] if e["type"] == "node"}
    for way in data["elements"]:
        if way["type"] == "way":
            way["geometry"] = [{"lon": nodes[n]["lon"], "lat": nodes[n]["lat"]} for n in way["nodes"]]
    result = {"source": {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                         "license": "ODbL 1.0", "attribution": "© OpenStreetMap contributors",
                         "license_url": "https://www.openstreetmap.org/copyright",
                         "geometry_derivation": "Exact coordinates of returned way node IDs"}, "osm": data}
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return {"file": str(output), "elements": len(data["elements"]),
            "steps": sum(e.get("tags", {}).get("highway") == "steps" for e in data["elements"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--water-way", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(fetch(args.source, args.water_way, args.output)))
