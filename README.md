# PDR v4.1 FROZEN-GO (8.5/10) — Provenance Debt at Resolution + Loss-Regression (SECONDARY)

**RQ (CENTERPIECES FROZEN, idea iteration STOPS):** How much deficiency at resolution is semantically repayable in range (recoverability CENTERPIECE), how much survives deployability at what excess cost vs Baseline0/1 (SECOND centerpiece) — plus secondary loss-regression enrichment? AVAIL-VAR 🔴 KILLED (frontier occupied); PDR CHOSEN. Run PDR-G1 now.

**Status:** PDR-G1 v4 kill test (see `PDR_Proposal_and_Implementation_Plan.md` §7 + §11 kill matrix). No full build until GO (A OPG era-controlled + B semantic PD + C some PD non-deployable + D excess cost PRIMARY (+regression bonus) + E lockfile/era/requery robustness). Gate is **artifact, not novelty**. Existing checkers (audit signatures, provenance-action incl. downgrade/repo-branch, trustPolicy) are Baseline 1; PDR characterizes prevalence/cost/behavior. Regression SECONDARY only (kill independently).

**Integrity + scope boundary:** provenance = origin/integrity, NOT safety. Mastra shape in-scope; RedHatInsights valid-attestation shape out-of-scope. Builder/path change = enrichment signal, never compromise proof without labels.

## Quick start (Windows PowerShell 5.1, `py`)

```powershell
py -m pytest tests/ -q
py scripts/fetch_corpus.py --config configs/experiments/kill_v1.yaml
py scripts/check_provenance.py --in results/raw/resolve/ --out results/raw/provenance/edges.csv
py scripts/analyze_kill.py --in results/raw/provenance/edges.csv --out results/processed/kill_summary.json
py scripts/scan_regression.py --config configs/experiments/regression_v1.yaml
```

ASCII-only prints (cp1252). Frozen: npm/node/checker versions + query dates in `data_manifest/tool_lock.json`.

## Layout

* `pdr/` — resolve (scopes+strata), provenance (lowest+best), regression (loss+builder), policy (direct AND full-tree artifact)
* `configs/experiments/` — kill_v1, census_v1, breakage_v1, regression_v1, main_v1
* `scripts/` — fetch/check/analyze/regression/census/breakage/figures/tables
* `tests/` — 5-state+unknown, recoverable!=safe, regression NA handling
* `docs/` — literature matrix (enforcement prior art + Smells + valid-attestation cases), scope_boundary (Mastra vs RedHat)
* `data_manifest/` — tool + query-date locks
* `results/raw|processed|publication/` — immutable chain (memo -> kill_memo.md)
* `paper/` `figures/` `tables/` — only after GO

## Gate v4.1 FROZEN (SUCCESS = A-F, no relaxation)

SUCCESS needs the COMBINED pattern: A meaningful OPG era-controlled + B meaningful semantic PD + C nontrivial semantic→deployable gap + D measurable excess cost vs B0/B1 + E robustness (lockfile/floating, direct/tree, era, requery) + F unknowns ≤20%. Regression bonus only.
ACCEPT AS KILLS (never reframe): high-OPG/almost-no-PD → thesis weakens; high-PD/almost-all-deploy/near-zero-cost → enforcement cheap → flagship weakens; vanishes under era/lockfile → artifact → KILL. Headline: `X% lacked (OPG); Y% semantically recoverable (PD); only Z% resolution-preserving deployable (+ R% regressed, secondary)`. Idea iteration stops — new experiment ID required for any protocol change.

---

## Pilot-run status (this implementation)

A pilot-scale run of `scripts/fetch_corpus.py` → `check_provenance.py` →
`analyze_kill.py` → `scan_regression.py` against 7 real repos (19,148 edges)
has been executed. Results, the honest A–F gate breakdown, and everything
NOT yet measured (C, D) are in `docs/gate_status.md` and
`PILOT_RUN_REPORT.md` at the repo root — read those before this file's
"Gate v4.1 FROZEN" section for the current, evidence-backed status rather
than the pre-run target state described above.
