# Wishtrip Trip Planner — Goa Itinerary Prototype

A full-stack prototype that turns traveller preferences into a personalised,
day-by-day Goa itinerary. Built for the Wishtrip AI Engineering Internship
take-home assignment.

**The core idea:** an itinerary is a physically-feasible route through scored
candidates — not a list of nice places. A deterministic planner (~90% of the
decisions: rules, scoring, geographic clustering, route sequencing, time
budgeting) makes every planning choice; the LLM (~10%) only writes narration
over the finished plan, and the app works fully with the LLM down.

## Quickstart (clean setup)

Requires conda (backend) and Node 18+ (frontend).

```bash
# 1. Backend environment
conda env create -f backend/environment.yml
conda activate wishtrip

# 2. Database (ships seeded; rebuild only if you want fresh OSM data)
python backend/data/seed.py   # uses cached Overpass response, no network needed

# 3. Backend API (http://localhost:8000, docs at /docs)
python -m uvicorn app.main:app --app-dir backend

# 4. Frontend (http://localhost:5173, proxies /itineraries to the backend)
cd frontend && npm install && npm run dev
```

Optional LLM narration: `export WISHTRIP_LLM_API_KEY=…`
(optional `WISHTRIP_LLM_BASE_URL`, `WISHTRIP_LLM_MODEL`, default OpenAI-compatible).
Without a key the API returns complete itineraries with template prose.

Verify: `pytest` from `backend/` (23 tests), `npm run typecheck && npm run build`
from `frontend/`.

## Architecture

```
browser (React + Vite, Leaflet/OSM)
  │  POST /itineraries  (TripRequest JSON)
  ▼
FastAPI (backend/app/main.py) — loads SQLite places, delegates, stamps request_id
  │  plan_trip(request, places) -> Itinerary   (pure, no DB/network)
  ▼
planner/filter.py → score.py → cluster.py → sequence.py → budget.py + meals.py
  │  every activity gets a `why`; assumptions collected throughout
  ▼
planner/narrate.py — LLM prose over the final plan, fail-open to templates
```

Boundaries that are load-bearing, not decorative:

- All planning logic lives in `backend/app/planner/` as **pure functions** —
  the FastAPI layer only loads data and the DB layer only stores it.
- Pipeline order is fixed: filter → score → cluster → sequence → pace-budget →
  explanations. Downstream steps never re-decide upstream ones.
- **The LLM never makes planning decisions** (no adding/removing/reordering).
  Its prose is validated (must mention every scheduled stop by name) and any
  failure falls back to template text.
- The frontend renders only the structured response; it works with narration
  on or off.

## Technology choices

| Layer | Choice | Why |
|---|---|---|
| Backend | Python + FastAPI | Planning is array/graph manipulation; Pydantic contracts double as docs |
| Data | SQLite via SQLAlchemy | Zero-setup, committable `.db`, satisfies "database or data layer" |
| Planner | Pure Python, no framework | Testable without DB/network; 23 focused tests |
| LLM | One OpenAI-compatible call behind an interface | Narration only; swappable, mockable, env-var driven |
| Frontend | React + Vite + TypeScript | Typed mirror of the Pydantic contract; single fetch module |
| Map | Leaflet + OpenStreetMap tiles | Free, no API key; numbered markers in route order |
| Geo data | Overpass API (cached) + Nominatim-style anchors | Free/open; no vendor keys, billing, or data-ownership terms |

## Data model & sources

**Destination: Goa, India** — one destination in depth: beaches, food, culture
(Old Goa churches, forts), nature (spice farms, waterfalls), wellness,
adventure, nightlife, plus real zones (North/South Goa, Panaji, Old Goa,
Morjim-Ashwem) that make geographic day-clustering meaningful.

- **POIs:** OpenStreetMap via the Overpass API (`backend/data/seed.py`; raw
  response cached in `backend/data/cache/` for rate-limit politeness), mapped
  from OSM tags to 10 categories, plus 27 curated famous places filling gaps
  OSM under-represents (wellness, adventure, flagship landmarks).
- **Enrichment is honestly flagged:** durations, price levels (INR-aware),
  ratings, suitability and opening-hours parsing are synthetic estimates —
  every such field is flagged (`cost_is_estimate`, `hours_unverified`) and
  surfaced in the UI as an assumption, never stated as fact.
- **`places` table:** id, name, lat/lon, zone, category/subcategory, duration,
  price_level (0–3), rating, opening_hours JSON, hours_unknown, tags,
  suitability, kids_ok/seniors_ok, seasonally_closed_months, description, source.
- **India-specific rules:** monsoon months (Jun–Sep) demote beaches/water
  activities and close seasonal venues; nightlife excluded for families/seniors.

Current DB: 396 places (`backend/data/wishtrip.db` is committed; re-run
`seed.py` to rebuild).

## Planning approach

1. **Filter** (hard constraints): budget tier → price levels; party exclusions
   (nightlife needs `kids_ok`, adventure needs `seniors_ok`); seasonal closure;
   restaurant diet filter (explicit tags, else meat-specialty names only);
   wheelchair skips treks/water outings.
2. **Score**: interest→category weights + rating bonus + party bonus −
   monsoon penalty. Ranked pool per zone.
3. **Cluster into days**: `nights + 1` single-zone days (North↔South is a real
   1.5–2 hr crossing); airport-nearest zones on arrival/departure days; full-day
   excursions (e.g. Dudhsagar) occupy a whole middle day **only if they match
   an interest**; categories interleaved so days mix food/beach/heritage.
4. **Sequence**: nearest-neighbour from the day start, then 2-opt on total
   travel time — through a pluggable estimator (haversine default, offline and
   test-friendly; Valhalla matrices can drop in).
5. **Pace-budget + meals**: pace → stops/day + active hours (easy ≈3, balanced
   ≈4–5, packed ≈6; edge days lighter); overflow drops lowest-scored stops from
   over-represented categories first; lunch ~13:00 and dinner ~19:00 anchored
   at diet-compatible in-zone venues.
6. **Explanations**: every activity carries a `why` derived from the decision
   (interest match, rating, party/diet fit, travel minutes from previous stop).

## Example trips (inputs → visibly different outputs)

Full request+response JSON in `examples/` (template narration — no LLM key set):

1. **`persona-1-packed-solo-backpacker`** — 3 nights, November, beaches +
   adventure + nightlife, budget: 4 fast days across Panaji/North/South/Old
   Goa, markets + forts + viewpoints, generic-meal honesty (no budget-tier
   restaurants in the data).
2. **`persona-2-easygoing-veg-family`** — 5 nights, December, 2 kids, veg:
   ≤3 stops/day, zero nightlife, zero waterfall treks (no interest match),
   Basilica + beaches + veg venues — including one OSM-asserted veg option
   at a fish-specialty kitchen (explicit diet tags win over name keywords;
   the diet assumption says to confirm with the kitchen).
3. **`persona-3-balanced-wellness-couple-monsoon`** — 4 nights, July:
   Devaaya Ayurveda Retreat surfaces, waterfall day-trip (nature match),
   beaches demoted, monsoon assumptions flagged.

## Constraints & assumptions

- Single destination (Goa) by design — depth over breadth.
- Travel times are haversine estimates at modest Goa road speeds, not live
  routing; first/last-mile and traffic are not modelled.
- Opening hours are only as good as OSM; unverified hours are flagged per
  activity ("hours not verified").
- Diet/wheelchair suitability is inferred, not verified — the itinerary says so.
- "Stays" are out of scope: no hotel data, arrival day simply starts late near
  the airport.
- The Goa airport anchor is a constant in `config.py`, not a Nominatim
  `anchors` table as plan.md Phase 1 sketched — geocoding origin cities was
  cut as low-value for the prototype (arrival-day logic only needs the
  airport).

## Known limitations

- 18 minor waterfalls share the `day_trip` category, so long trips can spend
  two full days on falls; only Dudhsagar-scale venues truly deserve it.
- 80 food venues can crowd top scores for food-heavy requests (mitigated by
  the variety interleave + diversity trim, not eliminated).
- The vegan/vegetarian filter leans on explicit OSM diet tags plus obvious
  meat-specialty names; mixed-menu kitchens pass with a stated assumption.
- Frontend has no automated tests (backend carries 23); map popups assume
  coordinates, which generic meals lack (they are skipped on the map).

## Alternatives considered

- **Geo MCP servers** (open-streetmap-mcp, valhalla-mcp): useful as *dev
  tooling* for exploring POIs/routing, but our planner is deterministic code
  with no agent loop — an MCP hop would add a process and failure mode for no
  capability gain. Plain HTTP + a pluggable estimator interface instead.
- **Commercial maps APIs** (Google/Mapbox/Geoapify/Stadia): keys + billing for
  capabilities free open APIs already cover at prototype fidelity.
- **LLM-first planning** (prompt wrapping): rejected — untestable constraint
  handling, silent hallucinations, no "why" traceability. The LLM writes
  postcards, not plans.

## What we'd improve with more time

- **Valhalla upgrade**: real drive/walk matrices behind the existing estimator
  interface (or Valhalla's TSP replacing hand-rolled 2-opt); isochrones for
  the arrival-day radius.
- More destinations through the same pipeline; learned scoring weights from
  traveller feedback.
- Structured opening-hours parsing from OSM strings; verified diet/access
  attributes; frontend tests for the form→timeline→map flow.

## Project map

```
wishtrip/
├── backend/app/main.py · models.py · config.py · db.py
├── backend/app/planner/ (filter score cluster sequence budget meals
│                         travel_time opening_hours explain narrate
│                         itinerary_builder)
├── backend/tests/ (23 tests) · backend/data/seed.py · backend/data/wishtrip.db
├── backend/environment.yml · backend/requirements.txt
├── frontend/src/{api,components,hooks} · plan.md · AGENTS.md · examples/
```
