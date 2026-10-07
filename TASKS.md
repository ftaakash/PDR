# TASKS.md — ordered backlog

Legend: **[AUTO]** Claude Code may do it end-to-end under the rules in
`CLAUDE.md`. **[HUMAN-GATE]** stop, show the human what you have, and wait.
Do tasks in order unless a task says otherwise. Tick the box and add a
one-line dated note when done. Each AUTO task ends with: tests pass,
`scripts/check_claims.py` passes, docs updated, committed.

## Track 1 — strengthen what already exists (no Docker needed)

- [x] **T1 [AUTO] Layer 1 "exists-any" retry** *(2026-10-05: done, `docs/phase2_layer1_alt_results.md`. Exists-any 27.67% [18.2, 41.5] edge / 52.7% repo vs 27.16% / 52.3% single-candidate; only 12 of 1,711 edges recovered. socket.io (384 edges) platform-blocked on Windows; needs a Linux rerun.)* (`layer1_alt_v1`, new experiment ID).
  *Why:* RQ2 asks whether *any* provenance-bearing in-range version exists;
  Layer 1 tried only the single highest. *Design first* (add a section to
  `docs/phase2_protocol.md` BEFORE running): for edges whose best candidate
  ended `RIPPLE` or `PEER_CONFLICT`, try the next provenance-bearing in-range
  versions in descending order, same minor/patch tolerance vs the resolved
  version, up to K=5, stop at first `OK`; record every attempt. Reuse
  `pdr.sandbox.patch_package_json_for_candidate` and the Layer 1 harness
  (host-safe: `--package-lock-only --ignore-scripts`). Needs packuments
  (cache is git-ignored; refetch). Output append-only JSONL. *Done when:*
  exists-any rate reported with repo-clustered CI next to the single-candidate
  rate; attempt-count distribution; regression test for the candidate-ordering
  function; `claims.json` extended.
- [x] **T2 [AUTO] Ripple-size sensitivity.** *(2026-10-05: done; table in `docs/phase2_layer1_results.md`, k=1 gives 41.4% edge / 65.1% repo vs 27.2% / 52.3% at k=0.)* Thresholds declared here, before
  computing: treat a candidate as OK if it changes at most k other top-level
  packages, k in {0, 1, 2, 5, 10}. Pure analysis of existing
  `phase2_layer1_results.jsonl` (`n_ripple` is stored). Label as a sensitivity
  analysis; do not replace the k=0 definition. *Done when:* table + clustered
  CIs in `docs/phase2_layer1_results.md`.
- [x] **T3 [AUTO] `scripts/layer1_report.py`** *(2026-10-05: done; reproduces the addendum figures, adds repo-weighted CI [41.5, 63.0]; registered as `layer1_summary`.)* producing
  `results/processed/layer1_summary.json` (edge-weighted, repo-weighted,
  clustered CIs, per-repo table, concentration). Register in `claims.json`.
- [x] **T4 [AUTO] Related-work pass.** *(2026-10-05: 14 sources opened and tabled in `docs/literature_matrix.md` with URLs and retrieval date; unverified items listed separately; novelty statement drafted. Gate G sweep still due before submission.)* (Started 2026-10-04: verified rows in `docs/audit_v2.md`.) Close the gap found in review: the
  dependency-update / breaking-update literature (semver update flow in npm,
  Dependabot compatibility and test-reliability studies, update-reproducibility
  work) next to the provenance literature. Open and read each source; fill
  `docs/literature_matrix.md` with URL, retrieval date, what it measures, and
  how PDR differs. Draft the novelty statement using the wording rule in
  `CLAUDE.md` #11. *Done when:* every row has a verified source; unverifiable
  claims from earlier chats are listed as unverified, not cited.

## Track 2 — Layer 3 on a Docker machine

- [ ] **T4b [HUMAN-GATE, optional] Optimizer upper bound.** `docs/audit_v2.md`
  found MaxNPM/PacSolve (ICSE 2023), a configurable npm solver. Decide whether
  to compare PDR's real-resolver recovery against an optimizer with a
  provenance objective on a subset. Strengthens Gate B; costs time.
- [x] **T5 [HUMAN-GATE] Docker environment.** *(2026-10-05: local Windows lacks Hyper-V; owner chose GitHub-hosted Ubuntu runners. Images pinned by digest, proxy fixed, self-test passed. `docs/phase3_protocol.md` Section 2.1.)* Human installs Docker (Windows:
  Docker Desktop + WSL2) and runs Claude Code inside WSL. Resolve the real base
  image digest (`docker pull node:20-bookworm-slim && docker inspect
  --format='{{index .RepoDigests 0}}' node:20-bookworm-slim`), replace the
  placeholder in `isolated_worker/Dockerfile`, pin the mitmproxy image version
  too, then run `bash isolated_worker/setup.sh`. Claude Code may prepare exact
  commands and review output; the human executes.
- [x] **T6 [AUTO, write before T7] `scripts/phase3_report.py`.** *(2026-10-05: done; analysis pre-specified in `docs/phase3_protocol.md` Section 10, tested on synthetic fixtures only. Found and fixed `paired_delta(..., "audit")` silently reporting a zero delta.)* Pre-specify the
  analysis *before any result exists*: outcome counts, `pdr.phase3.funnel`,
  paired deltas for install/audit/test (frozen primary: test-failure delta),
  per-repo table, attestation-gain summary. Test it on synthetic fixtures only.
- [x] **T7 [HUMAN-GATE] Decide `pdr_test_runs` (1 or 2) before the first real
  run.** *(2026-10-05: owner chose 2; `docs/phase3_protocol.md` Section 3.1, new outcome TEST_FLAKY.)* Review evidence that single-run npm test outcomes can be unstable;
  PDR is currently run once while B0 runs twice, which is asymmetric. Record
  the decision as a dated amendment in `docs/phase3_protocol.md`.
- [x] **T8 [AUTO with stops] Execute Phase 3 in the order of
  `docs/phase3_protocol.md` Section 9.** Stop for the human after each of:
  (a) `--selftest` result (network isolation really verified, denial visible in
  the proxy log); (b) `--dry-run` command review; (c) `--limit 2` records
  inspected against `pdr.phase3.validate_record`; (d) audit-output parser
  checked against real `npm audit signatures` output and fixed if wrong (the
  regexes are unvalidated); (e) full 23-experiment micro-pilot. Tag
  `freeze/phase3-worker-v1` once the worker image is final. *(2026-10-05: all stops done on GitHub runners; pre-specified REWORK flag raised, 13/23 invalid baselines; `docs/phase3_micropilot_results.md`.)*
- [x] **T9 [HUMAN-GATE] Verdict on the micro-pilot.** *(2026-10-07: owner chose to scale up (T10).)* Present the funnel and
  deltas with all limitations (hermetic-test screen selection effect, small
  n). Human decides whether to scale. Do not choose the paper's story.

## Track 3 — scale, analysis, paper

- [x] **T10 [AUTO after T9] Scale-up (Phase 4).** *(2026-10-07: `scale_v1`, 160 pinned repos, 262,066 edges; Layer 1 OK 28.51%; Layer 3 110 experiments in 31 testable repos, 0 attributable failures; `docs/phase4_results.md`.)* Needs `GITHUB_TOKEN` from the
  human (environment only). New experiment ID and a newly frozen, hash-locked
  manifest: larger corpus with popularity/age metadata, 100–200
  Layer-1-confirmed candidates for Layer 3. Selection stays outcome-blind.
- [x] **T11 [AUTO] Final analysis + figures.** *(2026-10-07: `scripts/make_figures.py` builds funnel, forest, ripple figures, tables and `paper/numbers.tex` from `claims.json` only.)* Funnel figure, forest plot of
  repo-clustered estimates, subgroup tables, sensitivity analyses, failure
  taxonomy. Every number registered in `claims.json`.
- [ ] **T12 [AUTO, then HUMAN-GATE] Paper draft** *(2026-10-07: draft done, `paper/main.tex` -> `paper/main.pdf`, 4 pages; awaiting owner review of every claim, author block, acknowledgment and the `check` notes in `refs.bib`.)* in `paper/` (IEEEtran
  LaTeX). Contribution framed as an empirical study of practical recoverability
  of missing npm provenance, not a new security system. Threats-to-validity
  taken from the limitations already documented. Only verified citations.
  Human reviews every claim before anything is shared.
- [ ] **T13 [HUMAN-GATE] Release.** Artifact README, license choice, git tag,
  optional Zenodo DOI, arXiv. Nothing is published without approval.

## Deliberately later

- Cross-ecosystem replication (e.g. PyPI attestations) as a *separate*
  experiment ID, only after the npm paper is drafted.
- A general "dependency-intervention framework" refactor: only after the
  paper ships; until then it would delay the paper.
