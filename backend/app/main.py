"""FastAPI entrypoint: POST /itineraries + /health.

Phase 3: the endpoint loads places from SQLite and delegates to the pure
planner. No planning logic lives here — the API layer only loads data,
stamps the response id, and maps planner failures to HTTP statuses.
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db, load_all_places
from .models import ErrorResponse, Itinerary, TripRequest
from .planner.itinerary_builder import NoSuitablePlacesError, plan_trip
from .planner.narrate import enrich_itinerary_narration


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Wishtrip Trip Planner",
    description="Turns traveller preferences into a personalised day-by-day itinerary.",
    version="0.1.0",
    lifespan=lifespan,
)

# Take-home prototype: the Vite dev server runs on another port, so the API
# allows cross-origin calls (tighten to explicit origins before production).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health_check() -> dict:
    place_count = len(load_all_places())
    return {"status": "ok", "places_loaded": place_count}


@app.post(
    "/itineraries",
    response_model=Itinerary,
    responses={422: {"model": ErrorResponse}},
)
def build_itinerary(trip_request: TripRequest) -> Itinerary:
    """Validate the trip request, plan against SQLite places, return the itinerary."""
    places = load_all_places()
    try:
        itinerary = plan_trip(trip_request, places)
    except NoSuitablePlacesError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    itinerary.request_id = uuid.uuid4().hex
    # Fail-open: template prose stays when the LLM is down or unconfigured.
    return enrich_itinerary_narration(itinerary)
