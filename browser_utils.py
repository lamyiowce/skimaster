"""Shared Playwright browser utilities."""

import asyncio

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

POPUP_SELECTORS = [
    "button#onetrust-accept-btn-handler",
    "button[aria-label='Dismiss sign-in info.']",
    "[data-testid='accept-btn']",
    "button.fc-cta-consent",
    "[aria-label='Close']",
]


async def create_browser_context(playwright, extra_http_headers: dict | None = None):
    """Launch headless Chromium and create a browser context."""
    browser = await playwright.chromium.launch(headless=True)
    ctx_kwargs = {"user_agent": USER_AGENT, "locale": "en-US"}
    if extra_http_headers:
        ctx_kwargs["extra_http_headers"] = extra_http_headers
    context = await browser.new_context(**ctx_kwargs)
    return browser, context


async def dismiss_popups(page):
    """Dismiss cookie banners and sign-in prompts on Booking.com."""
    for selector in POPUP_SELECTORS:
        try:
            btn = page.locator(selector)
            if await btn.is_visible(timeout=1500):
                await btn.click()
                await asyncio.sleep(0.3)
        except Exception:
            pass
