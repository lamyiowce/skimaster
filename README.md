# SkiMaster

Automated ski accommodation search for group trips. Scrapes Booking.com across European resorts, enriches results with ski lift proximity data, filters by constraints, and ranks options with AI.

## Architecture

Six-stage pipeline, each stage cached to JSON so you can re-run from any point:

```
config.py (trip params, resorts, constraints)
    │
    ▼
resolve_dest_ids.py ──► dest_ids.json
    Playwright → Booking.com search → extract dest_id from URL
    │
    ▼
scrape_booking.py ──► raw_results.json
    Playwright → search results pages → property detail pages
    Extracts: name, price, rating, address, coordinates
    │
    ▼
geo_lifts.py ──► enriched_results.json
    Nominatim API → geocode addresses (fallback if no coords from Booking)
    Overpass API → find ski lifts within 800m, calc walk time
    │
    ▼
rank_results.py ──► results.md, results.csv
    Filter by MAX_WALK_TO_LIFT_MINUTES and budget
    Rank via OpenAI API (fallback: sort by distance + price)
```

**Entry point:** `ski_search.py` orchestrates the pipeline. Supports `--from-cache`, `--from-enriched`, `--scrape-only` to skip stages.

**Shared utilities:** `browser_utils.py` has the Playwright browser setup, user agent, and popup dismissal used by both `resolve_dest_ids.py` and `scrape_booking.py`.

**Standalone helper:** `find_dest_id.py` resolves a single resort's Booking.com dest_id (for adding new resorts to config).

## Key config values (`config.py`)

All trip parameters live here: dates, group size, min bedrooms, resort list, budget per person, currency, sauna requirement, max walk distance to lifts. Also holds API keys (from env vars) and cache/output filenames.

## External dependencies

- **Playwright** (Chromium) — browser automation for Booking.com
- **httpx** — async HTTP for Nominatim + Overpass APIs
- **openai** — AI ranking (uses `OPENAI_API_KEY` env var)

## CI

`.github/workflows/ski-search.yml` — manual dispatch workflow. Accepts optional date/price/skip-scrape overrides. Runs the pipeline, commits results, uploads artifacts.

## Adding features — what to know

- Scraping is rate-limited with delays; respect this to avoid blocks.
- Nominatim has a 1 req/s policy; `geo_lifts.py` enforces this.
- Properties missing coordinates get geocoded by address; those missing both are kept but lack lift data.
- Budget filtering scales with property capacity (`no_rooms` field), not just per-person price.
- The AI ranking prompt is in `rank_results.py`; it gets the full filtered property list as JSON.
- All cache files are plain JSON; the pipeline reads/writes them directly.
