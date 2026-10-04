# Phase 1 results: diversified 45-repo de-risking run

Config: `configs/experiments/kill_v1_phase1_n45.yaml` (experiment ID
`kill_v1_phase1_n45`, a new ID per README's frozen-protocol rule --
`kill_v1.yaml`, the original 7-repo pilot, is untouched). Corpus: 45 repos
(the original 7 plus 38 more; **a deliberately diversified convenience
corpus with pre-specified stratification variables for coverage and
subgroup analysis, not a statistical stratified sample of npm** -- see
`docs/methodology_freeze.md` Section 4 for why that distinction matters),
**69,692 resolved edges**.

## Headline: does the pilot's 3.80% hold up?

| | Pilot (7 repos, edge-level naive) | Phase 1 (45 repos, edge-level naive) | Phase 1 (45 repos, repo-clustered) |
|---|---:|---:|---:|
| OPG | 84.07% | 83.29% | -- |
| Semantic recoverability | 3.80% | 4.29% | **4.29% [95% CI 2.17%, 6.50%]** |

**Yes, it holds up.** The point estimate is stable (3.8% -> 4.29%) across
an independently-sourced, diversified, 6.4x larger corpus, and the
repository-clustered bootstrap 95% CI (5,000 resamples, seed 20260924,
`scripts/bootstrap_ci.py`) is `[2.17%, 6.50%]`. Under the pre-specified
operational bound of 10% (`docs/methodology_freeze.md` Section 1 -- a
project-internal decision rule, not an established statistical cutoff),
this interval excludes the non-negligible region. Per that frozen decision
rule: **recoverability looks genuinely low at this scale, not a 7-repo
sampling artifact** -- stated as a decision under the project's own
pre-specified rule, not as an objective fact about the npm ecosystem.

## Secondary statistic: is recoverability concentrated or widespread?

**40 of 45 repos (88.9%, Wilson 95% CI [76.5%, 95.2%]) contain at least
one recoverable deficient edge.** This is the important nuance the
edge-level percentage alone hides: recoverability is **thin within each
repo but present across almost all of them**. Note this is a genuinely
different estimand from the primary statistic above (repo-weighted vs.
edge-weighted -- see `docs/methodology_freeze.md` Section 3's estimand
freeze); it is not a second measurement of the same 4.29% figure. That
matters for Kill Test 10 (statistical power) -- it means a larger Gate C/D
sample won't be starved for candidates concentrated in one or two outlier
repos; the population of candidates to test is broadly distributed.

## Breakdown by coverage variable (all computed directly, `results/processed/phase1_stratified_breakdown.json`)

| Stratum | OPG % | Semantic recovery % of deficient | n deficient |
|---|---:|---:|---:|
| lockfileVersion v2 | 79.02% | 1.42% | 2,817 |
| lockfileVersion v3 | 83.53% | 4.43% | 54,598 |
| size: small (<300 pkgs) | 82.12% | 0.90% | 1,888 |
| size: medium (300-800) | 78.82% | 2.07% | 18,009 |
| size: large (800-1600) | 83.13% | 6.71% | 23,839 |
| size: very_large (>1600) | 90.55% | 3.45% | 13,679 |
| monorepo | 83.27% | 3.55% | 20,005 |
| non-monorepo | 83.31% | 4.68% | 37,410 |

Direction is consistent everywhere (OPG stays 79-91%, recoverability stays
single-digit everywhere). The v2-lockfile stratum shows the lowest
recoverability (1.42%) but is also the smallest stratum (4 repos, 2,817
deficient edges) -- worth another look once the v2 stratum is larger at
Phase 3 scale, but not treated as a separate finding yet given n=4 repos.

## Decision (per `docs/methodology_freeze.md` Section 1)

CI entirely below 10% -> **proceed to Section 2's reframing rule, not a
re-run with a different threshold.** Given Phase 1.5's finding (see
`docs/phase1_5_results.md`) that a nontrivial share of proxy-positive
candidates don't survive real npm resolution unchanged, **Outcome B or C**
(rare recoverability, possibly compounded by operational cost) is looking
like the more likely eventual framing than Outcome A -- but this is not
decided until Gate C/D actually run at scale. Proceeding to Phase 3 (200
repos) remains justified: 88.9% repo coverage means there will be enough
candidates to power that analysis even if the edge-level rate stays ~4%.
