# HeatGov AI

![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)
![Tests 87/87](https://img.shields.io/badge/tests-87%2F87-brightgreen)
![License MIT](https://img.shields.io/badge/license-MIT-blue)

**From "where is it hot?" to "here is my $500,000 action plan" — in under two minutes.**

A decision-support platform that turns hyperlocal temperature data into a
budgeted, defensible heat-mitigation plan for a U.S. city. Pilot area: Central
Los Angeles.

FortyGuard Hackathon 2026.

---

## The finding this project is built on

> **Day-time and night-time thermal danger zones in Central Los Angeles do not
> overlap.** There is **0% intersection** between the 10% hottest tiles at 15:00
> (afternoon peak) and the 10% hottest at 22:00 (night).
>
> A single-timepoint heatmap therefore misses half the population at risk.
> HeatGov AI is the first tool to combine both danger maps into a single
> vulnerability score, weighted by CalEnviroScreen socio-demographic factors.

Measured across 8,674 tiles at 100 m resolution over 89.7 km². The FortyGuard
API anchors requests to **GMT-8**, so the hours above are local, not UTC — this
was verified against the API's own `metadata.timezone` field, not assumed. See
[docs/fortyguard-api-findings.md](docs/fortyguard-api-findings.md).

Why it matters: night-time heat is what prevents physiological recovery. A
neighbourhood that bakes at 3 p.m. but cools at night is a different public
health problem from one that never cools down, and the two are not the same
neighbourhoods.

---

## What is in the box

| Component | Status |
|---|---|
| FortyGuard data pipeline (6 heatmap analyses + environmental parameters) | Done |
| Fingerprinted Parquet cache — never downloads the same request twice | Done |
| Feature engineering to census tract level (94 tracts, 11 features) | Done |
| Vulnerability model (XGBoost + SHAP, two feature sets) | Done |
| Gemini conversational agent with function calling (5 tools) | Done |
| Budget optimizer (exact 0/1 knapsack) | Done |
| FastAPI REST API (6 endpoints, 27/27 end-to-end tests) | Done |
| Next.js + MapLibre single-page interface (48/48 end-to-end tests) | Done |

---

## Scientific Foundation

Four peer-reviewed studies shape the method. Each citation below was verified
against the publisher's own record; the attributions we started from were partly
incorrect, and the corrected ones are used throughout the code.

**1. Werbin, Z.R., Heidari, L., Buckley, S., Brochu, P., Butler, L.J.,
Connolly, C., Houttuijn Bloemendaal, L., McCabe, T.D., Miller, T.K., &
Hutyra, L.R. (2020).** *A tree-planting decision support tool for urban heat
mitigation.* PLOS ONE 15(10): e0224959.
[doi:10.1371/journal.pone.0224959](https://doi.org/10.1371/journal.pone.0224959)

The closest published analogue to HeatGov AI: a Boston-specific Heat
Vulnerability Index built by Principal Components Analysis over 13
sociodemographic and land-cover variables at census tract level, surfaced
through an interactive web tool that ranks priority tracts for planting. It
validates both our unit of analysis (the census tract) and our PCA/linear
baseline.

**2. Qu, S., Sillmann, J., Barrett, B.W., Graffy, P.M., Poschlod, B.,
Brunner, L., Mansour, R., von Szombathely, M., Hay-Chapman, F., Horton, T.H.,
Chan, J., Khedkar Rao, S., Woods, K., Kho, A.N., & Horton, D.E. (2026).**
*Integrating Machine Learning-Based Variable Selection into Heat Vulnerability
Index Design.* medRxiv, 29 March 2026.
[doi:10.64898/2026.03.29.26349672](https://doi.org/10.64898/2026.03.29.26349672)

Compares an unsupervised PCA-based HVI against Lasso, Random Forest and XGBoost
variable selection, using Chicago as the case study. **The result is a warning
for us**: on 77 communities the Random Forest-informed index scored highest
against heat-related excess mortality (Spearman ρ = 0.37), while XGBoost
*underperformed* because of its sensitivity to noise at small sample sizes. Our
study area yields **94 tracts** — larger than their 77, but the same regime.

We chose XGBoost anyway, as a project decision rather than a finding handed down
by that paper, and the warning proved well founded: Model A's cross-validated R²
is **0.37 ± 0.27**, with one of five folds coming out *negative*. Model B is
stable at **0.59 ± 0.08**. We report the fold spread rather than a single
headline number precisely because of this.

**3. Smith, I.A., et al. (2025).** *Integrated tree canopy expansion and cool
roofs can optimize air temperature and heat exposure reductions in Boston.*
Communications Earth & Environment.
[doi:10.1038/s43247-025-02462-3](https://doi.org/10.1038/s43247-025-02462-3)

Tree canopy expansion delivers air-temperature reductions about **35% larger**
than cool roofs per unit deployed — yet cool roofs deliver greater *population
heat-exposure* reduction overall, because they can be installed in the dense,
built-out, socially vulnerable districts where there is no ground left to plant.
This asymmetry is encoded directly in
[`backend/optimizer/intervention_rules.py`](backend/optimizer/intervention_rules.py):
above 80% impervious surface we recommend cool roofs, below 15% canopy we
recommend trees.

**4. Yin, H., et al. (2025).** *Heat vulnerability assessment and analysis of
driving mechanisms in a megacity based on local climate zones: a street-level
case study of Chengdu.* Sustainable Cities and Society.
[ScienceDirect S2210670725008364](https://www.sciencedirect.com/science/article/abs/pii/S2210670725008364)

Applies a gradient-boosting ensemble interpreted through SHAP, plus GeoDetector,
to identify heat-vulnerability drivers within a Local Climate Zone framework.
Precedent for our SHAP-based `explain_zone` tool.
*Author attribution taken from a secondary source — the publisher page returns
403 — and should be confirmed before submission.*

---

## Honest limitations

We would rather state these than have a judge find them.

**The label is not a heat index.** CalEnviroScreen 4.0 contains **no heat
indicator at all** — no temperature, no heat waves. We are not reproducing an
official heat vulnerability index. We are testing whether hyperlocal heat
metrics predict an official environmental-justice score. That is a real and
useful question, but it is a different one.

**Partial label leakage.** CalEnviroScreen's "Population Characteristics" half
already contains poverty, unemployment and housing burden. Supplying median
income as a predictor means partly predicting the label from its own
ingredients, which inflates R². We therefore train and report **two models**:

* **Model A — FortyGuard + geography only** (7 features). The honest measure of
  what FortyGuard data alone contributes.
* **Model B — full** (11 features today, 12 once tree canopy lands). The
  operational model.

The gap between them is the result, not a footnote. Measured at Step 3, the best
single correlation with the label is **0.513** for Model A's features versus
**0.806** for Model B's — and that 0.806 is `median_income`, which itself
correlates −0.842 with the label's own socio-economic half. The leakage is not
hypothetical.

**Small sample.** 94 census tracts against 11 features. Every score is reported
under cross-validation, never on a single split. Tracts qualify only if their
centroid falls inside the study area and they contain at least 30 FortyGuard
tiles; we checked that this threshold does not bias the sample (Mann-Whitney
p = 0.62 on the label, kept mean 81.0 vs dropped 82.3). A 50-tile threshold
*would* have biased it, and was rejected for that reason.

**Three tract vintages had to be reconciled.** CalEnviroScreen 4.0 is built on
2010 census tracts (2,343 in Los Angeles County); the LARIAC7 impervious layer
is on 2020 tracts (2,496). We verified against the live Census API that ACS
2018/2019 5-year sit on 2010 geography and ACS 2020/2021 on 2020 geography, so
the pipeline uses **ACS 2019**. Impervious surface, being a covariate rather
than the label, is transferred onto the 2010 tracts by area-weighted
intersection. The label is never transferred across vintages.

**CalEnviroScreen encodes missing data as -999.** 46 of the 2,343 Los Angeles
tracts carry it in `CIscoreP` - the label itself. Left as a number it would have
corrupted training with no visible error. The pipeline converts it to NaN and
drops the affected tracts, reporting the count.

**Tree canopy is not yet included.** The first canopy layer we obtained was
aggregated to *city* level: only three polygons cover the study area, so the
feature would have been near-constant and taught the model nothing. The pipeline
detects this and refuses to use it, running with 11 features instead of 12. A
tract-level layer is being sourced.

**Day-time heat features are largely a proxy for distance inland.** Measured at
tract level: `temp_max_15h`, `exceedance_hours_30C` and `persistence_max_hours`
correlate 0.86-0.89 with each other and 0.85 with `distance_to_coast_km`. The
night layer `temp_max_22h` is the exception, and it is also the strongest
FortyGuard predictor of the label (r = +0.513, versus +0.216 for the afternoon
layer). That is the headline finding reproduced at tract level: night heat is a
different, and more informative, signal than afternoon heat.

**Geography dominates land cover at this scale.** Step 2 found that the northern
band of the study area — Griffith Park, the *most* tree-covered — records the
**highest** heat dose, because it sits furthest from the ocean. Distance to the
coast is therefore included as an explicit control feature. Without it a model
would conclude that trees cause heat.

**Costs are estimates, never quotes.** Unit costs come from public sources
(USDA Forest Service, CoolRoofs NYC, municipal reports) and are presented as
planning-grade estimates.

---

## Quick start

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
copy .env.example .env      # then fill in FORTYGUARD_API_KEY and GEMINI_API_KEY
.\.venv\Scripts\python.exe backend\data_pipeline\pull_heatmaps.py
.\.venv\Scripts\python.exe backend\data_pipeline\pull_env_params.py
.\.venv\Scripts\python.exe backend\data_pipeline\compare_layers.py
.\.venv\Scripts\python.exe -m pytest backend\optimizer\ -v
```

Python 3.11 is required — see [docs/environment-notes.md](docs/environment-notes.md)
for the Windows Smart App Control constraint that pins several package versions.

External datasets must be downloaded manually; see
[data/external/README.md](data/external/README.md).

### Running the app

Two terminals. The backend serves data, the frontend serves the page.

```powershell
# Terminal 1 - API on port 8000
.\.venv\Scripts\python.exe -m uvicorn api.main:app --app-dir backend --port 8000

# Terminal 2 - interface on port 3000
cd frontend
npm install       # first time only
npm run dev
```

Then open <http://localhost:3000>. Interactive API docs live at
<http://localhost:8000/docs>.

To verify both halves without a browser:

```powershell
.\.venv\Scripts\python.exe backend\api\test_endpoints.py   # 27 checks, real uvicorn
cd frontend; npm test                                       # 48 checks, real HTTP + Gemini
```

---

## Study area

| | |
|---|---|
| Area | Central Los Angeles, CA |
| Bounding box | lon [-118.3000, -118.2200], lat [34.0300, 34.1400] |
| Size | 89.7 km², 8,674 tiles at 100 m |
| Period | 1–31 July 2025 |
| Heat threshold | 30 °C |

The box deliberately spans a land-cover gradient: Downtown and Skid Row in the
south, Echo Park and Silver Lake in the middle, the southern edge of Griffith
Park in the north.

---

## Data sources

| Source | Use |
|---|---|
| FortyGuard Temperature API | `tcm`, `exceedance`, `persistence`, `time_of_measure`, `env_params` |
| CalEnviroScreen 4.0 (OEHHA) | Label (`CIscoreP`) and 2010-vintage tract geometry |
| US Census ACS 2019 5-year | Age, income, population density |
| LA GeoHub | Tree canopy 2016, impervious surface |
| OpenStreetMap Standard | Basemap raster tiles (no API key required) |

---

## Repository layout

```
backend/
  config.py              single source of truth for the study area and features
  fortyguard/            official API client (vendored from the quickstart repo)
  data_pipeline/         fetch, cache, compare, and build features
  optimizer/             intervention rules and budget optimization
  agent/                 Gemini tools and the function-calling loop
  api/                   FastAPI application and its end-to-end test
  ml/                    training and prediction
frontend/
  app/                   the single page, its layout and global styles
  components/            HeatMap, ChatPanel, ActionPlan, Markdown
  lib/                   typed API client and the budget parser
  scripts/               browser-path integration test
data/
  raw/                   fingerprinted Parquet cache of API responses
  processed/             model-ready tables
  external/              manually downloaded datasets
docs/                    verified API findings and environment notes
notebooks/               executed, output-preserving analysis notebooks
```

---

## Team

- **Zahra Yeslek** — ML & Backend Engineer
  Responsible for data pipeline, XGBoost models, FastAPI backend, Gemini agent
- **Mariem Elbechir** — Data & Frontend Engineer
  Responsible for data collection, feature engineering, Next.js frontend, MapLibre integration

Built for FortyGuard Hackathon 2026.

---

## License

MIT — see [LICENSE](LICENSE).

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md) &middot; API keys and disclosure: [SECURITY.md](SECURITY.md)
