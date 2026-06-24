#!/usr/bin/env python
"""Reproduce the UDA-city heat-risk analysis and all GitHub Pages figures.

One entry point for the whole submission. It runs SUEWS (present, +2.5 K future,
and the cool-roof + greening intervention), computes the risk tables, and writes
every figure used on the site. Deterministic — same inputs reproduce the same
numbers and figures.

    .venv/bin/python scripts/reproduce.py

Inputs (in the repo):   uda-city.yml, uda-city-intervention.yml,
                        forcing/{present,future}_hot_humid/UDA_2024_data_60.txt,
                        neighbourhoods.yml, socioeconomic.csv, risk_bridge.py
Outputs:                outputs/derived/*.csv  and  docs/figs/fig1..6.png

Hazard = hours with hourly-mean T2 > 35 C after a 14-day spin-up (risk_bridge
defaults). Humid variant = wet-bulb (Stull 2011) > 28 C from the model's own
T2 + RH2. Risk = UNDRR hazard x exposure x vulnerability, min-max scaled and
combined as a geometric mean (risk_bridge.build_risk). SUEWS: NARP + classic OHM.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.simplefilter("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root for risk_bridge

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm, colors
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from supy.suews_sim import SUEWSSimulation
import risk_bridge as rb  # the hackathon's reference bridge — used verbatim

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "outputs" / "derived"
FIGS = ROOT / "docs" / "figs"
SPIN = rb.DEFAULT_SPINUP_DAYS  # 14 days
DERIVED.mkdir(parents=True, exist_ok=True)
FIGS.mkdir(parents=True, exist_ok=True)

# --- Okabe-Ito colour-blind-safe palette + cividis sequential ramp ---
BLUE, VERM, GREEN, ORANGE, SKY, GREY = (
    "#0072B2", "#D55E00", "#009E73", "#E69F00", "#56B4E9", "#6c757d")
TCOL = {"refuge": BLUE, "core": GREY, "hotspot": VERM}
RISK_CMAP = plt.get_cmap("cividis")
plt.rcParams.update({"font.size": 12, "axes.titlesize": 14, "axes.titleweight": "bold",
                     "figure.dpi": 130, "savefig.bbox": "tight",
                     "axes.spines.top": False, "axes.spines.right": False})


# --------------------------------------------------------------------------- #
# Humid-heat metrics (from the model's self-consistent 2 m state)
# --------------------------------------------------------------------------- #
def wet_bulb(T, RH):  # Stull (2011) empirical wet-bulb, deg C
    return (T * np.arctan(0.151977 * np.sqrt(RH + 8.313659)) + np.arctan(T + RH)
            - np.arctan(RH - 1.676331)
            + 0.00391838 * RH ** 1.5 * np.arctan(0.023101 * RH) - 4.686035)


def hours_over(series, thr):
    s = series.iloc[SPIN * 288:]
    return int((s.resample("h").mean() > thr).sum())


def run(config, forcing=None):
    sim = SUEWSSimulation(str(ROOT / config))
    if forcing:
        sim.update_forcing(str(ROOT / forcing))
    sim.run()
    return sim.results


def main():
    neigh = rb.load_neighbourhoods(ROOT / "neighbourhoods.yml")
    socio = pd.read_csv(ROOT / "socioeconomic.csv")

    print("[1/4] present scenario ...")
    res_p = run("uda-city.yml")
    print("[2/4] +2.5 K future scenario ...")
    res_f = run("uda-city.yml", "forcing/future_hot_humid/UDA_2024_data_60.txt")
    print("[3/4] cool-roof + greening intervention (present) ...")
    res_i = run("uda-city-intervention.yml")
    print("[4/4] intervention under +2.5 K future ...")
    res_if = run("uda-city-intervention.yml", "forcing/future_hot_humid/UDA_2024_data_60.txt")

    P = rb.build_risk(res_p, neigh, socio).set_index("gridiv")
    F = rb.build_risk(res_f, neigh, socio).set_index("gridiv")
    I = rb.build_risk(res_i, neigh, socio).set_index("gridiv")

    # present table
    P.reset_index().to_csv(DERIVED / "risk_present.csv", index=False)

    # future vs present
    fut = P[["name", "type"]].copy()
    fut["dry_hrs_pres"] = P["dangerous_heat_hours"]
    fut["dry_hrs_fut"] = F["dangerous_heat_hours"]
    fut["risk_pres"], fut["rank_pres"] = P["risk_index"], P["risk_rank"]
    fut["risk_fut"], fut["rank_fut"] = F["risk_index"], F["risk_rank"]
    fut.to_csv(DERIVED / "risk_future_vs_present.csv")

    # humid metrics (present)
    rows = {}
    for g in res_p.index.get_level_values(0).unique():
        d = res_p.loc[g]["SUEWS"]
        rows[g] = dict(dry_hrs=hours_over(d["T2"], 35.0),
                       WBT28_hrs=hours_over(wet_bulb(d["T2"], d["RH2"]), 28.0))
    H = neigh.set_index("gridiv")[["name", "type"]].join(pd.DataFrame(rows).T)
    H.to_csv(DERIVED / "risk_present_humid.csv")

    # intervention vs baseline
    iv = P[["name", "type"]].copy()
    iv["hrs_base"], iv["hrs_intv"] = P["dangerous_heat_hours"], I["dangerous_heat_hours"]
    iv["risk_base"], iv["risk_intv"] = P["risk_index"], I["risk_index"]
    iv["rank_base"], iv["rank_intv"] = P["risk_rank"], I["risk_rank"]
    iv.reset_index().to_csv(DERIVED / "risk_intervention_vs_baseline.csv", index=False)

    # intervention under future: does cooling offset +2.5 K? (treated grids 4/5/9)
    IFh = rb.build_risk(res_if, neigh, socio).set_index("gridiv")["dangerous_heat_hours"]
    treated = [4, 5, 9]
    off = pd.DataFrame({"name": P["name"], "present_base": P["dangerous_heat_hours"],
                        "future_base": F["dangerous_heat_hours"], "future_intv": IFh}).loc[treated]
    off["warming_add"] = off.future_base - off.present_base
    off["intv_cut_future"] = off.future_base - off.future_intv
    off["offset_pct"] = (off.intv_cut_future / off.warming_add * 100).round(0)
    off.reset_index().to_csv(DERIVED / "intervention_under_future.csv", index=False)

    print(f"    present dangerous-hours total: {int(P['dangerous_heat_hours'].sum())}; "
          f"future: {int(F['dangerous_heat_hours'].sum())}; "
          f"future+action offsets {off.offset_pct.min():.0f}-{off.offset_pct.max():.0f}% of warming")
    _figures(P.reset_index(), fut.reset_index(), H.reset_index(), iv.reset_index())
    _fig7(off.reset_index())
    print(f"done -> {DERIVED}/*.csv and {FIGS}/fig1..6.png")


# --------------------------------------------------------------------------- #
def _figures(P, F, H, I):
    # FIG 1 — hottest != highest-risk (leader-line labels; no point/label overlap)
    Pi = P.set_index("name")
    pos = {n: [Pi.loc[n, "dangerous_heat_hours"], Pi.loc[n, "risk_index"]] for n in Pi.index}
    pos["Lusitano Square"][0] = 3.2   # nudge the two tied (5 h) cores apart so circles separate
    pos["Victoria Exchange"][0] = 7.0
    fig, ax = plt.subplots(figsize=(9.4, 6.2))
    for n, (x, y) in pos.items():
        ax.scatter(x, y, s=150, color=TCOL[Pi.loc[n, "type"]], edgecolor="k", lw=0.8, zorder=3)
    lab = {"Kampong Lama": (45, 1.00, "left", False), "Dhobi Lines": (28.5, 0.85, "left", False),
           "Fuzhou Lanes": (13.5, 0.86, "left", True), "Mlima Moto": (7.5, 0.44, "left", False),
           "Lusitano Square": (1.0, 0.30, "left", True), "Victoria Exchange": (9.8, 0.155, "left", True),
           "Zheng He Towers": (3.6, 0.02, "left", True), "Serendib Rise": (27.5, 0.035, "left", False),
           "Taman Melati": (48.5, 0.035, "left", False), "Jade Gardens": (62, 0.075, "center", False)}
    for n, (lx, ly, ha, lead) in lab.items():
        x, y = pos[n]
        if lead:
            ax.annotate(n, (x, y), xytext=(lx, ly), fontsize=9, ha=ha, va="center",
                        arrowprops=dict(arrowstyle="-", color="#9aa3ab", lw=0.8, shrinkA=2, shrinkB=4))
        else:
            ax.text(lx, ly, n, fontsize=9, ha=ha, va="center")
    # labels follow the dataset's own neighbourhoods.yml 'type_description' field
    handles = [Line2D([], [], marker="o", color="w", markerfacecolor=BLUE, markeredgecolor="k",
                      markersize=9, label="Refuge - greener, low-density edge"),
               Line2D([], [], marker="o", color="w", markerfacecolor=GREY, markeredgecolor="k",
                      markersize=9, label="Core - formal mid/high-rise centre"),
               Line2D([], [], marker="o", color="w", markerfacecolor=VERM, markeredgecolor="k",
                      markersize=9, label="Hotspot - dense low-rise informal settlement")]
    leg = ax.legend(handles=handles, title="Neighbourhood type", loc="center right",
                    bbox_to_anchor=(1.0, 0.55), frameon=True, fontsize=8.6, title_fontsize=9.5)
    leg.get_frame().set_edgecolor("#9aa3ab"); leg.get_frame().set_linewidth(1.0)
    leg.get_title().set_fontweight("bold")
    ax.annotate("HIGHEST RISK\n(only 3rd hottest)", (42, 1.0), xytext=(49, 0.85), fontsize=10,
                color=VERM, fontweight="bold", ha="center",
                arrowprops=dict(arrowstyle="->", color=VERM, shrinkB=6))
    ax.annotate("HOTTEST\n(lowest risk)", (62, 0.0), xytext=(53, 0.20), fontsize=10, color=BLUE,
                fontweight="bold", ha="center", arrowprops=dict(arrowstyle="->", color=BLUE, shrinkB=6))
    ax.set_xlim(-3, 76); ax.set_ylim(-0.05, 1.10)
    ax.set_xlabel("Heat hazard  ->  hours of dangerous heat (air above 35 C)")
    ax.set_ylabel("Heat RISK to people  (risk index, 0-1)")
    ax.set_title("Where it's hottest is not where heat is most dangerous")
    ax.grid(alpha=.25)
    fig.savefig(FIGS / "fig1_hottest_vs_risk.png"); plt.close(fig)

    # FIG 2 — pillars (CB-safe distinct trio; legend outside; dataset-faithful labels)
    Ps = P.sort_values("risk_index"); y = np.arange(len(Ps)); h = 0.26
    fig, ax = plt.subplots(figsize=(10.6, 5.6))
    ax.barh(y + h, Ps.hazard, h, label="Hazard - dangerous-heat hours", color=VERM)
    ax.barh(y, Ps.exposure, h, label="Exposure - daytime population", color=GREEN)
    ax.barh(y - h, Ps.vulnerability, h, label="Vulnerability - ability to cope", color=BLUE)
    ax.set_yticks(y); ax.set_yticklabels(Ps.name)
    ax.set_xlabel("pillar score (0-1, scaled across the 10 neighbourhoods)")
    ax.set_title("Risk = Hazard x Exposure x Vulnerability")
    leg = ax.legend(title="The three pillars of risk", loc="center left", bbox_to_anchor=(1.01, 0.5),
                    frameon=True, fontsize=9, title_fontsize=9.5)
    leg.get_frame().set_edgecolor("#9aa3ab"); leg.get_title().set_fontweight("bold")
    ax.grid(alpha=.25, axis="x")
    fig.savefig(FIGS / "fig2_pillars.png"); plt.close(fig)

    # FIG 3 — present vs future
    Fs = F.sort_values("dry_hrs_fut", ascending=False); x = np.arange(len(Fs)); w = 0.4
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - w / 2, Fs.dry_hrs_pres, w, label="Present", color=SKY)
    ax.bar(x + w / 2, Fs.dry_hrs_fut, w, label="Future (+2.5 C)", color=VERM)
    ax.set_xticks(x); ax.set_xticklabels(Fs.name, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("dangerous-heat hours (T2 > 35 C)")
    ax.set_title("+2.5 C warming multiplies dangerous heat x7.7 - everywhere")
    ax.legend(frameon=False); ax.grid(alpha=.25, axis="y")
    fig.savefig(FIGS / "fig3_future.png"); plt.close(fig)

    # FIG 4 — intervention
    It = I[I.name.isin(["Kampong Lama", "Dhobi Lines", "Fuzhou Lanes"])]
    x = np.arange(len(It)); w = 0.4
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - w / 2, It.hrs_base, w, label="Baseline", color=VERM)
    ax.bar(x + w / 2, It.hrs_intv, w, label="Cool-roof + greening", color=BLUE)
    for xi, (hb, hi) in enumerate(zip(It.hrs_base, It.hrs_intv)):
        ax.text(xi + w / 2, hi + 0.6, f"-{(hb - hi) / hb * 100:.0f}%", ha="center",
                fontsize=10, color=BLUE, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(It.name, fontsize=11)
    ax.set_ylabel("dangerous-heat hours (T2 > 35 C)")
    ax.set_title("Cool roofs + street greening cut dangerous heat 60-73 %")
    ax.legend(frameon=False); ax.grid(alpha=.25, axis="y")
    fig.savefig(FIGS / "fig4_intervention.png"); plt.close(fig)

    # FIG 5 — humidity (dry-bulb vs wet-bulb)
    Hs = H.sort_values("WBT28_hrs", ascending=False); x = np.arange(len(Hs)); w = 0.4
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - w / 2, Hs.dry_hrs, w, label="Dry-bulb danger (T2 > 35 C)", color=SKY)
    ax.bar(x + w / 2, Hs.WBT28_hrs, w, label="Humid danger (wet-bulb > 28 C)", color=VERM)
    ax.set_xticks(x); ax.set_xticklabels(Hs.name, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("dangerous-heat hours")
    ax.set_title("Humidity reveals far more danger - and hits every neighbourhood")
    ax.legend(frameon=False); ax.grid(alpha=.25, axis="y")
    fig.savefig(FIGS / "fig5_humidity.png"); plt.close(fig)

    # FIG 6 — schematic city risk map
    order = ["refuge", "core", "hotspot"]
    titles = {"refuge": "REFUGE\n(green periphery)", "core": "CORE\n(formal centre)",
              "hotspot": "HOTSPOT\n(informal, dense)"}
    norm = colors.Normalize(0, 1)
    fig, ax = plt.subplots(figsize=(9, 7.0))
    ax.set_xlim(0, 3); ax.set_ylim(-0.4, 6.2); ax.axis("off")
    # title drawn inside the axes, well above the column headers (clear gap)
    ax.text(1.5, 5.9, "UDA-city — heat risk by neighbourhood (schematic)",
            ha="center", va="center", fontsize=15, fontweight="bold")
    for col, t in enumerate(order):
        rows = P[P.type == t].sort_values("risk_index", ascending=False).reset_index(drop=True)
        ax.text(col + 0.5, 4.55, titles[t], ha="center", va="bottom", fontsize=10.5, fontweight="bold")
        for i, r in rows.iterrows():
            yb = 3.5 - i * 1.05
            ax.add_patch(plt.Rectangle((col + 0.06, yb), 0.88, 0.92,
                                       facecolor=RISK_CMAP(norm(r.risk_index)), edgecolor="k", lw=1))
            txt = "white" if r.risk_index < 0.55 else "black"
            mark = "  * hottest" if r["name"] == "Jade Gardens" else (
                "  ^ top risk" if r["name"] == "Kampong Lama" else "")
            ax.text(col + 0.5, yb + 0.62, r["name"] + mark, ha="center", va="center",
                    fontsize=9, fontweight="bold", color=txt)
            ax.text(col + 0.5, yb + 0.34, f"risk {r.risk_index:.2f} . {int(r.dangerous_heat_hours)} hot-hrs",
                    ha="center", va="center", fontsize=8, color=txt)
    sm = cm.ScalarMappable(norm=norm, cmap=RISK_CMAP); sm.set_array([])
    fig.colorbar(sm, ax=ax, fraction=0.04, pad=0.02).set_label("heat RISK index (0-1)")
    fig.text(0.12, 0.02, "Schematic: UDA-city is synthetic - tiles grouped by neighbourhood type, not real coordinates.",
             fontsize=8, color="#6c757d")
    fig.savefig(FIGS / "fig6_map.png"); plt.close(fig)


def _fig7(off):
    # present baseline vs future (no action) vs future + intervention, treated grids
    x = np.arange(len(off)); w = 0.27
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.bar(x - w, off.present_base, w, label="Present (today)", color=SKY)
    ax.bar(x, off.future_base, w, label="+2.5 C future, no action", color=VERM)
    ax.bar(x + w, off.future_intv, w, label="+2.5 C future + cool-roof/greening", color=BLUE)
    for xi, r in off.reset_index(drop=True).iterrows():
        ax.text(xi, r.future_base + 4, f"offset {r.offset_pct:.0f}%", ha="center",
                fontsize=9, color=VERM, fontweight="bold")
        ax.annotate("", xy=(xi + w, r.future_intv), xytext=(xi, r.future_base),
                    arrowprops=dict(arrowstyle="->", color="#444", lw=1.1))
    ax.set_xticks(x); ax.set_xticklabels(off.name, fontsize=11)
    ax.set_ylabel("dangerous-heat hours (T2 > 35 C)")
    ax.set_title("Adaptation softens the +2.5 C future - but does not erase it")
    ax.legend(frameon=False, fontsize=9.5); ax.grid(alpha=.25, axis="y")
    fig.savefig(FIGS / "fig7_future_intervention.png"); plt.close(fig)


if __name__ == "__main__":
    main()
