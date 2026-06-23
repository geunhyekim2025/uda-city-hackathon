# UDA-city — SUEWS Community Hackathon dataset

A synthetic, lower-income, **hot-humid** city for the SUEWS Community Hackathon. Ten
morphologically-varied neighbourhoods share one SUEWS configuration, so you can drive an
urban climate model in plain language through the **suews-agent** — no manual input
assembly, no coding required.

> Synthetic by design: UDA-city supplies a realistic climate and city structure, **not a
> real place**. Differences between neighbourhoods come from urban form, land cover, and who
> lives there, not from differing weather.

## Start here

The single file an agent should read first is [`agent_manifest.yml`](agent_manifest.yml) — it
points at the canonical config, the scenarios, the output variables, and the risk bridge.
The city to load is [`uda-city.yml`](uda-city.yml) (10 neighbourhoods, `gridiv` 1–10).

```
# example, in plain English, through your AI agent:
Run the present hot-humid scenario for all 10 neighbourhoods and report
dangerous-heat hours per neighbourhood. Then translate that into a
socio-economic heat-risk indicator and explain where the bridge holds.
```

## The challenge, in one line

Across ten neighbourhoods of this hot-humid city, **where is heat most dangerous to people**,
now and under a hotter future — and is that the same as where it is simply hottest? You produce
a heat-hazard layer with SUEWS and bridge it to a socio-economic heat-**risk** indicator. The
threshold, the indicator framing, the visualisation, and the caveats are **yours to justify** —
there is no single correct route.

## What's in it

- `uda-city.yml` — the canonical 10-neighbourhood SUEWS config (load this).
- `neighbourhoods.yml` — `gridiv` → name, type, morphology, population (a readable sidecar).
- `socioeconomic.csv` — synthetic vulnerability proxies (age, AC access, outdoor work, deprivation).
- `scenarios.yml` — present hot-humid and a +2.5 °C hotter-future forcing.
- `forcing/` — the two derived SUEWS met files the scenarios point at.
- `risk_bridge.py` + `risk_bridge.md` — a **reference** hazard → exposure × vulnerability bridge
  (UNDRR-style). Reference, not the answer: thresholds and weights are arguments so you can
  justify your own.
- `agent_manifest.yml` — the agent entry point.
- `tests/` — quick checks (`pytest -m 'not slow'`) you can run to confirm your environment.

## Scenarios

- **Present** — present hot-humid hot season (a coastal tropical climate).
- **Future** — a humidity-preserving **+2.5 °C** pseudo-warming of the same window (a scenario
  stress test, **not** a downscaled climate projection).

The config points at the present file; switch the forcing to the future file to run the warming case.

## Physics

The canonical config runs **NARP** net radiation + **classic OHM** storage heat — single-layer,
laptop-runnable. This is a deliberate, fixed choice (no SPARTACUS, no dynamic OHM); please leave
it as is so every team's runs are comparable.

## Requirements

`supy >= 2026.6.5` (earlier 2026.x aborts at runtime). See `pyproject.toml`.

## Citing SUEWS

Järvi, L., Grimmond, C.S.B. & Christen, A. (2011). The Surface Urban Energy and Water Balance
Scheme (SUEWS): Evaluation in Los Angeles and Vancouver. *Journal of Hydrology*, 411(3–4),
219–237. https://doi.org/10.1016/j.jhydrol.2011.10.001

Ward, H.C., Kotthaus, S., Järvi, L. & Grimmond, C.S.B. (2016). SUEWS: Development and evaluation
at two UK sites. *Urban Climate*, 18, 1–32. https://doi.org/10.1016/j.uclim.2016.05.001

Use the version actually used in your run — guidance at https://docs.suews.io/stable/#how-to-cite-suews

## Honest limits

SUEWS gives an **environmental** heat hazard, not a health outcome. The socio-economic layer is
**synthetic** (read ranks, not absolute values). A high-hazard area is not automatically high-risk
if few vulnerable people are exposed there — keeping hazard, exposure and vulnerability separate,
and being honest about where the bridge breaks, is the point of the exercise.
