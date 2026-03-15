"""Steps 3 & 4: Geocode properties and find nearest ski lifts.

Geocoding priority:
1. Lat/lng already extracted from Booking.com property page source
2. Geocode street address via OpenStreetMap Nominatim

Ski lift lookup via Overpass API for aerialway features within 800m.
"""

import asyncio
import math

import httpx

import config

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
            resp = await client.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1},
                headers=NOMINATIM_HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
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
        resp = await client.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=20,
        )
        if resp.status_code != 200:
            return []

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


async def enrich_property(client: httpx.AsyncClient, prop: dict) -> dict:
    """Geocode a property (if needed) and find nearby ski lifts."""
    name = prop.get("name", "?")

    # Step 3: Geocode if needed
    lat = prop.get("latitude")
    lon = prop.get("longitude")

    if lat is None or lon is None:
        address = prop.get("street_address") or prop.get("address", "")
        resort = prop.get("resort", "")
        if address:
            coords = await geocode_address(client, address, resort)
            if coords:
                lat, lon = coords
                prop["latitude"] = lat
                prop["longitude"] = lon
                prop["geocode_source"] = "nominatim"
                print(f"    Geocoded {name}: {lat}, {lon}")
            else:
                print(f"    Could not geocode {name}")
        else:
            print(f"    No address for {name}, skipping geocode")
    else:
        prop["geocode_source"] = "booking"

    # Step 4: Find nearby ski lifts
    lifts = []
    if lat is not None and lon is not None:
        lifts = await find_nearby_lifts(client, lat, lon)

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
        if lat is not None:
            print(f"    No ski lifts found near {name}")

    return prop


async def enrich_all(properties: list[dict]) -> list[dict]:
    """Enrich all properties with geocoding and lift data."""
    print(f"\nEnriching {len(properties)} properties with geo + lift data...")

    async with httpx.AsyncClient() as client:
        enriched = []
        for i, prop in enumerate(properties):
            print(f"  [{i + 1}/{len(properties)}] {prop.get('name', '?')}")
            enriched_prop = await enrich_property(client, prop)
            enriched.append(enriched_prop)
            # Rate limit for Nominatim (1 req/sec) + Overpass courtesy
            await asyncio.sleep(1.5)

    return enriched
