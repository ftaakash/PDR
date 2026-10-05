# Experiment `layer1_alt_v1` results: does trying lower provenance-bearing versions help?

Design: `docs/phase2_protocol.md` Section 7 (pre-registered, tag
`freeze/layer1-alt-v1`) and amendment 7.1 (execution host). Run 2026-10-05,
npm 10.9.7 (the tool-locked version) on Windows. Scripts:
`scripts/layer1_alt_resolution.py` (plan + run),
`scripts/layer1_alt_report.py` -> `results/processed/layer1_alt_v1_summary.json`.
Raw: `results/processed/layer1_alt_v1_attempts.jsonl` (892 attempts),
plan: `results/processed/layer1_alt_v1_plan.json`. All figures below are
registered in `docs/claims.json` (`layer1_alt_v1`).

## Headline: almost nothing changes

| Estimand (all 2,349 proxy-positive edges, 40 repos) | Single candidate (Layer 1) | Exists-any (this experiment) |
|---|---|---|
| Edge-weighted OK rate [95% clustered CI] | 27.16% [18.0, 40.1] (638) | **27.67% [18.2, 41.5]** (650) |
| Repo-weighted OK rate [95% clustered CI] | 52.3% [41.5, 63.0] | **52.7% [42.0, 63.6]** |

Trying up to five lower provenance-bearing in-range versions recovers
**12 of the 1,711** edges whose single candidate failed (0.7% edge-weighted,
CI [0.0, 2.8]; 1.5% repo-weighted, CI [0.0, 4.4]). The 12 come from three
repos (`npm/cli` 9, `sinonjs/sinon` 2, `webpack-contrib/mini-css-extract-plugin`
1) and six distinct substitutions, five of them `@babel/*` or `browserslist`
patch versions. Layer 1's "tried only the highest version" limitation was
real but, on this corpus, **not material**: the single-candidate rate is a
close lower bound of the exists-any rate, not a large under-count.

This is a negative result for the hope that RQ2's "any version" framing would
recover substantially more, and it should be reported as such.

## Why: alternatives either do not exist or ripple the same way

| Edge status (1,711 Layer 1 RIPPLE / PEER_CONFLICT edges) | n |
|---|---:|
| `NO_ALTERNATIVE` (no other provenance-bearing, in-range, in-tolerance version below the original) | 524 |
| `ALT_EXHAUSTED` (every alternative tried failed) | 791 |
| `ALT_OK` (an alternative resolved cleanly) | 12 |
| `PLATFORM_BLOCKED` (`socketio/socket.io`, see below) | 384 |

First-OK attempt index: 1 (5 edges), 2 (5), 4 (2). Edges that exhausted their
alternatives used 1 (546), 2 (57), 3 (7) or 5 (181) attempts. Across attempt
indexes the failures are overwhelmingly `RIPPLE` (775 of 803 at index 1),
which matches the reading of Layer 1: ripple comes from re-resolving the
package's surrounding tree, not from which provenance-bearing version is
picked. Lower versions of the same package line pull the same neighbours.
The provenance gap is also often a single release: many packages gained
attestations only at their most recent release, so there is nothing lower to
try.

## Drift control: replication is exact where it could run

Every original candidate was re-run first ("attempt 0"). For the 435
substitutions the host could run, the outcome matched the recorded Layer 1
outcome in every case (404 RIPPLE -> RIPPLE, 31 PEER_CONFLICT ->
PEER_CONFLICT; edges: 1,272 + 55). No edge was `DRIFT_OK`. Registry movement
since Layer 1 and the Windows host did not change any runnable result.

## Limitation: socket.io could not be run on this host

`socketio/socket.io` (384 edges, all Layer 1 `RIPPLE`, 22% of the
population) depends on `eiows@7.1.0`, which excludes win32; npm refuses the
existing tree with `EBADPLATFORM` before any substitution, and npm's `--os`
override does not reach that check (amendment 7.1). Those edges stay in every
denominator and are not credited, so 27.67% is a lower bound. Of the 384,
209 have no alternative at all; 175 have at least one. If all 175 recovered
(an extreme assumption given 0.7% elsewhere), exists-any would be **35.12%
[28.7, 46.0]** edge-weighted and **53.9% [43.5, 64.3]** repo-weighted. Closing
this needs a Linux host (WSL2); the same command reruns only the missing
attempts.

## Process notes

- I first believed the Phase 1 lockfiles were missing and "recovered" them
  from git history; they were in fact tracked in the repository, and three
  were overwritten with near-identical blobs (root `"version"` differed). They
  were restored and their 29 attempts re-run with identical outcomes; see
  `docs/phase2_protocol.md` Section 7.2.
- A first run on npm 10.9.2 was stopped once the `EBADPLATFORM` problem
  appeared; it is kept unedited as
  `results/processed/layer1_alt_v1_attempts.invalid_win32_npm10.9.2.jsonl`
  and is not used.
- No versions were excluded by the `T_cut` rule (the plan records 0).
