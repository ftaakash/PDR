# Phase 2, Layer 1 results: full-scale resolution confirmation

All **2,349** `DEFICIENT_RESOLUTION_PRESERVING` candidates from the Phase 1
corpus (45 repos) were run through Layer 1: force the candidate via a real
`overrides`/direct-dependency edit against the repo's actual
`package.json` + `package-lock.json`, and re-resolve with
`npm install --package-lock-only --ignore-scripts` (no code execution --
`docs/phase2_protocol.md` Section 2). Script: `scripts/layer1_resolution.py`.
Raw output: `results/processed/phase2_layer1_results.jsonl` (2,349 rows).

## Headline: the screening proxy substantially overstates resolution-preserving-ness

| Outcome | n | % of proxy-positive candidates |
|---|---:|---:|
| **OK** (real resolution confirms the proxy) | 638 | **27.16%** |
| **RIPPLE** (candidate applies, but >=1 other package's version shifts as a side effect) | 1,656 | **70.50%** |
| **PEER_CONFLICT** (real `ERESOLVE` peer-dependency conflict) | 55 | **2.34%** |

Phase 1.5's 21-candidate pilot estimated 85.7% confirmed / 14.3% ripple.
**That estimate did not hold at scale.** This is exactly the failure mode a
small pilot is supposed to catch and a large run is supposed to correct --
21 candidates across 5 repos was not enough to see that ripple is the
*typical* outcome, not the exception. The full run reverses the pilot's
apparent conclusion.

## What this means for the project's headline number

Phase 1's reported "4.29% semantic recoverability" was always explicitly a
**screening-stage** proxy-positive rate (`docs/methodology_freeze.md`
Section 6), not a claim about real recoverability -- but it's worth making
the cascading correction explicit and prominent, because it changes the
headline by roughly 4x:

```
57,415 deficient edges (Phase 1 corpus)
    -> 2,349 screening-proxy-positive ("resolution-preserving")   = 4.09% of deficient
        -> 638 resolution-CONFIRMED (Layer 1 OK)                   = 1.11% of deficient
                                                                       (27.16% of proxy-positive)
```

**The population of edges that are actually, verifiably recoverable without
disturbing anything else in the tree is closer to ~1.1% of deficient edges,
not ~4%** -- and that's still before Gate C's structural/behavioral checks
(Layer 2/3), which will shrink it further. This is the single most
important revision this phase produced, and it should be the number carried
forward into any GO/KILL framing from here on, not the Phase 1 screening
figure alone.

## Per-repo variation is large and informative

| Repo | n candidates | OK % |
|---|---:|---:|
| `socketio/socket.io` | 384 | **0.0%** |
| `nestjs/nest` | 30 | 0.0% (all 30 are `PEER_CONFLICT`) |
| `puppeteer/puppeteer` | 62 | 8.1% |
| `winstonjs/winston` | 96 | 4.2% |
| `webpack-contrib/css-loader` | 465 | 24.3% |
| `webpack-contrib/mini-css-extract-plugin` | 437 | 27.9% |
| `stylelint/stylelint` | 37 | **86.5%** |
| `chaijs/chai` | 31 | 71.0% |
| `karma-runner/karma` | 34 | 70.6% |

**7 of 40 repos with candidates have a 0% real confirmation rate** -- every
single proxy-positive candidate for those repos either ripples or conflicts.
`nestjs/nest`'s 30/30 `PEER_CONFLICT` is a single root cause, not 30
independent findings: a pinned `@nestjs/apollo@14.0.2` dependency conflicts
with every one of that repo's candidate substitutions. This is a good
illustration of why edge-count and repo-count are different denominators
(`docs/methodology_freeze.md` Section 3's estimand freeze) -- one
maintainer's pinning choice in one repo produced 30 edge-level data points
from a single underlying cause.

## Ripple magnitude

Among the 1,656 `RIPPLE` candidates: median 4 other top-level packages
shift version as a side effect, mean 8.04, max **127** (a single candidate
substitution in one repo cascaded into 127 other packages changing
resolved version). This is the dedup/hoisting effect Phase 1.5's `espree`
example illustrated in miniature -- at full scale it is common and
sometimes very large, not an edge case.

## A real harness bug was found and fixed during this run (documented, not hidden)

The first full run showed 609/2,349 (25.9%) `RESOLUTION_FAIL` -- alarmingly
high. Investigation traced 559 of those to `npm error code EOVERRIDE`, and
tracing *that* to its root cause found a genuine bug in
`scripts/layer1_resolution.py`, not an ecosystem finding: npm's `overrides`
mechanism errors whenever the target package name is **also a direct
dependency of the root `package.json`, in any field**, even when the
specific edge under test is a nested/transitive one from a different
workspace package. Confirmed concretely via `puppeteer/puppeteer`: the
failing edge was `packages/browsers`'s own `yargs` dependency, but the
*root* `package.json`'s `devDependencies` separately pins
`yargs@18.0.0`, and that root-level pin is what `overrides` collided with.

Fix: before writing `overrides`, the script now checks whether the
candidate's package name appears in *any* of the root `package.json`'s own
dependency fields; if so, it patches that field directly to the candidate
version instead of adding an `overrides` entry (npm requires this
reconciliation). Verified against the same 15 originally-failing candidates
before trusting it, then applied to all 559 affected candidates. Post-fix,
genuine `RESOLUTION_FAIL` dropped to 0 -- the remaining 55 failures were all
real `ERESOLVE` peer conflicts (confirmed by inspecting each one's captured
npm error text) and were reclassified from `RESOLUTION_FAIL` to
`PEER_CONFLICT` accordingly, matching the frozen taxonomy in
`docs/phase2_protocol.md` Section 3.

This is now the second harness-correctness bug found by running at scale
after a small pilot looked clean (the first was the ~170k-subprocess
performance bug at 45-repo scale after the 7-repo pilot ran fine). Neither
was visible at pilot scale. Both are now documented rather than silently
absorbed into "the numbers changed a bit."

## What carries forward to Layer 2

Only the **638 `OK`** candidates are resolution-confirmed and eligible for
Layer 2 (structural install). `RIPPLE` and `PEER_CONFLICT` candidates are
retained in the dataset (they're a result, not noise) but are not promoted
-- per `docs/phase2_protocol.md` Section 2, Layer 2's install-success
measurement is only meaningful for candidates whose resolution was actually
clean.

## Addendum: uncertainty, concentration, and estimand (added after review)

The 27.16% above is the **edge-weighted** pooled rate, and it was first
reported without an interval. Computed afterwards from the same JSONL
(repository-clustered percentile bootstrap, 5,000 resamples, seed 20260928):

| Quantity | Value |
|---|---|
| Pooled (edge-weighted) OK rate | 27.16%, **95% CI [18.0%, 40.1%]** |
| Repo-weighted (macro) mean OK rate | **52.3%** (median 57.8%) |
| Repos with 0% OK / with >=50% OK | 7 of 40 / 24 of 40 |
| Share of all candidates held by top 3 repos | 54.7% (`css-loader`, `mini-css-extract-plugin`, `socket.io`; the first two are sibling `webpack-contrib` projects with similar trees) |
| Distinct (repo, package, candidate) substitutions behind the 638 OK edges | 234 |
| Resolution-confirmed share of deficient edges | 1.11%, CI [0.73%, 1.64%] (treats the 4.09% screening rate as fixed, so the interval is too narrow) |

**What this means.** "Only 27% survive" is true for the *average edge*, but
the *typical repository* sees roughly half of its candidates survive. The
pooled figure is pulled down by a few large repositories with many
near-duplicate candidates (`socket.io` alone: 384 candidates, 0 OK). Both
numbers are legitimate answers to different questions
(`docs/methodology_freeze.md` Section 3, estimand freeze) and any paper must
report both, with the interval, rather than quote 27% alone.

**Two design limits that make "OK" conservative, not exact.**
1. Layer 1 tested only the *single highest* in-range provenance-bearing
   version per edge. The research question (RQ2) asks whether *any* such
   version exists; lower provenance-bearing versions were never tried, so
   resolution-confirmed recovery is under-counted by construction.
   *Update 2026-10-05:* experiment `layer1_alt_v1` measured this and found
   the under-count is small: exists-any 27.67% vs 27.16% edge-weighted
   (`docs/phase2_layer1_alt_results.md`).
2. "OK" requires **zero** change to any other top-level package. One benign
   patch bump elsewhere counts as RIPPLE. A ripple-size sensitivity analysis
   (e.g. OK if <=k other packages change, or only patch-level changes) has
   not been done.

## Sensitivity analysis: ripple size (added 2026-10-05, TASKS.md T2)

*Sensitivity analysis, not a redefinition.* The frozen `OK` definition
(k = 0: zero other top-level packages change) is unchanged and remains the
number carried forward. The thresholds k in {0, 1, 2, 5, 10} were declared in
`TASKS.md` before this was computed. A candidate counts at tolerance k if it is
`OK`, or `RIPPLE` with the candidate actually applied and at most k other
top-level packages changing version; `PEER_CONFLICT` never counts. No new
resolution was run: this uses the stored `n_ripple` of
`phase2_layer1_results.jsonl`. Script: `scripts/layer1_report.py` ->
`results/processed/layer1_summary.json`. CIs: repository-clustered percentile
bootstrap, 5,000 resamples, seed 20260928.

| k (max other packages changed) | OK edges | Edge-weighted % [95% CI] | Repo-weighted % [95% CI] |
|---:|---:|---|---|
| 0 (frozen) | 638 | 27.16 [18.0, 40.1] | 52.3 [41.5, 63.0] |
| 1 | 973 | 41.42 [26.6, 58.7] | 65.1 [54.0, 75.8] |
| 2 | 1,109 | 47.21 [30.3, 64.8] | 74.8 [64.4, 84.2] |
| 5 | 1,494 | 63.60 [58.1, 74.3] | 80.7 [71.2, 89.0] |
| 10 | 1,673 | 71.22 [65.4, 80.4] | 82.6 [73.3, 90.9] |

**Reading.** The single most consequential definitional choice in Layer 1 is
how much side-effect is tolerated. Allowing one other package to move raises
the edge-weighted rate from 27% to 41%; allowing five raises it to 64%. The
k = 0 figure is therefore a strict lower bound on "recoverable without
disturbing the tree", and the paper should present this curve rather than a
single cut-off. Two cautions: (1) `n_ripple` counts packages, not the size or
direction of their version changes, so k = 1 can still mean a disruptive
change; (2) the repo-weighted CI for k = 0 ([41.5, 63.0]) was not reported in
the original addendum and is new here.
