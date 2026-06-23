#!/usr/bin/env python
"""Smoke test: load the canonical UDA-city, run a short window, check outputs.

The canonical `uda-city.yml` is now directly laptop-runnable — NARP radiation
+ classic OHM storage heat baked onto disk (no SPARTACUS, no runtime swap), and
its `model.control.forcing` points at the present hot-humid scenario. So this
smoke loads the config and its own forcing as-is.

Beyond "did it complete", this asserts the surface energy balance actually
closed: T2 (2 m air temperature) and QH (sensible heat) must be finite for
every grid. That guards against the silent failure mode where a run completes
but storage heat blows up to NaN and poisons the diagnostics.

    .venv/bin/python scripts/smoke_test.py                 # 7-day window
    .venv/bin/python scripts/smoke_test.py --full          # whole forcing file
    .venv/bin/python scripts/smoke_test.py path/to/city.yml

Exits 0 on success, non-zero on failure.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.simplefilter("ignore")

from supy.suews_sim import SUEWSSimulation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "uda-city.yml"
WINDOW_STEPS = 2016  # 7 days at 5-minute step (7 * 24 * 12)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--full"]
    full = "--full" in argv
    config_path = Path(args[0]).resolve() if args else DEFAULT_CONFIG
    if not config_path.is_file():
        print(f"FAIL: config not found: {config_path}", file=sys.stderr)
        return 2

    sim = SUEWSSimulation(str(config_path))
    fdf = sim.forcing.df
    if not full:
        fdf = fdf.head(WINDOW_STEPS)
        sim.update_forcing(fdf)
    sim.run()

    if not sim.is_complete:
        print("FAIL: simulation did not reach completion", file=sys.stderr)
        return 1

    # Surface energy balance must close: T2 and QH finite for every grid.
    res = sim.results
    bad = []
    for grid in res.index.get_level_values(0).unique():
        g = res.loc[grid]["SUEWS"]
        for col in ("T2", "QH"):
            if g[col].isna().any():
                bad.append(f"grid {grid} {col}")
    if bad:
        print(f"FAIL: non-finite diagnostics: {', '.join(bad)}", file=sys.stderr)
        return 1

    import supy
    n_sites = len(res.index.get_level_values(0).unique())
    g1 = res.loc[res.index.get_level_values(0)[0]]["SUEWS"]
    print(
        f"OK: {n_sites} site(s) x {len(fdf):,} steps ({len(fdf)//288} days) "
        f"under supy {supy.__version__}; NARP+OHM on disk; "
        f"T2 {g1['T2'].min():.1f}..{g1['T2'].max():.1f} C; "
        f"config: {config_path.relative_to(REPO_ROOT)}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
