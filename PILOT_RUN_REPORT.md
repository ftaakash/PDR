# PDR-G1 pilot run report

**What this is:** a working implementation of the pipeline `README.md`
specifies (`fetch_corpus.py` -> `check_provenance.py` -> `analyze_kill.py`
-> `scan_regression.py`), executed end-to-end against **real npm dependency
trees** (not synthetic/simulated data), plus a pytest suite covering the
classification logic. See `docs/gate_status.md` for the full gate
breakdown and honest limitations, and `docs/scope_boundary.md` for the
provenance-vs-safety boundary.

## Headline result (pilot scale -- 7 real repos, 19,148 edges)

- **84.07%** of resolved dependency edges lack provenance at the resolved
  version (OPG). Not an artifact of stale/pre-provenance packages: still
  **75.53%** among edges whose resolved version was published *after* npm
  provenance's GA date (2023-09-26).
- Of the deficient edges, only **3.80%** have any provenance-bearing version
  within their declared semver range at all (semantic recoverability), and
  **3.69%** of those are a "resolution-preserving" candidate (differs from
  what's currently resolved by at most a minor/patch step).
- **4.95%** of packages with enough version history show at least one
  provenance-*loss* event (present -> absent across their own version
  history) -- 1,597 such events across 137 packages in this corpus
  (secondary finding).
- Consistent in direction across all 7 repos (59%-92% OPG), across direct
  vs. transitive deps, and across every era bucket.

**Read this as a genuine, if small-sample, empirical signal -- not as
"PDR is proven."** See `docs/gate_status.md` for why: Gate B (meaningful
semantic recoverability) fails the working 5% threshold used here, which is
exactly the failure mode Kill Test 2 in the audit prompt warns about, and
this pilot is ~1/28th the size of the specified 200-repo G1 sample.

## What was and wasn't built

Built and run for real, this session:
- `pdr/resolve.py` -- real npm lockfile v2/v3 parser with correct
  node_modules resolution order, including npm-workspaces support (hit and
  fixed a real crash on `npm/cli`'s workspace-shaped lockfile along the way
  -- see `tests/test_resolve_workspaces.py`).
- `pdr/provenance.py` -- registry-verified provenance signal (checked live
  against known provenance/non-provenance packages before trusting it).
- `pdr/policy.py` -- the 5-state+unknown ladder classification, with the
  resolution-preserving tolerance explicitly flagged as a v0.1 proxy (see
  its docstring) rather than full tree re-resolution.
- `pdr/regression.py` -- secondary present->absent regression scan.
- `scripts/*.py` -- the exact pipeline `README.md`'s Quick Start describes.
- `scripts/semver_helper.js` -- npm-range semantics via Node's own `semver`
  package rather than an approximate Python re-implementation.
- 22 passing pytest tests, including a mechanical check that no code or
  output text equates "recoverable"/"provenanced" with "safe".

## Not built (declared, not silently skipped) -- see `docs/gate_status.md`

- Gate C (semantic-to-operational gap, renamed per
  `docs/methodology_freeze.md` Section 5) and Gate D (excess enforcement
  cost) at full scale -- both need the isolated-worker sandbox
  (`docs/methodology_freeze.md` Section 7), not yet built. A tiny, safe
  resolution-verification slice of what Gate C needs WAS run for real --
  see `docs/phase1_5_results.md`.
- The full 200-repo G1 sample (Phase 1 used 45; see `docs/phase1_results.md`).
- Builder/source-path-change enrichment for regression events.
- Popularity/age-based stratification (blocked on GitHub API quota this
  session -- see `docs/methodology_freeze.md` Section 4).
- The exhaustive academic-literature adversarial audit.

## Phase log

- **Pilot (7 repos, 19,148 edges):** see this file's sections above and
  `docs/gate_status.md`. Gate: A/E/F PASS, **B FAIL** (3.80% semantic
  recoverability), C/D PENDING.
- **Phase 0 (methodology freeze):** `docs/methodology_freeze.md` -- froze
  the B decision rule, sampling strategy, Gate C rename, Gate D primary
  metric, repo-clustered bootstrap method, and sandbox spec, before Phase 1
  ran against real data.
- **Phase 1 (45-repo diversified corpus, 69,692 edges):** `docs/phase1_results.md`.
  Point estimate held (3.80% -> 4.29%), repo-clustered bootstrap 95% CI
  `[2.17%, 6.50%]` -- entirely below the "not negligible" bound, so this is
  a real, low-but-real signal, not a 7-repo artifact. 88.9% of repos
  contain at least one recoverable case (Wilson CI `[76.5%, 95.2%]`), so
  the population isn't starved for a larger Gate C/D run.
- **Phase 1.5 (21-candidate resolution-verification pilot):**
  `docs/phase1_5_results.md`. Real, safe (`npm install --package-lock-only
  --ignore-scripts`, no code execution) test of proxy-vs-actual-resolution
  agreement: 85.7% confirmed, 14.3% showed a real ripple effect the local
  proxy couldn't see (concretely: forcing `espree` 9.4.1->9.6.1 pulled
  `acorn` 8.8.1->8.18.0 as a hoisting side effect). This is now a required
  second stage before Phase 2's Gate C/D counts a candidate as
  resolution-preserving at all.
- **Phase 2, Layer 1 (full-scale resolution confirmation, 2,349 candidates):**
  `docs/phase2_layer1_results.md`. **Major downward correction to the
  screening-proxy headline:** only 27.16% of proxy-positive candidates are
  resolution-confirmed (`OK`); 70.50% cause a real ripple effect elsewhere
  in the tree; 2.34% hit a genuine `ERESOLVE` peer conflict. Cascaded
  through Phase 1's corpus, the population of edges that are actually,
  verifiably recoverable without disturbing anything else shrinks from
  ~4.09% of deficient edges (screening) to **~1.11%** (resolution-
  confirmed) -- Phase 1.5's 21-candidate estimate (85.7% confirmed) did not
  hold at scale, which is exactly the failure mode running the full
  population is supposed to catch. A real harness bug (`EOVERRIDE`, from
  not reconciling a candidate with the root `package.json`'s OWN direct
  dependency on the same package, even for edges nested elsewhere in a
  monorepo) was found, root-caused against real npm error output, fixed,
  and the fix locked in with a network-free regression test
  (`tests/test_layer1_patch_logic.py`) before being trusted at scale.
- **Phase 2, Layer 2 (structural install, 13 candidates, 4 repos):**
  `docs/phase2_layer2_results.md`. 13/13 real `npm ci --ignore-scripts`
  installs succeeded (both B0/B1 baseline and PDR-substituted trees) --
  install-time consistency between `package.json` and `package-lock.json`
  required a second methodological fix (`npm ci` rejects a patched
  `package.json` against an unregenerated lockfile; fixed by re-resolving
  first, then installing). The `npm audit signatures` (B1) comparison could
  **not** run: it needs Sigstore's TUF trust-metadata CDN, which isn't in
  this session's network allowlist -- a real scope boundary, documented and
  fed back into the Phase 2 sandbox spec, not worked around.
- **Layer 3 (behavioral: real lifecycle scripts + test suites): explicitly
  not run.** This requires genuine disposable/isolated worker
  infrastructure (`docs/phase2_protocol.md` Section 5) that this shared
  session container is not. Running arbitrary real npm packages' install
  scripts here would mean executing untrusted code with no containment --
  a considered stopping point, not a time constraint.
- **Phase 3 (isolated-worker infrastructure + micro-pilot design):**
  `docs/phase3_protocol.md`. Built, in full, without ever running Layer 3
  in this container: `pdr/phase3.py` (classification logic, pair
  attribution, attrition funnel, repository-clustered paired deltas -- 18
  tests against synthetic fixtures only, `tests/test_phase3_logic.py`),
  `isolated_worker/` (Dockerfile, mitmproxy egress-allowlist addon,
  `orchestrate.py`'s command-construction-and-safety-gate, `runner.py`'s
  in-container stage runner with its own host-execution refusal check --
  22 tests, `tests/test_isolated_worker.py`, exercising both the real
  command construction path and deliberately mutilated/adversarial inputs).
  `scripts/phase3_select_micropilot.py` generated a real, hash-locked,
  outcome-blind 23-experiment cohort (25 targeted; small bucket has a
  documented, non-backfilled shortfall) BEFORE any Layer-3 result exists,
  with a frozen direct-dependency-field floor added after noticing the
  first draft under-sampled that patch mode. `scripts/phase3_pin_snapshots.py`
  recovered real commit SHAs for all 19 involved repos via git-metadata-only
  operations (19/19 pinned, 0 unresolved) and materialized one real snapshot
  end-to-end as proof. **Nothing in Phase 3 has been run against a live
  Docker daemon** -- none exists in this session -- stated plainly in
  `docs/phase3_protocol.md` Section 8/9 along with the exact next steps
  (`--selftest` first, then `--dry-run`, then `--limit 2`, then the full
  micro-pilot) and the two other unverified pieces (a placeholder base-image
  digest that `setup.sh` refuses to build past, and audit-signatures
  regexes never validated against real output because of the network wall
  Layer 2 hit). This is infrastructure and a frozen protocol, not a result.
- A real performance bug was found and fixed at Phase 1 scale: the
  classifier was spawning ~170k Node subprocesses on 45 repos (3 per
  deficient edge); refactored to dedupe by `(dep_name, range)` and batch
  across the whole corpus in ~5 subprocess calls total. Verified
  byte-identical classification output on the original 7-repo pilot before
  and after the refactor.

## Reproducing or extending this run

```powershell
py -m pytest tests/ -q
py scripts/fetch_corpus.py --config configs/experiments/kill_v1.yaml
py scripts/check_provenance.py --in results/raw/resolve/ --out results/raw/provenance/edges.csv
py scripts/analyze_kill.py --in results/raw/provenance/edges.csv --out results/processed/kill_summary.json
py scripts/scan_regression.py --config configs/experiments/regression_v1.yaml
```

(On Linux/macOS use `python3` instead of `py`; `node`/`npm` must be on
PATH for `scripts/semver_helper.js`, which `pip install -r requirements.txt`
does not cover -- see `package.json`.) To scale to the full 200-repo sample,
add more entries to `configs/experiments/kill_v1.yaml` -- any repo with a
committed npm lockfile v2/v3 works with zero code changes; the pipeline
already dedupes and caches per-package-name, so re-running after adding
repos only re-fetches what's new.


## Continuing with Claude Code

This repository is set up for handoff to Claude Code: `CLAUDE.md` (operating
rules: execution safety, scientific integrity, autonomy boundaries),
`TASKS.md` (ordered backlog with human gates), `.claude/settings.json`
(permission rules), `.claude/commands/` (`/verify`, `/next`), and
`docs/claims.json` + `scripts/check_claims.py` (every headline number is
recomputed from raw data and checked by a test). Git history starts at the tag
`import/chat-session-baseline`: everything before it (the Phase 0 freeze, the
Phase 2 protocol, the Phase 3 manifest hash) was frozen in prose and file
hashes inside the chat session and has **no independent timestamp**. Only
freezes tagged after the baseline are verifiable from git history.
