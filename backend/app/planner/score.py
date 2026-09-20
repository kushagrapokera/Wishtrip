"""Interest/traveller scoring: decide *how good* each eligible place is.

Scores are pure functions of (place, request) — no DB, no network — so tests
can rank hand-built fixtures directly.
"""

from app import config
from app.models import TripRequest


def score_place_for_traveller(place: dict, trip_request: TripRequest) -> float:
    """Weighted interest matches + rating bonus + party adjustments + monsoon demotion."""
    interest_score = calculate_interest_score(place, trip_request)
    rating_bonus = calculate_rating_bonus(place)
    party_bonus = calculate_party_bonus(place, trip_request)
    monsoon_penalty = calculate_monsoon_penalty(place, trip_request)
    return round(interest_score + rating_bonus + party_bonus - monsoon_penalty, 3)


def calculate_interest_score(place: dict, trip_request: TripRequest) -> float:
    """Sum of interest -> category weights for the place's category."""
    category = place.get("category", "")
    total = 0.0
    for interest in trip_request.interests:
        weights = config.INTEREST_CATEGORY_WEIGHTS.get(interest, {})
        total += weights.get(category, 0.0)
    return total


def calculate_rating_bonus(place: dict) -> float:
    """Top-rated places (4.8) earn the full bonus; unrated places earn nothing."""
    rating = place.get("rating")
    if rating is None:
        return 0.0
    return round(max(0.0, (rating - 3.0) / 1.8) * config.RATING_BONUS_SCALE, 3)


def calculate_party_bonus(place: dict, trip_request: TripRequest) -> float:
    """Families prefer kids_ok venues, seniors prefer seniors_ok venues."""
    bonus = 0.0
    has_children = (trip_request.party.children or 0) > 0
    if (trip_request.traveller_type == "family" or has_children) and place.get(
        "kids_ok", True
    ):
        bonus += config.KIDS_OK_BONUS
    if trip_request.traveller_type == "seniors" and place.get("seniors_ok", True):
        bonus += config.SENIORS_OK_BONUS
    if trip_request.traveller_type == "friends" and place.get("category") == "nightlife":
        bonus += config.FRIENDS_NIGHTLIFE_BONUS
    return bonus


def calculate_monsoon_penalty(place: dict, trip_request: TripRequest) -> float:
    """Beaches and water adventures lose appeal in monsoon months (June-Sept)."""
    if trip_request.travel_month in config.MONSOON_MONTHS:
        if place.get("category") in config.MONSOON_DEMOTED_CATEGORIES:
            return config.MONSOON_DEMOTION_PENALTY
    return 0.0


def rank_candidate_places(
    places: list[dict], trip_request: TripRequest
) -> list[dict]:
    """Return copies of eligible places sorted by descending planner score.

    Each copy carries ``planner_score`` and ``score_reasons`` (short strings
    that feed the per-activity ``why`` explanations downstream).
    """
    scored_places: list[dict] = []
    for place in places:
        ranked_place = dict(place)
        ranked_place["interest_score"] = calculate_interest_score(place, trip_request)
        ranked_place["planner_score"] = score_place_for_traveller(place, trip_request)
        ranked_place["score_reasons"] = describe_score_reasons(place, trip_request)
        scored_places.append(ranked_place)
    scored_places.sort(
        key=lambda ranked: (ranked["planner_score"], ranked.get("rating") or 0.0),
        reverse=True,
    )
    return scored_places


def describe_score_reasons(place: dict, trip_request: TripRequest) -> list[str]:
    """Short human phrases explaining the score (used for ``why`` text)."""
    reasons: list[str] = []
    category = place.get("category", "")
    for interest in trip_request.interests:
        weight = config.INTEREST_CATEGORY_WEIGHTS.get(interest, {}).get(category, 0.0)
        if weight >= 0.5:
            reasons.append(f"matches your interest in {interest}")
    rating = place.get("rating")
    if rating is not None and rating >= 4.5:
        reasons.append(f"highly rated ({rating})")
    if trip_request.traveller_type == "family" and place.get("kids_ok", True):
        reasons.append("kid-friendly for your family")
    if trip_request.traveller_type == "seniors" and place.get("seniors_ok", True):
        reasons.append("comfortable for senior travellers")
    if trip_request.traveller_type == "friends" and place.get("category") == "nightlife":
        reasons.append("lively nightlife pick for friends")
    return reasons
