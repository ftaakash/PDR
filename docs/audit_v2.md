# PDR novelty re-check — audit v2 (B.Tech novelty standard)

Method: `research-kill-test` skill (Gates A–G). Standard: does PDR establish a
useful, reproducible finding that existing work does not already establish?
(Not: "has nobody ever combined these techniques?") Audit v1 = the external,
harsher kill-test audit run before this repo existed; it is not stored here.
Searches run 2026-10-04, weighted to 2024–2026. Only sources opened at a
primary location carry the verdict.

## Verdict: 🟡 CONDITIONAL GO

Scores /10 — novelty 6.5 · feasibility 8 · attractiveness 7 · target fit 7.

## Frozen claim

Phenomenon -> measurement -> consequence: most resolved npm dependencies lack
build provenance; we measure how much of that deficiency could be recovered by
switching to an in-range provenance-bearing version, and how much of the
apparent recovery survives npm's real resolver, installation, and the
repository's own tests; this tells maintainers and policy designers whether
provenance enforcement can be met by version choice or must wait for upstream
publishers.

## Closest work (verified = opened at primary source)

| Work | Year | Verified? | What it establishes | Overlap with PDR |
|---|---|---|---|---|
| Pinckney et al., *Flexible and Optimal Dependency Management via Max-SMT* (PacSolve/MaxNPM), ICSE | 2023 | Yes (author page, ICSE program, Zenodo artifact) | Solver with configurable objectives over npm resolution; beats npm audit's fix on vulnerability reduction in 33% of cases, on top npm packages | **Partial, highest risk.** A provenance objective would plug in directly. Did not study provenance, app lockfiles, or tests |
| Pinckney, Cassano, Guha, Bell, *A Large Scale Analysis of Semantic Versioning in NPM* | not confirmed in opened page | Title/authors/claim yes | Time-travelling npm resolver; security patches reach dependents quickly in most cases when semver is used correctly | Partial: in-range update flow, not provenance |
| Rombaut, Cogo, Hassan, *Leveraging the Crowd…Dependabot Compatibility Score*, arXiv 2403.09012 | 2024 | Yes (arXiv) | 579,206 Dependabot PRs; compatibility scores usually lack enough data | Partial: update breakage risk, not provenance-conditioned candidates |
| Maksymiuk, *How Reproducible Are Build and Test Outcomes of Dependency Updates in JavaScript/npm Projects?*, TU Delft BSc thesis | 2026 | Yes (TU Delft repository) | 2,777 npm update PRs; test outcomes unstable, esp. browser/native/peer-dependency projects | Methodological: supports repeated test runs and the hermetic screen |
| Solarin, *Reproducibility is Not Enough: Artifact Verifiability in Decentralized-Build Package Ecosystems*, arXiv 2608.18180 | 2026 | Yes (arXiv text via index; direct PDF fetch returned no text) | Artifact verifiability in 4 ecosystems; "recovery" = recovering source state for rebuilds; provenance-bearing packages' advantage mostly reflects adopters' practices | Low on construct, **important for interpretation** (selection effect on provenance-bearing candidates) |
| Schorlemmer et al., *Signing in Four Public Software Package Registries*, arXiv 2401.14635 | 2024 | Yes (arXiv) | Signing quantity/quality in PyPI, Maven Central, Docker Hub, Hugging Face | Low: adoption only, and **does not cover npm** |
| Pohl, Novák, Ohm, Meier, *SoK: Towards Reproducibility for Software Packages in Scripting Language Ecosystems*, ARES | 2025 | Yes (publisher DOI listing) | Literature on scripting-ecosystem reproducibility is sparse | Low: reproducibility, not substitution |
| pnpm `trustPolicy: no-downgrade` | current docs | Yes (pnpm.io) | Fails install when a package's trust evidence drops vs earlier releases | Partial: enforcement baseline; blocks, does not search for alternatives |
| danielroe/provenance-action | current | Yes (GitHub README) | Fails CI when lockfile changes lose provenance / trusted publisher / staged publishing, incl. transitives; flags repo/branch changes | **Direct for RQ4 (regression)**; none for recovery |
| Exaforce analysis via NHIMG editorial | — | Secondary only | 26 of 205 (12.6%) GitHub-workflow-published top jsDelivr packages use provenance | Low: package-level adoption |
| vlt `reproduce` package README | — | Yes (npmjs page) | 3.72% of top 5,000 high-impact packages have provenance | Low: package-level adoption |

**UNVERIFIED, carries no weight:** the "University of Bonn thesis, 63,827
versions / 23,648 packages" cited by audit v1 (not found in two searches); the
npm RFC 0049 statement cited by audit v1 (not opened this pass); an NSF-indexed
paper on counterfactual pinning vs floating (title not confirmed).

## Residual gap (Gate B)

No verified source measures, on real application lockfiles, (1) whether a
provenance-bearing version exists inside the declared range of a deficient
resolved dependency, (2) whether npm's actual resolver accepts it without
changing the rest of the tree, and (3) whether it survives install and tests.
Tools detect or block provenance loss; update studies measure breakage of
arbitrary updates; MaxNPM could *compute* policy-optimal versions but did not
measure provenance recovery. The gap is a measurement gap, not a method gap.

## Gates

| Gate | Result | Reason |
|---|---|---|
| A — meaningful phenomenon | PASS | 83.29% of known resolved edges lack provenance (45 repos); enforcement tools now exist (pnpm, provenance-action), so "can enforcement be met by version choice?" is a live practitioner question |
| B — not already established | PASS (narrow) | Residual gap above. Holds only as an empirical measurement under npm's real resolver; fails if framed as a new method for finding provenance-preserving versions (MaxNPM territory) |
| C — reproducible | PASS | Public registry + GitHub data, pinned commit SHAs, open artifact, clean-room verified, claims registry. Caveat: registry state is read now, not at publish time |
| D — falsifiable | PASS | Frozen decision rules (methodology_freeze S1–S2); numeric kill conditions below |
| E — contribution type | PASS | Empirical finding (screening 4.09% vs resolution-confirmed 1.11% of deficient edges, CI 0.73–1.64%), missing comparative evidence (proxy vs real resolver), open artifact |
| F — scope & attractiveness | PASS (conditional) | Reads as a supply-chain security / empirical SE study. Weak until Layer 3 data exist and both estimands are reported |
| G — final sweep | PENDING | Repeat immediately before submission; watch terms below |

No narrowing was needed: the broad idea did not die. The change below is a
framing constraint, not a rescue.

## Required conditions for GO

1. Frame recoverability as **"under npm's actual resolver with targeted
   overrides"**, cite MaxNPM, and state that a global optimizer could find
   solutions npm does not. Optional strengthening (new task, human decision):
   compare against a MaxNPM-style optimizer on a subset as an upper bound.
2. Complete T1 ("exists-any" retry) so the measured quantity matches RQ2.
3. Complete the Layer 3 micro-pilot before claiming anything about tests.
4. Report edge-weighted and repo-weighted results with clustered CIs.
5. Treat RQ4 (regression) as prevalence only; detection is fully covered by
   existing tooling.
6. Add the Solarin selection-effect point to threats to validity:
   provenance-bearing candidates come from projects with different practices.

## Safe sentence

"Across 45 open-source npm repositories (69,692 resolved dependency edges),
we measure how much missing build provenance at the resolved version could be
recovered by switching to an in-range provenance-bearing version, and how much
of that apparent recovery survives npm's actual resolver, installation, and
the repository's own tests."

Banned overclaims: "first"; "novel provenance security system"; "provenance
makes dependencies safe"; ecosystem-wide prevalence from this corpus;
"stratified sample"; "objectively below X"; "only 27% survive" without the
repo-weighted figure; "recoverable" for screening-only results; "deployable";
any claim that npm cannot recover versions a global optimizer could.

## Kill / downgrade conditions for the next experiments

- Gate B KILL: a verified source already measures provenance-conditioned
  in-range recoverability on real lockfiles -> reframe as replication.
- If an optimizer comparison recovers >80% of proxy-positive candidates that
  npm rejects, the finding becomes "npm's resolver is the bottleneck": a
  different paper; rewrite the framing.
- Micro-pilot REWORK (infrastructure, not a project kill): >30% of the 23
  experiments have an invalid B0 baseline (install fails, tests fail, or flaky).
- Layer 3 adds nothing: NO_BEHAVIORAL_CHANGE in >50% of attributable
  experiments -> drop the Layer 3 claim; the paper is a Layer 1–2 study.
- Do not report Gate D from the micro-pilot if attributable test pairs < 10.

## Gate G watch terms

provenance-aware dependency resolution; attestation-aware version selection;
trusted publishing adoption npm; pnpm trustPolicy empirical; npm provenance
enforcement cost; MaxNPM / PacSolve follow-ups; Sigstore npm attestation study.

## Next action

T1 (exists-any retry), then T4 (finish the related-work matrix from the
verified rows above), then the Docker gate.
