"""Configuration for ski accommodation search."""

import os

# Group settings
GROUP_SIZE = 12
MIN_BEDROOMS = 4          # Enough bedrooms so no one sleeps in the living room
MAX_ACCOMMODATION_UNITS = 1  # Everyone must stay in the same apartment/chalet

# Travel dates
CHECK_IN = "2027-01-02"
CHECK_OUT = "2027-01-09"

# Requirements
REQUIRE_SAUNA = True
MIN_RATING = 8.0              # Minimum Booking.com review score (out of 10); properties with no rating are kept
MAX_WALK_TO_LIFT_MINUTES = 5
MAX_PRICE_PER_PERSON_CHF = 500
CURRENCY = "CHF"

# Resorts to search (snow-safe, 150+ km slopes).
# Each key is the resort display name; the list contains all village/area search
# terms that belong to that resort.  Booking.com assigns a separate dest_id to
# each village, so listing every altitude station ensures we don't miss properties
# in quieter hamlets within the same linked ski domain.
RESORTS: dict[str, list[str]] = {

    # ── AUSTRIA ────────────────────────────────────────────────────────────────

    # Ski Arlberg: 8 villages fully lift-linked under one pass since 2016.
    "St. Anton am Arlberg, Austria": [
        "St. Anton am Arlberg, Austria",
        "St. Christoph am Arlberg, Austria",
        "Stuben am Arlberg, Austria",
        "Lech am Arlberg, Austria",
        "Oberlech, Austria",
        "Zürs, Austria",
        "Warth, Austria",
        "Schröcken, Austria",
    ],

    # Silvretta Arena: only Ischgl and Samnaun are lift-linked across the border.
    "Ischgl, Austria": [
        "Ischgl, Austria",
        "Samnaun, Switzerland",
    ],

    # Sölden: standalone resort. Hochsölden (2 090 m) is the only altitude hamlet
    # with its own accommodation base directly on the slopes.
    "Sölden, Austria": [
        "Sölden, Austria",
        "Hochsölden, Austria",
    ],

    # Skicircus: four lift-linked villages under one pass.
    "Saalbach-Hinterglemm, Austria": [
        "Saalbach, Austria",
        "Hinterglemm, Austria",
        "Leogang, Austria",
        "Fieberbrunn, Austria",
    ],

    # ── ITALY ──────────────────────────────────────────────────────────────────

    # Matterhorn Ski Paradise (Italian side): two bases with rental stock.
    "Cervinia, Italy": [
        "Breuil-Cervinia, Italy",
        "Valtournenche, Italy",
    ],

    # Val Gardena / Sella Ronda: three main villages in the valley.
    "Selva di Val Gardena, Italy": [
        "Selva di Val Gardena, Italy",
        "Santa Cristina Val Gardena, Italy",
        "Ortisei, Italy",
    ],

    # Via Lattea: six Italian altitude stations + Montgenèvre on the French side
    # (cross-border pass, substantial rental stock).
    "Sestriere, Italy": [
        "Sestriere, Italy",
        "Sauze d'Oulx, Italy",
        "San Sicario, Italy",
        "Cesana Torinese, Italy",
        "Claviere, Italy",
        "Montgenèvre, France",
    ],

    # Skirama Dolomiti: Madonna di Campiglio + four lift-linked stations.
    # Marilleva 900 and 1400 share a Booking.com search term.
    "Madonna di Campiglio, Italy": [
        "Madonna di Campiglio, Italy",
        "Campo Carlo Magno, Italy",
        "Folgarida, Italy",
        "Marilleva, Italy",
        "Pinzolo, Italy",
    ],

    # ── FRANCE – Les 3 Vallées ──────────────────────────────────────────────────

    # Orelle has accommodation with gondola access directly into Val Thorens.
    "Val Thorens, France": [
        "Val Thorens, France",
        "Orelle, France",
    ],

    # Les Menuires has three searchable Booking.com clusters.
    "Les Menuires, France": [
        "Les Menuires, France",
        "Reberty, France",
        "Saint-Martin-de-Belleville, France",
    ],

    # ── FRANCE – Espace Killy ───────────────────────────────────────────────────

    # Tignes: five villages in the ski area; Le Lavachet has its own listings.
    "Tignes, France": [
        "Tignes Val Claret, France",
        "Tignes Le Lac, France",
        "Tignes Les Boisses, France",
        "Tignes Les Brévières, France",
        "Le Lavachet, France",
    ],

    # Val d'Isère: main village + two hamlets with direct lift access.
    "Val d'Isère, France": [
        "Val d'Isère, France",
        "La Daille, France",
        "Le Fornet, France",
    ],

    # ── FRANCE – Paradiski / La Plagne ─────────────────────────────────────────

    # 11 villages: 7 altitude stations + 4 lower villages. Each may have its own
    # Booking.com dest_id, so all are listed to ensure full coverage.
    "La Plagne, France": [
        "Plagne Centre, France",
        "Belle Plagne, France",
        "Plagne Bellecôte, France",
        "Plagne 1800, France",
        "Plagne Villages, France",
        "Plagne Soleil, France",
        "Aime-la-Plagne, France",
        "Montchavin, France",
        "Les Coches, France",
        "Montalbert, France",
        "Champagny-en-Vanoise, France",
    ],

    # ── FRANCE – Paradiski / Les Arcs ──────────────────────────────────────────

    # Four altitude stations + Peisey-Vallandry + Villaroger (rental chalets,
    # base of the Aiguille Rouge descent).
    "Les Arcs, France": [
        "Arc 1600, France",
        "Arc 1800, France",
        "Arc 1950, France",
        "Arc 2000, France",
        "Peisey-Vallandry, France",
        "Villaroger, France",
    ],

    # ── FRANCE – Alpe d'Huez Grand Domaine ─────────────────────────────────────

    # Six lift-linked villages sharing one pass.
    "Alpe d'Huez, France": [
        "Alpe d'Huez, France",
        "Vaujany, France",
        "Oz-en-Oisans, France",
        "Auris-en-Oisans, France",
        "Villard-Reculas, France",
        "La Garde-en-Oisans, France",
    ],

    # ── FRANCE – Portes du Soleil (French side) ─────────────────────────────────

    # Eight French-side villages. Ardent and Les Prodains are gondola-base
    # hamlets with rental chalets and a direct gondola link up to Avoriaz.
    "Avoriaz, France": [
        "Avoriaz, France",
        "Morzine, France",
        "Les Gets, France",
        "Châtel, France",
        "La Chapelle-d'Abondance, France",
        "Montriond, France",
        "Les Prodains, France",
        "Ardent, France",
    ],

    # ── FRANCE – Chamonix Valley ─────────────────────────────────────────────────

    # Five valley bases on the Mont Blanc Unlimited pass.
    "Chamonix, France": [
        "Chamonix-Mont-Blanc, France",
        "Argentière, France",
        "Les Houches, France",
        "Le Tour, France",
        "Vallorcine, France",
    ],

    # ── FRANCE – Espace San Bernardo ─────────────────────────────────────────────

    # Cross-border pass: La Rosière (France) + La Thuile (Italy), fully lift-linked.
    "La Rosière, France": [
        "La Rosière, France",
        "La Thuile, Italy",
    ],
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
