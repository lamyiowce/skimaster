"""Step 2: Scrape Booking.com for ski accommodation listings.

Uses Playwright headless Chromium to load search results and extract property details.
Visits each property's detail page to get the exact street address and coordinates.
"""

import asyncio
import json
import re
from urllib.parse import urlencode

from playwright.async_api import async_playwright

from browser_utils import create_browser_context, dismiss_popups
import config


def build_search_url(dest_id: str, dest_type: str) -> str:
    """Build a Booking.com search URL with all required filters."""
    params = {
        "dest_id": dest_id,
        "dest_type": dest_type,
        "checkin": config.CHECK_IN,
        "checkout": config.CHECK_OUT,
        "group_adults": config.GROUP_SIZE,
        "no_rooms": 1,
        "selected_currency": config.CURRENCY,
        # Property types: 201=apartment, 220=chalet, 213=holiday home
        # min_bedroom enforces enough rooms for the full group (no living-room sleeping)
        "nflt": "ht_id=201;ht_id=220;ht_id=213"
        + f";min_bedroom={config.MIN_BEDROOMS}"
        + (";hotelfacility=80" if config.REQUIRE_SAUNA else ""),
    }
    return "https://www.booking.com/searchresults.html?" + urlencode(params)


def parse_price(text: str) -> float | None:
    """Parse price from text, handling various formats."""
    if not text:
        return None
    # Remove currency symbols and whitespace, keep digits and separators
    cleaned = re.sub(r"[^\d.,]", "", text)
    if not cleaned:
        return None
    # Handle comma as thousands separator (e.g. 1,234 or 1.234)
    if "," in cleaned and "." in cleaned:
        # Both present: assume comma is thousands sep
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts[-1]) == 2:
            # Comma is decimal separator
            cleaned = cleaned.replace(",", ".")
        else:
            # Comma is thousands separator
            cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_rating(text: str) -> float | None:
    """Extract numeric rating from text."""
    if not text:
        return None
    match = re.search(r"(\d+\.?\d*)", text)
    if match:
        val = float(match.group(1))
        if 0 < val <= 10:
            return val
    return None


async def extract_property_cards(page) -> list[dict]:
    """Extract property information from search results page."""
    properties = []

    cards = page.locator("[data-testid='property-card']")
    count = await cards.count()
    print(f"    Found {count} property cards on page")

    for i in range(count):
        card = cards.nth(i)
        try:
            prop = {}

            # Name
            title_el = card.locator("[data-testid='title']")
            prop["name"] = await title_el.text_content() if await title_el.count() > 0 else ""

            # URL
            link_el = card.locator("a[data-testid='title-link']")
            if await link_el.count() > 0:
                prop["url"] = await link_el.get_attribute("href") or ""
                if prop["url"].startswith("/"):
                    prop["url"] = "https://www.booking.com" + prop["url"]
            else:
                prop["url"] = ""

            # Price — use .last because discounted listings have two elements
            # (strikethrough original + actual price); we want the final price
            price_el = card.locator("[data-testid='price-and-discounted-price']")
            if await price_el.count() == 0:
                price_el = card.locator("span.prco-valign-middle-helper")
            price_text = await price_el.last.text_content() if await price_el.count() > 0 else ""
            prop["price"] = parse_price(price_text)
            prop["price_text"] = (price_text or "").strip()

            # Rating
            rating_el = card.locator("[data-testid='review-score'] div").first
            rating_text = await rating_el.text_content() if await rating_el.count() > 0 else ""
            prop["rating"] = parse_rating(rating_text)

            # Review count
            review_el = card.locator("[data-testid='review-score']")
            review_text = await review_el.text_content() if await review_el.count() > 0 else ""
            review_match = re.search(r"(\d[\d,]*)\s*review", review_text, re.IGNORECASE)
            prop["review_count"] = int(review_match.group(1).replace(",", "")) if review_match else None
            prop["review_text"] = review_text.strip()

            # Address from card
            addr_el = card.locator("[data-testid='address']")
            prop["address"] = await addr_el.text_content() if await addr_el.count() > 0 else ""

            # Property type
            type_el = card.locator("[data-testid='recommendation-tag']")
            prop["property_type"] = await type_el.text_content() if await type_el.count() > 0 else ""

            # Full card text for capacity parsing later
            prop["card_text"] = await card.text_content() or ""

            # Placeholders for detail page data
            prop["street_address"] = ""
            prop["latitude"] = None
            prop["longitude"] = None

            if prop["name"]:
                properties.append(prop)

        except Exception as e:
            print(f"    Warning: error extracting card {i}: {e}")
            continue

    return properties


async def extract_detail_page_info(page, prop: dict) -> dict:
    """Visit a property's detail page to get address and coordinates."""
    if not prop.get("url"):
        return prop

    try:
        await page.goto(prop["url"], wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(1)
        await dismiss_popups(page)

        content = await page.content()

        # Try JSON-LD structured data first
        json_ld_matches = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            content,
            re.DOTALL,
        )
        for json_str in json_ld_matches:
            try:
                data = json.loads(json_str)
                if isinstance(data, list):
                    data = data[0]
                if isinstance(data, dict):
                    addr = data.get("address", {})
                    if isinstance(addr, dict):
                        parts = [
                            addr.get("streetAddress", ""),
                            addr.get("postalCode", ""),
                            addr.get("addressLocality", ""),
                        ]
                        street = ", ".join(p for p in parts if p)
                        if street:
                            prop["street_address"] = street

                    geo = data.get("geo", {})
                    if isinstance(geo, dict):
                        lat = geo.get("latitude")
                        lng = geo.get("longitude")
                        if lat and lng:
                            prop["latitude"] = float(lat)
                            prop["longitude"] = float(lng)
            except (json.JSONDecodeError, ValueError):
                continue

        # Try extracting lat/lng from page source (most reliable)
        if not prop["latitude"]:
            lat_match = re.search(r'"latitude"\s*:\s*(-?\d+\.?\d*)', content)
            lng_match = re.search(r'"longitude"\s*:\s*(-?\d+\.?\d*)', content)
            if lat_match and lng_match:
                prop["latitude"] = float(lat_match.group(1))
                prop["longitude"] = float(lng_match.group(1))

        # Try address from page elements if not found yet
        if not prop["street_address"]:
            for selector in [
                "[data-testid='PropertyHeaderAddressDesktop-TextContainer']",
                "span.hp_address_subtitle",
                "[data-testid='address']",
            ]:
                try:
                    el = page.locator(selector)
                    if await el.count() > 0:
                        text = await el.first.text_content()
                        if text and len(text.strip()) > 5:
                            prop["street_address"] = text.strip()
                            break
                except Exception:
                    continue

    except Exception as e:
        print(f"    Warning: could not load detail page for {prop.get('name', '?')}: {e}")

    return prop


async def scrape_resort(
    resort: str, dest_info: dict, browser_context
) -> list[dict]:
    """Scrape all properties for a single resort."""
    dest_id = dest_info["dest_id"]
    dest_type = dest_info["dest_type"]
    url = build_search_url(dest_id, dest_type)

    print(f"\n  Searching {resort}...")
    print(f"    URL: {url}")

    page = await browser_context.new_page()
    properties = []

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await dismiss_popups(page)

        # Extract from first page
        page_props = await extract_property_cards(page)

        # Check for additional pages (up to 3 pages)
        for page_num in range(2, 4):
            try:
                next_btn = page.locator(f"button[aria-label='Page {page_num}']")
                if await next_btn.count() > 0 and await next_btn.is_visible(timeout=2000):
                    await next_btn.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    await asyncio.sleep(2)
                    page_props.extend(await extract_property_cards(page))
                else:
                    break
            except Exception:
                break

        print(f"    Total properties found: {len(page_props)}")

        # Visit detail pages for address + coordinates
        for j, prop in enumerate(page_props):
            prop["resort"] = resort
            print(f"    [{j + 1}/{len(page_props)}] Getting details for: {prop.get('name', '?')}")
            prop = await extract_detail_page_info(page, prop)
            properties.append(prop)
            await asyncio.sleep(1.5)  # Polite rate limiting

    except Exception as e:
        print(f"    Error scraping {resort}: {e}")
    finally:
        await page.close()

    return properties


async def scrape_all(dest_ids: dict, resorts: dict, debug: bool = False) -> list[dict]:
    """Scrape all resort groups and return combined property list.

    For each resort group the full list of configured villages is searched.
    Properties from all villages are tagged with the parent resort group name.
    Duplicates (same URL appearing in two village searches) are removed.

    Set debug=True (enabled automatically by --resort) for verbose per-village output.
    """
    all_properties = []

    async with async_playwright() as p:
        browser, context = await create_browser_context(
            p, extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
        )

        for resort_group, villages in resorts.items():
            if debug:
                print(f"\n=== Resort group: {resort_group} ({len(villages)} village(s)) ===")
            seen_urls: set[str] = set()
            group_properties = []

            n_skipped = 0
            for village in villages:
                if village not in dest_ids:
                    if debug:
                        print(f"  Skipping {village} — no dest_id resolved")
                    n_skipped += 1
                    continue

                props = await scrape_resort(resort_group, dest_ids[village], context)

                # Deduplicate: a property can appear in multiple village searches
                # if the Booking.com destination areas overlap.
                new_props = []
                for prop in props:
                    url = prop.get("url", "")
                    if url not in seen_urls:
                        seen_urls.add(url)
                        new_props.append(prop)

                n_dupes = len(props) - len(new_props)
                dupe_note = f", {n_dupes} duplicate(s) removed" if n_dupes else ""
                print(f"  {village}: {len(new_props)} properties{dupe_note}")

                group_properties.extend(new_props)
                await asyncio.sleep(3)  # Polite delay between village searches

            skip_note = f", {n_skipped} village(s) skipped (no dest_id)" if n_skipped else ""
            print(f"  → {resort_group}: {len(group_properties)} unique properties total{skip_note}")
            all_properties.extend(group_properties)

        await browser.close()

    print(f"\nTotal properties scraped: {len(all_properties)}")
    return all_properties
