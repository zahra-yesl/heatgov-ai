"""Unit tests for the intervention recommendation rule.

Run from the project root:

    .venv/Scripts/python.exe -m pytest backend/optimizer/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from optimizer.intervention_rules import (  # noqa: E402
    CANOPY_SPARSE_THRESHOLD_PCT,
    COOL_ROOF,
    IMPERVIOUS_DENSE_THRESHOLD_PCT,
    SHADE,
    TREES,
    recommend_intervention,
)


# --------------------------------------------------------------- the three cases

def test_dense_downtown_tract_gets_cool_roof():
    """Skid Row profile: almost entirely paved, nowhere to plant."""
    tract = {"impervious_surface_pct": 85.0, "tree_canopy_pct": 4.0}
    assert recommend_intervention(tract) == COOL_ROOF


def test_low_canopy_residential_tract_gets_trees():
    """Residential street grid with room to plant and almost no shade."""
    tract = {"impervious_surface_pct": 55.0, "tree_canopy_pct": 10.0}
    assert recommend_intervention(tract) == TREES


def test_mixed_neighbourhood_gets_shade():
    """Echo Park profile: moderate density, canopy already established."""
    tract = {"impervious_surface_pct": 60.0, "tree_canopy_pct": 28.0}
    assert recommend_intervention(tract) == SHADE


# --------------------------------------------------------------- rule precedence

def test_impervious_test_wins_over_low_canopy():
    """A dense tract with no trees still gets cool roofs, not trees.

    This is the whole point of Smith et al. (2025): trees cool more per unit,
    but a fully built-out tract has no ground to put them in.
    """
    tract = {"impervious_surface_pct": 92.0, "tree_canopy_pct": 2.0}
    assert recommend_intervention(tract) == COOL_ROOF


# --------------------------------------------------------------- boundaries

def test_impervious_exactly_at_threshold_is_not_dense():
    """The rule is strictly greater-than, so 80.0 is not yet 'dense'."""
    tract = {"impervious_surface_pct": IMPERVIOUS_DENSE_THRESHOLD_PCT, "tree_canopy_pct": 30.0}
    assert recommend_intervention(tract) == SHADE


def test_impervious_just_above_threshold_is_dense():
    tract = {"impervious_surface_pct": IMPERVIOUS_DENSE_THRESHOLD_PCT + 0.1, "tree_canopy_pct": 30.0}
    assert recommend_intervention(tract) == COOL_ROOF


def test_canopy_exactly_at_threshold_is_not_sparse():
    """The rule is strictly less-than, so 15.0 counts as having some canopy."""
    tract = {"impervious_surface_pct": 50.0, "tree_canopy_pct": CANOPY_SPARSE_THRESHOLD_PCT}
    assert recommend_intervention(tract) == SHADE


def test_canopy_just_below_threshold_is_sparse():
    tract = {"impervious_surface_pct": 50.0, "tree_canopy_pct": CANOPY_SPARSE_THRESHOLD_PCT - 0.1}
    assert recommend_intervention(tract) == TREES


def test_extremes_are_accepted():
    assert recommend_intervention({"impervious_surface_pct": 100.0, "tree_canopy_pct": 0.0}) == COOL_ROOF
    assert recommend_intervention({"impervious_surface_pct": 0.0, "tree_canopy_pct": 0.0}) == TREES
    assert recommend_intervention({"impervious_surface_pct": 0.0, "tree_canopy_pct": 100.0}) == SHADE


# --------------------------------------------------------------- bad input

def test_missing_feature_raises():
    with pytest.raises(KeyError, match="tree_canopy_pct"):
        recommend_intervention({"impervious_surface_pct": 50.0})


def test_none_value_raises():
    with pytest.raises(ValueError, match="must be a number"):
        recommend_intervention({"impervious_surface_pct": None, "tree_canopy_pct": 10.0})


def test_nan_value_raises():
    with pytest.raises(ValueError, match="NaN"):
        recommend_intervention({"impervious_surface_pct": float("nan"), "tree_canopy_pct": 10.0})


def test_out_of_range_raises():
    with pytest.raises(ValueError, match="0 to 100"):
        recommend_intervention({"impervious_surface_pct": 150.0, "tree_canopy_pct": 10.0})
    with pytest.raises(ValueError, match="0 to 100"):
        recommend_intervention({"impervious_surface_pct": -1.0, "tree_canopy_pct": 10.0})


def test_fraction_instead_of_percentage_is_not_silently_accepted():
    """0.85 meaning '85%' would be read as 0.85% and give the wrong answer.

    We cannot detect this in general, so this test documents the contract:
    percentages, not fractions. 0.85 is a legal (if unusual) 0.85%.
    """
    tract = {"impervious_surface_pct": 0.85, "tree_canopy_pct": 0.04}
    assert recommend_intervention(tract) == TREES  # NOT cool_roof
