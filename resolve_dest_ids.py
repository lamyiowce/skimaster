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
                "resort": resort,
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


async def resolve_dest_ids(resorts: list[str]) -> dict:
    """Resolve dest_ids for all resorts, using cache where available."""
    cache = load_cache()
    to_resolve = [r for r in resorts if r not in cache]

    if not to_resolve:
        print(f"All {len(resorts)} resort dest_ids loaded from cache.")
        return cache

    print(f"Resolving {len(to_resolve)} resort dest_ids (cached: {len(resorts) - len(to_resolve)})...")

    async with async_playwright() as p:
        browser, context = await create_browser_context(p)
        page = await context.new_page()

        for resort in to_resolve:
            result = await resolve_single_dest_id(resort, page)
            if result:
                cache[resort] = result
            await asyncio.sleep(2)  # Polite delay between lookups

        await browser.close()

    save_cache(cache)
    return cache


if __name__ == "__main__":
    results = asyncio.run(resolve_dest_ids(config.RESORTS))
    print(f"\nResolved {len(results)} resorts total.")
