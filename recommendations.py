from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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

FOURSQUARE_PRICE_LEVELS = {
    "budget": 1,
    "moderate": 2,
    "premium": 3,
    "luxury": 4,
}

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
    """Expose configuration state without leaking any API keys."""
    return {
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
    headers: dict[str, str] | None = None,
    timeout: int = 8,
) -> dict[str, Any]:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "Roamory/1.0 travel-planner",
    }
    if headers:
        request_headers.update(headers)

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            pass
        raise RecommendationError(
            f"External recommendation service returned HTTP {exc.code}."
            + (f" {detail[:240]}" if detail else "")
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RecommendationError(
            "External recommendation service is temporarily unavailable."
        ) from exc


def resolve_destination(destination: str) -> dict[str, Any]:
    """Resolve a destination into exact coordinates using Geoapify's free geocoder."""
    query = (destination or "").strip()
    if not query:
        raise RecommendationError("Destination is required.")

    api_key = _geoapify_api_key()
    if not api_key:
        raise RecommendationError(
            "Destination lookup is not configured yet. Add GEOAPIFY_API_KEY."
        )

    params = urlencode(
        {
            "text": query,
            "format": "json",
            "limit": 5,
            "apiKey": api_key,
        }
    )
    response = _json_request(f"{GEOAPIFY_GEOCODE_URL}?{params}")
    raw_results = response.get("results") or []

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
        raise RecommendationError(
            "We could not identify that destination. Check the location name and try again."
        )

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
    min_rating: float = 0.0,
    price_levels: list[str] | tuple[str, ...] | None = None,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """
    Search real nearby places.

    Foursquare is preferred because its free Pro tier includes rating and price
    metadata. Geoapify is the zero-cost fallback when Foursquare is unavailable;
    fallback results intentionally leave rating/price blank rather than inventing
    values.
    """
    radius = max(500, min(int(radius_meters), MAX_RADIUS_METERS))
    result_count = max(1, min(int(max_results), 30))

    if _foursquare_api_key():
        try:
            return _search_foursquare(
                float(latitude),
                float(longitude),
                categories=categories,
                radius_meters=radius,
                min_rating=min_rating,
                price_levels=price_levels,
                max_results=result_count,
            )
        except RecommendationError:
            if not _geoapify_api_key():
                raise

    if _geoapify_api_key():
        return _search_geoapify_places(
            float(latitude),
            float(longitude),
            categories=categories,
            radius_meters=radius,
            max_results=result_count,
        )

    raise RecommendationError(
        "Place recommendations are not configured yet. "
        "Add FOURSQUARE_API_KEY and GEOAPIFY_API_KEY."
    )


def _search_foursquare(
    latitude: float,
    longitude: float,
    *,
    categories: str,
    radius_meters: int,
    min_rating: float,
    price_levels: list[str] | tuple[str, ...] | None,
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

    price_numbers = _normalise_foursquare_prices(price_levels)
    if categories == "food" and price_numbers:
        params["min_price"] = min(price_numbers)
        params["max_price"] = max(price_numbers)

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

        rating_10 = raw.get("rating")
        rating_5 = round(float(rating_10) / 2, 1) if rating_10 is not None else None
        if min_rating and (rating_5 is None or rating_5 < float(min_rating)):
            continue

        price = raw.get("price")
        if (
            categories == "food"
            and price_numbers
            and price is not None
            and int(price) not in price_numbers
        ):
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
                "rating": rating_5,
                "rating_source_scale": "5",
                "price_level": int(price) if price is not None else None,
                "price_label": _price_label(price),
                "distance_km": distance_km,
                "website": raw.get("website"),
                "provider": "foursquare",
            }
        )

    results.sort(
        key=lambda item: (
            -(float(item["rating"]) if item.get("rating") is not None else -1),
            float(item.get("distance_km") or 9999),
        )
    )
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


def _normalise_foursquare_prices(
    values: list[str] | tuple[str, ...] | None,
) -> set[int]:
    if not values:
        return set()
    result: set[int] = set()
    for value in values:
        token = str(value).strip().lower()
        if not token:
            continue
        if token.isdigit() and 1 <= int(token) <= 4:
            result.add(int(token))
        elif token in FOURSQUARE_PRICE_LEVELS:
            result.add(FOURSQUARE_PRICE_LEVELS[token])
    return result


def _price_label(value: Any) -> str | None:
    if value is None:
        return None
    try:
        price = int(value)
    except (TypeError, ValueError):
        return None
    return {
        1: "₹",
        2: "₹₹",
        3: "₹₹₹",
        4: "₹₹₹₹",
    }.get(price)


def _list_value(values: Any, index: int) -> Any:
    if isinstance(values, list) and index < len(values):
        return values[index]
    return None
