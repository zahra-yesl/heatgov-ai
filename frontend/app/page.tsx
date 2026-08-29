/**
 * HeatGov AI — Central Los Angeles
 * FortyGuard Hackathon 2026
 * Authors: Zahra Yeslek (ML & Backend), Mariem Elbechir (Data & Frontend)
 * License: MIT
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import ActionPlan from "@/components/ActionPlan";
import ChatPanel from "@/components/ChatPanel";
import HeatMap from "@/components/HeatMap";
import Tour from "@/components/Tour";
import { ClipboardIcon, SparkIcon, ThermometerIcon } from "@/components/icons";
import {
  type HealthResponse,
  type OptimizeResponse,
  getHealth,
  optimizeBudget,
} from "@/lib/api";

/**
 * The whole product is one screen.
 *
 * This component owns the state the panels share. The chat detects a budget and
 * hands it up; the page calls the optimizer and hands the plan back down. The
 * panels never talk to each other directly - a pattern React calls "lifting
 * state up", and the reason the table can never disagree with the answer.
 */
export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [plan, setPlan] = useState<OptimizeResponse | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);

  const [tab, setTab] = useState<Tab>("chat");
  const [planUnread, setPlanUnread] = useState(false);
  const [prefill, setPrefill] = useState<{ text: string; nonce: number } | null>(null);

  // Mirrors `tab` for the optimizer callback, which is memoised with no deps
  // and would otherwise read whichever tab was open when the page mounted.
  const tabRef = useRef(tab);
  useEffect(() => {
    tabRef.current = tab;
  }, [tab]);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  const handleBudget = useCallback(async (budgetUsd: number) => {
    setPlanLoading(true);
    setPlanError(null);
    try {
      setPlan(await optimizeBudget(budgetUsd, 10));
      // Badge it, never jump to it. An official mid-sentence in the chat should
      // not have the panel swapped out from under them.
      if (tabRef.current !== "plan") setPlanUnread(true);
    } catch (exception) {
      setPlanError(exception instanceof Error ? exception.message : String(exception));
    } finally {
      setPlanLoading(false);
    }
  }, []);

  const online = health?.status === "ok";

  return (
    <div className="flex h-screen min-w-7xl flex-col bg-slate-200">
      <header className="flex shrink-0 items-center gap-4 bg-linear-to-r from-blue-950 via-blue-800 to-blue-700 px-6 py-3 text-white shadow-lg">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/25">
          <ThermometerIcon className="h-6 w-6 text-amber-300" />
        </span>

        <div>
          <h1 className="text-2xl font-extrabold leading-tight tracking-tight">
            HeatGov AI
            <span className="ml-2 text-lg font-medium text-blue-200">
              Central Los Angeles
            </span>
          </h1>
          <p className="text-xs leading-tight text-blue-200/90">
            From &ldquo;where is it hot?&rdquo; to a budgeted action plan
          </p>
        </div>

        <div className="ml-auto flex items-center gap-4">
          <dl className="flex items-stretch gap-2">
            <Stat label="Model A R&sup2;" value={health?.model_a_r2 ?? "--"} />
            <Stat label="Model B R&sup2;" value={health?.model_b_r2 ?? "--"} />
            <Stat label="Tracts" value={health?.tracts ?? 94} />
            <Stat label="Tiles" value="8,674" />
          </dl>

          <span
            className="flex items-center gap-1.5 rounded-full bg-black/25 px-3 py-1.5 text-[11px] font-semibold ring-1 ring-white/15"
            title={health ? `API ${health.status}` : "API unreachable"}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                online ? "bg-emerald-400 shadow-[0_0_8px_2px_rgba(52,211,153,0.7)]" : "bg-red-400"
              }`}
            />
            {online ? "API online" : "API offline"}
          </span>
        </div>
      </header>

      <main className="flex min-h-0 flex-1">
        {/* Left: the map, 60% of the screen */}
        <div className="relative min-w-0 flex-6">
          <HeatMap />
        </div>

        {/* Right: one panel at a time, chosen by tab */}
        <div className="flex min-w-0 flex-4 flex-col border-l border-slate-300 shadow-[-8px_0_24px_-16px_rgba(15,23,42,0.5)]">
          <div role="tablist" className="flex shrink-0 gap-px bg-slate-300">
            <TabButton
              active={tab === "chat"}
              onClick={() => setTab("chat")}
              icon={<SparkIcon className="h-4 w-4" />}
              label="Chat"
            />
            <TabButton
              active={tab === "plan"}
              onClick={() => {
                setTab("plan");
                setPlanUnread(false);
              }}
              icon={<ClipboardIcon className="h-4 w-4" />}
              label="Action Plan"
              badge={planUnread}
            />
          </div>

          {/* Both panels stay mounted and are hidden with CSS. Unmounting the
              chat would throw away the message history and the session id, so
              switching tabs would silently start a new conversation. */}
          <div className="relative min-h-0 flex-1">
            <div
              role="tabpanel"
              aria-hidden={tab !== "chat"}
              className={`h-full ${tab === "chat" ? "" : "hidden"}`}
            >
              <ChatPanel
                onBudgetDetected={handleBudget}
                geminiModel={health?.gemini_model ?? null}
                prefill={prefill}
              />
            </div>

            <div
              role="tabpanel"
              aria-hidden={tab !== "plan"}
              className={`h-full ${tab === "plan" ? "" : "hidden"}`}
            >
              <ActionPlan
                plan={plan}
                loading={planLoading}
                error={planError}
                onTryExample={() => {
                  setPrefill({
                    text: "I have $500,000 for Central LA. Where should I invest?",
                    nonce: Date.now(),
                  });
                  setTab("chat");
                }}
              />
            </div>
          </div>
        </div>
      </main>

      <Tour />
    </div>
  );
}

type Tab = "chat" | "plan";

function TabButton({
  active,
  onClick,
  icon,
  label,
  badge,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  badge?: boolean;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex h-12 flex-1 items-center justify-center gap-2 text-sm transition-colors ${
        active
          ? "bg-white font-bold text-blue-800 shadow-sm"
          : "bg-slate-100 font-medium text-slate-500 hover:bg-slate-50 hover:text-slate-700"
      }`}
    >
      {icon}
      {label}
      {/* Sits next to the label, not out at the tab's edge, where it reads as
          an unrelated speck rather than a mark on this tab. */}
      {badge ? (
        <span className="pulse-once h-2 w-2 rounded-full bg-red-600" aria-label="new plan" />
      ) : null}
    </button>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-white/10 px-3 py-1 text-center ring-1 ring-white/15">
      <dd className="font-mono text-sm font-bold leading-tight text-white">{value}</dd>
      <dt
        className="text-[9px] font-semibold uppercase tracking-wide text-blue-200"
        dangerouslySetInnerHTML={{ __html: label }}
      />
    </div>
  );
}
