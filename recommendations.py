from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_REVERSE_URL = "https://photon.komoot.io/reverse"
GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
FOURSQUARE_SEARCH_URL = "https://places-api.foursquare.com/places/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_RADIUS_METERS = 15000
MAX_RADIUS_METERS = 50000

GEOAPIFY_ATTRACTION_CATEGORIES = (
    "tourism.attraction",
    "tourism.sights",
    "entertainment.museum",
    "leisure.park",
)
GEOAPIFY_FOOD_CATEGORIES = (
    "catering.restaurant",
    "catering.cafe",
    "catering.fast_food",
)

RAINY_WEATHER_CODES = {
    51, 53, 55, 56, 57,
    61, 63, 65, 66, 67,
    71, 73, 75, 77,
    80, 81, 82, 85, 86,
    95, 96, 99,
}


class RecommendationError(RuntimeError):
    """Raised when an external recommendation source cannot return usable data."""


def provider_status() -> dict[str, bool]:
    return {
        "openstreetmap": True,
        "geoapify": bool(_geoapify_api_key()),
        "foursquare": bool(_foursquare_api_key()),
        "weather": True,
    }


def _geoapify_api_key() -> str:
    return os.getenv("GEOAPIFY_API_KEY", "").strip()


def _foursquare_api_key() -> str:
    return (
        os.getenv("FOURSQUARE_API_KEY", "").strip()
        or os.getenv("FSQ_API_KEY", "").strip()
    )


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    form_payload: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 12,
) -> Any:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "Roamory/1.0 (student travel planner; https://roamory-1.onrender.com)",
    }
    if headers:
        request_headers.update(headers)

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    elif form_payload is not None:
        data = urlencode(form_payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            message = "Recommendation service is temporarily busy."
        else:
            message = "External recommendation service is temporarily unavailable."
        raise RecommendationError(message) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RecommendationError(
            "External recommendation service is temporarily unavailable."
        ) from exc


def resolve_destination(destination: str) -> dict[str, Any]:
    """Resolve a destination without requiring an API key."""
    query = (destination or "").strip()
    if not query:
        raise RecommendationError("Destination is required.")

    try:
        result = _resolve_destination_osm(query)
        if result:
            return result
    except RecommendationError:
        pass

    if _geoapify_api_key():
        try:
            result = _resolve_destination_geoapify(query)
            if result:
                return result
        except RecommendationError:
            pass

    raise RecommendationError(
        "We could not identify that destination. Check the location name and try again."
    )


def _resolve_destination_osm(query: str) -> dict[str, Any] | None:
    params = urlencode(
        {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 5,
        }
    )
    response = _json_request(f"{NOMINATIM_SEARCH_URL}?{params}", timeout=10)
    if not isinstance(response, list):
        return None

    candidates: list[dict[str, Any]] = []
    for raw in response:
        lat = raw.get("lat")
        lon = raw.get("lon")
        if lat is None or lon is None:
            continue
        address = raw.get("address") or {}
        name = (
            raw.get("name")
            or address.get("city")
            or address.get("town")
            or address.get("village")
            or query
        )
        candidates.append(
            {
                "place_id": f"osm-{raw.get('osm_type')}-{raw.get('osm_id')}",
                "name": name,
                "address": raw.get("display_name") or query,
                "latitude": float(lat),
                "longitude": float(lon),
                "country": address.get("country"),
                "state": address.get("state"),
                "result_type": raw.get("type") or raw.get("addresstype"),
                "provider": "openstreetmap",
            }
        )

    if not candidates:
        return None

    return {
        "query": query,
        "selected": candidates[0],
        "alternatives": candidates[1:],
    }


def _resolve_destination_geoapify(query: str) -> dict[str, Any] | None:
    api_key = _geoapify_api_key()
    params = urlencode(
        {
            "text": query,
            "format": "json",
            "limit": 5,
            "apiKey": api_key,
        }
    )
    response = _json_request(f"{GEOAPIFY_GEOCODE_URL}?{params}")
    raw_results = response.get("results") or [] if isinstance(response, dict) else []

    candidates: list[dict[str, Any]] = []
    for raw in raw_results:
        lat = raw.get("lat")
        lon = raw.get("lon")
        if lat is None or lon is None:
            continue
        candidates.append(
            {
                "place_id": raw.get("place_id"),
                "name": (
                    raw.get("city")
                    or raw.get("town")
                    or raw.get("village")
                    or raw.get("name")
                    or query
                ),
                "address": raw.get("formatted") or raw.get("address_line2") or query,
                "latitude": float(lat),
                "longitude": float(lon),
                "country": raw.get("country"),
                "state": raw.get("state"),
                "result_type": raw.get("result_type"),
                "provider": "geoapify",
            }
        )

    if not candidates:
        return None

    return {
        "query": query,
        "selected": candidates[0],
        "alternatives": candidates[1:],
    }


def search_nearby_places(
    latitude: float,
    longitude: float,
    *,
    categories: str = "attractions",
    radius_meters: int = DEFAULT_RADIUS_METERS,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Search verified nearby places without any API-key dependency."""
    radius = max(500, min(int(radius_meters), MAX_RADIUS_METERS))
    result_count = max(1, min(int(max_results), 30))

    results = _search_photon_places(
        float(latitude),
        float(longitude),
        categories=categories,
        radius_meters=radius,
        max_results=result_count,
    )
    if results:
        return results

    raise RecommendationError(
        "Roamory could not find enough mapped places around this destination."
    )


def _search_photon_places(
    latitude: float,
    longitude: float,
    *,
    categories: str,
    radius_meters: int,
    max_results: int,
) -> list[dict[str, Any]]:
    if categories == "food":
        osm_tags = (
            "amenity:restaurant",
            "amenity:cafe",
            "amenity:fast_food",
        )
    else:
        osm_tags = (
            "tourism:viewpoint",
            "tourism:attraction",
            "tourism:museum",
            "leisure:park",
            "leisure:garden",
            "natural:waterfall",
            "natural:peak",
            "historic",
        )

    gathered: list[dict[str, Any]] = []
    seen: set[str] = set()
    per_tag_limit = min(max(8, max_results), 20)
    radius_km = max(1, min(int(round(radius_meters / 1000)), 50))
    request_failed = False

    for osm_tag in osm_tags:
        params = urlencode(
            {
                "lon": f"{longitude:.7f}",
                "lat": f"{latitude:.7f}",
                "radius": radius_km,
                "limit": per_tag_limit,
                "osm_tag": osm_tag,
            }
        )
        try:
            response = _json_request(
                f"{PHOTON_REVERSE_URL}?{params}",
                timeout=10,
            )
        except RecommendationError:
            request_failed = True
            continue

        if not isinstance(response, dict):
            continue

        for feature in response.get("features") or []:
            properties = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []
            if len(coordinates) < 2:
                continue

            lon = coordinates[0]
            lat = coordinates[1]
            if lat is None or lon is None:
                continue

            name = properties.get("name")
            if not name:
                continue

            osm_key = str(properties.get("osm_key") or "").strip()
            osm_value = str(properties.get("osm_value") or "").strip()
            if not _photon_place_is_relevant(osm_key, osm_value, str(name), categories):
                continue

            distance_km = round(
                haversine_km(latitude, longitude, float(lat), float(lon)), 2
            )
            if distance_km * 1000 > radius_meters:
                continue

            dedupe_key = str(name).strip().lower()
            if not dedupe_key or dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            category = f"{osm_key}:{osm_value}" if osm_key and osm_value else osm_key
            gathered.append(
                {
                    "place_id": f"photon-{properties.get('osm_type')}-{properties.get('osm_id')}",
                    "name": str(name).strip(),
                    "address": _photon_address(properties),
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "categories": [category] if category else [],
                    "rating": None,
                    "rating_source_scale": None,
                    "price_level": None,
                    "price_label": None,
                    "distance_km": distance_km,
                    "website": (properties.get("extra") or {}).get("website"),
                    "provider": "photon-openstreetmap",
                }
            )

    if not gathered and request_failed:
        raise RecommendationError("OpenStreetMap place lookup is temporarily unavailable.")

    if categories == "food":
        gathered.sort(key=lambda item: float(item.get("distance_km") or 9999))
    else:
        gathered.sort(
            key=lambda item: (
                _photon_attraction_priority(item.get("categories") or []),
                float(item.get("distance_km") or 9999),
            )
        )

    return gathered[:max_results]


def _photon_place_is_relevant(
    osm_key: str,
    osm_value: str,
    name: str,
    categories: str,
) -> bool:
    lowered = name.lower()

    if categories == "food":
        return osm_key == "amenity" and osm_value in {"restaurant", "cafe", "fast_food"}

    blocked_name_tokens = (
        "tourist home",
        "guest house",
        "guesthouse",
        "hotel",
        "resort",
        "lodge",
        "homestay",
        "hostel",
        "taxi",
        "bus stand",
        "bus station",
        "super market",
        "supermarket",
        "travel agency",
        "restaurant",
        "cafe",
    )
    if any(token in lowered for token in blocked_name_tokens):
        return False

    return (
        (osm_key == "tourism" and osm_value in {"viewpoint", "attraction", "museum"})
        or (osm_key == "leisure" and osm_value in {"park", "garden"})
        or (osm_key == "natural" and osm_value in {"waterfall", "peak"})
        or osm_key == "historic"
    )


def _photon_attraction_priority(categories: list[str]) -> int:
    values = set(categories)
    priority_groups = (
        {"tourism:viewpoint", "natural:waterfall", "natural:peak"},
        {"leisure:garden", "leisure:park", "tourism:museum"},
        {"historic:monument", "historic:memorial", "historic:castle", "historic:ruins"},
        {"tourism:attraction"},
    )
    for index, group in enumerate(priority_groups):
        if values & group:
            return index
    return 9


def _photon_address(properties: dict[str, Any]) -> str:
    street = " ".join(
        part
        for part in (
            str(properties.get("housenumber") or "").strip(),
            str(properties.get("street") or "").strip(),
        )
        if part
    )
    pieces = (
        street,
        properties.get("district"),
        properties.get("city"),
        properties.get("state"),
        properties.get("postcode"),
        properties.get("country"),
    )
    return ", ".join(
        str(value).strip()
        for value in pieces
        if value and str(value).strip()
    )


def _search_foursquare(
    latitude: float,
    longitude: float,
    *,
    categories: str,
    radius_meters: int,
    max_results: int,
) -> list[dict[str, Any]]:
    api_key = _foursquare_api_key()
    query_text = "restaurant" if categories == "food" else "tourist attraction"

    params: dict[str, Any] = {
        "query": query_text,
        "ll": f"{latitude:.7f},{longitude:.7f}",
        "radius": radius_meters,
        "limit": min(max_results, 30),
        "sort": "DISTANCE",
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Places-Api-Version": "2025-06-17",
    }
    response = _json_request(
        f"{FOURSQUARE_SEARCH_URL}?{urlencode(params)}",
        headers=headers,
    )

    results: list[dict[str, Any]] = []
    for raw in response.get("results") or []:
        lat = raw.get("latitude")
        lon = raw.get("longitude")
        if lat is None or lon is None:
            continue

        distance_km = round(
            haversine_km(latitude, longitude, float(lat), float(lon)), 2
        )
        if distance_km * 1000 > radius_meters:
            continue

        location = raw.get("location") or {}
        address = ", ".join(
            str(value).strip()
            for value in (
                location.get("address"),
                location.get("locality"),
                location.get("region"),
                location.get("postcode"),
                location.get("country"),
            )
            if value and str(value).strip()
        )
        category_rows = raw.get("categories") or []
        category_names = [
            item.get("name")
            for item in category_rows
            if isinstance(item, dict) and item.get("name")
        ]

        results.append(
            {
                "place_id": raw.get("fsq_place_id"),
                "name": raw.get("name") or "Unnamed place",
                "address": address,
                "latitude": float(lat),
                "longitude": float(lon),
                "categories": category_names,
                "rating": None,
                "rating_source_scale": None,
                "price_level": None,
                "price_label": None,
                "distance_km": distance_km,
                "website": raw.get("website"),
                "provider": "foursquare",
            }
        )

    results.sort(key=lambda item: float(item.get("distance_km") or 9999))
    return results


def _search_geoapify_places(
    latitude: float,
    longitude: float,
    *,
    categories: str,
    radius_meters: int,
    max_results: int,
) -> list[dict[str, Any]]:
    api_key = _geoapify_api_key()
    category_values = (
        GEOAPIFY_FOOD_CATEGORIES
        if categories == "food"
        else GEOAPIFY_ATTRACTION_CATEGORIES
    )
    params = urlencode(
        {
            "categories": ",".join(category_values),
            "filter": f"circle:{longitude},{latitude},{radius_meters}",
            "bias": f"proximity:{longitude},{latitude}",
            "limit": min(max_results, 20),
            "apiKey": api_key,
        }
    )
    response = _json_request(f"{GEOAPIFY_PLACES_URL}?{params}")

    results: list[dict[str, Any]] = []
    for feature in response.get("features") or []:
        properties = feature.get("properties") or {}
        lat = properties.get("lat")
        lon = properties.get("lon")
        if lat is None or lon is None:
            continue

        distance_km = round(
            haversine_km(latitude, longitude, float(lat), float(lon)), 2
        )
        if distance_km * 1000 > radius_meters:
            continue

        results.append(
            {
                "place_id": properties.get("place_id"),
                "name": properties.get("name") or "Unnamed place",
                "address": properties.get("formatted") or "",
                "latitude": float(lat),
                "longitude": float(lon),
                "categories": properties.get("categories") or [],
                "rating": None,
                "rating_source_scale": None,
                "price_level": None,
                "price_label": None,
                "distance_km": distance_km,
                "website": (
                    properties.get("website")
                    or ((properties.get("datasource") or {}).get("raw") or {}).get("website")
                ),
                "provider": "geoapify",
            }
        )

    results.sort(key=lambda item: float(item.get("distance_km") or 9999))
    return results


def weather_forecast(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Return live forecast only when the trip falls inside the useful forecast window."""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise RecommendationError("Trip dates are invalid.") from exc

    today = date.today()
    last_forecast_day = today + timedelta(days=14)

    if end < today or start > last_forecast_day:
        return {
            "available": False,
            "partial": False,
            "days": [],
            "reason": (
                "Live weather is only used when the trip is close enough "
                "for a reliable forecast."
            ),
        }

    forecast_start = max(start, today)
    forecast_end = min(end, last_forecast_day)
    query = urlencode(
        {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,precipitation_sum"
            ),
            "timezone": "auto",
            "start_date": forecast_start.isoformat(),
            "end_date": forecast_end.isoformat(),
        }
    )
    response = _json_request(f"{OPEN_METEO_FORECAST_URL}?{query}")
    daily = response.get("daily") or {}
    dates = daily.get("time") or []

    days = []
    for index, day_value in enumerate(dates):
        code = _list_value(daily.get("weather_code"), index)
        days.append(
            {
                "date": day_value,
                "weather_code": code,
                "condition": weather_condition(code),
                "outdoor_friendly": not is_rainy_weather(code),
                "temperature_max_c": _list_value(
                    daily.get("temperature_2m_max"), index
                ),
                "temperature_min_c": _list_value(
                    daily.get("temperature_2m_min"), index
                ),
                "precipitation_probability": _list_value(
                    daily.get("precipitation_probability_max"), index
                ),
                "precipitation_mm": _list_value(
                    daily.get("precipitation_sum"), index
                ),
            }
        )

    return {
        "available": bool(days),
        "partial": forecast_start > start or forecast_end < end,
        "timezone": response.get("timezone"),
        "days": days,
        "reason": None if days else "No forecast data was returned for these dates.",
    }


def weather_condition(code: int | float | None) -> str:
    if code is None:
        return "unknown"
    code = int(code)
    if code == 0:
        return "clear"
    if code in (1, 2):
        return "partly_cloudy"
    if code == 3:
        return "overcast"
    if code in (45, 48):
        return "fog"
    if code in RAINY_WEATHER_CODES:
        return "wet"
    return "mixed"


def is_rainy_weather(code: int | float | None) -> bool:
    return code is not None and int(code) in RAINY_WEATHER_CODES


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _list_value(values: Any, index: int) -> Any:
    if isinstance(values, list) and index < len(values):
        return values[index]
    return None
