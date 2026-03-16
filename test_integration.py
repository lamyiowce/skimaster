"""Integration test: coordinate extraction → lift lookup for Arc 1950.

Tests the full path from raw Booking.com-like HTML through to ski lift
detection, using mocked HTTP responses so no real network calls are made.

Scenarios covered:
  1. Happy path  — single JSON-LD block, correct coordinates extracted,
                   Overpass returns nearby lifts.
  2. Overwrite bug (old behaviour) — two JSON-LD blocks where the second has
                   wrong coordinates (another hotel); verifies the fix (break)
                   prevents the overwrite.
  3. Regex fallback — no JSON-LD geo data; coordinates come from raw page
                   source; verifies the new pattern rejects integers and
                   accepts proper floats.
  4. Station filter — Overpass returns only aerialway=station nodes (boarding
                   points); verifies they are filtered out and the property
                   still reports lifts when an actual lift way is present.
  5. No lifts (wrong coords) — wrong coordinates passed to Overpass; response
                   contains no aerialway elements; verifies "no lifts" path.
"""

import asyncio
import json
import re
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Minimal stubs so we can import scrape_booking without Playwright installed
# ---------------------------------------------------------------------------
for mod in ("playwright", "playwright.async_api"):
    stub = types.ModuleType(mod)
    stub.async_playwright = None  # attribute accessed at import time
    sys.modules[mod] = stub

# browser_utils stub
bu = types.ModuleType("browser_utils")
bu.create_browser_context = AsyncMock()
bu.dismiss_popups = AsyncMock()
sys.modules["browser_utils"] = bu

import scrape_booking  # noqa: E402  (must come after stubs)
import geo_lifts       # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ARC1950_LAT = 45.4934
ARC1950_LON = 6.8399

PARIS_LAT = 48.8566
PARIS_LON = 2.3522


def make_booking_html(*, lat=ARC1950_LAT, lon=ARC1950_LON,
                      extra_json_ld=None, include_geo_in_first=True):
    """Return minimal HTML that mimics a Booking.com property detail page."""
    first_block = {
        "@type": "ApartmentComplex",
        "name": "Appartement de Standing - ARC 1950",
        "address": {
            "streetAddress": "n°151 et 152 Refuge du Montagnard ARC 1950",
            "postalCode": "73700",
            "addressLocality": "Arc 1950",
        },
    }
    if include_geo_in_first:
        first_block["geo"] = {"latitude": lat, "longitude": lon}

    blocks = [json.dumps(first_block)]
    if extra_json_ld:
        blocks.append(json.dumps(extra_json_ld))

    ld_tags = "\n".join(
        f'<script type="application/ld+json">{b}</script>' for b in blocks
    )
    return f"<html><head>{ld_tags}</head><body></body></html>"


def make_overpass_response(elements):
    """Return a mock httpx.Response for an Overpass API call."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"elements": elements}
    return mock_resp


TRANSARC_GONDOLA = {
    "type": "way",
    "tags": {"aerialway": "gondola", "name": "Transarc"},
    "center": {"lat": 45.505, "lon": 6.835},
}

COMBORCIERE_CHAIR = {
    "type": "node",
    "lat": 45.494,
    "lon": 6.841,
    "tags": {"aerialway": "chair_lift", "name": "Comborcières"},
}

STATION_NODE = {
    "type": "node",
    "lat": 45.493,
    "lon": 6.840,
    "tags": {"aerialway": "station", "name": "Arc 1950 station"},
}


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestCoordinateExtraction(unittest.IsolatedAsyncioTestCase):
    """Unit-level tests for extract_detail_page_info coordinate parsing."""

    async def _run_extract(self, html):
        prop = {
            "url": "https://www.booking.com/fake",
            "name": "Appartement de Standing - ARC 1950",
            "street_address": "",
            "latitude": None,
            "longitude": None,
        }
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value=html)
        mock_page.locator = MagicMock(return_value=MagicMock(
            count=AsyncMock(return_value=0)
        ))
        with patch("scrape_booking.dismiss_popups", AsyncMock()):
            return await scrape_booking.extract_detail_page_info(mock_page, prop)

    async def test_single_json_ld_block_correct_coords(self):
        """Happy path: one JSON-LD block gives Arc 1950 coordinates."""
        html = make_booking_html()
        prop = await self._run_extract(html)
        self.assertAlmostEqual(prop["latitude"], ARC1950_LAT, places=3)
        self.assertAlmostEqual(prop["longitude"], ARC1950_LON, places=3)

    async def test_two_json_ld_blocks_second_overwrites_without_fix(self):
        """Demonstrate the bug: without break, second block wins."""
        second_block = {
            "@type": "Hotel",
            "name": "Recommended hotel",
            "geo": {"latitude": PARIS_LAT, "longitude": PARIS_LON},
        }
        html = make_booking_html(extra_json_ld=second_block)
        prop = await self._run_extract(html)
        # With the fix (break after first), we should get Arc 1950 coords
        self.assertAlmostEqual(prop["latitude"], ARC1950_LAT, places=3,
                               msg="Second JSON-LD block must not overwrite first")
        self.assertAlmostEqual(prop["longitude"], ARC1950_LON, places=3,
                               msg="Second JSON-LD block must not overwrite first")

    async def test_regex_fallback_skips_integer_latitude(self):
        """Fallback regex must not match integer 'latitude' fields."""
        # No geo in JSON-LD; page source has an integer "latitude" first,
        # then the real float coordinates later.
        html = (
            '<html><head>'
            '<script type="application/ld+json">{"@type":"BreadcrumbList"}</script>'
            '</head><body>'
            'var ui = {"latitude": 4, "stars": 3};'          # integer — must be ignored
            '"latitude": 45.4934, "longitude": 6.8399'       # real coords
            '</body></html>'
        )
        prop = await self._run_extract(html)
        self.assertAlmostEqual(prop["latitude"], ARC1950_LAT, places=3,
                               msg="Regex must skip integer latitude=4 and find 45.4934")

    async def test_street_address_extracted(self):
        """Street address is populated from JSON-LD."""
        html = make_booking_html()
        prop = await self._run_extract(html)
        self.assertIn("Refuge du Montagnard", prop["street_address"])


class TestLiftDetection(unittest.IsolatedAsyncioTestCase):
    """Integration tests for geo_lifts.find_nearby_lifts and _attach_lift_data."""

    async def _find_lifts(self, overpass_elements, lat=ARC1950_LAT, lon=ARC1950_LON):
        mock_resp = make_overpass_response(overpass_elements)
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        return await geo_lifts.find_nearby_lifts(mock_client, lat, lon)

    async def test_gondola_and_chair_found(self):
        """Gondola (way) and chair lift (node) both returned and sorted by distance."""
        lifts = await self._find_lifts([TRANSARC_GONDOLA, COMBORCIERE_CHAIR])
        self.assertEqual(len(lifts), 2)
        names = [l["name"] for l in lifts]
        self.assertIn("Transarc", names)
        self.assertIn("Comborcières", names)
        # Closest lift first
        self.assertLessEqual(lifts[0]["distance_m"], lifts[1]["distance_m"])

    async def test_station_nodes_filtered_out(self):
        """aerialway=station nodes must be excluded; real lift ways kept."""
        lifts = await self._find_lifts([STATION_NODE, TRANSARC_GONDOLA])
        names = [l["name"] for l in lifts]
        self.assertNotIn("Arc 1950 station", names,
                         "aerialway=station should be filtered out")
        self.assertIn("Transarc", names)

    async def test_no_lifts_for_wrong_coordinates(self):
        """Empty Overpass response → no lifts attached, message flag set."""
        prop = {
            "name": "Appartement de Standing - ARC 1950",
            "latitude": PARIS_LAT,
            "longitude": PARIS_LON,
            "nearby_lifts": [],
        }
        geo_lifts._attach_lift_data(prop, [])
        self.assertIsNone(prop["nearest_lift_name"])
        self.assertEqual(prop["nearby_lifts"], [])

    async def test_correct_coords_yield_lifts(self):
        """Correct Arc 1950 coords + real Overpass data → lifts found."""
        lifts = await self._find_lifts([COMBORCIERE_CHAIR])
        self.assertEqual(len(lifts), 1)
        self.assertEqual(lifts[0]["name"], "Comborcières")
        self.assertGreater(lifts[0]["distance_m"], 0)
        self.assertGreater(lifts[0]["walk_minutes"], 0)

    async def test_deduplication(self):
        """Same lift appearing twice (node + way with same name/type) deduped."""
        duplicate = {
            "type": "way",
            "tags": {"aerialway": "chair_lift", "name": "Comborcières"},
            "center": {"lat": 45.495, "lon": 6.842},
        }
        lifts = await self._find_lifts([COMBORCIERE_CHAIR, duplicate])
        comborciere_count = sum(1 for l in lifts if l["name"] == "Comborcières")
        self.assertEqual(comborciere_count, 1, "Duplicate lift entry not deduplicated")

    async def test_walk_time_calculation(self):
        """Walk time is computed correctly from distance."""
        lifts = await self._find_lifts([COMBORCIERE_CHAIR])
        expected_dist = geo_lifts.haversine(
            ARC1950_LAT, ARC1950_LON, 45.494, 6.841
        ) * geo_lifts.HAVERSINE_FACTOR
        expected_walk = expected_dist / geo_lifts.WALKING_SPEED_M_PER_MIN
        self.assertAlmostEqual(lifts[0]["distance_m"], round(expected_dist), delta=1)
        self.assertAlmostEqual(lifts[0]["walk_minutes"], round(expected_walk, 1), delta=0.1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
