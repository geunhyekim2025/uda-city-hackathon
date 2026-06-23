#!/usr/bin/env python
"""Heat hazard -> socio-economic heat-risk bridge for UDA-city (#5, #6).

This is the documented, runnable bridge the hackathon package provides. It
takes SUEWS output (per-neighbourhood near-surface air temperature) plus the
synthetic socio-economic sidecar (socioeconomic.csv) and produces a
per-neighbourhood heat-RISK indicator, following the UNDRR-style decomposition

    risk = hazard x exposure x vulnerability

(each normalised to [0, 1], combined as a geometric mean so a near-zero in any
single component pulls the risk down — a deliberately conservative framing).

It is a REFERENCE, not the answer participants must copy: thresholds, weights,
and the combination rule are all surfaced as arguments precisely so teams can
justify their own choices (judging criterion: honest bridging).

Read risk_bridge.md for the conceptual framing, assumptions, and the caveats
that MUST travel with any output.

CLI:
    .venv/bin/python risk_bridge.py \
        --results outputs/suews/present.parquet \
        --threshold 35 --spinup-days 14 \
        --out outputs/derived/risk_present.csv

When --results is omitted it runs the present scenario from uda-city.yml live.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_THRESHOLD = 35.0   # deg C on 2 m air temperature (illustrative; justify your own)
DEFAULT_SPINUP_DAYS = 14   # discard model spin-up before computing the hazard


# --------------------------------------------------------------------------- #
# Hazard: dangerous-heat hours per neighbourhood from SUEWS T2
# --------------------------------------------------------------------------- #
def dangerous_heat_hours(results: pd.DataFrame, threshold: float,
                         spinup_days: int) -> pd.Series:
    """Hours per grid with hourly-mean T2 above `threshold`, after spin-up.

    `results` is a supy results frame: MultiIndex (grid, time) rows, MultiIndex
    (group, var) columns. Returns a Series indexed by gridiv.
    """
    out = {}
    for grid in results.index.get_level_values(0).unique():
        t2 = results.loc[grid][("SUEWS", "T2")].dropna()
        t2 = t2.iloc[spinup_days * 288:]               # 5-min steps -> 288/day
        hourly = t2.resample("h").mean()
        out[grid] = int((hourly > threshold).sum())
    return pd.Series(out, name="dangerous_heat_hours").sort_index()


def _minmax(s: pd.Series) -> pd.Series:
    """Scale to [0, 1]; a flat series maps to all-zeros (no spread, no signal)."""
    lo, hi = s.min(), s.max()
    if hi <= lo:
        return pd.Series(0.0, index=s.index)
    return (s - lo) / (hi - lo)


# --------------------------------------------------------------------------- #
# Vulnerability: combine socio-economic proxies into a [0, 1] index
# --------------------------------------------------------------------------- #
def vulnerability_index(socio: pd.DataFrame) -> pd.Series:
    """Equal-weight mean of five proxies, each oriented so higher = more
    vulnerable, then min-max scaled. AC access is protective, so it enters as
    (1 - ac_access)."""
    components = pd.DataFrame({
        "elderly": socio["frac_over65"],
        "young": socio["frac_under5"],
        "no_ac": 1.0 - socio["ac_access"],
        "outdoor_work": socio["frac_outdoor_workers"],
        "deprivation": socio["deprivation_index"],
    }, index=socio.index)
    raw = components.mean(axis=1)
    return _minmax(raw).rename("vulnerability")


# --------------------------------------------------------------------------- #
# Bridge
# --------------------------------------------------------------------------- #
def build_risk(results: pd.DataFrame, neighbourhoods: pd.DataFrame,
               socio: pd.DataFrame, threshold: float = DEFAULT_THRESHOLD,
               spinup_days: int = DEFAULT_SPINUP_DAYS) -> pd.DataFrame:
    """Join hazard, exposure and vulnerability on gridiv and return a ranked
    per-neighbourhood risk table."""
    for name, frame in (("neighbourhoods", neighbourhoods), ("socio", socio)):
        missing = {"gridiv"} - set(frame.columns)
        if missing:
            raise ValueError(f"{name} table missing required column(s): {missing}")

    haz = dangerous_heat_hours(results, threshold, spinup_days)
    df = neighbourhoods.set_index("gridiv").copy()
    df["dangerous_heat_hours"] = haz
    if df["dangerous_heat_hours"].isna().any():
        bad = df.index[df["dangerous_heat_hours"].isna()].tolist()
        raise ValueError(f"no SUEWS hazard for gridiv {bad} — results/config mismatch")

    socio_i = socio.set_index("gridiv")
    df["hazard"] = _minmax(df["dangerous_heat_hours"])
    df["exposure"] = _minmax(df["population_day"].astype(float))
    df["vulnerability"] = vulnerability_index(socio_i)

    # Geometric mean of the three pillars: a near-zero pillar (e.g. no exposed
    # population) keeps risk low even under extreme hazard. This is a choice —
    # an arithmetic mean would let one high pillar dominate; teams may justify
    # either (see risk_bridge.md).
    pillars = df[["hazard", "exposure", "vulnerability"]].clip(lower=0)
    df["risk_index"] = (pillars.prod(axis=1)) ** (1.0 / 3.0)
    df["risk_index"] = _minmax(df["risk_index"])
    df["risk_rank"] = df["risk_index"].rank(ascending=False, method="min").astype(int)

    cols = ["name", "type", "dangerous_heat_hours", "population_day",
            "hazard", "exposure", "vulnerability", "risk_index", "risk_rank"]
    return df.reset_index()[["gridiv"] + cols].sort_values("risk_rank")


def load_neighbourhoods(path: Path) -> pd.DataFrame:
    data = yaml.safe_load(path.read_text())["neighbourhoods"]
    return pd.DataFrame([{
        "gridiv": n["gridiv"], "name": n["name"], "type": n["type"],
        "population_day": n["population_density_per_ha"]["day"],
    } for n in data])


def run_scenario_live(config: Path, forcing: str | None) -> pd.DataFrame:
    import warnings
    warnings.simplefilter("ignore")
    from supy.suews_sim import SUEWSSimulation
    sim = SUEWSSimulation(str(config))
    if forcing:
        sim.update_forcing(forcing)
    sim.run()
    return sim.results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", type=Path,
                    help="parquet of a supy results frame; omit to run the "
                         "scenario live from --config/--forcing")
    ap.add_argument("--config", type=Path, default=REPO_ROOT / "uda-city.yml")
    ap.add_argument("--forcing", type=str, default=None,
                    help="forcing file for a live run (default: config's own)")
    ap.add_argument("--neighbourhoods", type=Path,
                    default=REPO_ROOT / "neighbourhoods.yml")
    ap.add_argument("--socio", type=Path, default=REPO_ROOT / "socioeconomic.csv")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--spinup-days", type=int, default=DEFAULT_SPINUP_DAYS)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if args.results:
        # parquet only — avoid pickle's arbitrary-code-execution risk on a
        # results file that may have come from another participant's run.
        results = pd.read_parquet(args.results)
    else:
        results = run_scenario_live(args.config, args.forcing)

    neighbourhoods = load_neighbourhoods(args.neighbourhoods)
    socio = pd.read_csv(args.socio)
    risk = build_risk(results, neighbourhoods, socio,
                      threshold=args.threshold, spinup_days=args.spinup_days)

    pd.set_option("display.width", 140)
    print(risk.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        risk.to_csv(args.out, index=False)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
