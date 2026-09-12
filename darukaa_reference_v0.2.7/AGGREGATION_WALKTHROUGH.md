# How Scores Aggregate: Indicator → Component → Overall

A precise walkthrough of what actually happens in the code, from a single indicator's
raw satellite value to the final decision output — for a conservation project (single
or multiple separate polygons) and, separately, for an agroforestry project (many small
tiled parcels). Every step below is grounded directly in `estimators.py`, `scoring.py`,
`report.py`, and `project_aggregation.py` — nothing here is aspirational.

**Update (v0.2.4):** an earlier revision of this document said the pipeline does not
produce a single score or a concern label, full stop. That was true then and is no
longer the whole story — a product/dashboard layer (`son_score.py`) now sits ON TOP of
everything below, described in Part C. What is still true, and remains a deliberate
choice: the underlying engine (Steps 1-9 below) never averages away a weak component to
flatter an overall number, and condition/pressure are never blended into one figure.

---

## Part A — Conservation project (one polygon, or several separate polygons)

### Step 1 — Indicator level: the responsive benchmark
For every **scored** indicator (a lean, deliberately-curated subset — currently 10 of 44
registered; see `INDICATOR_REGISTER.md` for why each of the other 34 isn't scored), the
site's value is compared against its SEED-aligned reference condition (same ecoregion ×
land-cover stratum, HMI-filtered, PNV-corrected for converted pixels — see
`METHODOLOGY_MASTER.md` §5). This produces a **signed, uncapped benchmark**:
- ratio-scale indicators (cover %, density, canopy height) → **log response ratio**,
  `ln(site/reference)`
- interval/bounded indicators (NDVI, indices) → **robust standardised deviation**,
  `(site − reference_median) / (1.4826 × reference_MAD)`

Both are oriented so **positive = better than reference**, for every indicator,
including pressure indicators (a pressure benchmark of +0.3 means *lower* pressure than
reference — the sign convention is unified before anything downstream sees it).

### Step 2 — Normalise for aggregation only
The signed benchmark is mapped to a 0–1 score via a declared logistic (`0.5` = exactly
at reference), used **only** for combining numbers below — the report's profile view
still shows the raw signed value and its estimator. This mapping is a display/
aggregation convenience, not a claim about ecological meaning.

### Step 3 — Subdimension level: average (the one place averaging is allowed)
Where a construct has more than one indicator sharing a subdimension, those are
averaged. This is the one place a mean is used — because indicators in the same
subdimension are genuinely redundant measures of the *same* thing, not different
things being blended together.

### Step 4 — Component (pillar) level: limiting factor
Within a construct (C1 landscape, C2 vegetation, C3 fauna, C4 pressure), the
component's headline is the **minimum** subdimension score — the weakest subdimension
sets the component's score, not the average. The mean across subdimensions is still
computed and shown, but only as context, never as the headline. This is the same
logic Landbanking's own EII uses internally (confirmed via document review: a hard
minimum of its three sub-scores, not a soft/fuzzy combination) — applied consistently
across every construct here, not just the one indicator that happens to use it natively.

### Step 5 — Condition roll-up (C1 + C2 + C3): non-compensatory, and optional
The three condition components combine into an optional, secondary roll-up via a
**penalised geometric mean** (equal weights by default; a project may declare different
weights, but that's a pre-registered methodology decision, not a per-run tweak). Two
things are true of this number that were not true of the composite it replaced:
- The **minimum component is always published alongside it**, by name. A high roll-up
  cannot exist in the report without also showing which component (if any) is dragging
  it down.
- A **sensitivity check** recomputes the roll-up under alternative weightings. If the
  coarse outcome band flips depending on which weights are used, the roll-up is flagged
  **UNSTABLE** — meaning: don't trust this single number, read the profile instead.

### Step 6 — Pressure axis (C4): kept separate, always
C4 (pressure) goes through the identical limiting-factor logic (Step 4) but is **never**
merged into the condition roll-up. State and pressure answer different questions
("what shape is it in" vs "what's bearing down on it") and blending them into one
number was one of the specific failures this methodology replaced.

### Step 7 — The decision output: condition × pressure matrix
Condition roll-up and pressure headline are combined into **one of four quadrants** —
this is the closest thing to a single "final answer," and it's categorical, not numeric:

| | Low pressure | High pressure |
|---|---|---|
| **Good condition** | Protect / maintain | Defend — abate threat |
| **Poor condition** | Restore | Stabilise, then restore |

### What the client-facing report actually shows (in this order)
1. Per-component profile with the limiting subdimension named (primary output)
2. The condition × pressure decision quadrant
3. The roll-up number, always with its minimum component and stability flag
4. The framing block (verbatim, every time a roll-up is shown): *"...a decision aid...
   NOT a measurement of biodiversity... a change in the number is not by itself
   ecological change... read the minimum component first, the profile second, the
   roll-up last."*

### Multiple separate conservation polygons in one project
If a conservation project has more than one distinct site (not a fragmented multi-parcel
AOI — genuinely separate places), **each is its own site profile**, run and reported
independently through Steps 1–7 above. There is currently no automatic project-level
combination across genuinely separate conservation sites (unlike agroforestry tiles,
below) — each stands as its own answer, since there's rarely an ecological reason to
force-combine unrelated places into one number. If that's needed for a specific project,
the multi-tile aggregation logic in Part B could be reused for it, but that's a
deliberate choice to make per project, not a default behaviour.

---

## Part B — Agroforestry project (many parcels, tiled into assessment units)

Agroforestry AOIs are typically hundreds of small, scattered parcels spanning too much
area for one buffer-based reference lookup to mean anything. They must be **tiled
first** (grouped into a manageable number of ecologically-local assessment units,
upstream of this pipeline — see `project_aggregation.py`'s module docstring), then each
tile runs through **exactly** Steps 1–7 above, independently, as if it were its own
small conservation site. Nothing in Part A changes for a tile — a tile's own profile,
roll-up, and matrix cell are produced by the identical code.

The only new step is what happens **across** tiles, and it deliberately mirrors Step 4
one level up:

### Step 8 — Cross-tile aggregation: worst tile, named
For every scored indicator, across every tile that has data for it, the
**project-level value is the worst tile's signed benchmark** — literally the minimum,
exactly the limiting-factor principle from Step 4, applied across tiles instead of
across subdimensions. The tile responsible is named explicitly in the output
(`multi_tile_summary.per_indicator[indicator].worst_tile`). A large, well-performing
tile can never mathematically hide a small degraded one.

Two secondary numbers are also reported, clearly labelled as context, never as the
headline:
- an **area-weighted geometric mean** of the tiles' normalised scores (still penalises
  low tiles, just less severely than the worst-tile headline)
- a plain **area-weighted mean of the raw indicator value** (a physically additive
  quantity — e.g. "average canopy cover across the project" — genuinely different in
  kind from a condition score, and never conflated with one)

### Step 9 — Same engine, one more time
These combined worst-tile-per-indicator values are fed into the **exact same**
`scoring.build_site_profile()` used for a single site in Steps 3–7. The "project" is
therefore, in every downstream sense, a site profile — same limiting-factor components,
same condition × pressure matrix, same sensitivity flag, same framing block. No parallel
aggregation logic exists at the profile level; only the *input* differs (worst-tile
values instead of one site's own values).

### What the project-level report shows (in addition to everything in Part A)
- A **per-indicator worst-tile table**: which tile set the project's number for each
  indicator, and why (`html_report.py` renders this as its own "Multi-tile aggregation"
  section)
- Every individual tile's own full report is also written and kept, in full — so anyone
  can drill from the project number down into exactly the tile (and, from there, the
  parcels within it) that's driving the result

### The trivial case, confirmed
Running this same multi-tile path with exactly one tile produces the identical result
as running the single-site pipeline directly on it — there is one aggregation
philosophy in this pipeline, not two. Agroforestry doesn't get a different methodology;
it gets one additional non-compensatory step *before* the same methodology.

---

## Summary table

| | Conservation (one site) | Agroforestry (many tiles) |
|---|---|---|
| Indicator → subdimension | average (Step 3) | average, per tile (Step 3) |
| Subdimension → component | minimum (Step 4) | minimum, per tile (Step 4) |
| Cross-tile, per indicator | — | **minimum across tiles** (Step 8) |
| Component → condition roll-up | penalised geometric mean + published minimum (Step 5) | same, on the worst-tile-combined values (Step 9) |
| Condition vs pressure | always separate (Step 6) | same |
| Final decision output | condition × pressure matrix (Step 7) | same |
| Overall condition score (0–1) + class | Step 10 (from the roll-up) | same, from the tile-combined roll-up |
| Overall pressure score (0–1) + class | Step 11, always separate from condition | same, always separate |

---

## Part C — The product/dashboard layer (v0.2.4): one score, one class, per site

Everything in Parts A and B produces a **profile** (`site_profiles` in the report) —
per-component headlines, the condition roll-up with its minimum and stability flag, the
pressure headline, the matrix cell. That's the primary, most information-dense output,
and it's still there, unchanged. `son_score.py` adds a layer on top that reduces it to
exactly what a dashboard widget or a downstream risk model (e.g. a TNFD State-of-Nature
input) actually needs to bind to: **two numbers, two classes, kept separate.**

### Step 10 — Overall Condition Score (0–1) and its class
`overall_condition()` takes the condition roll-up from Step 5 — the same
non-compensatory geometric mean, the same published minimum component, the same
stability flag — and:
- reports it as a single **0–1 score**
- maps it onto a **5-band concern class** (Very Low → Very High), using a declared
  product convention (equal-width bands on the normalised scale, symmetric around
  0.5 = "at reference") — stated explicitly as a convention, not a claim that these five
  bands are independently in the ecological literature
- attaches a **confidence flag**: how many of the 3 condition pillars (C1/C2/C3)
  actually had a scored indicator with data this run. A score computed from 1 of 3
  pillars is flagged `"low"` confidence, not presented identically to one computed from
  all 3 — this is what stops an incomplete assessment from silently looking complete.

### Step 11 — Overall Pressure Score (0–1) and its class — kept separate
`overall_pressure()` does the identical thing to the pressure headline from Step 6.
**This is never combined with the condition score inside this pipeline.** If a consumer
(a dashboard, a TNFD risk-aggregation module) wants one blended number, that combination
is that consumer's own explicit, documented step — not something invented here.

### Per-indicator classification: two modes, always both shown where both exist
Every scored indicator, in the scorecard, gets:
- a **reference-relative class** — bands the SAME normalised benchmark already used for
  scoring (Step 2). Always available, for every scored indicator.
- a **literature-anchored class**, only where a document review found a breakpoint
  defensibly independent of ecoregion (currently: `natural_habitat`, anchored to
  Andrén/Fahrig fragmentation thresholds — see `son_score.LITERATURE_BREAKPOINTS`). Most
  indicators don't have one (confirmed metric-by-metric, not assumed) and correctly show
  reference-relative only.

Critically: **the class always comes from the same reference-condition comparison the
indicator was already scored against** (per your confirmation) — this is not a second,
independently-computed number. Ex-situ metrics are classified this way because they have
a computable reference condition. In-situ metrics (cycle-2 change scores, `change.py`)
do not go through this classification at all — they report detected change vs. a site's
own Year-0, which is a different question with no reference-condition equivalent; see
`change.py`'s own docstring.

### What a dashboard actually binds to
```
son_summary = report["son_summary"][site_id]
son_summary["overall_condition"]["score"]           # 0-1
son_summary["overall_condition"]["concern_class"]    # "Moderate" etc.
son_summary["overall_condition"]["confidence"]       # {"level": "high"/"medium"/"low", ...}
son_summary["overall_pressure"]["score"]             # 0-1, SEPARATE
son_summary["overall_pressure"]["concern_class"]
son_summary["matrix_cell"]                           # the 4-quadrant decision
```
Two badges (condition, pressure), one confidence indicator, one decision quadrant — the
whole profile is still there underneath for anyone who needs to explain *why*.
