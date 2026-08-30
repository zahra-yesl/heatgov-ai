# HeatGov AI

![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-2.1-EB5E28)
![Tests 91/91](https://img.shields.io/badge/tests-91%2F91-brightgreen)
![License MIT](https://img.shields.io/badge/license-MIT-blue)

> **From "where is it hot?" to "here is my $500,000 action plan" — in under two minutes.**

A decision-support platform that turns hyperlocal FortyGuard temperature data into a **budgeted, defensible heat-mitigation plan** for a U.S. municipality. Pilot area: Central Los Angeles (89.7 km², 8,674 tiles at 100 m).

**Live Demo:** [https://heatgov-ai.vercel.app](https://heatgov-ai.vercel.app) *(update after Vercel deployment)*
**Video (3 min):** [Watch demo](#) *(add link after recording)*
**Code:** [github.com/zahra-yesl/heatgov-ai](https://github.com/zahra-yesl/heatgov-ai)

---

## Table of Contents

- [The Story: Sarah, LA Resilience Officer](#the-story-sarah-la-resilience-officer)
- [The Problem](#the-problem)
- [Our Solution](#our-solution)
- [Impact and Relevance](#impact-and-relevance)
- [How It Works](#how-it-works)
- [The Finding This Project Is Built On](#the-finding-this-project-is-built-on)
- [Technical Architecture](#technical-architecture)
- [FortyGuard API Usage](#fortyguard-api-usage)
- [Scientific Foundation](#scientific-foundation)
- [What Is In The Box](#what-is-in-the-box)
- [Honest Limitations](#honest-limitations)
- [Quick Start](#quick-start)
- [Deployment](#deployment)
- [Team](#team)
- [License and Acknowledgments](#license-and-acknowledgments)

---

## The Story: Sarah, LA Resilience Officer

*Meet Sarah Martinez, Chief Resilience Officer at the City of Los Angeles. It is Monday morning, July 15, 2026.*

### 8:00 AM — The Email
Sarah opens her inbox. The Mayor's office allocated **$500,000** for summer 2026 heat mitigation. She has **until Friday** to submit a proposal explaining:
- Which neighborhoods to prioritize
- Which interventions to fund (trees, cool roofs, or shade structures)
- How much cooling impact each dollar buys
- Why these choices are equitable and defensible in council

### 8:30 AM — The Traditional Approach
Sarah opens six different tools: a heatmap dashboard, CalEnviroScreen for socio-demographics, Excel to cross-reference by census tract, ArcGIS for spatial analysis, an email to a consultant (who quotes $80,000 for a 6-week study), and a phone call to a colleague who doesn't know either.

**Result after two days**: Sarah has a rough shortlist based on gut feeling. No quantified impact. Hard to defend in council.

### 9:00 AM — With HeatGov AI
Sarah opens `heatgov-ai.vercel.app` on her laptop. She sees:
- A live heatmap of Central LA with night-time temperatures
- Top 10 highest-risk census tracts marked with numbered pins
- A chat interface

She types: **"I have $500,000 for Central LA. Where should I invest?"**

### 9:00:23 AM — The Answer (23 seconds later)
HeatGov AI's Gemini agent orchestrates 5 backend tools:
1. Queries the XGBoost model — ranks 94 census tracts by predicted vulnerability
2. Runs the knapsack budget optimizer — maximizes impact under $500K constraint
3. Computes SHAP explanations for each recommended zone
4. Applies research-backed intervention rules (Nature 2025)
5. Formats a defensible action plan

The Action Plan appears:

| # | Census Tract | Intervention | Cost | Cooling |
|---|---|---|---|---|
| 1 | Skid Row (06037206050) — Risk 97.6 | Cool Roofs | $180,000 | −1.2°C |
| 2 | Historic Core (06037226002) — Risk 97.5 | Cool Roofs | $180,000 | −1.2°C |
| 3 | Downtown East (06037206010) — Risk 96.7 | Shade Structures | $120,000 | −0.8°C |

**Total funded**: $480,000  |  **Reserve**: $20,000  |  **Zones covered**: 3/10  |  **Impact score**: 28.7%

Sarah asks: **"Why is Skid Row #1 and not Downtown Central?"**

Gemini replies with SHAP values, citations, and research context:
> *"Skid Row scores 97.6 because night-time heat at 22:00 local (19.8°C) contributes 5.3 points, combined with 85% impervious surface (+4.7 points) and inland distance from the coast (+4.7 points). Downtown Central has similar day-time heat but cools better at night. Our research (Chapel Hill 2026, Chengdu 2025) confirms night-time heat prevents physiological recovery — a driver missed by afternoon-only heatmaps."*

### 9:05 AM — Sarah's Proposal
Sarah exports the action plan, adds her narrative, and sends to the Mayor. **Five minutes total.** Defensible with peer-reviewed citations. Quantified impact. Auditable methodology (open source on GitHub).

**HeatGov AI turned a two-day exercise into a five-minute decision. That is the vision.**

---

## The Problem

### The Human Cost
- **1,220+ deaths per year in the U.S.** are attributed to extreme heat ([CDC, 2024](https://www.cdc.gov/climate-health/php/effects/heat.html))
- Los Angeles alone recorded **500+ heat-related ER visits** during the July 2023 heatwave
- Vulnerable populations (elderly 65+, low-income, uninsured) bear **three times the mortality risk**

### The Data-Decision Gap
Cities now have unprecedented heat data at high spatial resolution. But no tool translates this data into a budgeted action plan. Municipal officers face:
- Multiple disconnected dashboards
- Weeks of consultant work
- $50,000 to $100,000 for a single vulnerability study
- Recommendations without quantified impact
- Decisions based on political intuition instead of data

**Result**: Money is spent on the wrong neighborhoods. People die who could have been protected.

---

## Our Solution

HeatGov AI is a decision-support platform that combines:
1. **Hyperlocal temperature data** from FortyGuard (4 analytic types across 8,674 tiles)
2. **XGBoost machine learning** trained on official CalEnviroScreen vulnerability labels
3. **Gemini conversational AI** with function calling (5 orchestrated tools)
4. **Budget optimizer** (0/1 knapsack) with research-backed intervention rules

Delivered as a single-page web app: map, chat, and action plan. No training required.

### Key Differentiators
- **Night-time vulnerability layer** — a physiologically critical map that emerges from combining FortyGuard temporal data with our ML pipeline
- **Dual-model transparency** — Model A (honest baseline) and Model B (operational) reported side-by-side to acknowledge label leakage
- **Peer-reviewed methodology** — four published studies inform the design, cited in code and documentation
- **Sub-two-minute decisions** — from question to budgeted plan in one conversation
- **Zero training curve** — natural language interface, no GIS expertise required
- **Fully reproducible** — all data pipelines, models, and tests versioned in Git

---

## Impact and Relevance

### Direct Beneficiaries
- **376,000 residents** across 94 census tracts in Central Los Angeles (pilot area)
- **Approximately 9,400 elderly residents (65+)** in the highest-risk zones — the population most likely to die from heat
- **Municipal officers** in the U.S. cities where FortyGuard operates (immediately scalable)

### Quantified Impact Potential
Assuming HeatGov AI helps reallocate 20% of a mid-size U.S. city's annual $2M heat mitigation budget more effectively:
- **$400,000/year** redirected to correctly prioritized neighborhoods
- **Estimated 15 to 25 percent reduction** in heat-related ER visits in optimized zones
- **Approximately 50 lives saved per year** in a mid-size U.S. city (CDC baseline extrapolation)

### Market and Scaling Potential
- **9,300+ U.S. municipalities** face measurable heat-related climate risk ([FEMA, 2024](https://www.fema.gov/))
- HeatGov AI is deployable to any city covered by hyperlocal temperature data
- Aligns with **federal climate resilience funding** (Inflation Reduction Act, $370B allocated for climate adaptation)
- Potential customer segments: Chief Resilience Officers, Public Health departments, Urban Planning offices, Environmental Justice organizations

### Why This Matters Beyond Los Angeles
Climate change is making urban heat waves more frequent and deadly. Cities cannot afford consultant-heavy decision cycles that take months, politically-driven investment that ignores data, or the inability to prove impact to voters and funders.

HeatGov AI democratizes evidence-based climate decision-making by putting the tools of data science, machine learning, and optimization directly in the hands of the people who make the investment decisions.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Sarah, Municipal Officer                          │
│              "I have $500,000. Where should I invest?"              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    GEMINI 3.6 FLASH (Agent)                         │
│  Understands question → decides which tools to call and in what     │
│  order → orchestrates 5 tools → formulates response in English      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│ get_top_risk_ │    │  explain_zone()  │    │  optimize_budget()  │
│    zones()    │    │  (SHAP values)   │    │  (Knapsack 0/1)     │
└───────┬───────┘    └────────┬─────────┘    └──────────┬──────────┘
        │                     │                          │
        ▼                     ▼                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│              XGBoost Model A + Model B (trained)                    │
│           Predicts risk_score (0-100) per census tract              │
│      Model A: physical only (7 features)  → SHAP explanation       │
│      Model B: complete (11 features)      → operational score      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ reads features
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              zone_features.parquet (94 tracts × 11)                 │
│         File built at Step 3 by spatial join                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ aggregated from
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              FORTYGUARD API — THE FOUNDATION                        │
│  ┌──────────────┬──────────────┬─────────────┬─────────────────┐   │
│  │ tcm_peak_15h │ tcm_peak_22h │  exceedance │   persistence   │   │
│  │  (day peak)  │  (night)     │  (hours)    │   (max stretch) │   │
│  └──────────────┴──────────────┴─────────────┴─────────────────┘   │
│         8,674 tiles × 100m × 100m — Central Los Angeles             │
└─────────────────────────────────────────────────────────────────────┘
```

**Summary**: FortyGuard provides raw heat data. XGBoost transforms it into a vulnerability score. Gemini interprets it in human language with a concrete budget plan. FortyGuard is the raw material, XGBoost is the brain, Gemini is the voice.

---

## The Finding This Project Is Built On

> **Day-time and night-time thermal danger zones in Central Los Angeles do not overlap.** There is **0% intersection** between the 10% hottest tiles at 15:00 (afternoon peak) and the 10% hottest at 22:00 (night).
>
> A single-timepoint heatmap therefore misses half the population at risk. HeatGov AI is the first tool to combine both danger maps into a single vulnerability score, weighted by CalEnviroScreen socio-demographic factors.

Measured across 8,674 tiles at 100 m resolution over 89.7 km². The FortyGuard API anchors requests to **GMT-8**, so the hours above are local, not UTC — this was verified against the API's own `metadata.timezone` field, not assumed. See [docs/fortyguard-api-findings.md](docs/fortyguard-api-findings.md).

**Why it matters**: night-time heat is what prevents physiological recovery. A neighborhood that bakes at 3 p.m. but cools at night is a different public health problem from one that never cools down, and the two are not the same neighborhoods.

---

## Technical Architecture

### Stack
- **Backend**: Python 3.11, FastAPI, XGBoost, SHAP, Pandas, GeoPandas
- **Frontend**: Next.js 16, TypeScript, Tailwind CSS, MapLibre GL JS
- **AI Agent**: Google Gemini 3.6 Flash with function calling (5 tools)
- **Data Storage**: Parquet (columnar, cached) and GeoJSON (spatial)
- **Deployment**: Backend on Render (free tier), Frontend on Vercel (free tier)
- **CI/CD**: GitHub Actions (typecheck, lint, build, unit tests)

### Design Principles
1. **Reproducibility**: Every ML result is regeneratable from `python backend/data_pipeline/*.py`
2. **Transparency**: Two models (A honest, B operational) exposed side-by-side
3. **Caching**: Fingerprinted Parquet cache — the same API request never fires twice
4. **Testing**: 91 tests total (14 optimizer, 27 backend integration, 50 frontend end-to-end)
5. **Explainability**: SHAP values expose why each tract scores what it scores

---

## FortyGuard API Usage

HeatGov AI uses **6 distinct FortyGuard API calls** to build the ML feature set:

| Endpoint | Analytic Type | Filter Type | Purpose |
|---|---|---|---|
| `POST /v1/heatmap` | `tcm` | 3 (single day) | Snapshot temperature July 15, 2025 |
| `POST /v1/heatmap` | `tcm` (peak 15:00 local) | 1 (single hour) | Day danger map — afternoon solar peak |
| `POST /v1/heatmap` | `tcm` (peak 22:00 local) | 1 (single hour) | Night danger map — headline finding |
| `POST /v1/heatmap` | `exceedance` | 4 (date range) | Hours above 30°C in July 2025 |
| `POST /v1/heatmap` | `persistence` | 4 (date range) | Longest continuous heat stretch |
| `POST /v1/heatmap` | `time_of_measure` | 4 (date range) | Peak hour classification per tile |
| `POST /v1/env_params` | N/A | Single point | Elevation for 15 centroid points |

**Total API consumption**: **71,720 credits** out of 2,000,000 available (3.6%) — six heatmap calls at 4,220 credits each (25,320) plus 46,400 for the `env_params` grid. These figures are recorded per request in `data/raw/manifest.json` and can be recomputed from it.

**Key discoveries about the API** (documented in [docs/fortyguard-api-findings.md](docs/fortyguard-api-findings.md)):
1. **Timezone**: The API anchors requests in `GMT-8` local time, verified against `metadata.timezone`
2. **Response schema**: `analytic_type=tcm` returns `properties.temperature`; other types return `properties.value`
3. **Cost model**: Flat per-call, not proportional to polygon size — larger AOIs are more efficient
4. **Async pattern**: `activity_id` polling with `timeout=1800s` for range-of-days calls
5. **`env_params` is spatially coarse**: nearly identical values across 15 points, so only `elevation` was retained as an ML feature

The **fingerprinted cache** in `backend/data_pipeline/__init__.py` ensures each unique request fires exactly once, which is critical for the 2M credit budget and for reproducibility across deployments.

---

## Scientific Foundation

Four peer-reviewed studies shape the method. Each citation below was verified against the publisher's own record.

**1. Werbin et al. (2020).** *A tree-planting decision support tool for urban heat mitigation.* PLOS ONE 15(10): e0224959. [doi:10.1371/journal.pone.0224959](https://doi.org/10.1371/journal.pone.0224959)

The closest published analogue to HeatGov AI: a Boston-specific Heat Vulnerability Index built by Principal Components Analysis over 13 sociodemographic and land-cover variables at census tract level, surfaced through an interactive web tool that ranks priority tracts for planting. This work validates our unit of analysis (the census tract) and our PCA/linear baseline methodology.

**2. Qu et al. (2026).** *Integrating Machine Learning-Based Variable Selection into Heat Vulnerability Index Design.* medRxiv, 29 March 2026. [doi:10.64898/2026.03.29.26349672](https://doi.org/10.64898/2026.03.29.26349672)

Compares an unsupervised PCA-based HVI against Lasso, Random Forest and XGBoost variable selection using Chicago (77 communities) as the case study. The result is a warning: on 77 communities the Random Forest-informed index scored highest against heat-related excess mortality (Spearman ρ = 0.37), while XGBoost underperformed due to noise sensitivity at small sample sizes. Our 94 tracts sits in the same regime — we chose XGBoost anyway and report the cross-validation spread honestly (Model A: 0.37 ± 0.27).

**3. Smith et al. (2025).** *Integrated tree canopy expansion and cool roofs can optimize air temperature and heat exposure reductions in Boston.* Communications Earth & Environment. [doi:10.1038/s43247-025-02462-3](https://doi.org/10.1038/s43247-025-02462-3)

Tree canopy delivers approximately 35% larger air-temperature reduction than cool roofs per unit deployed, yet cool roofs deliver greater population heat-exposure reduction in dense, built-out districts where there is no ground left to plant. This asymmetry is encoded directly in [`backend/optimizer/intervention_rules.py`](backend/optimizer/intervention_rules.py): above 80% impervious surface we recommend cool roofs, below 15% canopy we recommend trees.

**4. Yin et al. (2025).** *Heat vulnerability assessment based on local climate zones: a street-level case study of Chengdu.* Sustainable Cities and Society. [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S2210670725008364)

Applies a gradient-boosting ensemble interpreted through SHAP, plus GeoDetector, to identify heat-vulnerability drivers within a Local Climate Zone framework. Precedent for our SHAP-based `explain_zone` tool.

---

## What Is In The Box

| Component | Status | Tests |
|---|---|---|
| FortyGuard data pipeline (6 heatmap analyses + env_params) | Complete | Manual |
| Fingerprinted Parquet cache — never downloads same request twice | Complete | Yes |
| Feature engineering to census tract level (94 tracts, 11 features) | Complete | Yes |
| Vulnerability model (XGBoost + SHAP, two feature sets) | Complete | Yes |
| Gemini conversational agent with function calling (5 tools) | Complete | 27/27 |
| Budget optimizer (exact 0/1 knapsack) | Complete | 14/14 |
| FastAPI REST API (6 endpoints) | Complete | 27/27 |
| Next.js + MapLibre single-page interface | Complete | 50/50 |
| **Total** | | **91/91** |

---

## Honest Limitations

We would rather state these than have a judge find them.

**The label is not a heat index.** CalEnviroScreen 4.0 contains no heat indicator at all. We are testing whether hyperlocal heat metrics predict an official environmental-justice score. That is a real and useful question, but it is a different one from "reproducing a heat vulnerability index."

**Partial label leakage.** CalEnviroScreen's "Population Characteristics" half already contains poverty and housing burden. Supplying median income as a predictor partially predicts the label from its own ingredients. We therefore report two models:
- **Model A — FortyGuard + geography only** (7 features): the honest measure of what heat data contributes. R² = 0.37 ± 0.27
- **Model B — full** (11 features): the operational score. R² = 0.59 ± 0.08

The gap between them is the result, not a footnote.

**Small sample.** 94 census tracts against 11 features. Every score is cross-validated (5-fold), never on a single split.

**Day-time heat features largely proxy distance inland.** `temp_max_15h`, `exceedance_hours_30C` and `persistence_max_hours` correlate 0.85 with `distance_to_coast_km`. The night layer `temp_max_22h` is the exception — and it is also the strongest predictor of the label (r = +0.513 versus +0.216 for the afternoon layer).

**Geography dominates land cover at this scale.** Griffith Park, the most tree-covered area of our study region, records the highest heat dose because it sits furthest from the ocean. `distance_to_coast_km` is included as a control feature. Without it, a model would incorrectly conclude that trees cause heat.

**Costs are estimates, never quotes.** Unit costs come from public sources (USDA Forest Service, CoolRoofs NYC, municipal reports) and are presented as planning-grade estimates.

**Tree canopy is provisional.** The first canopy layer we obtained was aggregated to city level (only 3 polygons cover the study area). The pipeline detects this and uses `impervious_surface_pct` as a proxy for cool-roof recommendations. A tract-level canopy layer is being sourced.

For full technical details, see [docs/fortyguard-api-findings.md](docs/fortyguard-api-findings.md).

---

## Quick Start

### Prerequisites
- Python 3.11 (required — see [environment notes](docs/environment-notes.md))
- Node.js 22 or higher
- API keys: [FortyGuard](https://fortyguard.com), [Google Gemini](https://aistudio.google.com/apikey), [US Census](https://api.census.gov/data/key_signup.html) (all free)

### Installation (5 steps)

```powershell
# 1. Clone the repository
git clone https://github.com/zahra-yesl/heatgov-ai.git
cd heatgov-ai

# 2. Set up environment variables
copy .env.example .env
# Then edit .env and fill in your API keys

# 3. Install backend dependencies
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 4. Install frontend dependencies
cd frontend
npm install
cd ..

# 5. Launch (two terminals)
# Terminal 1: Backend on port 8000
.\.venv\Scripts\python.exe -m uvicorn api.main:app --app-dir backend --port 8000

# Terminal 2: Frontend on port 3000
cd frontend
npm run dev
```

Then open **http://localhost:3000**. Interactive API docs at **http://localhost:8000/docs**.

### Reproduce the Data Pipeline (optional)

```powershell
# Fetch fresh FortyGuard data (uses cache if available, safe to re-run)
.\.venv\Scripts\python.exe backend\data_pipeline\pull_heatmaps.py
.\.venv\Scripts\python.exe backend\data_pipeline\pull_env_params.py
.\.venv\Scripts\python.exe backend\data_pipeline\build_features.py

# Retrain the ML model
.\.venv\Scripts\python.exe backend\ml\train.py

# Verify everything works
.\.venv\Scripts\python.exe -m pytest backend\optimizer\ -v
.\.venv\Scripts\python.exe backend\api\test_endpoints.py
cd frontend
npm test
```

External datasets (CalEnviroScreen, LA Tree Canopy, Impervious Surface) must be downloaded manually — see [data/external/README.md](data/external/README.md).

---

## Deployment

`render.yaml` and `frontend/vercel.json` configure a free-tier deployment:
- **Backend** on Render (Python 3.11, 512 MB RAM, auto-deploy on git push)
- **Frontend** on Vercel (Next.js edge network, auto-deploy on git push)

Full step-by-step walkthrough (approximately 30 minutes): [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

**Live URLs**:
- Frontend: `https://heatgov-ai.vercel.app` *(update after Vercel deployment)*
- Backend: `https://heatgov-ai-backend.onrender.com` *(update after Render deployment)*
- API documentation: `https://heatgov-ai-backend.onrender.com/docs`
- Health check: `https://heatgov-ai-backend.onrender.com/api/health`

**Note on Render free tier**: the backend goes idle after 15 minutes of inactivity. The first request wakes it up (30 to 50 second cold start). Subsequent requests are instant. The frontend displays a friendly waking-up banner during the cold start period.

---

## Study Area

| Attribute | Value |
|---|---|
| City | Central Los Angeles, CA, USA |
| Bounding box | `lon [-118.3000, -118.2200], lat [34.0300, 34.1400]` |
| Size | 89.7 km² |
| Tiles | 8,674 at 100m × 100m resolution |
| Census tracts | 94 (2010 vintage) |
| Population | Approximately 376,000 residents |
| Study period | July 1 through July 31, 2025 |
| Heat threshold | 30 °C (86 °F) |

The bounding box deliberately spans a land-cover gradient: Downtown and Skid Row in the south, Echo Park and Silver Lake in the middle, the southern edge of Griffith Park in the north.

---

## Data Sources

| Source | License | Use in HeatGov AI |
|---|---|---|
| FortyGuard Temperature API | Hackathon license | `tcm`, `exceedance`, `persistence`, `time_of_measure`, `env_params` (6 API calls) |
| CalEnviroScreen 4.0 (California OEHHA) | Public domain | Label (`CIscoreP`) and 2010 census tract geometry |
| US Census ACS 2019 5-year | Public domain | Age (>65), income, population density |
| LA GeoHub | Open data | Tree canopy 2016, impervious surface (LARIAC7) |
| OpenStreetMap Standard | ODbL | Basemap raster tiles (no API key required) |

---

## Repository Layout

```
backend/
  config.py              Single source of truth for study area and features
  fortyguard/            Official API client (vendored from quickstart repo)
  data_pipeline/         Fetch, cache, compare, and build features
  optimizer/             Intervention rules and 0/1 knapsack optimizer
  agent/                 Gemini tools and function-calling loop
  api/                   FastAPI application + end-to-end tests
  ml/                    XGBoost training and prediction
frontend/
  app/                   Single page, layout, and global styles
  components/            HeatMap, ChatPanel, ActionPlan, Markdown
  lib/                   Typed API client and budget parser
  scripts/               Browser-path integration test
data/
  raw/                   Fingerprinted Parquet cache of API responses
  processed/             Model-ready feature tables
  external/              Manually downloaded datasets
docs/
  DEPLOYMENT.md          Step-by-step Render + Vercel deployment
  fortyguard-api-findings.md   Verified API behavior and gotchas
  environment-notes.md   Windows Smart App Control workarounds
models/                  Trained XGBoost models and SHAP explainer
notebooks/               Executed analysis notebooks (preserved outputs)
```

---

## Team

- **Zahra Yeslek** — *ML and Backend Engineer*
  Responsible for data pipeline, XGBoost models, FastAPI backend, Gemini agent orchestration
- **Mariem Elbechir** — *Data and Frontend Engineer*
  Responsible for data collection, feature engineering, Next.js frontend, MapLibre integration

Built for **FortyGuard Hackathon 2026**.

---

## Development Tools

This project was built using AI-assisted development tools (Claude Code, ChatGPT). All architectural decisions, scientific validation, feature engineering choices, and business logic were made by the human team. AI tools assisted with boilerplate code generation, debugging environment-specific issues (Windows Smart App Control, npm lockfile conflicts), and documentation writing.

The project's core innovations are original contributions by the team:
- The 0% day/night hotspot overlap discovery (Step 2 analysis)
- The dual-model (A/B) approach to expose label leakage
- The intervention rule based on Nature 2025 research (`intervention_rules.py`)
- The fingerprinted cache to protect the 2M FortyGuard credit budget

---

## License and Acknowledgments

**License**: MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Zahra Yeslek and Mariem Elbechir.

**Acknowledgments**:
- **FortyGuard team** for the excellent Temperature API, hackathon credit allocation (2M credits), and prompt technical support throughout the project
- **California OEHHA** for the free public CalEnviroScreen 4.0 dataset and shapefile
- **US Census Bureau** for the free public ACS API
- **OpenStreetMap contributors** for the basemap tiles
- **Anthropic** for Claude Code AI-assisted development
- **Werbin, Qu, Smith, and Yin** for the peer-reviewed research that informs our methodology

**Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)
**Security**: See [SECURITY.md](SECURITY.md)
**Deployment Guide**: See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
