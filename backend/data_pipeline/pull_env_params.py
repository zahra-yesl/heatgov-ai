"""Fetch environmental parameters at a grid of points across the study area.

Run from the project root:

    .venv/Scripts/python.exe backend/data_pipeline/pull_env_params.py

Unlike the heatmap endpoint, /v1/env_params is a *point* endpoint: one call
returns heat index, humidity, air quality, solar irradiance and more for a
single coordinate. We therefore sample a regular grid (3 columns x 5 rows =
15 points) spread across Central Los Angeles.

The endpoint also requires the ambient temperature at that point, which we read
from the cached peak-hour heatmap: for each grid point we take the nearest tile
and use its average temperature.

RESILIENCE
----------
Every point costs credits, so no successful call is ever thrown away. Each
response is appended to data/raw/fortyguard_env_params_partial.json the moment
it arrives. If the run dies halfway through - a dropped connection, a stalled
server-side task, a Ctrl-C - rerunning resumes from that file and only fetches
the points that are still missing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402
from data_pipeline import (  # noqa: E402
    CreditMeter,
    cache_status,
    fingerprint,
    make_client,
    record_manifest,
    rule,
    utc_now,
    write_meta,
)

CACHE_KEY = "env_params"
RAW_JSON_PATH = config.RAW_DIR / "fortyguard_env_params_raw.json"
PARTIAL_PATH = config.RAW_DIR / "fortyguard_env_params_partial.json"

# Heatmaps we read the ambient temperature from, best first. The 15:00 layer is
# the daily thermal peak, so it is the right ambient value for peak-hour features.
TEMPERATURE_SOURCES = ("tcm_peak_15h", "tcm_peak_22h", "tcm_daily")


def flatten(obj, prefix: str = "") -> dict:
    """Flatten a nested JSON response into one flat row of scalar columns.

    The env_params schema is not documented in the client, so rather than
    guessing field names we flatten whatever comes back. Numeric lists are
    summarised as min / mean / max.
    """
    out: dict = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = "{}.{}".format(prefix, key) if prefix else str(key)
            out.update(flatten(value, child))
    elif isinstance(obj, list):
        numbers = [x for x in obj if isinstance(x, (int, float)) and not isinstance(x, bool)]
        if obj and len(numbers) == len(obj):
            out["{}.min".format(prefix)] = float(min(numbers))
            out["{}.mean".format(prefix)] = float(sum(numbers) / len(numbers))
            out["{}.max".format(prefix)] = float(max(numbers))
        elif obj and all(isinstance(x, dict) for x in obj):
            for index, item in enumerate(obj):
                out.update(flatten(item, "{}[{}]".format(prefix, index)))
    else:
        out[prefix or "value"] = obj
    return out


def load_temperature_source() -> gpd.GeoDataFrame:
    """Return the best available cached heatmap for ambient temperature."""
    for key in TEMPERATURE_SOURCES:
        path = config.cache_path(key)
        if path.exists():
            gdf = gpd.read_parquet(path)
            if "average_temperature" in gdf.columns:
                print("  Ambient temperature source: {}".format(path.name))
                return gdf
    raise RuntimeError(
        "No cached tcm heatmap found. Run pull_heatmaps.py first: the env_params "
        "endpoint requires an ambient temperature for every point."
    )


def nearest_temperatures(gdf: gpd.GeoDataFrame, points: list[tuple[float, float]]) -> list[float]:
    """Ambient temperature of the tile nearest to each sample point."""
    lons = gdf["centroid_lon"].to_numpy()
    lats = gdf["centroid_lat"].to_numpy()
    temps = gdf["average_temperature"].to_numpy()

    values = []
    for lon, lat in points:
        # Plain squared distance is fine: tiles are 100 m apart over a small area.
        distances = (lons - lon) ** 2 + (lats - lat) ** 2
        values.append(float(temps[int(np.argmin(distances))]))
    return values


def load_partial() -> dict:
    """Responses already paid for in an earlier run."""
    if not PARTIAL_PATH.exists():
        return {}
    try:
        return json.loads(PARTIAL_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("  Partial file is corrupt, starting fresh.")
        return {}


def save_partial(store: dict) -> None:
    PARTIAL_PATH.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")


def fetch_point(client, lon: float, lat: float, temperature: float) -> dict:
    """One env_params call, retried on transient failures.

    Catches broad Exception on purpose: a dropped TCP connection surfaces as
    requests.ConnectionError, which is NOT a FortyGuardError and would
    otherwise abort the whole grid.
    """
    attempts = config.ENV_POINT_RETRIES + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return client.environmental_parameters(
                latitude=lat,
                longitude=lon,
                temperature=temperature,
                start_date=config.TEST_DATE,
                filter_type=config.FILTER_SINGLE_HOUR,
                start_time=config.ENV_PARAMS_HOUR,
                poll_interval=config.ENV_POINT_POLL_S,
                timeout=config.ENV_POINT_TIMEOUT_S,
                verbose=False,
            )
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            last_error = exc
            if attempt < attempts:
                backoff = 5 * attempt
                print("      attempt {}/{} failed ({}), retrying in {}s".format(
                    attempt, attempts, type(exc).__name__, backoff
                ))
                time.sleep(backoff)

    raise last_error if last_error else RuntimeError("unreachable")


def build_dataframe(store: dict, points: list[tuple[float, float]]) -> pd.DataFrame:
    """Turn the partial store into a flat table, skipping points that failed."""
    rows: list[dict] = []
    for index in range(len(points)):
        label = "point_{:02d}".format(index)
        entry = store.get(label)
        if not entry or not entry.get("response"):
            continue
        row = {
            "point_id": label,
            "longitude": entry["longitude"],
            "latitude": entry["latitude"],
            "ambient_temperature": entry["ambient_temperature"],
        }
        row.update(flatten(entry["response"].get("result", {})))
        rows.append(row)

    if not rows:
        raise RuntimeError(
            "No env_params point succeeded. Inspect {} for the recorded errors.".format(
                PARTIAL_PATH.name
            )
        )
    return pd.DataFrame(rows)


def fetch_grid(client, meter: CreditMeter, force: bool = False) -> pd.DataFrame:
    points = config.env_param_grid()
    payload = {
        "endpoint": "env_params",
        "grid": points,
        "start_date": config.TEST_DATE,
        "start_time": config.ENV_PARAMS_HOUR,
        "filter_type": config.FILTER_SINGLE_HOUR,
        "polygon": config.CENTRAL_LA_RING,
    }
    fp = fingerprint(payload)
    status = cache_status(CACHE_KEY, fp)
    path = config.cache_path(CACHE_KEY)

    if status == "hit" and not force:
        df = pd.read_parquet(path)
        print("  CACHE HIT   {} ({} points) - no API call, 0 credits".format(path.name, len(df)))
        return df

    reason = "forced refetch" if force else (
        "no cached file" if status == "miss" else "stale fingerprint"
    )
    print("  CACHE MISS  {}".format(reason))

    source = load_temperature_source()
    temperatures = nearest_temperatures(source, points)

    store = load_partial() if not force else {}
    already = sum(1 for v in store.values() if v.get("response"))
    if already:
        print("  RESUMING    {} point(s) recovered from {}".format(already, PARTIAL_PATH.name))

    print("  Sampling {} points at {} local on {} ...".format(
        len(points), config.ENV_PARAMS_HOUR, config.TEST_DATE
    ))

    before = meter.used()
    failures: list[str] = []

    for index, ((lon, lat), temperature) in enumerate(zip(points, temperatures)):
        label = "point_{:02d}".format(index)

        if store.get(label, {}).get("response"):
            print("    {}  ({:.4f}, {:.4f})  RESUMED, no API call".format(label, lon, lat))
            continue

        started = time.monotonic()
        try:
            response = fetch_point(client, lon, lat, temperature)
        except Exception as exc:  # noqa: BLE001 - record and continue to the next point
            message = "{}: {}".format(type(exc).__name__, exc)
            failures.append("{}: {}".format(label, message))
            store[label] = {
                "longitude": lon,
                "latitude": lat,
                "ambient_temperature": temperature,
                "error": message,
            }
            save_partial(store)  # remember the failure too, so reruns retry it
            print("    {}  ({:.4f}, {:.4f})  FAILED  {}".format(label, lon, lat, message[:90]))
            continue

        store[label] = {
            "longitude": lon,
            "latitude": lat,
            "ambient_temperature": temperature,
            "response": response,
        }
        save_partial(store)  # persist immediately: this point has already been paid for
        print("    {}  ({:.4f}, {:.4f})  ambient {:.2f} C  OK  ({:.0f}s)".format(
            label, lon, lat, temperature, time.monotonic() - started
        ))

    credits = meter.used() - before
    df = build_dataframe(store, points)

    # Parquet needs homogeneous column types; stringify anything non-numeric.
    for column in df.columns:
        if df[column].dtype == object and column != "point_id":
            df[column] = df[column].astype(str)
    df.to_parquet(path, index=False)
    RAW_JSON_PATH.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")

    entry = {
        "key": CACHE_KEY,
        "analytic_type": "env_params",
        "label": "Environmental parameters, {}/{} grid points".format(len(df), len(points)),
        "fingerprint": fp,
        "activity_id": "(multi-point)",
        "tiles": int(len(df)),
        "credits": int(credits),
        "fetched_at": utc_now(),
        "request": payload,
        "failed_points": failures,
    }
    write_meta(CACHE_KEY, entry)
    record_manifest(CACHE_KEY, entry)

    print("  SAVED       {} ({}/{} points, {} columns) - {:,} credits".format(
        path.name, len(df), len(points), len(df.columns), credits
    ))
    if failures:
        print("  {} point(s) still failing (rerun to retry just those):".format(len(failures)))
        for message in failures:
            print("    {}".format(message[:140]))
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch environmental parameters for HeatGov AI")
    parser.add_argument("--force", action="store_true", help="ignore cache and partial file")
    args = parser.parse_args()

    print(config.describe())
    print()
    print(rule("="))
    print("[env_params]  Environmental parameters at {} grid points".format(
        config.ENV_GRID_COLS * config.ENV_GRID_ROWS
    ))
    print("  why: heat index, humidity, air quality and solar irradiance are")
    print("       features 6-9 of the model and cannot be derived from temperature alone.")
    print(rule("="))

    client = make_client()
    meter = CreditMeter(client)
    print("Credits used so far: {:,}   remaining: {:,}".format(meter.session_start, meter.remaining()))

    df = fetch_grid(client, meter, force=args.force)

    numeric = df.select_dtypes("number")
    print()
    print("  numeric columns: {}".format(len(numeric.columns)))
    if not numeric.empty:
        summary = numeric.describe().T[["min", "mean", "max", "std"]]
        print(summary.to_string())

    print()
    print("  preview (df.head()):")
    preview_cols = list(df.columns)[:8]
    print(df[preview_cols].head().to_string(index=False))

    print()
    print("Credits consumed this run : {:,}".format(meter.session_total()))
    print("Credits remaining         : {:,}".format(meter.remaining()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
