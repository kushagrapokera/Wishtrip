"""Phase 4 narration tests: LLM prose is layered on, never structural.

The fail-open invariant: whatever the LLM does (or fails to do), the caller
always gets back the complete structured itinerary.
"""

import json

import httpx
import pytest

from app import config
from app.models import TripRequest
from app.planner.itinerary_builder import plan_trip
from app.planner.narrate import enrich_itinerary_narration

LLM_KEY_ENV_VAR = config.LLM_API_KEY_ENV_VAR


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


def make_itinerary():
    trip_request = TripRequest(
        origin_city="delhi",
        start_month=12,
        nights=1,
        traveller_type="solo",
        party={"adults": 1},
        interests=["beaches"],
        pace="balanced",
        budget_level="premium",
    )
    places = [make_place(f"beach-{index}") for index in range(6)]
    return plan_trip(trip_request, places)


def scheduled_place_names(itinerary) -> list[list[str]]:
    return [
        [activity.name for activity in day.activities if activity.kind == "place"]
        for day in itinerary.days
    ]


class FakeLlmResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": json.dumps(self.payload)}}]}


def test_itinerary_returns_when_llm_narration_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    itinerary = make_itinerary()
    template_narration = itinerary.summary.narration
    monkeypatch.setenv(LLM_KEY_ENV_VAR, "test-key")

    def timeout_post(*args, **kwargs):
        raise httpx.TimeoutException("llm took too long")

    monkeypatch.setattr("httpx.post", timeout_post)
    fallback = enrich_itinerary_narration(itinerary)

    assert fallback.summary.narration == template_narration
    assert scheduled_place_names(fallback) == scheduled_place_names(itinerary)
    assert config.LLM_FALLBACK_ASSUMPTION in fallback.assumptions


def test_llm_disabled_without_api_key_keeps_template_prose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    itinerary = make_itinerary()
    monkeypatch.delenv(LLM_KEY_ENV_VAR, raising=False)
    enriched = enrich_itinerary_narration(itinerary)
    assert enriched.summary.narration == itinerary.summary.narration
    assert scheduled_place_names(enriched) == scheduled_place_names(itinerary)


def test_llm_narration_applies_valid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    itinerary = make_itinerary()
    monkeypatch.setenv(LLM_KEY_ENV_VAR, "test-key")
    day_notes = [
        f"A slow morning wandering {', '.join(names)} — pure Goa."
        for names in scheduled_place_names(itinerary)
    ]
    payload = {"trip_summary": "Sun, sand and slow days.", "day_notes": day_notes}
    monkeypatch.setattr("httpx.post", lambda *a, **k: FakeLlmResponse(payload))

    enriched = enrich_itinerary_narration(itinerary)
    assert enriched.summary.narration is not None
    assert "Sun, sand and slow days." in enriched.summary.narration
    assert scheduled_place_names(enriched) == scheduled_place_names(itinerary)
    assert [a.place_id for d in enriched.days for a in d.activities] == [
        a.place_id for d in itinerary.days for a in d.activities
    ]


def test_llm_narration_rejects_response_that_drops_places(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    itinerary = make_itinerary()
    template_narration = itinerary.summary.narration
    monkeypatch.setenv(LLM_KEY_ENV_VAR, "test-key")
    payload = {
        "trip_summary": "A rushed rewrite.",
        "day_notes": ["Lovely day, trust me." for _ in itinerary.days],
    }
    monkeypatch.setattr("httpx.post", lambda *a, **k: FakeLlmResponse(payload))

    fallback = enrich_itinerary_narration(itinerary)
    assert fallback.summary.narration == template_narration
    assert scheduled_place_names(fallback) == scheduled_place_names(itinerary)
