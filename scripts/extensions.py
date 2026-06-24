#!/usr/bin/env python
"""Novel extensions to the UDA-city heat-risk analysis.

Adds four things the core bridge does not do, all reproducible:

  1. Day vs night risk  - splits the hazard into daytime (06-18 h) and night
     (18-06 h) wet-bulb danger, and pairs each with the matching daytime /
     nighttime population (UNDRR exposure is time-of-day specific).
  2. Person-hours of dangerous heat - dangerous hours x exposed population
     density. An ABSOLUTE, transferable metric (no min-max), which is immune to
     the relative-scaling weakness of the index.
  3. Intervention decomposition - cool-roof-only vs greening-only vs combined,
     plus a greening dose (1x, 2x) under the +2.5 K future.
  4. Robustness - risk ranking under thresholds 34/35/36 C, vulnerability-weight
     leave-one-out, and a 'dangerous hot nights' (consecutive) metric.

    .venv/bin/python scripts/extensions.py

Writes outputs/derived/ext_*.csv and docs/figs/fig8..11.png.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from supy.suews_sim import SUEWSSimulation
import risk_bridge as rb

DERIVED = ROOT / "outputs" / "derived"; DERIVED.mkdir(parents=True, exist_ok=True)
SUEWS = ROOT / "outputs" / "suews"; SUEWS.mkdir(parents=True, exist_ok=True)
FIGS = ROOT / "docs" / "figs"
SPIN = rb.DEFAULT_SPINUP_DAYS
FUTURE = "forcing/future_hot_humid/UDA_2024_data_60.txt"
BLUE, VERM, GREEN, ORANGE, SKY, GREY = ("#0072B2", "#D55E00", "#009E73", "#E69F00", "#56B4E9", "#6c757d")
plt.rcParams.update({"font.size": 12, "axes.titlesize": 13.5, "axes.titleweight": "bold",
                     "figure.dpi": 130, "savefig.bbox": "tight",
                     "axes.spines.top": False, "axes.spines.right": False})


def wet_bulb(T, RH):
    return (T * np.arctan(0.151977 * np.sqrt(RH + 8.313659)) + np.arctan(T + RH)
            - np.arctan(RH - 1.676331)
            + 0.00391838 * RH ** 1.5 * np.arctan(0.023101 * RH) - 4.686035)


def run_cached(config, tag, forcing=None):
    """Run a config (or load a cached parquet) and return the results frame."""
    pq = SUEWS / f"{tag}.parquet"
    if pq.exists():
        return pd.read_parquet(pq)
    sim = SUEWSSimulation(str(ROOT / config))
    if forcing:
        sim.update_forcing(str(ROOT / forcing))
    sim.run()
    sim.results.to_parquet(pq)
    return sim.results


def _minmax(s):
    lo, hi = s.min(), s.max()
    return pd.Series(0.0, index=s.index) if hi <= lo else (s - lo) / (hi - lo)


def main():
    neigh = rb.load_neighbourhoods(ROOT / "neighbourhoods.yml")
    socio = pd.read_csv(ROOT / "socioeconomic.csv")
    # population: day already in loader; add night
    nraw = __import__("yaml").safe_load((ROOT / "neighbourhoods.yml").read_text())["neighbourhoods"]
    pop = pd.DataFrame([{"gridiv": n["gridiv"],
                         "pop_day": n["population_density_per_ha"]["day"],
                         "pop_night": n["population_density_per_ha"]["night"]} for n in nraw]).set_index("gridiv")
    meta = neigh.set_index("gridiv")[["name", "type"]]

    print("running scenarios (cached after first run) ...")
    res_p = run_cached("uda-city.yml", "present_full")
    grids = res_p.index.get_level_values(0).unique()

    # ---------- 1 & 2: day/night wet-bulb hazard, exposure, person-hours ----------
    rows = {}
    for g in grids:
        d = res_p.loc[g]["SUEWS"]
        wb = wet_bulb(d["T2"], d["RH2"]).iloc[SPIN * 288:]
        hourly = wb.resample("h").mean()
        is_day = (hourly.index.hour >= 6) & (hourly.index.hour < 18)
        day_hrs = int(((hourly > 28) & is_day).sum())
        night_hrs = int(((hourly > 28) & ~is_day).sum())
        # dangerous hot nights: nights whose night-min T2 stays > 28 C (no recovery)
        t2 = d["T2"].iloc[SPIN * 288:]
        nightly_min = t2[(t2.index.hour >= 18) | (t2.index.hour < 6)].resample("D").min().dropna()
        hot = (nightly_min > 28).astype(int).values
        run = mx = 0
        for v in hot:
            run = run + 1 if v else 0
            mx = max(mx, run)
        rows[g] = dict(day_hrs=day_hrs, night_hrs=night_hrs,
                       hot_nights=int(hot.sum()), max_consec_hot_nights=int(mx))
    DN = meta.join(pd.DataFrame(rows).T).join(pop)
    # person-hours per hectare (absolute, transferable)
    DN["ph_day"] = DN.day_hrs * DN.pop_day
    DN["ph_night"] = DN.night_hrs * DN.pop_night
    DN["ph_total"] = DN.ph_day + DN.ph_night
    # time-resolved risk: day uses pop_day, night uses pop_night
    vuln = rb.vulnerability_index(socio.set_index("gridiv"))
    def tod_risk(hrs, popcol):
        pil = pd.DataFrame({"h": _minmax(hrs), "e": _minmax(DN[popcol].astype(float)), "v": vuln}).clip(lower=0)
        return _minmax((pil.prod(axis=1)) ** (1 / 3))
    DN["risk_day"] = tod_risk(DN.day_hrs, "pop_day")
    DN["risk_night"] = tod_risk(DN.night_hrs, "pop_night")
    DN["rank_day"] = DN.risk_day.rank(ascending=False, method="min").astype(int)
    DN["rank_night"] = DN.risk_night.rank(ascending=False, method="min").astype(int)
    DN.reset_index().to_csv(DERIVED / "ext_day_night.csv", index=False)
    print("  day/night + person-hours ->", (DERIVED / "ext_day_night.csv").name)

    # ---------- 3: intervention decomposition + greening dose under future ----------
    def dry_hrs(res):
        return rb.build_risk(res, neigh, socio).set_index("gridiv")["dangerous_heat_hours"]
    decomp = pd.DataFrame({
        "baseline": dry_hrs(res_p),
        "roof_only": dry_hrs(run_cached("uda-city-roofonly.yml", "roofonly_present")),
        "green_only": dry_hrs(run_cached("uda-city-greenonly.yml", "greenonly_present")),
        "combined": dry_hrs(run_cached("uda-city-intervention.yml", "intervention_full")),
    }).loc[[4, 5, 9]]
    decomp.insert(0, "name", meta.loc[[4, 5, 9], "name"])
    decomp.to_csv(DERIVED / "ext_decomposition.csv")
    print("  decomposition ->", (DERIVED / "ext_decomposition.csv").name)

    dose = pd.DataFrame({
        "present": dry_hrs(res_p),
        "future_noaction": dry_hrs(run_cached("uda-city.yml", "future_full", FUTURE)),
        "future_green1x": dry_hrs(run_cached("uda-city-greenonly.yml", "greenonly_future", FUTURE)),
        "future_green2x": dry_hrs(run_cached("uda-city-green2x.yml", "green2x_future", FUTURE)),
        "future_combined": dry_hrs(run_cached("uda-city-intervention.yml", "intervention_future", FUTURE)),
    }).loc[[4, 5, 9]]
    dose.insert(0, "name", meta.loc[[4, 5, 9], "name"])
    dose.to_csv(DERIVED / "ext_greening_dose.csv")
    print("  greening dose ->", (DERIVED / "ext_greening_dose.csv").name)

    # ---------- 4: robustness (threshold band + weight leave-one-out) ----------
    P = rb.build_risk(res_p, neigh, socio).set_index("gridiv")
    band = {}
    for thr in (34.0, 35.0, 36.0):
        band[f"rank@{thr:.0f}"] = rb.build_risk(res_p, neigh, socio, threshold=thr).set_index("gridiv")["risk_rank"]
    BAND = meta.join(pd.DataFrame(band))
    # vulnerability weight leave-one-out: drop each proxy, recompute risk rank
    comps = ["frac_over65", "frac_under5", "ac_access", "frac_outdoor_workers", "deprivation_index"]
    s_i = socio.set_index("gridiv")
    loo = {}
    base_haz = _minmax(P["dangerous_heat_hours"]); base_exp = _minmax(pop["pop_day"].astype(float))
    for drop in comps:
        keep = [c for c in comps if c != drop]
        v = pd.DataFrame({c: (1 - s_i[c] if c == "ac_access" else s_i[c]) for c in keep}).mean(axis=1)
        v = _minmax(v)
        ri = _minmax((pd.DataFrame({"h": base_haz, "e": base_exp, "v": v}).clip(lower=0).prod(axis=1)) ** (1 / 3))
        loo[f"drop_{drop}"] = ri.rank(ascending=False, method="min").astype(int)
    LOO = meta.join(pd.DataFrame(loo))
    BAND.join(LOO.drop(columns=["name", "type"])).reset_index().to_csv(DERIVED / "ext_robustness.csv", index=False)
    print("  robustness ->", (DERIVED / "ext_robustness.csv").name)

    _figures(DN.reset_index(), decomp.reset_index(), dose.reset_index(), BAND.reset_index())
    # console summary
    print("\nDay vs night top-3 risk:")
    print("  day  :", list(DN.sort_values('rank_day').name[:3]))
    print("  night:", list(DN.sort_values('rank_night').name[:3]))
    print("Person-hours (per ha) leader:", DN.sort_values('ph_total', ascending=False).name.iloc[0])


def _figures(DN, decomp, dose, band):
    # FIG 8 - dangerous humid heat is a daytime problem; population flips by clock
    D = DN.sort_values("day_hrs", ascending=False); x = np.arange(len(D)); w = 0.4
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11.5, 5), gridspec_kw={"width_ratios": [1.5, 1]})
    ax.bar(x - w / 2, D.day_hrs, w, label="Daytime (06-18 h)", color=ORANGE)
    ax.bar(x + w / 2, D.night_hrs, w, label="Nighttime (18-06 h)", color=BLUE)
    ax.set_xticks(x); ax.set_xticklabels(D.name, rotation=42, ha="right", fontsize=8.5)
    ax.set_ylabel("dangerous humid-heat hours (wet-bulb > 28 C)")
    ax.set_title("Dangerous humid heat is a daytime problem")
    ax.legend(frameon=False); ax.grid(alpha=.25, axis="y")
    # who is home, by type (day vs night population)
    typ = DN.drop_duplicates("type").set_index("type")[["pop_day", "pop_night"]].loc[["refuge", "core", "hotspot"]]
    xt = np.arange(len(typ))
    ax2.bar(xt - w / 2, typ.pop_day, w, label="Daytime pop.", color="#9aa7b2")
    ax2.bar(xt + w / 2, typ.pop_night, w, label="Nighttime pop.", color="#33475b")
    for xi, t in enumerate(typ.index):
        d, n = typ.loc[t]; arr = "↑" if n > d else ("↓" if n < d else "=")
        ax2.text(xi, max(d, n) + 12, arr, ha="center", fontsize=14, fontweight="bold",
                 color=(VERM if n > d else (BLUE if n < d else "#888")))
    ax2.set_xticks(xt); ax2.set_xticklabels(typ.index, fontsize=10)
    ax2.set_ylabel("people per hectare")
    ax2.set_title("Who is home shifts by the clock")
    ax2.legend(frameon=False, fontsize=9); ax2.grid(alpha=.25, axis="y")
    fig.suptitle("")
    fig.savefig(FIGS / "fig8_day_night.png"); plt.close(fig)

    # FIG 9 - person-hours (absolute, transferable) coloured by type
    TCOL = {"refuge": BLUE, "core": GREY, "hotspot": VERM}
    D2 = DN.sort_values("ph_total", ascending=False); x = np.arange(len(D2))
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x, D2.ph_total / 1000, color=[TCOL[t] for t in D2.type])
    ax.set_xticks(x); ax.set_xticklabels(D2.name, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("dangerous person-hours per hectare (thousands)")
    ax.set_title("Person-hours of dangerous heat - absolute, transferable (no min-max)")
    from matplotlib.patches import Patch
    h = [Patch(facecolor=TCOL[t], edgecolor="#333", linewidth=.4, label=t.capitalize())
         for t in ("refuge", "core", "hotspot")]
    leg = ax.legend(handles=h, loc="upper right", frameon=True, fontsize=9.5)
    leg.get_frame().set_edgecolor("#9aa3ab"); leg.get_frame().set_linewidth(1.0)
    ax.grid(alpha=.25, axis="y")
    fig.savefig(FIGS / "fig9_person_hours.png"); plt.close(fig)

    # FIG 10 - intervention decomposition
    x = np.arange(len(decomp)); w = 0.2
    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.bar(x - 1.5 * w, decomp.baseline, w, label="Baseline", color=GREY)
    ax.bar(x - 0.5 * w, decomp.roof_only, w, label="Cool-roof only", color=SKY)
    ax.bar(x + 0.5 * w, decomp.green_only, w, label="Greening only", color=GREEN)
    ax.bar(x + 1.5 * w, decomp.combined, w, label="Combined", color=BLUE)
    ax.set_xticks(x); ax.set_xticklabels(decomp.name, fontsize=11)
    ax.set_ylabel("dangerous-heat hours (T2 > 35 C)")
    ax.set_title("Which lever cools more? Cool roofs do most of the work")
    ax.legend(frameon=False, fontsize=9.5); ax.grid(alpha=.25, axis="y")
    fig.savefig(FIGS / "fig10_decomposition.png"); plt.close(fig)

    # FIG 11 - greening dose under future (can you green your way out of +2.5 C?)
    x = np.arange(len(dose)); w = 0.15
    fig, ax = plt.subplots(figsize=(9, 5))
    cols = [("present", "Present", SKY), ("future_noaction", "+2.5C no action", VERM),
            ("future_green1x", "+2.5C green 1x", "#7bbf8a"),
            ("future_green2x", "+2.5C green 2x", GREEN),
            ("future_combined", "+2.5C roof+green", BLUE)]
    for i, (c, lab, col) in enumerate(cols):
        ax.bar(x + (i - 2) * w, dose[c], w, label=lab, color=col)
    ax.set_xticks(x); ax.set_xticklabels(dose.name, fontsize=11)
    ax.set_ylabel("dangerous-heat hours (T2 > 35 C)")
    ax.set_title("You cannot green your way out of +2.5 C (none reach 'present')")
    ax.legend(frameon=False, fontsize=8.5, ncol=2); ax.grid(alpha=.25, axis="y")
    fig.savefig(FIGS / "fig11_greening_dose.png"); plt.close(fig)


if __name__ == "__main__":
    main()
