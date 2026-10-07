# Phase 4 results: scale-up `scale_v1` (TASKS.md T10)

Protocol: `docs/phase4_protocol.md` (tag `freeze/scale-v1-design`, committed
before any repository was selected). Layer 3 manifest frozen at
`freeze/scale-v1-manifest` before any Layer 3 run. Layer 3 ran on GitHub
Actions run 37603963471 (20 parallel jobs per stage, about 30 minutes wall
clock). Analysis: `scripts/scale_report.py` -> `results/processed/scale_v1_summary.json`.
Every figure below is registered in `docs/claims.json` (`scale_v1`).
CIs: repository-clustered percentile bootstrap (5,000 resamples, seed
20260928) unless marked Wilson.

## The funnel (160 new, commit-pinned repositories)

| Stage | Result | Edge / experiment-weighted [95% CI] | Repo-weighted [95% CI] |
|---|---|---|---|
| Resolved edges | 262,066 edges, 160 repos; 1.94% UNKNOWN | | |
| Lacking provenance (OPG, among known edges) | 217,924 / 256,995 | **84.80%** [82.7, 87.0] | 83.4% [80.8, 85.8] |
| Screening-positive in-range candidate (among deficient) | 17,549 / 217,924 | **8.05%** [6.7, 9.4] | 5.8% [4.7, 7.0] |
| Layer 1 OK: npm's resolver accepts it with no other change | 5,003 / 17,549 | **28.51%** [23.8, 33.3] | 45.2% [39.8, 50.8] |
| Layer 3 cohort | 363 experiments in 91 repos (119 repos had an OK candidate; 28 removed by the hermetic text screen; cap 5 per repo) | | |
| Stage A: repository's own tests reproducible in the worker | 31 / 91 repos | **34.1%** (Wilson [25.2, 44.3]) | |
| Stage B: experiments run (testable repos) | 110 experiments in 31 repos | | |
| Judgeable (B0 tests pass on both runs) | 108 experiments in 30 repos | | |
| **Substitution-attributable failure at any stage** | **0 / 110** | install, lifecycle and test paired deltas all 0 | |

Layer 1 outcomes: OK 5,003; RIPPLE 10,860; PEER_CONFLICT 1,573;
RESOLUTION_FAIL 113 (93 are `EUNSUPPORTEDPROTOCOL` in one repository,
`js-primer/js-primer`, an unsupported dependency protocol in its own manifest;
2 are `EOVERRIDE`). No `EBADPLATFORM` occurred on this corpus.

## Layer 3 in detail

Pre-specified outcome counts over the 110 experiments: **OK 97,
LIFECYCLE_FAIL 12, TEST_FAIL 1**. Among the 108 judgeable experiments the
pre-specified OK share is **88.89%** [75.5, 100.0] experiment-weighted, 90.0%
[80.0, 100.0] repo-weighted.

**None of the 13 non-OK outcomes is attributable to the substitution:**
- The 12 `LIFECYCLE_FAIL` (`paaatrick/playball` x5, `rtfpessoa/diff2html` x5,
  `vscode-icons/vscode-icons` x2) fail identically on the unmodified baseline:
  a post-install download blocked by the network allowlist (Playwright browser
  download, an HTTP fetch) or a vendored binary build without execute
  permission (`./configure: Permission denied`). The tests of these repos still
  pass on both arms.
- The 1 `TEST_FAIL` (`wangwangit/SubsTracker`) is in a repository whose B0
  tests were not reproducible in Stage B, so it is not judgeable.

So the attributable-failure funnel is clean at every stage: install 110/110,
lifecycle 98/98 attributable, peer 98/98, audit-signature status 98/98, tests
96/96 attributable (`pdr.phase3.funnel`). Paired failure deltas (PDR - B0):
install 0/110 pairs, lifecycle 0/110, test 0/108 (30 repos). The bootstrap CI
is degenerate at [0, 0] because no event occurred; *exploratory* rule-of-three
upper bounds for a zero count are about **2.8% per experiment** (3/108) and
**10% per repository** (3/30).

Audit: all 110 pairs parsed; no pair lost a verified signature or gained an
invalid/missing one. Attestation gain: +1 or more in 99 pairs, 0 in 11, never
negative (median +1).

Exploratory subgroups (judgeable experiments, OK / n): stars 1k-2k 5/10,
2k-5k 23/28, 5k-20k 44/46, 20k+ 24/24; created before 2018 48/60, after 2018
48/48. All non-OK in these subgroups are the baseline-shared lifecycle failures
above, so the differences reflect which repositories have such post-install
steps, not the substitution.

## Why 60 of 91 repositories were untestable (Stage A)

Tests fail on the unmodified baseline in 41, install fails in 18, tests are
flaky in 1. Sampled install-failure causes: git dependencies or private
registries the allowlist refuses, `engines` requiring npm 11 or an older npm,
and `npm ci` usage errors in workspace monorepos. These are properties of the
repositories and of a locked-down, offline-by-default worker, not of the
substitution; they bound what Layer 3 can say: **the behavioural result covers
roughly one third of eligible repositories, those whose own test suites are
self-contained and reproducible**.

## What this means (for the owner to frame; not a chosen story)

- The large losses happen **before** behaviour: 84.8% of edges lack
  provenance, only 8.05% of those have a screening-positive candidate, and only
  28.5% of those survive npm's real resolver without moving any other package.
  End to end, about **2.3% of deficient edges** (5,003 / 217,924) are
  resolution-confirmed recoverable on this corpus (an edge-level product of
  pooled rates; not separately bootstrapped).
- **Once a candidate passes the resolver, it behaved identically to the
  baseline in every testable case** (0/110 attributable failures, upper bound
  about 3% per experiment). This replicates the micro-pilot's 12/12 at about
  nine times the size and on a new, stratified corpus.
- This matches the README's pre-registered pattern "high-PD / almost all
  deploy / near-zero cost", which the README says weakens the "excess
  enforcement cost" flagship. The data instead support a framing in which the
  bottleneck is **availability and resolution** (upstream publishers and npm's
  resolver), not breakage.

## Limitations

Registry state read on 2026-10-07; the 160-repo sample is stratified random
within a GitHub-search frame (>=1k stars, active, JS/TS, committed lockfile v2+),
not the npm ecosystem; Layer 3 covers testable repositories only (34%); tests
measure what each repository chose to test; the worker refuses network hosts
other than the npm registry and Sigstore; the Layer 1 run used Windows with
npm 10.9.7 (no platform blocks occurred).
