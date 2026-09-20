"""Central configuration for the Wishtrip planner.

All planner thresholds live here so no rule is duplicated in code (AGENTS.md §5).
"""

# --- Destination -----------------------------------------------------------

SUPPORTED_DESTINATIONS = {"goa"}

# Goa bounding box (N, S, E, W) used by the Overpass fetch in data/seed.py
GOA_BBOX_SOUTH = 14.9
GOA_BBOX_WEST = 73.7
GOA_BBOX_NORTH = 15.8
GOA_BBOX_EAST = 74.4

GOA_ZONES = [
    "north_goa",
    "south_goa",
    "panaji",
    "old_goa",
    "morjim_ashwem",
]

# --- Seasonality -----------------------------------------------------------

# Monsoon months in Goa (1-based): outdoor/water POIs are demoted, seasonal venues closed
MONSOON_MONTHS = {6, 7, 8, 9}

# --- Pace budgets ----------------------------------------------------------

# pace -> (max activity stops per day, max active hours per day excluding meals/sleep)
PACE_BUDGETS = {
    "easy_going": {"max_stops_per_day": 3, "max_active_hours": 6.0},
    "balanced": {"max_stops_per_day": 5, "max_active_hours": 8.5},
    "packed": {"max_stops_per_day": 6, "max_active_hours": 11.0},
}

# --- Meal anchors ----------------------------------------------------------

# Meal slot -> (anchor start hour, duration minutes)
MEAL_ANCHOR_TIMES = {
    "lunch": {"start_hour": 13, "duration_minutes": 60},
    "dinner": {"start_hour": 19, "duration_minutes": 75},
}

# --- Budget tiers ----------------------------------------------------------

# budget_level -> allowed price_level values (0 free, 1 budget, 2 mid, 3 premium)
ALLOWED_PRICE_LEVELS = {
    "budget": {0, 1},
    "mid": {0, 1, 2},
    "premium": {0, 1, 2, 3},
}

# --- Interest scoring ------------------------------------------------------

# interest -> category weights (a place whose category matches scores higher)
INTEREST_CATEGORY_WEIGHTS = {
    "beaches": {"beach": 1.0, "adventure": 0.3, "food": 0.1},
    "food": {"food": 1.0, "market": 0.6, "nightlife": 0.3},
    "culture": {"museum_heritage": 1.0, "fort_landmark": 1.0, "market": 0.3},
    "nature": {"park_nature": 1.0, "beach": 0.4, "day_trip": 0.6},
    "wellness": {"wellness_spa": 1.0, "beach": 0.3, "park_nature": 0.3},
    "adventure": {"adventure": 1.0, "day_trip": 0.5, "park_nature": 0.3},
    "nightlife": {"nightlife": 1.0, "food": 0.3},
}

RATING_BONUS_SCALE = 1.0  # max bonus added for a top-rated place

# --- Traveller-type scoring adjustments --------------------------------------

# Bonus added when a place's suitability matches the party (score.py)
KIDS_OK_BONUS = 0.3
SENIORS_OK_BONUS = 0.3
FRIENDS_NIGHTLIFE_BONUS = 0.3

# Score penalty for outdoor categories during monsoon (score.py demotes,
# filter.py drops seasonally closed venues outright)
MONSOON_DEMOTED_CATEGORIES = {"beach", "adventure"}
MONSOON_DEMOTION_PENALTY = 0.6

# --- Day scheduling ----------------------------------------------------------

DAY_START_HOUR = 9  # middle days open the schedule at 09:00
ARRIVAL_DAY_START_HOUR = 11  # day 1 starts later (travel into Goa)
DAY_END_HOUR = 21  # nothing is scheduled to end after 21:00

# Arrival and departure days are lighter: fewer stops, fewer active hours
EDGE_DAY_STOP_REDUCTION = 1
EDGE_DAY_HOURS_FRACTION = 0.6

# A single venue that consumes most of a day (Dudhsagar Falls); the day
# still fits up to two light nearby stops plus dinner afterwards
DAY_TRIP_CATEGORY = "day_trip"
DAY_TRIP_EXTRA_STOPS = 2
DAY_TRIP_EXTRA_MAX_DURATION_MINUTES = 90

# Sightseeing days fill a long idle run-up to dinner with nearby light
# stops; whatever long gap remains becomes an explicit rest block
AFTERNOON_FILL_MAX_STOPS = 2
AFTERNOON_FILL_MAX_DURATION_MINUTES = 90
REST_MIN_GAP_MINUTES = 120

# Fallback opening window assumed when OSM hours are unknown; the activity
# is still flagged hours_unverified so the UI states the assumption
DEFAULT_OPEN_HOUR = 9
DEFAULT_CLOSE_HOUR = 21

# --- Travel-time estimation --------------------------------------------------

# Below this distance the leg is a walk, above it a drive (Goa road speeds
# are modest; the overhead covers parking / finding the lane)
WALK_DISTANCE_KM_THRESHOLD = 1.0
WALK_SPEED_KMH = 4.5
DRIVE_SPEED_KMH = 28.0
TRAVEL_OVERHEAD_MINUTES = 5

# Goa (Dabolim) airport anchor: arrival/departure days prefer places near it
GOA_AIRPORT_LAT = 15.3808
GOA_AIRPORT_LON = 73.8314

# --- Indicative costs (INR, always flagged cost_is_estimate) ------------------

# Sightseeing spend by price_level (0 free, 1 budget, 2 mid, 3 premium)
INDICATIVE_COST_INR_BY_PRICE_LEVEL = {0: 0, 1: 250, 2: 700, 3: 1500}
# Meal spend by price_level (plan.md: meals ~Rs.300-1,500)
MEAL_COST_INR_BY_PRICE_LEVEL = {0: 200, 1: 400, 2: 800, 3: 1500}

# Group-cost rule: base costs above are per adult; children count as a
# fraction (no verified child-price data, so the factor is an assumption).
CHILD_COST_FRACTION = 0.5

# --- Dietary filtering ---------------------------------------------------------

# Diet markers honoured when a place carries explicit dietary_tags. A vegan
# venue also serves veg/jain/halal travellers; veg/vegan food is halal by
# default (no meat), so halal accepts those tags too. Jain accepts veg/vegan
# kitchens as candidates because OSM Goa carries no jain signal at all —
# excluding every explicitly-veg restaurant for jain travellers would be
# worse than keeping them with the "ask the kitchen" assumption downstream.
DIET_ACCEPTED_TAGS = {
    "veg": {"veg", "vegan", "jain"},
    "vegan": {"vegan"},
    "jain": {"jain", "veg", "vegan"},
    "halal": {"halal", "veg", "vegan", "jain"},
}

# Fallback when a restaurant carries no diet tags: only names that advertise
# a meat specialty outright (Goan thalis serve both, so they are kept and the
# diet assumption is surfaced instead of silently filtering them out)
NON_VEG_SPECIALTY_KEYWORDS = (
    "seafood",
    "steakhouse",
    "steak house",
    "fish fry",
    "fish hut",
    "prawn",
    "crab",
    "bbq",
    "barbecue",
    "kebab",
    "butcher",
)
HARAM_KEYWORDS = ("pork", "bacon", "ham", "lard")

# Human-readable zone labels for day themes
ZONE_LABELS = {
    "north_goa": "North Goa",
    "south_goa": "South Goa",
    "panaji": "Panaji",
    "old_goa": "Old Goa",
    "morjim_ashwem": "Morjim-Ashwem",
}

# --- LLM narration (Phase 4; templates only when the key is missing) ----------

# Env vars drive the narration layer; no key means template prose, never an error
LLM_API_KEY_ENV_VAR = "WISHTRIP_LLM_API_KEY"
LLM_BASE_URL_ENV_VAR = "WISHTRIP_LLM_BASE_URL"
LLM_MODEL_ENV_VAR = "WISHTRIP_LLM_MODEL"
LLM_DEFAULT_BASE_URL = "https://api.openai.com/v1"
LLM_DEFAULT_MODEL = "gpt-4o-mini"
LLM_TIMEOUT_SECONDS = 20
LLM_MAX_TOKENS = 600
LLM_TEMPERATURE = 0.7
LLM_MAX_NARRATION_CHARS = 4000

# Surfaced in the itinerary when template prose stands in for the LLM
LLM_FALLBACK_ASSUMPTION = (
    "LLM narration unavailable — showing template prose "
    "(set WISHTRIP_LLM_API_KEY for natural summaries)"
)
