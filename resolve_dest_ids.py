"""Step 1: Resolve Booking.com destination IDs for resort names.

Uses Playwright to search Booking.com and extract dest_id/dest_type from URL params.
Caches results in dest_ids.json so lookup only happens once per resort.
"""

import asyncio
import json
import re
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright

from browser_utils import create_browser_context, dismiss_popups
import config


async def resolve_single_dest_id(resort: str, page) -> dict | None:
    """Search Booking.com for a resort and extract dest_id + dest_type from the URL."""
    try:
        await page.goto("https://www.booking.com", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1)

        await dismiss_popups(page)

        # Type resort name in search box
        search_box = page.locator("[name='ss']")
        await search_box.fill("")
        await search_box.fill(resort)
        await asyncio.sleep(2)

        # Click the first autocomplete suggestion if available
        try:
            suggestion = page.locator("[data-testid='autocomplete-results-options'] li").first
            if await suggestion.is_visible(timeout=3000):
                await suggestion.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        # Submit the search
        submit = page.locator("button[type='submit']")
        await submit.click()
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # Extract dest_id and dest_type from URL
        url = page.url
        params = parse_qs(urlparse(url).query)

        dest_id = params.get("dest_id", [None])[0]
        dest_type = params.get("dest_type", [None])[0]

        if not dest_id:
            # Try extracting from ss_all_dest_id or similar params
            dest_id = params.get("ss_all_dest_id", [None])[0]

        if not dest_id:
            # Try to find in page source via regex
            content = await page.content()
            match = re.search(r'"dest_id"\s*:\s*"?(-?\d+)"?', content)
            if match:
                dest_id = match.group(1)
            match_type = re.search(r'"dest_type"\s*:\s*"(\w+)"', content)
            if match_type:
                dest_type = match_type.group(1)

        if dest_id:
            print(f"  ✓ {resort}: dest_id={dest_id}, dest_type={dest_type or 'city'}")
            return {
                "dest_id": dest_id,
                "dest_type": dest_type or "city",
            }
        else:
            print(f"  ✗ {resort}: could not resolve dest_id")
            return None

    except Exception as e:
        print(f"  ✗ {resort}: error — {e}")
        return None


def load_cache() -> dict:
    """Load cached dest_ids from file."""
    try:
        with open(config.DEST_IDS_CACHE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict):
    """Save dest_ids cache to file."""
    with open(config.DEST_IDS_CACHE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def all_villages(resorts: dict | None = None) -> list[str]:
    """Return a flat list of every village search term for the given resorts dict.

    Defaults to config.RESORTS when no dict is provided.
    """
    if resorts is None:
        resorts = config.RESORTS
    villages = []
    for village_list in resorts.values():
        villages.extend(village_list)
    return villages


async def resolve_dest_ids(villages: list[str]) -> dict:
    """Resolve dest_ids for the given villages, using cache where available.

    Returns a dict keyed by village name containing only the requested villages
    (not the full cache).
    """
    cache = load_cache()
    to_resolve = [v for v in villages if v not in cache]

    if not to_resolve:
        print(f"All {len(villages)} village dest_ids loaded from cache.")
    else:
        print(f"Resolving {len(to_resolve)} village dest_ids (cached: {len(villages) - len(to_resolve)})...")

        async with async_playwright() as p:
            browser, context = await create_browser_context(p)
            page = await context.new_page()

            for village in to_resolve:
                result = await resolve_single_dest_id(village, page)
                if result:
                    cache[village] = result
                await asyncio.sleep(2)  # Polite delay between lookups

            await browser.close()

        save_cache(cache)

    return {v: cache[v] for v in villages if v in cache}


if __name__ == "__main__":
    villages = all_villages()
    results = asyncio.run(resolve_dest_ids(villages))
    print(f"\nResolved {len(results)}/{len(villages)} villages total.")
