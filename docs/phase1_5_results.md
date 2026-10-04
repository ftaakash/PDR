# Phase 1.5 results: tiny resolution-verification pilot

**Superseded by the full-scale run.** `docs/phase2_layer1_results.md`
ran this same check against all 2,349 candidates, not just 21, and found
the confirmation rate this small pilot estimated (85.7%) did not hold --
the full run found 27.16%. This file is kept as the historical record of
the micro-pilot that justified building the full Layer 1 script in the
first place; read the Layer 1 doc for the current numbers.

Before building the full Gate C/D harness, per the reviewer's
recommendation, this ran a small **real** experiment testing the single
most important open methodological question flagged in
`docs/methodology_freeze.md` Section 6: does `pdr/policy.py`'s local
semver-diff proxy for "resolution-preserving" agree with what npm's actual
resolver does once you force the candidate for real?

**Scope and safety, stated plainly:** this used
`npm install --package-lock-only --ignore-scripts` only -- resolves
against the live registry, writes no `node_modules`, executes no package
code. It is lighter than both the "structural" and "behavioral" modes in
the full sandbox spec (Section 7), which are correctly deferred to Phase 2
until the isolated-worker infrastructure exists. Nothing in this pilot ran
untrusted code from the packages under study.

## Selection

21 `DEFICIENT_RESOLUTION_PRESERVING` candidates, fixed before running (not
cherry-picked after seeing outcomes), across 5 repos chosen for strata
diversity: `axios/axios` (5), `koajs/koa` (2), `tj/commander.js` (2),
`redis/node-redis` (6, monorepo), `mozilla/source-map` (6, lockfileVersion
v2). Script: `scripts/phase1_5_resolution_check.py`. Raw output:
`results/processed/phase1_5_resolution_check.json`.

## Result

| | n | % |
|---|---:|---:|
| npm resolution succeeded at all | 21/21 | 100% |
| candidate actually applied by npm's real resolver | 21/21 | 100% |
| **triggered a ripple** (>=1 other top-level package's resolved version changed as a side effect) | 3/21 | 14.3% |
| **fully confirmed** (applied cleanly, zero ripple -- proxy and real resolution agree) | 18/21 | **85.7%** |

## The ripple cases, in full (this is the finding)

```text
tj/commander.js:  @babel/code-frame 7.29.0 -> 7.29.7
  side effect: @babel/helper-validator-identifier  7.28.5 -> 7.29.7

mozilla/source-map:  espree 9.4.1 -> 9.6.1   (occurred twice, same repo)
  side effects: acorn                8.8.1 -> 8.18.0
                eslint-visitor-keys  3.3.0 -> 3.4.3
```

The `espree` case is the clearest evidence of exactly what
`docs/methodology_freeze.md` Section 6 predicted: forcing `espree` to a
provenance-bearing candidate that looked like a clean minor bump (9.4.1 ->
9.6.1) in isolation actually pulls `acorn` from 8.8.1 to 8.18.0 -- a large
jump the local per-edge proxy had no way to see, because `acorn`'s own
resolved version is a hoisting/dedup consequence of `espree`'s declared
range, not something the `espree` edge's own semver diff encodes.

## Interpretation

This is a **tiny, non-representative sample** (21 candidates, 5 repos) --
it does not establish a precise disagreement rate for the whole corpus.
What it DOES establish, concretely and for real:

1. The screening-stage proxy is not equivalent to actual resolution, as
   flagged. At this small scale, the disagreement rate was 14.3%, not
   negligible.
2. All ripples observed were *expansions* (an unrelated package moved
   further from what was resolved before), which is the direction that
   would make Gate C's operational-viability check (peer conflicts, test
   breakage) more likely to fail than the local proxy alone would predict
   -- i.e., this pilot's finding, if it generalizes, would make Gate C/D
   results for the full harness *harder* to pass than a naive reading of
   Gate B's numbers alone would suggest.
3. None of the 21 resolutions *failed outright* -- structural viability at
   the resolution-only level was 100% in this sample. That's a mildly
   encouraging sign for Gate C's install-success sub-criterion specifically
   (separate from the ripple/peer-conflict sub-criteria).

## What this changes for Phase 2

The full Gate C/D harness must implement the two-stage design from
`docs/methodology_freeze.md` Section 6 for real (screening proxy ->
resolution-confirmed only), not just the local proxy alone -- a candidate
should not be counted as "resolution-preserving" for Gate C/D purposes
unless it passed the real-resolution check this script performs. The
`fetch package.json + overrides + npm install --package-lock-only
--ignore-scripts` pattern in `scripts/phase1_5_resolution_check.py` is
directly reusable as the first stage of the Phase 2 harness.
