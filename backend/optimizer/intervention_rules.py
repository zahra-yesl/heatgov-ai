"""Rule-based intervention recommendation for a census tract.

The optimizer (Step 5) calls this to decide *which* intervention to price for a
tract before deciding *whether* the budget can afford it.

SCIENTIFIC BASIS
----------------
Smith, I.A., et al. (2025). "Integrated tree canopy expansion and cool roofs can
optimize air temperature and heat exposure reductions in Boston."
Communications Earth & Environment. https://doi.org/10.1038/s43247-025-02462-3

That study found two things that pull in opposite directions:

* Tree canopy expansion delivers air-temperature reductions roughly **35%
  larger** than cool roofs, per unit deployed.
* Cool roofs nonetheless deliver **greater population heat-exposure reduction**
  overall, because they can be installed in exactly the dense, built-up,
  socially vulnerable districts where there is no room to plant a tree.

So the choice is not "which is better in general" but "which is deployable
here". Dense, highly impervious tracts have roofs and no planting space; that is
why the impervious-surface test is applied first.
"""

from __future__ import annotations

# Above this share of impervious surface a tract is effectively fully built out:
# there is roof area available but little open ground for planting.
IMPERVIOUS_DENSE_THRESHOLD_PCT = 80.0

# Below this canopy share a tract is tree-poor enough that planting delivers the
# full marginal benefit reported by Smith et al. (2025).
CANOPY_SPARSE_THRESHOLD_PCT = 15.0

COOL_ROOF = "cool_roof"
TREES = "trees"
SHADE = "shade"

VALID_INTERVENTIONS = (COOL_ROOF, TREES, SHADE)


def recommend_intervention(tract_features: dict) -> str:
    """Return the intervention best suited to one tract's physical profile.

    Parameters
    ----------
    tract_features:
        Mapping that must contain ``impervious_surface_pct`` and
        ``tree_canopy_pct``, both expressed as percentages from 0 to 100.

    Returns
    -------
    One of ``"cool_roof"``, ``"trees"`` or ``"shade"``.

    Raises
    ------
    KeyError
        If either required feature is absent. Guessing a default here would
        silently produce a recommendation a city might act on, so a missing
        input is treated as a hard error rather than filled in.
    ValueError
        If either feature is None, not a number, or outside 0-100.
    """
    impervious = _validated(tract_features, "impervious_surface_pct")
    canopy = _validated(tract_features, "tree_canopy_pct")

    if impervious > IMPERVIOUS_DENSE_THRESHOLD_PCT:
        # Dense and built out: roofs are the available surface.
        return COOL_ROOF
    if canopy < CANOPY_SPARSE_THRESHOLD_PCT:
        # Room to plant and few trees to start with: highest marginal cooling.
        return TREES
    # Mixed fabric with some existing canopy: target the places people wait
    # outdoors rather than re-treating the whole tract.
    return SHADE


def _validated(tract_features: dict, key: str) -> float:
    """Read one percentage feature, failing loudly on bad input."""
    if key not in tract_features:
        raise KeyError(
            f"recommend_intervention requires {key!r}; got keys "
            f"{sorted(tract_features)}"
        )
    value = tract_features[key]
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number from 0 to 100, got {value!r}")
    value = float(value)
    if value != value:  # NaN
        raise ValueError(f"{key} is NaN; a tract with unknown land cover cannot be scored")
    if not 0.0 <= value <= 100.0:
        raise ValueError(f"{key} must be a percentage from 0 to 100, got {value}")
    return value
