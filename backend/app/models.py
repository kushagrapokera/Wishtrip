"""Pydantic contracts for the Wishtrip API (plan.md §Contracts).

Backend planner and frontend both code against these shapes — do not change
field names without updating plan.md and the frontend fetch layer.
"""

from datetime import date as date_class
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

PaceLevel = Literal["easy_going", "balanced", "packed"]
BudgetLevel = Literal["budget", "mid", "premium"]
TravellerType = Literal["solo", "couple", "family", "friends", "seniors"]
DietaryPreference = Literal["veg", "vegan", "jain", "halal", "none"]


class PartyComposition(BaseModel):
    adults: int = Field(ge=1, le=12)
    children: int = Field(ge=0, le=8, default=0)


class TripRequest(BaseModel):
    destination: str = "goa"
    origin_city: str
    # Full date or month name; month alone is enough (drives seasonality)
    start_date: Optional[date_class] = None
    start_month: Optional[int] = Field(None, ge=1, le=12)
    nights: int = Field(ge=1, le=21)
    traveller_type: TravellerType
    party: PartyComposition
    interests: list[str] = Field(min_length=1)
    pace: PaceLevel
    budget_level: BudgetLevel
    # Optional enhancements
    dietary_preference: DietaryPreference = "none"
    needs_wheelchair_access: bool = False

    @model_validator(mode="after")
    def validate_start_timing(self) -> "TripRequest":
        if self.start_date is None and self.start_month is None:
            raise ValueError("provide start_date or start_month")
        if self.destination not in ("goa",):
            raise ValueError(f"unsupported destination: {self.destination}")
        return self

    @property
    def travel_month(self) -> int:
        if self.start_date is not None:
            return self.start_date.month
        return self.start_month


class TravelLeg(BaseModel):
    """Movement between two consecutive stops of a day."""

    from_place_id: Optional[str] = None  # None for the first leg of the day
    to_place_id: str
    travel_minutes: int = Field(ge=0)
    mode: Literal["walk", "drive"]


class ScheduledActivity(BaseModel):
    """One entry on a day's timeline: a visited place, a meal, or a transfer."""

    kind: Literal["place", "meal", "transfer_note"]
    place_id: Optional[str] = None
    name: str
    category: Optional[str] = None
    # Coordinates for the frontend map (Phase 5); None for generic meals with
    # no venue. Added as optional fields — old clients simply ignore them.
    lat: Optional[float] = None
    lon: Optional[float] = None
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    visit_duration_minutes: int = Field(ge=0)
    # Group total for the whole party (per-adult base x party multiplier).
    indicative_cost_inr: Optional[int] = None
    cost_is_estimate: bool = True
    hours_unverified: bool = False
    why: str
    travel_leg_before: Optional[TravelLeg] = None


class DayPlan(BaseModel):
    day_number: int = Field(ge=1)
    date: Optional[date_class] = None
    zone: str
    theme: str  # short label, e.g. "North Goa beaches"
    activities: list[ScheduledActivity]
    day_travel_minutes_total: int = 0
    # Group total for the day (sum of activity group costs).
    day_cost_inr_estimate: int = 0


class ItinerarySummary(BaseModel):
    total_days: int
    # Group total for the trip (sum of day group costs).
    total_estimated_cost_inr: int
    narration: Optional[str] = None  # LLM or template prose; None = narration unavailable


class Itinerary(BaseModel):
    request_id: Optional[str] = None
    trip_request: TripRequest
    days: list[DayPlan]
    summary: ItinerarySummary
    assumptions: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str
