# AI collaboration log — UDA-city heat-risk submission

A curated record of how this submission was built with an AI coding agent
(Claude Code / suews-agent driving `supy` and the SUEWS MCP tools). It documents
the workflow, the prompts that mattered, and — most importantly — the points
where the AI and I **cross-checked and corrected** the analysis rather than
taking the first answer. (This is a readable log of the session; the raw tool
transcript can be attached alongside.)

## Workflow at a glance

1. **Ground the agent in the dataset, not guesses.** First prompt pointed it at
   `agent_manifest.yml` and made it read `risk_bridge.md` + `risk_bridge.py`
   *in full* before running anything — so every later step used the repo's own
   contract (canonical config, physics lock, hazard definition, caveats).
2. **Confirm it runs before trusting it.** Built a Python 3.12 env, installed
   `supy >= 2026.6.5` (the manifest's hard requirement), and ran the repo's own
   `scripts/smoke_test.py` — which asserts T2/QH finite — before any analysis.
3. **Present scenario → risk bridge** for all 10 neighbourhoods, using the
   reference `build_risk` verbatim, then read the result against the urban form.
4. **Stress the result**: humid-heat metrics, +2.5 K future, and a cool-roof +
   greening intervention — each validated, each cross-checked.
5. **Deliverable**: a reproducibility script (`scripts/reproduce.py`) + a public
   GitHub Pages story site, with an honest "holds / breaks" section.

## Prompts that mattered (paraphrased)

- *"Read risk_bridge.md and risk_bridge.py in full, plus the lead example prompt.
  Then summarise what the bridge computes, what SUEWS outputs it needs, and where
  the docs flag limitations. Don't run anything yet."* — forced comprehension
  before action.
- *"Which is hottest, which is highest-risk, and are they the same? Explain the
  divergence in terms of urban form (roughness, mixing, exposure, vulnerability)."*
- *"The docs flag that 35 C dry-bulb is inappropriate for a humid city. Re-compute
  the hazard using a humid-heat metric from the forcing data."*
- *"Run a cool-roof + greening intervention ... quantify the reduction in
  dangerous-heat hours and risk index versus baseline."*

## Where AI + human cross-checking changed the answer

These are the moments the collaboration added real value — catching things a
single-pass answer would have got wrong:

1. **Apparent-temperature threshold saturation (caught, then fixed).** The first
   humid-heat pass kept the 35 C threshold on *apparent temperature*. Cross-check:
   AT runs ~6 C hotter than T2 here, so every neighbourhood was "dangerous" ~800 h
   — the hazard signal collapsed into noise and the ranking scrambled. Correction:
   threshold the metric at its own danger level (wet-bulb > 28 C; AT > ~41 C).
   **Lesson surfaced for the writeup: change the metric and the threshold together.**

2. **Min–max relative-scaling artefact (honest bridging).** After the intervention
   cut Kampong Lama's dangerous hours 60 %, its *relative* risk index stayed pinned
   at 1.00 and untreated neighbourhoods' indices *rose* without getting hotter.
   We traced this to the bridge's min–max scaling and made it a headline caveat:
   **judge interventions by absolute hazard avoided, not a relative index.**

3. **Physically-consistent humidity.** Rather than splice forcing-level RH onto the
   modelled T2 (inconsistent — RH depends on temperature), we used the model's own
   2 m RH2/Q2, which are height-consistent with T2. Stated explicitly so a reviewer
   can object.

4. **Energy-balance verification of the intervention.** We didn't just report fewer
   hot hours — we checked the mechanism: QN down ~37 W/m^2 (higher albedo), QE up
   ~5 W/m^2 (greening), QH down ~25 % (less sensible heating of the air). The
   cooling is traceable to QN + QF = QS + QE + QH, not asserted.

5. **Config edited under constraint, then validated.** Editing land cover required
   the surface fractions to still sum to 1.0; the agent enforced that, then ran
   `suews validate` (zero errors/warnings) *before* the long run — the SUEWS MCP's
   recommended guardrail against a confident-but-wrong narrative.

## Engineering issues the agent caught and fixed

- `matplotlib.cm.get_cmap` was removed in the installed version → switched to
  `plt.get_cmap`.
- GitHub Pages "Page build failed" because it ran **Jekyll** on a hand-written
  static site → added `docs/.nojekyll` (correct fix for static HTML).
- Verified the live site end-to-end (every asset HTTP 200, new sections served)
  rather than assuming the push deployed.

## Reproduce everything

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv "supy>=2026.6.5" pyyaml matplotlib pandas
.venv/bin/python scripts/reproduce.py    # runs 3 SUEWS scenarios, writes CSVs + all 6 figures
```

Deterministic: same inputs reproduce the same numbers (present/future dangerous-hour
totals 242 / 1861; intervention −60/−65/−73 %) and the same figures on the site.
