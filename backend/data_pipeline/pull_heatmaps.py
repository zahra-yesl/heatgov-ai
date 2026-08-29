"""Fetch and cache every FortyGuard heatmap analysis for the study area.

Run from the project root:

    .venv/Scripts/python.exe backend/data_pipeline/pull_heatmaps.py

Each analysis is written to data/raw/fortyguard_<key>.parquet as GeoParquet
(tile polygons plus their values), next to a .meta.json sidecar recording the
request fingerprint, the activity id and the credit cost.

Nothing is ever downloaded twice: a fetch only happens when the cache is
missing or when its fingerprint no longer matches the pending request.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import shape  # noqa: E402

import config  # noqa: E402
from fortyguard import FortyGuardError  # noqa: E402
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

# Columns that identify a tile rather than measure it.
INDEX_COLUMNS = ("tile_id", "centroid_lon", "centroid_lat")


@dataclass(frozen=True)
class HeatmapSpec:
    """One FortyGuard heatmap request, with the reason we need it."""

    key: str
    analytic_type: str
    label: str
    why: str
    params: dict = field(default_factory=dict)

    def call_kwargs(self) -> dict:
        return {
            "polygon_aoi": config.CENTRAL_LA_POLYGON,
            "granularity": config.GRANULARITY_M,
            "analytic_type": self.analytic_type,
            **self.params,
        }

    def fingerprint_payload(self) -> dict:
        """Everything that makes this request unique, including the polygon."""
        return {
            "analytic_type": self.analytic_type,
            "granularity": config.GRANULARITY_M,
            "polygon": config.CENTRAL_LA_RING,
            **self.params,
        }


SPECS: list[HeatmapSpec] = [
    HeatmapSpec(
        key="tcm_daily",
        analytic_type="tcm",
        label="Daily snapshot (24 h aggregate)",
        why="Baseline reference. Averaged over a whole day, so spatially flat.",
        params={
            "start_date": config.TEST_DATE,
            "filter_type": config.FILTER_SINGLE_DAY,
        },
    ),
    HeatmapSpec(
        key="tcm_peak_15h",
        analytic_type="tcm",
        label="Hourly snapshot, 15:00 local (daily thermal peak)",
        why="The afternoon peak, when the urban heat island is at its widest.",
        params={
            "start_date": config.TEST_DATE,
            "filter_type": config.FILTER_SINGLE_HOUR,
            "start_time": config.HOUR_AFTERNOON,
        },
    ),
    HeatmapSpec(
        key="tcm_peak_22h",
        analytic_type="tcm",
        label="Hourly snapshot, 22:00 local (night-time control)",
        why="Night layer. Night heat blocks physiological recovery and drives mortality.",
        params={
            "start_date": config.TEST_DATE,
            "filter_type": config.FILTER_SINGLE_HOUR,
            "start_time": config.HOUR_NIGHT,
        },
    ),
    HeatmapSpec(
        key="exceedance",
        analytic_type="exceedance",
        label="Hours above 30 C, July 2025",
        why="Total heat dose: how many hours a place spends past the danger line.",
        params={
            "start_date": config.STUDY_START_DATE,
            "end_date": config.STUDY_END_DATE,
            "filter_type": config.FILTER_RANGE_OF_DAYS,
            "threshold": config.HEAT_THRESHOLD_C,
            "direction": config.HEAT_DIRECTION,
        },
    ),
    HeatmapSpec(
        key="persistence",
        analytic_type="persistence",
        label="Longest unbroken run above 30 C, July 2025",
        why="Heat without relief, the driver of medical emergencies.",
        params={
            "start_date": config.STUDY_START_DATE,
            "end_date": config.STUDY_END_DATE,
            "filter_type": config.FILTER_RANGE_OF_DAYS,
            "threshold": config.HEAT_THRESHOLD_C,
            "direction": config.HEAT_DIRECTION,
        },
    ),
    HeatmapSpec(
        key="time_of_measure",
        analytic_type="time_of_measure",
        label="UTC hour of the daily peak, 1-7 July 2025",
        why="Late peaks mark heavy thermal mass (concrete), early peaks open ground.",
        params={
            "start_date": config.PEAK_HOUR_WINDOW_START,
            "end_date": config.PEAK_HOUR_WINDOW_END,
            "filter_type": config.FILTER_RANGE_OF_DAYS,
        },
    ),
]


def result_to_geodataframe(result: dict) -> gpd.GeoDataFrame:
    """Turn a heatmap result into a GeoParquet-ready GeoDataFrame.

    Tile properties differ per analytic type (tcm carries three temperature
    fields, the analysis types carry a single value), so properties are
    flattened generically rather than hard-coded.
    """
    features = result["map_data"]["features"]
    if not features:
        raise ValueError("map_data contains no features")

    rows: list[dict] = []
    geometries = []
    for feature in features:
        props = dict(feature["properties"])
        ring = feature["geometry"]["coordinates"][0]
        points = ring[:-1] if ring[0] == ring[-1] else ring
        props["centroid_lon"] = sum(p[0] for p in points) / len(points)
        props["centroid_lat"] = sum(p[1] for p in points) / len(points)
        rows.append(props)
        geometries.append(shape(feature["geometry"]))

    return gpd.GeoDataFrame(pd.DataFrame(rows), geometry=geometries, crs="EPSG:4326")


def value_columns(gdf: gpd.GeoDataFrame) -> list[str]:
    """Measurement columns: numeric columns that are not tile identifiers."""
    return [
        c
        for c in gdf.columns
        if c not in INDEX_COLUMNS
        and c != "geometry"
        and pd.api.types.is_numeric_dtype(gdf[c])
    ]


def describe_values(gdf: gpd.GeoDataFrame) -> list[dict]:
    """Per-column spread statistics. Spread is what the ML model learns from."""
    stats = []
    for column in value_columns(gdf):
        series = gdf[column].dropna()
        if series.empty:
            continue
        stats.append(
            {
                "column": column,
                "min": float(series.min()),
                "mean": float(series.mean()),
                "max": float(series.max()),
                "std": float(series.std()),
                "spread": float(series.max() - series.min()),
            }
        )
    return stats


def print_stats(stats: list[dict]) -> None:
    header = "{:>22} | {:>8} | {:>8} | {:>8} | {:>7} | {:>8}".format(
        "column", "min", "mean", "max", "std", "spread"
    )
    print(header)
    print(rule("-", len(header)))
    for s in stats:
        print(
            "{:>22} | {:8.2f} | {:8.2f} | {:8.2f} | {:7.3f} | {:8.2f}".format(
                s["column"], s["min"], s["mean"], s["max"], s["std"], s["spread"]
            )
        )


def fetch_one(client, spec: HeatmapSpec, meter: CreditMeter, force: bool = False) -> dict:
    """Fetch one analysis, or load it from cache. Returns a summary dict."""
    print()
    print(rule("="))
    print("[{}]  {}".format(spec.key, spec.label))
    print("  why: {}".format(spec.why))
    print(rule("="))

    fp = fingerprint(spec.fingerprint_payload())
    status = cache_status(spec.key, fp)
    path = config.cache_path(spec.key)

    if status == "hit" and not force:
        gdf = gpd.read_parquet(path)
        print("  CACHE HIT   {} ({:,} tiles) - no API call, 0 credits".format(path.name, len(gdf)))
        credits = 0
        activity_id = "(cached)"
    else:
        if force:
            reason = "forced refetch"
        elif status == "miss":
            reason = "no cached file"
        else:
            reason = "cached file came from a different request (stale fingerprint)"
        print("  CACHE MISS  {}".format(reason))
        print("  Calling POST /v1/heatmap analytic_type={} ...".format(spec.analytic_type))

        before = meter.used()
        response = client.create_heatmap(
            **spec.call_kwargs(),
            poll_interval=config.POLL_INTERVAL_S,
            timeout=config.REQUEST_TIMEOUT_S,
            verbose=True,
        )
        credits = meter.used() - before
        activity_id = response["activity_id"]

        gdf = result_to_geodataframe(response["result"])
        gdf.to_parquet(path)

        entry = {
            "key": spec.key,
            "analytic_type": spec.analytic_type,
            "label": spec.label,
            "fingerprint": fp,
            "activity_id": activity_id,
            "tiles": int(len(gdf)),
            "credits": int(credits),
            "fetched_at": utc_now(),
            "request": spec.fingerprint_payload(),
            "stats_data": response["result"].get("stats_data", {}),
        }
        write_meta(spec.key, entry)
        record_manifest(spec.key, {k: v for k, v in entry.items() if k != "stats_data"})
        print("  SAVED       {} ({:,} tiles) - {:,} credits".format(path.name, len(gdf), credits))

    stats = describe_values(gdf)
    print()
    print_stats(stats)
    print()
    print("  preview (df.head()):")
    preview_cols = [c for c in gdf.columns if c != "geometry"]
    print(gdf[preview_cols].head().to_string(index=False))

    return {
        "key": spec.key,
        "label": spec.label,
        "tiles": int(len(gdf)),
        "credits": int(credits),
        "activity_id": activity_id,
        "stats": stats,
        "path": str(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch FortyGuard heatmaps for HeatGov AI")
    parser.add_argument("--force", action="store_true", help="refetch even on a cache hit")
    parser.add_argument("--only", nargs="*", help="restrict to these dataset keys")
    args = parser.parse_args()

    specs = SPECS
    if args.only:
        wanted = set(args.only)
        specs = [s for s in SPECS if s.key in wanted]
        if not specs:
            print("No spec matches {}. Known keys: {}".format(args.only, [s.key for s in SPECS]))
            return 1

    print(config.describe())
    print()
    print("Datasets to process: {}".format(len(specs)))

    client = make_client()
    meter = CreditMeter(client)
    print("Credits used so far: {:,}   remaining: {:,}".format(meter.session_start, meter.remaining()))

    summaries: list[dict] = []
    failures: list[tuple[str, str]] = []

    for spec in specs:
        try:
            summaries.append(fetch_one(client, spec, meter, force=args.force))
        except FortyGuardError as exc:
            failures.append((spec.key, "{}: {}".format(type(exc).__name__, exc)))
            print("  FAILED      {}: {}".format(type(exc).__name__, exc))
        except Exception as exc:  # noqa: BLE001 - report and keep going
            failures.append((spec.key, "{}: {}".format(type(exc).__name__, exc)))
            print("  FAILED      {}: {}".format(type(exc).__name__, exc))

    print()
    print(rule("="))
    print("SUMMARY")
    print(rule("="))
    header = "{:>18} | {:>8} | {:>9} | file".format("dataset", "tiles", "credits")
    print(header)
    print(rule("-", len(header) + 24))
    for s in summaries:
        print(
            "{:>18} | {:8,} | {:9,} | {}".format(
                s["key"], s["tiles"], s["credits"], Path(s["path"]).name
            )
        )

    if failures:
        print()
        print("FAILURES")
        for key, message in failures:
            print("  {}: {}".format(key, message))

    print()
    print("Credits consumed this run : {:,}".format(meter.session_total()))
    print("Credits remaining         : {:,}".format(meter.remaining()))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
