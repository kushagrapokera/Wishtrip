"""Haversine travel-time estimation behind a pluggable interface.

The planner never calls these helpers' internals directly: every step takes a
``travel_minutes_between`` callable, so Phase 6 can swap the haversine default
for a Valhalla matrix implementation without touching planning logic.
"""

import math
from collections.abc import Callable

from app import config

TravelMinutesFn = Callable[[float, float, float, float], int]


def calculate_haversine_distance_km(
    from_lat: float, from_lon: float, to_lat: float, to_lon: float
) -> float:
    """Great-circle distance in kilometres between two coordinates."""
    earth_radius_km = 6371.0
    lat_delta = math.radians(to_lat - from_lat)
    lon_delta = math.radians(to_lon - from_lon)
    haversine_a = (
        math.sin(lat_delta / 2) ** 2
        + math.cos(math.radians(from_lat))
        * math.cos(math.radians(to_lat))
        * math.sin(lon_delta / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(haversine_a))


def estimate_travel_minutes(
    from_lat: float, from_lon: float, to_lat: float, to_lon: float
) -> int:
    """Offline travel-time estimate: walk under 1 km, drive above it.

    Goa speeds are deliberately modest (lanes, traffic, parking) and every leg
    carries a fixed overhead. Remote routing (Valhalla) is a drop-in
    replacement behind the same signature.
    """
    distance_km = calculate_haversine_distance_km(from_lat, from_lon, to_lat, to_lon)
    if distance_km < config.WALK_DISTANCE_KM_THRESHOLD:
        speed_kmh = config.WALK_SPEED_KMH
    else:
        speed_kmh = config.DRIVE_SPEED_KMH
    return int(distance_km / speed_kmh * 60) + config.TRAVEL_OVERHEAD_MINUTES


def choose_travel_mode(distance_km: float) -> str:
    """Walk for sub-kilometre hops, drive otherwise (matches the estimator)."""
    if distance_km < config.WALK_DISTANCE_KM_THRESHOLD:
        return "walk"
    return "drive"
