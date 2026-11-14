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

MIN_RESTAURANTS_PER_DAY = 2
DAILY_FOOD_RADIUS_METERS = 5000


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
    food_limit = min(30, max(12, day_count * 4))

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

        anchor = _day_anchor(day_places, centre)
        day_food = _food_places_near_anchor(anchor, food_places)
        restaurants = _pick_food_stops(
            anchor,
            day_food,
            used_food,
            count=MIN_RESTAURANTS_PER_DAY,
        )
        if len(restaurants) < MIN_RESTAURANTS_PER_DAY:
            raise RecommendationError(
                f"Roamory could not find two verified food places close enough to the Day {offset + 1} route."
            )
        for restaurant in restaurants:
            used_food.add(_place_key(restaurant))

        items: list[dict[str, Any]] = []
        if day_places:
            items.append(_activity_from_place(day_places[0], "10:00", "activity", day_weather))
        if restaurants:
            items.append(_activity_from_place(restaurants[0], "13:00", "restaurant", None))
        if len(day_places) > 1:
            items.append(_activity_from_place(day_places[1], "15:00", "activity", day_weather))
        if len(restaurants) > 1:
            items.append(_activity_from_place(restaurants[1], "19:30", "restaurant", None))

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



def build_missing_restaurant_plan(
    trip: Any,
    days: list[dict[str, Any]],
    activities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return only the food stops needed to reach two restaurants on every trip day."""
    destination = resolve_destination(trip["destination"])
    centre = destination["selected"]

    global_food = search_nearby_places(
        centre["latitude"],
        centre["longitude"],
        categories="food",
        max_results=30,
    )

    used_food: set[str] = {
        str(activity.get("name") or "").strip().lower()
        for activity in activities
        if activity.get("type") == "restaurant" and activity.get("name")
    }
    additions: list[dict[str, Any]] = []

    for day in days:
        day_number = int(day["day_number"])
        day_activities = [
            activity
            for activity in activities
            if int(activity.get("day_number") or 0) == day_number
        ]
        existing_restaurants = [
            activity
            for activity in day_activities
            if activity.get("type") == "restaurant"
        ]
        needed = max(0, MIN_RESTAURANTS_PER_DAY - len(existing_restaurants))
        if not needed:
            continue

        sightseeing = [
            activity
            for activity in day_activities
            if activity.get("type") != "restaurant"
            and activity.get("latitude") is not None
            and activity.get("longitude") is not None
        ]
        anchor = _day_anchor(sightseeing, centre)
        day_food = _food_places_near_anchor(anchor, global_food)

        blocked_names = {
            str(activity.get("name") or "").strip().lower()
            for activity in existing_restaurants
            if activity.get("name")
        }
        restaurants = _pick_food_stops(
            anchor,
            day_food,
            used_food,
            count=needed,
            blocked_names=blocked_names,
        )

        times = _missing_food_times(existing_restaurants, needed)
        items = []
        for index, restaurant in enumerate(restaurants):
            used_food.add(str(restaurant.get("name") or "").strip().lower())
            items.append(
                _activity_from_place(
                    restaurant,
                    times[min(index, len(times) - 1)],
                    "restaurant",
                    None,
                )
            )

        if items:
            additions.append(
                {
                    "day_number": day_number,
                    "date": day.get("date"),
                    "items": items,
                }
            )

    return additions


def _missing_food_times(
    existing_restaurants: list[dict[str, Any]],
    needed: int,
) -> list[str]:
    existing_times = [
        str(activity.get("start_time") or "")
        for activity in existing_restaurants
    ]
    preferred = ["13:00", "19:30"]
    available = [
        time
        for time in preferred
        if not any(
            existing.startswith(time[:2])
            for existing in existing_times
            if existing
        )
    ]
    while len(available) < needed:
        available.append("18:30")
    return available[:needed]


def _day_anchor(
    places: list[dict[str, Any]],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    coordinates = [
        (float(place["latitude"]), float(place["longitude"]))
        for place in places
        if place.get("latitude") is not None and place.get("longitude") is not None
    ]
    if not coordinates:
        return fallback

    return {
        "latitude": sum(lat for lat, _ in coordinates) / len(coordinates),
        "longitude": sum(lon for _, lon in coordinates) / len(coordinates),
    }


def _food_places_near_anchor(
    anchor: dict[str, Any],
    fallback_food: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    anchor_lat = anchor.get("latitude")
    anchor_lon = anchor.get("longitude")
    if anchor_lat is None or anchor_lon is None:
        return fallback_food

    try:
        local_food = search_nearby_places(
            float(anchor_lat),
            float(anchor_lon),
            categories="food",
            radius_meters=DAILY_FOOD_RADIUS_METERS,
            max_results=16,
        )
    except RecommendationError:
        local_food = []

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for place in [*local_food, *fallback_food]:
        key = _place_key(place).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(place)

    return sorted(
        merged,
        key=lambda place: haversine_km(
            float(anchor_lat),
            float(anchor_lon),
            float(place["latitude"]),
            float(place["longitude"]),
        ),
    )


def _pick_food_stops(
    anchor: dict[str, Any],
    food_places: list[dict[str, Any]],
    used_food: set[str],
    *,
    count: int,
    blocked_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    blocked_names = {name.lower() for name in (blocked_names or set())}
    if count <= 0:
        return []

    def name_key(place: dict[str, Any]) -> str:
        return str(place.get("name") or "").strip().lower()

    available = [
        place
        for place in food_places
        if name_key(place) and name_key(place) not in blocked_names
    ]
    preferred = [
        place
        for place in available
        if _place_key(place) not in used_food and name_key(place) not in used_food
    ]
    fallback = [
        place
        for place in available
        if place not in preferred
    ]

    selected: list[dict[str, Any]] = []
    selected_names: set[str] = set()
    for place in [*preferred, *fallback]:
        key = name_key(place)
        if key in selected_names:
            continue
        selected.append(place)
        selected_names.add(key)
        if len(selected) >= count:
            break
    return selected

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
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "estimated_cost": 0,
        "notes": " · ".join(details),
    }


def _place_key(place: dict[str, Any]) -> str:
    return str(place.get("place_id") or place.get("name") or "")
