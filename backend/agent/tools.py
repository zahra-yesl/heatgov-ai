"""The five tools the Gemini agent may call.

Every function here returns plain JSON-serialisable data, because Gemini reads
the return value back as text. Each one is also directly usable by the FastAPI
layer, so the agent and the REST API can never drift apart.

MISSING TREE CANOPY, HANDLED HONESTLY
-------------------------------------
`tree_canopy_pct` is not in the feature table: the canopy layer available at
Step 3 was aggregated to city level and the pipeline rejected it. The
intervention rule needs it to choose between trees and shade.

Rather than invent a number, we:
  * apply the impervious-surface branch normally, which needs no canopy data,
    and mark those recommendations "high" confidence;
  * for the remainder, use pervious surface (100 - impervious) as an explicit
    stand-in, and mark them "provisional".

Pervious surface is not canopy - it also counts grass, bare soil and water - so
it over-estimates tree cover. Every response carries `canopy_data_available` so
the agent can say so out loud instead of quietly implying certainty.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402
from ml.predict import get_model  # noqa: E402
from optimizer.intervention_rules import recommend_intervention as _rule  # noqa: E402
from optimizer.knapsack import INTERVENTION_COSTS, optimize as _optimize  # noqa: E402

CANOPY_COLUMN = "tree_canopy_pct"

HEATMAP_LAYERS = {
    "tcm_peak_15h": ("max_temperature", "C", "Afternoon temperature at 15:00 local"),
    "tcm_peak_22h": ("max_temperature", "C", "Night temperature at 22:00 local"),
    "tcm_daily": ("average_temperature", "C", "24-hour average temperature"),
    "exceedance": ("value", "hours", "Hours above 30 C during July 2025"),
    "persistence": ("value", "hours", "Longest unbroken stretch above 30 C"),
    "time_of_measure": ("value", "hour of day", "Local hour of the daily thermal peak"),
}


def _zone_frame() -> pd.DataFrame:
    """Feature table with both model scores attached."""
    model = get_model()
    table = model._tract_table().copy()

    meta = _feature_columns()
    scores_b = model.model.predict(table[model.columns])
    table["risk_score"] = np.clip(scores_b, 0.0, 100.0)

    physical = meta.get("features_model_a", [])
    available = [c for c in physical if c in table.columns]
    if len(available) == len(physical):
        table["physical_score"] = np.clip(
            _model_a().predict(table[physical]), 0.0, 100.0
        )
    else:
        table["physical_score"] = np.nan
    return table


def _feature_columns() -> dict:
    import json

    path = config.MODELS_DIR / "feature_columns.json"
    return json.loads(path.read_text(encoding="utf-8"))


_MODEL_A = None


def _model_a():
    """Model A is refit on demand: only Model B was persisted at Step 4.

    Refitting on 94 rows with fixed hyperparameters takes well under a second,
    and keeps the physical-only score available for the scientific explanation
    without a second pickle to keep in sync.
    """
    global _MODEL_A
    if _MODEL_A is None:
        from xgboost import XGBRegressor

        meta = _feature_columns()
        model = get_model()
        table = model._tract_table()
        features = meta["features_model_a"]
        _MODEL_A = XGBRegressor(
            max_depth=3, n_estimators=100, learning_rate=0.05,
            random_state=42, objective="reg:squarederror", n_jobs=1, verbosity=0,
        ).fit(table[features], table[config.LABEL_COLUMN])
    return _MODEL_A


_CENTROIDS: dict[str, tuple[float, float]] | None = None


def _centroid(tract_fips: str) -> tuple[float, float]:
    """Tract centroid as (lat, lon), from a cache built once per process.

    Re-reading the GeoJSON per tract cost about 3 seconds each, which made a
    ten-zone answer unusable in a live demo.
    """
    global _CENTROIDS
    if _CENTROIDS is None:
        gdf = gpd.read_file(config.PROCESSED_DIR / "zone_features.geojson")
        points = gdf.geometry.centroid
        _CENTROIDS = {
            str(fips): (float(point.y), float(point.x))
            for fips, point in zip(gdf["tract_fips"], points)
        }
    return _CENTROIDS.get(tract_fips, (float("nan"), float("nan")))


def _land_cover(row: pd.Series) -> tuple[dict, bool]:
    """Land-cover inputs for the intervention rule, and whether canopy is real."""
    impervious = float(row["impervious_surface_pct"])
    if CANOPY_COLUMN in row.index and pd.notna(row.get(CANOPY_COLUMN)):
        return {"impervious_surface_pct": impervious,
                "tree_canopy_pct": float(row[CANOPY_COLUMN])}, True
    # Stand-in: pervious surface. Over-estimates canopy, so it is flagged.
    return {"impervious_surface_pct": impervious,
            "tree_canopy_pct": max(0.0, 100.0 - impervious)}, False


# --------------------------------------------------------------------- tools

def get_top_risk_zones(top_n: int = 10) -> dict:
    """Return the most heat-vulnerable census tracts, highest risk first."""
    top_n = max(1, min(int(top_n), 50))
    frame = _zone_frame().sort_values("risk_score", ascending=False).head(top_n)

    zones = []
    for fips, row in frame.iterrows():
        latitude, longitude = _centroid(fips)
        zones.append({
            "tract_fips": fips,
            "name": str(row.get("approx_location", "Los Angeles")),
            "risk_score": round(float(row["risk_score"]), 1),
            "physical_score": (
                round(float(row["physical_score"]), 1)
                if pd.notna(row["physical_score"]) else None
            ),
            "night_temp_c": round(float(row["temp_max_22h"]), 2),
            "impervious_surface_pct": round(float(row["impervious_surface_pct"]), 1),
            "median_income_usd": int(row["median_income"]),
            "lat": round(latitude, 5),
            "lon": round(longitude, 5),
        })
    return {"zones": zones, "count": len(zones), "total_tracts_analyzed": 94}


def explain_zone(tract_fips: str) -> dict:
    """Explain a tract's score using SHAP on the physical-only model.

    Model A is used on purpose. Model B scores higher but its explanation is led
    by median income, which mirrors CalEnviroScreen's own socio-economic half -
    circular, and useless as advice. Model A answers the question a city can act
    on: what about this place, physically, makes it dangerous?
    """
    model = get_model()
    fips = str(tract_fips).zfill(11)
    table = model._tract_table()
    if fips not in table.index:
        return {"error": f"Unknown tract {tract_fips}. The study area holds "
                         f"{len(table)} tracts in Central Los Angeles."}

    import shap

    meta = _feature_columns()
    features = meta["features_model_a"]
    row = table.loc[[fips]][features]
    model_a = _model_a()
    contributions = shap.TreeExplainer(model_a).shap_values(row)[0]

    from ml.predict import FEATURE_LABELS, FEATURE_UNITS, _sentence

    order = np.argsort(np.abs(contributions))[::-1][:3]
    drivers = [{
        "feature": features[i],
        "label": FEATURE_LABELS.get(features[i], features[i]),
        "value": round(float(row.iloc[0, i]), 2),
        "unit": FEATURE_UNITS.get(features[i], ""),
        "impact_points": round(float(contributions[i]), 2),
        "explanation": _sentence(features[i], float(row.iloc[0, i]), float(contributions[i])),
    } for i in order]

    full = model.explain(fips, top_n=3)
    return {
        "tract_fips": fips,
        "name": str(table.loc[fips].get("approx_location", "Los Angeles")),
        "risk_score": round(full["predicted_score"], 1),
        "physical_score": round(float(np.clip(model_a.predict(row)[0], 0, 100)), 1),
        "official_calenviroscreen_score": round(full["actual_score"], 1),
        "top_physical_drivers": drivers,
        "note": (
            "Drivers come from the physical-only model, so they describe what the "
            "environment contributes, independent of income."
        ),
    }


def recommend_intervention(tract_fips: str) -> dict:
    """Recommend the intervention best suited to a tract's built form."""
    model = get_model()
    fips = str(tract_fips).zfill(11)
    table = model._tract_table()
    if fips not in table.index:
        return {"error": f"Unknown tract {tract_fips}."}

    row = table.loc[fips]
    inputs, canopy_real = _land_cover(row)
    intervention = _rule(inputs)

    from optimizer.knapsack import EXPECTED_REDUCTION_C, INTERVENTION_DETAIL

    high_confidence = inputs["impervious_surface_pct"] > 80.0
    return {
        "tract_fips": fips,
        "intervention": intervention,
        "detail": INTERVENTION_DETAIL[intervention],
        "estimated_cost_usd": INTERVENTION_COSTS[intervention],
        "expected_reduction_c": EXPECTED_REDUCTION_C[intervention],
        "impervious_surface_pct": round(inputs["impervious_surface_pct"], 1),
        "canopy_data_available": canopy_real,
        "confidence": "high" if (canopy_real or high_confidence) else "provisional",
        "confidence_note": (
            "Based on measured impervious surface."
            if (canopy_real or high_confidence)
            else "Tree canopy data is unavailable for this study area; pervious "
                 "surface was used as a stand-in, which over-estimates canopy. "
                 "Treat the trees-versus-shade choice as provisional."
        ),
        "source": "Smith et al. 2025, doi:10.1038/s43247-025-02462-3",
    }


def optimize_budget(budget_usd: float, top_n: int = 10) -> dict:
    """Compute the best combination of interventions for a given budget."""
    budget_usd = float(budget_usd)
    if budget_usd <= 0:
        return {"error": "Budget must be positive."}

    frame = _zone_frame().sort_values("risk_score", ascending=False)
    frame = frame.head(max(1, min(int(top_n), len(frame))))

    canopy_real = CANOPY_COLUMN in frame.columns and frame[CANOPY_COLUMN].notna().any()
    zones = []
    for fips, row in frame.iterrows():
        inputs, _ = _land_cover(row)
        zones.append({
            "tract_fips": fips,
            "risk_score": float(row["risk_score"]),
            "name": str(row.get("approx_location", "Los Angeles")),
            **inputs,
        })

    result = _optimize(zones, budget_usd)
    result["canopy_data_available"] = bool(canopy_real)
    if not canopy_real:
        result["data_caveat"] = (
            "Tree canopy data is unavailable for this study area. Cool-roof "
            "recommendations rest on measured impervious surface and are firm; "
            "the trees-versus-shade split uses pervious surface as a stand-in "
            "and is provisional."
        )
    return result


def get_heatmap_stats(analytic_type: str) -> dict:
    """Return summary statistics for one cached FortyGuard layer."""
    if analytic_type not in HEATMAP_LAYERS:
        return {"error": f"Unknown layer {analytic_type!r}.",
                "available": sorted(HEATMAP_LAYERS)}

    column, unit, description = HEATMAP_LAYERS[analytic_type]
    path = config.cache_path(analytic_type)
    if not path.exists():
        return {"error": f"Layer {analytic_type} is not cached. Run pull_heatmaps.py."}

    gdf = gpd.read_parquet(path)
    series = gdf[column].dropna()
    return {
        "analytic_type": analytic_type,
        "description": description,
        "unit": unit,
        "tiles": int(len(gdf)),
        "min": round(float(series.min()), 2),
        "mean": round(float(series.mean()), 2),
        "max": round(float(series.max()), 2),
        "std": round(float(series.std()), 3),
        "spread": round(float(series.max() - series.min()), 2),
        "resolution_m": config.GRANULARITY_M,
        "area_km2": round(config.study_area_km2(), 1),
        "period": f"{config.STUDY_START_DATE} to {config.STUDY_END_DATE}",
    }


TOOL_FUNCTIONS = {
    "get_top_risk_zones": get_top_risk_zones,
    "explain_zone": explain_zone,
    "recommend_intervention": recommend_intervention,
    "optimize_budget": optimize_budget,
    "get_heatmap_stats": get_heatmap_stats,
}
