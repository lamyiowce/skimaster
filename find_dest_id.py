#!/usr/bin/env python3
"""Helper: Resolve a single resort's Booking.com destination ID.

Usage:
    python find_dest_id.py "Verbier, Switzerland"
"""

import asyncio
import sys

from resolve_dest_ids import resolve_single_dest_id
from playwright.async_api import async_playwright


async def main(resort: str):
    print(f"Looking up Booking.com dest_id for: {resort}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = await context.new_page()
        result = await resolve_single_dest_id(resort, page)
        await browser.close()

    if result:
        print(f"\nResolved:")
        print(f"  dest_id:   {result['dest_id']}")
        print(f"  dest_type: {result['dest_type']}")
        print(f"\nTo add this resort, add \"{resort}\" to RESORTS in config.py")
    else:
        print(f"\nCould not resolve dest_id for \"{resort}\"")
        print("Try a more specific name, e.g. \"Verbier, Switzerland\"")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python find_dest_id.py \"Resort Name, Country\"")
        sys.exit(1)

    asyncio.run(main(sys.argv[1]))
