# AGENTS.md — Wishtrip Trip Planner

## 1. Files to read EVERY session (before writing any code)

| File | Why |
|---|---|
| `plan.md` | The full implementation plan — architecture, planner pipeline, contracts, milestones. Never deviate from it without updating it first. |
| `Wishtrip AI Engineering Internship Assignment - wishtrip-ai-engineering-intern-assignment.pdf` | The original assignment brief — requirements, evaluation criteria, submission rules. |
| `AGENTS.md` (this file) | Coding conventions and architecture boundaries for this repo. |

Do not propose or implement architectural changes that contradict `plan.md`;
if a change is genuinely needed, update `plan.md` first, then the code.

## 2. Purpose

Take-home prototype for the Wishtrip AI Engineering Internship: a full-stack web app
that converts traveller preferences into a personalised, day-by-day itinerary.

## 3. Planned stack & layout

- **Backend:** Python + FastAPI (`backend/app/`), SQLite at `backend/data/wishtrip.db`
  (seeded by `backend/data/seed.py` from OpenStreetMap Overpass API + clearly-flagged synthetic enrichment).
- **Frontend:** React + Vite (`frontend/`), Leaflet + OSM tiles for the map (no map API keys).
- **Destination:** single destination — Goa, India — by design (depth over breadth, per assignment rules).

## 4. Architecture boundaries (important)

- All planning logic lives in `backend/app/planner/` as **pure, testable functions**,
  independent of the FastAPI layer and the database.
- Planner pipeline order is fixed: filter → score → cluster days → sequence stops →
  pace-budget → explanations. Do not merge steps or let downstream steps re-decide upstream ones.
- **The LLM never makes planning decisions.** It only writes narration from an already
  final structured itinerary, behind a fail-open interface (app must work fully with the LLM down).
- Frontend consumes only the structured API response; it must render without the narration layer.

## 5. Naming conventions (mandatory — code must read like Java: self-explanatory, easy to debug)

The goal: anyone opening a file for the first time should understand what it does
without reading its body. No single-letter names, no cryptic abbreviations, no "clever" code.

**Files & folders**
- `snake_case` everywhere in backend (`itinerary_builder.py`, `place_repository.py`).
- Folder names are singular nouns describing content: `planner/`, `models/`, `tests/`.
- One responsibility per file; the filename says what that responsibility is.
- React components: `PascalCase.tsx` named after what renders on screen (`ItineraryTimeline.tsx`,
  `PreferenceForm.tsx`); hooks `usePaceBudget.ts`; utilities `paceUtils.ts` not `utils.ts` junk-drawers.

**Functions**
- Backend: `snake_case`, verb-first, states what it returns or does —
  `filter_by_budget_level()`, `score_place_for_traveller()`, `build_day_sequence()`, `calculate_travel_minutes()`.
- Frontend: `camelCase` handlers as `handle<Event>` (`handleFormSubmit`), fetchers as `fetch<Thing>`
  (`fetchItinerary`), components render, never compute planning logic.
- Booleans read as predicates: `is_wheelchair_accessible`, `has_opening_hours`, `should_drop_activity`.
- No function over ~40 lines without a reason; extract a well-named helper instead of nesting.

**Variables & constants**
- Descriptive nouns with units where relevant: `visit_duration_minutes`, `max_walk_distance_km`,
  `travel_time_buffer_minutes` — never `d`, `tmp`, `data2`.
- Constants in `UPPER_SNAKE_CASE`, grouped in one config module: `PACE_BUDGETS`, `MEAL_ANCHOR_TIMES`.
- Reuse over duplication: before writing any constant, helper, or query, check whether one already
  exists. Shared logic goes in the dedicated module, never copy-pasted between files.

**Pydantic models / API shapes**
- Model names are nouns matching the domain: `TripRequest`, `Itinerary`, `DayPlan`, `ScheduledActivity`.
- Field names mirror the contract in plan.md §4 exactly — the API response and the docs must never drift.

**Comments**
- Comment only constraints the code cannot express (e.g., why a threshold is what it is),
  never narrate what the next line does.

## 6. Domain rules

- Every itinerary activity must carry a `why` explanation derived from the planning decision.
- Any synthetic/unverified data attribute (duration, price, opening hours) must be
  flagged at the field level and surfaced in the UI as an assumption, never stated as fact.
- Request/response contracts: `POST /itineraries` — see plan.md §4 for the exact Pydantic shapes.
- Pace budgets: easy_going ≈ 3 stops/day, balanced ≈ 4–5, packed ≈ 6 — centralised in one config module.

## 7. Testing

- pytest for planner rules (backend/tests/): pace budgets, no cross-city day zigzags,
  budget filtering, party-suitability exclusion, opening-hours conflicts, LLM-failure fallback.
- Planner functions must stay pure so tests need no DB or network.
- Test names describe the rule under test: `test_packed_pace_allows_six_stops_per_day`.

## 8. Gotchas

- Do not use any Wishtrip private code, APIs, or datasets (assignment rule).
- OSM Overpass fetches are rate-limited — seed script should cache raw responses.
