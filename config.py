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

# Resorts to search (snow-safe, 150+ km slopes)
RESORTS = [
    # Austria
    "St. Anton am Arlberg, Austria",
    "Ischgl, Austria",
    "Sölden, Austria",
    "Saalbach-Hinterglemm, Austria",
    # Italy
    "Cervinia, Italy",
    "Selva di Val Gardena, Italy",
    "Sestriere, Italy",
    "Madonna di Campiglio, Italy",
    # France
    "Val Thorens, France",
    "Les Menuires, France",
    "Tignes, France",
    "Val d'Isère, France",
    "La Plagne, France",
    "Les Arcs, France",
    "Alpe d'Huez, France",
    "Avoriaz, France",
    "Chamonix, France",
    "La Rosière, France",
]

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
