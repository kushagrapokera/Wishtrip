"""Meal anchoring: lunch ~13:00 and dinner ~19:30 at diet-compatible venues."""

from app import config
from app.models import TripRequest
from app.planner.travel_time import (
    TravelMinutesFn,
    calculate_haversine_distance_km,
    estimate_travel_minutes,
)


def select_meal_venue(
    day_places: list[dict],
    meal_candidates: list[dict],
    used_place_ids: set[str],
    travel_minutes_fn: TravelMinutesFn = estimate_travel_minutes,
) -> dict | None:
    """Best unused food venue near the day's midpoint (already diet-filtered upstream)."""
    del travel_minutes_fn  # proximity is haversine; routing plugs in at schedule time
    available = [
        place
        for place in meal_candidates
        if place["id"] not in used_place_ids
    ]
    if not available or not day_places:
        return None
    mid_lat = sum(place["lat"] for place in day_places) / len(day_places)
    mid_lon = sum(place["lon"] for place in day_places) / len(day_places)
    return min(
        available,
        key=lambda place: calculate_haversine_distance_km(
            mid_lat, mid_lon, place["lat"], place["lon"]
        ),
    )


def meal_candidates_for_zone(ranked_places: list[dict], zone: str) -> list[dict]:
    """Food venues in the day's zone, score order (ranked_places is pre-sorted)."""
    return [
        place
        for place in ranked_places
        if place.get("category") == "food" and place.get("zone") == zone
    ]


def build_generic_meal_name(meal: str, zone: str) -> str:
    """Fallback label when no diet-compatible venue is left in the zone.

    The meal word is baked in, so callers must use the label as-is (no prefix).
    """
    zone_label = config.ZONE_LABELS.get(zone, zone)
    return f"{meal.capitalize()} — local eateries in {zone_label} (unverified)"


def should_serve_dinner(is_departure_day: bool) -> bool:
    """Dinner is anchored every night except the departure day."""
    return not is_departure_day


def describe_meal_suitability(trip_request: TripRequest) -> str:
    if trip_request.dietary_preference != "none":
        return f"{trip_request.dietary_preference}-friendly"
    return "local"
