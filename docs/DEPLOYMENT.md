# Deploying HeatGov AI

Two free services, one each:

```
  Browser
     |
     |  https
     v
  Vercel  ------------------->  Render
  Next.js front end             FastAPI + XGBoost + Gemini agent
  (frontend/)                   (backend/)
```

The front end is static-ish and always warm. The backend is a real Python
process and, on the free tier, goes to sleep. Everything below is written so
that a judge who opens the link cold still sees a working product.

Files that make this work, already in the repository:

| File | What it does |
|---|---|
| `render.yaml` | Tells Render how to build and start the API |
| `frontend/vercel.json` | Tells Vercel the front end lives in `frontend/` |
| `backend/requirements-deploy.txt` | Runtime-only dependencies, used if the full install is too heavy |

---

## 0. Before you deploy: the data problem

**Read this first. Skipping it produces a backend that starts, passes its health
check, and then fails every real request.**

Render builds from GitHub. It has no other copy of the project. But the files
the API reads at run time are all git-ignored, because they are generated
output:

| File | Size | Read by |
|---|---|---|
| `models/best_model.pkl` | 114 KB | `/api/predict`, `/api/zones/ranked` |
| `models/shap_explainer.pkl` | 257 KB | `/api/predict` (the SHAP drivers) |
| `models/feature_columns.json` | 1 KB | model input ordering |
| `models/metrics.json` | 3 KB | `/api/health` R2 scores |
| `models/top_features*.json` | 1 KB | agent tools |
| `data/processed/zone_features.parquet` | 25 KB | every ranking and prediction |
| `data/processed/zone_features.geojson` | 130 KB | agent tract lookup |
| `data/raw/fortyguard_tcm_peak_15h.parquet` | 688 KB | `/api/heatmap/tcm_peak_15h` |
| `data/raw/fortyguard_tcm_peak_22h.parquet` | 675 KB | `/api/heatmap/tcm_peak_22h` |
| `data/raw/fortyguard_exceedance.parquet` | 590 KB | `/api/heatmap/exceedance` |
| `data/raw/fortyguard_persistence.parquet` | 581 KB | `/api/heatmap/persistence` |
| `data/raw/fortyguard_time_of_measure.parquet` | 524 KB | agent heatmap summary |

About 3.5 MB in total. That is small enough to commit, and committing it is the
only approach that works on a free tier: Render's persistent disks are a paid
feature, and rebuilding the models during the build would need the FortyGuard
and Census APIs plus the hand-downloaded CalEnviroScreen shapefile.

**This is a decision, not a mechanical step.** Committing these files publishes
FortyGuard-derived temperature data for Central Los Angeles in a public
repository. Check that against the hackathon terms and the FortyGuard API terms
before running the commands below.

If you decide to go ahead, add these lines at the end of `.gitignore`:

```gitignore
# Deployment: the API cannot rebuild these on Render, so the artifacts it reads
# at run time are committed as an exception to the rules above. About 3.5 MB.
!models/best_model.pkl
!models/shap_explainer.pkl
!models/feature_columns.json
!models/metrics.json
!models/top_features.json
!models/top_features_model_a.json
!data/processed/zone_features.parquet
!data/processed/zone_features.geojson
!data/raw/fortyguard_tcm_peak_15h.parquet
!data/raw/fortyguard_tcm_peak_22h.parquet
!data/raw/fortyguard_exceedance.parquet
!data/raw/fortyguard_persistence.parquet
!data/raw/fortyguard_time_of_measure.parquet
```

Then, from the project root:

```powershell
git add .gitignore
git add -f models/best_model.pkl models/shap_explainer.pkl models/feature_columns.json models/metrics.json models/top_features.json models/top_features_model_a.json
git add -f data/processed/zone_features.parquet data/processed/zone_features.geojson
git add -f data/raw/fortyguard_tcm_peak_15h.parquet data/raw/fortyguard_tcm_peak_22h.parquet data/raw/fortyguard_exceedance.parquet data/raw/fortyguard_persistence.parquet data/raw/fortyguard_time_of_measure.parquet
git commit -m "chore(deploy): commit the model and data artifacts the API reads at run time"
git push
```

Confirm before pushing that nothing larger slipped in:

```powershell
git diff --cached --stat
```

If you decide **not** to publish the data, the deployed backend can still serve
`/api/health` and the Gemini agent's explanatory answers, but the map, the
rankings and the budget plan will return errors. In that case demo from
localhost and treat the deployment as evidence that the project ships.

### Confirm the build is sound before you deploy

A deployment is only as good as the artifacts you just committed, so run the
three suites locally first:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\optimizer\ -v   # 14 unit tests
.\.venv\Scripts\python.exe backend\api\test_endpoints.py     # 27 end-to-end checks
cd frontend; npm test                                        # 50 browser-path checks
```

**91 checks in total.** The last two start real servers and need real keys, and
`npm test` makes one live Gemini call. Budget for that: the free tier allows 20
`generate_content` requests per key per **day**, so two or three full runs
exhaust a single key. `npm run test:no-agent` skips the Gemini call when you
only need to check the HTTP paths.

---

## 1. Backend on Render (free tier)

1. Go to <https://render.com/> and sign up with GitHub.
2. Dashboard, then **New**, then **Web Service**.
3. Connect the `heatgov-ai` repository.
4. Render detects `render.yaml`. Confirm the settings it fills in:
   - Name: `heatgov-ai-backend`
   - Environment: Python
   - Plan: Free
   - Region: Oregon
   - Build command: `pip install -r backend/requirements.txt`
   - Start command: `uvicorn api.main:app --app-dir backend --host 0.0.0.0 --port $PORT`
   - Health check path: `/api/health`
5. **Environment variables.** `render.yaml` declares the names but deliberately
   carries no values for the secrets, so add them by hand in the dashboard:

   | Variable | Value |
   |---|---|
   | `FORTYGUARD_API_KEY` | your FortyGuard key |
   | `GEMINI_API_KEYS` | your Gemini keys, comma-separated, no spaces |
   | `CENSUS_API_KEY` | your Census key |

   `FORTYGUARD_BASE_URL`, `GEMINI_MODEL` and `PYTHON_VERSION` are already set in
   `render.yaml` and need no action.

   Never put a real key in `render.yaml`. It is a committed file.
6. Click **Create Web Service**.
7. The first build takes roughly 8 to 12 minutes. Watch the log; the risky part
   is the dependency install, not the start.
8. Copy the deployed URL, for example `https://heatgov-ai-backend.onrender.com`.
9. Test it:

   ```
   https://YOUR-URL.onrender.com/api/health
   ```

   Expect JSON with `"status": "ok"`. Check `"model_loaded": true` as well. If
   it is `false`, section 0 was skipped.

### If the build fails or the service runs out of memory

`backend/requirements.txt` installs the whole development toolchain, JupyterLab
included, which the running API never imports. The free tier gives 512 MB of
RAM, and that is genuinely tight for pandas, GeoPandas, XGBoost and SHAP loaded
together.

Change the build command in `render.yaml` to the runtime-only list:

```yaml
buildCommand: pip install -r backend/requirements-deploy.txt
```

Same pinned versions, minus JupyterLab, ipykernel, Folium and pytest.

---

## 2. Front end on Vercel (free tier)

1. Go to <https://vercel.com/> and sign up with GitHub.
2. Dashboard, then **Add New**, then **Project**.
3. Import the `heatgov-ai` repository.
4. **Set Root Directory to `frontend`.** This is the step people miss. Without
   it Vercel looks for a Next.js app at the repository root and the build fails.
5. Framework: Next.js, detected automatically.
6. Environment variable:

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | the Render URL from step 8 above |

   For example `https://heatgov-ai-backend.onrender.com`. No trailing slash.

   Next.js inlines `NEXT_PUBLIC_*` variables at **build** time. Changing this
   value later has no effect until you redeploy.
7. Click **Deploy**.
8. Three to five minutes.
9. Vercel returns a URL such as `https://heatgov-ai-xxx.vercel.app`.

---

## 3. Point the backend's CORS at the Vercel URL

The API already accepts any `*.vercel.app` origin by pattern, so a standard
deployment needs no change here. Do this step if you add a custom domain, or if
you want the production URL matched exactly rather than by pattern.

1. Back in the Render dashboard, open the service.
2. **Environment**, then add:

   | Variable | Value |
   |---|---|
   | `ALLOWED_ORIGINS` | `https://heatgov-ai-xxx.vercel.app` |

   Comma-separated for several. No trailing slash: the origin a browser sends
   never has one.
3. Save. Render redeploys automatically, about two minutes.

---

## 4. Test end to end

1. Open the Vercel URL.
2. First load takes 30 to 50 seconds while the backend wakes up. The chat panel
   shows a banner saying so.
3. The map loads with the heatmap tiles and the study-area outline.
4. In the chat, type: `I have $500,000 for Central LA. Where should I invest?`
5. Wait 15 to 25 seconds while Gemini runs its tool calls.
6. The Action Plan tab picks up a red dot.
7. Open it and read the three funded interventions.

If all seven happen, the deployment is good.

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `CORS error` in the browser console | The Vercel origin is not allowed | Add it to `ALLOWED_ORIGINS` on Render (section 3) |
| `Cannot connect`, every request fails | `NEXT_PUBLIC_API_URL` is wrong, or has a trailing slash | Fix it in Vercel and **redeploy**. It is baked in at build time |
| `/api/health` returns 500 | A missing environment variable | Read the Render log; it names the variable |
| `/api/health` is fine but `model_loaded` is `false` | The model files are not in the repository | Section 0 |
| `/api/heatmap/...` returns 404 or 500 | The FortyGuard parquet files are not in the repository | Section 0 |
| `Agent unavailable: ... 429 ... RESOURCE_EXHAUSTED` | Gemini free-tier quota | Add more keys to `GEMINI_API_KEYS`, comma-separated. The agent rotates through them |
| `Agent unavailable: ... 404 ... model` | Google retired the model name | Update `GEMINI_MODEL` on Render |
| The service dies partway through a request | 512 MB exceeded | Switch to `requirements-deploy.txt` (section 1) |
| First request always slow, later ones fast | Normal free-tier behaviour | Nothing to fix; the banner explains it |

### Reading the logs

Render dashboard, service, **Logs**. Python tracebacks appear there in full.
Vercel: project, **Deployments**, pick one, **Build Logs** for build failures
and **Runtime Logs** for anything after.

---

## 6. What the free tier actually gives you

| | Render free | Vercel Hobby |
|---|---|---|
| Sleeps when idle | Yes, after 15 min | No |
| Cold start | 30-50 s | n/a |
| Memory | 512 MB | n/a |
| Build minutes | 500 per month | 6000 per month |
| Custom domain | Yes | Yes |
| Good enough for a live demo | With the cold-start banner, yes | Yes |

The one thing worth knowing before a judged demo: **open the app five minutes
early**. That single request wakes the backend, and everything after it is
fast. A paid Render instance or an external pinger removes the problem, and
neither is necessary if you remember to warm it up.
