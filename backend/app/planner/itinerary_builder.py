"""Itinerary assembly: the fixed pipeline filter → score → cluster → sequence → budget → explain.

``plan_trip`` is pure — (TripRequest, place dicts) in, ``Itinerary`` out — so
tests need no DB or network. The FastAPI layer (Phase 3) only loads data and
delegates here.
"""

from datetime import date, timedelta

from app import config
from app.models import DayPlan, Itinerary, ItinerarySummary, ScheduledActivity, TravelLeg, TripRequest
from app.planner import budget as pace_budget
from app.planner import cluster as day_cluster
from app.planner import explain as explainer
from app.planner import filter as place_filter
from app.planner import meals as meal_anchor
from app.planner import narrate as narrator
from app.planner import score as place_score
from app.planner import sequence as day_sequence
from app.planner.opening_hours import (
    calculate_earliest_start_minutes,
    calculate_latest_end_minutes,
)
from app.planner.travel_time import (
    TravelMinutesFn,
    calculate_haversine_distance_km,
    choose_travel_mode,
    estimate_travel_minutes,
)

LUNCH_ANCHOR_MINUTES = config.MEAL_ANCHOR_TIMES["lunch"]["start_hour"] * 60
LUNCH_DURATION_MINUTES = config.MEAL_ANCHOR_TIMES["lunch"]["duration_minutes"]
DINNER_ANCHOR_MINUTES = config.MEAL_ANCHOR_TIMES["dinner"]["start_hour"] * 60
DINNER_DURATION_MINUTES = config.MEAL_ANCHOR_TIMES["dinner"]["duration_minutes"]
MINIMUM_SHORTENED_VISIT_MINUTES = 20

CATEGORY_THEME_WORDS = {
    "beach": "beaches",
    "food": "food trail",
    "museum_heritage": "heritage",
    "fort_landmark": "forts & viewpoints",
    "park_nature": "nature",
    "market": "markets",
    "nightlife": "nightlife",
    "wellness_spa": "wellness",
    "adventure": "adventure",
    "day_trip": "day trip",
}


class NoSuitablePlacesError(ValueError):
    """Raised when filters leave nothing to plan with (Phase 3 maps this)."""


def plan_trip(
    trip_request: TripRequest,
    places: list[dict],
    travel_minutes_fn: TravelMinutesFn = estimate_travel_minutes,
) -> Itinerary:
    """Build a complete day-by-day itinerary for the request."""
    eligible_places, exclusion_notes = place_filter.filter_places_for_request(
        places, trip_request
    )
    if not eligible_places:
        raise NoSuitablePlacesError(
            "no suitable places left after filtering; loosen budget, dates or interests"
        )

    ranked_places = place_score.rank_candidate_places(eligible_places, trip_request)
    day_clusters = day_cluster.cluster_places_into_days(
        ranked_places, trip_request, travel_minutes_fn
    )

    used_place_ids: set[str] = set()
    day_plans: list[DayPlan] = []
    itinerary_assumptions: list[str] = list(exclusion_notes)
    # Fill helpers may only take leftovers: every clustered id belongs to its
    # day already, and the day loop schedules those unconditionally.
    clustered_place_ids: set[str] = {
        place["id"] for cluster in day_clusters for place in cluster["places"]
    }

    for day_index, cluster in enumerate(day_clusters):
        day_plan = schedule_day_cluster(
            cluster, day_index, len(day_clusters), trip_request,
            ranked_places, used_place_ids, clustered_place_ids,
            travel_minutes_fn, itinerary_assumptions,
        )
        day_plans.append(day_plan)

    collect_global_assumptions(
        trip_request, ranked_places, day_plans, itinerary_assumptions
    )

    day_summaries = [summarise_day_plan(day) for day in day_plans]
    total_cost = sum(day.day_cost_inr_estimate for day in day_plans)
    return Itinerary(
        trip_request=trip_request,
        days=day_plans,
        summary=ItinerarySummary(
            total_days=len(day_plans),
            total_estimated_cost_inr=total_cost,
            narration=narrator.narrate_itinerary(
                day_summaries, trip_request, len(day_plans)
            ),
        ),
        assumptions=sorted(set(itinerary_assumptions)),
    )


def schedule_day_cluster(
    cluster: dict,
    day_index: int,
    total_days: int,
    trip_request: TripRequest,
    ranked_places: list[dict],
    used_place_ids: set[str],
    clustered_place_ids: set[str],
    travel_minutes_fn: TravelMinutesFn,
    itinerary_assumptions: list[str],
) -> DayPlan:
    """Sequence, budget-trim and timetable one day cluster."""
    day_number = day_index + 1
    is_arrival_day = day_index == 0
    is_departure_day = day_index == total_days - 1
    is_edge_day = is_arrival_day or is_departure_day
    visit_date = calculate_visit_date(trip_request, day_index)
    start_lat, start_lon = calculate_day_start_point(cluster, is_arrival_day)

    if cluster.get("is_day_trip"):
        return schedule_day_trip(
            cluster, day_number, total_days, trip_request, visit_date,
            start_lat, start_lon, ranked_places, used_place_ids,
            clustered_place_ids, travel_minutes_fn, itinerary_assumptions,
        )

    ordered_places = day_sequence.build_day_sequence(
        cluster["places"], start_lat, start_lon, travel_minutes_fn
    )
    affordable_places = pace_budget.apply_pace_budget_to_day(
        ordered_places, trip_request, is_edge_day,
        start_lat, start_lon, travel_minutes_fn,
    )
    return schedule_sightseeing_day(
        cluster["zone"], affordable_places, day_number, trip_request, visit_date,
        is_departure_day, start_lat, start_lon, ranked_places,
        used_place_ids, clustered_place_ids, travel_minutes_fn,
        itinerary_assumptions,
    )


def schedule_sightseeing_day(
    zone: str,
    ordered_places: list[dict],
    day_number: int,
    trip_request: TripRequest,
    visit_date: date | None,
    is_departure_day: bool,
    start_lat: float,
    start_lon: float,
    ranked_places: list[dict],
    used_place_ids: set[str],
    clustered_place_ids: set[str],
    travel_minutes_fn: TravelMinutesFn,
    itinerary_assumptions: list[str],
) -> DayPlan:
    """Timetable sightseeing stops with lunch/dinner anchored around them."""
    day_start_minutes = (
        config.ARRIVAL_DAY_START_HOUR * 60 if day_number == 1 else config.DAY_START_HOUR * 60
    )
    scheduler = DayScheduler(
        trip_request=trip_request,
        visit_date=visit_date,
        current_minutes=day_start_minutes,
        current_lat=start_lat,
        current_lon=start_lon,
        previous_place_id=None,
        travel_minutes_fn=travel_minutes_fn,
        assumptions=itinerary_assumptions,
    )

    lunch_venue, dinner_venue = reserve_meal_venues(
        zone, ordered_places, ranked_places, used_place_ids,
        meal_anchor.should_serve_dinner(is_departure_day),
    )
    needs_dinner = meal_anchor.should_serve_dinner(is_departure_day)
    lunch_placed = False
    dinner_placed = False

    for place in ordered_places:
        if not lunch_placed and scheduler.current_minutes >= LUNCH_ANCHOR_MINUTES:
            scheduler.anchor_meal("lunch", lunch_venue, zone, used_place_ids)
            lunch_placed = True
        if (
            not dinner_placed
            and needs_dinner
            and scheduler.current_minutes >= DINNER_ANCHOR_MINUTES
        ):
            scheduler.anchor_meal("dinner", dinner_venue, zone, used_place_ids)
            dinner_placed = True
        scheduler.schedule_place_visit(place, used_place_ids)

    if not lunch_placed:
        scheduler.current_minutes = max(scheduler.current_minutes, 12 * 60)
        scheduler.anchor_meal("lunch", lunch_venue, zone, used_place_ids)
    if needs_dinner and not dinner_placed:
        is_edge_day = day_number == 1 or is_departure_day
        day_max_stops, _ = pace_budget.lookup_day_budget(trip_request, is_edge_day)
        fill_afternoon_gap(
            scheduler, zone, ranked_places, used_place_ids,
            clustered_place_ids, day_max_stops,
        )
        maybe_insert_rest_block(scheduler, zone)
        scheduler.current_minutes = max(scheduler.current_minutes, DINNER_ANCHOR_MINUTES)
        scheduler.anchor_meal("dinner", dinner_venue, zone, used_place_ids)

    if not ordered_places:
        itinerary_assumptions.append(
            f"day {day_number}: candidate pool exhausted — a rest day with meals only"
        )
    return scheduler.to_day_plan(day_number, zone, describe_day_theme(zone, ordered_places))


def schedule_day_trip(
    cluster: dict,
    day_number: int,
    total_days: int,
    trip_request: TripRequest,
    visit_date: date | None,
    start_lat: float,
    start_lon: float,
    ranked_places: list[dict],
    used_place_ids: set[str],
    clustered_place_ids: set[str],
    travel_minutes_fn: TravelMinutesFn,
    itinerary_assumptions: list[str],
) -> DayPlan:
    """A day-trip venue leads its day: excursion first, then light nearby stops + dinner."""
    scheduler = DayScheduler(
        trip_request=trip_request,
        visit_date=visit_date,
        current_minutes=config.DAY_START_HOUR * 60,
        current_lat=start_lat,
        current_lon=start_lon,
        previous_place_id=None,
        travel_minutes_fn=travel_minutes_fn,
        assumptions=itinerary_assumptions,
    )
    day_trip_place = cluster["places"][0]
    scheduler.schedule_place_visit(day_trip_place, used_place_ids, is_day_trip=True)
    for nearby_place in pick_nearby_evening_stops(
        day_trip_place, cluster.get("zone", ""), ranked_places,
        used_place_ids, clustered_place_ids, scheduler.current_lat,
        scheduler.current_lon, travel_minutes_fn,
    ):
        scheduler.schedule_place_visit(nearby_place, used_place_ids)
    if meal_anchor.should_serve_dinner(day_number == total_days):
        dinner_venue = meal_anchor.select_meal_venue(
            [day_trip_place],
            meal_anchor.meal_candidates_for_zone(ranked_places, cluster.get("zone", "")),
            used_place_ids,
        )
        scheduler.current_minutes = max(scheduler.current_minutes, DINNER_ANCHOR_MINUTES)
        scheduler.anchor_meal("dinner", dinner_venue, cluster.get("zone", ""), used_place_ids)
    itinerary_assumptions.append(
        f"day {day_number}: {day_trip_place['name']} is a full-day excursion — "
        "carry lunch and confirm transport (assumption)"
    )
    theme = f"{config.ZONE_LABELS.get(cluster['zone'], cluster['zone'])} day trip: {day_trip_place['name']}"
    return scheduler.to_day_plan(day_number, cluster["zone"], theme)


def pick_nearby_evening_stops(
    day_trip_place: dict,
    zone: str,
    ranked_places: list[dict],
    used_place_ids: set[str],
    clustered_place_ids: set[str],
    current_lat: float,
    current_lon: float,
    travel_minutes_fn: TravelMinutesFn,
) -> list[dict]:
    """Up to two light unused same-zone stops nearest the excursion site."""
    candidates = [
        place
        for place in ranked_places
        if place["id"] not in used_place_ids
        and place["id"] not in clustered_place_ids
        and place["id"] != day_trip_place["id"]
        and place.get("zone") == zone
        and place.get("category") != config.DAY_TRIP_CATEGORY
        and place.get("visit_duration_minutes", 60) <= config.DAY_TRIP_EXTRA_MAX_DURATION_MINUTES
    ]
    candidates.sort(
        key=lambda place: (
            travel_minutes_fn(current_lat, current_lon, place["lat"], place["lon"]),
            -(place.get("planner_score", 0.0)),
        )
    )
    return candidates[: config.DAY_TRIP_EXTRA_STOPS]


class DayScheduler:
    """Mutable per-day timetable cursor (one instance per day, discarded after)."""

    def __init__(
        self,
        trip_request: TripRequest,
        visit_date: date | None,
        current_minutes: int,
        current_lat: float,
        current_lon: float,
        previous_place_id: str | None,
        travel_minutes_fn: TravelMinutesFn,
        assumptions: list[str],
    ) -> None:
        self.trip_request = trip_request
        self.visit_date = visit_date
        self.current_minutes = current_minutes
        self.current_lat = current_lat
        self.current_lon = current_lon
        self.previous_place_id = previous_place_id
        self.travel_minutes_fn = travel_minutes_fn
        self.assumptions = assumptions
        self.activities: list[ScheduledActivity] = []

    def schedule_place_visit(
        self, place: dict, used_place_ids: set[str], is_day_trip: bool = False
    ) -> bool:
        """Append a sightseeing stop; shrink or skip it when hours/day-end forbid."""
        travel_minutes = self.travel_minutes_fn(
            self.current_lat, self.current_lon, place["lat"], place["lon"]
        )
        travel_mode = choose_travel_mode(
            calculate_haversine_distance_km(
                self.current_lat, self.current_lon, place["lat"], place["lon"]
            )
        )
        arrival_minutes = self.current_minutes + travel_minutes
        earliest_start = calculate_earliest_start_minutes(place, self.visit_date)
        if earliest_start is not None and arrival_minutes < earliest_start:
            arrival_minutes = earliest_start
        latest_end = calculate_latest_end_minutes(place, self.visit_date)
        day_end_minutes = config.DAY_END_HOUR * 60
        effective_close = min(latest_end, day_end_minutes) if latest_end else day_end_minutes

        visit_minutes = place.get("visit_duration_minutes", 60)
        if arrival_minutes >= effective_close:
            self.assumptions.append(
                f"skipped {place['name']}: cannot fit inside its hours on this day"
            )
            return False
        if arrival_minutes + visit_minutes > effective_close:
            visit_minutes = effective_close - arrival_minutes
            if visit_minutes < MINIMUM_SHORTENED_VISIT_MINUTES:
                self.assumptions.append(
                    f"skipped {place['name']}: too little time inside its hours"
                )
                return False
            self.assumptions.append(
                f"shortened visit at {place['name']} to fit published hours (assumption)"
            )

        end_minutes = arrival_minutes + visit_minutes
        if is_day_trip:
            why = explainer.build_why_for_day_trip(place, self.trip_request)
        else:
            why = explainer.build_why_for_place(
                place, self.trip_request, travel_minutes, travel_mode
            )
        self.activities.append(
            ScheduledActivity(
                kind="place",
                place_id=place["id"],
                name=place["name"],
                category=place.get("category"),
                lat=place["lat"],
                lon=place["lon"],
                start_time=format_clock_time(arrival_minutes),
                end_time=format_clock_time(end_minutes),
                visit_duration_minutes=visit_minutes,
                indicative_cost_inr=estimate_place_cost_for_party(place, self.trip_request),
                cost_is_estimate=True,
                hours_unverified=bool(place.get("hours_unknown", True)),
                why=why,
                travel_leg_before=TravelLeg(
                    from_place_id=self.previous_place_id,
                    to_place_id=place["id"],
                    travel_minutes=travel_minutes,
                    mode=travel_mode,  # type: ignore[arg-type]
                ),
            )
        )
        used_place_ids.add(place["id"])
        self.current_minutes = end_minutes
        self.current_lat, self.current_lon = place["lat"], place["lon"]
        self.previous_place_id = place["id"]
        return True

    def anchor_meal(
        self, meal: str, meal_venue: dict | None, zone: str, used_place_ids: set[str]
    ) -> None:
        """Append a lunch/dinner activity at the current cursor.

        Travel to a real venue consumes clock time like any sightseeing leg,
        so the recorded travel leg and the timetable stay consistent with
        each other.
        """
        duration = LUNCH_DURATION_MINUTES if meal == "lunch" else DINNER_DURATION_MINUTES
        zone_label = config.ZONE_LABELS.get(zone, zone)
        if meal_venue is not None:
            travel_minutes = self.travel_minutes_fn(
                self.current_lat, self.current_lon,
                meal_venue["lat"], meal_venue["lon"],
            )
            travel_mode = choose_travel_mode(
                calculate_haversine_distance_km(
                    self.current_lat, self.current_lon,
                    meal_venue["lat"], meal_venue["lon"],
                )
            )
        else:
            travel_minutes, travel_mode = 10, "drive"
        meal_start_minutes = self.current_minutes + travel_minutes
        end_minutes = min(meal_start_minutes + duration, config.DAY_END_HOUR * 60)
        actual_duration = end_minutes - meal_start_minutes
        if actual_duration <= 0:
            return

        if meal_venue is not None:
            name = f"{meal.capitalize()} — {meal_venue['name']}"
            place_id: str | None = meal_venue["id"]
            meal_lat: float | None = meal_venue["lat"]
            meal_lon: float | None = meal_venue["lon"]
            cost = estimate_meal_cost_for_party(meal_venue, self.trip_request)
            hours_unverified = bool(meal_venue.get("hours_unknown", True))
            used_place_ids.add(meal_venue["id"])
            next_lat, next_lon = meal_venue["lat"], meal_venue["lon"]
        else:
            name = meal_anchor.build_generic_meal_name(meal, zone)
            place_id = None
            meal_lat, meal_lon = None, None
            cost = calculate_group_cost(
                config.MEAL_COST_INR_BY_PRICE_LEVEL[1], self.trip_request
            )
            hours_unverified = True
            next_lat, next_lon = self.current_lat, self.current_lon
            self.assumptions.append(
                f"no verified {meal} venue left in {zone_label} — generic meal assumed"
            )

        self.activities.append(
            ScheduledActivity(
                kind="meal",
                place_id=place_id,
                name=name,
                category="food",
                lat=meal_lat,
                lon=meal_lon,
                start_time=format_clock_time(meal_start_minutes),
                end_time=format_clock_time(end_minutes),
                visit_duration_minutes=actual_duration,
                indicative_cost_inr=cost,
                cost_is_estimate=True,
                hours_unverified=hours_unverified,
                why=explainer.build_why_for_meal(
                    meal_venue,
                    f"{meal.capitalize()} break",
                    self.trip_request,
                    zone_label,
                ),
                travel_leg_before=TravelLeg(
                    from_place_id=self.previous_place_id,
                    to_place_id=place_id or f"meal-day-{meal}",
                    travel_minutes=travel_minutes,
                    mode=travel_mode,  # type: ignore[arg-type]
                ),
            )
        )
        self.current_minutes = end_minutes
        self.current_lat, self.current_lon = next_lat, next_lon
        if place_id is not None:
            self.previous_place_id = place_id

    def anchor_rest_break(self, end_minutes: int, zone: str) -> bool:
        """Cover a long idle span with explicit unstructured time (no fake venue)."""
        if end_minutes <= self.current_minutes:
            return False
        zone_label = config.ZONE_LABELS.get(zone, zone)
        self.activities.append(
            ScheduledActivity(
                kind="transfer_note",
                place_id=None,
                name=f"Free time in {zone_label} — rest at your own pace",
                category=None,
                lat=None,
                lon=None,
                start_time=format_clock_time(self.current_minutes),
                end_time=format_clock_time(end_minutes),
                visit_duration_minutes=end_minutes - self.current_minutes,
                indicative_cost_inr=0,
                cost_is_estimate=False,
                hours_unverified=False,
                why=explainer.build_why_for_rest_break(zone_label, self.trip_request),
                travel_leg_before=None,
            )
        )
        self.current_minutes = end_minutes
        return True

    def to_day_plan(self, day_number: int, zone: str, theme: str) -> DayPlan:
        day_travel = sum(
            activity.travel_leg_before.travel_minutes
            for activity in self.activities
            if activity.travel_leg_before is not None
        )
        day_cost = sum(activity.indicative_cost_inr or 0 for activity in self.activities)
        return DayPlan(
            day_number=day_number,
            date=self.visit_date,
            zone=zone,
            theme=theme,
            activities=self.activities,
            day_travel_minutes_total=day_travel,
            day_cost_inr_estimate=day_cost,
        )


def reserve_meal_venues(
    zone: str,
    ordered_places: list[dict],
    ranked_places: list[dict],
    used_place_ids: set[str],
    needs_dinner: bool,
) -> tuple[dict | None, dict | None]:
    """Pick lunch (and maybe dinner) venues near the day's midpoint."""
    if not ordered_places:
        return None, None
    day_place_ids = {place["id"] for place in ordered_places}
    unavailable_ids = set(used_place_ids) | day_place_ids
    candidates = meal_anchor.meal_candidates_for_zone(ranked_places, zone)
    lunch_venue = meal_anchor.select_meal_venue(
        ordered_places, candidates, unavailable_ids
    )
    if lunch_venue is not None:
        used_place_ids.add(lunch_venue["id"])
        unavailable_ids.add(lunch_venue["id"])
    dinner_venue: dict | None = None
    if needs_dinner:
        dinner_venue = meal_anchor.select_meal_venue(
            ordered_places, candidates, unavailable_ids
        )
        if dinner_venue is not None:
            used_place_ids.add(dinner_venue["id"])
    return lunch_venue, dinner_venue


def fill_afternoon_gap(
    scheduler: DayScheduler,
    zone: str,
    ranked_places: list[dict],
    used_place_ids: set[str],
    clustered_place_ids: set[str],
    day_max_stops: int,
) -> None:
    """Schedule leftover same-zone light stops into the run-up to dinner.

    Never exceeds the day's pace budget: stops already on the timeline count
    toward day_max_stops. Only true leftovers are eligible — clustered ids
    belong to their own days.
    """
    for _ in range(config.AFTERNOON_FILL_MAX_STOPS):
        place_stops = sum(
            1 for activity in scheduler.activities if activity.kind == "place"
        )
        if place_stops >= day_max_stops:
            return
        if DINNER_ANCHOR_MINUTES - scheduler.current_minutes < config.REST_MIN_GAP_MINUTES:
            return
        candidates = [
            place
            for place in ranked_places
            if place["id"] not in used_place_ids
            and place["id"] not in clustered_place_ids
            and place.get("zone") == zone
            and place.get("category") != config.DAY_TRIP_CATEGORY
            and place.get("visit_duration_minutes", 60) <= config.AFTERNOON_FILL_MAX_DURATION_MINUTES
        ]
        candidates.sort(
            key=lambda place: (
                scheduler.travel_minutes_fn(
                    scheduler.current_lat, scheduler.current_lon,
                    place["lat"], place["lon"],
                ),
                -(place.get("planner_score", 0.0)),
            )
        )
        scheduled_any = False
        for place in candidates:
            if scheduler.schedule_place_visit(place, used_place_ids):
                scheduled_any = True
                break
        if not scheduled_any:
            return


def maybe_insert_rest_block(scheduler: DayScheduler, zone: str) -> None:
    """Turn a remaining long idle span into an explicit rest activity."""
    if DINNER_ANCHOR_MINUTES - scheduler.current_minutes >= config.REST_MIN_GAP_MINUTES:
        scheduler.anchor_rest_break(DINNER_ANCHOR_MINUTES, zone)


def calculate_visit_date(trip_request: TripRequest, day_index: int) -> date | None:
    if trip_request.start_date is None:
        return None
    return trip_request.start_date + timedelta(days=day_index)


def calculate_day_start_point(cluster: dict, is_arrival_day: bool) -> tuple[float, float]:
    """Day 1 starts at the airport; later days start at the day's centroid."""
    if is_arrival_day:
        return (config.GOA_AIRPORT_LAT, config.GOA_AIRPORT_LON)
    cluster_places = cluster.get("places") or []
    if not cluster_places:
        return (config.GOA_AIRPORT_LAT, config.GOA_AIRPORT_LON)
    return (
        sum(place["lat"] for place in cluster_places) / len(cluster_places),
        sum(place["lon"] for place in cluster_places) / len(cluster_places),
    )


def describe_day_theme(zone: str, ordered_places: list[dict]) -> str:
    zone_label = config.ZONE_LABELS.get(zone, zone)
    if not ordered_places:
        return f"{zone_label} rest day"
    category_tally: dict[str, int] = {}
    for place in ordered_places:
        category_tally[place.get("category", "")] = category_tally.get(place.get("category", ""), 0) + 1
    dominant_category = max(category_tally, key=lambda category: category_tally[category])
    theme_word = CATEGORY_THEME_WORDS.get(dominant_category, "sights")
    return f"{zone_label} {theme_word}"


def summarise_day_plan(day_plan: DayPlan) -> str:
    stop_count = sum(1 for activity in day_plan.activities if activity.kind == "place")
    return f"{day_plan.theme} with {stop_count} stops."


def calculate_party_cost_multiplier(trip_request: TripRequest) -> float:
    """Adults at full price, children at CHILD_COST_FRACTION (assumption)."""
    adults = trip_request.party.adults or 0
    children = trip_request.party.children or 0
    return adults + children * config.CHILD_COST_FRACTION


def calculate_group_cost(base_cost_inr: int, trip_request: TripRequest) -> int:
    """Scale a per-adult base cost to the whole party; free stays free."""
    if not base_cost_inr:
        return 0
    return int(round(base_cost_inr * calculate_party_cost_multiplier(trip_request)))


def estimate_place_cost_for_party(place: dict, trip_request: TripRequest) -> int:
    base_cost = config.INDICATIVE_COST_INR_BY_PRICE_LEVEL.get(place.get("price_level", 0), 0)
    return calculate_group_cost(base_cost, trip_request)


def estimate_meal_cost_for_party(meal_venue: dict, trip_request: TripRequest) -> int:
    base_cost = config.MEAL_COST_INR_BY_PRICE_LEVEL.get(meal_venue.get("price_level", 1), 400)
    return calculate_group_cost(base_cost, trip_request)


def format_clock_time(total_minutes: int) -> str:
    clamped = max(0, min(total_minutes, 23 * 60 + 59))
    return f"{clamped // 60:02d}:{clamped % 60:02d}"


def collect_global_assumptions(
    trip_request: TripRequest,
    ranked_places: list[dict],
    day_plans: list[DayPlan],
    itinerary_assumptions: list[str],
) -> None:
    """Honest data caveats that hold for the whole itinerary."""
    itinerary_assumptions.append(
        "visit durations, prices and ratings are estimates from OSM + synthetic "
        "enrichment — verify before you go"
    )
    adults = trip_request.party.adults or 0
    children = trip_request.party.children or 0
    itinerary_assumptions.append(
        f"costs are group estimates for {adults} adult(s)"
        + (f" + {children} child(ren) at 50% each" if children else "")
        + " — verify prices locally"
    )
    itinerary_assumptions.append(
        "travel legs are haversine-distance estimates, not live routing"
    )
    unverified_count = sum(
        1
        for day in day_plans
        for activity in day.activities
        if activity.hours_unverified
    )
    if unverified_count:
        itinerary_assumptions.append(
            f"{unverified_count} stop(s) have unverified opening hours — "
            "confirm timings locally"
        )
    if trip_request.travel_month in config.MONSOON_MONTHS:
        itinerary_assumptions.append(
            "monsoon month (Jun-Sep): beaches and water activities are demoted and "
            "seasonal venues may stay shut — confirm locally"
        )
    if trip_request.dietary_preference != "none":
        diet = trip_request.dietary_preference
        itinerary_assumptions.append(
            f"{diet} suitability is inferred from venue data, not verified — "
            "ask the kitchen before ordering"
        )
    if trip_request.needs_wheelchair_access:
        itinerary_assumptions.append(
            "step-free access is not verified in OSM data — call venues ahead"
        )
