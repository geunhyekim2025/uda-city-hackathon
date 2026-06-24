#!/usr/bin/env python
"""Second batch of extensions (scoring-criteria deepening).

  A. Science-optimal intervention - cool roof + cool PAVEMENT only (no trees),
     present and +2.5 K future. Follows from the decomposition finding that the
     dataset's low-albedo trees (0.14) warm the air; the optimal AIR-TEMPERATURE
     package drops them.
  B. Vulnerable person-hours - dangerous person-hours x vulnerable fraction = a
     headcount-of-harm metric. Plus an adaptive-capacity 4-pillar UNDRR variant
     (risk = hazard x exposure x sensitivity x lack-of-capacity).
  C. Heatwave events + intensity - dangerous days, longest spell, number of
     multi-day events, and degree-hours (intensity x duration).
  D. Roughness -> heat - regression of dangerous hours on frontal-area density
     (lambda_f), quantifying the mixing mechanism.

    .venv/bin/python scripts/extensions2.py
Writes outputs/derived/ext2_*.csv and docs/figs/fig12..14.png.
"""
from __future__ import annotations
import sys, warnings
from pathlib import Path
warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np, pandas as pd, yaml
from supy.suews_sim import SUEWSSimulation
import risk_bridge as rb

DERIVED = ROOT/"outputs"/"derived"; SUEWS = ROOT/"outputs"/"suews"; FIGS = ROOT/"docs"/"figs"
for d in (DERIVED, SUEWS, FIGS): d.mkdir(parents=True, exist_ok=True)
SPIN = rb.DEFAULT_SPINUP_DAYS; FUTURE = "forcing/future_hot_humid/UDA_2024_data_60.txt"
BLUE, VERM, GREEN, ORANGE, SKY, GREY = ("#0072B2","#D55E00","#009E73","#E69F00","#56B4E9","#6c757d")
plt.rcParams.update({"font.size":12,"axes.titlesize":13.5,"axes.titleweight":"bold","figure.dpi":130,
                     "savefig.bbox":"tight","axes.spines.top":False,"axes.spines.right":False})


def run_cached(config, tag, forcing=None):
    pq = SUEWS/f"{tag}.parquet"
    if pq.exists(): return pd.read_parquet(pq)
    sim = SUEWSSimulation(str(ROOT/config))
    if forcing: sim.update_forcing(str(ROOT/forcing))
    sim.run(); sim.results.to_parquet(pq); return sim.results


def _mm(s):
    lo, hi = s.min(), s.max()
    return pd.Series(0.0, index=s.index) if hi <= lo else (s-lo)/(hi-lo)


def main():
    neigh = rb.load_neighbourhoods(ROOT/"neighbourhoods.yml")
    socio = pd.read_csv(ROOT/"socioeconomic.csv")
    meta = neigh.set_index("gridiv")[["name","type"]]
    nraw = yaml.safe_load((ROOT/"neighbourhoods.yml").read_text())["neighbourhoods"]
    morph = pd.DataFrame([{"gridiv":n["gridiv"], "lambda_f":n["morphology"]["lambda_f"],
                           "pop_day":n["population_density_per_ha"]["day"],
                           "pop_night":n["population_density_per_ha"]["night"]} for n in nraw]).set_index("gridiv")

    def dry_hrs(res): return rb.build_risk(res, neigh, socio).set_index("gridiv")["dangerous_heat_hours"]
    res_p = run_cached("uda-city.yml", "present_full")

    # ---------- A. science-optimal package (cool roof + cool pavement, no trees) ----------
    opt = pd.DataFrame({
        "name": meta.loc[[4,5,9],"name"],
        "baseline_present": dry_hrs(res_p),
        "optimal_present": dry_hrs(run_cached("uda-city-roofonly.yml","roofonly_present")),
        "combined_present": dry_hrs(run_cached("uda-city-intervention.yml","intervention_full")),
        "baseline_future": dry_hrs(run_cached("uda-city.yml","future_full",FUTURE)),
        "optimal_future": dry_hrs(run_cached("uda-city-roofonly.yml","roofonly_future",FUTURE)),
        "combined_future": dry_hrs(run_cached("uda-city-intervention.yml","intervention_future",FUTURE)),
    }).loc[[4,5,9]]
    opt.to_csv(DERIVED/"ext2_optimal_intervention.csv")
    print("A optimal-intervention ->", "ext2_optimal_intervention.csv")

    # ---------- B. vulnerable person-hours + adaptive-capacity pillar ----------
    s_i = socio.set_index("gridiv")
    haz = dry_hrs(res_p)
    # person-hours (day) using daytime exposure; vulnerable fraction = raw vulnerability mean
    vraw = pd.DataFrame({"e":s_i.frac_over65,"y":s_i.frac_under5,"na":1-s_i.ac_access,
                         "o":s_i.frac_outdoor_workers,"d":s_i.deprivation_index}).mean(axis=1)
    B = meta.join(morph[["pop_day"]])
    B["person_hours"] = haz * B.pop_day
    B["vuln_fraction"] = vraw
    B["vuln_person_hours"] = (B.person_hours * vraw)
    # 3-pillar vs 4-pillar (separate adaptive capacity)
    sens = _mm(pd.DataFrame({"e":s_i.frac_over65,"y":s_i.frac_under5,
                             "o":s_i.frac_outdoor_workers,"d":s_i.deprivation_index}).mean(axis=1))
    lackcap = _mm(1 - s_i.ac_access)
    h, e = _mm(haz), _mm(B.pop_day.astype(float))
    vuln3 = rb.vulnerability_index(s_i)
    r3 = _mm((pd.DataFrame({"h":h,"e":e,"v":vuln3}).clip(lower=0).prod(axis=1))**(1/3))
    r4 = _mm((pd.DataFrame({"h":h,"e":e,"s":sens,"c":lackcap}).clip(lower=0).prod(axis=1))**(1/4))
    B["risk_3pillar"] = r3; B["rank_3pillar"] = r3.rank(ascending=False, method="min").astype(int)
    B["risk_4pillar"] = r4; B["rank_4pillar"] = r4.rank(ascending=False, method="min").astype(int)
    B.reset_index().to_csv(DERIVED/"ext2_vulnerable.csv", index=False)
    print("B vulnerable/ capacity ->", "ext2_vulnerable.csv")

    # ---------- C. heatwave events + degree-hours ----------
    rows = {}
    for g in res_p.index.get_level_values(0).unique():
        t2 = res_p.loc[g][("SUEWS","T2")].iloc[SPIN*288:]
        dmax = t2.resample("D").max().dropna()
        hot_day = (dmax > 35).astype(int).values
        # longest spell + count of events (>=3 consecutive hot days)
        longest = run = events = 0
        for v in hot_day:
            run = run+1 if v else 0
            longest = max(longest, run)
            if v and run == 3: events += 1   # count each spell once when it reaches 3
        degree_hours = float((t2[t2 > 35] - 35).sum())
        rows[g] = dict(hot_days=int(hot_day.sum()), longest_spell=int(longest),
                       heatwave_events=int(events), degree_hours=round(degree_hours,0))
    C = meta.join(pd.DataFrame(rows).T)
    C.reset_index().to_csv(DERIVED/"ext2_heatwave.csv", index=False)
    print("C heatwave/degree-hours ->", "ext2_heatwave.csv")

    # ---------- D. roughness -> heat regression ----------
    D = meta.join(morph[["lambda_f"]]); D["dangerous_hours"] = haz
    x, y = np.log10(D.lambda_f.values), D.dangerous_hours.values
    slope, intercept = np.polyfit(x, y, 1)
    yhat = slope*x + intercept
    ss_res = ((y-yhat)**2).sum(); ss_tot = ((y-y.mean())**2).sum()
    r2 = 1 - ss_res/ss_tot
    D.reset_index().to_csv(DERIVED/"ext2_roughness.csv", index=False)
    print(f"D roughness->heat  R^2(log lambda_f) = {r2:.2f}, slope = {slope:.0f} hrs/decade")

    _figures(opt.reset_index(), B.reset_index(), C.reset_index(), D.reset_index(), slope, intercept, r2)

    # console highlights
    print("\nA: optimal (roof+pavement) vs combined, present dangerous hrs:")
    for _, r in opt.iterrows():
        print(f"   {r['name']:<13} base {int(r.baseline_present):>2} | optimal {int(r.optimal_present):>2} "
              f"| combined {int(r.combined_present):>2}")
    print("B: 3-pillar vs 4-pillar (capacity) top-3:",
          list(B.sort_values('rank_3pillar').name[:3]), "vs", list(B.sort_values('rank_4pillar').name[:3]))
    print("C: hottest heatwave (longest spell days):",
          C.sort_values('longest_spell', ascending=False).iloc[0]['name'], int(C.longest_spell.max()))


def _figures(opt, B, C, D, slope, intercept, r2):
    TCOL = {"refuge":BLUE,"core":GREY,"hotspot":VERM}
    # FIG 12 - science-optimal intervention (present + future)
    x = np.arange(len(opt)); w = 0.13
    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    series = [("baseline_present","Present baseline",GREY),
              ("optimal_present","Present: roof+pavement (optimal)",SKY),
              ("combined_present","Present: roof+green (combined)","#9ecae1"),
              ("baseline_future","+2.5C baseline",VERM),
              ("optimal_future","+2.5C: roof+pavement",BLUE),
              ("combined_future","+2.5C: roof+green","#7bbf8a")]
    for i,(c,lab,col) in enumerate(series):
        ax.bar(x+(i-2.5)*w, opt[c], w, label=lab, color=col)
    ax.set_xticks(x); ax.set_xticklabels(opt.name, fontsize=11)
    ax.set_ylabel("dangerous-heat hours (T2 > 35 C)")
    ax.set_title("Science-optimal package: cool roof + cool PAVEMENT (drop the trees)")
    ax.legend(frameon=False, fontsize=8, ncol=2); ax.grid(alpha=.25, axis="y")
    fig.savefig(FIGS/"fig12_optimal.png"); plt.close(fig)

    # FIG 13 - vulnerable person-hours (headcount of harm)
    D2 = B.sort_values("vuln_person_hours", ascending=False); x = np.arange(len(D2))
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x, D2.vuln_person_hours/1000, color=[TCOL[t] for t in D2.type])
    ax.set_xticks(x); ax.set_xticklabels(D2.name, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("vulnerable person-hours per ha (thousands)")
    ax.set_title("Headcount of harm: vulnerable person-hours of dangerous heat")
    for t,c in TCOL.items(): ax.bar([],[],color=c,label=t)
    ax.legend(frameon=False); ax.grid(alpha=.25, axis="y")
    fig.savefig(FIGS/"fig13_vulnerable.png"); plt.close(fig)

    # FIG 14 - roughness -> heat regression (leader-line labels; boxed legend)
    Di = D.set_index("name")
    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    for _, r in D.iterrows():
        ax.scatter(r.lambda_f, r.dangerous_hours, s=200, color=TCOL[r.type], edgecolor="k", lw=.7, zorder=3)
    xs = np.linspace(D.lambda_f.min(), D.lambda_f.max(), 100)
    ax.plot(xs, slope*np.log10(xs)+intercept, "--", color="#444")
    ax.set_xscale("log")
    lab = {"Jade Gardens": (8, 2, "left", 0), "Taman Melati": (8, -1, "left", 0),
           "Kampong Lama": (9, 2, "left", 0), "Fuzhou Lanes": (9, 3, "left", 0),
           "Serendib Rise": (-9, 2, "right", 1), "Dhobi Lines": (9, 9, "left", 1),
           "Lusitano Square": (2, 15, "center", 1), "Victoria Exchange": (-4, -16, "right", 1),
           "Zheng He Towers": (8, -15, "left", 1), "Mlima Moto": (-9, 7, "right", 1)}
    for n, (dx, dy, ha, lead) in lab.items():
        r = Di.loc[n]
        ax.annotate(n, (r.lambda_f, r.dangerous_hours), xytext=(dx, dy), textcoords="offset points",
                    fontsize=8.3, ha=ha, va="center",
                    arrowprops=(dict(arrowstyle="-", color="#9aa3ab", lw=.7) if lead else None))
    handles = [Line2D([], [], ls="--", color="#444", label=f"log-fit  R$^2$ = {r2:.2f}")]
    for t in ("refuge", "core", "hotspot"):
        handles.append(Line2D([], [], marker="o", color="w", markerfacecolor=TCOL[t], markeredgecolor="k",
                              markersize=9, label=t.capitalize()))
    leg = ax.legend(handles=handles, loc="upper right", frameon=True, fontsize=9)
    leg.get_frame().set_edgecolor("#9aa3ab"); leg.get_frame().set_linewidth(1.0)
    ax.set_xlabel("frontal-area density  $\\lambda_f$  (roughness, log scale)")
    ax.set_ylabel("dangerous-heat hours (above 35 C)")
    ax.set_title("Smoother neighbourhoods are hotter: roughness -> mixing -> heat")
    ax.set_ylim(-6, 70); ax.grid(alpha=.25, which="both")
    fig.savefig(FIGS/"fig14_roughness.png"); plt.close(fig)


if __name__ == "__main__":
    main()
