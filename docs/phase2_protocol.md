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
