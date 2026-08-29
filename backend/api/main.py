"""HeatGov AI — Central Los Angeles

FortyGuard Hackathon 2026
Authors: Zahra Yeslek (ML & Backend), Mariem Elbechir (Data & Frontend)
License: MIT

REST API.

Start from the project root:

    .venv/Scripts/python.exe -m uvicorn backend.api.main:app --reload --port 8000

Interactive docs once running: http://localhost:8000/docs

Every endpoint delegates to the same functions the Gemini agent calls, so the
conversational answer and the REST answer can never disagree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import geopandas as gpd  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import config  # noqa: E402
from agent import tools  # noqa: E402
from ml.predict import ModelNotTrained, get_model  # noqa: E402

app = FastAPI(
    title="HeatGov AI",
    description=(
        "Turns hyperlocal FortyGuard temperature data into a budgeted "
        "heat-mitigation plan for Central Los Angeles."
    ),
    version="1.0.0",
)

# The Next.js dev server runs on a different port, which browsers treat as a
# different origin and block by default. This is the explicit allow-list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------- request bodies

class PredictRequest(BaseModel):
    tract_fips: str = Field(..., description="11-digit census tract FIPS code")


class OptimizeRequest(BaseModel):
    budget_usd: float = Field(..., gt=0, description="Available budget in US dollars")
    top_n: int = Field(10, ge=1, le=50, description="How many high-risk zones to consider")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


# --------------------------------------------------------------- session store

# In-memory only. A hackathon demo does not need persistence, and keeping
# conversations out of disk avoids storing anything a user typed.
_SESSIONS: dict[str, list] = {}


# --------------------------------------------------------------- endpoints

@app.get("/api/health")
def health() -> dict:
    """Liveness plus the headline cross-validated scores of both models."""
    metrics_path = config.MODELS_DIR / "metrics.json"
    model_a_r2 = model_b_r2 = None
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        for entry in metrics.get("models", []):
            if entry["model"] == "XGBoost Model A":
                model_a_r2 = round(entry["cv_r2_mean"], 2)
            elif entry["model"] == "XGBoost Model B":
                model_b_r2 = round(entry["cv_r2_mean"], 2)

    try:
        get_model()
        model_loaded = True
    except ModelNotTrained:
        model_loaded = False

    return {
        "status": "ok" if model_loaded else "model_not_trained",
        "model_a_r2": model_a_r2,
        "model_b_r2": model_b_r2,
        "model_loaded": model_loaded,
        "study_area": config.CITY_NAME,
        "tracts": 94,
        "gemini_model": config.GEMINI_MODEL,
        "gemini_configured": bool(config.GEMINI_API_KEY),
    }


@app.get("/api/heatmap/{analytic_type}")
def heatmap(analytic_type: str) -> dict:
    """Return one cached FortyGuard layer as GeoJSON."""
    if analytic_type not in tools.HEATMAP_LAYERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown layer {analytic_type!r}. "
                   f"Available: {sorted(tools.HEATMAP_LAYERS)}",
        )

    path = config.cache_path(analytic_type)
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Layer {analytic_type} is not cached. "
                   "Run backend/data_pipeline/pull_heatmaps.py.",
        )

    column, unit, description = tools.HEATMAP_LAYERS[analytic_type]
    gdf = gpd.read_parquet(path)
    keep = [c for c in ("tile_id", column) if c in gdf.columns]
    payload = json.loads(gdf[keep + ["geometry"]].to_json())

    # The map needs a colour scale. Sending min/max here means the browser does
    # not have to scan 8,674 values before it can draw anything. p5/p95 are sent
    # alongside because a single outlier tile stretched over min/max flattens
    # the whole ramp into one colour.
    series = gdf[column].dropna()
    payload["metadata"] = {
        "analytic_type": analytic_type,
        "value_column": column,
        "unit": unit,
        "description": description,
        "tiles": len(gdf),
        "stats": {
            "min": round(float(series.min()), 2),
            "p5": round(float(series.quantile(0.05)), 2),
            "mean": round(float(series.mean()), 2),
            "p95": round(float(series.quantile(0.95)), 2),
            "max": round(float(series.max()), 2),
        },
    }
    return payload


@app.get("/api/zones/ranked")
def zones_ranked(top_n: int = 10) -> dict:
    """Census tracts ranked by predicted risk, with both model scores."""
    if not 1 <= top_n <= 50:
        raise HTTPException(status_code=422, detail="top_n must be between 1 and 50")
    return tools.get_top_risk_zones(top_n)


@app.post("/api/predict")
def predict(request: PredictRequest) -> dict:
    """Both scores for one tract, plus its strongest physical drivers."""
    result = tools.explain_zone(request.tract_fips)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return {
        "tract_fips": result["tract_fips"],
        "name": result["name"],
        "risk_score_b": result["risk_score"],
        "risk_score_a": result["physical_score"],
        "official_calenviroscreen_score": result["official_calenviroscreen_score"],
        "top_shap_features": result["top_physical_drivers"],
        "note": result["note"],
    }


@app.post("/api/optimize")
def optimize(request: OptimizeRequest) -> dict:
    """Best combination of interventions for a budget."""
    result = tools.optimize_budget(request.budget_usd, request.top_n)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@app.post("/api/agent/chat")
def agent_chat(request: ChatRequest) -> dict:
    """Ask the Gemini agent. It decides which tools to run."""
    from agent.gemini_agent import AgentUnavailable, get_agent

    try:
        agent = get_agent()
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    history = _SESSIONS.get(request.session_id, []) if request.session_id else []

    try:
        result = agent.chat(request.message, history)
    except AgentUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if request.session_id:
        _SESSIONS[request.session_id] = result["history"]

    return {
        "reply": result["reply"],
        "tool_calls": [
            {"tool": call["tool"], "args": call["args"]} for call in result["tool_calls"]
        ],
        "rounds": result["rounds"],
        "model": result["model"],
        "session_id": request.session_id,
    }
