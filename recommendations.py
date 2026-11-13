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
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
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
    """Search nearby places with a keyless source first and paid-key providers only as fallback."""
    radius = max(500, min(int(radius_meters), MAX_RADIUS_METERS))
    result_count = max(1, min(int(max_results), 30))

    try:
        results = _search_overpass_places(
            float(latitude),
            float(longitude),
            categories=categories,
            radius_meters=radius,
            max_results=result_count,
        )
        if results:
            return results
    except RecommendationError:
        pass

    if _geoapify_api_key():
        try:
            results = _search_geoapify_places(
                float(latitude),
                float(longitude),
                categories=categories,
                radius_meters=radius,
                max_results=result_count,
            )
            if results:
                return results
        except RecommendationError:
            pass

    if _foursquare_api_key():
        try:
            results = _search_foursquare(
                float(latitude),
                float(longitude),
                categories=categories,
                radius_meters=radius,
                max_results=result_count,
            )
            if results:
                return results
        except RecommendationError:
            pass

    raise RecommendationError(
        "Roamory could not load nearby places right now. Please try again."
    )


def _search_overpass_places(
    latitude: float,
    longitude: float,
    *,
    categories: str,
    radius_meters: int,
    max_results: int,
) -> list[dict[str, Any]]:
    if categories == "food":
        selectors = f"""
          nwr(around:{radius_meters},{latitude:.7f},{longitude:.7f})["amenity"~"^(restaurant|cafe|fast_food)$"];
        """
    else:
        selectors = f"""
          nwr(around:{radius_meters},{latitude:.7f},{longitude:.7f})["tourism"~"^(attraction|viewpoint|museum|gallery|zoo|theme_park)$"];
          nwr(around:{radius_meters},{latitude:.7f},{longitude:.7f})["historic"];
          nwr(around:{radius_meters},{latitude:.7f},{longitude:.7f})["leisure"~"^(park|garden)$"];
          nwr(around:{radius_meters},{latitude:.7f},{longitude:.7f})["natural"~"^(peak|waterfall|beach|spring)$"];
        """

    query = f"""
        [out:json][timeout:18];
        (
          {selectors}
        );
        out center 120;
    """

    response = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            response = _json_request(
                endpoint,
                method="POST",
                form_payload={"data": query},
                timeout=22,
            )
            if isinstance(response, dict):
                break
        except RecommendationError:
            response = None

    if not isinstance(response, dict):
        raise RecommendationError("OpenStreetMap place lookup is temporarily unavailable.")

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for element in response.get("elements") or []:
        tags = element.get("tags") or {}
        name = tags.get("name:en") or tags.get("name")
        if not name:
            continue

        lat = element.get("lat")
        lon = element.get("lon")
        if lat is None or lon is None:
            center = element.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")
        if lat is None or lon is None:
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

        address = _osm_address(tags)
        category_names = _osm_categories(tags)
        results.append(
            {
                "place_id": f"osm-{element.get('type')}-{element.get('id')}",
                "name": str(name).strip(),
                "address": address,
                "latitude": float(lat),
                "longitude": float(lon),
                "categories": category_names,
                "rating": None,
                "rating_source_scale": None,
                "price_level": None,
                "price_label": None,
                "distance_km": distance_km,
                "website": tags.get("website") or tags.get("contact:website"),
                "provider": "openstreetmap",
            }
        )

    results.sort(key=lambda item: float(item.get("distance_km") or 9999))
    return results[:max_results]


def _osm_address(tags: dict[str, Any]) -> str:
    if tags.get("addr:full"):
        return str(tags["addr:full"]).strip()

    street = " ".join(
        part
        for part in (
            str(tags.get("addr:housenumber") or "").strip(),
            str(tags.get("addr:street") or "").strip(),
        )
        if part
    )
    pieces = [
        street,
        tags.get("addr:place"),
        tags.get("addr:suburb"),
        tags.get("addr:city"),
        tags.get("addr:state"),
        tags.get("addr:postcode"),
    ]
    address = ", ".join(str(value).strip() for value in pieces if value and str(value).strip())
    return address or str(tags.get("is_in") or "").strip()


def _osm_categories(tags: dict[str, Any]) -> list[str]:
    categories = []
    for key in ("tourism", "historic", "leisure", "natural", "amenity"):
        value = tags.get(key)
        if value:
            categories.append(f"{key}:{value}")
    return categories


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
