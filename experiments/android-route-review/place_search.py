"""Transient place discovery; never chooses a place or calls a walking API."""
import math
import re
import time
from datetime import datetime, timezone


def walking_category(value):
    # Names such as '공원주차장' are not evidence that the category is a park.
    if not isinstance(value, str):
        return False
    parts = [p.strip() for p in value.split(">")]
    return any(p in ("공원", "호수", "하천", "산책로", "수목원", "생태공원") for p in parts) and not any(
        p in ("주차장", "공영주차장", "버스정류장", "음식점", "카페") for p in parts)


class PlaceSearchService:
    def __init__(self, client):
        self.client = client
        self.available = {}
        self.expires = 0
        self.generation = 0

    def resolve(self, identifier):
        if not isinstance(identifier, str) or time.monotonic() > self.expires or identifier not in self.available:
            raise ValueError("Select a place from the current search; no arbitrary coordinates")
        return dict(self.available[identifier])

    def search(self, request):
        self.available = {}
        self.generation += 1
        if not isinstance(request, dict) or set(request) != {"query", "location"}:
            raise ValueError("Explicit query and location state required")
        query, location = request["query"], request["location"]
        if not isinstance(query, str) or len(query) > 100:
            raise ValueError("Invalid query")
        query = query.strip()
        words = query.split()
        # Explicit province/city tokens only. '광주' alone is ambiguous, so do not infer its province.
        region_aliases = {"서울": "서울", "서울특별시": "서울", "부산": "부산", "부산광역시": "부산",
                          "인천": "인천", "대구": "대구", "대전": "대전", "울산": "울산", "세종": "세종",
                          "경기": "경기", "경기도": "경기", "강원": "강원", "강원특별자치도": "강원",
                          "충북": "충북", "충청북도": "충북", "충남": "충남", "충청남도": "충남",
                          "전북": "전북", "전북특별자치도": "전북", "전남": "전남", "전라남도": "전남",
                          "경북": "경북", "경상북도": "경북", "경남": "경남", "경상남도": "경남",
                          "제주": "제주", "제주특별자치도": "제주", "광주광역시": "광주"}
        explicit_region = region_aliases.get(words[0]) if words else None
        place_terms = [re.sub(r"\s+", "", word) for word in words
                       if len(word) > 1 and word.endswith(("공원", "호수", "하천", "수목원"))]
        if location is not None:
            if not isinstance(location, dict) or set(location) != {"x", "y", "accuracy_m", "age_ms"}:
                raise ValueError("Location quality required")
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in location.values()):
                raise ValueError("Invalid location")
            if not (-180 <= location["x"] <= 180 and -90 <= location["y"] <= 90
                    and 0 <= location["accuracy_m"] <= 150 and 0 <= location["age_ms"] <= 120000):
                raise ValueError("Fresh accurate location required")
        if not query and location is None:
            raise ValueError("Nearby discovery requires location; no default centre")
        keywords = [query] if query else ["공원", "호수", "하천"]
        # Reserve the entire search before spending; never return a partial failure as success.
        if self.client.limit - self.client.calls < len(keywords):
            raise RuntimeError("Place search budget exhausted")
        candidates, truncated = {}, False
        for keyword in keywords:
            params = dict(query=keyword, size=15, page=1, sort="accuracy")
            if location is not None:
                params.update(x=location["x"], y=location["y"], sort="distance")
                if not query:
                    params["radius"] = 3000
            status, payload, _ = self.client.get("/v2/local/search/keyword.json", params)
            if status != 200 or not isinstance(payload.get("documents"), list):
                raise RuntimeError("Place search failed; no fallback or retry")
            truncated |= payload.get("meta", {}).get("is_end") is False
            for document in payload["documents"]:
                if not isinstance(document, dict):
                    continue
                if not walking_category(document.get("category_name", "")):
                    continue
                address = document.get("address_name", "")
                name = document.get("place_name", "")
                if not isinstance(address, str) or not isinstance(name, str):
                    continue
                if explicit_region and not address.startswith(explicit_region + " "):
                    continue
                if query and any(term not in name.replace(" ", "") for term in place_terms):
                    continue
                try:
                    x, y = float(document["x"]), float(document["y"])
                    distance = float(document["distance"]) if location is not None and document.get("distance") else None
                    if not (-180 <= x <= 180 and -90 <= y <= 90) or (distance is not None and (not math.isfinite(distance) or distance < 0)):
                        continue
                    candidate = dict(id=document["id"], name=document["place_name"],
                                     address=document.get("road_address_name") or document.get("address_name", ""),
                                     category=document["category_name"], x=x, y=y, distance_m=distance)
                    if not all(isinstance(candidate[k], str) and candidate[k] for k in ("id", "name", "address", "category")):
                        continue
                    candidates[candidate["id"]] = candidate
                except (KeyError, TypeError, ValueError):
                    continue
        items = list(candidates.values())
        if location is not None:
            items.sort(key=lambda p: p["distance_m"] if p["distance_m"] is not None else math.inf)
        # Minimal selectable POIs in RAM for this debug session only; never store GPS or raw response.
        self.available = {item['id']: {key: item[key] for key in ('id', 'name', 'x', 'y', 'category')} for item in items[:5]}
        self.expires = time.monotonic() + 600
        return dict(query=query, scope="NEARBY_3KM" if not query else "NAMED_QUERY",
                    location_used=location is not None, candidates=items[:5],
                    truncated=truncated or len(items) > 5, source="카카오 장소 검색 API",
                    requested_at=datetime.now(timezone.utc).isoformat(),
                    calls_sent=self.client.calls, call_limit=self.client.limit,
                    route_calls_sent=0, recommendation_quality="NOT_ACCEPTED")
