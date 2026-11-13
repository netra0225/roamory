from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from recommendations import (
    RecommendationError,
    haversine_km,
    resolve_destination,
    search_nearby_places,
    weather_forecast,
)


INTEREST_KEYWORDS = {
    "nature": (
        "park", "garden", "lake", "waterfall", "mountain", "peak", "viewpoint",
        "trail", "forest", "beach", "botanical", "nature",
    ),
    "culture": (
        "museum", "palace", "fort", "temple", "church", "heritage", "historic",
        "monument", "gallery", "art", "cultural",
    ),
}

INDOOR_KEYWORDS = (
    "museum", "gallery", "palace", "mall", "aquarium", "indoor", "cafe",
)


def build_trip_plan(
    trip: Any,
    *,
    interest: str = "mixed",
) -> dict[str, Any]:
    destination = resolve_destination(trip["destination"])
    centre = destination["selected"]
    latitude = centre["latitude"]
    longitude = centre["longitude"]

    day_count = _trip_day_count(trip["start_date"], trip["end_date"])
    attraction_limit = min(30, max(10, day_count * 4))
    food_limit = min(30, max(8, day_count * 3))

    attractions = search_nearby_places(
        latitude,
        longitude,
        categories="attractions",
        max_results=attraction_limit,
    )

    food_places = search_nearby_places(
        latitude,
        longitude,
        categories="food",
        max_results=food_limit,
    )

    if not attractions:
        raise RecommendationError(
            f"We could not find enough verified places around {trip['destination']} to build a trip."
        )

    attractions = _rank_for_interest(attractions, interest)

    forecast = weather_forecast(
        latitude,
        longitude,
        trip["start_date"],
        trip["end_date"],
    )
    weather_by_date = {
        item["date"]: item
        for item in forecast.get("days", [])
        if item.get("date")
    }

    start = datetime.strptime(trip["start_date"], "%Y-%m-%d").date()
    used_attractions: set[str] = set()
    used_food: set[str] = set()
    plan: list[dict[str, Any]] = []

    for offset in range(day_count):
        current_date = start + timedelta(days=offset)
        day_weather = weather_by_date.get(current_date.isoformat())
        candidates = [
            place
            for place in attractions
            if _place_key(place) not in used_attractions
        ]

        if day_weather and not day_weather.get("outdoor_friendly", True):
            candidates.sort(
                key=lambda place: (
                    0 if _looks_indoor(place) else 1,
                    -(float(place.get("rating") or 0)),
                    float(place.get("distance_km") or 9999),
                )
            )

        day_places = candidates[:2]
        for place in day_places:
            used_attractions.add(_place_key(place))

        anchor = day_places[-1] if day_places else centre
        restaurant = _nearest_unused_food(anchor, food_places, used_food)
        if restaurant:
            used_food.add(_place_key(restaurant))

        items: list[dict[str, Any]] = []
        if day_places:
            items.append(_activity_from_place(day_places[0], "10:00", "activity", day_weather))
        if len(day_places) > 1:
            items.append(_activity_from_place(day_places[1], "15:00", "activity", day_weather))
        if restaurant:
            items.append(_activity_from_place(restaurant, "19:30", "restaurant", None))

        plan.append(
            {
                "day_number": offset + 1,
                "date": current_date.isoformat(),
                "weather": day_weather,
                "items": items,
            }
        )

    return {
        "destination": centre,
        "alternatives": destination.get("alternatives") or [],
        "weather": forecast,
        "days": plan,
        "provider_note": (
            "Recommendations use verified place data. Weather is only applied when a live forecast is available."
        ),
    }


def _trip_day_count(start_date: str, end_date: str) -> int:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    return max(1, (end - start).days + 1)


def _rank_for_interest(
    places: list[dict[str, Any]],
    interest: str,
) -> list[dict[str, Any]]:
    interest = (interest or "mixed").lower()
    keywords = INTEREST_KEYWORDS.get(interest)
    if not keywords:
        return places

    def score(place: dict[str, Any]):
        haystack = " ".join(
            [
                place.get("name") or "",
                " ".join(str(value) for value in (place.get("categories") or [])),
            ]
        ).lower()
        interest_hit = any(keyword in haystack for keyword in keywords)
        return (
            0 if interest_hit else 1,
            float(place.get("distance_km") or 9999),
        )

    return sorted(places, key=score)


def _looks_indoor(place: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            place.get("name") or "",
            " ".join(str(value) for value in (place.get("categories") or [])),
        ]
    ).lower()
    return any(keyword in haystack for keyword in INDOOR_KEYWORDS)


def _nearest_unused_food(
    anchor: dict[str, Any],
    food_places: list[dict[str, Any]],
    used_food: set[str],
) -> dict[str, Any] | None:
    available = [place for place in food_places if _place_key(place) not in used_food]
    if not available:
        return None

    anchor_lat = anchor.get("latitude")
    anchor_lon = anchor.get("longitude")
    if anchor_lat is None or anchor_lon is None:
        return available[0]

    return min(
        available,
        key=lambda place: haversine_km(
            float(anchor_lat),
            float(anchor_lon),
            float(place["latitude"]),
            float(place["longitude"]),
        ),
    )


def _activity_from_place(
    place: dict[str, Any],
    start_time: str,
    activity_type: str,
    weather: dict[str, Any] | None,
) -> dict[str, Any]:
    details: list[str] = ["Suggested by Roamory"]
    if place.get("rating") is not None:
        details.append(f"{place['rating']}★")
    if place.get("price_label"):
        details.append(str(place["price_label"]))
    if place.get("distance_km") is not None:
        details.append(f"{place['distance_km']} km from destination centre")
    if weather and weather.get("condition") == "wet":
        details.append("weather-aware day")

    return {
        "name": place["name"],
        "type": activity_type,
        "start_time": start_time,
        "location": place.get("address") or "",
        "estimated_cost": 0,
        "notes": " · ".join(details),
    }


def _place_key(place: dict[str, Any]) -> str:
    return str(place.get("place_id") or place.get("name") or "")
