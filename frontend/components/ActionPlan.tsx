"use client";

import { ClipboardIcon, SparkIcon } from "@/components/icons";
import { INTERVENTION_LABELS, type OptimizeResponse, usd } from "@/lib/api";

interface Props {
  plan: OptimizeResponse | null;
  loading: boolean;
  error: string | null;
  /** Drops a worked example into the chat composer and shows it. */
  onTryExample?: () => void;
}

const INTERVENTION_STYLES: Record<string, string> = {
  cool_roof: "bg-sky-100 text-sky-800 ring-sky-200",
  trees: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  shade: "bg-amber-100 text-amber-800 ring-amber-200",
};

export default function ActionPlan({ plan, loading, error, onTryExample }: Props) {
  return (
    <section className="flex h-full flex-col bg-slate-50">
      <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-2.5 shadow-sm">
        <ClipboardIcon className="h-4 w-4 text-blue-800" />
        <h2 className="text-sm font-bold text-slate-800">Action Plan</h2>
        {plan ? (
          <span className="rounded-full bg-blue-800 px-2.5 py-0.5 text-[10px] font-bold text-white shadow-sm">
            {usd(plan.budget_usd)}
          </span>
        ) : null}
        {loading ? (
          <span className="ml-auto flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-blue-700" />
            Optimizing&hellip;
          </span>
        ) : null}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {error ? (
          <div className="m-4 rounded-xl bg-red-50 p-3 text-xs text-red-800 shadow-sm ring-1 ring-red-200">
            <div className="font-semibold">Optimizer failed</div>
            <div className="mt-1 font-mono">{error}</div>
          </div>
        ) : null}

        {!plan && !loading && !error ? (
          <div className="flex h-full flex-col items-center justify-center px-8 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-linear-to-br from-blue-700 to-blue-900 shadow-lg">
              <SparkIcon className="h-7 w-7 text-amber-300" />
            </div>
            <p className="mt-3 text-sm font-bold text-slate-800">
              No plan yet. Ask HeatGov AI for one!
            </p>
            <p className="mt-1 max-w-xs text-xs leading-relaxed text-slate-500">
              It ranks every census tract by predicted heat risk, then solves for
              the combination of interventions that buys the most cooling.
            </p>
            {onTryExample ? (
              <button
                type="button"
                onClick={onTryExample}
                className="mt-4 rounded-lg bg-blue-800 px-4 py-2 text-xs font-bold text-white shadow-md transition hover:bg-blue-900"
              >
                Try Example
              </button>
            ) : null}
          </div>
        ) : null}

        {plan ? (
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 z-10 bg-slate-100/95 text-[10px] font-bold uppercase tracking-wide text-slate-500 backdrop-blur">
              <tr>
                <th className="px-2.5 py-2">#</th>
                <th className="px-2.5 py-2">Census Tract</th>
                <th className="px-2.5 py-2">Intervention</th>
                <th className="px-2.5 py-2 text-right">Cost</th>
                <th className="px-2.5 py-2 text-right">Cooling</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {plan.plan.map((item, index) => (
                <tr key={item.tract_fips} className="bg-white transition hover:bg-blue-50/60">
                  <td className="px-2.5 py-2.5 font-bold text-slate-300">{index + 1}</td>
                  <td className="px-2.5 py-2.5">
                    <div className="font-mono font-medium text-slate-800">
                      {item.tract_fips}
                    </div>
                    <div className="text-[10px] font-semibold text-red-600">
                      risk {item.risk_score}
                    </div>
                  </td>
                  <td className="px-2.5 py-2.5">
                    <span
                      className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ring-1 ${
                        INTERVENTION_STYLES[item.intervention] ??
                        "bg-slate-100 text-slate-700 ring-slate-200"
                      }`}
                    >
                      {INTERVENTION_LABELS[item.intervention] ?? item.intervention}
                    </span>
                    <div className="mt-1 text-[10px] leading-tight text-slate-500">
                      {item.detail}
                    </div>
                  </td>
                  <td className="px-2.5 py-2.5 text-right font-mono font-semibold text-slate-800">
                    {usd(item.cost_usd)}
                  </td>
                  <td className="px-2.5 py-2.5 text-right font-mono font-bold text-blue-800">
                    &minus;{item.expected_reduction_c}&deg;C
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>

      {plan ? (
        <footer className="border-t border-slate-200 bg-white px-4 py-2.5 shadow-[0_-4px_12px_-8px_rgba(15,23,42,0.4)]">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-semibold text-slate-600">
            <span>
              Total funded:{" "}
              <span className="font-mono text-sm font-extrabold text-blue-800">
                {usd(plan.total_cost_usd)}
              </span>
            </span>
            <span>
              Zones covered:{" "}
              <span className="font-mono text-sm font-extrabold text-blue-800">
                {plan.zones_funded}/{plan.zones_considered}
              </span>
            </span>
            <span>
              Impact score:{" "}
              <span className="font-mono text-sm font-extrabold text-red-600">
                {plan.coverage_score}%
              </span>
            </span>
            <span className="text-slate-400">Unspent: {usd(plan.remaining_usd)}</span>
          </div>

          {/* Per-tract, never summed. Adding degrees across separate tracts is
              meaningless, and the backend deliberately does not expose a total. */}
          <p className="mt-1.5 text-[10px] leading-tight text-slate-500">
            Each funded tract cools by the amount shown in its own row (mean{" "}
            {plan.mean_expected_reduction_c}&deg;C). These are per-tract figures
            and must not be added together.
          </p>

          <p className="mt-1 text-[10px] leading-tight text-slate-400">
            Cost estimates based on public references (USDA Forest Service, NYC
            CoolRoofs), not quotes.
            {plan.canopy_data_available
              ? null
              : " Tree canopy data provisional: pervious surface used as a stand-in."}
          </p>
        </footer>
      ) : null}
    </section>
  );
}
