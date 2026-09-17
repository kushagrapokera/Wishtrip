"""Geographic day-grouping: every normal day stays inside a single zone.

North<->South Goa is a real 1.5-2 hr crossing, so a day never mixes zones;
day-trip venues (Dudhsagar Falls) each occupy a whole middle day on their own.
"""

from app import config
from app.models import TripRequest
from app.planner.travel_time import (
    TravelMinutesFn,
    estimate_travel_minutes,
)

# Cluster over-assigns on purpose (budget.py trims to the pace afterwards).
MAX_PLACES_PER_DAY_CLUSTER = 12


def cluster_places_into_days(
    ranked_places: list[dict],
    trip_request: TripRequest,
    travel_minutes_fn: TravelMinutesFn = estimate_travel_minutes,
) -> list[dict]:
    """Group ranked candidates into ``nights + 1`` single-zone day clusters.

    Returns a list of ``{"zone": str, "places": [...], "is_day_trip": bool}``
    dicts in day order. Each input place appears at most once.
    """
    del travel_minutes_fn  # reserved for Valhalla-aware clustering (Phase 6)
    total_days = trip_request.nights + 1

    day_trip_places = [
        ranked_place
        for ranked_place in ranked_places
        if ranked_place.get("category") == config.DAY_TRIP_CATEGORY
        # A full-day excursion must match an interest; rating alone never
        # justifies burning a whole day (score.py records the interest part).
        and ranked_place.get("interest_score", 0.0) > 0.0
    ]
    sightseeing_places = [p for p in ranked_places if p.get("category") != config.DAY_TRIP_CATEGORY]

    day_trip_count = min(len(day_trip_places), total_days)
    if sightseeing_places and total_days > 1 and day_trip_count == total_days:
        day_trip_count = total_days - 1
    # Full-day excursions are rare highlights, not daily commutes inland.
    day_trip_count = min(day_trip_count, max(1, total_days // 3))
    chosen_day_trips = day_trip_places[:day_trip_count]
    remaining_days = total_days - day_trip_count

    day_clusters: list[dict] = []
    if remaining_days > 0:
        zone_to_places = group_places_by_zone(sightseeing_places)
        day_zone_names = assign_zone_to_each_day(list(zone_to_places), remaining_days, zone_to_places)
        day_clusters = deal_places_round_robin(zone_to_places, day_zone_names)

    full_schedule: list[dict] = []
    if day_clusters:
        full_schedule.append(day_clusters[0])
        for day_trip_place in chosen_day_trips:
            full_schedule.append(
                {
                    "zone": day_trip_place["zone"],
                    "places": [day_trip_place],
                    "is_day_trip": True,
                }
            )
        full_schedule.extend(day_clusters[1:])
    else:
        for day_trip_place in chosen_day_trips:
            full_schedule.append(
                {
                    "zone": day_trip_place["zone"],
                    "places": [day_trip_place],
                    "is_day_trip": True,
                }
            )
    return full_schedule


def group_places_by_zone(places: list[dict]) -> dict[str, list[dict]]:
    """Bucket places by zone, most-stocked zone first (input is score-ordered)."""
    zone_to_places: dict[str, list[dict]] = {}
    for place in places:
        zone_to_places.setdefault(place["zone"], []).append(place)
    return {
        zone: interleave_categories_for_variety(zone_places)
        for zone, zone_places in sorted(
            zone_to_places.items(), key=lambda item: len(item[1]), reverse=True
        )
    }


def interleave_categories_for_variety(places: list[dict]) -> list[dict]:
    """Cycle through categories so a day mixes (e.g.) food, beach and heritage.

    Score order is kept within each category and categories lead with their
    best stop first; single-category pools come back unchanged, so pace-budget
    behaviour is unaffected.
    """
    by_category: dict[str, list[dict]] = {}
    for place in places:
        by_category.setdefault(place.get("category", ""), []).append(place)
    categories_by_best_score = sorted(
        by_category,
        key=lambda category: by_category[category][0].get("planner_score", 0.0),
        reverse=True,
    )
    interleaved: list[dict] = []
    for position in range(max(len(stops) for stops in by_category.values())):
        for category in categories_by_best_score:
            if position < len(by_category[category]):
                interleaved.append(by_category[category][position])
    return interleaved


def assign_zone_to_each_day(
    zones_by_stock: list[str],
    day_count: int,
    zone_to_places: dict[str, list[dict]],
) -> list[str]:
    """Cycle zones across days, then pin airport-nearest zones to edge days.

    Arrival/departure days stay within easy reach of Goa airport, so the first
    and last day get the airport-nearest zones among the assigned ones.
    """
    if not zones_by_stock or day_count <= 0:
        return []
    day_zone_names = [zones_by_stock[i % len(zones_by_stock)] for i in range(day_count)]
    if day_count >= 2:
        zone_distance = {
            zone: calculate_zone_airport_distance(zone_places)
            for zone, zone_places in zone_to_places.items()
        }
        day_zone_names = pin_nearest_zone_to_edge_days(day_zone_names, zone_distance)
    return day_zone_names


def pin_nearest_zone_to_edge_days(
    day_zone_names: list[str], zone_distance: dict[str, float]
) -> list[str]:
    """Swap the airport-nearest assigned zone into day 1, next-nearest into last day."""
    pinned = list(day_zone_names)
    ranked = sorted(set(pinned), key=lambda zone: zone_distance.get(zone, float("inf")))
    if ranked:
        first_zone = ranked[0]
        first_index = pinned.index(first_zone)
        pinned[0], pinned[first_index] = pinned[first_index], pinned[0]
    if len(pinned) >= 2 and len(ranked) >= 2:
        last_zone = ranked[1]
        last_index = len(pinned) - 1 - pinned[::-1].index(last_zone)
        if last_index != 0:
            pinned[-1], pinned[last_index] = pinned[last_index], pinned[-1]
    return pinned


def calculate_zone_airport_distance(zone_places: list[dict]) -> float:
    """Mean haversine distance of the zone's candidates from Goa airport."""
    from app.planner.travel_time import calculate_haversine_distance_km

    if not zone_places:
        return float("inf")
    total = sum(
        calculate_haversine_distance_km(
            place["lat"], place["lon"],
            config.GOA_AIRPORT_LAT, config.GOA_AIRPORT_LON,
        )
        for place in zone_places
    )
    return total / len(zone_places)


def deal_places_round_robin(
    zone_to_places: dict[str, list[dict]], day_zone_names: list[str]
) -> list[dict]:
    """Deal each zone's candidates across its days one at a time (score order kept)."""
    day_places: list[list[dict]] = [[] for _ in day_zone_names]
    zone_day_indexes: dict[str, list[int]] = {}
    for day_index, zone in enumerate(day_zone_names):
        zone_day_indexes.setdefault(zone, []).append(day_index)

    for zone, day_indexes in zone_day_indexes.items():
        deal_cursor = 0
        for place in zone_to_places.get(zone, []):
            target_day = day_indexes[deal_cursor % len(day_indexes)]
            if len(day_places[target_day]) >= MAX_PLACES_PER_DAY_CLUSTER:
                if all(len(day_places[i]) >= MAX_PLACES_PER_DAY_CLUSTER for i in day_indexes):
                    break
                deal_cursor += 1
                continue
            day_places[target_day].append(place)
            deal_cursor += 1

    return [
        {"zone": zone, "places": places, "is_day_trip": False}
        for zone, places in zip(day_zone_names, day_places)
    ]
