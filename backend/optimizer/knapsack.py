"""Budget optimizer: which tracts to treat, with which intervention.

This is the 0/1 knapsack problem. Each tract may receive at most one
intervention; each intervention has a cost and an expected benefit; the total
cost must fit the budget; we maximise total benefit.

Solved exactly by dynamic programming over the budget in $10,000 steps. With
roughly 100 tracts and a budget in the millions that is a table of about
100 x 500 cells - instantaneous, and exact, so there is no reason to approximate.

COSTS ARE PLANNING ESTIMATES, NEVER QUOTES
------------------------------------------
    trees      $400/tree x 500 trees   = $200,000 per tract   (USDA Forest Service)
    cool_roof  ~$180,000 per tract                            (CoolRoofs NYC)
    shade      2 structures x ~$60,000 = $120,000 per tract   (municipal reports)

EXPECTED TEMPERATURE REDUCTION
------------------------------
Per Smith, I.A., et al. (2025), "Integrated tree canopy expansion and cool roofs
can optimize air temperature and heat exposure reductions in Boston",
Communications Earth & Environment, https://doi.org/10.1038/s43247-025-02462-3

That study found tree canopy delivers air-temperature reductions about 35%
larger than cool roofs per unit deployed, while cool roofs deliver greater
*population* heat-exposure reduction because they can be installed in dense,
built-out districts where there is no ground to plant. The figures below encode
that asymmetry: trees cool more, but the rule in intervention_rules.py only
selects them where there is room.

    trees      in a low-canopy tract    -1.5 C
    cool_roof  in a dense tract         -1.2 C   (1.5 / 1.35, per the 35% gap)
    shade      in a mixed tract         -0.8 C   localised, not tract-wide

These are order-of-magnitude planning figures for prioritisation, not
engineering predictions for a specific site.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from optimizer.intervention_rules import (  # noqa: E402
    COOL_ROOF,
    SHADE,
    TREES,
    recommend_intervention,
)

# Planning-grade unit costs, in US dollars per tract.
INTERVENTION_COSTS: dict[str, float] = {
    TREES: 200_000.0,
    COOL_ROOF: 180_000.0,
    SHADE: 120_000.0,
}

# Expected air-temperature reduction in degrees Celsius.
EXPECTED_REDUCTION_C: dict[str, float] = {
    TREES: 1.5,
    COOL_ROOF: 1.2,
    SHADE: 0.8,
}

INTERVENTION_DETAIL: dict[str, str] = {
    TREES: "Plant approximately 500 street trees (~$400 each)",
    COOL_ROOF: "Coat public and multi-family rooftops with high-albedo material",
    SHADE: "Install 2 shade structures at high-traffic transit stops",
}

# Dynamic-programming resolution. $10,000 is finer than any real municipal
# budget line, and keeps the table small.
BUDGET_STEP_USD = 10_000


@dataclass
class Candidate:
    """One tract, with the single intervention the rules selected for it."""

    tract_fips: str
    risk_score: float
    intervention: str
    cost: float
    expected_reduction_c: float
    name: str = ""
    detail: str = field(default="")

    @property
    def benefit(self) -> float:
        """Risk-weighted cooling: treating a high-risk tract is worth more.

        A degree removed from a tract scoring 95 helps more people at risk than
        the same degree removed from a tract scoring 40, so the two are not
        interchangeable and the optimizer must not treat them as such.
        """
        return self.risk_score * self.expected_reduction_c


def build_candidates(zones: list[dict]) -> list[Candidate]:
    """Turn scored tracts into priced, one-intervention-each candidates.

    ``zones`` items need ``tract_fips``, ``risk_score``,
    ``impervious_surface_pct`` and ``tree_canopy_pct``.
    """
    candidates: list[Candidate] = []
    for zone in zones:
        try:
            intervention = recommend_intervention(zone)
        except (KeyError, ValueError):
            # A tract with unknown land cover cannot be priced honestly.
            continue
        candidates.append(
            Candidate(
                tract_fips=str(zone["tract_fips"]),
                risk_score=float(zone["risk_score"]),
                intervention=intervention,
                cost=INTERVENTION_COSTS[intervention],
                expected_reduction_c=EXPECTED_REDUCTION_C[intervention],
                name=str(zone.get("name", "")),
                detail=INTERVENTION_DETAIL[intervention],
            )
        )
    return candidates


def solve_knapsack(candidates: list[Candidate], budget_usd: float) -> list[Candidate]:
    """Exact 0/1 knapsack by dynamic programming over discretised budget."""
    if budget_usd <= 0 or not candidates:
        return []

    capacity = int(budget_usd // BUDGET_STEP_USD)
    weights = [int(c.cost // BUDGET_STEP_USD) for c in candidates]
    values = [c.benefit for c in candidates]

    # table[i][w] = best benefit using the first i candidates within budget w
    table = [[0.0] * (capacity + 1) for _ in range(len(candidates) + 1)]
    for i in range(1, len(candidates) + 1):
        weight, value = weights[i - 1], values[i - 1]
        row, previous = table[i], table[i - 1]
        for w in range(capacity + 1):
            row[w] = previous[w]
            if weight <= w:
                alternative = previous[w - weight] + value
                if alternative > row[w]:
                    row[w] = alternative

    # Walk the table backwards to recover which candidates were taken.
    chosen: list[Candidate] = []
    w = capacity
    for i in range(len(candidates), 0, -1):
        if table[i][w] != table[i - 1][w]:
            chosen.append(candidates[i - 1])
            w -= weights[i - 1]

    chosen.reverse()
    return chosen


def optimize(zones: list[dict], budget_usd: float) -> dict:
    """Return the funded plan and what it buys.

    ``coverage_score`` is the share of the total risk-weighted cooling available
    across all candidates that this budget actually captures - a 0-100 answer to
    "how much of the problem does this money solve?".
    """
    candidates = build_candidates(zones)
    chosen = solve_knapsack(candidates, budget_usd)

    total_cost = sum(c.cost for c in chosen)
    total_benefit = sum(c.benefit for c in chosen)
    available_benefit = sum(c.benefit for c in candidates)
    coverage = (total_benefit / available_benefit * 100) if available_benefit else 0.0

    plan = [
        {
            "tract_fips": c.tract_fips,
            "name": c.name,
            "intervention": c.intervention,
            "detail": c.detail,
            "cost_usd": c.cost,
            "risk_score": round(c.risk_score, 1),
            "expected_reduction_c": c.expected_reduction_c,
        }
        for c in sorted(chosen, key=lambda c: c.risk_score, reverse=True)
    ]

    return {
        "plan": plan,
        "total_cost_usd": total_cost,
        "budget_usd": budget_usd,
        "remaining_usd": budget_usd - total_cost,
        "zones_funded": len(chosen),
        "zones_considered": len(candidates),
        "coverage_score": round(coverage, 1),
        # Deliberately NOT a sum. Degrees in separate tracts do not add: three
        # tracts each cooled by 1 C is not "3 C of cooling", and quoting it that
        # way would be indefensible in front of a technical reviewer.
        "mean_expected_reduction_c": round(
            sum(c.expected_reduction_c for c in chosen) / len(chosen), 2
        ) if chosen else 0.0,
        "reduction_note": (
            "Each funded tract cools by the amount shown in its own plan entry. "
            "These are per-tract figures and must not be added together."
        ),
        "mean_risk_of_funded_zones": round(
            sum(c.risk_score for c in chosen) / len(chosen), 1
        ) if chosen else 0.0,
        "cost_note": (
            "Unit costs are planning-grade estimates from public sources "
            "(USDA Forest Service, CoolRoofs NYC, municipal reports), not quotes. "
            "Temperature reductions follow Smith et al. (2025), "
            "doi:10.1038/s43247-025-02462-3."
        ),
    }
