"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Three-step onboarding, shown once per browser.
 *
 * Targets are found by `data-tour` attributes rather than refs, because the
 * three of them live in different components - and one of them, the risk pin,
 * is a plain DOM node created by MapLibre outside React's tree entirely.
 */

const STORAGE_KEY = "heatgov.tour.v1";
const CARD_WIDTH = 304;
const GAP = 14;
const HALO = 8;
const EDGE = 12;

/* Upper bound on the card's rendered height. Only the side placement needs it,
   to keep a card anchored to a target near the bottom of the screen fully
   visible - the first pin sits about twenty pixels off the bottom edge. */
const CARD_MAX_HEIGHT = 168;

const POLL_MS = 400;
const POLL_TIMEOUT_MS = 30_000;

type Placement = "bottom" | "top" | "right";

interface Step {
  target: string;
  title: string;
  body: string;
  placement: Placement;
}

const STEPS: Step[] = [
  {
    target: "layers",
    title: "Four heat layers",
    body: "Try switching between Day and Night to see the difference.",
    placement: "bottom",
  },
  {
    target: "pin",
    title: "The ten highest-risk tracts",
    body: "Click any red pin to see zone details and SHAP explanations.",
    placement: "right",
  },
  {
    target: "chat",
    title: "Ask for a plan",
    body: "Ask for a budget plan: try “I have $500K”.",
    placement: "top",
  },
];

function find(target: string): Element | null {
  return document.querySelector(`[data-tour="${target}"]`);
}

export default function Tour() {
  const [index, setIndex] = useState<number | null>(null);
  const [box, setBox] = useState<DOMRect | null>(null);

  /* ------------------------------------------------------------- start it */

  useEffect(() => {
    // A browser with storage blocked simply gets the tour every time, which is
    // a better failure than a crash on first paint.
    try {
      if (window.localStorage.getItem(STORAGE_KEY) === "seen") return;
    } catch {
      /* private mode, or site data disabled */
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const startedAt = Date.now();

    // The risk pins only exist once the map has loaded and the API has
    // answered, so the tour waits for all three anchors rather than pointing
    // at empty space.
    const poll = () => {
      if (cancelled) return;
      if (STEPS.every((step) => find(step.target))) {
        setIndex(0);
        return;
      }
      if (Date.now() - startedAt > POLL_TIMEOUT_MS) return;
      timer = setTimeout(poll, POLL_MS);
    };

    timer = setTimeout(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  /* ------------------------------------------------------------- measure */

  const measure = useCallback(() => {
    if (index === null) return;
    const element = find(STEPS[index].target);
    setBox(element ? element.getBoundingClientRect() : null);
  }, [index]);

  useEffect(() => {
    if (index === null) return;
    // Measured on the next frame, not inline: the pin this points at may have
    // been added to the DOM in the same tick, and its box would still be empty.
    const frame = requestAnimationFrame(measure);
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", measure);
    };
  }, [index, measure]);

  /* -------------------------------------------------------------- finish */

  const finish = useCallback(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, "seen");
    } catch {
      /* nothing to do; the tour will simply show again */
    }
    setIndex(null);
  }, []);

  useEffect(() => {
    if (index === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, finish]);

  if (index === null || !box) return null;

  const step = STEPS[index];
  const last = index === STEPS.length - 1;

  /* ------------------------------------------------------- card placement */

  const clamp = (value: number, low: number, high: number) =>
    Math.max(low, Math.min(value, high));
  const clampLeft = (value: number) =>
    clamp(value, EDGE, window.innerWidth - CARD_WIDTH - EDGE);

  const card: React.CSSProperties = { width: CARD_WIDTH, position: "fixed" };
  const arrow: React.CSSProperties = { position: "absolute" };
  const centreX = box.left + box.width / 2;
  const centreY = box.top + box.height / 2;

  if (step.placement === "bottom") {
    card.left = clampLeft(box.left);
    card.top = box.bottom + GAP;
    arrow.top = -6;
    arrow.left = clamp(centreX - (card.left as number) - 6, 16, CARD_WIDTH - 28);
  } else if (step.placement === "top") {
    card.left = clampLeft(centreX - CARD_WIDTH / 2);
    // Anchored by its bottom edge, so no guess at the card's height is needed.
    card.bottom = window.innerHeight - box.top + GAP;
    arrow.bottom = -6;
    arrow.left = clamp(centreX - (card.left as number) - 6, 16, CARD_WIDTH - 28);
  } else {
    // Prefer the right of the target, but flip when it would run off-screen.
    const toTheRight = box.right + GAP + CARD_WIDTH + EDGE < window.innerWidth;
    card.left = toTheRight ? box.right + GAP : box.left - GAP - CARD_WIDTH;
    // Clamped so a target near the bottom of the window - the highest-risk pin
    // is one - cannot push the buttons off the screen.
    card.top = clamp(
      centreY - CARD_MAX_HEIGHT / 2,
      EDGE,
      window.innerHeight - CARD_MAX_HEIGHT - EDGE,
    );
    arrow.top = clamp(centreY - (card.top as number) - 6, 14, CARD_MAX_HEIGHT - 30);
    if (toTheRight) arrow.left = -6;
    else arrow.right = -6;
  }

  return (
    <div className="pointer-events-none fixed inset-0 z-50">
      {/* The scrim is drawn as one enormous shadow cast outward by the
          highlight, which cuts a hole around the target without needing an SVG
          mask. Clicks pass straight through, so the page stays usable. */}
      <div
        className="pointer-events-none fixed rounded-2xl ring-2 ring-blue-700 transition-all duration-300"
        style={{
          left: box.left - HALO,
          top: box.top - HALO,
          width: box.width + HALO * 2,
          height: box.height + HALO * 2,
          boxShadow: "0 0 0 9999px rgb(15 23 42 / 0.34)",
        }}
      />

      <div
        style={card}
        role="dialog"
        aria-label={step.title}
        className="fade-up pointer-events-auto rounded-xl bg-white p-4 shadow-2xl ring-1 ring-slate-900/10"
      >
        <div
          style={arrow}
          className="h-3 w-3 rotate-45 bg-white ring-1 ring-slate-900/10"
        />

        <div className="relative">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-800 text-[10px] font-bold text-white">
              {index + 1}
            </span>
            <h3 className="text-sm font-bold text-slate-900">{step.title}</h3>
          </div>

          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-600">
            {step.body}
          </p>

          <div className="mt-3 flex items-center gap-2">
            <div className="flex gap-1.5">
              {STEPS.map((_, dot) => (
                <span
                  key={dot}
                  className={`h-1.5 rounded-full transition-all ${
                    dot === index ? "w-4 bg-blue-800" : "w-1.5 bg-slate-300"
                  }`}
                />
              ))}
            </div>

            {last ? null : (
              <button
                type="button"
                onClick={finish}
                className="ml-auto text-[11px] font-medium text-slate-400 transition hover:text-slate-700"
              >
                Skip
              </button>
            )}

            <button
              type="button"
              onClick={() => (last ? finish() : setIndex(index + 1))}
              className={`${last ? "ml-auto" : ""} rounded-lg bg-blue-800 px-3.5 py-1.5 text-xs font-bold text-white shadow-md transition hover:bg-blue-900`}
            >
              {last ? "Got it" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
