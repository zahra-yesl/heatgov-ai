"""Compare the cached FortyGuard layers and test the core HeatGov AI thesis.

Run from the project root:

    .venv/Scripts/python.exe backend/data_pipeline/compare_layers.py

The thesis: in a city it is not the peak temperature that harms people, it is
the *duration* of exposure. If that is true, then `exceedance` and
`persistence` should do two things a temperature snapshot cannot:

1. Separate neighbourhoods far more sharply (discrimination).
2. Carry information a temperature snapshot does not already contain
   (complementarity, measured by rank correlation).

This script measures both. It reads only cached Parquet files and never calls
the API.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402
from data_pipeline import rule  # noqa: E402

# key -> (column to read, human label, is the scale a true ratio scale?)
#
# "Ratio scale" means zero is a real zero, so a max/min ratio is meaningful.
# Hours above a threshold start at zero hours. Degrees Celsius do not: 0 C is an
# arbitrary point, so a Celsius ratio would be nonsense and is not reported.
LAYERS: list[tuple[str, str, str, bool]] = [
    ("tcm_daily", "average_temperature", "tcm 24 h average (C)", False),
    ("tcm_daily", "max_temperature", "tcm 24 h daily max (C)", False),
    ("tcm_peak_15h", "average_temperature", "tcm 15:00 snapshot (C)", False),
    ("tcm_peak_22h", "average_temperature", "tcm 22:00 snapshot (C)", False),
    ("exceedance", "value", "exceedance (hours > 30 C)", True),
    ("persistence", "value", "persistence (longest run, h)", True),
    ("time_of_measure", "value", "time_of_measure (peak hour)", False),
]


def load_layers() -> tuple[pd.DataFrame, list[tuple[str, str, bool]]]:
    """Load every cached layer into one tile-aligned DataFrame."""
    frames: dict[str, pd.Series] = {}
    descriptors: list[tuple[str, str, bool]] = []
    reference: gpd.GeoDataFrame | None = None

    for key, column, label, is_ratio in LAYERS:
        path = config.cache_path(key)
        if not path.exists():
            print("  SKIP {} - {} not found".format(label, path.name))
            continue
        gdf = gpd.read_parquet(path)
        if column not in gdf.columns:
            print("  SKIP {} - column {} absent".format(label, column))
            continue
        gdf = gdf.sort_values("tile_id").reset_index(drop=True)
        if reference is None:
            reference = gdf
        elif len(gdf) != len(reference):
            print("  SKIP {} - {} tiles, expected {}".format(label, len(gdf), len(reference)))
            continue
        frames[label] = gdf[column]
        descriptors.append((label, key, is_ratio))

    if reference is None:
        raise RuntimeError("No cached layers found. Run pull_heatmaps.py first.")

    df = pd.DataFrame(frames)
    df["tile_id"] = reference["tile_id"]
    df["centroid_lon"] = reference["centroid_lon"]
    df["centroid_lat"] = reference["centroid_lat"]
    return df, descriptors


def discrimination_table(df: pd.DataFrame, descriptors: list[tuple[str, str, bool]]) -> None:
    """How sharply does each layer separate the coolest tile from the hottest?"""
    print()
    print(rule("="))
    print("1. DISCRIMINATION - how far apart are the best and worst tiles?")
    print(rule("="))
    header = "{:>30} | {:>8} | {:>8} | {:>8} | {:>8} | {:>9}".format(
        "layer", "min", "mean", "max", "spread", "max/min"
    )
    print(header)
    print(rule("-", len(header)))
    for label, _key, is_ratio in descriptors:
        s = df[label].dropna()
        ratio = "{:9.2f}x".format(s.max() / s.min()) if is_ratio and s.min() > 0 else "{:>9}".format("n/a")
        print(
            "{:>30} | {:8.2f} | {:8.2f} | {:8.2f} | {:8.2f} | {}".format(
                label, s.min(), s.mean(), s.max(), s.max() - s.min(), ratio
            )
        )
    print()
    print("  A max/min ratio is only printed for layers measured on a true ratio")
    print("  scale (hours, which start at a real zero). Degrees Celsius have an")
    print("  arbitrary zero, so a Celsius ratio would be meaningless.")


def complementarity_table(df: pd.DataFrame, descriptors: list[tuple[str, str, bool]]) -> None:
    """Does each layer add information a temperature snapshot lacks?"""
    labels = [d[0] for d in descriptors]
    corr = df[labels].corr(method="spearman")

    print()
    print(rule("="))
    print("2. COMPLEMENTARITY - Spearman rank correlation between layers")
    print(rule("="))
    short = {label: label[:16] for label in labels}
    header = "{:>30} |".format("") + "".join(" {:>16} |".format(short[c]) for c in labels)
    print(header)
    print(rule("-", len(header)))
    for row in labels:
        line = "{:>30} |".format(row)
        for col in labels:
            line += " {:16.2f} |".format(corr.loc[row, col])
        print(line)
    print()
    print("  Two layers with a correlation near 1.0 say the same thing, so the")
    print("  second one adds nothing to the model. A correlation well below 1.0")
    print("  means the layer carries independent signal worth feeding to XGBoost.")


def verdict(df: pd.DataFrame, descriptors: list[tuple[str, str, bool]]) -> None:
    labels = [d[0] for d in descriptors]
    baseline = "tcm 24 h average (C)"
    if baseline not in labels:
        return

    corr = df[labels].corr(method="spearman")
    print()
    print(rule("="))
    print("3. VERDICT")
    print(rule("="))

    for target in ("exceedance (hours > 30 C)", "persistence (longest run, h)"):
        if target not in labels:
            continue
        r = corr.loc[baseline, target]
        shared = r * r * 100.0
        print(
            "  {:<30} vs baseline: rho = {:+.2f}  ->  {:.0f}% of its ranking".format(
                target, r, shared
            )
        )
        print("  {:<30} is explained by the 24 h average; the rest is new signal.".format(""))

    ex = df.get("exceedance (hours > 30 C)")
    base = df[baseline]
    if ex is not None:
        hot_by_temp = base.nlargest(int(0.10 * len(base))).index
        hot_by_dose = ex.nlargest(int(0.10 * len(ex))).index
        overlap = len(set(hot_by_temp) & set(hot_by_dose)) / max(len(hot_by_temp), 1) * 100
        print()
        print("  Top 10% of tiles by 24 h temperature vs top 10% by heat dose:")
        print("    overlap = {:.0f}%".format(overlap))
        print("    {:.0f}% of the worst-exposed tiles would be MISSED by ranking".format(100 - overlap))
        print("    on temperature alone. That gap is the reason HeatGov AI exists.")


def main() -> int:
    print(config.describe())
    print()
    print("Loading cached layers ...")
    df, descriptors = load_layers()
    print("  {} layers over {:,} tiles".format(len(descriptors), len(df)))

    discrimination_table(df, descriptors)
    complementarity_table(df, descriptors)
    verdict(df, descriptors)

    out = config.PROCESSED_DIR / "layer_comparison.parquet"
    df.to_parquet(out, index=False)
    print()
    print("Tile-aligned comparison table saved to {}".format(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
