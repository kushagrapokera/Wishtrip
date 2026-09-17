"""Smoke tests for the Phase 0 contract: TripRequest validation and /health.

NOTE: the Phase 0 POST /itineraries 501 stub was replaced by the real planner
in Phase 3 — end-to-end API tests live in tests/test_api_itineraries.py.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import TripRequest


@pytest.fixture
def api_client() -> TestClient:
    with TestClient(app) as client:
        yield client


def test_health_endpoint_reports_ok(api_client: TestClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["places_loaded"], int)


def test_valid_trip_request_passes_validation() -> None:
    trip = TripRequest(
        origin_city="delhi",
        start_month=12,
        nights=4,
        traveller_type="family",
        party={"adults": 2, "children": 2},
        interests=["beaches", "food"],
        pace="balanced",
        budget_level="mid",
    )
    assert trip.travel_month == 12


def test_trip_request_requires_month_or_date() -> None:
    with pytest.raises(ValidationError):
        TripRequest(
            origin_city="delhi",
            nights=4,
            traveller_type="solo",
            party={"adults": 1},
            interests=["food"],
            pace="packed",
            budget_level="budget",
        )

