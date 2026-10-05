# Phase 3 micro-pilot results (Layer 3, 23 experiments) -- verdict: REWORK

Run: GitHub Actions run 37309704666, 2026-10-05, worker frozen at tag
`freeze/phase3-worker-v1`. Raw: `results/processed/phase3_micropilot_results.jsonl`
(23 records, all pass `pdr.phase3.validate_record`). Analysis: the
pre-specified `scripts/phase3_report.py` (`docs/phase3_protocol.md` Section 10)
-> `results/processed/phase3_summary.json`. Counts below are registered in
`docs/claims.json` (`phase3_micropilot`).

## Pre-specified result

| Outcome | n |
|---|---:|
| OK | 9 |
| TEST_FAIL | 12 |
| TEST_FLAKY | 1 |
| INSTALL_FAIL | 1 |

**The pre-specified REWORK flag is raised.** 13 of 23 experiments (56.5%) have
an invalid B0 baseline (B0 install failed, or B0 tests failed or were flaky),
above the 30% threshold in `docs/audit_v2.md`. Under that rule the
micro-pilot is an infrastructure REWORK, not a project verdict, and **no
Gate D (test-failure delta) claim is made from this run.** For the record,
the pre-specified primary test delta is +0.053 [0.000, 0.176] over 19 pairs,
from a single new failure; most of those pairs are B0-fail/PDR-fail pairs that
carry no information.

## Where the substitution can be judged (B0 passes both runs): 10 experiments

- **9 OK**: PDR installed, ran lifecycle scripts, introduced no new peer
  problem, preserved audit-signature status, and passed the tests on both
  runs (`caolan/async` x2, `isaacs/minimatch`, `isaacs/node-glob`,
  `motdotla/dotenv`, `terser/terser`, `tj/commander.js`, `winstonjs/winston` x2).
- **1 TEST_FAIL** (`webpack-contrib/mini-css-extract-plugin`, `node-releases@2.0.57`,
  overrides mode): B0 passes twice, PDR fails twice. The failing step is the
  repo's own **lint** (`lint:code`: 6 errors, `package-json/order-properties`),
  which runs inside its `npm test`. Most likely cause (inferred from the log,
  not yet confirmed by a controlled rerun): the harness's added `overrides`
  field in `package.json` breaks the repo's package.json key-order lint rule.
  If confirmed, this is a **measurement artifact**, not a behavioural effect
  of the provenance-bearing version.

## Why the baselines failed (from the B0 logs; exploratory classification)

| Cause | Experiments |
|---|---|
| Worker's Node 20 is too old for the pinned repo (`--experimental-transform-types`, `fs/promises.glob`, `zlib.zstdCompressSync`, "requires >=22.18.0") | `google/zx`, `jshttp/content-type`, `npm/node-tar`, `webpack/webpack-cli` |
| Lint step fails on Node 20 / ESLint config (`cheerio`, ESLint v9 flat-config message in `showdown`) | `cheeriojs/cheerio`, `showdownjs/showdown` |
| Tool missing from image (`pnpm: not found`; also a refused `registry.yarnpkg.com`) | `commitizen/cz-cli` |
| Jest worker killed (`SIGKILL`, 4 GB cap) | `stylelint/stylelint` x2 (B0 flaky) |
| Tests need an external URL ("import option should work with absolute URLs") | `webpack-contrib/css-loader` x2 |
| `npm ci` usage error in a workspaces monorepo (B0 never reached tests) | `npm/cli` |
| Git dependency from `github.com`, refused by the allowlist | `markedjs/marked` (INSTALL_FAIL on both arms) |

**The largest single cause is a worker-image mismatch:** the Dockerfile uses
Node 20, while `data_manifest/tool_lock.json` records Node v22.22.2 for every
earlier phase. Four repos fail outright on Node 20.

## What did work

- Isolation held: the network self-test passed, and the only hosts refused
  during experiments were `registry.yarnpkg.com` and `github.com`, both logged.
- `npm audit signatures` parsing on real output: every parseable pair shows an
  attestation gain of +1 to +3, matching the intended substitution, which
  independently corroborates the Phase 1 `dist.attestations` classifier.
- Only the substituted package changed in most PDR trees (tree diff 1), as
  Layer 1 `OK` implies; `npm/cli` (1,186) is the exception because its B0
  never installed.

## Limitations

n = 23 (10 judgeable), 19 repositories, hermetic-test screen selection effect
(`docs/phase3_protocol.md` Section 6), single GitHub runner type, Node 20 worker.
None of the counts above supports a claim about test-survival rates in
general.
