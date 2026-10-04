# Methodology freeze (Phase 0)

Per the reviewer feedback this responds to, these decisions are frozen
**before** their results are allowed to influence the thesis. One honest
caveat on process: this freeze was authored in the same working session as
the Phase 1 run it governs, not as a separate prior step with a time gap.
The freeze text below was written and committed first, then Phase 1 was
executed against it unchanged -- but a reviewer should know the two
happened close together, not that this document predates this repo by
weeks. Section 3's seed and thresholds were fixed in the script before it
was run against real data, which is the part that actually matters for
avoiding post-hoc tuning.

## 1. Gate B threshold rationale

The pilot's B gate used a bare "5%" point threshold. That threshold is a
**working gate for pipeline development**, not a statistically derived
value, and it stays that way -- semantic recoverability doesn't have a
principled a-priori "meaningful" cutoff. **The 10%/5% figures below are a
pre-specified OPERATIONAL bound for this project's own decision-making,
not a claim that 10% is a scientifically established cutoff for
"meaningful recoverability" in general.** The paper-facing phrasing for
this must stay conditional: *"under the pre-specified operational bound of
10%, the repository-clustered confidence interval excludes the
non-negligible region"* -- never *"recoverability is objectively below
10%"*, which would misstate a project-internal decision rule as an
external scientific fact. What changes from here on: **the primary
Phase-1-onward statistic is not a point estimate against a threshold, but
a repository-clustered bootstrap confidence interval** (Section 3). The
decision rule is:

- If the 95% CI sits entirely below ~10%: treat recoverability as
  genuinely low, not a sampling artifact -- reframe the thesis per
  Section 2 rather than re-running with a different threshold.
- If the 95% CI is wide and straddles a plausibly "meaningful" region
  (roughly 5-15%): treat Phase 1 as inconclusive and the sample as still
  too small -- proceed to Phase 3 (200 repos) before deciding anything.
- If the point estimate rises substantially with a larger, still-stratified
  sample: treat that as evidence the pilot's 7 repos were an unlucky draw.

## 2. Reframing rule if recoverability stays low

Per the reviewer's Outcome A/B/C framing, decided in advance:

- **Outcome A** (recoverability rises with scale): original RQ2/RQ3 stand
  as originally framed.
- **Outcome B** (recoverability stays ~3-6%, but a meaningful share of that
  small population is operationally costly): the flagship claim becomes
  "rare recoverability + nontrivial enforcement cost" -- both halves matter,
  neither alone.
- **Outcome C** (recoverability stays low AND Gate C/D show almost nothing
  recoverable survives deployment): the paper becomes a **provenance
  deficiency persistence / scarcity-of-feasible-recovery** study. This is
  a legitimate, different, still-publishable empirical contribution, not a
  failed project. This must not be dressed up as the original flagship
  framing after the fact -- the abstract must say plainly that recovery was
  found to be rare and operationally costly.

## 3. Repository-level uncertainty method

**Primary Phase-1 statistic:** semantic recoverability among deficient
edges, with uncertainty from a **repository-clustered percentile
bootstrap** (resample repositories with replacement, not edges; recompute
the pooled statistic per resample; take the 2.5/97.5 percentiles). Edges
within one repository share a lockfile and a dependency graph and are not
independent draws -- a naive per-edge binomial CI would badly overstate
precision. Implementation: `scripts/bootstrap_ci.py`. Frozen parameters,
fixed before running against Phase-1 data: `n_boot=5000`, `seed=20260924`.

**Secondary Phase-1 statistic:** proportion of repositories containing at
least one recoverable deficient edge, with a **Wilson score interval**
(repositories are the natural independent unit for this statistic, so a
closed-form binomial-proportion CI is correct and preferable to resampling
here).

**Estimand, frozen explicitly (per external review):** the primary
statistic (4.29% at Phase 1 scale) estimates the **edge-weighted
proportion of deficient dependency edges that have a recoverable
alternative** -- i.e., every edge counts equally regardless of which repo
it's in, so a repo with a larger dependency tree contributes more weight
to the pooled number than a repo with a smaller one. This is a different
quantity from the secondary statistic (repo-weighted: "88.9% of
repositories contain >=1 recoverable case", every repo counts once
regardless of tree size) and would be different again from a
package-weighted estimand ("proportion of unique packages that have a
recoverable alternative somewhere they're used"). All three are legitimate
questions; this project reports the first two and must not blur them
together or swap which one a stated percentage refers to without saying so
explicitly, in this document or the eventual paper.

## 4. Sampling strategy (Phase 1)

**Terminology precision, per external review:** what follows is a
**deliberately diversified convenience corpus with pre-specified
stratification variables used for coverage and subgroup analysis** -- not
statistical stratified sampling in the strict sense (which would require
sampling *within* each stratum from a defined population, e.g. drawing N
repos at random from all npm-lockfile-v3 repos in a given size bucket).
The actual procedure below is "probe a candidate list, keep everything that
qualifies, analyze by pre-specified groups" -- perfectly reasonable for a
de-risking experiment, but it should not be described as "a stratified
sample of npm" anywhere in this project, including in the eventual paper.
Convenience-sample risk from the 7-repo pilot is addressed by diversifying
the Phase 1 expansion (`configs/experiments/kill_v1_phase1_n45.yaml`) on
three variables computed **objectively from each repo's own lockfile**,
not estimated:

1. `lockfileVersion` (v2 vs v3)
2. dependency-tree size bucket (small <300 / medium 300-800 / large
   800-1600 / very_large >1600 resolved packages)
3. monorepo vs single-package (presence of npm-workspace-root entries in
   the lockfile, i.e. "packages" keys with no `node_modules/` prefix)

**Deliberately not used in Phase 1:** GitHub stars / repository age. This
session's anonymous GitHub REST API quota (60 requests/hour) was exhausted
partway through metadata collection. Rather than build a sample using
verified data for some repos and unverified/guessed data for others, that
axis is deferred to Phase 3, where an authenticated API token should be
arranged first so the full ~200-repo sample can be stratified on popularity
and age too.

Selection procedure was: probe a larger candidate list (60 well-known npm
projects spanning utility libraries, CLI tools, test/build tooling, and
applications) for a committed lockfile v2/v3, keep every repo that had one
(45 total, including the original 7 pilot repos), and use all of them
rather than hand-picking a "nicer" subset after seeing results. This gives
**coverage** across the three variables above and guards against the
specific failure mode of "7 unusually chosen projects" -- it does not give
**representativeness** of the npm ecosystem, and Section 10 below is
explicit that no claim of that kind should be made from this corpus.

## 5. Gate C rename

Per the reviewer's objection: `npm ci → peer check → audit signatures →
tests` does not demonstrate production deployability. Gate C is
reconceived as **"semantic-to-operational gap"**, not "deployability", and
is defined as a **study-specific operational criterion**:

> A candidate is "operationally viable" if it (a) resolves successfully
> under real npm resolution (not just the local semver-diff proxy --
> Section 6), (b) installs structurally (`npm ci --ignore-scripts`) without
> error, (c) produces no new peer-dependency conflict, (d) does not
> regress `npm audit signatures` status, and (e) does not newly fail the
> repository's own test suite.

This is never described as "safe" or "production-ready" anywhere in
outputs -- see `docs/scope_boundary.md`, unchanged.

## 6. Screening vs. empirical resolution-preserving

`pdr/policy.py`'s `DEFICIENT_RESOLUTION_PRESERVING` state, as shipped in
the pilot, is a **screening-stage proxy**: local semver diff between the
currently resolved version and the best in-range provenanced candidate,
evaluated per-edge in isolation. It does not model npm's real
deduplication/hoisting behavior across the whole tree.

Frozen for Phase 1.5 / Phase 2: every proxy-positive candidate must also
pass an **empirical resolution stage** -- force the candidate via a real
`overrides` entry against the repo's actual `package.json` +
`package-lock.json`, and re-resolve with npm itself
(`npm install --package-lock-only --ignore-scripts`). A candidate is
**resolution-confirmed** only if (a) npm's real resolver actually applies
it, AND (b) no other top-level package's resolved version changes as a
side effect. See `docs/phase1_5_results.md` for the first real run of this
check and its disagreement rate with the proxy.

## 7. Sandbox specification

Full target spec for the Gate C/D harness (Phase 2), following the
reviewer's execution model:

```
Host
 └── isolated worker (per experiment, disposable)
      ├── immutable repo snapshot
      ├── isolated filesystem, no host mounts
      ├── capped CPU / RAM
      ├── hard wall-clock timeout
      ├── restricted network (npm registry only)
      ├── no credentials
      └── two install modes:
            structural:  npm ci --ignore-scripts
            behavioral:  full install, lifecycle scripts enabled
```

**What actually ran in this session (Phase 1.5) is narrower than this
spec, deliberately:** a third, even lighter mode --
`npm install --package-lock-only --ignore-scripts` ("resolution-
verification") -- which resolves against the live registry but creates no
`node_modules`, downloads no tarballs, and executes no code at all. This
session's execution environment is a shared container, not the
per-experiment isolated worker above, so **structural mode (real `npm ci`)
and behavioral mode (lifecycle scripts enabled) are both explicitly
deferred to Phase 2**, which must not begin implementation until the
isolated-worker infrastructure above actually exists. Running arbitrary
real npm packages' install/lifecycle scripts outside that isolation would
be executing untrusted code with no containment, which this project does
not do.

## 8. Gate D primary cost metric (frozen ahead of measurement)

Baseline matrix:

- **B0** -- original lockfile, no provenance policy.
- **B1** -- existing checker (`npm audit signatures`) run against B0's
  resolution, no substitution.
- **PDR** -- B0's resolution with every resolution-confirmed candidate
  (Section 6) substituted via `overrides`.

Candidate cost variables (all will be measured when Gate D actually runs):
installation success, peer-conflict rate, test failure rate, wall-clock
install time, wall-clock test time, packages changed, edges changed,
substitutions required.

**Primary D metric, frozen now, before any Phase 2 data exists:** the
**test-suite failure rate delta** between PDR and B0 (does substituting
provenance-bearing candidates newly break tests that passed under B0).
**Co-primary:** **installation success rate delta**. Wall-clock cost and
transfer size are secondary/reported, not used to decide GO/KILL on Gate D
-- this is fixed now specifically so the metric can't be picked after
seeing which one tells the nicer story.

## 9. Provenance classifier validation (planned for Phase 2)

`dist.attestations` presence was verified live against known
provenance/non-provenance packages before this pipeline trusted it
(`pdr/provenance.py` docstring). Phase 2's install runs are also the right
moment to cross-check a stratified sample against `npm audit signatures`
output directly, as an independent validation of the corpus-scale
classifier -- not to replace it, since `dist.attestations` is what makes
corpus-scale measurement affordable at all.

## 10. Dataset separation (Phase 3, stated now to avoid future drift)

Two datasets must stay conceptually and physically separate:

- **Dataset A -- G1 kill-test corpus** (~200 repos): decides whether the
  frozen PDR research question survives.
- **Dataset B -- prevalence corpus** (larger, ideally closer to randomly
  sampled): estimates ecosystem-wide prevalence.

Phase 1's 45-repo corpus and the original 7-repo pilot are neither of
these -- both are de-risking/feasibility samples and must not be quoted as
an ecosystem prevalence estimate in the eventual paper.
