# Wishtrip AI Engineering Internship — Implementation Plan (Phased)

> Build a full-stack prototype that turns a traveller's preferences into a practical,
> personalised, day-by-day itinerary. Decisions are made by deterministic planning code;
> the LLM only writes the narration.
>
> **Read every session:** `plan.md` (this file), `AGENTS.md` (conventions & boundaries),
> and the assignment PDF. Naming/style rules live in `AGENTS.md` §5 — this plan follows them.

---

## Phase overview

| Phase | Name | Output | Depends on | Est. |
|---|---|---|---|---|
| 0 | Scaffolding | Empty-but-running backend + frontend, config, contracts | — | ~0.5 day |
| 1 | Data foundation | `wishtrip.db` with 150–300 Goa POIs | 0 | ~2 days |
| 2 | Planner core | Deterministic itineraries from pure functions + passing tests | 0 (1 helpful) | ~2.5 days |
| 3 | API integration | `POST /itineraries` serving real itineraries end-to-end (curl-testable) | 1, 2 | ~0.5 day |
| 4 | LLM narration | Prose summaries layered on the structured plan, fail-open | 3 | ~0.5 day |
| 5 | Frontend | Usable app: form → itinerary view → map | 3 (4 helpful) | ~2 days |
| 6 | Hardening & submission | Tests green, README, personas, clean setup | 5 | ~1 day |

Rule: **a phase is done only when its exit check passes.** Do not start phase N+1
on an unverified phase N.

---

## Core idea / intuition (applies to all phases)

An itinerary is a **physically-feasible route through scored candidates**, not a list of
nice places. The planner therefore has two kinds of logic:

| Kind | What it decides | Examples |
|---|---|---|
| **Rules + scoring (~60%)** | What is *eligible* and *how good* | Budget filters, party-suitability filters, interest-weighted POI scores, pace budgets |
| **Optimization (~30%)** | What *fits where* and in *what order* | Clustering POIs into geographic days, sequencing stops to minimise travel time, dropping lowest-scored items when a day overflows |
| **LLM (~10%)** | Narration only | Per-day "why this suits you" prose, trip summary. Cannot add/remove/reorder anything |

Key invariants (hold in every phase):
- The app works fully **without the LLM** (structured itinerary always rendered; LLM failure degrades gracefully).
- Every unverified/synthetic attribute is **flagged as an assumption**, never presented as fact.
- Every activity in the output carries a **`why`** explaining its selection.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python + FastAPI** | Planning logic is array/graph manipulation; readable, testable, fast to build |
| Data layer | **SQLite** (via SQLAlchemy or raw SQL) | Zero-setup, satisfies "database or clearly defined data layer", easy to ship |
| Planner | Pure Python functions (no framework) | Testable and independent of the API layer (AGENTS.md §4) |
| LLM | OpenAI-compatible API call, abstracted behind an interface | Only for narration; swappable, mockable in tests |
| Frontend | **React + Vite** | Simple form + itinerary view |
| Map | **Leaflet + OpenStreetMap tiles** | Free, no API key needed |
| Tests | **pytest** | Focused tests on planning rules |

---

## Geo services strategy (decided — with justification)

**Decision: the app calls free geo APIs directly; MCP servers are used only as
development tooling inside ZCode, never shipped in the app.**

We evaluated the geo MCP ecosystem ([OpenStreetMap MCPs](https://mcpservers.org/servers/jagan-shanmugam/open-streetmap-mcp),
[Nominatim/Overpass MCP](https://github.com/cyanheads/nominatim-mcp-server),
[Valhalla MCP](https://mcpservers.org/servers/aatakansalar/valhalla-mcp),
[registry of 77+ geospatial MCPs](https://sparkgeo.com/blog/geospatial-mcp-servers-mapped-and-categorized/),
commercial ones like [Stadia Maps](https://stadiamaps.com/location-for-ai/),
[Geoapify](https://www.geoapify.com/mcp/) and [Mapbox](https://www.mapbox.com/blog/geoai-in-2026-four-predictions-on-agents-mcp-and-live-data)).
MCP is a protocol for **LLM agents to call tools**. Our planner is deterministic Python
running a fixed pipeline — it has no agent loop — so an MCP hop would add a process,
a failure mode, and an interview question ("why?") without adding capability. A plain
HTTP call is simpler, faster, easier to test, and easier to defend. This restraint is
itself part of the answer to the rubric's "alternatives considered".

**In the app (direct HTTP calls, all free/open):**

| Need | Service | Used for |
|---|---|---|
| POI discovery | **Overpass API** | Phase 1 — fetch Goa POIs (cached; AGENTS.md §8) |
| Geocoding | **Nominatim** | Resolve origin city / locate airport + zone anchors; requires only a User-Agent header |
| Routing / travel times | **Valhalla** (or OSRM) | Real drive/walk times + time-distance matrices. Valhalla also has built-in **TSP optimisation** — a candidate replacement for our hand-rolled 2-opt in `sequence.py` |
| Offline fallback | **haversine estimator** | Default travel-time source so tests, CI, and clean setups never need the network. Remote routing is a pluggable enhancement behind one interface, not a dependency |

**In ZCode during development (MCP, optional):** `open-streetmap-mcp`
(Nominatim + Overpass, zero-config) and `valhalla-mcp` — so the agent can
explore/curate the Goa POI set and prototype routing queries conversationally
before committing to `seed.py`.

**Explicitly rejected:** Google Maps / Mapbox / MapQuest / Stadia / Geoapify MCPs —
API keys + billing + vendor data-ownership terms for capabilities free open APIs
already cover; [Travel Assistant MCP](https://mcpservers.org/servers/skarlekar/mcp_travelassistant)
(flights/hotels) — out of scope, stays are indicative only. All named in the README
as alternatives considered.

---

Repo layout (matches AGENTS.md §3; file names per AGENTS.md §5):

```
wishtrip/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, POST /itineraries
│   │   ├── models.py          # Pydantic: TripRequest, Itinerary, DayPlan, ScheduledActivity
│   │   ├── planner/
│   │   │   ├── filter.py      # hard-constraint filtering
│   │   │   ├── score.py       # interest/traveller-type scoring
│   │   │   ├── cluster.py     # geographic day-grouping
│   │   │   ├── sequence.py    # within-day ordering (nearest-neighbour + 2-opt)
│   │   │   ├── budget.py      # pace/time budgeting, drop rules
│   │   │   ├── meals.py       # meal slot anchoring
│   │   │   └── narrate.py     # LLM narration (optional, fail-open)
│   │   ├── config.py          # PACE_BUDGETS, MEAL_ANCHOR_TIMES, category weight maps
│   │   └── db.py
│   ├── data/
│   │   ├── seed.py            # Overpass fetch + enrichment + load into SQLite
│   │   └── wishtrip.db
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/        # PreferenceForm.tsx, ItineraryTimeline.tsx, DayTabs.tsx, TripMap.tsx
│       ├── api/fetchItinerary.ts
│       └── hooks/
├── README.md
└── plan.md
```

---

## Phase 0 — Scaffolding (~0.5 day)

**Goal:** repo skeleton exists; both halves run hello-world; contracts are written down.

**Tasks:**
1. Init repo, `backend/` and `frontend/` as per the layout above; add `.gitignore`, README stub.
2. Backend: FastAPI app boots (`uvicorn`), `/health` endpoint, `config.py` with
   `PACE_BUDGETS`, `MEAL_ANCHOR_TIMES`, category weight maps, zone list.
3. `models.py`: write the **full Pydantic contracts now** — `TripRequest`, `Itinerary`,
   `DayPlan`, `ScheduledActivity` — exactly per §Contracts below. Planner and frontend
   both code against these from day one.
4. Frontend: Vite React app boots, renders a placeholder page.

**Exit check:** `uvicorn` serves `/health`; `npm run dev` shows the placeholder;
`TripRequest` JSON example validates in the OpenAPI docs.

---

## Phase 1 — Data foundation (~2 days)

**Goal:** a queryable Goa POI database with honest sourcing.

**Destination: Goa, India.** It natively covers every interest category the assignment
names — beaches, food, culture (Old Goa churches, forts), nature (spice farms, waterfalls),
wellness (yoga/ayurveda), adventure (water sports), nightlife — plus distinct zones
(North Goa, South Goa, Panaji, Old Goa) that make geographic day-clustering meaningful.
Jaipur is the backup choice (strong culture/food/markets, no beaches or water adventure).

**Tasks:**
1. Overpass fetch for the Goa bounding box (~14.9–15.8 N, 73.7–74.4 E); **cache raw
   responses** (rate limits — AGENTS.md §8).
2. Geocode the fixed anchors (Goa airport, zone centroids, origin-city lookup) via
   **Nominatim** (direct HTTP, User-Agent set) and store them as a small `anchors` table.
3. Map OSM tags → our categories; drop junk/ambiguous entries.
4. Enrich with synthetic attributes, each flagged `source: synthetic`:
   `visit_duration_minutes`, `price_level` (0–3, INR-aware), `suitability`
   (kids_ok, seniors_ok, nightlife, wellness, adventure), `why_visit`.
5. Parse `opening_hours` → weekly-schedule JSON; missing → `hours_unknown: true`.
6. Assign `zone` (north_goa | south_goa | panaji | old_goa | morjim_ashwem).
7. Write `seed.py` → `wishtrip.db` with the `places` schema below.

**Schema (`places` table):**
```
id, name, lat, lon, zone, category, subcategory,
visit_duration_minutes, price_level, rating,
opening_hours JSON, hours_unknown BOOL,
tags JSON (interests it satisfies), suitability JSON,
kids_ok BOOL, seniors_ok BOOL,
description, source JSON
```

**India-specific data rules:**
- Indicative costs in **INR** (meal ~₹300–1,500 by price_level; entry fees where known; flag estimates).
- **Monsoon (June–September):** strongly demote beaches/water sports; mark seasonal
  venues `seasonally_closed` — the month input must drive this.
- Alcohol/nightlife venues flagged for exclusion from family/seniors parties.

**Exit check:** DB opens in `sqlite3`; sanity queries work — counts per category and
per zone are balanced; no POI has an unflagged synthetic field; spot-check 10 famous
places for sane coordinates.

---

## Phase 2 — Planner core (~2.5 days)

**Goal:** a pure function `plan_trip(request, places) -> Itinerary` that produces real,
sensible itineraries with no API, DB, or network in the loop.

**Tasks (one module per step, pipeline order is fixed — AGENTS.md §4):**
1. **Filter** (`filter.py`) — budget tier → allowed price levels; party type exclusions
   (no nightlife for families/seniors); monsoon demotion + `seasonally_closed` drops;
   dietary restaurant filter (veg/vegan/jain/halal tags); mobility → accessibility preference.
2. **Score** (`score.py`) — interest → category weight vector; place score = weighted
   interest matches + rating bonus + traveller-type adjustments (+kids_ok for families,
   +seniors_ok for seniors). Output: ranked candidate pool per zone.
3. **Cluster into days** (`cluster.py`) — greedy geographic grouping (or k-means) so a
   day stays in one zone (North↔South is a real 1.5–2 hr crossing — never cross zones
   twice in a day). `nights` → `nights + 1` day slots; arrival/departure days lighter and
   within ~45 min of the airport. Day-trip POIs (Dudhsagar Falls) consume a full day.
4. **Sequence** (`sequence.py`) — nearest-neighbour from hotel/start, then **2-opt**
   improvement on total travel time. Travel times come from a **single pluggable
   `travel_time_estimator` interface**: default = haversine estimate (pure, offline,
   test-friendly); optional implementation = Valhalla matrix API (real drive/walk
   times). No planner step knows which implementation is active.
5. **Budget** (`budget.py` + `meals.py`) — pace → stops/day + active-hours budget;
   overflow drops lowest-scored items; anchor lunch (~13:00) and dinner (~19:30) at
   diet-compatible places.
6. **Explanations** — every selection records its `why`: interest match, travel minutes
   from previous stop, pace fit, party suitability, dietary compatibility.

**Tests (write alongside, names describe the rule):**
`test_easy_going_pace_limits_day_to_three_stops`, `test_day_never_crosses_zones_twice`,
`test_budget_request_excludes_premium_venues`, `test_family_request_excludes_nightlife_venues`,
`test_vegan_diet_filters_restaurants`, `test_monsoon_month_demotes_beaches_and_drops_seasonally_closed`,
`test_stop_not_scheduled_before_published_opening_time`, `test_day_trip_poi_occupies_full_day`.

**Exit check:** full pytest suite green; eyeball 3 printed itineraries (packed solo /
easy-going family / monsoon wellness couple) — each visibly different, geographically
coherent, no absurd timings.

---

## Phase 3 — API integration (~0.5 day)

**Goal:** `POST /itineraries` serves real itineraries; backend complete without LLM.

**Tasks:**
1. Wire `main.py` → planner: validate `TripRequest`, load places from SQLite, call
   `plan_trip`, return `Itinerary`.
2. Error handling: invalid inputs → 422 with clear messages; empty result pool
   (e.g., over-tight filters) → structured "no suitable places" response, not a crash.
3. Keep planner untouched — the API layer only loads data and delegates.

**Exit check:** `curl` with a real request returns a valid itinerary; FastAPI docs show
request/response schemas matching `models.py`; LLM is not involved anywhere yet.

---

## Phase 4 — LLM narration (~0.5 day)

**Goal:** traveller-facing prose layered on the finished structured plan.

**Tasks:**
1. `narrate.py` behind an interface: input = final `Itinerary`, output = per-day prose +
   trip summary. One OpenAI-compatible call; prompt includes the structured plan only.
2. Validation: LLM output may not add/remove/reorder places — parse back and verify.
3. **Fail-open:** on any LLM error/timeout, return the structured itinerary with
   template-generated text. Env-var driven; missing key = templates only.

**Test:** `test_itinerary_returns_when_llm_narration_fails`.

**Exit check:** kill the LLM key → endpoint still returns complete itineraries with
template prose; with the key set → natural summaries, same structure.

---

## Phase 5 — Frontend (~2 days)

**Goal:** a stranger can use the app without instructions.

**Tasks:**
1. `PreferenceForm.tsx`: 6 required inputs + optional dietary/mobility/transport;
   client-side validation mirroring `TripRequest`.
2. `api/fetchItinerary.ts`: single typed fetch against the contract.
3. `ItineraryTimeline.tsx` + `DayTabs.tsx`: ordered activities with times, travel legs
   ("25 min drive"), indicative costs in ₹, per-activity **why** note.
4. `TripMap.tsx`: Leaflet, numbered markers per day showing route order.
5. Assumption flags rendered honestly: "hours not verified", "cost estimated",
   "may be closed in monsoon".

**Exit check:** form submit → full itinerary view; narration off → template text still
renders fine; no console errors; map markers match the day's order.

---

## Phase 6 — Hardening & submission (~1 day)

**Goal:** submission-ready: clean setup, documented, demonstrably personalised.

**Tasks:**
1. Fill any remaining test gaps; full suite green.
2. Clean setup: one documented command (or `docker compose up`) from a fresh clone.
3. README: architecture, tech choices, data model & sources, planning approach,
   constraints, assumptions, limitations (per §Limitations below).
4. Record 3 demo personas with outputs (must be visibly different):
   1. **Packed-budget solo backpacker**, 3 nights, November — hostels, beaches, water sports, nightlife
   2. **Easy-going vegetarian family**, two kids, 5 nights, December — North-Goa beaches,
      spice farm, Old Goa churches, kid-ok dining
   3. **Balanced wellness couple**, 4 nights, July (monsoon) — ayurveda/yoga, indoor
      heritage, waterfalls, cafés — proving seasonality handling
5. Walk-through notes: alternatives considered, what we'd improve with more time:
   - **Valhalla upgrade** — swap haversine for real routing everywhere (matrix API for
     sequencing, isochrones for arrival-day radius), or replace 2-opt with Valhalla's
     built-in TSP optimisation. Designed for via the estimator interface (Phase 2).
   - More destinations via the same pipeline; learned scoring weights from feedback.
   - Named-alternatives section: geo MCP servers (why we kept them dev-only) and
     commercial platforms (why rejected) — see Geo services strategy above.

**Exit check:** assignment submission checklist below, all boxes ticked.

---

## Contracts

Request (`POST /itineraries`):

```json
{
  "destination": "goa",
  "origin_city": "delhi",
  "start_date": "2026-11-12",
  "nights": 4,
  "traveller_type": "family",
  "party": {"adults": 2, "children": 2},
  "interests": ["beaches", "food", "culture"],
  "pace": "balanced",
  "budget_level": "mid"
}
```

- `start_date` may be a full date or a month name; month is enough (drives seasonality).
- Optional: dietary preferences (`veg`/`vegan`/`jain`/`halal`), mobility needs,
  transport preference (scooter rental vs private cab).

Response: structured `Itinerary` — list of `DayPlan`, each with ordered
`ScheduledActivity` items (place ref or meal/transfer, `start_time`, `end_time`,
`lat`/`lon` for the frontend map, travel leg with `travel_minutes` + mode,
`indicative_cost_inr`, and a `why` string).

---

## Limitations to state honestly (feed into README in Phase 6)

- Single destination (Goa) by design — depth over breadth.
- POI data from OSM; durations/prices/suitability are synthetic estimates, flagged per-field.
- Travel times default to haversine-distance estimates (offline-safe); the Valhalla
  routing implementation is optional and may not be active in the submitted demo.
- Opening hours only as good as OSM; unverified hours surfaced in the UI.
- No real hotel/booking data — "stays" are indicative only.

---

## Submission checklist

- [ ] Working prototype (clean setup: one documented command or `docker compose up`)
- [ ] Repo with setup instructions
- [ ] README: architecture, tech choices, data model & sources, planning approach,
      constraints, assumptions, limitations
- [ ] 3 example trip requests with visibly different outputs
- [ ] Tests passing
- [ ] Can explain every choice + what we'd improve with more time
