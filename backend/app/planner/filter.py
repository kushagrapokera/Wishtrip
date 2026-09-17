"""Hard-constraint filtering: decide what is *eligible*, never how good.

Every exclusion is recorded as a human-readable note so the itinerary can
surface honest assumptions instead of silently dropping places.
"""

from app import config
from app.models import TripRequest


def filter_places_for_request(
    places: list[dict], trip_request: TripRequest
) -> tuple[list[dict], list[str]]:
    """Return (eligible_places, exclusion_notes) for the trip request."""
    eligible_places: list[dict] = []
    exclusion_tally: dict[str, int] = {}

    for place in places:
        exclusion_reason = find_exclusion_reason(place, trip_request)
        if exclusion_reason is None:
            eligible_places.append(place)
        else:
            exclusion_tally[exclusion_reason] = exclusion_tally.get(exclusion_reason, 0) + 1

    exclusion_notes = [
        f"filtered out {count} place(s): {reason}"
        for reason, count in sorted(exclusion_tally.items())
    ]
    return eligible_places, exclusion_notes


def find_exclusion_reason(place: dict, trip_request: TripRequest) -> str | None:
    """First hard-constraint violation for the place, or None if eligible."""
    if not is_budget_compatible(place, trip_request):
        return f"over budget ({trip_request.budget_level} tier)"
    if not is_party_compatible(place, trip_request):
        return "unsuitable for the party (family/seniors exclusion)"
    if not is_seasonally_open(place, trip_request):
        return "seasonally closed in the travel month"
    if not is_diet_compatible(place, trip_request):
        return f"incompatible with {trip_request.dietary_preference} diet"
    if not is_mobility_compatible(place, trip_request):
        return "inaccessible terrain for wheelchair needs"
    return None


def is_budget_compatible(place: dict, trip_request: TripRequest) -> bool:
    """Budget tier maps to allowed price levels (config.ALLOWED_PRICE_LEVELS)."""
    allowed_levels = config.ALLOWED_PRICE_LEVELS[trip_request.budget_level]
    return place.get("price_level", 0) in allowed_levels


def is_party_compatible(place: dict, trip_request: TripRequest) -> bool:
    """Families (or parties with children) need kids_ok; seniors need seniors_ok.

    Nightlife venues are seeded kids_ok=False, adventure venues
    seniors_ok=False, so this single rule covers both exclusions.
    """
    has_children = (trip_request.party.children or 0) > 0
    if trip_request.traveller_type == "family" or has_children:
        if not place.get("kids_ok", True):
            return False
    if trip_request.traveller_type == "seniors":
        if not place.get("seniors_ok", True):
            return False
    return True


def is_seasonally_open(place: dict, trip_request: TripRequest) -> bool:
    """Venues closed in the travel month (monsoon shacks, water sports) are dropped."""
    closed_months = place.get("seasonally_closed_months") or []
    return trip_request.travel_month not in closed_months


def is_diet_compatible(place: dict, trip_request: TripRequest) -> bool:
    """Dietary filter applies to restaurants; other categories always pass.

    Explicit dietary_tags win when present. Without them only an outright meat
    specialty in the name is filtered — mixed-menu Goan kitchens are kept and
    the uncertainty is surfaced as an assumption downstream.
    """
    dietary_preference = trip_request.dietary_preference
    if dietary_preference == "none":
        return True
    if place.get("category") != "food":
        return True

    accepted_tags = config.DIET_ACCEPTED_TAGS[dietary_preference]
    explicit_tags = set(place.get("dietary_tags") or [])
    tag_markers = {tag for tag in (place.get("tags") or []) if tag in accepted_tags}
    if explicit_tags or tag_markers:
        return bool((explicit_tags | tag_markers) & accepted_tags)

    searchable_text = " ".join(
        [
            str(place.get("name") or ""),
            str(place.get("subcategory") or ""),
            str(place.get("description") or ""),
        ]
    ).lower()
    if dietary_preference in ("veg", "vegan", "jain"):
        if any(keyword in searchable_text for keyword in config.NON_VEG_SPECIALTY_KEYWORDS):
            return False
    if dietary_preference == "halal":
        if any(keyword in searchable_text for keyword in config.HARAM_KEYWORDS):
            return False
    return True


def is_mobility_compatible(place: dict, trip_request: TripRequest) -> bool:
    """Wheelchair travellers skip uneven-terrain outings (treks, water sports)."""
    if not trip_request.needs_wheelchair_access:
        return True
    if place.get("category") in ("adventure", "day_trip"):
        return False
    return True
