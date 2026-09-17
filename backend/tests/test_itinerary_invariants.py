"""Cross-cutting itinerary invariants + optimisation/estimator properties.

These sit above the per-rule tests: whatever the request, a finished itinerary
must never repeat a venue, must keep a valid timeline, and the optimiser must
never worsen the route it was given.
"""

import re

from app.models import TripRequest
from app.planner import sequence as day_sequence
from app.planner.itinerary_builder import plan_trip
from app.planner.travel_time import (
    choose_travel_mode,
    estimate_travel_minutes,
)

TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def make_place(place_id: str, **overrides) -> dict:
    place = {
        "id": place_id,
        "name": f"Place {place_id}",
        "lat": 15.55,
        "lon": 73.75,
        "zone": "north_goa",
        "category": "beach",
        "subcategory": None,
        "visit_duration_minutes": 60,
        "price_level": 1,
        "rating": 4.0,
        "opening_hours": {},
        "hours_unknown": True,
        "tags": ["beaches"],
        "suitability": [],
        "kids_ok": True,
        "seniors_ok": True,
        "seasonally_closed_months": [],
        "description": "",
        "source": {},
    }
    place.update(overrides)
    return place


def test_itinerary_never_repeats_venue_and_keeps_valid_timeline() -> None:
    places = [make_place(f"beach-{index}") for index in range(14)]
    trip_request = TripRequest(
        origin_city="delhi",
        start_month=12,
        nights=3,
        traveller_type="friends",
        party={"adults": 3},
        interests=["beaches", "food", "nightlife"],
        pace="balanced",
        budget_level="premium",
    )
    itinerary = plan_trip(trip_request, places)

    assert len(itinerary.days) == 4
    venue_ids = [
        activity.place_id
        for day in itinerary.days
        for activity in day.activities
        if activity.place_id is not None
    ]
    assert len(venue_ids) == len(set(venue_ids))

    for day in itinerary.days:
        assert day.activities
        for activity in day.activities:
            assert activity.why.strip()
            assert TIME_PATTERN.match(activity.start_time)
            assert TIME_PATTERN.match(activity.end_time)
            assert activity.start_time < activity.end_time
        day_starts = [activity.start_time for activity in day.activities]
        assert day_starts == sorted(day_starts)


def test_sequence_two_opt_never_worsens_greedy_route() -> None:
    zigzag_stops = [
        make_place("far-east", lat=15.55, lon=73.90),
        make_place("near-north", lat=15.56, lon=73.75),
        make_place("mid-east", lat=15.55, lon=73.82),
        make_place("near-south", lat=15.54, lon=73.75),
        make_place("farther-east", lat=15.55, lon=73.95),
    ]
    start_lat, start_lon = 15.55, 73.75
    greedy_order = day_sequence.order_by_nearest_neighbour(
        zigzag_stops, start_lat, start_lon, estimate_travel_minutes
    )
    improved_order = day_sequence.improve_sequence_with_two_opt(
        greedy_order, start_lat, start_lon, estimate_travel_minutes
    )
    assert {place["id"] for place in improved_order} == {
        place["id"] for place in zigzag_stops
    }
    assert day_sequence.calculate_total_travel_minutes(
        improved_order, start_lat, start_lon, estimate_travel_minutes
    ) <= day_sequence.calculate_total_travel_minutes(
        greedy_order, start_lat, start_lon, estimate_travel_minutes
    )


def test_travel_estimator_walks_short_hops_and_drives_long_ones() -> None:
    short_hop_minutes = estimate_travel_minutes(15.55, 73.75, 15.551, 73.751)
    long_haul_minutes = estimate_travel_minutes(15.55, 73.75, 15.30, 73.95)
    assert choose_travel_mode(0.2) == "walk"
    assert choose_travel_mode(12.0) == "drive"
    assert 0 < short_hop_minutes < long_haul_minutes
