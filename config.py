"""Configuration for ski accommodation search."""

import os

# Group settings
GROUP_SIZE = 12
MIN_BEDROOMS = 4

# Travel dates
CHECK_IN = "2026-03-21"
CHECK_OUT = "2026-03-28"

# Requirements
REQUIRE_SAUNA = True
MAX_WALK_TO_LIFT_MINUTES = 5
MAX_PRICE_PER_PERSON_CHF = 500
CURRENCY = "CHF"

# Resorts to search (snow-safe, 150+ km slopes).
# Each key is the resort display name; the list contains all village/area search
# terms that belong to that resort.  Booking.com assigns a separate dest_id to
# each village, so listing multiple villages ensures we don't miss properties
# that sit in a quieter hamlet within the same ski domain.
RESORTS: dict[str, list[str]] = {
    # Austria
    "St. Anton am Arlberg, Austria": ["St. Anton am Arlberg, Austria"],
    "Ischgl, Austria": ["Ischgl, Austria"],
    "Sölden, Austria": ["Sölden, Austria"],
    # Saalbach and Hinterglemm are two distinct villages sharing one ski area
    "Saalbach-Hinterglemm, Austria": ["Saalbach, Austria", "Hinterglemm, Austria"],
    # Italy
    "Cervinia, Italy": ["Cervinia, Italy", "Valtournenche, Italy"],
    # Val Gardena spans three main villages on the Sella Ronda circuit
    "Selva di Val Gardena, Italy": [
        "Selva di Val Gardena, Italy",
        "Santa Cristina Val Gardena, Italy",
        "Ortisei, Italy",
    ],
    "Sestriere, Italy": ["Sestriere, Italy"],
    "Madonna di Campiglio, Italy": ["Madonna di Campiglio, Italy"],
    # France
    "Val Thorens, France": ["Val Thorens, France"],
    "Les Menuires, France": ["Les Menuires, France"],
    "Tignes, France": ["Tignes, France"],
    "Val d'Isère, France": ["Val d'Isère, France"],
    # Paradiski / La Plagne area: multiple distinct villages around the domain
    "La Plagne, France": [
        "La Plagne, France",
        "Peisey-Vallandry, France",
        "Les Coches, France",
        "Montchavin, France",
        "Champagny-en-Vanoise, France",
    ],
    # Les Arcs has four altitude stations; Arc 1950 is a separate Booking.com entry
    "Les Arcs, France": ["Les Arcs, France", "Arc 1950, France"],
    # Alpe d'Huez domain includes Vaujany (quieter village, same lifts)
    "Alpe d'Huez, France": ["Alpe d'Huez, France", "Vaujany, France"],
    # Portes du Soleil: Avoriaz sits above Morzine which has far more rental stock
    "Avoriaz, France": ["Avoriaz, France", "Morzine, France"],
    # Chamonix valley: Argentière is a second hub with direct lift access
    "Chamonix, France": ["Chamonix, France", "Argentière, France"],
    "La Rosière, France": ["La Rosière, France"],
}

# Output
OUTPUT_FILE = "results.md"
OUTPUT_CSV = "results.csv"

# OpenAI API
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-5.4"

# Cache files
DEST_IDS_CACHE = "dest_ids.json"
RAW_RESULTS_CACHE = "raw_results.json"
ENRICHED_RESULTS_CACHE = "enriched_results.json"
