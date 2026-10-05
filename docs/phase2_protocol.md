# Phase 2 protocol (frozen before execution)

Per the reviewer's layered redesign, Gate C ("semantic-to-operational gap")
and Gate D (excess enforcement cost) are decomposed into a funnel:

```
Proxy-positive (screening, Gate B's DEFICIENT_RESOLUTION_PRESERVING)
      |
Layer 1 -- Resolution-confirmed  (real npm resolver, overrides, no execution)
      |
Layer 2 -- Structurally installable  (npm ci --ignore-scripts, real disk, no execution)
      |
Layer 3 -- Behaviorally viable  (real install incl. lifecycle scripts + repo test suite)
      |
Test-surviving
```

Each candidate that fails a layer is retired with a reason code (Section 3)
rather than silently dropped, so the funnel itself becomes a result, not
just a filter.

## 1. What this session's environment actually is

Before deciding what to run, the honest description of the execution
environment this document governs: a single shared container, persistent
for the conversation, with egress restricted to an allowlist of domains
(registry.npmjs.org, github.com, and similar -- not a general-purpose
network), but with **no** disposable-per-experiment isolation, no CPU/RAM
caps under this project's control, and no guarantee that one candidate's
execution can't affect another's environment or this session's own
working state. It is a reasonable, moderately-restricted dev sandbox. It
is **not** the isolated worker `docs/methodology_freeze.md` Section 7
specifies for Gate C/D, and was never claimed to be.

## 2. Frozen decision: which layers run where, and why

| Layer | What it does | Executes package code? | Runs in this session? |
|---|---|---|---|
| **1 -- Resolution** | `npm install --package-lock-only --ignore-scripts` against a real `package.json`+`overrides` | **No** -- resolves metadata only, no `node_modules`, no tarball extraction | **Yes** |
| **2 -- Structural install** | `npm ci --ignore-scripts` (real `node_modules` on disk) | **No** -- `--ignore-scripts` unconditionally skips every lifecycle hook (`preinstall`/`install`/`postinstall`/`prepare`) | **Yes**, at bounded scale (Section 4) |
| **3 -- Behavioral** | Real install with lifecycle scripts enabled, then the repo's own test command | **Yes** -- by design, this is the whole point of the layer | **No -- deferred** (Section 5) |

Layer 2 is included because `--ignore-scripts` is not a convenience flag,
it is npm's actual code-execution boundary: with it set, no code from any
package in the tree runs during install, full stop. Downloading and
extracting real tarballs is I/O, not execution, and carries the same
residual risk any `npm install` on any machine carries independent of this
project (a malicious tarball exploiting the extractor itself) -- not a risk
this project is introducing. Layer 3 is different in kind, not degree: it
means deliberately executing arbitrary code from real, untrusted,
third-party npm packages, which is exactly the thing an isolated,
disposable, resource-capped, no-host-mount worker exists to contain. That
worker does not exist in this session, so Layer 3 does not run here. This
is not a capability gap to work around with more caution; it is the
correct place to stop.

## 3. Failure/outcome taxonomy (frozen, applies to every layer)

```
RESOLUTION_FAIL      -- npm's real resolver rejected the override outright
RIPPLE               -- resolved, but >=1 other top-level package's version
                         changed as a side effect (Phase 1.5's finding)
PEER_CONFLICT         -- resolution produced a peer-dependency conflict
INSTALL_FAIL           -- Layer 2: npm ci --ignore-scripts exited nonzero
TIMEOUT                 -- exceeded the per-candidate wall-clock budget
RESOURCE_LIMIT           -- exceeded disk/memory budget (Layer 2)
LIFECYCLE_FAIL             -- Layer 3 only, not produced by this session
TEST_FAIL                   -- Layer 3 only, not produced by this session
NO_BEHAVIORAL_CHANGE          -- Layer 3 only, not produced by this session
OK                              -- candidate cleared the layer cleanly
```

A candidate that is `RESOLUTION_FAIL` or has a `RIPPLE` at Layer 1 is
**not** promoted to Layer 2 as a resolution-confirmed candidate. `RIPPLE`
candidates are still recorded (they're the more interesting failure mode,
per Phase 1.5), just not advanced -- Layer 2's install-success measurement
is only meaningful for candidates whose resolution was actually clean.

## 4. Frozen scope for what runs in this session

- **Layer 1, full run:** every `DEFICIENT_RESOLUTION_PRESERVING` candidate
  from the Phase 1 corpus (2,349 candidates across 40 repos) is in scope --
  this is the safe, cheap layer, no reason to sub-sample it now that the
  performance issue from the 45-repo classifier run is already fixed.
  Batched, resumable (checkpointed to JSONL), so a run interrupted by a
  tool time limit picks up where it left off rather than restarting.
- **Layer 2, bounded micro-pilot:** a fixed, pre-committed sample of
  Layer-1-confirmed candidates, capped in size because each real `npm ci`
  downloads and extracts a full dependency tree (can be tens to low
  hundreds of MB per repo) -- unlike Layer 1, this has real bandwidth/disk
  cost per candidate. Sample: up to 5 confirmed candidates each from 6
  small-to-medium repos (`axios/axios`, `koajs/koa`, `tj/commander.js`,
  `mozilla/source-map`, `nodeca/js-yaml`, `eemeli/yaml`), chosen for tree
  size (all in the small/medium size bucket from Phase 1's strata) so a
  full `npm ci` per candidate stays tractable. This mirrors Phase 1.5's
  "tiny pilot before the giant harness" discipline, just one layer deeper.
- **Baseline comparison included in Layer 2:** for every candidate tested,
  `npm audit signatures` is run against both the unmodified tree (B0/B1
  reference) and the PDR-substituted tree, so Gate D's B0/B1/PDR matrix
  starts collecting real data rather than only being specified.
- **Layer 3:** zero candidates. See Section 5.

## 5. What Layer 3 needs before it can run anywhere

Not implemented in this session. To run responsibly, it needs:

1. A disposable, isolated worker per candidate (container or VM), torn
   down after each run -- no shared state between candidates, no shared
   state with whatever orchestrates them.
2. No host filesystem mounts beyond the one repo snapshot being tested.
3. CPU/RAM caps and a hard wall-clock timeout enforced by the isolation
   layer itself, not just a cooperative `timeout` command inside a shared
   container.
4. Network restricted to the npm registry only (no arbitrary egress),
   enforced at the network layer the worker runs on, not by convention.
   **Must also explicitly include Sigstore's TUF trust-metadata CDN** --
   discovered empirically in the Layer 2 micro-pilot
   (`docs/phase2_layer2_results.md`): `npm audit signatures` cannot run at
   all without it (`tuf-js`'s `Updater.refresh` fails outright), so a
   registry-only allowlist silently breaks Baseline 1 for the entire Gate D
   comparison. "npm registry only" as originally scoped in this section was
   wrong in a way that would have gone unnoticed until Layer 3 tried to run
   B1 -- caught now instead, before real infrastructure is built around it.
5. No credentials of any kind reachable from inside the worker.

`scripts/layer1_resolution.py` and `scripts/layer2_structural_install.py`
(Section 4) are written so that a Layer 3 script can reuse the same
candidate-selection and result-schema code once that infrastructure
exists -- only the actual install command changes (drop `--ignore-scripts`,
add the repo's test command after install).

## 6. Gate D data collected at this scope

At Layer 2 micro-pilot scale, Gate D's frozen primary metric
(`docs/methodology_freeze.md` Section 8: test-failure-rate delta) is
**not** measurable yet -- that requires Layer 3. What IS collected at this
scope: install-success-rate delta (PDR vs. B0) and
`npm-audit-signatures`-status delta (PDR vs. B1), both secondary/co-primary
metrics from the frozen matrix. These are real, if small-sample, first
data points toward Gate D -- not a Gate D verdict.

## 7. Amendment 2026-10-05: experiment `layer1_alt_v1` ("exists-any" retry)

*Written and committed before any `layer1_alt_v1` attempt was run. Nothing in
Sections 1-6 changes; this is a new experiment ID that reuses the Layer 1
harness.*

**Reason (stated before outcomes).** RQ2 asks whether *any* provenance-bearing
in-range version is recoverable. Layer 1 tried only the single highest such
version per edge (`docs/phase2_layer1_results.md`, addendum limit 1), so its
27.16% OK rate is a lower bound by construction. This experiment measures how
much of that gap closes when lower provenance-bearing versions are tried.

**Population.** The 1,711 Layer 1 edges whose single candidate ended `RIPPLE`
(1,656) or `PEER_CONFLICT` (55). Layer 1 `OK` edges are not re-run.

**Alternative candidates per edge** (pure function
`pdr.layer1_alt.alternative_candidates`, unit-tested). A version `v` of the
edge's package qualifies iff all hold:
1. `dist.attestations` is present in the registry packument (same signal as
   `pdr.provenance`);
2. `semver.satisfies(v, declared_range)` with `includePrerelease: false`;
3. `semver.diff(resolved_version, v)` is in `{null, "patch", "minor"}` (the
   frozen `RESOLUTION_TOLERANCE` of `pdr/policy.py`, unchanged);
4. `semver.lt(v, original_candidate)` (the original candidate was the
   maximum, so anything higher is a later release, not an alternative);
5. registry publish time `<= T_cut = 2026-09-24T00:00:00Z`. Phase 1's run date
   was not recorded; the latest publish timestamp of any resolved version in
   the Phase 1 data is 2026-09-23T20:42Z, so this cut-off excludes releases
   that could not have existed when Phase 1 ran (e.g. backports on a lower
   line). The number of versions excluded by this rule is recorded.

Qualifying versions are tried in descending semver order, at most **K = 5**
per edge, stopping at the first `OK`. Edges with zero qualifying versions are
recorded as `NO_ALTERNATIVE` (a result, not missing data).

**Attempt procedure.** Identical to `scripts/layer1_resolution.py`: same
`pdr.sandbox.patch_package_json_for_candidate` edit of the cached
`package.json`, same Phase 1 lockfile, `npm install --package-lock-only
--ignore-scripts --no-audit --no-fund`, 60 s timeout, same `OK`/`RIPPLE`
definition (`OK` = candidate applied and zero other top-level version
changes). A non-zero exit whose stderr contains `ERESOLVE` is `PEER_CONFLICT`
(the rule Layer 1's documented reclassification applied by hand); any other
non-zero exit is `RESOLUTION_FAIL`. Host-safe per Section 2: no scripts, no
`node_modules`.

Because the override is applied by package name, an attempt's outcome
depends only on `(repo, package, version)`; each such triple is run once and
its outcome is shared by every edge that tries it.

**Inputs that had to be recovered.** The Phase 1 lockfiles were not in the
handoff. `scripts/recover_phase1_lockfiles.py` recovers each from git history
and accepts it only on exact git-blob match (repos pinned in
`phase3_micropilot_pins.json`) or on exact byte length plus an identical
re-parsed edge multiset versus `edges.csv`. Repos that cannot be recovered
this way are excluded and reported, never replaced by HEAD.

**Drift control.** The registry has moved since Layer 1 ran, and the local
npm is 10.9.2 (Layer 1's tool lock records 10.9.7). Before any alternative,
each population substitution's *original* candidate is re-run under the same
conditions ("attempt 0"). Concordance with the recorded Layer 1 outcome is
reported. An edge whose attempt 0 now comes back `OK` is reported as
`DRIFT_OK` and is **not** credited as exists-any recovery (its alternatives
are still tried and reported, as exploratory).

**Estimands (pre-specified).**
- Primary: exists-any resolution-confirmed rate over all 2,349 proxy-positive
  edges = (Layer 1 `OK` + edges with an alternative `OK`) / 2,349, both
  edge-weighted (repo-clustered percentile bootstrap, 5,000 resamples, seed
  20260928, as in the Layer 1 addendum) and repo-weighted (macro mean, same
  bootstrap), reported next to the single-candidate rate.
- Secondary: alternative-`OK` rate within the 1,711-edge population; share
  `NO_ALTERNATIVE`; distribution of the attempt index of the first `OK` and
  of attempts used by edges that never reached `OK`; outcome counts per
  attempt; attempt-0 concordance.
- Anything else computed from these data is labelled exploratory.

**Outputs.** `results/processed/layer1_alt_v1_plan.json` (every edge's retry
list, built deterministically by `scripts/layer1_alt_resolution.py plan` and
committed before the first attempt), `results/processed/layer1_alt_v1_attempts.jsonl` (append-only,
one row per `(repo, package, version)` attempt, resumable) and
`results/processed/layer1_alt_v1_summary.json` (from
`scripts/layer1_alt_report.py`), registered in `docs/claims.json`.

### 7.1 Amendment 2026-10-05: execution host (before any valid attempt)

The first run of `layer1_alt_v1` was stopped after 666 attempts because the
host is native Windows, not the Linux machine Layer 1 ran on: npm refused
`socketio/socket.io`'s *existing* tree with `EBADPLATFORM` (its dependency
`eiows@7.1.0` excludes win32), so 223 attempts were recorded as
`RESOLUTION_FAIL` when they measured nothing. npm's `--os`/`--cpu` overrides
do not reach this check (`build-ideal-tree.js` calls `checkPlatform` without
the environment in both npm 10.9.2 and 10.9.7). That run is kept unedited as
`results/processed/layer1_alt_v1_attempts.invalid_win32_npm10.9.2.jsonl` and
is not used. Changes for the valid run, made before it started:

1. Attempts use npm **10.9.7** (the version in `data_manifest/tool_lock.json`)
   via `PDR_NPM_CLI`; every attempt row records `npm_version` and `host_os`.
2. `EBADPLATFORM` is recorded as `PLATFORM_BLOCKED`, an environment outcome
   outside the frozen taxonomy. A repo whose attempt 0 is platform-blocked gets
   no further attempts. Its edges stay in every denominator and are **not
   credited** (the primary estimate is therefore a lower bound); an upper
   bound that credits every blocked edge having at least one alternative is
   reported beside it. Running those edges needs a Linux host (WSL2).

For the 244 substitutions outside socket.io, the invalid run's attempt 0
agreed with the recorded Layer 1 outcome in every case, which suggests the
Windows host does not otherwise change resolution; the valid run re-measures
this.

### 7.2 Correction 2026-10-05: the Phase 1 lockfiles were never missing

Section 7's "Inputs that had to be recovered" paragraph is wrong. The 45
Phase 1 lockfiles are tracked in git under `results/raw/resolve_phase1/`; a
truncated directory listing (`ls ... | head`) was misread as showing only
`_manifest.json`. `scripts/recover_phase1_lockfiles.py` then rewrote the
files in place. For 42 repos the rewritten bytes were identical to the
tracked files (no git diff). For 3 (`mochajs/mocha`, `nodejs/undici`,
`rollup/rollup`) the accepted blob had the same length and the same parsed
edge multiset but a different root `"version"` field, so the
length-plus-edges criterion was not sufficient evidence of identity.

What was done: the 3 tracked files were restored from git; the script now
pins by the exact blob ID of a present lockfile and never overwrites it, and
the 3 entries in `results/processed/phase1_lockfile_recovery.json` were
regenerated that way (status `PINNED`). All 29 `layer1_alt_v1` attempts for
those 3 repos were re-run against the restored files into
`results/processed/layer1_alt_v1_attempts.recheck_tracked_lockfiles.jsonl`:
every outcome and every `n_ripple` matched the main run, so no reported
number changes. The recovery record remains useful as a commit pin for each
repo's analyzed lockfile.
