"""Phase 2 planner rule tests: each name states the rule under test.

All planner functions are pure, so every test builds small synthetic fixtures
and needs no DB or network.
"""

from datetime import date

from app.models import TripRequest
from app.planner import filter as place_filter
from app.planner import score as place_score
from app.planner.itinerary_builder import (
    calculate_group_cost,
    estimate_meal_cost_for_party,
    estimate_place_cost_for_party,
    plan_trip,
)
from app.planner.score import calculate_party_bonus

NORTH_ZONE = "north_goa"
SOUTH_ZONE = "south_goa"
PANAJI_ZONE = "panaji"


def make_place(place_id: str, **overrides) -> dict:
    place = {
        "id": place_id,
        "name": f"Place {place_id}",
        "lat": 15.55,
        "lon": 73.75,
        "zone": NORTH_ZONE,
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


def make_request(**overrides) -> TripRequest:
    fields = {
        "origin_city": "delhi",
        "start_month": 12,
        "nights": 2,
        "traveller_type": "solo",
        "party": {"adults": 1},
        "interests": ["beaches"],
        "pace": "balanced",
        "budget_level": "premium",
    }
    fields.update(overrides)
    return TripRequest(**fields)


def place_stops(day) -> list:
    return [activity for activity in day.activities if activity.kind == "place"]


def test_easy_going_pace_limits_day_to_three_stops() -> None:
    places = [make_place(f"beach-{i}") for i in range(12)]
    itinerary = plan_trip(make_request(pace="easy_going"), places)
    assert len(itinerary.days) == 3
    for day in itinerary.days:
        assert len(place_stops(day)) <= 3


def test_packed_pace_allows_six_stops_per_day() -> None:
    places = [make_place(f"beach-{i}") for i in range(20)]
    itinerary = plan_trip(make_request(pace="packed"), places)
    stop_counts = [len(place_stops(day)) for day in itinerary.days]
    assert max(stop_counts) <= 6
    assert max(stop_counts) == 6


def test_day_never_crosses_zones_twice() -> None:
    places = [
        make_place(f"north-{i}", zone=NORTH_ZONE, lat=15.57, lon=73.74)
        for i in range(4)
    ] + [
        make_place(f"south-{i}", zone=SOUTH_ZONE, lat=15.25, lon=73.95)
        for i in range(4)
    ] + [
        make_place(f"panaji-{i}", zone=PANAJI_ZONE, lat=15.49, lon=73.83)
        for i in range(4)
    ]
    zone_by_id = {place["id"]: place["zone"] for place in places}
    itinerary = plan_trip(make_request(nights=3), places)
    for day in itinerary.days:
        day_zones = [
            zone_by_id[activity.place_id]
            for activity in day.activities
            if activity.place_id in zone_by_id
        ]
        zone_changes = sum(
            1 for first, second in zip(day_zones, day_zones[1:]) if first != second
        )
        assert zone_changes <= 1


def test_budget_request_excludes_premium_venues() -> None:
    places = [
        make_place("free-park", category="park_nature", price_level=0),
        make_place("budget-cafe", category="food", price_level=1),
        make_place("mid-spa", category="wellness_spa", price_level=2),
        make_place("premium-club", category="nightlife", price_level=3),
        make_place("premium-resort", category="beach", price_level=3),
    ]
    price_by_id = {place["id"]: place["price_level"] for place in places}
    itinerary = plan_trip(make_request(budget_level="budget"), places)
    scheduled_ids = [
        activity.place_id
        for day in itinerary.days
        for activity in day.activities
        if activity.kind == "place"
    ]
    assert scheduled_ids
    assert all(price_by_id[place_id] in {0, 1} for place_id in scheduled_ids)


def test_family_request_excludes_nightlife_venues() -> None:
    places = [
        make_place("night-club", category="nightlife", kids_ok=False),
        make_place("beach-shack", category="beach", kids_ok=True),
        make_place("spice-farm", category="park_nature", kids_ok=True),
        make_place("family-diner", category="food", kids_ok=True),
    ]
    family_request = make_request(
        traveller_type="family", party={"adults": 2, "children": 2}
    )
    itinerary = plan_trip(family_request, places)
    scheduled_categories = [
        activity.category
        for day in itinerary.days
        for activity in day.activities
        if activity.kind == "place"
    ]
    assert scheduled_categories
    assert "nightlife" not in scheduled_categories


def test_vegan_diet_filters_restaurants() -> None:
    places = [
        make_place(
            "steakhouse",
            name="Seafood Steakhouse",
            category="food",
            description="charcoal grill seafood and steaks",
        ),
        make_place(
            "vegan-cafe",
            name="Green Bowl Vegan Cafe",
            category="food",
            dietary_tags=["vegan", "veg"],
        ),
        make_place("heritage-walk", category="museum_heritage"),
    ]
    vegan_request = make_request(dietary_preference="vegan", interests=["food", "culture"])
    eligible, _ = place_filter.filter_places_for_request(places, vegan_request)
    eligible_ids = {place["id"] for place in eligible}
    assert "steakhouse" not in eligible_ids
    assert "vegan-cafe" in eligible_ids
    assert "heritage-walk" in eligible_ids


def test_monsoon_month_demotes_beaches_and_drops_seasonally_closed() -> None:
    beach = make_place("sunny-beach", category="beach", rating=4.5)
    shack = make_place(
        "water-sports", category="adventure", seasonally_closed_months=[6, 7, 8, 9]
    )
    museum = make_place("old-church", category="museum_heritage", rating=4.2)
    monsoon_request = make_request(start_month=7, interests=["wellness"])
    eligible, _ = place_filter.filter_places_for_request(
        [beach, shack, museum], monsoon_request
    )
    assert "water-sports" not in {place["id"] for place in eligible}

    dry_request = make_request(start_month=12, interests=["wellness"])
    assert place_score.score_place_for_traveller(
        beach, monsoon_request
    ) < place_score.score_place_for_traveller(beach, dry_request)
    # Same wellness request: beach wins in December, indoor heritage wins in July
    dry_ranked = place_score.rank_candidate_places([beach, museum], dry_request)
    monsoon_ranked = place_score.rank_candidate_places(
        [beach, museum], monsoon_request
    )
    assert dry_ranked[0]["id"] == "sunny-beach"
    assert monsoon_ranked[0]["id"] == "old-church"


def test_stop_not_scheduled_before_published_opening_time() -> None:
    late_museum = make_place(
        "late-museum",
        name="Late Museum",
        category="museum_heritage",
        rating=4.8,
        opening_hours={"daily": "12:00-18:00"},
        hours_unknown=False,
    )
    filler = make_place("morning-beach", category="beach", rating=3.2)
    dated_request = make_request(
        start_date=date(2026, 12, 10), interests=["culture", "beaches"]
    )
    itinerary = plan_trip(dated_request, [late_museum, filler])
    museum_starts = [
        activity.start_time
        for day in itinerary.days
        for activity in day.activities
        if activity.place_id == "late-museum"
    ]
    assert museum_starts
    assert all(start >= "12:00" for start in museum_starts)


def test_day_trip_poi_occupies_full_day() -> None:
    day_trip = make_place(
        "dudhsagar",
        name="Dudhsagar Falls",
        category="day_trip",
        zone=SOUTH_ZONE,
        lat=15.31,
        lon=74.31,
        rating=4.8,
        visit_duration_minutes=360,
    )
    nearby = [
        make_place(f"south-beach-{i}", zone=SOUTH_ZONE, lat=15.27, lon=73.96)
        for i in range(6)
    ]
    itinerary = plan_trip(make_request(nights=2, interests=["nature"]), [day_trip] + nearby)
    falls_days = [
        day
        for day in itinerary.days
        if any(activity.place_id == "dudhsagar" for activity in day.activities)
    ]
    assert len(falls_days) == 1
    falls_places = place_stops(falls_days[0])
    assert falls_places[0].place_id == "dudhsagar"
    assert 1 <= len(falls_places) <= 3
    assert [activity.place_id for activity in falls_places].count("dudhsagar") == 1


def test_day_trip_day_adds_nearby_stops_and_dinner() -> None:
    day_trip = make_place(
        "dudhsagar",
        name="Dudhsagar Falls",
        category="day_trip",
        zone=SOUTH_ZONE,
        lat=15.31,
        lon=74.31,
        rating=4.8,
        visit_duration_minutes=360,
    )
    nearby = [
        make_place(
            f"south-beach-{i}", zone=SOUTH_ZONE, lat=15.30, lon=74.30,
            visit_duration_minutes=60,
        )
        for i in range(30)
    ]
    dinner_spot = make_place(
        "south-diner", name="South Diner", category="food", zone=SOUTH_ZONE,
        lat=15.30, lon=74.29, visit_duration_minutes=60,
    )
    itinerary = plan_trip(
        make_request(nights=2, interests=["nature", "food"]), [day_trip] + nearby + [dinner_spot]
    )
    falls_days = [
        day
        for day in itinerary.days
        if any(activity.place_id == "dudhsagar" for activity in day.activities)
    ]
    assert len(falls_days) == 1
    kinds = [activity.kind for activity in falls_days[0].activities]
    assert "meal" in kinds
    assert len(place_stops(falls_days[0])) >= 2


def test_day_trip_without_interest_match_does_not_consume_day() -> None:
    day_trip = make_place(
        "dudhsagar",
        name="Dudhsagar Falls",
        category="day_trip",
        zone=SOUTH_ZONE,
        lat=15.31,
        lon=74.31,
        rating=4.8,
        visit_duration_minutes=360,
    )
    nearby = [
        make_place(f"south-beach-{i}", zone=SOUTH_ZONE, lat=15.27, lon=73.96)
        for i in range(6)
    ]
    foodie_request = make_request(nights=1, interests=["food"])
    itinerary = plan_trip(foodie_request, [day_trip] + nearby)
    scheduled_ids = {
        activity.place_id
        for day in itinerary.days
        for activity in day.activities
    }
    assert "dudhsagar" not in scheduled_ids


def test_group_cost_scales_with_party_size() -> None:
    solo_request = make_request(party={"adults": 1})
    family_request = make_request(
        traveller_type="family", party={"adults": 2, "children": 2}
    )
    paid_place = make_place("paid-fort", price_level=1)
    solo_cost = estimate_place_cost_for_party(paid_place, solo_request)
    family_cost = estimate_place_cost_for_party(paid_place, family_request)
    assert solo_cost == 250
    assert family_cost == 750


def test_children_count_as_half_price_for_meals() -> None:
    family_request = make_request(
        traveller_type="family", party={"adults": 2, "children": 2}
    )
    meal_venue = make_place("diner", category="food", price_level=2)
    assert estimate_meal_cost_for_party(meal_venue, family_request) == 2400


def test_free_places_stay_free_for_family() -> None:
    family_request = make_request(
        traveller_type="family", party={"adults": 2, "children": 2}
    )
    free_place = make_place("free-beach", price_level=0)
    assert estimate_place_cost_for_party(free_place, family_request) == 0
    assert calculate_group_cost(0, family_request) == 0


def test_friends_party_prefers_nightlife_venues() -> None:
    friends_request = make_request(
        traveller_type="friends", party={"adults": 3}, interests=["nightlife"]
    )
    solo_request = make_request(
        traveller_type="solo", party={"adults": 3}, interests=["nightlife"]
    )
    club = make_place("night-club", category="nightlife", kids_ok=False, rating=4.0)
    beach = make_place("calm-beach", category="beach", kids_ok=True, rating=4.0)
    assert calculate_party_bonus(club, friends_request) > calculate_party_bonus(
        beach, friends_request
    )
    assert calculate_party_bonus(club, friends_request) > calculate_party_bonus(
        club, solo_request
    )


def clock_to_minutes(clock_time: str) -> int:
    hours, minutes = clock_time.split(":")
    return int(hours) * 60 + int(minutes)


def test_easy_arrival_day_has_no_long_unexplained_gap() -> None:
    beaches = [
        make_place(f"panaji-beach-{i}", zone=PANAJI_ZONE, lat=15.49, lon=73.83)
        for i in range(8)
    ]
    diners = [
        make_place(
            f"panaji-diner-{i}", name=f"Panaji Diner {i}", category="food",
            zone=PANAJI_ZONE, lat=15.49, lon=73.84,
        )
        for i in range(4)
    ]
    itinerary = plan_trip(
        make_request(
            pace="easy_going", nights=1, interests=["beaches", "food"],
            budget_level="premium",
        ),
        beaches + diners,
    )
    arrival_day = itinerary.days[0]
    assert any(activity.kind == "meal" for activity in arrival_day.activities)
    for previous, current in zip(arrival_day.activities, arrival_day.activities[1:]):
        idle_gap = clock_to_minutes(current.start_time) - clock_to_minutes(previous.end_time)
        assert idle_gap < 120
