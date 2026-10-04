# PDR-G1 analysis memo (45 real repos, 69,692 edges)

DE-RISKING SCALE (45 real repos, 69,692 edges; not the full 200-repo G1 kill-test sample specified in the audit prompt's Kill Test 10, unless n_repos >= 200 as noted above). Corpus composition (convenience vs. diversified vs. stratified) is documented per-experiment in its own config/results docs, not asserted generically here -- see docs/phase1_results.md or the equivalent for this run's actual corpus, and docs/methodology_freeze.md Section 4 for the standing caution against calling any pre-200-repo corpus a representative sample of npm.

**Headline:** 83.29% of resolved edges lacked provenance (OPG); of those, 4.29% were semantically recoverable (a provenance-bearing version exists in the declared range), and 4.09% were resolution-preserving CANDIDATES (screening-stage proxy only -- not yet resolution-confirmed or operationally viable; see Gate C, renamed 'semantic-to-operational gap' per docs/methodology_freeze.md Section 5 -- this is deliberately not called 'deployable').

**Boundary reminder (never drop this line):** none of the above is a safety claim. Provenance is origin/integrity evidence, not a guarantee the code is benign.

## Gate results

- **A_opg_era_controlled**: PASS
- **B_semantic_pd**: FAIL
- **C_semantic_to_operational_gap**: PENDING
- **D_excess_enforcement_cost**: PENDING
- **E_robustness**: PASS
- **F_unknowns_bounded**: PASS

**Overall (measured criteria A/B/E/F only):** MEASURED_FAIL_B__C_D_PENDING

Per README.md, SUCCESS requires the COMBINED A-F pattern with no relaxation, so this pilot cannot itself issue a final GO or KILL -- C and D are PENDING (not measured), and among what WAS measured, criteria A, E, F passed; criteria B FAILED. A single FAIL among measured criteria means this run does not currently satisfy the gate, independent of C/D. What this pilot DOES establish regardless: the pipeline runs end-to-end on real npm dependency trees and the constructs are computable. Kill Test 1 (phenomenon existence) is answered YES at pilot scale -- deficiency is not negligible. If B failed here, read that as Kill Test 2's concern (recoverability may be too thin to be statistically useful) showing up in real data, not as a pipeline defect.
