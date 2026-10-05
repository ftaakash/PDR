# Phase 3 protocol (frozen before any behavioral execution)

Phase 3 answers the two questions Phase 2 deliberately left open (Layer 3):
does provenance recovery remain viable after real package execution and
tests, and does PDR substitution introduce measurable cost versus the
existing baseline. This document is written and the supporting code built
and tested **before any Layer 3 result exists** -- `pdr/phase3.py`'s
classification logic is pinned by `tests/test_phase3_logic.py` against
synthetic fixtures only, so interpretation cannot drift toward whatever the
first real numbers happen to look like.

**Status, stated plainly:** the isolated-worker infrastructure below is
written and unit-tested (`tests/test_isolated_worker.py`,
`tests/test_phase3_logic.py`, `tests/test_layer1_patch_logic.py`'s shared
patch logic) but **has not been executed against a live Docker daemon** --
none exists in the session that built it. First real use of any of this
must start with `isolated_worker/orchestrate.py --selftest`, not with real
experiments; see Section 9.

## 1. Estimand (does not replace Phase 1's)

Per explicit review feedback: Layer 3 introduces a **new, conditional**
estimand, layered on top of -- never substituted for -- Phase 1's primary
estimand.

- **Phase 1 primary (unchanged):** edge-weighted proportion of deficient
  dependency edges having a recoverable provenance-bearing alternative.
- **Phase 3 conditional:** among Layer-1-resolution-confirmed candidates,
  the proportion that remain operationally viable after structural
  installation, lifecycle execution, provenance verification, and repository
  tests.

```
Population
  -> Provenance deficient
    -> Screening-positive (Gate B proxy)
      -> Resolution-confirmed (Layer 1)
        -> Structurally viable (Layer 2 -- done, small sample)
          -> Behaviorally viable (Layer 3 -- this document)
            -> Test-surviving
```

Each arrow is a different question. Reporting only the final percentage
would hide exactly the information the funnel (Section 5) exists to show:
attrition at every layer.

## 2. Isolation architecture

```
Host (this project's dev/CI environment)
  |
  +-- pdr-internal docker network (--internal: NO route to the outside
  |     world at all, from any container on it, except via the proxy)
  |
  +-- pdr-proxy container (mitmproxy + isolated_worker/proxy_allowlist.py)
  |     - the ONLY container attached to both pdr-internal and a normal,
  |       outside-reaching network
  |     - allowlist: registry.npmjs.org, tuf-repo-cdn.sigstore.dev,
  |       fulcio.sigstore.dev, rekor.sigstore.dev -- everything else 403s,
  |       logged (`docker logs pdr-proxy`) so denials are auditable, not
  |       just silently dropped
  |
  +-- one disposable pdr-worker:phase3-v1 container PER (candidate, arm):
        --cap-drop=ALL --security-opt=no-new-privileges --read-only
        --network=pdr-internal (workers are NEVER on any other network)
        --user 10001:10001 (non-root, fixed UID -- isolated_worker/Dockerfile)
        --memory 4g --memory-swap 4g --cpus 2 --pids-limit 512
        tmpfs /work (rw,exec -- node_modules and native builds need exec;
                     size-capped, wiped on container removal)
        tmpfs /tmp  (rw,noexec -- no code execution needed there)
        ONE bind mount: the pinned repo snapshot, read-only, nothing else
        NO credentials, NO docker socket, NO host mounts beyond the snapshot
        destroyed immediately after producing its one result (`docker rm -f`
        in orchestrate.py's run_arm(), in a `finally` block)
```

`isolated_worker/orchestrate.py`'s `assert_command_safe()` checks every
`docker run` invocation against this spec BEFORE executing it -- required
flags present, forbidden flags (`--privileged`, host network/pid/ipc, the
docker socket, `--cap-add`, extra devices, non-snapshot mounts,
credential-shaped env vars) absent. `tests/test_isolated_worker.py` locks
this in with adversarial inputs (missing flags, injected forbidden flags,
mutated mounts) so a regression here fails CI, not a real run.

**Registry-only network was wrong.** `docs/phase2_layer2_results.md` found
`npm audit signatures` needs Sigstore's TUF CDN; the allowlist above
includes it from the start, fed back from that finding rather than
rediscovered here.

## 3. Experiment design: B0 / PDR arms, B1 folded into audit

- **B0** -- the pinned repo snapshot, unmodified. Run to completion (all
  stages) so every PDR result has something to be compared against, not
  just installed-and-hope.
- **PDR** -- the same snapshot, `package.json` patched with the Layer-1
  substitution (`pdr.sandbox.patch_package_json_for_candidate`, the exact
  function `tests/test_layer1_patch_logic.py` already covers), then
  re-resolved and run through every stage.
- **B1** is not a third install: per `docs/methodology_freeze.md` Section 8,
  it is `npm audit signatures` run on the B0 tree. The audit delta compares
  PDR's audit stage against B0's, not against a separate baseline run.
- **B0 tests run twice** (`b0_test_runs=2`), PDR once. This is the cheapest
  available flakiness signal: `pdr.phase3.b0_test_status` returns `FLAKY`
  when the two B0 runs disagree, and `pdr.phase3.paired_delta` excludes
  flaky-B0 pairs from the test-stage delta entirely (a "new" PDR test
  failure against a flaky baseline is not evidence of anything). This is a
  cost/rigor trade-off stated openly: it catches gross flakiness, not rare
  flakiness, and PDR itself is never re-run to check its own stability.

Candidate source: **only** Layer-1 `outcome == "OK"` candidates
(`results/processed/phase2_layer1_results.jsonl`) -- Section 4's `RIPPLE`
and `PEER_CONFLICT` candidates are not promoted, unchanged from Layer 2's
rule.

## 4. Stages and failure taxonomy

```
resolve -> install -> lifecycle -> peer -> audit -> test
```

`resolve` only runs for the PDR arm (B0's tree is already resolved by
construction). `install` failure stops the arm. Later stages still run and
are recorded even if `peer` or `audit` looks concerning, since a real
research question here is exactly how far into the pipeline problems
appear.

| Outcome | Meaning |
|---|---|
| `RESOLUTION_FAIL` | PDR's re-resolution step failed |
| `INSTALL_FAIL` | `npm ci --ignore-scripts` failed |
| `LIFECYCLE_FAIL` | `npm rebuild` / root `prepare` script failed |
| `PEER_CONFLICT` | new problem in `npm ls --all` vs. B0, or an `ERESOLVE` at resolve/install |
| `AUDIT_SIGNATURE_CHANGE` | parsed `npm audit signatures` counts got worse vs. B0 (more invalid/missing) |
| `TEST_FAIL` | attributable test failure (Section 3's flakiness rule applied) |
| `NO_BEHAVIORAL_CHANGE` | PDR installed but the resulting tree is version-identical to B0 -- nothing was actually tested |
| `TIMEOUT` / `RESOURCE_LIMIT` | stage-level, from the worker's own recorded timing/OOM signal |
| `OK` | reached `test`, tree differs from B0, no attributable failure at any stage |

`pdr/phase3.py`'s `classify_pair()` implements first-failure-wins over this
exact stage order and is the ONLY place this logic lives -- the JSONL
records store raw per-stage data, not a pre-baked verdict, so re-running
`classify_pair` against unchanged raw data after a taxonomy fix (the kind
Phase 2 needed twice) never requires re-executing anything in a container.

**Attribution.** A PDR failure only counts toward a delta if B0 reached and
passed the same stage (`classify_pair`'s `attributable` dict) -- a repo
whose tests are already broken on B0 cannot manufacture a PDR "regression".
`docs/phase2_layer1_results.md`'s `nestjs/nest` case (30 candidates, one
root cause) is the reminder for why this matters: without pairing, one
already-broken repo can silently dominate a naive failure count.

## 5. Reporting: funnel with attrition at every layer, not one final number

`pdr.phase3.funnel()` reports, per stage: how many candidates entered, how
many were attributable, how many passed, how many failed, and the pass
rate among attributable candidates -- not just a final test-survival
percentage. `tests/test_phase3_logic.py::test_funnel_is_monotone_and_attribution_aware`
locks in that entering-counts are non-increasing and that a B0-also-fails
candidate is excluded from a stage's attributable denominator.

## 6. Micro-pilot: frozen allocation, outcome-blind selection

Per explicit review feedback: start with 20-30 candidates, diversified by
dependency-tree size, not the easiest packages, with the allocation frozen
**before** observing any Layer-3 outcome.

`scripts/phase3_select_micropilot.py` is that freeze, executable:

- **Experiment unit:** `(repo, dep_name, candidate_version)` -- several
  Layer-1-`OK` edges in one repo can imply the identical substitution (the
  patch depends only on this triple), so they collapse to one experiment,
  keeping all contributing `edge_id`s for traceability back to Phase 1.
- **Allocation (frozen constant, `ALLOCATION` in the script):** 5 small +
  10 medium + 10 large = 25 target. `very_large` excluded from the
  micro-pilot on compute-cost grounds, stated as a constant, not discovered
  post hoc.
- **Direct-field floor:** an early draft of the selection happened to pick
  only 1 direct-dependency-field experiment (of 23) because only ~5% of the
  pool is direct-field (`patch_package_json_for_candidate`'s other branch,
  `docs/phase2_layer1_results.md`'s EOVERRIDE fix) -- both patch mechanisms
  should be exercised, not just the common one. Fixed by adding a frozen
  `DIRECT_FLOOR` per bucket **before generating the committed manifest**,
  not after seeing it looked thin.
- **Hermetic-test screen:** a repo is excluded if its `test` script's TEXT
  mentions a browser/e2e/external-service keyword (`chrome`, `playwright`,
  `wireit`, `submodule`, `e2e`, `docker`, ...) or is on an explicit
  hard-coded exclusion list (`redis/node-redis`: needs a live Redis
  server). This is a text-pattern screen, not a judgment about whether
  those repos are less important -- they need a worker image with a
  browser or a service dependency, which this micro-pilot's image doesn't
  have. 9 of 40 candidate repos were excluded this way; **not silently**
  -- the manifest records which repos and why (`pool.repos_excluded_by_screen`).
- **Selection effect of the hermetic screen (a real limitation of the
  micro-pilot, stated up front):** the 9 excluded repos are not a random
  slice -- they are browser-/e2e-/service-dependent projects (`chai`,
  `karma`, `mocha`, `sinon`, `jquery`, `playwright`, `puppeteer`,
  `node-redis`, `source-map`), and several of them had HIGH Layer-1
  confirmation rates (`chai` 71%, `karma` 70.6%;
  `docs/phase2_layer1_results.md`). The micro-pilot therefore says nothing
  about test-survival for that class of project, and the screen also
  removed `mozilla/source-map`, which supplied 5 of Layer 2's 13 candidates
  and is why the small bucket is short (3 of 5). Any Layer 3 headline must
  be scoped to "repositories with hermetic, worker-runnable test suites".
- **Per-repo cap:** 3, so one large repo's pool doesn't dominate a bucket.
- **Determinism + tamper-evidence:** selection uses `random.Random(seed)`
  seeded per bucket (`SEED = 20260928`, matching Phase 1's bootstrap seed
  for consistency, not reused for any statistical reason); re-running the
  script against unchanged inputs produces a byte-identical manifest
  (verified: `configs/experiments/phase3_micropilot_manifest.sha256` is
  identical across two independent runs). `orchestrate.py` refuses to run
  unless the manifest's hash matches this committed file, so the cohort
  cannot be quietly edited between freezing and execution.

**Actual result of running the selector** (not hypothetical --
`configs/experiments/phase3_micropilot_manifest.json` exists):
Layer-1-OK edges: 638 -> 166 unique experiments after the hermetic screen
-> **23 selected** (small:3/5 -- pool shortfall, not backfilled, per the
frozen no-backfill rule; medium:10, large:10), spanning 19 repos, 4
direct-field + 19 overrides-mode substitutions.

## 7. Snapshot provenance: pinning what Phases 1-2 actually analyzed

Phases 1-2's lockfiles were fetched from each repo's HEAD **without**
recording a commit SHA -- fine for lockfile analysis, not fine for Layer 3,
which needs the repo's actual source (its test suite) at a commit
consistent with the analyzed lockfile. `scripts/phase3_pin_snapshots.py`
recovers this after the fact via `git hash-object` on the stored lockfile
bytes compared against `git rev-parse <sha>:package-lock.json` for
candidate commits (git metadata operations only -- no repository code is
ever executed to do this), confirmed additionally against the cached
`package.json`. Repos where no commit satisfies both are marked
`UNRESOLVED`, never silently pinned to current HEAD.

**Run for the micro-pilot's 19 repos: 19/19 PINNED, 0 unresolved.** 17 are
at HEAD; **2 are pinned to an older commit** (`cheeriojs/cheerio`,
`motdotla/dotenv`) -- those repos moved between Phase 1's lockfile fetch and
this pinning run, exactly the scenario this step exists to catch. (An
earlier draft of this paragraph said only one repo had moved; that was a
transcription error caught by re-checking the pins file against the text.)

## 8. Known unverified pieces (stated, not hidden)

- **`isolated_worker/Dockerfile`'s base-image digest is a placeholder.**
  This session has no reachable Docker registry to resolve a real digest
  against. `isolated_worker/setup.sh` refuses to build while the
  placeholder string is present, with an explicit message, rather than
  building against a silently-fake pin.
- **`pdr.phase3.parse_audit_signatures`'s regexes are unvalidated against
  real `npm audit signatures` output** -- `docs/phase2_layer2_results.md`
  never got a successful run to check the format against (the network
  wall). `audit_parse_ok` is explicitly `False` rather than silently `True`
  when parsing fails, and the FIRST micro-pilot run's job includes checking
  this parser against real output before trusting `AUDIT_SIGNATURE_CHANGE`
  classifications at any scale beyond that.
- **`orchestrate.py` has not run against a live daemon.** The command
  construction and safety gate are unit-tested; the actual `docker run`
  behavior, the proxy's real interception behavior, and the runner's
  in-container behavior are not yet observed. Section 9 is the plan for
  closing this gap in order, smallest risk first.

## 9. Execution order (not yet performed)

1. `isolated_worker/setup.sh` -- build the network, proxy, and image (will
   currently stop at the Dockerfile digest check; needs a real digest
   first).
2. `orchestrate.py --selftest` -- proves registry + TUF CDN are reachable
   through the proxy, a non-allowlisted host is denied AND that denial is
   visible in the proxy's own logs (closing the loop on Section 8's second
   unverified piece), and a direct/bypassing connection fails. Gated: no
   experiment can run without a passing self-test recorded for the exact
   current image ID.
3. `orchestrate.py --dry-run` -- print every `docker run` command for the
   full 23-experiment manifest without executing anything; visually confirm
   against Section 2 before spending compute.
4. `orchestrate.py --limit 2` -- two real experiments, one per arm each;
   manually inspect the raw JSONL record structure against
   `pdr.phase3.validate_record` before trusting the rest.
5. Full 23-experiment micro-pilot.
6. Debug whatever Section 8 surfaces (expected: at least the audit-parser
   regexes need adjusting against real output).
7. Only then: scale to the larger 100-200-candidate Layer-3 cohort the
   review recommends, via the same frozen selection script with an updated
   `ALLOCATION` -- a new, reviewable one-line change, not a rewrite.

## 10. Pre-specified analysis (added 2026-10-05, before any Layer 3 result exists; TASKS.md T6)

`scripts/phase3_report.py` reads `results/processed/phase3_micropilot_results.jsonl`
and writes `results/processed/phase3_summary.json`. It was written and tested
on synthetic fixtures only (`tests/test_phase3_report.py`); no real record
existed when it was committed. Everything below is fixed now; anything else
computed later is labelled exploratory.

1. **Record validity.** Every record is checked with
   `pdr.phase3.validate_record`; invalid records are listed and excluded, never
   repaired. Classification is always **recomputed** with
   `pdr.phase3.classify_pair` from the raw arms; the stored `classification`
   is ignored, so a later taxonomy fix needs no re-execution.
2. **Outcome counts** over experiments (unit: `(repo, package, candidate)`),
   plus a per-repo table.
3. **Funnel**: `pdr.phase3.funnel`, unchanged.
4. **Paired deltas** with `pdr.phase3.paired_delta` (repo-clustered bootstrap,
   5,000 resamples, seed 20260928) for `install`, `lifecycle` and `test`.
   **Frozen primary: the `test` delta** (flaky-B0 pairs excluded, as in
   Section 3). Per `docs/audit_v2.md`, the test delta is **not reported as a
   Gate D result if fewer than 10 attributable test pairs exist**; it is still
   printed, marked underpowered.
5. **Audit** is summarised from the parsed counts, not through
   `paired_delta`: pairs with `audit_parse_ok`, pairs classified
   `AUDIT_SIGNATURE_CHANGE`, and the change in `invalid`/`missing`. (While
   writing this section, `paired_delta(records, "audit")` was found to count
   every audit pair as "passed" on both arms, because audit is judged by
   comparison, not exit code; `pdr.phase3._stage_fail` now returns
   "indeterminate" for audit, so that call yields `n_pairs = 0` instead of a
   spurious zero delta. Regression test added.)
6. **Attestation gain** (`classify_pair`'s `attestation_gain`, the intended
   effect): n with a parseable audit on both arms, count with gain > 0, = 0,
   < 0, and the median.
7. **Both estimands** for the viability rate (`OK` share): experiment-weighted
   and repo-weighted, each with the repo-clustered CI from `pdr.stats.clustered`,
   over (a) all valid experiments and (b) experiments with a usable baseline
   (B0 installed and B0 tests `PASS`).
8. **Kill / downgrade flags** from `docs/audit_v2.md`, computed and printed,
   never acted on by the script: B0 invalid (install fails, tests fail or
   flaky) in more than 30% of experiments -> `REWORK`; `NO_BEHAVIORAL_CHANGE`
   in more than 50% of experiments that reached the end -> "Layer 3 adds
   nothing"; fewer than 10 attributable test pairs -> "no Gate D claim".
