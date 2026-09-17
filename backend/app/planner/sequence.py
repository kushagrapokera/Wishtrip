"""Within-day ordering: nearest-neighbour construction + 2-opt improvement.

The route is an open tour — it starts at the day's entry point and ends at the
last stop (no return leg). Travel times flow through the pluggable estimator
so tests use haversine while production can later use Valhalla matrices.
"""

from app.planner.travel_time import (
    TravelMinutesFn,
    estimate_travel_minutes,
)


def build_day_sequence(
    places: list[dict],
    start_lat: float,
    start_lon: float,
    travel_minutes_fn: TravelMinutesFn = estimate_travel_minutes,
) -> list[dict]:
    """Order the day's stops from the start point, then 2-opt the total."""
    if len(places) <= 2:
        return list(places)
    greedy_order = order_by_nearest_neighbour(places, start_lat, start_lon, travel_minutes_fn)
    return improve_sequence_with_two_opt(greedy_order, start_lat, start_lon, travel_minutes_fn)


def order_by_nearest_neighbour(
    places: list[dict],
    start_lat: float,
    start_lon: float,
    travel_minutes_fn: TravelMinutesFn,
) -> list[dict]:
    """Repeatedly visit the closest unvisited stop to the current position."""
    unvisited = list(places)
    ordered: list[dict] = []
    current_lat, current_lon = start_lat, start_lon
    while unvisited:
        nearest = min(
            unvisited,
            key=lambda place: travel_minutes_fn(
                current_lat, current_lon, place["lat"], place["lon"]
            ),
        )
        ordered.append(nearest)
        unvisited.remove(nearest)
        current_lat, current_lon = nearest["lat"], nearest["lon"]
    return ordered


def improve_sequence_with_two_opt(
    ordered_places: list[dict],
    start_lat: float,
    start_lon: float,
    travel_minutes_fn: TravelMinutesFn,
) -> list[dict]:
    """Reverse segments while the open-tour travel time keeps shrinking."""
    best_order = list(ordered_places)
    best_total = calculate_total_travel_minutes(best_order, start_lat, start_lon, travel_minutes_fn)
    improved = True
    while improved:
        improved = False
        for first in range(len(best_order) - 1):
            for second in range(first + 1, len(best_order)):
                candidate = (
                    best_order[:first]
                    + list(reversed(best_order[first : second + 1]))
                    + best_order[second + 1 :]
                )
                candidate_total = calculate_total_travel_minutes(
                    candidate, start_lat, start_lon, travel_minutes_fn
                )
                if candidate_total < best_total:
                    best_order, best_total = candidate, candidate_total
                    improved = True
    return best_order


def calculate_total_travel_minutes(
    ordered_places: list[dict],
    start_lat: float,
    start_lon: float,
    travel_minutes_fn: TravelMinutesFn,
) -> int:
    """Sum of start -> first -> ... -> last legs (no return to start)."""
    total_minutes = 0
    current_lat, current_lon = start_lat, start_lon
    for place in ordered_places:
        total_minutes += travel_minutes_fn(
            current_lat, current_lon, place["lat"], place["lon"]
        )
        current_lat, current_lon = place["lat"], place["lon"]
    return total_minutes
