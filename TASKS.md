# TASKS.md — ordered backlog

Legend: **[AUTO]** Claude Code may do it end-to-end under the rules in
`CLAUDE.md`. **[HUMAN-GATE]** stop, show the human what you have, and wait.
Do tasks in order unless a task says otherwise. Tick the box and add a
one-line dated note when done. Each AUTO task ends with: tests pass,
`scripts/check_claims.py` passes, docs updated, committed.

## Track 1 — strengthen what already exists (no Docker needed)

- [ ] **T1 [AUTO] Layer 1 "exists-any" retry** (`layer1_alt_v1`, new experiment ID).
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
- [ ] **T2 [AUTO] Ripple-size sensitivity.** Thresholds declared here, before
  computing: treat a candidate as OK if it changes at most k other top-level
  packages, k in {0, 1, 2, 5, 10}. Pure analysis of existing
  `phase2_layer1_results.jsonl` (`n_ripple` is stored). Label as a sensitivity
  analysis; do not replace the k=0 definition. *Done when:* table + clustered
  CIs in `docs/phase2_layer1_results.md`.
- [ ] **T3 [AUTO] `scripts/layer1_report.py`** producing
  `results/processed/layer1_summary.json` (edge-weighted, repo-weighted,
  clustered CIs, per-repo table, concentration). Register in `claims.json`.
- [ ] **T4 [AUTO] Related-work pass.** (Started 2026-10-04: verified rows in `docs/audit_v2.md`.) Close the gap found in review: the
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
- [ ] **T5 [HUMAN-GATE] Docker environment.** Human installs Docker (Windows:
  Docker Desktop + WSL2) and runs Claude Code inside WSL. Resolve the real base
  image digest (`docker pull node:20-bookworm-slim && docker inspect
  --format='{{index .RepoDigests 0}}' node:20-bookworm-slim`), replace the
  placeholder in `isolated_worker/Dockerfile`, pin the mitmproxy image version
  too, then run `bash isolated_worker/setup.sh`. Claude Code may prepare exact
  commands and review output; the human executes.
- [ ] **T6 [AUTO, write before T7] `scripts/phase3_report.py`.** Pre-specify the
  analysis *before any result exists*: outcome counts, `pdr.phase3.funnel`,
  paired deltas for install/audit/test (frozen primary: test-failure delta),
  per-repo table, attestation-gain summary. Test it on synthetic fixtures only.
- [ ] **T7 [HUMAN-GATE] Decide `pdr_test_runs` (1 or 2) before the first real
  run.** Review evidence that single-run npm test outcomes can be unstable;
  PDR is currently run once while B0 runs twice, which is asymmetric. Record
  the decision as a dated amendment in `docs/phase3_protocol.md`.
- [ ] **T8 [AUTO with stops] Execute Phase 3 in the order of
  `docs/phase3_protocol.md` Section 9.** Stop for the human after each of:
  (a) `--selftest` result (network isolation really verified, denial visible in
  the proxy log); (b) `--dry-run` command review; (c) `--limit 2` records
  inspected against `pdr.phase3.validate_record`; (d) audit-output parser
  checked against real `npm audit signatures` output and fixed if wrong (the
  regexes are unvalidated); (e) full 23-experiment micro-pilot. Tag
  `freeze/phase3-worker-v1` once the worker image is final.
- [ ] **T9 [HUMAN-GATE] Verdict on the micro-pilot.** Present the funnel and
  deltas with all limitations (hermetic-test screen selection effect, small
  n). Human decides whether to scale. Do not choose the paper's story.

## Track 3 — scale, analysis, paper

- [ ] **T10 [AUTO after T9] Scale-up (Phase 4).** Needs `GITHUB_TOKEN` from the
  human (environment only). New experiment ID and a newly frozen, hash-locked
  manifest: larger corpus with popularity/age metadata, 100–200
  Layer-1-confirmed candidates for Layer 3. Selection stays outcome-blind.
- [ ] **T11 [AUTO] Final analysis + figures.** Funnel figure, forest plot of
  repo-clustered estimates, subgroup tables, sensitivity analyses, failure
  taxonomy. Every number registered in `claims.json`.
- [ ] **T12 [AUTO, then HUMAN-GATE] Paper draft** in `paper/` (IEEEtran
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
