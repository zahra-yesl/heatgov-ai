"""Fetch American Community Survey demographics for Los Angeles County tracts.

Run from the project root:

    .venv/Scripts/python.exe backend/data_pipeline/fetch_census.py

WHY ACS 2019 AND NOT 2020
-------------------------
The ACS changed census tract geography between vintages. Measured against the
live API on 2026-08-27, Los Angeles County returns:

    ACS 2018 5-year -> 2,346 tracts  (2010 geography)
    ACS 2019 5-year -> 2,346 tracts  (2010 geography)
    ACS 2020 5-year -> 2,498 tracts  (2020 geography)
    ACS 2021 5-year -> 2,498 tracts  (2020 geography)

CalEnviroScreen 4.0 carries 2,343 Los Angeles tracts, i.e. 2010 geography.
Joining ACS 2020 onto it would mismatch a subset of tracts silently - no error,
just demographics attached to the wrong neighbourhoods. ACS 2019 is therefore
the vintage that joins cleanly.

NO FABRICATED DATA
------------------
If the API is unreachable or the key is missing, this module raises. It never
substitutes plausible-looking numbers. Invented income figures in a submission
judged by municipal officials would be a credibility failure, not a shortcut.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

import config  # noqa: E402
from data_pipeline import rule  # noqa: E402

BASE_URL = "https://api.census.gov/data/{year}/acs/acs5"

# The ACS splits variables across two endpoints. Detail tables (B*) live at the
# root; subject tables (S*) live under /subject. Requesting an S variable from
# the root endpoint returns an error, so they are fetched separately.
DETAIL_VARIABLES = {"B01003_001E": "population"}
SUBJECT_VARIABLES = {
    "S0101_C02_030E": "pop_over_65_pct",
    "S1901_C01_012E": "median_income",
}

# ACS uses large negative values as annotation codes (e.g. -666666666 means
# "estimate not available"). They must never reach a model.
ACS_SENTINEL_FLOOR = -1e6


class CensusUnavailable(RuntimeError):
    """The ACS could not be reached, or returned something that is not data."""


def _fetch(year: int, path: str, variables: dict[str, str], key: str) -> pd.DataFrame:
    """Call one ACS endpoint and return a tidy DataFrame indexed by tract FIPS."""
    url = BASE_URL.format(year=year) + path
    params = {
        "get": "NAME," + ",".join(variables),
        "for": "tract:*",
        "in": f"state:{config.ACS_STATE_FIPS} county:{config.ACS_COUNTY_FIPS}",
        "key": key,
    }

    try:
        response = requests.get(url, params=params, timeout=90)
    except requests.RequestException as exc:
        raise CensusUnavailable(f"Could not reach {url}: {exc}") from exc

    # A missing or rejected key returns an HTML page with HTTP 200, so status
    # code alone is not a reliable success test.
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type:
        snippet = response.text[:200].replace("\n", " ")
        raise CensusUnavailable(
            f"{url} returned {content_type!r} instead of JSON "
            f"(HTTP {response.status_code}). First bytes: {snippet!r}. "
            "A 'Missing Key' page means CENSUS_API_KEY is absent or invalid."
        )

    rows = response.json()
    frame = pd.DataFrame(rows[1:], columns=rows[0])
    frame["tract_fips"] = (
        frame["state"] + frame["county"] + frame["tract"]
    )

    for code, name in variables.items():
        frame[name] = pd.to_numeric(frame[code], errors="coerce")
        frame.loc[frame[name] < ACS_SENTINEL_FLOOR, name] = pd.NA

    return frame[["tract_fips", "NAME", *variables.values()]]


def fetch_acs(force: bool = False) -> pd.DataFrame:
    """Return ACS demographics for every LA County tract, using the disk cache."""
    cache = config.ACS_CACHE_PATH
    if cache.exists() and not force:
        frame = pd.read_csv(cache, dtype={"tract_fips": str})
        print(f"  CACHE HIT   {cache.name} ({len(frame):,} tracts) - no API call")
        return frame

    if not config.CENSUS_API_KEY:
        raise CensusUnavailable(
            "CENSUS_API_KEY is not set. Get a free key at "
            "https://api.census.gov/data/key_signup.html and add it to .env. "
            "See data/external/README.md."
        )

    print(f"  CACHE MISS  calling ACS {config.ACS_YEAR} 5-year ...")
    detail = _fetch(config.ACS_YEAR, "", DETAIL_VARIABLES, config.CENSUS_API_KEY)
    subject = _fetch(config.ACS_YEAR, "/subject", SUBJECT_VARIABLES, config.CENSUS_API_KEY)

    frame = detail.merge(subject.drop(columns=["NAME"]), on="tract_fips", how="outer")

    if len(frame) < 2000:
        raise CensusUnavailable(
            f"Expected roughly 2,346 Los Angeles tracts, got {len(frame)}. "
            "Refusing to continue with a partial extract."
        )

    frame.to_csv(cache, index=False)
    print(f"  SAVED       {cache.name} ({len(frame):,} tracts)")
    return frame


def main() -> int:
    print(rule("="))
    print(f"[census]  ACS {config.ACS_YEAR} 5-year, Los Angeles County")
    print("  why: pop_over_65_pct, median_income and pop_density are the three")
    print("       socio-demographic features of the full model.")
    print(rule("="))

    frame = fetch_acs()

    print()
    print(f"  tracts: {len(frame):,}")
    vintage = "2010 geography" if len(frame) < 2400 else "2020 geography"
    print(f"  vintage check: {len(frame):,} tracts -> {vintage}")
    if len(frame) >= 2400:
        print("  WARNING: this is 2020 geography and will NOT join to CalEnviroScreen 4.0.")

    print()
    numeric = frame.select_dtypes("number")
    print(numeric.describe().T[["count", "min", "mean", "max"]].to_string())

    print()
    print("  preview (df.head()):")
    print(frame.head().to_string(index=False))

    missing = frame[list(DETAIL_VARIABLES.values()) + list(SUBJECT_VARIABLES.values())].isna().sum()
    print()
    print("  missing values per column:")
    for name, count in missing.items():
        print(f"    {name:<18} {count:>5} of {len(frame):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
