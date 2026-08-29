"""Central configuration for HeatGov AI.

Every constant that describes *what* we study (the area, the period, the heat
threshold) lives here so the data pipeline, the ML training script and the API
all read from a single source of truth.

Secrets are NOT stored here: they are read from the .env file at the project
root via python-dotenv.

THE THESIS
----------
Day-time and night-time thermal danger zones in Central Los Angeles do NOT
overlap: 0% intersection between the 10% hottest tiles at 15:00 (afternoon peak)
and at 22:00 (night). The FortyGuard API anchors requests to GMT-8, so these are
local hours, not UTC.

A single-timepoint heatmap therefore misses half the population at risk.
HeatGov AI is the first tool to combine both danger maps into a single
vulnerability score, weighted by CalEnviroScreen socio-demographic factors.

Measured in Step 2 over 8,674 tiles; see docs/fortyguard-api-findings.md.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from dotenv import load_dotenv

# --------------------------------------------------------------- paths

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"            # verbatim FortyGuard API responses (cache)
PROCESSED_DIR = DATA_DIR / "processed"  # engineered features, model-ready tables
EXTERNAL_DIR = DATA_DIR / "external"  # CalEnviroScreen, Census, tree canopy
MODELS_DIR = PROJECT_ROOT / "models"  # trained model artifacts

for _directory in (RAW_DIR, PROCESSED_DIR, EXTERNAL_DIR, MODELS_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------- secrets

load_dotenv(PROJECT_ROOT / ".env")

FORTYGUARD_API_KEY = os.getenv("FORTYGUARD_API_KEY")
FORTYGUARD_BASE_URL = os.getenv("FORTYGUARD_BASE_URL", "https://api.fortyguard.com")

# Gemini keys, one or several.
#
# The free tier caps requests per minute per key, and a demo that runs the
# tool-calling loop three or four times can exhaust one key mid-answer. So the
# agent accepts a pool: set GEMINI_API_KEYS to a comma-separated list and it
# moves to the next key when Google returns 429 / RESOURCE_EXHAUSTED.
#
# GEMINI_API_KEY (singular) is still read and still works; it is simply the
# one-element case. Duplicates are dropped so a .env that sets both does not
# retry the same exhausted key twice.
def _gemini_keys() -> list[str]:
    raw = f"{os.getenv('GEMINI_API_KEYS', '')},{os.getenv('GEMINI_API_KEY', '')}"
    seen: list[str] = []
    for key in (part.strip() for part in raw.split(",")):
        if key and key not in seen:
            seen.append(key)
    return seen


GEMINI_API_KEYS: list[str] = _gemini_keys()
GEMINI_API_KEY: str | None = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else None
# Gemini model names are retired over time. Verified against the live API on
# 2026-08-27: gemini-2.0-flash returns 404, and gemini-2.5-flash returns 404
# with the message "Please update your code to use models/gemini-3.6-flash".
# gemini-3.6-flash answered a function-calling probe in 2.6 s, versus 27 s for
# gemini-flash-latest, so it is pinned here rather than tracking "latest",
# whose behaviour could shift mid-demo.
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
RETIRED_GEMINI_MODELS = {
    "gemini-2.0-flash": DEFAULT_GEMINI_MODEL,
    "gemini-2.5-flash": DEFAULT_GEMINI_MODEL,
    "gemini-1.5-flash": DEFAULT_GEMINI_MODEL,
    "gemini-1.5-pro": DEFAULT_GEMINI_MODEL,
}

_configured_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
if _configured_model in RETIRED_GEMINI_MODELS:
    GEMINI_MODEL = RETIRED_GEMINI_MODELS[_configured_model]
    print(
        f"[config] GEMINI_MODEL={_configured_model!r} has been retired by Google; "
        f"using {GEMINI_MODEL!r} instead. Update .env to silence this."
    )
else:
    GEMINI_MODEL = _configured_model
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")

# --------------------------------------------------------------- study area

CITY_NAME = "Central Los Angeles"
CITY_STATE = "CA"

# Bounding box of the pilot area. FortyGuard expects [longitude, latitude].
#
# The area deliberately spans a strong land-cover gradient, which is what gives
# the ML model something to learn from:
#   * south  - Downtown, Skid Row, Historic Core: dense concrete, no canopy
#   * middle - Echo Park, Silver Lake: mixed residential, partial canopy
#   * north  - southern edge of Griffith Park: hills, dense tree canopy
LON_WEST = -118.3000
LON_EAST = -118.2200
LAT_SOUTH = 34.0300
LAT_NORTH = 34.1400

# GeoJSON ring, counter-clockwise, first point repeated to close the polygon.
CENTRAL_LA_RING: list[list[float]] = [
    [LON_WEST, LAT_SOUTH],   # south-west
    [LON_EAST, LAT_SOUTH],   # south-east
    [LON_EAST, LAT_NORTH],   # north-east
    [LON_WEST, LAT_NORTH],   # north-west
    [LON_WEST, LAT_SOUTH],   # close the ring
]

# Payload shape expected by FortyGuardClient.create_heatmap(polygon_aoi=...)
CENTRAL_LA_POLYGON: dict = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": CITY_NAME},
            "geometry": {"type": "Polygon", "coordinates": [CENTRAL_LA_RING]},
        }
    ],
}

# Approximate centroid, handy for point endpoints (environmental parameters).
CENTROID_LON = (LON_WEST + LON_EAST) / 2
CENTROID_LAT = (LAT_SOUTH + LAT_NORTH) / 2


# Reference point for the maritime-influence control feature.
#
# Step 2 found that heat in Central Los Angeles is governed by distance from the
# ocean, not by land cover: the northern band (Griffith Park, high tree canopy)
# records the HIGHEST heat dose, because it sits furthest inland. Without this
# control a model would conclude that trees cause heat.
SANTA_MONICA_PIER_LON = -118.4970
SANTA_MONICA_PIER_LAT = 34.0089


def study_area_km2() -> float:
    """Approximate bounding-box area in square kilometres."""
    mid_lat_rad = math.radians(CENTROID_LAT)
    width_km = abs(LON_EAST - LON_WEST) * 111.320 * math.cos(mid_lat_rad)
    height_km = abs(LAT_NORTH - LAT_SOUTH) * 110.574
    return width_km * height_km


# --------------------------------------------------------------- study period

STUDY_START_DATE = "2025-07-01"
STUDY_END_DATE = "2025-07-31"
TEST_DATE = "2025-07-15"          # single representative day

# OBSERVED BEHAVIOUR: `start_time` is interpreted as LOCAL time, not UTC.
#
# Measured on 2025-07-15 over this exact polygon (see docs/fortyguard-api-findings.md):
#   start_time="15:00" -> mean 28.85 C, which matches the mean of the daily
#                         max_temperature (28.98 C). This is the thermal peak.
#   start_time="22:00" -> mean 18.80 C, i.e. night-time.
# Had these been UTC, 15:00 UTC would be 08:00 local and could not be the peak.
HOUR_AFTERNOON = "15:00"   # local, daily thermal peak
HOUR_NIGHT = "22:00"       # local, night-time control layer
LOCAL_UTC_OFFSET_HOURS = -7  # PDT in July, for reference only

# time_of_measure is expensive over a long window; one week is enough to
# establish the modal peak hour of each tile.
PEAK_HOUR_WINDOW_START = "2025-07-01"
PEAK_HOUR_WINDOW_END = "2025-07-07"

# --------------------------------------------------------------- analysis parameters

HEAT_THRESHOLD_C = 30.0           # exceedance / persistence threshold, Celsius
HEAT_DIRECTION = "above"
GRANULARITY_M = 100               # spatial resolution in meters (60, 80 or 100)

# FortyGuard filter_type codes.
FILTER_SINGLE_HOUR = 1
FILTER_RANGE_OF_HOURS = 2
FILTER_SINGLE_DAY = 3
FILTER_RANGE_OF_DAYS = 4

ANALYTIC_TYPES: tuple[str, ...] = (
    "tcm",
    "time_of_measure",
    "exceedance",
    "persistence",
)

# --------------------------------------------------------------- env params sampling

# Environmental parameters are a point endpoint, so we sample a regular grid.
# The study area is taller than it is wide, hence 3 columns x 5 rows = 15 points.
ENV_GRID_COLS = 3
ENV_GRID_ROWS = 5
ENV_PARAMS_HOUR = HOUR_AFTERNOON  # sample at the thermal peak, matching feature names


def env_param_grid() -> list[tuple[float, float]]:
    """Return (longitude, latitude) sample points inset from the polygon edges."""
    points: list[tuple[float, float]] = []
    for row in range(ENV_GRID_ROWS):
        lat = LAT_SOUTH + (LAT_NORTH - LAT_SOUTH) * (row + 0.5) / ENV_GRID_ROWS
        for col in range(ENV_GRID_COLS):
            lon = LON_WEST + (LON_EAST - LON_WEST) * (col + 0.5) / ENV_GRID_COLS
            points.append((round(lon, 6), round(lat, 6)))
    return points


# --------------------------------------------------------------- model features

# Label: CalEnviroScreen 4.0 composite percentile.
#
# IMPORTANT HONESTY NOTE. CalEnviroScreen 4.0 contains no heat indicator of any
# kind - no temperature, no heat waves. We are NOT reproducing an official heat
# vulnerability index. We are testing whether hyperlocal heat metrics predict an
# official environmental-justice score. Say it that way in the pitch.
LABEL_COLUMN = "CIscoreP"

# Two feature sets, trained and reported separately.
#
# CES 4.0's "Population Characteristics" half already contains poverty,
# unemployment and housing burden. Feeding median income back in as a predictor
# means partly predicting the label from its own ingredients, which inflates R2.
# FEATURES_FORTYGUARD is the honest measure of what FortyGuard data alone buys;
# FEATURES_FULL is the operational model. Report both.
FEATURES_FORTYGUARD: tuple[str, ...] = (
    "temp_max_15h",
    "temp_max_22h",
    "exceedance_hours_30C",
    "persistence_max_hours",
    "peak_hour_mode",
    "elevation_m",
    "distance_to_coast_km",
)

FEATURES_SOCIO: tuple[str, ...] = (
    "pop_over_65_pct",
    "median_income",
    "pop_density",
)

FEATURES_LANDCOVER: tuple[str, ...] = (
    "impervious_surface_pct",
    "tree_canopy_pct",
)

FEATURES_FULL: tuple[str, ...] = (
    FEATURES_FORTYGUARD + FEATURES_SOCIO + FEATURES_LANDCOVER
)

CATEGORICAL_FEATURES: tuple[str, ...] = ("peak_hour_mode",)

# --------------------------------------------------------------- external data

# Downloaded file names vary with the portal's export naming, so these are
# glob patterns resolved at run time rather than fixed paths.
CES_SHAPEFILE_GLOB = "calenviroscreen40*/*.shp"
CES_EXCEL_GLOB = "calenviroscreen40*.xlsx"
IMPERVIOUS_GLOB = "*impermeable*.geojson"
TREE_CANOPY_GLOB = "*[Tt]ree*[Cc]anopy*.geojson"
ACS_CACHE_PATH = EXTERNAL_DIR / "acs_2019_la_tracts.csv"

# CalEnviroScreen ships in California Albers, an equal-area projection. We keep
# every areal computation (tract area, area-weighted overlay, population
# density) in this CRS, and only drop back to lon/lat for haversine distance.
PROJECTED_CRS = "EPSG:3310"
GEOGRAPHIC_CRS = "EPSG:4326"

# CalEnviroScreen uses -999 as its missing-data sentinel. 46 of the 2,343 Los
# Angeles tracts carry it in CIscoreP - the label. Left untouched it would
# corrupt training with no visible error.
CES_MISSING_SENTINEL = -999.0

# US Census ACS 5-year.
#
# MEASURED, not assumed: the ACS switched tract geography between vintages.
#   ACS 2018 / 2019 5-year -> 2,346 LA County tracts -> 2010 geography
#   ACS 2020 / 2021 5-year -> 2,498 LA County tracts -> 2020 geography
# CalEnviroScreen 4.0 has 2,343 LA tracts, i.e. 2010 geography, so ACS 2019 is
# the vintage that joins cleanly. Using 2020 would silently mismatch tracts.
ACS_YEAR = 2019
ACS_STATE_FIPS = "06"       # California
ACS_COUNTY_FIPS = "037"     # Los Angeles County

ACS_VARIABLES = {
    "B01003_001E": "population",        # detail table
    "S0101_C02_030E": "pop_over_65_pct",  # subject table
    "S1901_C01_012E": "median_income",    # subject table
}

# --------------------------------------------------------------- tract selection

# A tract joins the study set only if its centroid falls inside the study
# polygon AND it contains at least this many FortyGuard tiles. Edge tracts
# clipped to a sliver would otherwise yield a p95 computed from three tiles.
MIN_TILES_PER_TRACT = 30

# --------------------------------------------------------------- API behaviour

# --------------------------------------------------------------- API behaviour

POLL_INTERVAL_S = 5.0
REQUEST_TIMEOUT_S = 1800.0        # generous: month-long heatmap analyses are slow

# Point endpoints (env_params) return in seconds, not minutes. Giving them the
# heatmap timeout means one stalled server-side task blocks the run for half an
# hour, so they get their own much tighter budget plus a couple of retries for
# transient network drops.
ENV_POINT_TIMEOUT_S = 240.0
ENV_POINT_POLL_S = 3.0
ENV_POINT_RETRIES = 2

# --------------------------------------------------------------- cache layout

MANIFEST_PATH = RAW_DIR / "manifest.json"


def cache_path(key: str, suffix: str = "parquet") -> Path:
    """Return the canonical cache file for one pipeline dataset.

    ``key`` is a short slug such as ``tcm_daily`` or ``exceedance``. Never call
    the API without checking this path first.
    """
    return RAW_DIR / f"fortyguard_{key}.{suffix}"


def meta_path(key: str) -> Path:
    """Sidecar file holding the request fingerprint for one cached dataset.

    The fingerprint guards against a silent mismatch: if the study polygon or
    the dates change, the cached file no longer describes the same request and
    must be refetched.
    """
    return RAW_DIR / f"fortyguard_{key}.meta.json"


def describe() -> str:
    """Human-readable summary of the active configuration (used in notebooks)."""
    return (
        f"Study area   : {CITY_NAME}, {CITY_STATE}\n"
        f"Bounding box : lon [{LON_WEST}, {LON_EAST}]  lat [{LAT_SOUTH}, {LAT_NORTH}]\n"
        f"Approx area  : {study_area_km2():.1f} km2\n"
        f"Period       : {STUDY_START_DATE} -> {STUDY_END_DATE}\n"
        f"Threshold    : {HEAT_THRESHOLD_C} C ({HEAT_DIRECTION})\n"
        f"Granularity  : {GRANULARITY_M} m\n"
        f"API key set  : {bool(FORTYGUARD_API_KEY)}"
    )
