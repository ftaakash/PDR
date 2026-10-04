# Gate status (PDR-G1, pilot run)

**Superseded for anything beyond the original 7-repo pilot.** This file is
the frozen snapshot for the *pilot* run specifically (kept as history, not
rewritten). For the current picture: `docs/phase1_results.md` (45-repo
de-risking run, Gate A/B/E/F) and `docs/phase1_5_results.md` (real
resolution-verification pilot for Gate C's screening question) both
postdate and extend this file. `docs/methodology_freeze.md` is the current
source of truth for terminology and thresholds (e.g. Gate C is now called
"semantic-to-operational gap", not "deployability gap" -- this file
predates that rename and is left in its original wording below).

This is the living record of where the v4.1 FROZEN gate (README.md) actually
stands after running the pipeline in this repo against a real, if small,
corpus. It exists so nobody has to re-derive "what did we actually check" by
reading code.

## Corpus

7 real GitHub repos with a committed npm lockfile v3 at HEAD (see
`configs/experiments/kill_v1.yaml`): microsoft/vscode, npm/cli,
microsoft/playwright, puppeteer/puppeteer, axios/axios, socketio/socket.io,
nestjs/nest. **19,148 resolved edges, 2,841 unique dependency names.**

This is a convenience sample (chosen only by "has an npm lockfile v3"), not
a random or stratified sample of the npm ecosystem, and it is an order of
magnitude below the 200-repo G1 sample the audit prompt's Kill Test 10
specifies. Treat every number below as "the pipeline and constructs behave
sensibly on real data", not as an ecosystem-wide estimate.

## Gate results (this run)

| Criterion | Status | Headline number |
|---|---|---|
| A -- OPG, era-controlled | **PASS** | 84.07% of resolved edges lacked provenance overall; 75.53% among edges whose resolved version postdates npm provenance GA (2023-09-26) |
| B -- meaningful semantic PD | **FAIL** (below the 5% working threshold used here) | Only 3.80% of deficient edges have an in-range provenance-bearing alternative at all |
| C -- semantic-to-operational gap (was "deployable gap") | **PENDING** | Not measured -- see "What Phase 2 requires" below |
| D -- excess enforcement cost vs B0/B1 | **PENDING** | Not measured -- see "What Phase 2 requires" below |
| E -- robustness | **PASS** | Direct (67.65%) vs transitive (84.91%) OPG both nonzero and same direction as overall; consistent sign across all 4 era buckets and all 7 repos (range 59%-92% OPG) |
| F -- unknowns bounded | **PASS** | 1.46% unknown |

**This pilot cannot issue a final GO or KILL** -- README's Gate requires the
COMBINED A-F pattern, and C/D are not measured. What it DOES establish:
Kill Test 1 ("could PDR simply discover almost everything is already
provenanced?") is answered **no** at pilot scale -- deficiency is real and
large. But Kill Test 2's concern ("is the expected number of recoverable
cases large enough to analyze statistically?") looks like the sharper risk:
recoverability is real but small (3.8% of deficient edges), and per README's
own "ACCEPT AS KILLS" list, *"high-PD/almost-all-deploy/near-zero-cost ->
enforcement cheap -> flagship weakens"* is the wrong-direction failure mode
this guards against -- here the risk runs the other way: recoverability
itself may be too thin, in the same population where it's most needed
(pre-GA-era packages: only 0.5% semantic-recoverable), for RQ2/RQ3 to be
statistically well-powered without a much larger corpus. This is exactly
the kind of finding the audit prompt's Kill Test 10 (statistical power) says
to check before committing 6-12 months -- do it on the full 200-repo sample
before treating this pilot's 3.8% as more than a warning sign.

## What Phase 2 requires (C and D)

Gate C (semantic-to-operational gap) and D (enforcement cost) need actually substituting
each `DEFICIENT_RESOLUTION_PRESERVING` candidate into its real repo and
running: `npm install` (structural installability), a peer-dependency
check, `npm audit signatures` (Baseline 1), and the repo's own test suite --
then comparing failure rates against B0 (no policy) and B1 (existing
checker) baselines, per Kill Test 5's confounder list (repo age, lockfile
staleness, Node/npm version, native deps, lifecycle scripts, etc.). That's
real compute time per repo (install + full test suite, times the number of
candidate recoveries), which is why it wasn't attempted in this pilot run.
The harness entry points this needs are NOT yet built; `pdr/policy.py`'s
`Classification.candidate_version` field already carries exactly the
(edge, current version, candidate version) triples Phase 2 would iterate
over.

## Known limitations (declared, not hidden)

- **Lockfile-only.** No floating-dependency (no-lockfile) repos analyzed;
  Gate E's "lockfile vs floating" robustness axis is untested here.
- **Resolution-preserving tolerance is a v0.1 proxy** (minor/patch diff from
  the currently resolved version, computed with Node's own `semver`
  package). It does NOT simulate full-tree re-resolution effects (dedup/
  hoisting collisions with other requesters of the same package). Kill
  Test 3 in the audit prompt is aimed exactly at this distinction --
  unresolved here, flagged in `pdr/policy.py`'s docstring.
- **Regression builder/source-path enrichment not computed** -- prevalence
  only (4.95% of dated packages show >=1 present->absent transition, 1,597
  events across 137 packages). `pdr/regression.py:fetch_attestation_bundle()`
  is the entry point for the richer version.
- **"Does the registry say V has provenance right now" vs "did V have
  provenance at publish time"** are not distinguished (Kill Test 11).
