# PDR: The Complete Project Guide

*Provenance Debt at Resolution. A plain-language guide to every part of this
project: what we asked, how we measured it, what we found, and why each design
choice was made. Read it top to bottom once, then use the section headings to
revise before a review.*

Every number in this guide comes from `docs/claims.json`, which a test
recomputes from the raw data. If a number here ever disagrees with that file,
the file wins.

---

## 1. The project in one paragraph

When a JavaScript project installs its dependencies with npm, most of the
package versions it ends up with have **no build provenance**: no signed
record of which source code and which build produced them. npm can attach such
a record, and tools now let projects *require* it. So we asked: **if a project
wants provenance for a dependency that lacks it, can it simply switch to a
different version of that dependency (one the project already allows) that
does have provenance? And if it switches, does anything break?** We measured
this on 205 real open-source projects (45 in Phase 1, 160 in the scale-up).
Answer: **only about 2.3% of the missing provenance can be recovered this way**,
because suitable versions rarely exist or npm can't adopt them without changing
other packages. But **when npm *can* adopt them, nothing broke**: 0 failures in
110 isolated experiments.

**Where this sits.** PDR is a *consumer-side, resolution-time* study. Release-side
work such as Santos-Grueiro's *On Good Authority* (arXiv 2606.22593, 2026) looks
at each new release and asks whether its publication path changed compared with
the release before it (new publisher, workflow, repository, lost provenance,
signing change). We look at the project that installs packages and ask what it
can do about missing provenance with the ranges it already declares and npm's
real resolver. Same topic, opposite end of the supply chain.

---

## 2. Words you must know

| Term | Plain meaning |
|---|---|
| **npm** | The package manager and registry for JavaScript. `registry.npmjs.org` hosts millions of packages. |
| **Dependency** | A package your project uses. Dependencies have their own dependencies, forming a **tree**. |
| **Lockfile** (`package-lock.json`) | A file listing the *exact* version of every package in the tree. It is what actually gets installed. |
| **Semver range** | How a project declares which versions it accepts, e.g. `^1.2.0` means "1.2.0 or any newer 1.x". |
| **Resolver** | npm's algorithm that picks one exact version per package so that every range in the tree is satisfied. |
| **Provenance / attestation** | A signed statement (made with Sigstore) linking a published version to the source repository and CI build that produced it. In npm it appears as `dist.attestations` in the registry metadata. |
| **Sigstore** | The open signing infrastructure npm uses for provenance. `npm audit signatures` verifies these signatures. |
| **Edge** | One dependency relationship in a lockfile: "package A requires package B with range R, resolved to version V". Our unit of counting. |
| **Deficient edge** | An edge whose resolved version has no provenance. |
| **Screening-positive** | A deficient edge for which a provenance-bearing version exists inside the declared range *and* is at most a minor/patch step away from the resolved version. |
| **`overrides`** | A `package.json` field that forces npm to use a specific version of a package everywhere in the tree. We use it to force the candidate. |
| **Ripple** | Forcing the candidate made npm change the version of *other* packages too. |
| **Peer conflict** | npm refuses because of a peer-dependency rule (`ERESOLVE`). |
| **Lifecycle scripts** | Code packages run during install (`preinstall`, `postinstall`, `prepare`). This is where untrusted code executes. |
| **B0 / PDR** | B0 = the unmodified project (baseline). PDR = the same project with the provenance-bearing version substituted. |
| **Attributable failure** | A failure in PDR at a stage that B0 passed. Only these count against the substitution. |
| **Edge-weighted vs repo-weighted** | Edge-weighted = pool all edges together (big projects count more). Repo-weighted = compute a rate per project, then average (every project counts equally). We always report both. |
| **Clustered bootstrap CI** | A 95% confidence interval computed by resampling *projects*, not edges, because edges in the same project are not independent. |
| **Pre-registration** | Writing the plan and freezing it in git (a tag) *before* running the experiment, so nobody can tune the method to the results. |

**Provenance is origin evidence, not a safety guarantee.** A package with
provenance can still be buggy or malicious; provenance only tells you where it
came from. We never claim otherwise, and a test (`tests/test_no_safety_claims.py`)
enforces this wording in the code.

---

## 3. The research questions

- **RQ1:** How many resolved dependency edges lack provenance?
- **RQ2:** For deficient edges, does an in-range provenance-bearing version exist,
  and does npm's real resolver accept it?
- **RQ3:** If npm accepts it, does the project still install, run its scripts,
  and pass its own tests?
- **RQ4:** How much do the answers depend on how strictly we define "no side
  effects"?

---

## 4. The big picture: a funnel

Each stage keeps only what survived the previous one. The result is not one
number but **attrition at every stage**.

```
All resolved edges                         262,066 edges (160 repos, scale_v1)
  -> lacking provenance (RQ1)               84.80% of known edges
    -> screening-positive candidate (RQ2a)   8.05% of deficient
      -> npm resolver accepts, no ripple     28.51% of those        (Layer 1, RQ2b)
         = about 2.3% of all deficient edges are recoverable
        -> structurally installable          13/13 (small Layer 2 sample)
          -> testable project (own tests pass in our sandbox)  31 of 91 repos
            -> no attributable failure at any stage           110 of 110 experiments (Layer 3, RQ3)
```

The two "layers" that execute things (Layer 2 install, Layer 3 scripts and tests)
are the expensive, careful part. Layer 1 runs nothing; it only asks npm to
re-resolve.

---

## 5. The data: two corpora

### 5.1 Phase 1 corpus (45 repositories)
Well-known JavaScript projects with a committed `package-lock.json`, chosen in
the pilot phase across lockfile version, tree size and monorepo/single package.
**69,692 edges.** Limitation: chosen by hand, and the lockfiles were fetched
from the default branch without recording the exact commit (we later
recovered the commits; see Section 12).

### 5.2 scale_v1 corpus (160 repositories), the main dataset
Designed and frozen in git (tag `freeze/scale-v1-design`) **before** any data
was fetched (`docs/phase4_protocol.md`).
- **Frame:** GitHub search for JavaScript or TypeScript repositories with
  ≥1,000 stars, not forks, not archived, pushed in the last six months.
  **5,862 repositories** were found.
- **Strata:** 4 star bands (1k–2k, 2k–5k, 5k–20k, 20k+) × 2 age groups
  (created before / after 2018) = 8 groups.
- **Sample:** in each group, candidates were shuffled with a fixed seed and the
  first **20 eligible** ones kept. Eligible = has a root `package-lock.json`
  (version ≥2) at the current commit. Total **160**.
- **Pinning:** each repository's exact commit SHA was recorded, and the lockfile
  and `package.json` were fetched *at that commit*. Anyone can re-fetch the
  same files later.
- Script: `scripts/scale_select_corpus.py` → `configs/experiments/scale_v1.yaml`.
- **262,066 edges.**

*Why stratify?* So the sample isn't dominated by one kind of project (only huge
famous ones, or only new ones), and so we can look at differences across groups.

---

## 6. Phase 1 classification (RQ1, RQ2a)

**What:** Parse every lockfile into edges, then label each edge.
**How:**
1. `scripts/fetch_corpus.py` downloads each lockfile; `pdr/resolve.py` turns it
   into edges, correctly handling workspaces (monorepos) and nested `node_modules`.
2. `scripts/check_provenance.py` downloads each package's registry metadata
   once (12,115 packages for scale_v1) and `pdr/policy.py` classifies each edge:
   - `PROVENANCED`: resolved version already has provenance.
   - `DEFICIENT_UNRECOVERABLE`: no provenance-bearing version anywhere in the range.
   - `DEFICIENT_SEMANTIC_ONLY`: one exists in range, but more than a minor/patch
     step from the resolved version.
   - `DEFICIENT_RESOLUTION_PRESERVING` (= **screening-positive**): one exists in
     range and within a minor/patch step.
   - `UNKNOWN`: couldn't be determined (e.g. git or local dependencies).
3. All range logic uses npm's **own** `semver` library (`scripts/semver_helper.js`),
   so we never reimplement npm's rules incorrectly.

**Results:**

| | Phase 1 (45) | scale_v1 (160) |
|---|---|---|
| Edges | 69,692 | 262,066 |
| UNKNOWN | 1.09% | 1.94% |
| Lacking provenance (OPG) | **83.29%** [79.3, 87.0]; repo-weighted 81.3% | **84.80%** [82.7, 87.0]; repo-weighted 83.4% |
| Screening-positive among deficient | **4.09%** [2.0, 6.3]; repo-weighted 2.7% | **8.05%** [6.7, 9.4]; repo-weighted 5.8% |

*Why "within a minor/patch step"?* A major-version jump usually means breaking
API changes; nobody would call that "the same dependency". We anchor the
tolerance to the version actually resolved, not to the range.

---

## 7. Layer 1: does npm's real resolver accept the candidate? (RQ2b)

**Why this layer exists:** the screening step only says "a suitable version
exists". It ignores that npm must fit that version into the whole tree. A
21-candidate pilot suggested 86% would be accepted; the full run showed that
was badly wrong.

**How (per candidate):** take the project's real `package.json` and lockfile,
force the candidate (via `overrides`, or by editing the root dependency
directly when the package is a root dependency, because `overrides` errors in
that case), then run:

```
npm install --package-lock-only --ignore-scripts
```

This only computes a new lockfile; it downloads no package code and runs
nothing. Then compare the new lockfile with the old one:
- **OK**: candidate applied and **no other top-level package changed**.
- **RIPPLE**: candidate applied, but other packages moved.
- **PEER_CONFLICT**: npm refused with `ERESOLVE`.
- **RESOLUTION_FAIL**: any other refusal.

Each unique (project, package, candidate) is resolved once and shared by all
edges that need it. npm version pinned to **10.9.7** (the version recorded in
`data_manifest/tool_lock.json`).

**Results:**

| | Phase 1 | scale_v1 |
|---|---|---|
| Candidates | 2,349 | 17,549 |
| OK | 638 → **27.16%** [18.0, 40.1]; repo-weighted **52.3%** [41.5, 63.0] | 5,003 → **28.51%** [23.8, 33.3]; repo-weighted **45.2%** [39.8, 50.8] |
| RIPPLE | 1,656 | 10,860 |
| PEER_CONFLICT | 55 | 1,573 |
| RESOLUTION_FAIL | 0 | 113 |

**Key insight:** the main reason for rejection is **ripple**. Forcing one
version makes npm re-resolve its neighbours, and other packages move. The two
corpora agree closely (27% vs 28.5%), which is strong evidence the result is
real and not a quirk of one sample.

**Why edge- and repo-weighted rates differ:** in Phase 1, a few projects
contributed hundreds of near-identical candidates (`socket.io` had 384, 0 OK),
pulling the pooled rate down. The typical project does better than the
typical edge. Both answers are correct; they answer different questions.

---

## 8. Two follow-up analyses on Layer 1

### 8.1 Does trying an older version help? (experiment `layer1_alt_v1`)
Layer 1 tried only the *highest* suitable version. Maybe a slightly older one
works. For the 1,711 Phase 1 edges that failed, we tried up to **5 lower**
provenance-bearing in-range versions, highest first, stopping at the first OK.
- Recovered: **12 of 1,711**. Exists-any rate **27.67%** [18.2, 41.5] vs 27.16%.
- 524 edges had no lower candidate at all.
- So: **older versions almost never help.** The ripple comes from re-resolving
  the package's neighbours, not from which exact version you pick.
- Drift check: we re-ran every original candidate first; all 435 that could run
  gave the same answer as the original Layer 1. (384 socket.io edges couldn't
  run on Windows; reported as a bound.)
- Design and results: `docs/phase2_protocol.md` §7, `docs/phase2_layer1_alt_results.md`.

### 8.2 How strict should "no side effects" be? (ripple sensitivity, RQ4)
OK requires zero other packages to change. What if we allow k?

| k (other packages allowed to change) | Edge-weighted OK | Repo-weighted OK |
|---|---|---|
| 0 (our definition) | 27.16% | 52.3% |
| 1 | 41.42% | 65.1% |
| 2 | 47.21% | 74.8% |
| 5 | 63.60% | 80.7% |
| 10 | 71.22% | 82.6% |

So our headline is a **strict lower bound**. A project willing to accept small
side effects can recover more. (Thresholds were fixed before computing;
`docs/phase2_layer1_results.md`.)

---

## 9. Layer 2: does it install? (small sample)

`npm ci --ignore-scripts` (real files on disk, but no scripts run) for 13
Layer-1-OK candidates in 4 repositories: **13/13 installed**. Small and
deliberately cautious; superseded by Layer 3, which installs too.

---

## 10. Layer 3: does the project still work? (RQ3)

This is where we **run untrusted third-party code**, so safety comes first.

### 10.1 The isolation design (`isolated_worker/`)
Every run happens in a **fresh, disposable Docker container**, destroyed after
one job:
- no Linux capabilities (`--cap-drop=ALL`), `no-new-privileges`, read-only root
  filesystem, non-root user (UID 10001);
- memory 8 GB, 2 CPUs, at most 512 processes, hard time limits per stage;
- the project snapshot is mounted **read-only**; nothing else from the host;
- **no credentials, no Docker socket**;
- network: an **internal** Docker network with no route to the internet. The
  only way out is a proxy (`isolated_worker/proxy_allowlist.py`) that allows
  exactly four hosts: `registry.npmjs.org` and three Sigstore hosts. Everything
  else gets a logged 403.

`orchestrate.py` checks every `docker run` command against this specification
**before** running it (`assert_command_safe`), and unit tests try to inject
forbidden flags to prove the check works.

**Network self-test (must pass before any experiment):** from inside a worker,
the registry and Sigstore are reachable through the proxy (HTTP 200), a
non-allowed site is refused and the refusal appears in the proxy log, and a
direct connection without the proxy fails ("Could not resolve host").

**Where it runs:** GitHub-hosted Ubuntu runners (free for a public repo),
started manually with a read-only token and no secrets. The local Windows
machine lacked the Hyper-V components needed for WSL/Docker
(`docs/phase3_protocol.md` §2.1).

### 10.2 One experiment
For one project and one substitution, two arms:
- **B0:** the unmodified project.
- **PDR:** the project with the candidate forced in.

Each arm goes through: **resolve** (PDR only) → **install** (`npm ci
--ignore-scripts`) → **lifecycle** (`npm rebuild` + `prepare`) → **peer**
(`npm ls --all`) → **audit** (`npm audit signatures`) → **test** (`npm test`,
**twice**). The PDR arm restores the original `package.json` before testing
(Section 12 explains why). A PDR failure counts only if B0 passed that stage
(**attribution**). Running tests twice per arm exposes flaky tests.

The decision logic is a pure function (`pdr/phase3.py: classify_pair`) with
unit tests on synthetic records, written before any real result existed.

### 10.3 The micro-pilot (23 experiments, three rounds)
Before scaling, a frozen 23-experiment cohort was run three times, each round
a dated, pre-registered fix:

| Round | Change | OK | Baselines unusable |
|---|---|---|---|
| v1 | — | 9 | 13 of 23 |
| v2 | Node 22 (matches tool lock; v1 wrongly used Node 20), corepack, 8 GB | 8 | 13 of 23 |
| v3 | restore original `package.json` before tests; 6 GB Node heap | **12 of 12 judgeable** | 11 of 23 |

Lesson: the remaining problem was **untestable baselines**, not the substitution.

### 10.4 The scale-up Layer 3 (scale_v1)
- **Cohort (frozen before running, tag `freeze/scale-v1-manifest`):** all
  Layer-1-OK substitutions in the 160 repositories, minus projects whose test
  script text mentions browsers or external services, at most **5 per project**
  (seeded). **363 experiments in 91 projects.**
- **Stage A, baseline screen:** run only B0 for each of the 91 projects. A
  project is **testable** if it installs and its tests pass twice:
  **31 of 91 (34.1%**, Wilson CI [25.2, 44.3]). Untestable reasons: tests fail
  on the unmodified project (41), install fails (18), flaky (1).
- **Stage B, experiments:** **110 experiments** in those 31 projects.
- **Parallelism:** 20 GitHub jobs per stage, projects split between jobs by a
  deterministic, balanced rule; total wall time about 30 minutes.

**Results:**
- **Attributable failures at any stage: 0 of 110.** Paired failure differences
  (PDR minus B0): install 0/110, lifecycle 0/110, tests 0/108.
- 12 experiments show a lifecycle failure, but **the unmodified project fails
  identically** (a blocked post-install browser download, a binary build without
  execute permission), so it isn't the substitution.
- Upper bound (rule of three for zero events): about **2.8% per experiment**,
  **10% per project**.
- Audit signature status never got worse; **99 of 110** substitutions increased
  the number of verified attestations, as intended.

---

## 11. Statistics, simply

- **Why not just a percentage?** Because edges in the same project are linked
  (same lockfile, same maintainers). Treating 262,066 edges as independent would
  make the uncertainty look far smaller than it is.
- **Clustered bootstrap:** randomly resample whole *projects* (with replacement)
  5,000 times, recompute the rate each time, and take the middle 95% of results
  as the interval. Seed fixed (20260928) so anyone gets the same numbers.
- **Edge-weighted vs repo-weighted:** always both. "27% of edges" and "52% for
  the typical project" are both true and answer different questions.
- **Wilson interval:** for project-level proportions (e.g. 31/91 testable).
- **Rule of three:** if 0 events happen in n trials, the 95% upper bound on the
  rate is about 3/n.

Code: `pdr/stats.py` (tested so that it reproduces the registered Layer 1 figures exactly).

---

## 12. Problems we found and fixed (good to mention to reviewers)

Being able to explain these shows the work was checked, not just run.
1. **EOVERRIDE bug (Phase 1):** `overrides` fails when the package is also a root
   dependency in *any* field. Fixed by editing that field directly; this turned
   559 false "failures" into real results.
2. **Empty results counted as OK (Layer 3):** when a container crashed before
   producing data, the classifier called it "OK". Fixed: such runs are now
   `WORKER_ERROR`; a regression test prevents it returning.
3. **Missing Python in the worker image:** the container's entry script couldn't
   start; the image now installs Python.
4. **Proxy started as root and crashed under `--cap-drop=ALL`:** now runs
   directly as an unprivileged user.
5. **HTTPS interception broke every request:** the proxy now filters by
   hostname on the `CONNECT` request and passes encrypted traffic through
   untouched, so npm checks the real certificates.
6. **Wrong Node version (20 instead of 22):** four projects refused to run;
   fixed to match the recorded tool versions.
7. **Our own `package.json` edit tripped linters:** some projects lint
   `package.json` inside `npm test`, so adding `overrides` "failed" their tests.
   Fixed by restoring the original file before tests.
8. **Platform block on Windows:** one project (`socket.io`) depends on a
   Linux-only package; recorded as `PLATFORM_BLOCKED` instead of a false failure.
9. **Lockfile "recovery" mistake:** a cut-off file listing made us think the
   Phase 1 lockfiles were missing; three were overwritten with near-identical
   copies, then restored from git and the affected results re-checked
   (identical). Documented in `docs/phase2_protocol.md` §7.2.

---

## 13. How we kept the science honest

- **Pre-registration with git tags:** `freeze/layer1-alt-v1`,
  `freeze/phase3-worker-v1..v3`, `freeze/scale-v1-design`,
  `freeze/scale-v1-manifest`. Each tag predates the results it governs.
- **Amendments, not edits:** every change is a new, dated section with its
  reason written before seeing outcomes (`docs/phase3_protocol.md` §§2.1, 3.1,
  11, 12; `docs/phase4_protocol.md`).
- **Claims registry:** `docs/claims.json` + `scripts/check_claims.py` recompute
  every headline number from raw data; a test fails if any document number
  drifts. The paper's numbers are generated from it (`paper/numbers.tex`).
- **Outcome-blind selection:** cohorts are chosen from Layer 1 results and
  `package.json` text only, never from Layer 3 outcomes.
- **Negatives reported:** e.g. the micro-pilot's REWORK flag, the 34%
  testability limit, and the fact that the result weakens the original
  "enforcement is costly" hypothesis.
- **Citations:** only sources actually opened are cited (`docs/literature_matrix.md`).

---

## 14. What it all means

1. **Most dependencies lack provenance** (about 84%).
2. **Version choice rarely fixes it** (about 2.3% of deficient edges), because
   provenance-bearing versions usually don't exist close to what's resolved,
   and when they do, npm can't adopt them without moving other packages.
3. **When npm can adopt them, switching is safe in practice** for the projects
   we could test (0/110 failures).
4. **This is the consumer's view.** Release-side studies can flag a release
   whose provenance disappeared; our funnel says whether the projects that
   depend on it could have stayed on a provenance-bearing version.
5. **So the bottleneck is availability and resolution, not breakage.** Progress
   depends on publishers adding provenance and on resolvers that can optimise
   for it (e.g. MaxNPM-style solvers), not on projects fearing breakage.

---

## 15. Limitations (say these before a reviewer does)

- Provenance is read from the registry *today*, not at publish time.
- The corpora are popular, active GitHub projects with committed lockfiles, not
  the whole npm ecosystem.
- Layer 3 covers only the **34%** of projects whose own tests run reproducibly in
  a locked-down sandbox; projects needing browsers, network services or special
  tools are not represented.
- Tests only check what each project chose to test.
- Zero observed failures gives an **upper bound** (~3%), not proof of zero.
- Our "no ripple" definition is strict; with looser definitions recovery rises.

---

## 16. Repository map

| Path | What it is |
|---|---|
| `pdr/resolve.py` | Lockfile → edges (handles workspaces) |
| `pdr/provenance.py` | Reads `dist.attestations` from registry metadata (reusable by MCP-Lock, see `docs/mcp_lock_reuse.md`) |
| `pdr/policy.py` | Classifies edges (PROVENANCED / DEFICIENT_* / UNKNOWN) |
| `pdr/semver_client.py`, `scripts/semver_helper.js` | npm's own semver, batched |
| `pdr/sandbox.py` | Outcome names, `overrides`/direct-field patch logic |
| `pdr/layer1_alt.py` | Lower-version retry logic (T1) |
| `pdr/phase3.py` | Layer 3 classification, attribution, funnel, paired deltas |
| `pdr/stats.py` | Clustered bootstrap, ripple sensitivity |
| `isolated_worker/` | Dockerfile, proxy allowlist, orchestrator, in-container runner |
| `scripts/fetch_corpus.py`, `check_provenance.py` | Phase 1 pipeline |
| `scripts/layer1_resolution.py`, `scale_layer1.py` | Layer 1 |
| `scripts/scale_select_corpus.py`, `scale_select_experiments.py` | scale_v1 sampling and cohort |
| `scripts/phase3_report.py`, `scale_report.py` | Pre-specified analyses |
| `scripts/check_claims.py` | Recomputes every registered number |
| `scripts/make_figures.py` | Paper figures, tables, number macros |
| `.github/workflows/layer3.yml`, `layer3_scale.yml` | Layer 3 on GitHub runners |
| `.github/workflows/paper.yml` | Builds the paper PDF |
| `configs/experiments/` | Corpora, frozen manifests (+ SHA-256), pins |
| `results/processed/` | All result files (JSONL) and summaries |
| `docs/` | Protocols, results, literature, claims |
| `paper/` | LaTeX source, figures, PDF |
| `tests/` | 122 tests (run `python -m pytest tests -q`) |

## 17. Reproduce it

```bash
python -m pytest tests -q            # all tests must pass
python scripts/check_claims.py       # every number vs the raw data
python scripts/scale_report.py       # scale_v1 analysis
python scripts/make_figures.py       # figures, tables, paper numbers
```
Re-running data collection needs a `GITHUB_TOKEN` in the environment (corpus
selection) and npm 10.9.7; Layer 3 runs only through the GitHub workflows
(manual dispatch), never on a personal machine.

---

## 18. Questions reviewers are likely to ask

**Q: Isn't provenance just about security? Are you saying these packages are safe?**
No. Provenance is evidence of *origin*. We never treat it as a safety judgment.

**Q: Why not just look at the declared range? If a version satisfies it, isn't it fine?**
That is the screening step, and it overstates recoverability. npm has to fit
the version into the whole tree; in 62% (scale_v1) to 70% (Phase 1) of cases
that moves other packages (ripple).

**Q: Why count edges and not packages?**
An edge is the real decision point ("this requirement resolved to this
version"). We also report per-project averages so big projects don't dominate.

**Q: Isn't this already covered by Santos-Grueiro's release-authority paper (arXiv 2606.22593)?**
No, it is the other end of the supply chain. That paper is producer-side and
release-time: it compares each release with the one before it (publisher,
workflow, repository, provenance, signing) across 45,812 releases in five
registries and builds a review queue of 204 discontinuities. It leaves
dependency graphs out on purpose. We are consumer-side and resolution-time: our
unit is a resolved edge in a project's lockfile, and we ask whether that project
can get provenance within its own ranges through npm's resolver, and whether
switching breaks it. Both use provenance loss between releases; their rates
(shares of releases) and ours (shares of resolved edges) are not comparable.

**Q: Couldn't a smarter solver do better than npm?**
Possibly; MaxNPM-style solvers optimise across the whole tree. We measured what
npm itself does today, and say so explicitly.

**Q: Running untrusted code is dangerous. How did you contain it?**
Disposable containers, no privileges, read-only filesystem, no credentials,
internal-only network with a four-host allowlist, a self-test proving isolation
before every run, on throwaway cloud VMs (Section 10.1).

**Q: Two-thirds of projects were untestable. Doesn't that bias the result?**
It limits it. The behavioural result is about projects with self-contained,
reproducible tests. We report the 34% openly and don't generalise beyond it.

**Q: Zero failures sounds too good. Could the harness hide failures?**
We found and fixed exactly such problems (empty runs counted as OK, lint
artifacts). The baseline arm runs the same steps, failures must be absent in
B0 to count, tests run twice, and a validator rejects malformed records. Zero
observed still only gives an upper bound (~3%).

**Q: Did you change the method after seeing results?**
Every change is a dated amendment with its reason stated beforehand, and the
plans are tagged in git before the runs. The micro-pilot changes were based on
baseline logs only (which don't involve the substitution).

**Q: Why do edge- and repo-weighted numbers differ so much?**
A few projects contribute many near-identical candidates. Pooled numbers follow
the big projects; per-project averages follow the typical one.

**Q: What would you do next?**
Compare against an optimising solver on a subset, extend the worker image so
more projects are testable, and replicate on another ecosystem (e.g. PyPI
attestations).
