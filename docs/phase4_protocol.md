# Phase 4 protocol: scale-up `scale_v1` (TASKS.md T10)

*Written 2026-10-07 and committed before any `scale_v1` repository is
selected or any data is fetched. Owner decision (2026-10-07): "Option A, the
longer route", with a GitHub token and parallel Layer 3 jobs. Everything below
is frozen by tag `freeze/scale-v1-design` before the first fetch; any later
change is a dated amendment here.*

## 1. Questions

Same funnel as Phases 1-3, on a larger, stratified, commit-pinned corpus:
1. Of resolved dependency edges, how many lack provenance (OPG)?
2. How many deficient edges have a screening-positive in-range candidate?
3. How many of those survive npm's real resolver (Layer 1, single highest
   candidate, frozen k = 0 definition)?
4. Among Layer-1-confirmed substitutions in repositories whose own test suite
   is reproducible in the isolated worker, how many keep install, lifecycle,
   peer, audit-signature status and tests (Layer 3)?

## 2. Corpus (new repositories only)

- **Frame.** GitHub repositories found by the search API with
  `language:JavaScript` or `language:TypeScript`, `stars:>=1000`,
  `fork:false`, `archived:false`, `pushed:>=2026-04-07`, queried in four star
  bands (1000-1999, 2000-4999, 5000-19999, >=20000), up to 1,000 results per
  (language, band) query, retrieved 2026-10-07. The 45 Phase 1 repositories
  are removed from the frame (they remain their own, already analysed corpus).
- **Strata.** star band (4) x age (`created_at` before vs. on/after
  2018-01-01) = 8 strata.
- **Sample.** Target **160 repositories, 20 per stratum**. Within each stratum
  candidates are visited in a seeded random order (`SEED = 20261007`) and the
  first 20 *eligible* ones are kept. Eligible = a root `package-lock.json` with
  `lockfileVersion >= 2` exists at the default-branch HEAD commit and parses.
  Shortfalls are recorded, not backfilled across strata.
- **Pinning.** The HEAD commit SHA is recorded at selection; the lockfile and
  `package.json` are fetched **at that SHA** (fixes the Phase 1 limitation of
  HEAD fetches without a SHA). Stars, created_at, pushed_at and language are
  stored per repository.
- Config written to `configs/experiments/scale_v1.yaml` by
  `scripts/scale_select_corpus.py`.

## 3. Phase 1 classification and Layer 1 (unchanged definitions)

- `pdr.resolve` + `pdr.policy` exactly as Phase 1 (same tolerance,
  `dist.attestations` signal). Registry facts as of the fetch date.
- Layer 1 on every `DEFICIENT_RESOLUTION_PRESERVING` edge: same patch rule and
  `npm install --package-lock-only --ignore-scripts`, npm 10.9.7, same OK /
  RIPPLE / PEER_CONFLICT / RESOLUTION_FAIL taxonomy; `EBADPLATFORM` on the
  analysis host is `PLATFORM_BLOCKED` (Section 7.1 of `phase2_protocol.md`).
  Each `(repo, package, candidate)` is resolved once and shared by its edges.
- Estimates: edge-weighted and repo-weighted, repo-clustered percentile
  bootstrap (5,000 resamples, seed 20260928), via `pdr.stats.clustered`.

## 4. Layer 3 cohort (outcome-blind)

- Unit: unique `(repo, package, candidate)` with Layer 1 `OK`.
- Repositories: the 160 `scale_v1` repositories (all commit-pinned).
- Static hermetic-test screen: identical keyword list to
  `phase3_select_micropilot.py` (applied to the `test` script text only).
- Per-repository cap **5**, seeded selection (`SEED`), no size allocation.
- Manifest `configs/experiments/scale_v1_manifest.json` + `.sha256`, written
  before any Layer 3 run.

## 5. Layer 3 execution

- Worker exactly as `freeze/phase3-worker-v3` (Node 22.22.2, corepack, 8 GB,
  6 GB V8 heap, original `package.json` restored before tests, PDR and B0 tests
  run twice, same allowlist: registry.npmjs.org + Sigstore hosts only).
- **Stage A, baseline screen.** B0 only, once per repository, tests twice.
  A repository is *testable* iff B0 installs and its tests pass on both runs.
- **Stage B, experiments.** Only experiments in testable repositories; B0 is
  re-run alongside PDR in the same job so every pair shares one runner.
- Both stages run on GitHub-hosted Ubuntu runners as a matrix of up to 20
  parallel jobs, sharded by repository (a repository never spans shards).
- The network self-test runs first in every job; a job that fails it records
  nothing.

## 6. Pre-specified analysis

Reported for the `scale_v1` corpus, next to the Phase 1 corpus:
1. OPG, proxy-positive share and Layer 1 OK rate, edge- and repo-weighted with
   clustered CIs.
2. Testable-repository rate (Stage A) with a Wilson CI (repositories are the
   unit), and the reasons for untestable baselines.
3. Layer 3 among judgeable experiments: `pdr.phase3` outcome counts and
   funnel; the share `OK`, experiment-weighted and repo-weighted with clustered
   CIs; the paired test-failure delta (primary, `paired_delta`); attestation
   gain summary.
4. If the judgeable count is below 30 experiments, no rate is reported as an
   estimate, only counts.
5. Exploratory (labelled as such): the above by star band and by age stratum.

## 7. Stop points

By the owner's instruction the run proceeds without intermediate approvals,
except: any change to isolation code beyond the plumbing in Section 5
(sharding, file paths), any allowlist change, or a failing network self-test
stops the work for the owner.
