"""Seed the Wishtrip SQLite database with Goa POIs (plan.md Phase 1).

Pipeline:
  1. Fetch OSM POIs via the Overpass API (raw responses cached under data/cache/).
  2. Map OSM tags to our category scheme.
  3. Enrich with clearly-flagged synthetic attributes (durations, price levels,
     suitability) — nothing synthetic is ever presented as OSM-sourced.
  4. Add a small curated list of famous Goa places to fill categories OSM
     under-represents (wellness, adventure) — flagged `curated`.
  5. Deduplicate and load into SQLite.

Run from the backend directory:
    ~/miniconda3/envs/wishtrip/bin/python data/seed.py
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import config  # noqa: E402
from app.db import Place, init_db  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent / "cache"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
REQUEST_USER_AGENT = "wishtrip-prototype/0.1 (internship take-home assignment)"

OVERPASS_QUERY = f"""
[out:json][timeout:180];
(
  nwr["natural"="beach"]({config.GOA_BBOX_SOUTH},{config.GOA_BBOX_WEST},{config.GOA_BBOX_NORTH},{config.GOA_BBOX_EAST});
  nwr["tourism"~"^(museum|attraction|viewpoint|gallery|zoo|theme_park|artwork|spa_resort)$"]({config.GOA_BBOX_SOUTH},{config.GOA_BBOX_WEST},{config.GOA_BBOX_NORTH},{config.GOA_BBOX_EAST});
  nwr["historic"~"^(fort|castle|monument|memorial|ruins|archaeological_site)$"]({config.GOA_BBOX_SOUTH},{config.GOA_BBOX_WEST},{config.GOA_BBOX_NORTH},{config.GOA_BBOX_EAST});
  nwr["amenity"~"^(restaurant|cafe|fast_food|bar|pub|nightclub|marketplace|place_of_worship)$"]({config.GOA_BBOX_SOUTH},{config.GOA_BBOX_WEST},{config.GOA_BBOX_NORTH},{config.GOA_BBOX_EAST});
  nwr["leisure"~"^(park|garden|nature_reserve|water_park)$"]({config.GOA_BBOX_SOUTH},{config.GOA_BBOX_WEST},{config.GOA_BBOX_NORTH},{config.GOA_BBOX_EAST});
  nwr["waterway"="waterfall"]({config.GOA_BBOX_SOUTH},{config.GOA_BBOX_WEST},{config.GOA_BBOX_NORTH},{config.GOA_BBOX_EAST});
  nwr["sport"~"^(scuba_diving|surfing|kitesurfing|paragliding)$"]({config.GOA_BBOX_SOUTH},{config.GOA_BBOX_WEST},{config.GOA_BBOX_NORTH},{config.GOA_BBOX_EAST});
  nwr["shop"="scuba_diving"]({config.GOA_BBOX_SOUTH},{config.GOA_BBOX_WEST},{config.GOA_BBOX_NORTH},{config.GOA_BBOX_EAST});
);
out center tags;
"""

MONSOON_MONTHS = [6, 7, 8, 9]

# category -> (visit duration mins, price level, why_visit template)
CATEGORY_DEFAULTS = {
    "beach": (120, 0, "A Goan beach — swimming, sunsets and shack dining."),
    "museum_heritage": (90, 1, "Heritage site that carries Goa's Portuguese-era story."),
    "fort_landmark": (75, 1, "Historic fort or landmark with wide views and photo stops."),
    "park_nature": (90, 0, "Green space for an unhurried nature break."),
    "food": (60, 2, "A chance to taste Goan cuisine."),
    "market": (60, 0, "Local market — souvenirs, spices and street energy."),
    "nightlife": (90, 2, "One of Goa's well-known evening spots."),
    "wellness_spa": (90, 3, "Wellness and recovery — yoga, ayurveda or spa time."),
    "adventure": (120, 2, "Active, outdoor fun on or around the water."),
    "day_trip": (360, 2, "A full-day excursion away from the coast."),
}

# Cap how many places we keep per category (quality over breadth; plan.md targets
# ~150-300 usable POIs). Within a category, Wikipedia-linked OSM elements and
# curated entries are kept first, then highest pseudo-rating.
CATEGORY_CAPS = {
    "food": 80,
    "museum_heritage": 70,
    "nightlife": 35,
    "park_nature": 70,
    "beach": 60,
    "fort_landmark": None,   # keep all
    "market": 20,
    "day_trip": None,
    "adventure": None,
    "wellness_spa": None,
}

# Interests each category satisfies (inverse of INTEREST_CATEGORY_WEIGHTS)
CATEGORY_TO_INTERESTS = {
    "beach": ["beaches", "nature", "wellness"],
    "museum_heritage": ["culture", "food"],
    "fort_landmark": ["culture"],
    "park_nature": ["nature", "wellness"],
    "food": ["food"],
    "market": ["food", "culture"],
    "nightlife": ["nightlife"],
    "wellness_spa": ["wellness"],
    "adventure": ["adventure", "beaches"],
    "day_trip": ["nature", "adventure"],
}

# Curated famous places that fill category gaps in OSM (wellness, adventure,
# flagship landmarks). Coordinates are approximate-from-memory — the `source`
# field says so; OSM entries carry precise coordinates.
CURATED_PLACES = [
    ("Basilica of Bom Jesus", 15.5005, 73.9103, "old_goa", "museum_heritage", "UNESCO-listed baroque church holding St Francis Xavier's relics."),
    ("Se Cathedral", 15.5013, 73.9113, "old_goa", "museum_heritage", "One of Asia's largest churches, iconic Portuguese-Gothic architecture."),
    ("Church of St Francis of Assisi", 15.5008, 73.9109, "old_goa", "museum_heritage", "Painted interiors and the attached archaeology museum."),
    ("Fort Aguada", 15.5545, 73.7376, "north_goa", "fort_landmark", "17th-century Portuguese fort guarding the Mandovi mouth, with a lighthouse."),
    ("Chapora Fort", 15.6026, 73.7368, "north_goa", "fort_landmark", "Hilltop fort with panoramic views over Vagator and Anjuna."),
    ("Fort Reis Magos", 15.4799, 73.8350, "panaji", "fort_landmark", "Restored riverside fort across the Mandovi from Panaji."),
    ("Dudhsagar Falls", 15.3144, 74.3144, "south_goa", "day_trip", "Four-tiered waterfall among India's tallest — a full-day jeep trek."),
    ("Bhagwan Mahavir Wildlife Sanctuary", 15.3527, 74.2318, "south_goa", "park_nature", "Mollem's forest reserve on the Karnataka border, gateway to Dudhsagar."),
    ("Bondla Wildlife Sanctuary", 15.4434, 74.1006, "south_goa", "park_nature", "Compact sanctuary with a mini-zoo and deer park — good with kids."),
    ("Sahakari Spice Farm", 15.4218, 74.0459, "south_goa", "park_nature", "Guided spice-garden walk with a traditional Goan buffet lunch."),
    ("Mangueshi Temple", 15.4469, 74.0030, "south_goa", "museum_heritage", "Elegant 18th-century Shiva temple, one of Goa's most important."),
    ("Shanta Durga Temple", 15.4553, 73.9722, "south_goa", "museum_heritage", "Large peaceful temple complex with distinctive Goan temple architecture."),
    ("Goa State Museum", 15.4929, 73.8306, "panaji", "museum_heritage", "State collections spanning Goan art, sculpture and history."),
    ("Museum of Goa", 15.5518, 73.7638, "north_goa", "museum_heritage", "Contemporary art museum in Pilerne by Subodh Kerkar."),
    ("Fontainhas Heritage Quarter", 15.4954, 73.8292, "panaji", "museum_heritage", "Latin-quarter lanes of colourful Portuguese-era houses."),
    ("Anjuna Flea Market", 15.5755, 73.7402, "north_goa", "market", "Legendary Wednesday flea market — crafts, clothing, souvenirs."),
    ("Mapusa Friday Market", 15.5920, 73.8064, "north_goa", "market", "Local Produce market frequented by Goans, not just tourists."),
    ("Margao Market", 15.2700, 73.9576, "south_goa", "market", "South Goa's main market — spices, fish and daily Goan life."),
    ("Tito's Lane", 15.5595, 73.7509, "north_goa", "nightlife", "Baga's famous nightlife strip of clubs and bars."),
    ("Curlies Beach Shack", 15.5864, 73.7371, "north_goa", "nightlife", "Anjuna cliff-top institution for sunset drinks and parties."),
    ("Thalassa Greek Taverna", 15.5906, 73.7367, "north_goa", "food", "Cliffside Greek restaurant overlooking Vagator beach."),
    ("Gunpowder", 15.5859, 73.7685, "north_goa", "food", "South-Indian-focused restaurant in an Assagao heritage house."),
    ("Vinayak Family Restaurant", 15.5869, 73.7695, "north_goa", "food", "Beloved local Goan thali and seafood classic in Assagao."),
    ("Martin's Corner", 15.2823, 73.9578, "south_goa", "food", "Iconic Goan family restaurant near Betalbatim."),
    ("Devaaya Ayurveda Retreat", 15.5152, 73.8629, "north_goa", "wellness_spa", "Ayurveda and naturopathy retreat on Divar island."),
    ("Grande Island Dive Sites", 15.3533, 73.7783, "south_goa", "adventure", "Snorkelling and scuba day trips to Grande Island."),
    ("Parasailing Point Calangute", 15.5420, 73.7550, "north_goa", "adventure", "Banner parasailing flights off Calangute beach."),
    ("Deltin Royale Casino", 15.4990, 73.8140, "panaji", "nightlife", "Large offshore casino on the Mandovi river."),
]


def fetch_overpass() -> dict:
    """Query Overpass for the Goa bbox; cache the raw JSON response."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / "overpass_goa.json"
    if cache_file.exists():
        print(f"cache hit: {cache_file}")
        return json.loads(cache_file.read_text())

    print("fetching from Overpass API (this can take ~30-60s)...")
    response = httpx.post(
        OVERPASS_URL,
        data={"data": OVERPASS_QUERY},
        headers={"User-Agent": REQUEST_USER_AGENT},
        timeout=240,
    )
    response.raise_for_status()
    data = response.json()
    cache_file.write_text(json.dumps(data))
    print(f"cached {len(data.get('elements', []))} raw elements to {cache_file}")
    return data


def choose_category(tags: dict) -> str | None:
    """Pick the most specific category from an element's OSM tags.

    Order matters: specific natural/historic features must win before the
    generic tourism=attraction fallback, and small shrines are only kept if
    they carry a Wikipedia link (otherwise hundreds of unnamed-local temples
    flood the heritage category).

    Only Dudhsagar-scale falls deserve a full day; every OSM waterfall is a
    minor cascade, so they map to park_nature (~90 min). The curated
    Dudhsagar Falls entry keeps its explicit day_trip category.
    """
    if tags.get("waterway") == "waterfall":
        return "park_nature"
    for key, value in [
        ("historic", "fort"), ("historic", "castle"), ("historic", "ruins"),
        ("historic", "monument"), ("historic", "memorial"), ("historic", "archaeological_site"),
    ]:
        if tags.get(key) == value:
            return "fort_landmark"
    if tags.get("natural") == "beach":
        return "beach"
    for key, value in [
        ("sport", "scuba_diving"), ("sport", "surfing"), ("sport", "kitesurfing"),
        ("sport", "paragliding"), ("shop", "scuba_diving"),
    ]:
        if tags.get(key) == value:
            return "adventure"
    if tags.get("leisure") in ("park", "garden", "nature_reserve"):
        return "park_nature"
    if tags.get("leisure") == "water_park":
        return "adventure"
    if tags.get("tourism") in ("museum", "gallery"):
        return "museum_heritage"
    if tags.get("tourism") in ("zoo", "theme_park"):
        return "adventure" if tags.get("tourism") == "theme_park" else "park_nature"
    if tags.get("tourism") == "spa_resort":
        return "wellness_spa"
    if tags.get("tourism") == "viewpoint":
        return "park_nature"
    if tags.get("amenity") in ("restaurant", "cafe"):
        return "food"
    if tags.get("amenity") in ("bar", "pub", "nightclub"):
        return "nightlife"
    if tags.get("amenity") == "marketplace":
        return "market"
    if tags.get("tourism") == "attraction":
        return "museum_heritage"
    if tags.get("amenity") == "place_of_worship" and (
        "wikipedia" in tags or "wikidata" in tags
    ):
        return "museum_heritage"
    return None


def zone_for(lat: float, lon: float) -> str:
    """Assign a Goa zone from coordinates (plan.md Phase 1 zone list)."""
    if 15.45 <= lat <= 15.54 and 73.88 <= lon <= 73.95:
        return "old_goa"
    if lat > 15.60 and lon < 73.78:
        return "morjim_ashwem"
    if 15.42 <= lat <= 15.55 and lon <= 73.88:
        return "panaji"
    if lat >= 15.45:
        return "north_goa"
    return "south_goa"


def deterministic_rating(place_id: str) -> float:
    """Stable pseudo-rating in [3.0, 4.8] so scoring has signal; flagged synthetic."""
    digest = hashlib.sha256(place_id.encode()).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return round(3.0 + bucket * 1.8, 1)


def extract_dietary_tags(tags: dict) -> list[str]:
    """Explicit diet markers from OSM ``diet:*`` tags for filter.py.

    Only positive assertions are kept (``diet:vegetarian=yes`` means the
    kitchen serves veg food; a vegan kitchen also serves veg travellers).
    Meat-signal tags (``diet:seafood=yes``) are ignored on purpose: they say
    what is served, not what is excluded, so the name-keyword fallback in
    filter.py stays responsible for those.
    """
    dietary_tags: set[str] = set()
    if str(tags.get("diet:vegetarian", "")).lower() in ("yes", "only"):
        dietary_tags.add("veg")
    if str(tags.get("diet:vegan", "")).lower() in ("yes", "only"):
        dietary_tags.update(("veg", "vegan"))
    return sorted(dietary_tags)


def parse_osm_element(element: dict) -> dict | None:
    tags = element.get("tags", {})
    name = tags.get("name")
    if not name:
        return None
    category = choose_category(tags)
    if category is None:
        return None

    if "lat" in element and "lon" in element:
        lat, lon = element["lat"], element["lon"]
    elif "center" in element:
        lat, lon = element["center"]["lat"], element["center"]["lon"]
    else:
        return None

    duration, price, why_visit = CATEGORY_DEFAULTS[category]
    is_worship = tags.get("amenity") == "place_of_worship"
    is_nightlife = category == "nightlife"
    is_adventure = category == "adventure"
    is_shack = "shack" in name.lower()

    return {
        "id": f"osm-{element['type']}-{element['id']}",
        "name": name,
        "lat": lat,
        "lon": lon,
        "zone": zone_for(lat, lon),
        "category": category,
        "subcategory": tags.get("cuisine") or tags.get("historic") or tags.get("tourism"),
        "visit_duration_minutes": duration,
        "price_level": price,
        "rating": deterministic_rating(f"osm-{element['type']}-{element['id']}"),
        "opening_hours_raw": tags.get("opening_hours"),
        "hours_unknown": "opening_hours" not in tags,
        "tags": CATEGORY_TO_INTERESTS[category],
        "suitability": ["nightlife"] if is_nightlife else (["adventure"] if is_adventure else []),
        "kids_ok": not is_nightlife,
        "seniors_ok": not is_adventure,
        "dietary_tags": extract_dietary_tags(tags),
        "seasonally_closed_months": MONSOON_MONTHS if (is_adventure or is_shack) else [],
        "description": tags.get("description") or why_visit,
        "has_wiki": "wikipedia" in tags or "wikidata" in tags,
        "source": {"category": "osm", "osm_type": element["type"], "osm_id": element["id"]},
    }


def parse_curated(name_lat_lon_zone: tuple) -> dict:
    (name, lat, lon, zone, category, description) = name_lat_lon_zone
    duration, price, _ = CATEGORY_DEFAULTS[category]
    is_nightlife = category == "nightlife"
    is_adventure = category == "adventure"
    place_id = f"curated-{hashlib.sha256(name.encode()).hexdigest()[:10]}"
    return {
        "id": place_id,
        "name": name,
        "lat": lat,
        "lon": lon,
        "zone": zone,
        "category": category,
        "subcategory": None,
        "visit_duration_minutes": duration,
        "price_level": price,
        "rating": deterministic_rating(place_id),
        "opening_hours_raw": None,
        "hours_unknown": True,
        "tags": CATEGORY_TO_INTERESTS[category],
        "suitability": ["nightlife"] if is_nightlife else (["adventure"] if is_adventure else []),
        "kids_ok": not is_nightlife,
        "seniors_ok": not is_adventure,
        # Curated entries carry no verified diet claim; the keyword fallback
        # in filter.py plus the diet assumption cover them.
        "dietary_tags": [],
        "seasonally_closed_months": MONSOON_MONTHS if is_adventure else [],
        "description": description,
        "has_wiki": True,
        "source": {
            "category": "curated",
            "notes": "curated famous place; coordinates approximate — verify before production",
        },
    }


def apply_category_caps(places: list[dict]) -> list[dict]:
    """Trim oversized categories, keeping Wikipedia-linked and curated places first."""
    kept: list[dict] = []
    for category, cap in CATEGORY_CAPS.items():
        in_category = [p for p in places if p["category"] == category]
        if cap is None or len(in_category) <= cap:
            kept.extend(in_category)
            continue
        in_category.sort(
            key=lambda p: (1 if p.get("has_wiki") else 0, p["rating"]),
            reverse=True,
        )
        kept.extend(in_category[:cap])
    return kept


def dedupe(places: list[dict]) -> list[dict]:
    """Drop duplicates by rounded coordinates and by exact name (case-insensitive)."""
    seen_coords: set[tuple] = set()
    seen_names: set[str] = set()
    unique: list[dict] = []
    for place in places:
        coord_key = (round(place["lat"], 3), round(place["lon"], 3))
        name_key = place["name"].strip().lower()
        if coord_key in seen_coords or name_key in seen_names:
            continue
        seen_coords.add(coord_key)
        seen_names.add(name_key)
        unique.append(place)
    return unique


def parse_opening_hours(raw: str | None) -> dict:
    """Keep the raw string; structured parsing is a later refinement (hours_unknown flag
    communicates honesty). Empty string when unknown."""
    return {"raw": raw} if raw else {}


def main() -> None:
    started = time.time()
    overpass_data = fetch_overpass()

    osm_places = [
        parsed
        for element in overpass_data.get("elements", [])
        if (parsed := parse_osm_element(element)) is not None
    ]
    curated_places = [parse_curated(entry) for entry in CURATED_PLACES]

    # Curated entries win name collisions: they are famous anchors whose OSM
    # twins are sometimes mis-tagged duplicates (e.g. the Fort Aguada resort
    # element 5km from the actual fort). OSM keeps precision for everything else.
    all_places = apply_category_caps(dedupe(curated_places + osm_places))
    print(f"osm parsed: {len(osm_places)}, curated: {len(curated_places)}, after dedupe + caps: {len(all_places)}")

    from app.db import Base, SessionLocal, engine

    # Full rebuild: drop first so schema changes (new columns) apply to the
    # committed database instead of failing against the old table shape.
    Base.metadata.drop_all(engine)
    init_db()
    with SessionLocal() as session:
        session.query(Place).delete()
        for record in all_places:
            session.add(
                Place(
                    id=record["id"],
                    name=record["name"],
                    lat=record["lat"],
                    lon=record["lon"],
                    zone=record["zone"],
                    category=record["category"],
                    subcategory=record["subcategory"],
                    visit_duration_minutes=record["visit_duration_minutes"],
                    price_level=record["price_level"],
                    rating=record["rating"],
                    opening_hours=parse_opening_hours(record["opening_hours_raw"]),
                    hours_unknown=record["hours_unknown"],
                    tags=record["tags"],
                    suitability=record["suitability"],
                    kids_ok=record["kids_ok"],
                    seniors_ok=record["seniors_ok"],
                    dietary_tags=record["dietary_tags"],
                    seasonally_closed_months=record["seasonally_closed_months"],
                    description=record["description"],
                    source=record["source"],
                )
            )
        session.commit()

    print(f"seeded {len(all_places)} places in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
