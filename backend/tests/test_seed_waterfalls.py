"""Seed regression: only Dudhsagar-scale falls deserve a full day."""

import importlib.util
from pathlib import Path


def load_seed_module():
    seed_path = Path(__file__).resolve().parent.parent / "data" / "seed.py"
    spec = importlib.util.spec_from_file_location("wishtrip_seed", seed_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_osm_waterfall_maps_to_park_nature_not_day_trip() -> None:
    seed = load_seed_module()
    assert seed.choose_category({"waterway": "waterfall"}) == "park_nature"


def test_day_trip_defaults_stay_full_day_scale() -> None:
    seed = load_seed_module()
    duration, _, _ = seed.CATEGORY_DEFAULTS["day_trip"]
    assert duration == 360
    duration, _, _ = seed.CATEGORY_DEFAULTS["park_nature"]
    assert duration == 90
