from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GOOGLE_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_RADIUS_METERS = 15000
MAX_RADIUS_METERS = 50000

ATTRACTION_TYPES = (
    "tourist_attraction",
    "museum",
    "historical_landmark",
    "park",
    "national_park",
    "art_gallery",
    "zoo",
    "aquarium",
    "amusement_park",
    "hiking_area",
    "observation_deck",
)

FOOD_TYPES = (
    "restaurant",
    "cafe",
    "bakery",
)

PRICE_LEVELS = {
    "free": "PRICE_LEVEL_FREE",
    "budget": "PRICE_LEVEL_INEXPENSIVE",
    "moderate": "PRICE_LEVEL_MODERATE",
    "premium": "PRICE_LEVEL_EXPENSIVE",
    "luxury": "PRICE_LEVEL_VERY_EXPENSIVE",
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


def google_places_configured() -> bool:
    return bool(_google_api_key())


def _google_api_key() -> str:
    return (
        os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
        or os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    )


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 8,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json"}
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
            f"External place/weather service returned HTTP {exc.code}."
            + (f" {detail[:240]}" if detail else "")
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RecommendationError("External place/weather service is temporarily unavailable.") from exc


def resolve_destination(destination: str) -> dict[str, Any]:
    """Resolve a user-entered destination to a concrete Google place and coordinates."""
    query = (destination or "").strip()
    if not query:
        raise RecommendationError("Destination is required.")

    api_key = _google_api_key()
    if not api_key:
        raise RecommendationError("Google Places is not configured.")

    payload = {
        "textQuery": query,
        "maxResultCount": 5,
    }
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.location,places.types,places.primaryType"
        ),
    }
    response = _json_request(
        GOOGLE_TEXT_SEARCH_URL,
        method="POST",
        payload=payload,
        headers=headers,
    )
    places = response.get("places") or []
    if not places:
        raise RecommendationError(
            "We could not identify that destination. Check the location name and try again."
        )

    candidates = [_normalise_place(place) for place in places if place.get("location")]
    if not candidates:
        raise RecommendationError(
            "We found the destination name but could not verify its location."
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
    """Fetch real nearby places and apply strict local rating/price/distance filtering."""
    api_key = _google_api_key()
    if not api_key:
        raise RecommendationError("Google Places is not configured.")

    radius = max(500, min(int(radius_meters), MAX_RADIUS_METERS))
    result_count = max(1, min(int(max_results), 20))
    included_types = FOOD_TYPES if categories == "food" else ATTRACTION_TYPES

    payload = {
        "includedTypes": list(included_types),
        "maxResultCount": result_count,
        "rankPreference": "POPULARITY",
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                },
                "radius": float(radius),
            }
        },
    }
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,places.location,"
            "places.primaryType,places.types,places.rating,places.userRatingCount,"
            "places.priceLevel,places.googleMapsUri,places.businessStatus"
        ),
    }
    response = _json_request(
        GOOGLE_NEARBY_SEARCH_URL,
        method="POST",
        payload=payload,
        headers=headers,
    )

    allowed_prices = _normalise_price_levels(price_levels)
    results: list[dict[str, Any]] = []
    for raw in response.get("places") or []:
        if raw.get("businessStatus") not in (None, "OPERATIONAL"):
            continue

        place = _normalise_place(raw)
        place["distance_km"] = round(
            haversine_km(
                float(latitude),
                float(longitude),
                place["latitude"],
                place["longitude"],
            ),
            2,
        )

        if place["distance_km"] * 1000 > radius:
            continue

        rating = float(place.get("rating") or 0)
        if rating < float(min_rating or 0):
            continue

        if allowed_prices and categories == "food":
            if place.get("price_level") not in allowed_prices:
                continue

        results.append(place)

    results.sort(
        key=lambda item: (
            -(float(item.get("rating") or 0)),
            -(int(item.get("user_rating_count") or 0)),
            float(item.get("distance_km") or 9999),
        )
    )
    return results


def weather_forecast(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Return real forecast data only when the trip overlaps Open-Meteo's forecast horizon."""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise RecommendationError("Trip dates are invalid.") from exc

    today = date.today()
    last_forecast_day = today + timedelta(days=15)

    if end < today or start > last_forecast_day:
        return {
            "available": False,
            "partial": False,
            "days": [],
            "reason": "Forecast is only used when the trip is close enough for reliable live weather data.",
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
        precipitation_probability = _list_value(
            daily.get("precipitation_probability_max"), index
        )
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
                "precipitation_probability": precipitation_probability,
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


def _normalise_price_levels(
    values: list[str] | tuple[str, ...] | None,
) -> set[str]:
    if not values:
        return set()

    normalised = set()
    for value in values:
        token = str(value).strip()
        if not token:
            continue
        mapped = PRICE_LEVELS.get(token.lower(), token.upper())
        normalised.add(mapped)
    return normalised


def _normalise_place(place: dict[str, Any]) -> dict[str, Any]:
    location = place.get("location") or {}
    display_name = place.get("displayName") or {}
    return {
        "place_id": place.get("id"),
        "name": display_name.get("text") or place.get("name") or "Unnamed place",
        "address": place.get("formattedAddress") or "",
        "latitude": float(location.get("latitude")),
        "longitude": float(location.get("longitude")),
        "primary_type": place.get("primaryType"),
        "types": place.get("types") or [],
        "rating": place.get("rating"),
        "user_rating_count": place.get("userRatingCount"),
        "price_level": place.get("priceLevel"),
        "maps_url": place.get("googleMapsUri"),
    }


def _list_value(values: Any, index: int) -> Any:
    if isinstance(values, list) and index < len(values):
        return values[index]
    return None
