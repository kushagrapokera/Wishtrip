"""Pace/time budgeting: trim an ordered day to what the traveller can enjoy.

Overflow always drops the lowest-scored stop first — the day keeps its
geographic order, just with fewer pins. Day-trip days bypass the budget: one
venue already fills the day.
"""

from app import config
from app.models import TripRequest
from app.planner.travel_time import (
    TravelMinutesFn,
    estimate_travel_minutes,
)


def apply_pace_budget_to_day(
    ordered_places: list[dict],
    trip_request: TripRequest,
    is_edge_day: bool,
    start_lat: float,
    start_lon: float,
    travel_minutes_fn: TravelMinutesFn = estimate_travel_minutes,
) -> list[dict]:
    """Keep the affordable prefix of stops: pace count first, then active hours."""
    if not ordered_places:
        return []
    max_stops, max_active_hours = lookup_day_budget(trip_request, is_edge_day)

    affordable = list(ordered_places)
    while len(affordable) > max_stops:
        drop_lowest_scored_stop(affordable)
    while (
        affordable
        and calculate_day_active_hours(affordable, start_lat, start_lon, travel_minutes_fn)
        > max_active_hours
    ):
        if len(affordable) == 1:
            break
        drop_lowest_scored_stop(affordable)
    return affordable


def lookup_day_budget(trip_request: TripRequest, is_edge_day: bool) -> tuple[int, float]:
    """(max stops, max active hours); arrival/departure days are lighter."""
    pace_budget = config.PACE_BUDGETS[trip_request.pace]
    max_stops = pace_budget["max_stops_per_day"]
    max_hours = pace_budget["max_active_hours"]
    if is_edge_day:
        max_stops = max(1, max_stops - config.EDGE_DAY_STOP_REDUCTION)
        max_hours = max_hours * config.EDGE_DAY_HOURS_FRACTION
    return max_stops, max_hours


def is_over_stop_count(places: list[dict], max_stops: int) -> bool:
    return len(places) > max_stops


def drop_lowest_scored_stop(places: list[dict]) -> None:
    """Remove the lowest-scored stop in place (ties: later in the day first).

    Drops come from the most-represented category first, so trimming a mixed
    day preserves its variety instead of collapsing it to one category.
    Single-category days are unaffected (every stop is droppable).
    """
    places.pop(choose_drop_index(places))


def choose_drop_index(places: list[dict]) -> int:
    """Index to drop: lowest score within an over-represented category."""
    category_tally: dict[str, int] = {}
    for place in places:
        category_tally[place.get("category", "")] = (
            category_tally.get(place.get("category", ""), 0) + 1
        )
    droppable = [
        index
        for index, place in enumerate(places)
        if category_tally[place.get("category", "")] > 1
    ] or list(range(len(places)))
    return min(
        droppable,
        key=lambda index: (places[index].get("planner_score", 0.0), -index),
    )


def calculate_day_active_hours(
    ordered_places: list[dict],
    start_lat: float,
    start_lon: float,
    travel_minutes_fn: TravelMinutesFn,
) -> float:
    """Visit durations plus travel legs, in hours (meals are anchored separately)."""
    if not ordered_places:
        return 0.0
    visit_minutes = sum(place.get("visit_duration_minutes", 60) for place in ordered_places)
    travel_minutes = 0
    current_lat, current_lon = start_lat, start_lon
    for place in ordered_places:
        travel_minutes += travel_minutes_fn(
            current_lat, current_lon, place["lat"], place["lon"]
        )
        current_lat, current_lon = place["lat"], place["lon"]
    return (visit_minutes + travel_minutes) / 60.0
