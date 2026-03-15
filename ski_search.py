#!/usr/bin/env python3
"""SkiMaster — Automated ski accommodation search pipeline.

Usage:
    python ski_search.py                                    # Full pipeline
    python ski_search.py --from-cache raw_results.json      # Skip scraping, redo geo + ranking
    python ski_search.py --from-enriched enriched.json      # Skip to filtering + ranking
    python ski_search.py --scrape-only                      # Scrape without geo or AI
"""

import argparse
import asyncio
import json
import sys

import config
from resolve_dest_ids import resolve_dest_ids, all_villages
from scrape_booking import scrape_all
from geo_lifts import enrich_all
from rank_results import filter_properties, deduplicate_properties, rank_with_ai, write_results
from send_email import send_summary_email


def print_banner():
    """Print config summary banner."""
    print("=" * 60)
    print("  SkiMaster — Group Ski Accommodation Search")
    print("=" * 60)
    print(f"  Group size:       {config.GROUP_SIZE}")
    print(f"  Dates:            {config.CHECK_IN} → {config.CHECK_OUT}")
    print(f"  Budget:           max {config.MAX_PRICE_PER_PERSON_CHF} {config.CURRENCY}/person")
    print(f"  Sauna required:   {config.REQUIRE_SAUNA}")
    print(f"  Max walk to lift: {config.MAX_WALK_TO_LIFT_MINUTES} min")
    print(f"  Resorts:          {len(config.RESORTS)} ({len(all_villages())} villages)")
    print(f"  AI model:         {config.OPENAI_MODEL}")
    print(f"  AI key:           {'set' if config.OPENAI_API_KEY else 'NOT SET (fallback ranking)'}")
    print(f"  Output:           {config.OUTPUT_FILE}, {config.OUTPUT_CSV}")
    print("=" * 60)
    print()


def save_json(data: list[dict], path: str, resorts: dict):
    """Save property list to JSON, embedding the resort groups that produced it."""
    payload = {
        "resorts_searched": list(resorts.keys()),
        "properties": data,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    print(f"Cached results to {path}")


def load_json(path: str, expected_resorts: dict) -> list[dict]:
    """Load a property list from JSON and warn if it came from a different resort set.

    Handles both the current wrapped format and plain-list files from older runs.
    """
    with open(path) as f:
        raw = json.load(f)

    if isinstance(raw, list):
        # Legacy format — no metadata available
        print(f"  Warning: {path} has no metadata (old format); resort coverage unknown.")
        return raw

    properties = raw["properties"]
    cached_resorts = set(raw.get("resorts_searched", []))
    expected = set(expected_resorts.keys())

    missing = expected - cached_resorts
    extra = cached_resorts - expected

    if missing:
        print(f"  Warning: cache is missing {len(missing)} resort(s) vs current config:")
        for r in sorted(missing):
            print(f"    - {r}")
    if extra:
        print(f"  Warning: cache contains {len(extra)} resort(s) not in current config:")
        for r in sorted(extra):
            print(f"    + {r}")
    if not missing and not extra:
        print(f"  Resort coverage matches config ({len(cached_resorts)} resort(s)).")

    return properties


def main():
    parser = argparse.ArgumentParser(description="SkiMaster — Ski accommodation search")
    parser.add_argument(
        "--from-cache",
        metavar="FILE",
        help="Skip resolving + scraping, load raw results from JSON and redo geo + ranking",
    )
    parser.add_argument(
        "--from-enriched",
        metavar="FILE",
        help="Skip everything before filtering + ranking, load enriched results from JSON",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Scrape without geocoding or AI ranking",
    )
    parser.add_argument(
        "--resort",
        metavar="NAME",
        help="Run only for a single resort group (substring match, e.g. 'Les Arcs')",
    )
    args = parser.parse_args()

    print_banner()

    # Apply optional single-resort filter
    resorts = config.RESORTS
    if args.resort:
        resorts = {k: v for k, v in config.RESORTS.items() if args.resort.lower() in k.lower()}
        if not resorts:
            print(f"No resort matching '{args.resort}'. Available resorts:")
            for name in config.RESORTS:
                print(f"  {name}")
            sys.exit(1)
        print("=" * 60)
        print("  [DRY RUN]")
        for resort_name, villages in resorts.items():
            print(f"  Resort : {resort_name}")
            for v in villages:
                print(f"    village: {v}")
        print("=" * 60)
        print()

    if args.from_enriched:
        # Skip to filtering + ranking
        print(f"Loading enriched results from {args.from_enriched}...")
        properties = load_json(args.from_enriched, expected_resorts=resorts)
        if args.resort:
            before = len(properties)
            properties = [p for p in properties if p.get("resort") in resorts]
            print(f"  [DRY RUN] Kept {len(properties)}/{before} properties for {list(resorts.keys())}")
        print(f"Loaded {len(properties)} enriched properties.")

    elif args.from_cache:
        # Skip scraping, redo geo + ranking
        print(f"Loading raw results from {args.from_cache}...")
        properties = load_json(args.from_cache, expected_resorts=resorts)
        if args.resort:
            before = len(properties)
            properties = [p for p in properties if p.get("resort") in resorts]
            print(f"  [DRY RUN] Kept {len(properties)}/{before} properties for {list(resorts.keys())}")
        print(f"Loaded {len(properties)} raw properties.")

        # Step 3+4: Geocode + find lifts
        print("\n--- Step 3+4: Geocoding & Lift Lookup ---")
        properties = asyncio.run(enrich_all(properties))
        save_json(properties, config.ENRICHED_RESULTS_CACHE, resorts=resorts)

    else:
        # Full pipeline
        # Step 1: Resolve dest IDs
        print("--- Step 1: Resolving Booking.com destination IDs ---")
        villages = all_villages(resorts)
        dest_ids = asyncio.run(resolve_dest_ids(villages))
        print(f"Resolved {len(dest_ids)}/{len(villages)} villages.\n")

        # Step 2: Scrape
        print("--- Step 2: Scraping Booking.com ---")
        properties = asyncio.run(scrape_all(dest_ids, resorts=resorts, debug=bool(args.resort)))
        save_json(properties, config.RAW_RESULTS_CACHE, resorts=resorts)

        if args.scrape_only:
            print(f"\n--scrape-only: Done. {len(properties)} properties saved to {config.RAW_RESULTS_CACHE}")
            return

        # Step 3+4: Geocode + find lifts
        print("\n--- Step 3+4: Geocoding & Lift Lookup ---")
        properties = asyncio.run(enrich_all(properties))
        save_json(properties, config.ENRICHED_RESULTS_CACHE, resorts=resorts)

    # Step 5: Filter
    print("\n--- Step 5: Filtering ---")
    filtered = filter_properties(properties)

    if not filtered:
        print("\nNo properties passed the filters. Try relaxing constraints.")
        sys.exit(1)

    # Step 5b: Deduplicate (after filtering, before ranking — keeps best version)
    filtered = deduplicate_properties(filtered)

    # Step 6: AI Ranking
    print("\n--- Step 6: AI Ranking ---")
    ai_ranking = rank_with_ai(filtered)

    # Write outputs
    print("\n--- Writing Results ---")
    write_results(ai_ranking, filtered, config.OUTPUT_FILE, config.OUTPUT_CSV)

    n_total = len(properties)
    n_with_lift = sum(1 for p in filtered if p.get("nearest_lift_name"))
    n_no_price  = sum(1 for p in filtered if p.get("price") is None)
    print(f"\n{'=' * 60}")
    print(f"  Pipeline complete")
    print(f"  Properties enriched : {n_total}")
    print(f"  Passed filters      : {len(filtered)}")
    print(f"    with lift data    : {n_with_lift}")
    print(f"    no price listed   : {n_no_price}")
    print(f"  Report: {config.OUTPUT_FILE}")
    print(f"  Data  : {config.OUTPUT_CSV}")
    print(f"{'=' * 60}")

    # Send email summary if SMTP is configured
    send_summary_email(config.OUTPUT_FILE)


if __name__ == "__main__":
    main()
