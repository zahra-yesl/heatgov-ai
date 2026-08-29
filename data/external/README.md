# External datasets — manual download instructions

These files are too large or too licence-encumbered to commit, so they are
git-ignored and must be downloaded by hand. `build_features.py` refuses to run
until they are present, and will name the missing file.

Status: CalEnviroScreen and impervious surface are in place and working.
Only the tract-level tree canopy layer is still missing (section 2).

---

## 1. CalEnviroScreen 4.0 — REQUIRED (label + tract geometry)

**Page:** https://oehha.ca.gov/calenviroscreen/report/calenviroscreen-40

Download the **shapefile / geodatabase** ("CalEnviroScreen 4.0 Shapefile" or
"CalEnviroScreen 4.0 Data Layer"), not just the spreadsheet.

**Save to:** `data/external/calenviroscreen40/`
(unzip the whole folder — keep `.shp`, `.shx`, `.dbf`, `.prj` together; a `.shp`
alone is unreadable)

### Why the shapefile and not the Excel file

The shapefile carries **geometry and scores in one consistent file**. That
matters more than convenience here:

> CalEnviroScreen 4.0 is built on **2010** census tracts. Los Angeles redrew its
> tract boundaries for the 2020 census. Joining CES 4.0 scores onto a 2020 tract
> layer would mismatch a subset of tracts **silently** — no error, just wrong
> numbers. Using the CES shapefile's own geometry removes the join entirely.

For the same reason the pipeline uses **ACS 2019 5-year** data. Verified against
the live API: ACS 2018/2019 return 2,346 LA County tracts (2010 geography) while
ACS 2020/2021 return 2,498 (2020 geography).

### Columns the pipeline reads

| Shapefile field | Excel equivalent | Use |
|---|---|---|
| `Tract` | `Census Tract` | Join key (FIPS, 11 digits) |
| `CIscoreP` | `CES 4.0 Percentile` | **The label `y`** |
| `CIscore` | `CES 4.0 Score` | Reference |
| `TotPop19` | `Total Population` | Density denominator cross-check |
| `PolBurdP` | `Pollution Burden Pctl` | Label-leakage diagnostic |
| `PopCharP` | `Population Characteristics Pctl` | Label-leakage diagnostic |

The last two are not model features. They exist so we can quantify how much of
the label is already explained by its own socio-economic half.

**Optional backup:** also download the Excel results file as
`data/external/calenviroscreen40.xlsx`. The pipeline falls back to it if the
shapefile is unreadable.

> **Note:** CalEnviroScreen 4.0 contains **no heat indicator** — no temperature,
> no heat-wave metric. Its 21 indicators cover air and water pollution, hazardous
> sites, and socio-economic and health burden. We are testing whether hyperlocal
> heat metrics predict an environmental-justice score, not reproducing a heat
> index. This is stated plainly in the project README.

---

## 2. LA Tree Canopy — STILL NEEDED (tract level)

**What was downloaded first does not work.** `Tree_Canopy_Coverage_*.geojson`
contains 210 polygons that are **cities**, not census tracts. Only three of them
touch the study area:

| Polygon | Share of study area | `Tree_PW` |
|---|---|---|
| City of Los Angeles | 94.4% | 4.1 |
| City of Glendale | 5.6% | 6.3 |
| (third, tiny) | <1% | null |

A feature built from that would be 4.1 for almost every tract — no spatial
variance, nothing for a model to learn, exactly the flaw that got the
`env_params` features cut in Step 2. 134 of the 210 polygons have a null value,
and the 1.1–16 range does not look like a canopy percentage.

`build_features.py` detects this automatically and refuses the layer, running
with 11 features instead of 12. The old file can stay where it is.

**What to look for instead:** the tract-level sibling of the impervious file you
already have. Search the LA County open data portal
(https://egis-lacounty.hub.arcgis.com or https://data.lacounty.gov) for:

```
lariac7 tree canopy tract
```

Expect roughly 2,496 polygons with a `CT20` column and a percentage column —
the same shape as `cso_lariac7_impermeable_tract`. Save it into
`data/external/` with `tree` and `canopy` in the file name; the pipeline finds
it by glob and will pick it up on the next run.

---

## 3. LA Impervious Surface — DONE

`cso_lariac7_impermeable_tract_*.geojson` — LARIAC7, already aggregated per
census tract. Exactly the right shape.

| | |
|---|---|
| Polygons | 2,496 (2020 tract geography) |
| Key column | `CT20` |
| Value column | `impermeable_pct` |
| Over the study area | 180 tracts, 26.5% to 96.6%, mean 69.0 |

Note the vintage: this layer is on **2020** tracts while CalEnviroScreen is on
**2010** tracts. The pipeline transfers the percentage onto the CES tracts by
area-weighted intersection. That is legitimate for a covariate; the label is
never moved between vintages.

---

## 4. Census ACS — FREE API KEY NEEDED (no file download)

**The US Census API now rejects keyless requests.** A keyless call returns an
HTML page titled "Missing Key" with HTTP 200 — not an error code, so a naive
script would fail with a confusing JSON parse error. This was verified against
the live API on 2026-08-26.

### Get a key (takes about one minute, free)

1. Go to https://api.census.gov/data/key_signup.html
2. Enter your organisation name and email
3. The key arrives by email immediately
4. Add it to your `.env` at the project root:

```
CENSUS_API_KEY=your_key_here
```

Then tell Claude **"census key added"**.

### What is fetched

| Variable | Table | Feature |
|---|---|---|
| `B01003_001E` | Total population | `pop_density` numerator |
| `S0101_C02_030E` | Percent age 65 and over | `pop_over_65_pct` |
| `S1901_C01_012E` | Median household income | `median_income` |

ACS **2019 5-year**, which is published on 2010 tract geography — the same
vintage CalEnviroScreen 4.0 uses, so the two join cleanly.

The response is cached to `data/external/acs_2019_la_tracts.csv`, so the API is
called once.

### If you would rather not sign up

Download manually from https://data.census.gov: search each table code above,
filter to *All Census Tracts in Los Angeles County, California*, choose the
**2019 ACS 5-Year** vintage, and export CSV. Tell Claude and it will read the
files instead.

**The pipeline never invents demographic values.** If neither the key nor the
files are available it stops and says so. Fabricated income figures in a
submission judged by municipal officials would be a credibility failure, not a
shortcut.

---

## Checklist

```
data/external/
├── calenviroscreen40shpf2021shp/            # DONE  .shp .shx .dbf .prj
├── cso_lariac7_impermeable_tract_*.geojson  # DONE  2,496 tracts
├── Tree_Canopy_Coverage_*.geojson           # city level - pipeline rejects it
├── <lariac7 tree canopy by tract>.geojson   # STILL NEEDED
└── acs_2019_la_tracts.csv                   # DONE  fetched automatically
```

Verify with:

```powershell
.\.venv\Scripts\python.exe -c "import geopandas as gpd; g=gpd.read_file('data/external/calenviroscreen40shpf2021shp/CES4 Final Shapefile.shp'); print(g.shape); print(sorted(g.columns))"
```
