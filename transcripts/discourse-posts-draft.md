# SUEWS Discourse — hackathon channel post drafts

Ready-to-paste posts for the SUEWS Community Discourse hackathon channel.
Each shares a real, reusable finding from building the UDA-city submission —
best practice and a critical suggestion, not just "we did X". Post the ones you
like; edit freely so they're in your own voice.

---

## Post 1 — Best practice: a humid-heat threshold has to move with the metric

Working the UDA-city (hot-humid, RH ≈ 81%) hazard layer, I hit a trap worth
flagging. The natural instinct is "dry-bulb 35 °C is wrong for a humid city, so
switch T2 to apparent temperature." But if you keep the **35 °C threshold** on
apparent temperature, AT runs ~6 °C hotter than T2 here, so *every*
neighbourhood is "dangerous" ~800 hours — the hazard signal saturates and the
ranking turns to noise.

The fix: threshold each metric at *its own* danger level (e.g. wet-bulb
Tw > 28 °C, or AT recalibrated to ~41 °C). When you do, the humid metric is
informative again — and, interestingly, the neighbourhood *ranking* is robust to
the metric choice because humidity is near-uniform across the city; what changes
is the *absolute* danger (wet-bulb > 28 °C for 90–265 h everywhere).

**Suggestion for the SUEWS recipe set:** when documenting heat-hazard examples,
pair every metric with a metric-appropriate threshold, and note that swapping the
metric without the threshold is a silent failure mode.

---

## Post 2 — Critical suggestion: relative (min–max) risk indices hide interventions

When bridging a SUEWS hazard to a 0–1 risk index, min–max scaling across sites is
common. It has a sharp edge that bit me: after a cool-roof + greening run cut the
worst neighbourhood's dangerous-heat hours by 60%, its **relative risk index
didn't move** (still 1.0, because it's still the worst), and *untreated*
neighbourhoods' indices went *up* without getting any hotter — purely because the
scale re-baselined.

So a relative index can make a genuinely effective intervention look like it
helped nobody. For SUEWS-to-policy work I'd suggest: report the **absolute**
hazard change (hours of dangerous heat avoided) alongside any relative index, and
be explicit that min–max indices don't transfer between cities or before/after
states. Happy to share the worked example.

---

## Post 3 — Best practice: validate before you run, and use the model's own 2 m state

Two small habits that saved me from confident-but-wrong results on UDA-city:

1. **Validate the YAML before every long run.** Editing land cover for an
   intervention, I had to keep surface fractions summing to 1.0; running
   `suews validate` (zero errors) before the simulation caught structure issues
   up front instead of after a narrative was written.
2. **Use the model's self-consistent near-surface humidity.** SUEWS outputs
   `RH2`/`Q2` at the same 2 m height as `T2`. For humid-heat indices, that's more
   defensible than splicing forcing-level RH (defined at a different height /
   temperature) onto modelled T2.

If useful to others, I've put a one-command reproducibility script and an
honest "where the bridge holds / breaks" writeup in my hackathon repo.

---

*(Links to add when posting: your GitHub Pages site and repository.)*
