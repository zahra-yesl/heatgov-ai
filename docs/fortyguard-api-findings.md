# FortyGuard API - verified findings

Everything below was observed on real calls, not read from documentation.
Sources: `notebooks/00_test_api.ipynb` (Step 1) and `backend/data_pipeline/`
(Step 2). Last updated 2026-08-26.

## Account and credit cost

| Field | Value |
|---|---|
| Plan | Hackathon |
| Billing period | Aug 19, 2026 - Sep 23, 2026 |
| Key expiry | 2026-09-23 |
| Total credits | 2,000,000 |

**Credit cost is flat per call, not per tile.**

| Call | Tiles / points | Credits |
|---|---|---|
| `create_heatmap`, Downtown only (16.4 km2) | 1,607 | 4,220 |
| `create_heatmap`, Central LA (89.7 km2) | 8,674 | 4,220 |
| `environmental_parameters`, one point | 1 | ~3,100 |

A 5.4x larger area costs exactly the same. Always request the largest polygon
that is actually needed. Conversely, the *point* endpoint is expensive relative
to what it returns: 15 points cost 46,400 credits, eleven times one heatmap.

Consumed through Step 2: 96,240 of 2,000,000.

## Study area

```
lon [-118.3000, -118.2200]   lat [34.0300, 34.1400]
89.7 km2, 8,674 tiles at 100 m granularity, tile size ~100 m x 102 m
```

Accepted in a single request with no area-cap error, so no tiling is required.

## `start_time` is LOCAL time, not UTC

The `env_params` response settles this definitively. Requesting
`start_time="15:00"` returns:

```json
"metadata": {
  "timezone": "GMT-8",
  "timezone_offset_hours": -8,
  "time_range": { "start": "2025-07-15T15:00:00-08:00" }
}
```

The API anchors to **GMT-8 and ignores daylight saving**, so `"15:00"` means
15:00 PST (16:00 on a July wall clock in Los Angeles).

Corroborating evidence from the heatmaps:

| Request | Mean tile temperature |
|---|---|
| `start_time="15:00"` | 28.85 C |
| `start_time="22:00"` | 18.80 C |
| daily `max_temperature`, same day | 28.98 C |

The 15:00 snapshot matches the daily maximum, so 15:00 is the thermal peak. Had
the value been UTC it would have been 08:00 local and could not be the peak.
This also explains why `time_of_measure` reports a modal peak hour of 16.

## Response shapes

### `create_heatmap`

```
{ "activity_id": "...", "result": { "map_data": {GeoJSON}, "stats_data": {...} } }
```

`tcm` tile properties (there is **no** `temperature` key - the quickstart sample
notebook is misleading):

| Property | Example |
|---|---|
| `tile_id` | `0` |
| `average_temperature` | `22.3533` |
| `min_temperature` | `17.3705` |
| `max_temperature` | `29.141` |

For a **single-hour** request (`filter_type=1`) the three fields are identical,
since there is only one instant to aggregate.

`exceedance`, `persistence` and `time_of_measure` tiles carry a single
`properties.value` instead, in hours.

### `environmental_parameters`

Requires a `temperature` argument (the ambient temperature at that point), which
the pipeline reads from the nearest tile of the cached peak-hour heatmap.

Returns a nested object flattened by the pipeline into 63 columns:
`metadata.*`, `locations[0].elevation`, `locations[0].parameters.<name>`
(each with the value repeated), and `locations[0].solar_irradiance.clear_sky.{ghi,dni,dhi}`.

## UNITS: tiles are in CELSIUS, not Fahrenheit

`FortyGuardClient.create_heatmap` documents `tcm` tiles as "in degrees
Fahrenheit". **The observed data contradicts this.** Mean tile temperature on a
July day is 22.05: as Celsius that is 71.7 F, normal for Los Angeles in July; as
Fahrenheit it would be -5.5 C, impossible. The `threshold` argument is Celsius
too, so no unit conversion is needed anywhere in the pipeline.

## Layer comparison (8,674 tiles, `compare_layers.py`)

### Discrimination

| Layer | min | mean | max | spread | max/min |
|---|---|---|---|---|---|
| tcm 24 h average (C) | 20.24 | 21.77 | 22.56 | 2.31 | n/a |
| tcm 24 h daily max (C) | 26.27 | 28.98 | 30.89 | 4.62 | n/a |
| tcm 15:00 snapshot (C) | 26.05 | 28.85 | 30.91 | 4.86 | n/a |
| tcm 22:00 snapshot (C) | 17.31 | 18.80 | 19.81 | 2.50 | n/a |
| exceedance (hours > 30 C) | 10.56 | 49.18 | 98.26 | 87.71 | **9.31x** |
| persistence (longest run, h) | 1.61 | 6.49 | 11.23 | 9.62 | **6.96x** |
| time_of_measure (peak hour) | 2 | 13.52 | 16 | 14 | n/a |

A max/min ratio is reported only for hours, which sit on a true ratio scale.
Degrees Celsius have an arbitrary zero, so a Celsius ratio would be meaningless.

### Top-decile overlap: does a temperature ranking find the worst-exposed tiles?

| Temperature baseline | vs exceedance | vs persistence |
|---|---|---|
| tcm 24 h average | 35% | 61% |
| tcm 24 h daily max | 73% | 32% |
| tcm 15:00 snapshot | 73% | 32% |
| tcm 22:00 snapshot | **0%** | 18% |

Read honestly: the gap between a temperature ranking and a duration ranking is
real but its size depends entirely on which temperature metric is used. Against
a 24 h average, 65% of the worst-dose tiles are missed; against a daily maximum,
27%. Claims in the pitch must name the baseline.

### The strongest finding: day and night rank differently

Top-decile overlap between the hottest tiles at 15:00 and the hottest at 22:00
is **0%**. The neighbourhoods that bake in the afternoon are not the ones that
stay hot at night, and night heat is what prevents physiological recovery. The
night layer is the least redundant temperature layer we have (Spearman 0.57
against the afternoon snapshot, versus 0.99 between the afternoon snapshot and
the daily maximum).

## Cautions for feature engineering

**1. `env_params` is nearly constant across the study area.** Measured spread
over the 15 grid points:

| Parameter | Spread | Usable as a feature? |
|---|---|---|
| `air_quality:idx`, pm2.5, pm10, no2, o3, so2 | **0.00** | No - identical everywhere |
| `relative_humidity_percent` | 0.20 pp | No |
| `solar_irradiance.clear_sky.ghi` | 2.98 W/m2 | No |
| `wet_bulb_temperature_celsius` | 0.10 C | No |
| `apparent_temperature_celsius` | 0.20 C | No |
| `heat_index_celsius` | 4.30 C | Redundant - a function of the temperature we supplied |
| `co2_ppm` | 5.0 | Marginal |
| `methane_ppb` | 26.5 | Marginal |
| **`elevation`** | **161 m** | **Yes - the only strongly varying field** |

Three of the four env_params features planned in the specification
(`humidity_afternoon`, `aqi_max`, `solar_irradiance_peak`) carry no spatial
signal at this scale: they come from a coarse regional model, not from
hyperlocal sensing. `heat_index_peak` is derived from the ambient temperature we
pass in, so it adds nothing independent. `elevation`, which the specification
does not list, is the one genuinely informative field.

**2. `time_of_measure` has only three distinct values**, so it behaves as a
category, not a continuous variable:

| Peak hour | Tiles | Where |
|---|---|---|
| 16 | 7,087 | everywhere |
| 2 | 882 | far south, east of -118.268 |
| 3 | 705 | far north, east of -118.268 |

The 02:00-03:00 tiles are spatially coherent rather than random noise, but a
2 a.m. thermal peak in July is physically odd and should be treated with
suspicion until corroborated.

**3. A confounder dominates the north-south gradient.** Mean values by latitude
band:

| Band | 15:00 (C) | 22:00 (C) | exceedance (h) | persistence (h) |
|---|---|---|---|---|
| S (Downtown) | 28.76 | 19.40 | 43.65 | 5.79 |
| S-mid | 29.00 | 19.14 | 48.29 | 6.45 |
| middle | 29.01 | 18.65 | 50.20 | 6.45 |
| N-mid | 28.62 | 18.32 | 45.77 | 6.32 |
| N (Griffith) | 28.87 | 18.49 | **57.82** | **7.44** |

The northern band - the one containing Griffith Park and its tree canopy - has
the **highest** heat dose, not the lowest. The reason is distance from the
ocean: at this scale Los Angeles is governed by a coastal-to-inland gradient
that outweighs the concrete-versus-canopy contrast.

Consequence for Step 3: a model given tree canopy without a distance-to-coast
control will conclude that trees cause heat. A proxy for maritime influence
(distance to the coastline, or simply longitude combined with elevation) must be
included.

## Reliability

The heatmap endpoint has been reliable: 7 for 7 calls, each completing in under
a minute of polling.

The `env_params` point endpoint is not. Across two runs it produced a task stuck
in `processing` past a 1,800 s budget, and two `requests.ConnectionError`
failures from the server closing the connection. The pipeline therefore uses a
tight 240 s per-point timeout, two retries with backoff, and writes every
successful response to disk immediately so a crash never discards work already
paid for.
