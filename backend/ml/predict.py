"""Inference and explanation for the trained HeatGov AI model.

Two entry points, both used by the FastAPI layer in Step 5:

    predict(features_dict) -> risk score 0-100
    explain(tract_id)      -> the three features that moved that tract's score most

Run directly for a self-test:

    .venv/Scripts/python.exe backend/ml/predict.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

warnings.filterwarnings("ignore")

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shap  # noqa: E402

import config  # noqa: E402

MODELS_DIR = config.MODELS_DIR
FEATURES_PATH = config.PROCESSED_DIR / "zone_features.parquet"

# Plain-English names for the report and for the Gemini agent to quote.
FEATURE_LABELS = {
    "temp_max_22h": "night-time heat (22:00 temperature)",
    "temp_max_15h": "afternoon heat (15:00 temperature)",
    "exceedance_hours_30C": "hours above 30 C in July",
    "persistence_max_hours": "longest unbroken stretch above 30 C",
    "distance_to_coast_km": "distance inland from the coast",
    "impervious_surface_pct": "paved and built-up surface",
    "elevation_m": "elevation",
    "pop_density": "population density",
    "pop_over_65_pct": "share of residents over 65",
    "median_income": "median household income",
    "peak_at_2h": "heat peaking at 02:00",
    "peak_at_3h": "heat peaking at 03:00",
    "peak_at_16h": "heat peaking at 16:00",
}

FEATURE_UNITS = {
    "temp_max_22h": "C",
    "temp_max_15h": "C",
    "exceedance_hours_30C": "h",
    "persistence_max_hours": "h",
    "distance_to_coast_km": "km",
    "impervious_surface_pct": "%",
    "elevation_m": "m",
    "pop_density": "people/km2",
    "pop_over_65_pct": "%",
    "median_income": "$",
}


class ModelNotTrained(RuntimeError):
    """The artifacts are missing. Run backend/ml/train.py first."""


class VulnerabilityModel:
    """The trained model plus everything needed to explain a single tract."""

    def __init__(self) -> None:
        model_path = MODELS_DIR / "best_model.pkl"
        columns_path = MODELS_DIR / "feature_columns.json"
        if not model_path.exists() or not columns_path.exists():
            raise ModelNotTrained(
                f"{model_path.name} or {columns_path.name} is missing. "
                "Run: .venv/Scripts/python.exe backend/ml/train.py"
            )

        self.model = joblib.load(model_path)
        meta = json.loads(columns_path.read_text(encoding="utf-8"))
        self.columns: list[str] = meta["columns"]
        self.peak_hour_columns: list[str] = meta.get("peak_hour_columns", [])
        self.model_name: str = meta.get("best_model", "unknown")
        self.label: str = meta.get("label", config.LABEL_COLUMN)

        # Rebuilding the explainer from the model is cheap and avoids depending
        # on a pickle that may not survive a library upgrade.
        self.explainer = shap.TreeExplainer(self.model)

        self._tracts: pd.DataFrame | None = None

    # ------------------------------------------------------------ features

    def _tract_table(self) -> pd.DataFrame:
        """The Step 3 feature table, one-hot encoded the same way as training."""
        if self._tracts is None:
            if not FEATURES_PATH.exists():
                raise ModelNotTrained(
                    f"{FEATURES_PATH} is missing. Run backend/data_pipeline/build_features.py"
                )
            frame = pd.read_parquet(FEATURES_PATH)
            frame = self._encode_peak_hour(frame)
            self._tracts = frame.set_index("tract_fips")
        return self._tracts

    def _encode_peak_hour(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Recreate the training-time indicator columns, in the same order."""
        if "peak_hour_mode" not in frame.columns:
            return frame
        for name in self.peak_hour_columns:
            hour = float(name.removeprefix("peak_at_").removesuffix("h"))
            frame[name] = (frame["peak_hour_mode"] == hour).astype(int)
        return frame

    def _row_from_dict(self, features: dict) -> pd.DataFrame:
        """Build a single model-ready row, expanding peak_hour_mode if given."""
        values = dict(features)

        if "peak_hour_mode" in values and self.peak_hour_columns:
            hour = values.pop("peak_hour_mode")
            for name in self.peak_hour_columns:
                expected = float(name.removeprefix("peak_at_").removesuffix("h"))
                values.setdefault(name, int(float(hour) == expected))

        missing = [c for c in self.columns if c not in values]
        if missing:
            raise KeyError(
                f"Missing feature(s) {missing}. This model expects: {self.columns}"
            )

        return pd.DataFrame([[values[c] for c in self.columns]], columns=self.columns)

    # ------------------------------------------------------------ inference

    def predict(self, features: dict) -> float:
        """Predicted vulnerability score, clipped to the label's 0-100 range."""
        row = self._row_from_dict(features)
        raw = float(self.model.predict(row)[0])
        return float(np.clip(raw, 0.0, 100.0))

    def predict_tract(self, tract_id: str) -> float:
        row = self._lookup(tract_id)
        return float(np.clip(float(self.model.predict(row[self.columns])[0]), 0.0, 100.0))

    def _lookup(self, tract_id: str) -> pd.DataFrame:
        table = self._tract_table()
        key = str(tract_id).zfill(11)
        if key not in table.index:
            raise KeyError(
                f"Unknown tract {tract_id!r}. The study area holds {len(table)} tracts, "
                f"for example {list(table.index[:3])}."
            )
        return table.loc[[key]]

    # ------------------------------------------------------------ explanation

    def explain(self, tract_id: str, top_n: int = 3) -> dict:
        """Return the features that pushed this tract's score furthest.

        SHAP attributes a prediction to its inputs additively: base value plus
        one contribution per feature equals the prediction. A positive
        contribution pushed this tract towards higher vulnerability.
        """
        row = self._lookup(tract_id)
        design = row[self.columns]
        contributions = self.explainer.shap_values(design)[0]
        prediction = float(np.clip(float(self.model.predict(design)[0]), 0.0, 100.0))

        order = np.argsort(np.abs(contributions))[::-1][:top_n]
        drivers = []
        for rank, index in enumerate(order, start=1):
            name = self.columns[index]
            value = float(design.iloc[0, index])
            shap_value = float(contributions[index])
            drivers.append({
                "rank": rank,
                "feature": name,
                "label": FEATURE_LABELS.get(name, name),
                "value": value,
                "unit": FEATURE_UNITS.get(name, ""),
                "shap": shap_value,
                "direction": "increases" if shap_value > 0 else "decreases",
                "sentence": _sentence(name, value, shap_value),
            })

        return {
            "tract_id": row.index[0],
            "location": str(row.iloc[0].get("approx_location", "")),
            "predicted_score": prediction,
            "actual_score": float(row.iloc[0][self.label]),
            "base_value": float(self.explainer.expected_value),
            "model": self.model_name,
            "drivers": drivers,
        }

    def top_risk_tracts(self, top_n: int = 5) -> pd.DataFrame:
        """Highest predicted scores, for the agent's get_top_risk_zones tool."""
        table = self._tract_table()
        scores = self.model.predict(table[self.columns])
        result = table[["approx_location", self.label]].copy()
        result["predicted_score"] = np.clip(scores, 0.0, 100.0)
        return result.sort_values("predicted_score", ascending=False).head(top_n)


def _sentence(name: str, value: float, shap_value: float) -> str:
    """One clause a municipal official can read without a statistics course."""
    label = FEATURE_LABELS.get(name, name)
    unit = FEATURE_UNITS.get(name, "")
    direction = "raises" if shap_value > 0 else "lowers"
    if unit == "$":
        shown = f"${value:,.0f}"
    elif unit:
        shown = f"{value:,.1f} {unit}"
    else:
        shown = f"{value:,.2f}"
    return f"{label} of {shown} {direction} the score by {abs(shap_value):.1f} points"


_MODEL: VulnerabilityModel | None = None


def get_model() -> VulnerabilityModel:
    """Load the model once and reuse it (FastAPI will call this per request)."""
    global _MODEL
    if _MODEL is None:
        _MODEL = VulnerabilityModel()
    return _MODEL


def predict(features_dict: dict) -> float:
    return get_model().predict(features_dict)


def explain(tract_id: str, top_n: int = 3) -> dict:
    return get_model().explain(tract_id, top_n=top_n)


def main() -> int:
    model = get_model()
    print(f"Loaded {model.model_name} with {len(model.columns)} features")
    print(f"  columns: {model.columns}")

    print("\n--- top_risk_tracts(5) ---")
    print(model.top_risk_tracts(5).to_string())

    worst = model.top_risk_tracts(1).index[0]
    print(f"\n--- explain({worst}) ---")
    result = model.explain(worst)
    print(f"  predicted {result['predicted_score']:.1f} | "
          f"actual {result['actual_score']:.1f} | base {result['base_value']:.1f}")
    for driver in result["drivers"]:
        print(f"    {driver['rank']}. {driver['sentence']}")

    print("\n--- predict(features_dict) round trip ---")
    table = model._tract_table()
    sample = table.loc[worst, model.columns].to_dict()
    print(f"  predict() -> {model.predict(sample):.2f}")
    print(f"  predict_tract() -> {model.predict_tract(worst):.2f}")

    print("\n--- error handling ---")
    try:
        model.predict({"temp_max_22h": 19.0})
    except KeyError as exc:
        print(f"  incomplete input raises KeyError: {str(exc)[:90]}...")
    try:
        model.explain("00000000000")
    except KeyError as exc:
        print(f"  unknown tract raises KeyError: {str(exc)[:90]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
