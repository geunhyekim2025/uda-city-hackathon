"""Tests for the heat hazard -> risk bridge.

Unit tests run on tiny synthetic tables (fast, no SUEWS); the integration test
runs the present scenario live and is marked slow.

    .venv/bin/python -m pytest tests/test_risk_bridge.py -v
    .venv/bin/python -m pytest tests/test_risk_bridge.py -v -m "not slow"
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import risk_bridge as rb  # noqa: E402


def _fake_results(gridiv_t2: dict[int, float], n_days: int = 20) -> pd.DataFrame:
    """A supy-shaped results frame: each grid held at a constant T2 so the
    dangerous-hours count is deterministic."""
    idx_t = pd.date_range("2024-03-02", periods=n_days * 288, freq="5min")
    frames = []
    for grid, t2 in gridiv_t2.items():
        cols = pd.MultiIndex.from_tuples([("SUEWS", "T2")])
        df = pd.DataFrame(t2, index=idx_t, columns=cols)
        df.index = pd.MultiIndex.from_product([[grid], idx_t])
        frames.append(df)
    return pd.concat(frames)


def test_dangerous_hours_threshold():
    # grid 1 always 40 C (all post-spinup hours dangerous), grid 2 always 30 C (none)
    res = _fake_results({1: 40.0, 2: 30.0}, n_days=20)
    haz = rb.dangerous_heat_hours(res, threshold=35.0, spinup_days=14)
    assert haz[1] == 6 * 24      # 20 days - 14 spin-up = 6 days * 24 h
    assert haz[2] == 0


def test_minmax_flat_series_is_zero():
    s = pd.Series([5.0, 5.0, 5.0])
    assert (rb._minmax(s) == 0.0).all()


def test_vulnerability_ac_is_protective():
    socio = pd.DataFrame({
        "frac_over65": [0.1, 0.1], "frac_under5": [0.1, 0.1],
        "ac_access": [0.9, 0.1],  # grid B has far less AC
        "frac_outdoor_workers": [0.3, 0.3], "deprivation_index": [0.4, 0.4],
    }, index=[1, 2])
    vul = rb.vulnerability_index(socio)
    assert vul[2] > vul[1]  # less AC -> more vulnerable


def test_build_risk_zero_exposure_kills_risk():
    res = _fake_results({1: 40.0, 2: 40.0}, n_days=20)  # equal hazard
    nb = pd.DataFrame({
        "gridiv": [1, 2], "name": ["A", "B"], "type": ["hotspot", "core"],
        "population_day": [0.0, 300.0],  # grid 1 has no daytime population
    })
    socio = pd.DataFrame({
        "gridiv": [1, 2],
        "frac_over65": [0.1, 0.1], "frac_under5": [0.1, 0.1],
        "ac_access": [0.5, 0.5], "frac_outdoor_workers": [0.3, 0.3],
        "deprivation_index": [0.5, 0.5],
    })
    risk = rb.build_risk(res, nb, socio, threshold=35.0, spinup_days=14)
    r1 = risk.set_index("gridiv").loc[1]
    # geometric mean: zero exposure -> zero risk index, ranked last
    assert r1["risk_index"] == 0.0
    assert r1["risk_rank"] == risk["risk_rank"].max()


def test_build_risk_missing_grid_raises():
    res = _fake_results({1: 40.0}, n_days=20)  # only grid 1
    nb = pd.DataFrame({
        "gridiv": [1, 2], "name": ["A", "B"], "type": ["hotspot", "core"],
        "population_day": [200.0, 300.0],
    })
    socio = pd.DataFrame({
        "gridiv": [1, 2],
        "frac_over65": [0.1, 0.1], "frac_under5": [0.1, 0.1],
        "ac_access": [0.5, 0.5], "frac_outdoor_workers": [0.3, 0.3],
        "deprivation_index": [0.5, 0.5],
    })
    with pytest.raises(ValueError, match="no SUEWS hazard"):
        rb.build_risk(res, nb, socio)


@pytest.mark.slow
def test_integration_present_scenario():
    res = rb.run_scenario_live(REPO_ROOT / "uda-city.yml", forcing=None)
    nb = rb.load_neighbourhoods(REPO_ROOT / "neighbourhoods.yml")
    socio = pd.read_csv(REPO_ROOT / "socioeconomic.csv")
    risk = rb.build_risk(res, nb, socio)
    assert len(risk) == 10
    # ranks are 1..10 (ties may skip ranks via method="min", so no perfect
    # permutation is guaranteed); top rank is always 1
    assert risk["risk_rank"].min() == 1
    assert risk["risk_rank"].between(1, 10).all()
    assert risk["risk_index"].between(0, 1).all()
    # hazard must be finite and positive somewhere
    assert risk["dangerous_heat_hours"].sum() > 0
