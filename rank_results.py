"""Steps 5 & 6: Filter properties by criteria and rank with Claude AI.

Filtering:
- Reject properties beyond MAX_WALK_TO_LIFT_MINUTES (no lift data = too far)
- Reject over-budget properties (budget scales with capacity)

AI Ranking:
- Send filtered properties to Claude for top-5 ranking
- Fallback: basic Markdown table sorted by lift distance + price
"""

import csv
import re
from datetime import datetime

import openai

import config

# Compiled once at module level for efficiency
_BEDROOM_PATTERNS = [
    re.compile(r"(\d+)\s*bed\s*rooms?", re.IGNORECASE),
    re.compile(r"(\d+)\s*bedrooms?", re.IGNORECASE),
    re.compile(r"(\d+)\s*(?:br|bdr|bdrm)s?\b", re.IGNORECASE),
]
_CAPACITY_PATTERNS = [
    re.compile(r"sleeps\s+(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s*guests?", re.IGNORECASE),
    re.compile(r"for\s+(\d+)\s*people", re.IGNORECASE),
    re.compile(r"capacity[:\s]+(\d+)", re.IGNORECASE),
    re.compile(r"up\s+to\s+(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s*person", re.IGNORECASE),
    re.compile(r"(\d+)\s*beds\b", re.IGNORECASE),
]
_MULTI_UNIT_PATTERNS = [
    re.compile(r"\b[2-9]\s*(?:apartments?|units?|chalets?|villas?)\b"),
    re.compile(r"\bapartments?\s*[2-9]\b"),
    re.compile(r"\bmultiple\s+(?:apartments?|units?)\b"),
]


def _listing_text(prop: dict) -> str:
    return prop.get("card_text", "") + " " + prop.get("name", "")


def _first_int_match(
    text: str, patterns: list[re.Pattern], min_val: int, max_val: int
) -> int | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            val = int(match.group(1))
            if min_val <= val <= max_val:
                return val
    return None


def parse_bedroom_count(prop: dict) -> int | None:
    """Extract bedroom count from listing text."""
    return _first_int_match(_listing_text(prop), _BEDROOM_PATTERNS, 1, 20)


def is_multi_unit(prop: dict) -> bool:
    """Return True if the listing appears to be multiple separate units."""
    text = _listing_text(prop).lower()
    return any(p.search(text) for p in _MULTI_UNIT_PATTERNS)


def parse_capacity(prop: dict) -> int | None:
    """Extract property capacity from listing text."""
    return _first_int_match(_listing_text(prop), _CAPACITY_PATTERNS, 4, 30)


def calculate_max_budget(capacity: int | None) -> float:
    """Calculate max budget based on capacity. Budget scales with property capacity."""
    if not capacity:
        return config.GROUP_SIZE * config.MAX_PRICE_PER_PERSON_CHF
    effective = min(capacity, config.GROUP_SIZE)
    return effective * config.MAX_PRICE_PER_PERSON_CHF


def calculate_num_nights() -> int:
    """Calculate number of nights from check-in/out dates."""
    try:
        ci = datetime.strptime(config.CHECK_IN, "%Y-%m-%d")
        co = datetime.strptime(config.CHECK_OUT, "%Y-%m-%d")
        return (co - ci).days
    except ValueError:
        return 7


def filter_properties(properties: list[dict]) -> list[dict]:
    """Apply distance, budget, bedroom count, and single-unit filters."""
    filtered = []
    seen_urls = set()
    num_nights = calculate_num_nights()
    rejected_distance = 0
    rejected_budget = 0
    rejected_multi_unit = 0
    rejected_bedrooms = 0
    rejected_rating = 0
    rejected_duplicate = 0

    for prop in properties:
        # Deduplicate by URL (keep first/highest-ranked occurrence)
        url = prop.get("url", "")
        if url and url in seen_urls:
            rejected_duplicate += 1
            continue
        if url:
            seen_urls.add(url)

        # Filter: single accommodation unit only (no multi-apartment setups)
        if config.MAX_ACCOMMODATION_UNITS == 1 and is_multi_unit(prop):
            rejected_multi_unit += 1
            continue

        # Filter by lift distance (no lift data = assume too far)
        walk_min = prop.get("nearest_lift_walk_minutes")
        if walk_min is None or walk_min > config.MAX_WALK_TO_LIFT_MINUTES:
            rejected_distance += 1
            continue

        # Filter by budget
        price = prop.get("price")
        capacity = parse_capacity(prop)
        prop["parsed_capacity"] = capacity
        if price is not None:
            max_budget = calculate_max_budget(capacity)

            if price > max_budget:
                rejected_budget += 1
                continue

            # Calculate per-person (total stay)
            effective_guests = min(capacity, config.GROUP_SIZE) if capacity else config.GROUP_SIZE
            prop["price_per_person"] = round(price / effective_guests, 2)
        else:
            prop["price_per_person"] = None

        # Filter: minimum rating (keep properties with no rating)
        rating = prop.get("rating")
        if rating is not None and rating < config.MIN_RATING:
            rejected_rating += 1
            continue

        # Filter: enough bedrooms so no one sleeps in the living room
        bedroom_count = parse_bedroom_count(prop)
        prop["bedroom_count"] = bedroom_count
        if bedroom_count is not None and bedroom_count < config.MIN_BEDROOMS:
            rejected_bedrooms += 1
            continue

        filtered.append(prop)

    print(f"\nFiltering results:")
    print(f"  Input: {len(properties)} properties")
    print(f"  Rejected (duplicate): {rejected_duplicate}")
    print(f"  Rejected (multiple units): {rejected_multi_unit}")
    print(f"  Rejected (too far from lift): {rejected_distance}")
    print(f"  Rejected (over budget): {rejected_budget}")
    print(f"  Rejected (rating below {config.MIN_RATING}): {rejected_rating}")
    print(f"  Rejected (too few bedrooms): {rejected_bedrooms}")
    print(f"  Remaining: {len(filtered)} properties")

    return filtered


def build_ai_prompt(properties: list[dict]) -> str:
    """Build a prompt for Claude to rank properties."""
    num_nights = calculate_num_nights()

    prop_descriptions = []
    for i, p in enumerate(properties, 1):
        lines = [
            f"### Property {i}: {p.get('name', 'Unknown')}",
            f"- Resort: {p.get('resort', 'Unknown')}",
            f"- Price: {p.get('price_text', 'Unknown')} ({config.CURRENCY} total for stay)",
        ]
        if p.get("price_per_person"):
            lines.append(f"- Price per person (total stay): {config.CURRENCY} {p['price_per_person']}")
        if p.get("rating"):
            lines.append(f"- Rating: {p['rating']}/10 ({p.get('review_count', '?')} reviews)")
        if p.get("nearest_lift_name"):
            lines.append(
                f"- Nearest lift: {p['nearest_lift_name']} ({p['nearest_lift_type']}) "
                f"— {p['nearest_lift_distance_m']}m, {p['nearest_lift_walk_minutes']} min walk"
            )
        else:
            lines.append("- Nearest lift: Unknown")
        if p.get("bedroom_count"):
            lines.append(f"- Bedrooms: {p['bedroom_count']}")
        if p.get("parsed_capacity"):
            lines.append(f"- Capacity: sleeps {p['parsed_capacity']}")
        if p.get("street_address"):
            lines.append(f"- Address: {p['street_address']}")
        lines.append(f"- URL: {p.get('url', 'N/A')}")
        prop_descriptions.append("\n".join(lines))

    return f"""You are helping a group of {config.GROUP_SIZE} friends find the best ski accommodation.

## Requirements
- Group size: {config.GROUP_SIZE} friends
- Dates: {config.CHECK_IN} to {config.CHECK_OUT} ({num_nights} nights)
- Need: **Single** chalet or large apartment with sauna — everyone must stay together in one unit
- At least {config.MIN_BEDROOMS} bedrooms — no one sleeps in the living room
- Max {config.MAX_WALK_TO_LIFT_MINUTES} minute walk to a ski lift
- Budget: max {config.MAX_PRICE_PER_PERSON_CHF} CHF per person for the full stay
  - Budget scales with capacity: a property sleeping N pays max N × {config.MAX_PRICE_PER_PERSON_CHF} CHF (capped at {config.GROUP_SIZE} × {config.MAX_PRICE_PER_PERSON_CHF} = {config.GROUP_SIZE * config.MAX_PRICE_PER_PERSON_CHF} CHF)
- Currency: {config.CURRENCY}

## Properties to rank

{chr(10).join(prop_descriptions)}

## Instructions

Rank these properties and give me your **top 5** recommendations, ordered by overall suitability.

For each property, provide:
1. **Name** and resort
2. **Price per person** in CHF (total for the stay, not per night)
3. **Nearest lift** — name, type, and walk time
4. **Rating** and review count
5. **Booking link**
6. **Red flags** — any concerns (too expensive, far from lifts, low rating, small capacity, too few bedrooms, multiple separate units, etc.)
7. **Why it's ranked here** — brief justification

Format as a numbered Markdown list. After the top 5, add a brief summary of the overall search quality and any general observations."""


def rank_with_ai(properties: list[dict]) -> str:
    """Send properties to OpenAI for AI ranking."""
    api_key = config.OPENAI_API_KEY
    if not api_key:
        print("  No OPENAI_API_KEY — using fallback ranking")
        return fallback_ranking(properties)

    print(f"  Sending {len(properties)} properties to OpenAI for ranking...")

    try:
        client = openai.OpenAI(api_key=api_key)
        prompt = build_ai_prompt(properties)

        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            max_completion_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.choices[0].message.content
        print("  AI ranking complete.")
        return response_text

    except Exception as e:
        print(f"  AI ranking failed: {e}")
        print("  Falling back to basic ranking...")
        return fallback_ranking(properties)


def fallback_ranking(properties: list[dict]) -> str:
    """Generate a basic Markdown table sorted by lift distance and price."""
    # Sort: properties with lift data first (by distance), then unknowns, then by price
    def sort_key(p):
        walk = p.get("nearest_lift_walk_minutes")
        price = p.get("price") or float("inf")
        if walk is not None:
            return (0, walk, price)
        return (1, 0, price)

    sorted_props = sorted(properties, key=sort_key)

    lines = [
        "# Ski Accommodation Results (Auto-ranked)",
        "",
        "*AI ranking unavailable — sorted by lift proximity and price.*",
        "",
        "| # | Name | Resort | Price (CHF) | CHF/person | Lift | Walk (min) | Rating | Link |",
        "|---|------|--------|-------------|------------|------|------------|--------|------|",
    ]

    for i, p in enumerate(sorted_props[:20], 1):
        name = p.get("name", "?")[:40]
        resort = p.get("resort", "?")[:20]
        price = p.get("price_text", "?")
        ppn = p.get("price_per_person", "?")
        lift = (p.get("nearest_lift_name") or "?")[:25]
        walk = p.get("nearest_lift_walk_minutes", "?")
        rating = p.get("rating", "?")
        url = p.get("url", "")
        link = f"[Book]({url})" if url else "N/A"

        lines.append(f"| {i} | {name} | {resort} | {price} | {ppn} | {lift} | {walk} | {rating} | {link} |")

    return "\n".join(lines)


def write_results(
    ai_ranking: str, properties: list[dict], output_md: str, output_csv: str
):
    """Write results to Markdown and CSV files."""
    num_nights = calculate_num_nights()

    # Markdown report
    md_lines = [
        "# Ski Accommodation Search Results",
        "",
        f"**Search date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Dates:** {config.CHECK_IN} to {config.CHECK_OUT} ({num_nights} nights)",
        f"**Group size:** {config.GROUP_SIZE}",
        f"**Budget:** max {config.MAX_PRICE_PER_PERSON_CHF} CHF/person",
        f"**Max walk to lift:** {config.MAX_WALK_TO_LIFT_MINUTES} min",
        f"**Properties analyzed:** {len(properties)}",
        "",
        "---",
        "",
        ai_ranking,
        "",
        "---",
        "",
        f"*Generated by SkiMaster • {len(config.RESORTS)} resorts searched*",
    ]

    with open(output_md, "w") as f:
        f.write("\n".join(md_lines))
    print(f"  Wrote Markdown report: {output_md}")

    # CSV export
    csv_fields = [
        "name",
        "resort",
        "price",
        "price_text",
        "price_per_person",
        "rating",
        "review_count",
        "parsed_capacity",
        "bedroom_count",
        "nearest_lift_name",
        "nearest_lift_type",
        "nearest_lift_distance_m",
        "nearest_lift_walk_minutes",
        "street_address",
        "latitude",
        "longitude",
        "url",
    ]

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for prop in properties:
            writer.writerow(prop)
    print(f"  Wrote CSV export: {output_csv}")
