"""Render licensed source geometry for review, without tiles or invented paths."""
import html
import json
import math
from pathlib import Path

from prepare_site import eligible

ROOT = Path(__file__).resolve().parent


def render_map(source_path, title, water_source=None, input_comparison=False):
    source = json.loads(source_path.read_text(encoding="utf-8"))
    elements = source["osm"]["elements"]
    walking = [e for e in elements if e.get("tags", {}).get("highway")]
    points = [p for e in walking for p in e.get("geometry", [])]
    if not points:
        raise ValueError("No walking source geometry")
    lat = sum(p["lat"] for p in points) / len(points)
    scale = math.cos(math.radians(lat))
    xmin, xmax = min(p["lon"] for p in points) * scale, max(p["lon"] for p in points) * scale
    ymin, ymax = min(p["lat"] for p in points), max(p["lat"] for p in points)
    zoom = min(900 / (xmax - xmin), 650 / (ymax - ymin))

    def xy(p):
        return f'{50 + (p["lon"] * scale - xmin) * zoom:.2f},{700 - (p["lat"] - ymin) * zoom:.2f}'

    drawings = []
    water_elements = elements if water_source is None else json.loads(water_source.read_text(encoding="utf-8"))["osm"]["elements"]
    for e in water_elements:
        tags = e.get("tags", {})
        if tags.get("natural") == "water" or tags.get("waterway") == "river":
            geometry = e.get("geometry", [])
            if not geometry:
                continue
            kind = "polygon" if tags.get("natural") == "water" else "polyline"
            drawings.append(f'<{kind} points="{" ".join(map(xy, geometry))}" fill="{("#ccecf7" if kind == "polygon" else "none")}" stroke="#88c5dd" stroke-width="5"/>')
    rows = []
    for e in walking:
        tags = e.get("tags", {})
        category = "candidate" if eligible(tags) else "excluded"
        if tags.get("highway") == "cycleway" and tags.get("foot") not in ("yes", "designated", "permissive"):
            category = "unknown"
        detail = html.escape(json.dumps(tags, ensure_ascii=False))
        link = f'https://www.openstreetmap.org/way/{e["id"]}'
        drawings.append(f'<a href="{link}" target="_blank" rel="noopener"><polyline class="{category}" points="{" ".join(map(xy, e.get("geometry", [])))}"><title>way {e["id"]}: {detail}</title></polyline></a>')
        rows.append(f'<tr><td><a href="{link}" target="_blank" rel="noopener">{e["id"]}</a></td><td>{category}</td><td>{detail}</td></tr>')
    comparison_note = ""
    if input_comparison:
        original = json.loads((ROOT / "drafts/lake.probe.json").read_text(encoding="utf-8"))
        alternative_path = ROOT / "drafts/lake.alternative.probe.json"
        for i, (node, p) in enumerate(zip(original["sample_node_ids"], original["walk_points"])):
            x, y = xy({"lon": p[0], "lat": p[1]}).split(",")
            drawings.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#ce4c2f" stroke="white" stroke-width="1.5"><title>원본 입력 {i}: OSM node {node}</title></circle>')
            drawings.append(f'<text x="{float(x)+8}" y="{float(y)-5}" font-size="13" fill="#9c3225">{i}</text>')
        if alternative_path.exists():
            alternative = json.loads(alternative_path.read_text(encoding="utf-8"))
            change = alternative["input_change"]
            p = alternative["walk_points"][change["index"]]
            x, y = xy({"lon": p[0], "lat": p[1]}).split(",")
            drawings.append(f'<circle cx="{x}" cy="{y}" r="7" fill="#375cc9" stroke="white" stroke-width="2"><title>비교 입력: OSM node {change["alternative_source_node"]}</title></circle>')
            drawings.append(f'<text x="{float(x)+10}" y="{float(y)+14}" font-size="13" fill="#375cc9">비교</text>')
            comparison_note = f'<p>붉은 점: 원본 입력 8개 · 파란 점: 입력 {change["index"]}의 비교 후보.<br>같은 OSM 보행망에서 원본과 {change["source_offset_m"]}m 떨어진 실제 노드를 사용했습니다. 현재 통행·추천 품질은 미검증입니다.</p>'
    return f'''<section><h2>{html.escape(title)}</h2><p>원본 기준: {html.escape(source["osm"].get("osm3s", {}).get("timestamp_osm_base", "미상"))} · 구간 {len(walking)}개</p>
    {comparison_note}
    <svg role="img" aria-label="{html.escape(title)} 원본 보행망" viewBox="0 0 1000 760">{"".join(drawings)}</svg>
    <details><summary>구간 ID와 원본 태그 확인</summary><table><thead><tr><th>OSM ID</th><th>분류</th><th>태그</th></tr></thead><tbody>{"".join(rows)}</tbody></table></details></section>'''


def main():
    content = render_map(ROOT / "sources/lake-walkways.osm.json", "원천호수 후보 수역과 주변 보행망", input_comparison=True)
    content += render_map(ROOT / "sources/river-walkways.osm.json", "탄천 일부 구간의 보행망", ROOT / "sources/local-targets.osm.json")
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>경기숨길 실험 자료 검토</title><style>
    body{font-family:system-ui,sans-serif;background:#f4f7f8;color:#15313e;margin:0;padding:24px;line-height:1.6}
    main{max-width:1100px;margin:auto}section{background:white;padding:20px;margin:24px 0;border-radius:12px}
    h1{margin:0}svg{display:block;width:100%;max-height:650px;background:#fafcfc;border:1px solid #d8e3e7}
    polyline{fill:none;stroke-linecap:round;stroke-linejoin:round}.candidate{stroke:#16784f;stroke-width:3}
    .unknown{stroke:#c88308;stroke-width:3}.excluded{stroke:#a2a8ae;stroke-width:2;stroke-dasharray:5 4}
    a:hover polyline{stroke:#b42c63;stroke-width:6}table{border-collapse:collapse;width:100%;font-size:13px}
    td,th{text-align:left;padding:8px;border-bottom:1px solid #d8e3e7;overflow-wrap:anywhere}td:last-child{max-width:600px}
    .notice{padding:16px;background:#fff3d6;border-left:4px solid #c88308}a{color:#17567b}
    </style><main><h1>경기숨길 실험 자료 검토</h1>
    <p class="notice">OSM 원본 보행망과 실험 입력을 표시합니다. 카카오 응답은 별도 검사 도구에서 검증하며, 현재 통행 가능 여부와 추천 품질은 미검증입니다.</p>
    <p>초록: 보행 후보 · 주황: 보행 허용 태그가 없는 자전거도로 · 회색: 면 형상 또는 제한 구간.<br>
    선을 가리키면 원본 태그, 클릭하면 해당 OSM 구간을 확인할 수 있습니다. 배경 지도와 임의 연결선은 사용하지 않습니다.</p>'''
    page += content + '''<p>© OpenStreetMap contributors · <a href="https://www.openstreetmap.org/copyright">ODbL 1.0 및 출처</a><br>
    원본 기준 시각은 전체 데이터베이스 시각이며 개별 구간의 현장 관측 시각을 뜻하지 않습니다.</p></main></html>'''
    (ROOT / "review.html").write_text(page, encoding="utf-8")
    print("Source review generated; Kakao requests: 0.")


if __name__ == "__main__":
    main()
