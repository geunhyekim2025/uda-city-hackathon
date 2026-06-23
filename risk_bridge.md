# Heat hazard → socio-economic heat-risk bridge

This document describes the **reference bridge** UDA-city provides for turning
a SUEWS heat-hazard layer into a per-neighbourhood socio-economic heat-**risk**
indicator. The runnable implementation is [`risk_bridge.py`](risk_bridge.py);
the synthetic socio-economic inputs are [`socioeconomic.csv`](socioeconomic.csv).

It is a starting point, **not the answer you must copy**. The thresholds,
weights, and combination rule are all exposed as arguments precisely so you can
make — and justify — your own choices. Honest discussion of where this bridge
holds and where it breaks is itself a judged criterion.

## The decomposition

Following the UNDRR framing, risk is decomposed into three pillars:

```
risk = f(hazard, exposure, vulnerability)
```

- **Hazard** — the physical heat signal from SUEWS. The reference metric is
  *dangerous-heat hours*: the count of hours in the analysis window whose
  hourly-mean 2 m air temperature (`T2`) exceeds a threshold (default 35 °C),
  per neighbourhood, after discarding model spin-up.
- **Exposure** — how many people are in harm's way. The reference uses daytime
  population density (people ha⁻¹) from [`neighbourhoods.yml`](neighbourhoods.yml).
- **Vulnerability** — who is exposed and how able they are to cope. The
  reference combines five proxies from `socioeconomic.csv`: fraction over 65,
  fraction under 5, lack of air-conditioning access (`1 − ac_access`),
  fraction of outdoor workers, and a deprivation index.

Each pillar is min–max scaled to `[0, 1]` across the ten neighbourhoods, then
combined as a **geometric mean**:

```
risk_index = (hazard · exposure · vulnerability) ^ (1/3)
```

then re-scaled to `[0, 1]` and ranked. The geometric mean is deliberately
conservative: a near-zero in *any* pillar (e.g. nobody lives there) pulls the
risk down, even under extreme hazard. An arithmetic mean would instead let one
high pillar dominate — a defensible alternative if you argue for it.

## Why hazard ranking ≠ risk ranking

A central teaching point: the **hottest** neighbourhood is not necessarily the
**highest-risk** one. In UDA-city the low-rise *refuge* neighbourhoods can show
the highest `T2` (low building roughness → weak turbulent mixing → warmer near-
surface air under NARP), yet the dense informal *hotspot* neighbourhoods carry
far higher exposure and vulnerability (more people, less AC, more outdoor work,
higher deprivation). The risk bridge is where those pull against each other.
Surfacing that tension — rather than hiding it — is the point.

## Assumptions and caveats (these MUST travel with any output)

- **SUEWS produces an environmental hazard, not a health outcome.** `T2` over a
  threshold is a proxy for dangerous conditions, not a prediction of heat
  morbidity or mortality.
- **The threshold is a choice.** 35 °C on dry-bulb `T2` is illustrative. A humid-
  heat index (this is a *humid* city — RH ≈ 81 %) would arguably be more
  appropriate; a wet-bulb or apparent-temperature metric is a reasonable
  extension. State and justify whatever you pick.
- **The socio-economic layer is synthetic.** `socioeconomic.csv` carries
  plausible *magnitudes* for a low-income tropical city, not survey data for any
  real place. Treat ranks, not absolute values, as meaningful.
- **Min–max scaling is relative.** Every index is relative to the ten
  neighbourhoods in this dataset; it does not transfer to other cities.
- **Neighbourhood aggregation hides individuals.** A district-mean vulnerability
  masks the most exposed people within it.
- **The future scenario is pseudo-warming, not a projection.** See
  [`scenarios.yml`](scenarios.yml).
- **Anthropogenic heat is off in the baseline.** Population density here feeds
  *exposure/vulnerability*, not model heat (`emissions = 0`); see the README.

## Running it

```bash
# live present-scenario run straight from the canonical config
.venv/bin/python risk_bridge.py --out outputs/derived/risk_present.csv

# future scenario, custom threshold
.venv/bin/python risk_bridge.py \
    --forcing forcing/future_hot_humid/UDA_2024_data_60.txt \
    --threshold 36 --out outputs/derived/risk_future.csv
```

Outputs a per-neighbourhood table: `dangerous_heat_hours`, the three scaled
pillars, `risk_index`, and `risk_rank`.
