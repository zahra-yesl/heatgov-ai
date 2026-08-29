"""Build the model-ready feature table for HeatGov AI.

Run from the project root:

    .venv/Scripts/python.exe backend/data_pipeline/build_features.py

Turns 8,674 FortyGuard tiles plus four external datasets into one row per census
tract: 12 features and the CalEnviroScreen label, saved to
data/processed/zone_features.parquet.

GEOGRAPHY, THE PART THAT SILENTLY BREAKS THINGS
-----------------------------------------------
Three tract vintages are in play:

    CalEnviroScreen 4.0        2,343 LA tracts   2010 geography  <- unit of analysis
    ACS 2019 5-year            2,346 LA tracts   2010 geography  <- joins directly
    LARIAC7 impervious (CT20)  2,496 LA tracts   2020 geography  <- transferred by area

We keep the CES 2010 tracts as the unit of analysis because the label lives
there and must stay exact. The impervious percentage is a *covariate*, so
transferring it across vintages by area-weighted intersection is legitimate.
Transferring the label that way would not have been.

All areal work happens in EPSG:3310 (California Albers, equal-area). Only the
haversine distance drops back to lon/lat.
"""

from __future__ import annotations

import argparse
import math
import sys
import warnings
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

warnings.filterwarnings("ignore", category=UserWarning)

import geopandas as gpd  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402
from data_pipeline import rule  # noqa: E402
from data_pipeline.fetch_census import fetch_acs  # noqa: E402

OUTPUT_PATH = config.PROCESSED_DIR / "zone_features.parquet"
GEOJSON_PATH = config.PROCESSED_DIR / "zone_features.geojson"
CORRELATION_PLOT_PATH = config.PROCESSED_DIR / "feature_correlations.png"

# CES fields we carry through: the label, the two half-scores used only to
# quantify label leakage, and descriptive demographics that are NOT score
# components and therefore safe to cross-check against ACS.
CES_KEEP = {
    "Tract": "tract_raw",
    "County": "county",
    "ApproxLoc": "approx_location",
    "CIscoreP": "CIscoreP",
    "CIscore": "ces_score",
    "PolBurdP": "pollution_burden_pctl",
    "PopCharP": "population_char_pctl",
    "TotPop19": "ces_population",
    "Elderly65": "ces_elderly65_pct",
}


def banner(step: int, title: str) -> None:
    print()
    print(rule("="))
    print(f"STEP {step}. {title}")
    print(rule("="))


def resolve_one(pattern: str, label: str, required: bool = True) -> Path | None:
    """Find exactly one external file matching a glob, or explain what is wrong."""
    matches = sorted(config.EXTERNAL_DIR.glob(pattern))
    if not matches:
        message = (
            f"{label}: no file matching {pattern!r} in {config.EXTERNAL_DIR}. "
            "See data/external/README.md for download instructions."
        )
        if required:
            raise FileNotFoundError(message)
        print(f"  MISSING     {message}")
        return None
    if len(matches) > 1:
        print(f"  NOTE        {label}: {len(matches)} matches, using {matches[0].name}")
    return matches[0]


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in kilometres.

    A flat-map ruler would do at this scale, but the sphere is two lines of code
    and removes the question entirely.
    """
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


# --------------------------------------------------------------- step 1

def load_fortyguard_layers() -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Load the cached tile layers into one tile-indexed table."""
    banner(1, "Load the Step 2 FortyGuard cache")

    wanted = {
        "tcm_peak_15h": ("max_temperature", "tile_temp_15h"),
        "tcm_peak_22h": ("max_temperature", "tile_temp_22h"),
        "exceedance": ("value", "tile_exceedance"),
        "persistence": ("value", "tile_persistence"),
        "time_of_measure": ("value", "tile_peak_hour"),
    }

    frames: dict[str, pd.Series] = {}
    reference: gpd.GeoDataFrame | None = None

    for key, (column, alias) in wanted.items():
        path = config.cache_path(key)
        if not path.exists():
            raise FileNotFoundError(
                f"{path} is missing. Run backend/data_pipeline/pull_heatmaps.py first."
            )
        gdf = gpd.read_parquet(path).sort_values("tile_id").reset_index(drop=True)
        if reference is None:
            reference = gdf
        else:
            # Every layer must describe the same tiles, or a per-tract average
            # would silently mix geographies.
            if len(gdf) != len(reference) or not gdf["tile_id"].equals(reference["tile_id"]):
                raise ValueError(f"{key} tile ids do not match {list(wanted)[0]}")
        frames[alias] = gdf[column]
        print(f"  {key:<18} {len(gdf):>6,} tiles | {column} -> {alias}")

    tiles = pd.DataFrame(frames)
    tiles["tile_id"] = reference["tile_id"]
    tiles["centroid_lon"] = reference["centroid_lon"]
    tiles["centroid_lat"] = reference["centroid_lat"]

    points = gpd.GeoDataFrame(
        tiles,
        geometry=gpd.points_from_xy(tiles["centroid_lon"], tiles["centroid_lat"]),
        crs=config.GEOGRAPHIC_CRS,
    ).to_crs(config.PROJECTED_CRS)

    env_path = config.cache_path("env_params")
    if not env_path.exists():
        raise FileNotFoundError(
            f"{env_path} is missing. Run backend/data_pipeline/pull_env_params.py first."
        )
    env = pd.read_parquet(env_path)
    elevation_column = next(c for c in env.columns if c.endswith("elevation"))
    env = env[["longitude", "latitude", elevation_column]].rename(
        columns={elevation_column: "elevation_m"}
    )
    print(f"  env_params         {len(env):>6} points | elevation {env['elevation_m'].min():.0f}"
          f"-{env['elevation_m'].max():.0f} m")

    return env, points


# --------------------------------------------------------------- step 2

def load_tracts() -> gpd.GeoDataFrame:
    """Load CalEnviroScreen tracts for Los Angeles County."""
    banner(2, "Load CalEnviroScreen 4.0 tracts")

    path = resolve_one(config.CES_SHAPEFILE_GLOB, "CalEnviroScreen shapefile")
    gdf = gpd.read_file(path)
    print(f"  loaded {len(gdf):,} California tracts from {path.name} (CRS {gdf.crs})")

    missing_fields = [f for f in CES_KEEP if f not in gdf.columns]
    if missing_fields:
        raise ValueError(f"Shapefile is missing expected fields: {missing_fields}")

    gdf = gdf[[*CES_KEEP, "geometry"]].rename(columns=CES_KEEP)
    gdf = gdf[gdf["county"] == "Los Angeles"].copy()
    print(f"  Los Angeles County: {len(gdf):,} tracts")

    # The FIPS code is stored as a float (6.083002103e+09). Rebuild the 11-digit
    # zero-padded string so it can join to ACS.
    gdf["tract_fips"] = gdf["tract_raw"].astype(float).round().astype("int64").map("{:011d}".format)

    # -999 is CalEnviroScreen's missing-data sentinel, not a score.
    numeric_columns = [
        "CIscoreP", "ces_score", "pollution_burden_pctl",
        "population_char_pctl", "ces_population", "ces_elderly65_pct",
    ]
    for column in numeric_columns:
        gdf[column] = pd.to_numeric(gdf[column], errors="coerce")
        sentinel = gdf[column] <= config.CES_MISSING_SENTINEL + 1
        if sentinel.any():
            print(f"  {column:<22} {sentinel.sum():>4} tracts carry the -999 sentinel -> NaN")
        gdf.loc[sentinel, column] = np.nan

    if gdf.crs is None:
        raise ValueError("Shapefile has no CRS; cannot project safely.")
    return gdf.to_crs(config.PROJECTED_CRS)


# --------------------------------------------------------------- step 3

def select_tracts(tracts: gpd.GeoDataFrame, points: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Keep tracts whose centroid is inside the study area and that hold enough tiles."""
    banner(3, "Select the study tracts")

    study = (
        gpd.GeoSeries.from_wkt(
            [f"POLYGON(({', '.join(f'{x} {y}' for x, y in config.CENTRAL_LA_RING)}))"],
            crs=config.GEOGRAPHIC_CRS,
        )
        .to_crs(config.PROJECTED_CRS)
        .iloc[0]
    )

    intersecting = tracts[tracts.intersects(study)].copy()
    print(f"  intersecting the study polygon      : {len(intersecting):>4}")

    centred = intersecting[intersecting.geometry.centroid.within(study)].copy()
    print(f"  centroid inside the study polygon   : {len(centred):>4}")

    joined = gpd.sjoin(
        points, centred[["tract_fips", "geometry"]], how="inner", predicate="within"
    )
    counts = joined.groupby("tract_fips").size().rename("n_tiles")
    centred = centred.merge(counts, on="tract_fips", how="left")
    centred["n_tiles"] = centred["n_tiles"].fillna(0).astype(int)

    thin = centred[centred["n_tiles"] < config.MIN_TILES_PER_TRACT]
    if len(thin):
        print(f"  dropped for < {config.MIN_TILES_PER_TRACT} tiles              : {len(thin):>4}"
              f"   (tile counts {sorted(thin['n_tiles'])[:8]}...)")

    kept = centred[centred["n_tiles"] >= config.MIN_TILES_PER_TRACT].copy()
    print(f"  KEPT                                : {len(kept):>4} tracts")
    print(f"  tiles per tract: min {kept['n_tiles'].min()} | median "
          f"{int(kept['n_tiles'].median())} | max {kept['n_tiles'].max()}")

    joined = joined[joined["tract_fips"].isin(kept["tract_fips"])]
    return kept, joined


# --------------------------------------------------------------- step 4

def aggregate_fortyguard(kept: gpd.GeoDataFrame, joined: pd.DataFrame,
                         env: pd.DataFrame) -> pd.DataFrame:
    """Roll the tiles of each tract up into five thermal features plus elevation."""
    banner(4, "Aggregate FortyGuard tiles to tract level")

    grouped = joined.groupby("tract_fips")
    features = pd.DataFrame({
        "temp_max_15h": grouped["tile_temp_15h"].quantile(0.95),
        "temp_max_22h": grouped["tile_temp_22h"].quantile(0.95),
        "exceedance_hours_30C": grouped["tile_exceedance"].mean(),
        "persistence_max_hours": grouped["tile_persistence"].max(),
        "peak_hour_mode": grouped["tile_peak_hour"].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan
        ),
    })

    for name, how in [
        ("temp_max_15h", "p95 of tile max temperature, 15:00 layer"),
        ("temp_max_22h", "p95 of tile max temperature, 22:00 layer"),
        ("exceedance_hours_30C", "mean hours above 30 C over July"),
        ("persistence_max_hours", "max unbroken run above 30 C"),
        ("peak_hour_mode", "most frequent peak hour (categorical)"),
    ]:
        series = features[name]
        print(f"  {name:<24} {series.min():7.2f} .. {series.max():7.2f}   {how}")

    # Elevation comes from only 15 sampled points, so it is interpolated by
    # inverse-distance weighting rather than measured per tract.
    centroids = kept.to_crs(config.GEOGRAPHIC_CRS).geometry.centroid
    elevations = []
    for lon, lat in zip(centroids.x, centroids.y):
        distances = np.hypot(env["longitude"] - lon, env["latitude"] - lat).to_numpy()
        distances = np.maximum(distances, 1e-9)
        weights = 1.0 / distances**2
        elevations.append(float(np.average(env["elevation_m"], weights=weights)))

    elevation = pd.Series(elevations, index=kept["tract_fips"].to_numpy(), name="elevation_m")
    features = features.join(elevation)
    print(f"  {'elevation_m':<24} {elevation.min():7.1f} .. {elevation.max():7.1f}   "
          f"inverse-distance from {len(env)} sampled points")
    print("  CAUTION: elevation_m is interpolated from 15 points; it may behave as a")
    print("           spatial smoother rather than as true terrain height.")

    return features


# --------------------------------------------------------------- step 5

def add_geography(kept: gpd.GeoDataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Distance to the ocean, the control that stops trees taking the blame for heat."""
    banner(5, "Geographic control feature")

    geographic = kept.to_crs(config.GEOGRAPHIC_CRS)
    centroids = geographic.geometry.centroid
    distances = [
        haversine_km(lon, lat, config.SANTA_MONICA_PIER_LON, config.SANTA_MONICA_PIER_LAT)
        for lon, lat in zip(centroids.x, centroids.y)
    ]
    series = pd.Series(distances, index=kept["tract_fips"].to_numpy(), name="distance_to_coast_km")
    print(f"  distance_to_coast_km     {series.min():7.2f} .. {series.max():7.2f} km "
          f"(from Santa Monica Pier)")

    kept = kept.copy()
    kept["tract_area_km2"] = kept.geometry.area / 1e6
    print(f"  tract_area_km2           {kept['tract_area_km2'].min():7.2f} .. "
          f"{kept['tract_area_km2'].max():7.2f} km2")

    return features.join(series), kept


# --------------------------------------------------------------- step 6

def add_census(kept: gpd.GeoDataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Join real ACS demographics and cross-check them against CalEnviroScreen."""
    banner(6, f"Census ACS {config.ACS_YEAR} 5-year demographics")

    acs = fetch_acs()
    acs = acs.set_index("tract_fips")

    frame = features.join(acs[["population", "pop_over_65_pct", "median_income"]])
    areas = kept.set_index("tract_fips")["tract_area_km2"]
    frame["pop_density"] = frame["population"] / areas
    frame = frame.drop(columns=["population"])

    matched = frame["pop_over_65_pct"].notna().sum()
    print(f"  matched on 11-digit FIPS : {matched} of {len(frame)} tracts")
    if matched < 0.9 * len(frame):
        raise ValueError(
            f"Only {matched}/{len(frame)} tracts matched ACS. That points at a tract "
            "vintage mismatch, not missing data. Refusing to continue."
        )

    # Independent check: CalEnviroScreen carries its own elderly percentage, and
    # it is a descriptive field rather than a score component. If the two
    # disagree, the join is wrong.
    ces_elderly = kept.set_index("tract_fips")["ces_elderly65_pct"]
    both = pd.concat([frame["pop_over_65_pct"], ces_elderly], axis=1).dropna()
    correlation = both.iloc[:, 0].corr(both.iloc[:, 1])
    print(f"  CROSS-CHECK ACS pop_over_65_pct vs CES Elderly65: r = {correlation:+.3f} "
          f"over {len(both)} tracts")
    if correlation < 0.8:
        print("  WARNING: the two elderly measures disagree. Suspect the FIPS join.")
    else:
        print("  -> consistent, the FIPS join is sound.")

    for name in ("pop_over_65_pct", "median_income", "pop_density"):
        series = frame[name].dropna()
        print(f"  {name:<24} {series.min():10.1f} .. {series.max():10.1f}  "
              f"({frame[name].isna().sum()} missing)")

    return frame


# --------------------------------------------------------------- step 7

def add_landcover(kept: gpd.GeoDataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Area-weighted transfer of impervious surface, plus tree canopy if usable."""
    banner(7, "Land cover")

    features = features.copy()
    features["impervious_surface_pct"] = _area_weighted(
        kept, resolve_one(config.IMPERVIOUS_GLOB, "impervious surface"),
        value_column="impermeable_pct", label="impervious_surface_pct",
    )

    canopy_path = resolve_one(config.TREE_CANOPY_GLOB, "tree canopy", required=False)
    canopy = _canopy_or_none(kept, canopy_path)
    if canopy is not None:
        features["tree_canopy_pct"] = canopy
    else:
        print("  tree_canopy_pct is NOT included. The model runs with 11 features.")
        print("  Download the tract-level LARIAC7 canopy layer and rerun to add it.")

    return features


def _area_weighted(kept: gpd.GeoDataFrame, path: Path, value_column: str, label: str) -> pd.Series:
    """Transfer a percentage from one tract vintage to another by intersection area."""
    source = gpd.read_file(path).to_crs(config.PROJECTED_CRS)
    if value_column not in source.columns:
        raise ValueError(f"{path.name} has no {value_column!r} column; found {list(source.columns)}")

    source = source[[value_column, "geometry"]].dropna(subset=[value_column])
    source = source[source.intersects(kept.union_all())]
    print(f"  {label}: {len(source)} source polygons overlap the study tracts")

    pieces = gpd.overlay(
        kept[["tract_fips", "geometry"]], source, how="intersection", keep_geom_type=True
    )
    pieces["piece_area"] = pieces.geometry.area

    weighted = pieces.groupby("tract_fips").apply(
        lambda g: np.average(g[value_column], weights=g["piece_area"]),
        include_groups=False,
    )
    weighted.name = label
    print(f"  {label:<24} {weighted.min():7.1f} .. {weighted.max():7.1f} "
          f"(mean {weighted.mean():.1f}, {len(weighted)} tracts)")
    return weighted


def _canopy_or_none(kept: gpd.GeoDataFrame, path: Path | None) -> pd.Series | None:
    """Use the canopy layer only if it actually resolves below city level."""
    if path is None:
        return None

    source = gpd.read_file(path)
    print(f"  tree canopy source: {path.name} ({len(source)} polygons)")

    percent_column = next(
        (c for c in source.columns
         if any(t in c.lower() for t in ("pct", "percent", "canopy", "tree"))
         and pd.api.types.is_numeric_dtype(source[c])),
        None,
    )
    if percent_column is None:
        print("  SKIPPED: no numeric canopy percentage column found.")
        return None

    study_polygons = source[source.to_crs(config.PROJECTED_CRS).intersects(kept.union_all())]
    if len(study_polygons) < 20:
        print(f"  SKIPPED: only {len(study_polygons)} polygon(s) cover the study area, so this")
        print("           layer is aggregated above tract level (cities, not tracts).")
        print(f"           A feature built from it would be near-constant "
              f"({study_polygons[percent_column].tolist()[:4]}) and teach the model nothing.")
        return None

    print(f"  using column {percent_column!r}")
    return _area_weighted(kept, path, percent_column, "tree_canopy_pct")


# --------------------------------------------------------------- step 8

def finalise(kept: gpd.GeoDataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Attach the label, drop unusable rows, save, and report."""
    banner(8, "Label, save and report")

    meta = kept.set_index("tract_fips")[[
        "approx_location", "n_tiles", "tract_area_km2",
        config.LABEL_COLUMN, "pollution_burden_pctl", "population_char_pctl",
    ]]
    frame = features.join(meta)
    frame.index.name = "tract_fips"

    missing_label = frame[config.LABEL_COLUMN].isna()
    if missing_label.any():
        print(f"  DROPPED {missing_label.sum()} tract(s) with no {config.LABEL_COLUMN} "
              "(CalEnviroScreen -999 sentinel)")
        frame = frame[~missing_label]

    present = [f for f in config.FEATURES_FULL if f in frame.columns]
    absent = [f for f in config.FEATURES_FULL if f not in frame.columns]
    incomplete = frame[present].isna().any(axis=1)
    if incomplete.any():
        print(f"  {incomplete.sum()} tract(s) have at least one missing feature "
              "(kept; imputation is a Step 4 decision)")

    frame = frame.reset_index()
    frame.to_parquet(OUTPUT_PATH, index=False)

    # Same table with tract geometry, in lon/lat. The diagnostic notebook maps
    # from it and the Step 6 frontend will hand it straight to MapLibre.
    geo = (
        kept[["tract_fips", "geometry"]]
        .merge(frame, on="tract_fips", how="inner")
        .to_crs(config.GEOGRAPHIC_CRS)
    )
    geo.to_file(GEOJSON_PATH, driver="GeoJSON")

    print()
    print(f"  SAVED {OUTPUT_PATH}")
    print(f"  SAVED {GEOJSON_PATH} ({len(geo)} tract polygons, for the map)")
    print(f"  shape: {frame.shape[0]} tracts x {len(present)} features + label")
    if absent:
        print(f"  ABSENT features: {absent}")

    print()
    print("  preview (df.head()):")
    preview = ["tract_fips", "approx_location", *present[:6], config.LABEL_COLUMN]
    print(frame[[c for c in preview if c in frame.columns]].head().to_string(index=False))

    report_correlations(frame, present)
    return frame


def report_correlations(frame: pd.DataFrame, present: list[str]) -> None:
    """Correlations against the label, plus the diagnostics that must not be hidden."""
    print()
    print(rule("="))
    print(f"CORRELATION WITH THE LABEL ({config.LABEL_COLUMN})")
    print(rule("="))

    correlations = (
        frame[present + [config.LABEL_COLUMN]]
        .corr(numeric_only=True)[config.LABEL_COLUMN]
        .drop(config.LABEL_COLUMN)
        .sort_values(key=abs, ascending=False)
    )
    for name, value in correlations.items():
        strength = "STRONG" if abs(value) > 0.5 else "usable" if abs(value) > 0.3 else "weak"
        marker = " <--" if name in ("elevation_m", "distance_to_coast_km") and abs(value) > 0.3 else ""
        print(f"  {name:<24} r = {value:+.3f}   {strength}{marker}")

    strong = (correlations.abs() > 0.3).sum()
    print()
    print(f"  {strong} feature(s) exceed |r| > 0.3.")
    print("  If XGBoost is going to work at Step 4, we should see |r| > 0.3 for at "
          "least 3 features.")
    if strong < 3:
        print("  WARNING: below that bar. Expect a weak model and say so honestly.")

    geographic = [c for c in ("elevation_m", "distance_to_coast_km") if c in correlations.index]
    if geographic and correlations.abs().idxmax() in geographic:
        print()
        print("  NOTE: a geographic feature is the single strongest predictor. That")
        print("  confirms the Step 2 finding that maritime influence, not land cover,")
        print("  governs heat at this scale. It is a result, not a bug.")

    if {"elevation_m", "distance_to_coast_km"} <= set(present):
        collinear = frame["elevation_m"].corr(frame["distance_to_coast_km"])
        print()
        print(f"  COLLINEARITY elevation_m vs distance_to_coast_km: r = {collinear:+.3f}")
        if abs(collinear) > 0.8:
            print("  -> above 0.8. They carry the same information; drop one at Step 4.")

    variances = frame[present].std()
    dead = variances[variances < 1e-6]
    if len(dead):
        print()
        print(f"  DEAD FEATURES (no spatial variance): {list(dead.index)}")

    plot_correlation_matrix(frame, present)


def plot_correlation_matrix(frame: pd.DataFrame, present: list[str]) -> None:
    columns = present + [config.LABEL_COLUMN]
    matrix = frame[columns].corr(numeric_only=True)

    fig, ax = plt.subplots(figsize=(10, 8.5))
    image = ax.imshow(matrix, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(columns)), columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(columns)), columns, fontsize=8)
    for i in range(len(columns)):
        for j in range(len(columns)):
            value = matrix.iat[i, j]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=7,
                    color="white" if abs(value) > 0.55 else "black")
    ax.set_title(f"HeatGov AI - feature correlations ({len(frame)} tracts)")
    fig.colorbar(image, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(CORRELATION_PLOT_PATH, dpi=140)
    plt.close(fig)
    print()
    print(f"  Correlation heatmap saved to {CORRELATION_PLOT_PATH}")


# --------------------------------------------------------------- entry point

def main() -> int:
    parser = argparse.ArgumentParser(description="Build the HeatGov AI feature table")
    parser.parse_args()

    print(config.describe())

    env, points = load_fortyguard_layers()
    tracts = load_tracts()
    kept, joined = select_tracts(tracts, points)
    features = aggregate_fortyguard(kept, joined, env)
    features, kept = add_geography(kept, features)
    features = add_census(kept, features)
    features = add_landcover(kept, features)
    finalise(kept, features)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
