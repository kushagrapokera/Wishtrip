"""Phase 3 API tests: POST /itineraries serves real itineraries end-to-end.

The planner itself is covered in tests/test_planner_phase2.py; these tests
prove the HTTP layer loads data, delegates, stamps ids, and maps the empty
pool to a structured error instead of crashing.
"""

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


@pytest.fixture
def api_client() -> TestClient:
    with TestClient(app) as client:
        yield client


def balanced_request_payload() -> dict:
    return {
        "origin_city": "delhi",
        "start_month": 12,
        "nights": 4,
        "traveller_type": "family",
        "party": {"adults": 2, "children": 2},
        "interests": ["beaches", "food", "culture"],
        "pace": "balanced",
        "budget_level": "mid",
    }


def test_post_itineraries_returns_valid_itinerary(api_client: TestClient) -> None:
    response = api_client.post("/itineraries", json=balanced_request_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert body["summary"]["total_days"] == 5
    assert len(body["days"]) == 5
    assert body["summary"]["narration"]
    for day in body["days"]:
        assert day["activities"]
        for activity in day["activities"]:
            assert activity["why"]
            assert activity["start_time"] < activity["end_time"]
        mapped_places = [
            activity for activity in day["activities"] if activity["place_id"]
        ]
        assert mapped_places
        for activity in mapped_places:
            assert activity["lat"] is not None
            assert activity["lon"] is not None


def test_post_itineraries_empty_pool_returns_structured_error(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module, "load_all_places", lambda: [])
    response = api_client.post("/itineraries", json=balanced_request_payload())
    assert response.status_code == 422
    assert "no suitable places" in response.json()["detail"]


def test_post_itineraries_invalid_request_returns_422(api_client: TestClient) -> None:
    response = api_client.post("/itineraries", json={"origin_city": "delhi"})
    assert response.status_code == 422
