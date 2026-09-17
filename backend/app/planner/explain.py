"""Per-activity ``why`` explanations derived from planning decisions.

Every string here traces back to a rule the planner actually applied —
interest match, rating, party suitability, diet, or travel time — never prose
invented after the fact.
"""

from app.models import TripRequest


def build_why_for_place(
    place: dict,
    trip_request: TripRequest,
    travel_minutes: int | None = None,
    travel_mode: str | None = None,
) -> str:
    """One-to-two sentence reason this stop suits this traveller."""
    clauses: list[str] = []
    score_reasons = place.get("score_reasons") or []
    if score_reasons:
        clauses.append("; ".join(score_reasons[:2]).capitalize())
    else:
        clauses.append("Fits your trip rhythm and route")

    diet_clause = describe_diet_clause(place, trip_request)
    if diet_clause:
        clauses.append(diet_clause)

    if travel_minutes is not None and travel_mode is not None:
        clauses.append(f"{travel_minutes} min {travel_mode} from the previous stop")

    pace_clause = describe_pace_clause(trip_request)
    if pace_clause:
        clauses.append(pace_clause)
    return ". ".join(clauses) + "."


def describe_diet_clause(place: dict, trip_request: TripRequest) -> str | None:
    if trip_request.dietary_preference == "none" or place.get("category") != "food":
        return None
    return f"Suits your {trip_request.dietary_preference} diet"


def describe_pace_clause(trip_request: TripRequest) -> str | None:
    if trip_request.pace == "easy_going":
        return "kept unhurried for your easy-going pace"
    if trip_request.pace == "packed":
        return "fits your packed pace"
    return None


def build_why_for_meal(
    meal_venue: dict | None,
    generic_meal_name: str,
    trip_request: TripRequest,
    zone_label: str,
) -> str:
    """Reason for the anchored meal: diet fit plus staying in the day's zone."""
    diet_word = trip_request.dietary_preference
    if meal_venue is not None:
        if diet_word != "none":
            return (
                f"{diet_word.capitalize()}-compatible {meal_venue['name']} keeps you "
                f"in {zone_label} over mealtime."
            )
        return f"Local dining at {meal_venue['name']} keeps you in {zone_label} over mealtime."
    if diet_word != "none":
        return (
            f"{generic_meal_name}: no verified {diet_word} venue left in {zone_label}, "
            "so ask the kitchen before ordering (assumption)."
        )
    return f"{generic_meal_name}: a convenient break that keeps you in {zone_label}."


def build_why_for_day_trip(place: dict, trip_request: TripRequest) -> str:
    """Full-day excursions get their own reason: the outing needs the whole day."""
    base_reason = build_why_for_place(place, trip_request)
    return f"A full-day excursion, so the day is kept free for it. {base_reason}"
