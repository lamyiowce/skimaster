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
from rank_results import filter_properties, rank_with_ai, write_results


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
    total_villages = sum(len(v) for v in config.RESORTS.values())
    print(f"  Resorts:          {len(config.RESORTS)} ({total_villages} villages)")
    print(f"  AI model:         {config.OPENAI_MODEL}")
    print(f"  AI key:           {'set' if config.OPENAI_API_KEY else 'NOT SET (fallback ranking)'}")
    print(f"  Output:           {config.OUTPUT_FILE}, {config.OUTPUT_CSV}")
    print("=" * 60)
    print()


def save_json(data, path: str):
    """Save data to JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"Cached results to {path}")


def load_json(path: str) -> list[dict]:
    """Load data from JSON file."""
    with open(path) as f:
        return json.load(f)


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
        print(f"Test run: limiting to {list(resorts.keys())}\n")

    if args.from_enriched:
        # Skip to filtering + ranking
        print(f"Loading enriched results from {args.from_enriched}...")
        properties = load_json(args.from_enriched)
        print(f"Loaded {len(properties)} enriched properties.")

    elif args.from_cache:
        # Skip scraping, redo geo + ranking
        print(f"Loading raw results from {args.from_cache}...")
        properties = load_json(args.from_cache)
        print(f"Loaded {len(properties)} raw properties.")

        # Step 3+4: Geocode + find lifts
        print("\n--- Step 3+4: Geocoding & Lift Lookup ---")
        properties = asyncio.run(enrich_all(properties))
        save_json(properties, config.ENRICHED_RESULTS_CACHE)

    else:
        # Full pipeline
        # Step 1: Resolve dest IDs
        print("--- Step 1: Resolving Booking.com destination IDs ---")
        villages = [v for vs in resorts.values() for v in vs]
        dest_ids = asyncio.run(resolve_dest_ids(villages))
        print(f"Resolved {len(dest_ids)}/{len(villages)} villages.\n")

        # Step 2: Scrape
        print("--- Step 2: Scraping Booking.com ---")
        properties = asyncio.run(scrape_all(dest_ids, resorts=resorts))
        save_json(properties, config.RAW_RESULTS_CACHE)

        if args.scrape_only:
            print(f"\n--scrape-only: Done. {len(properties)} properties saved to {config.RAW_RESULTS_CACHE}")
            return

        # Step 3+4: Geocode + find lifts
        print("\n--- Step 3+4: Geocoding & Lift Lookup ---")
        properties = asyncio.run(enrich_all(properties))
        save_json(properties, config.ENRICHED_RESULTS_CACHE)

    # Step 5: Filter
    print("\n--- Step 5: Filtering ---")
    filtered = filter_properties(properties)

    if not filtered:
        print("\nNo properties passed the filters. Try relaxing constraints.")
        sys.exit(1)

    # Step 6: AI Ranking
    print("\n--- Step 6: AI Ranking ---")
    ai_ranking = rank_with_ai(filtered)

    # Write outputs
    print("\n--- Writing Results ---")
    write_results(ai_ranking, filtered, config.OUTPUT_FILE, config.OUTPUT_CSV)

    print(f"\nDone! {len(filtered)} properties ranked.")
    print(f"  Report: {config.OUTPUT_FILE}")
    print(f"  Data:   {config.OUTPUT_CSV}")


if __name__ == "__main__":
    main()
