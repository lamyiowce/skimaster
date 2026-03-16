"""Steps 3 & 4: Geocode properties and find nearest ski lifts.

Geocoding priority:
1. Lat/lng already extracted from Booking.com property page source
2. Geocode street address via OpenStreetMap Nominatim

Ski lift lookup via Overpass API for aerialway features within 800m.
"""

import asyncio
import math
import time

import httpx
from tenacity import retry

import config
from http_utils import RETRY_HTTP

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

NOMINATIM_HEADERS = {
    "User-Agent": "SkiAccommodationSearch/1.0 (ski-group-trip-planner)"
}

# Aerialway types that are actual ski lifts
SKI_LIFT_TYPES = {
    "gondola",
    "cable_car",
    "chair_lift",
    "drag_lift",
    "t-bar",
    "platter",
    "rope_tow",
    "magic_carpet",
    "mixed_lift",
    "funicular",
}

# Types to skip
SKIP_LIFT_TYPES = {"zip_line", "goods", "canopy"}

# Walking speed: ~67 meters per minute, haversine × 1.3 for street routing
WALKING_SPEED_M_PER_MIN = 67
HAVERSINE_FACTOR = 1.3

@retry(**RETRY_HTTP)
async def _nominatim_get(client: httpx.AsyncClient, query: str) -> httpx.Response:
    """Single Nominatim GET with automatic retry on rate-limit / transient errors."""
    resp = await client.get(
        NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": 1},
        headers=NOMINATIM_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return resp


@retry(**RETRY_HTTP)
async def _overpass_post(client: httpx.AsyncClient, query: str) -> httpx.Response:
    """Single Overpass POST with automatic retry on rate-limit / transient errors."""
    resp = await client.post(
        OVERPASS_URL,
        data={"data": query},
        timeout=20,
    )
    resp.raise_for_status()
    return resp


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate haversine distance in meters between two coordinates."""
    R = 6371000  # Earth's radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def geocode_address(client: httpx.AsyncClient, address: str, resort: str = "") -> tuple[float, float] | None:
    """Geocode an address using Nominatim. Returns (lat, lng) or None."""
    queries = [address]
    if resort:
        queries.extend([f"{address}, {resort}", resort])

    for query in queries:
        try:
            resp = await _nominatim_get(client, query)
            results = resp.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
        except Exception:
            pass
        await asyncio.sleep(1)  # Nominatim rate limit: 1 req/sec

    return None


async def find_nearby_lifts(
    client: httpx.AsyncClient, lat: float, lon: float, radius: int = 800
) -> list[dict]:
    """Query Overpass API for aerialway features within radius meters."""
    query = f"""
    [out:json][timeout:15];
    (
      node["aerialway"](around:{radius},{lat},{lon});
      way["aerialway"](around:{radius},{lat},{lon});
    );
    out center;
    """

    try:
        resp = await _overpass_post(client, query)
        data = resp.json()
        lifts = []
        seen = set()  # Deduplicate by name+type

        for element in data.get("elements", []):
            tags = element.get("tags", {})
            lift_type = tags.get("aerialway", "")

            # Skip non-ski types
            if lift_type in SKIP_LIFT_TYPES:
                continue
            if lift_type not in SKI_LIFT_TYPES:
                continue

            name = tags.get("name", f"Unnamed {lift_type}")
            dedup_key = f"{name}|{lift_type}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Get coordinates (nodes have lat/lon, ways have center)
            if "lat" in element and "lon" in element:
                lift_lat, lift_lon = element["lat"], element["lon"]
            elif "center" in element:
                lift_lat = element["center"]["lat"]
                lift_lon = element["center"]["lon"]
            else:
                continue

            distance_m = haversine(lat, lon, lift_lat, lift_lon) * HAVERSINE_FACTOR
            walk_minutes = distance_m / WALKING_SPEED_M_PER_MIN

            lifts.append({
                "name": name,
                "type": lift_type,
                "distance_m": round(distance_m),
                "walk_minutes": round(walk_minutes, 1),
                "lat": lift_lat,
                "lon": lift_lon,
            })

        # Sort by distance
        lifts.sort(key=lambda x: x["distance_m"])
        return lifts

    except Exception as e:
        print(f"    Warning: Overpass query failed: {e}")
        return []


def _attach_lift_data(prop: dict, lifts: list[dict]) -> None:
    """Store lift lookup results on a property dict."""
    name = prop.get("name", "?")
    prop["nearby_lifts"] = lifts
    if lifts:
        nearest = lifts[0]
        prop["nearest_lift_name"] = nearest["name"]
        prop["nearest_lift_type"] = nearest["type"]
        prop["nearest_lift_distance_m"] = nearest["distance_m"]
        prop["nearest_lift_walk_minutes"] = nearest["walk_minutes"]
        print(
            f"    Nearest lift for {name}: {nearest['name']} "
            f"({nearest['type']}) — {nearest['distance_m']}m, "
            f"{nearest['walk_minutes']} min walk"
        )
    else:
        prop["nearest_lift_name"] = None
        prop["nearest_lift_type"] = None
        prop["nearest_lift_distance_m"] = None
        prop["nearest_lift_walk_minutes"] = None
        if prop.get("latitude") is not None:
            print(f"    No ski lifts found near {name}")


async def _geocode_all(client: httpx.AsyncClient, properties: list[dict]) -> None:
    """Geocode properties sequentially (Nominatim 1 req/sec rate limit)."""
    for prop in properties:
        name = prop.get("name", "?")
        lat = prop.get("latitude")
        lon = prop.get("longitude")

        if lat is not None and lon is not None:
            prop["geocode_source"] = "booking"
            continue

        address = prop.get("street_address") or prop.get("address", "")
        resort = prop.get("resort", "")
        if not address:
            print(f"    No address for {name}, skipping geocode")
            continue

        coords = await geocode_address(client, address, resort)
        if coords:
            prop["latitude"], prop["longitude"] = coords
            prop["geocode_source"] = "nominatim"
            print(f"    Geocoded {name}: {coords[0]}, {coords[1]}")
        else:
            print(f"    Could not geocode {name}")
        # geocode_address already sleeps 1s per attempt; add a small extra
        # buffer only when a request was actually made.
        await asyncio.sleep(0.5)


async def _find_lifts_for_property(
    client: httpx.AsyncClient, prop: dict, sem: asyncio.Semaphore
) -> None:
    """Find nearby lifts for a single property (called concurrently)."""
    lat = prop.get("latitude")
    lon = prop.get("longitude")

    lifts = []
    if lat is not None and lon is not None:
        async with sem:
            lifts = await find_nearby_lifts(client, lat, lon)

    _attach_lift_data(prop, lifts)


async def enrich_all(properties: list[dict]) -> list[dict]:
    """Enrich all properties with geocoding and lift data.

    Phase 1 — Geocode sequentially (Nominatim rate-limits to 1 req/sec).
    Phase 2 — Find lifts in parallel (Overpass has no strict per-IP limit).
    """
    total = len(properties)
    print(f"\nEnriching {total} properties with geo + lift data...")

    async with httpx.AsyncClient() as client:
        # Phase 1: Geocode (sequential)
        t0 = time.perf_counter()
        print(f"\n  [geocode] start — {total} properties")
        await _geocode_all(client, properties)
        t1 = time.perf_counter()
        print(f"  [geocode] done — {t1 - t0:.1f}s")

        # Phase 2: Lift lookup (parallel, capped at 5 concurrent requests)
        print(f"\n  [lifts] start — querying Overpass in parallel")
        sem = asyncio.Semaphore(5)
        has_coords = [p for p in properties if p.get("latitude") is not None]
        no_coords = [p for p in properties if p.get("latitude") is None]
        for p in no_coords:
            _attach_lift_data(p, [])
        tasks = [_find_lifts_for_property(client, prop, sem) for prop in has_coords]
        await asyncio.gather(*tasks)
        t2 = time.perf_counter()
        print(f"  [lifts] done — {t2 - t1:.1f}s")

    n_booking   = sum(1 for p in properties if p.get("geocode_source") == "booking")
    n_nominatim = sum(1 for p in properties if p.get("geocode_source") == "nominatim")
    n_no_coords = sum(1 for p in properties if p.get("latitude") is None)
    n_has_lift  = sum(1 for p in properties if p.get("nearest_lift_name"))
    n_no_lift   = sum(1 for p in properties if p.get("latitude") is not None and not p.get("nearest_lift_name"))
    print(f"\nEnrichment summary ({total} properties):")
    print(f"  Geocoding : {n_booking} from Booking.com, {n_nominatim} via Nominatim, {n_no_coords} failed")
    print(f"  Lift data : {n_has_lift} with nearest lift, {n_no_lift} no lift found nearby")
    print(f"  Total enrichment time: {t2 - t0:.1f}s")

    return properties
