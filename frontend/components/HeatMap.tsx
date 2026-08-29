"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { GeoJSONSource, Map as MapLibreMap, Marker, Popup } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { LayerIcon } from "@/components/icons";
import {
  LAYERS,
  type HeatmapMetadata,
  type LayerId,
  type PredictResponse,
  type Zone,
  getHeatmap,
  getRankedZones,
  predictTract,
} from "@/lib/api";

const CENTER: [number, number] = [-118.26, 34.085];
const ZOOM = 12;

const TILE_SOURCE = "fortyguard-tiles";
const TILE_LAYER = "fortyguard-tiles-fill";
const FILL_OPACITY = 0.62;
const FADE_MS = 320;

const OSM_SOURCE = "osm";

const STUDY_SOURCE = "study-area";
const STUDY_LAYER = "study-area-outline";

/*
 * The exact area the model was trained on, mirrored from backend/config.py
 * (LON_WEST/LON_EAST/LAT_SOUTH/LAT_NORTH). Drawing it is not decoration: every
 * score on this screen is undefined outside this box, and an official reading
 * a heat map has no other way to know where the evidence stops.
 */
const STUDY_RING: [number, number][] = [
  [-118.3, 34.03],
  [-118.22, 34.03],
  [-118.22, 34.14],
  [-118.3, 34.14],
  [-118.3, 34.03],
];

/* Centre of the northern edge, so the label sits just above the box. */
const STUDY_LABEL_AT: [number, number] = [-118.26, 34.14];


/*
 * OpenStreetMap Standard raster tiles.
 *
 * Declared inline rather than fetched as a remote style.json, which removes the
 * whole class of start-up races: MapLibre fires `load` as soon as it has parsed
 * this object, with no round trip for a style, glyphs or sprites first.
 *
 * The `background` layer underneath is the offline state. If not a single tile
 * arrives, the map shows a deliberate grey rather than a void.
 */
const BASEMAP_STYLE = {
  version: 8 as const,
  sources: {
    [OSM_SOURCE]: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
  layers: [
    {
      id: "background",
      type: "background" as const,
      paint: { "background-color": "#eef2f7" },
    },
    { id: OSM_SOURCE, type: "raster" as const, source: OSM_SOURCE },
  ],
};

/* Only used to decide whether to warn the official that the streets are
   missing. Nothing is torn down when it expires. */
const BASEMAP_TIMEOUT_MS = 9000;

/** Blue (cool) to yellow to red (hot), stretched over the 5th-95th percentile. */
function colourRamp(column: string, low: number, high: number) {
  const middle = low + (high - low) / 2;
  return [
    "interpolate",
    ["linear"],
    ["get", column],
    low, "#1d4ed8",
    low + (middle - low) / 2, "#38bdf8",
    middle, "#fde047",
    middle + (high - middle) / 2, "#f97316",
    high, "#b91c1c",
  ];
}

interface Props {
  onZoneSelected?: (zone: Zone) => void;
}

export default function HeatMap({ onZoneSelected }: Props) {
  const container = useRef<HTMLDivElement | null>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const popup = useRef<Popup | null>(null);
  const studyLabel = useRef<Marker | null>(null);
  const ready = useRef(false);

  // Kept in refs, not state: the MapLibre click handler is registered once and
  // would otherwise capture the values from the first render forever.
  const currentColumn = useRef("max_temperature");
  const currentUnit = useRef("C");
  const currentLabel = useRef("");

  const [layer, setLayer] = useState<LayerId>("tcm_peak_22h");
  const [metadata, setMetadata] = useState<HeatmapMetadata | null>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<PredictResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [basemapOffline, setBasemapOffline] = useState(false);

  /* -------------------------------------------------------- tile loading */

  const loadLayer = useCallback(async (which: LayerId, instance: MapLibreMap) => {
    setLoading(true);
    setError(null);
    try {
      // Fade the old layer out while the new one is in flight, so switching
      // reads as a transition rather than a flicker.
      if (instance.getLayer(TILE_LAYER)) {
        instance.setPaintProperty(TILE_LAYER, "fill-opacity", 0);
      }

      const data = await getHeatmap(which);
      const column = data.metadata.value_column;

      // Drop tiles with no value before handing the data to MapLibre: the
      // colour expression cannot interpolate over null and would log an error
      // for every one of them.
      const features = data.features.filter(
        (feature) =>
          feature.properties?.[column] !== null &&
          feature.properties?.[column] !== undefined,
      );
      const collection = { type: "FeatureCollection" as const, features };

      const { p5, p95 } = data.metadata.stats;
      const paint = colourRamp(column, p5, p95);

      currentColumn.current = column;
      currentUnit.current = data.metadata.unit;
      currentLabel.current = data.metadata.description;

      const existing = instance.getSource(TILE_SOURCE);
      if (existing) {
        (existing as GeoJSONSource).setData(collection as never);
        instance.setPaintProperty(TILE_LAYER, "fill-color", paint as never);
        instance.setPaintProperty(TILE_LAYER, "fill-opacity", FILL_OPACITY);
      } else {
        instance.addSource(TILE_SOURCE, {
          type: "geojson",
          data: collection as never,
        });
        // Raster basemaps bake their streets and labels into one image, so
        // there is no label layer to slide underneath - the heat fill can only
        // go on top. Readability is bought with opacity instead; see
        // FILL_OPACITY.
        //
        // The study-area outline is added at map load, so naming it here keeps
        // the boundary above the fill no matter which finishes first.
        instance.addLayer(
          {
            id: TILE_LAYER,
            type: "fill",
            source: TILE_SOURCE,
            paint: {
              "fill-color": paint as never,
              "fill-opacity": FILL_OPACITY,
              "fill-opacity-transition": { duration: FADE_MS },
              "fill-color-transition": { duration: 300 },

              // The two properties that kill the spreadsheet look.
              //
              // MapLibre draws a one-pixel outline on every fill in the layer
              // colour, and antialiases each polygon edge against whatever is
              // behind it. With 8,674 squares packed edge to edge, both show up
              // as a grid of hairlines: the basemap bleeding through thousands
              // of half-transparent seams. Turning them off makes neighbouring
              // tiles meet flush, which is most of the "smoothing" on its own.
              "fill-outline-color": "transparent",
              "fill-antialias": false,
            },
          },
          instance.getLayer(STUDY_LAYER) ? STUDY_LAYER : undefined,
        );

        instance.on("mouseenter", TILE_LAYER, () => {
          instance.getCanvas().style.cursor = "pointer";
        });
        instance.on("mouseleave", TILE_LAYER, () => {
          instance.getCanvas().style.cursor = "";
        });
        instance.on("click", TILE_LAYER, async (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const maplibregl = (await import("maplibre-gl")).default;
          const value = Number(feature.properties?.[currentColumn.current]);
          popup.current?.remove();
          popup.current = new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
            .setLngLat(event.lngLat)
            .setHTML(
              [
                '<div style="font-family:system-ui;font-size:12px;line-height:1.5">',
                `<div style="font-weight:700;color:#1e40af">${currentLabel.current}</div>`,
                `<div style="font-size:22px;font-weight:800;color:#b91c1c;margin:2px 0">${value.toFixed(2)} ${currentUnit.current}</div>`,
                '<div style="color:#64748b">100 m modeled tile, July 2025</div>',
                "</div>",
              ].join(""),
            )
            .addTo(instance);
        });
      }

      setMetadata(data.metadata);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : String(exception));
    } finally {
      setLoading(false);
    }
  }, []);

  /* ---------------------------------------------------------- risk pins */

  const openZone = useCallback(
    async (zone: Zone) => {
      onZoneSelected?.(zone);
      setDetailLoading(true);
      setDetail(null);
      map.current?.flyTo({ center: [zone.lon, zone.lat], zoom: 13.5, speed: 0.9 });
      try {
        setDetail(await predictTract(zone.tract_fips));
      } catch (exception) {
        setError(exception instanceof Error ? exception.message : String(exception));
      } finally {
        setDetailLoading(false);
      }
    },
    [onZoneSelected],
  );

  const loadZones = useCallback(
    async (instance: MapLibreMap) => {
      try {
        const maplibregl = (await import("maplibre-gl")).default;
        const data = await getRankedZones(10);
        setZones(data.zones);

        markers.current.forEach((marker) => marker.remove());
        markers.current = data.zones.map((zone, index) => {
          const element = document.createElement("div");
          element.className = "heat-pin";
          // The onboarding tour points at the highest-risk pin.
          if (index === 0) element.dataset.tour = "pin";
          element.style.background = index < 3 ? "#dc2626" : "#1e40af";
          element.textContent = String(index + 1);
          element.title = `#${index + 1} - tract ${zone.tract_fips} - risk ${zone.risk_score}`;
          element.addEventListener("click", (event) => {
            event.stopPropagation();
            void openZone(zone);
          });
          return new maplibregl.Marker({ element })
            .setLngLat([zone.lon, zone.lat])
            .addTo(instance);
        });
      } catch (exception) {
        setError(exception instanceof Error ? exception.message : String(exception));
      }
    },
    [openZone],
  );

  /* ---------------------------------------------------------- create map */

  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | null = null;
    let offlineTimer: ReturnType<typeof setTimeout> | null = null;
    let basemapTileArrived = false;

    void (async () => {
      // Imported here, not at the top of the file: maplibre-gl touches `window`
      // on import, and Next.js renders this module on the server first.
      const maplibregl = (await import("maplibre-gl")).default;
      if (cancelled || !container.current || map.current) return;

      const instance = new maplibregl.Map({
        container: container.current,
        style: BASEMAP_STYLE,
        center: CENTER,
        zoom: ZOOM,
        attributionControl: { compact: true },
      });
      instance.addControl(new maplibregl.NavigationControl({}), "top-right");
      instance.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");
      map.current = instance;

      // MapLibre sizes its canvas once, from whatever the container measured at
      // construction. If the stylesheet lands a tick later the canvas keeps the
      // stale size for good, so the container is watched explicitly.
      observer = new ResizeObserver(() => instance.resize());
      observer.observe(container.current);

      // `sourceId` is only present on the source-flavoured events, so it is not
      // on the base type MapLibre declares for these handlers.
      const sourceOf = (event: unknown) =>
        (event as { sourceId?: string }).sourceId;

      instance.on("data", (event) => {
        if (sourceOf(event) === OSM_SOURCE && "tile" in event) {
          basemapTileArrived = true;
          setBasemapOffline(false);
        }
      });

      instance.on("error", (event) => {
        const reason = event?.error?.message ?? "unknown MapLibre error";
        // Basemap tiles drop out and come back on their own; never escalate one
        // to the error banner, which is reserved for our API.
        if (sourceOf(event) === OSM_SOURCE || /tile/i.test(reason)) return;
        setError(reason);
      });

      instance.on("load", () => {
        ready.current = true;
        instance.resize();

        instance.addSource(STUDY_SOURCE, {
          type: "geojson",
          data: {
            type: "Feature",
            properties: {},
            geometry: { type: "Polygon", coordinates: [STUDY_RING] },
          } as never,
        });
        instance.addLayer({
          id: STUDY_LAYER,
          type: "line",
          source: STUDY_SOURCE,
          paint: {
            "line-color": "#1e40af",
            "line-opacity": 0.6,
            "line-width": 2,
            "line-dasharray": [3, 2],
          },
        });

        // An HTML marker, not a symbol layer. Text in MapLibre needs a `glyphs`
        // font endpoint, which the local raster style deliberately does not
        // have - adding one would put a network dependency back in front of
        // first paint.
        //
        // Anchored "top", so the caption hangs just inside the northern edge.
        // Hung above it instead, it sits off the top of the viewport at the
        // default zoom and is never seen.
        const label = document.createElement("div");
        label.className = "study-label";
        label.textContent = "Study Area: Central Los Angeles";
        studyLabel.current = new maplibregl.Marker({
          element: label,
          anchor: "top",
          // Pushed clear of the layer-toggle row, which sits over the polygon's
          // northern edge at the default zoom.
          offset: [0, 66],
        })
          .setLngLat(STUDY_LABEL_AT)
          .addTo(instance);

        void loadLayer(layer, instance);
        void loadZones(instance);
      });

      // Purely informational. The style is local, so `load` always fires and the
      // heat layer always draws; this only tells the official why the streets
      // underneath are missing. Nothing is replaced or torn down.
      offlineTimer = setTimeout(() => {
        if (!basemapTileArrived && !cancelled) setBasemapOffline(true);
      }, BASEMAP_TIMEOUT_MS);
    })();

    return () => {
      cancelled = true;
      if (offlineTimer) clearTimeout(offlineTimer);
      observer?.disconnect();
      markers.current.forEach((marker) => marker.remove());
      markers.current = [];
      popup.current?.remove();
      studyLabel.current?.remove();
      studyLabel.current = null;
      map.current?.remove();
      map.current = null;
      ready.current = false;
    };
    // Runs once on mount. The layer toggle has its own effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (ready.current && map.current) void loadLayer(layer, map.current);
  }, [layer, loadLayer]);

  /* -------------------------------------------------------------- render */

  const stats = metadata?.stats;

  return (
    <div className="relative h-full w-full overflow-hidden bg-slate-200">
      {/* `map-host` is not decoration: see the comment in globals.css. */}
      <div ref={container} className="map-host absolute inset-0" />

      {/* Loading skeleton */}
      {loading ? (
        <div className="absolute inset-0 z-30 flex items-center justify-center">
          <div className="skeleton absolute inset-0" />
          <div className="relative flex items-center gap-3 rounded-xl bg-white/90 px-5 py-3 shadow-xl ring-1 ring-slate-300 backdrop-blur">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-700" />
            <div>
              <div className="text-sm font-semibold text-slate-800">
                Loading 8,674 modeled tiles
              </div>
              <div className="text-[11px] text-slate-500">
                {LAYERS.find((option) => option.id === layer)?.hint}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Layer toggle */}
      <div
        data-tour="layers"
        className="absolute left-4 top-4 z-10 flex gap-1 rounded-xl bg-white/95 p-1.5 shadow-xl ring-1 ring-slate-900/10 backdrop-blur"
      >
        {LAYERS.map((option) => {
          const active = layer === option.id;
          return (
            <button
              key={option.id}
              type="button"
              title={option.hint}
              onClick={() => setLayer(option.id)}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 ${
                active
                  ? "bg-blue-800 text-white shadow-md"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              <LayerIcon id={option.id} className="h-4 w-4" />
              {option.label}
              {option.starred ? (
                <span className={active ? "text-amber-300" : "text-amber-500"}>&#9733;</span>
              ) : null}
            </button>
          );
        })}
      </div>

      {error ? (
        <div className="fade-up absolute left-1/2 top-20 z-30 max-w-lg -translate-x-1/2 rounded-xl bg-red-50 px-4 py-3 text-xs text-red-800 shadow-xl ring-1 ring-red-300">
          <div className="font-semibold">Backend unreachable</div>
          <div className="mt-1 font-mono">{error}</div>
          <div className="mt-1 font-mono text-[10px]">
            .venv\Scripts\python.exe -m uvicorn api.main:app --app-dir backend --port 8000
          </div>
        </div>
      ) : null}

      {/* Tract detail card */}
      {detail || detailLoading ? (
        <div className="fade-up absolute bottom-10 left-4 z-10 w-80 rounded-xl bg-white/97 p-4 shadow-2xl ring-1 ring-slate-900/10 backdrop-blur">
          <button
            type="button"
            onClick={() => setDetail(null)}
            className="absolute right-2.5 top-1.5 text-lg leading-none text-slate-400 transition hover:text-slate-700"
            aria-label="Close"
          >
            &times;
          </button>
          {detailLoading ? (
            <div className="text-sm text-slate-600">Scoring tract&hellip;</div>
          ) : null}
          {detail ? (
            <>
              <div className="font-mono text-[11px] text-slate-500">
                Tract {detail.tract_fips}
              </div>
              <div className="text-sm font-bold text-slate-900">{detail.name}</div>
              <div className="mt-2.5 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg bg-red-50 p-2 ring-1 ring-red-100">
                  <div className="text-lg font-extrabold text-red-700">
                    {detail.risk_score_b}
                  </div>
                  <div className="text-[9px] font-semibold uppercase text-slate-500">
                    Risk (B)
                  </div>
                </div>
                <div className="rounded-lg bg-blue-50 p-2 ring-1 ring-blue-100">
                  <div className="text-lg font-extrabold text-blue-800">
                    {detail.risk_score_a}
                  </div>
                  <div className="text-[9px] font-semibold uppercase text-slate-500">
                    Physical (A)
                  </div>
                </div>
                <div className="rounded-lg bg-slate-100 p-2 ring-1 ring-slate-200">
                  <div className="text-lg font-extrabold text-slate-700">
                    {detail.official_calenviroscreen_score}
                  </div>
                  <div className="text-[9px] font-semibold uppercase text-slate-500">
                    CES 4.0
                  </div>
                </div>
              </div>
              <div className="mt-3 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                Physical drivers (SHAP, Model A)
              </div>
              <ul className="mt-1.5 space-y-1.5 text-[11px] text-slate-700">
                {detail.top_shap_features.map((driver) => (
                  <li key={driver.feature} className="flex gap-2">
                    <span
                      className={`shrink-0 rounded px-1 font-mono text-[10px] font-bold ${
                        driver.impact_points >= 0
                          ? "bg-red-100 text-red-700"
                          : "bg-blue-100 text-blue-800"
                      }`}
                    >
                      {driver.impact_points >= 0 ? "+" : ""}
                      {driver.impact_points}
                    </span>
                    <span>
                      {driver.label}: <strong>{driver.value}</strong> {driver.unit}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}

      {/* Right-hand rail: shortlist on top, legend directly beneath it.
          They used to sit at opposite ends of the map, which read as two
          unrelated widgets; stacked with a single gap they read as one
          control surface. `top-28` clears MapLibre's zoom buttons. */}
      {zones.length > 0 || stats ? (
        <div className="absolute right-4 top-28 z-10 flex w-60 flex-col gap-4">
          {zones.length > 0 ? (
            <div className="fade-up rounded-xl bg-white/95 p-2.5 shadow-xl ring-1 ring-slate-900/10 backdrop-blur">
              <div className="px-1 pb-1.5 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                Highest risk tracts
              </div>
              {zones.slice(0, 5).map((zone, index) => (
                <button
                  key={zone.tract_fips}
                  type="button"
                  onClick={() => void openZone(zone)}
                  className="flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left text-[11px] transition hover:bg-slate-100"
                >
                  <span
                    className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-white shadow"
                    style={{ background: index < 3 ? "#dc2626" : "#1e40af" }}
                  >
                    {index + 1}
                  </span>
                  <span className="font-mono text-slate-600">
                    {zone.tract_fips.slice(-6)}
                  </span>
                  <span className="ml-auto font-bold text-red-700">{zone.risk_score}</span>
                </button>
              ))}
            </div>
          ) : null}

          {stats ? (
            <div className="fade-up rounded-xl bg-white/95 p-3.5 shadow-xl ring-1 ring-slate-900/10 backdrop-blur">
              <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-500">
                <LayerIcon id={layer} className="h-3.5 w-3.5" />
                {metadata?.description}
              </div>
              <div
                className="mt-2.5 h-3.5 w-full rounded-full ring-1 ring-slate-900/10"
                style={{
                  background:
                    "linear-gradient(to right,#1d4ed8,#38bdf8,#fde047,#f97316,#b91c1c)",
                }}
              />
              <div className="mt-1.5 flex justify-between font-mono text-[11px] font-semibold text-slate-700">
                <span>{stats.p5}</span>
                <span className="text-slate-400">{stats.mean}</span>
                <span>{stats.p95}</span>
              </div>
              <div className="mt-1 text-[10px] text-slate-500">
                {metadata?.unit} &middot; {metadata?.tiles.toLocaleString()} modeled
                tiles &middot; 5th-95th pct
              </div>
              <div className="mt-2.5 flex items-center gap-2 border-t border-slate-200 pt-2.5 text-[10px] text-slate-600">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-red-600 text-[9px] font-bold text-white">
                  1
                </span>
                Top-10 risk tracts &mdash; click a pin
              </div>
              {basemapOffline ? (
                <div className="mt-2 rounded-md bg-amber-50 px-2 py-1 text-[10px] text-amber-800 ring-1 ring-amber-200">
                  Street basemap unavailable; heat data is unaffected.
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
