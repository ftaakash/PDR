# Prior-art / literature matrix (stub)

README.md is explicit that "Gate is artifact, not novelty" -- the exhaustive
adversarial literature audit is `PDR_Proposal_and_Implementation_Plan.md`'s
job (designed as a standalone prompt for a separate deep-research pass), and
README's "FROZEN-GO (8.5/10)" status line indicates that pass already ran
and PDR survived it. This repo does not re-litigate novelty; it builds and
runs the empirical artifact the audit said was the remaining gate.

What's filled in below are only the prior-art facts this pipeline itself
needed to verify directly (to avoid silently assuming tool behavior, per the
audit prompt's own "verify, don't assume" standard) -- not a full matrix.

| Tool/mechanism | Verified fact | Source |
|---|---|---|
| npm provenance / `dist.attestations` | Presence of `dist.attestations` on a version's registry packument is the ground-truth signal for "this version has provenance"; confirmed live against `turbo`, `vite`, `tsx`, `esbuild`, `@changesets/cli` (present) vs `express`, `npm`, `eslint` (absent) before writing `pdr/provenance.py`. | live registry query, this session |
| npm provenance general availability | GA'd 2023-09-26; beta available from npm 9.5.0 (2023-04-19). Used as the era-control cutoff in Gate A. | github.blog changelog, 2023-09-26; github.blog, 2023-04-19 |
| `npm audit signatures` (Baseline 1) | Reads the same `dist.attestations`/signature data this pipeline reads (per npm's own documentation of the command). PDR's stated position (frozen in the master prompt) is that B1 already does verification -- PDR characterizes prevalence/recoverability/cost on top of it, not around a claimed gap in it. | npm docs (not re-verified line-by-line in this pilot; flagged for the full audit) |
| `-/npm/v1/attestations/{name}@{version}` endpoint | Returns the full Sigstore attestation bundle (SLSA predicate + DSSE envelope) for a version; reachable and returns real data for `vite@8.3.0`. This is the endpoint Phase 2's builder/source-path regression enrichment would use. | live registry query, this session |

**Everything else in the audit prompt's literature-search sections
(academic databases, the full competitor matrix, KILL TEST 16's reviewer
objections, etc.) has not been (re-)run here** -- that is a distinct,
much larger research task from building and executing the G1 artifact, and
this session prioritized the latter per the "Run PDR-G1 now" instruction in
README's Status line. If a fresh literature pass is wanted, the original
`PDR_Proposal_and_Implementation_Plan.md` is still the right prompt to run
it with (ideally against a deep-research-capable tool with academic
database access, e.g. multi-source literature search — this pipeline's own
web access is general web search, not IEEE/ACM/USENIX database access).

---

## Related-work matrix (TASKS.md T4, retrieved 2026-10-05)

Every row below was opened at the URL given on 2026-10-05 and the "measures"
column is taken from what that page says (abstract or full text), not from
memory. Rows from `docs/audit_v2.md` (2026-10-04) were re-opened. Where only
an abstract page was readable, that is stated.

### A. Dependency updates, semver and breaking updates

| Work | URL (retrieved 2026-10-05) | What it measures | How PDR differs |
|---|---|---|---|
| Pinckney, Cassano, Guha, Bell. *A Large Scale Analysis of Semantic Versioning in NPM*. arXiv 2304.00394 (MSR 2023 per search index; venue not shown on the opened page) | https://arxiv.org/abs/2304.00394 (abstract) | Every version of every npm package; a time-travelling resolver tracks update flow; security patches reach 90.09% of dependents when semver is used correctly | Studies whether *newer* versions flow down ranges; PDR asks whether an in-range version with *provenance* exists and whether npm's resolver accepts it on real application lockfiles |
| Pinckney, Cassano, Guha, Bell, Culpo, Gamblin. *Flexible and Optimal Dependency Management via Max-SMT* (PacSolve / MaxNPM). ICSE 2023, DOI 10.1109/ICSE48619.2023.00124 | https://www.osti.gov/biblio/2223021 (bibliographic record; the ACM page returned 403 and the author page 404). Abstract numbers re-confirmed only via search-index text: beats `npm audit fix` on vulnerability reduction in 33% of cases, newer deps in 14%, fewer deps in 21% | Configurable-objective solver as a drop-in npm replacement | Highest overlap: a provenance objective could plug into MaxNPM. PDR measures what npm's *own* resolver does with targeted overrides; it does not propose a solver and must not claim npm cannot find what an optimizer could (T4b) |
| He, He, Zhang, Zhou. *Automating Dependency Updates in Practice: An Exploratory Study on GitHub Dependabot*. IEEE TSE (arXiv 2206.07230) | https://arxiv.org/abs/2206.07230 (abstract) | Dependabot adoption: technical lag falls, developers accept bot PRs, compatibility scores too scarce, 11.3% of projects deprecate Dependabot | Arbitrary version bumps chosen by a bot; PDR's candidates are provenance-conditioned and evaluated without merging |
| Rombaut, Cogo, Hassan. *Leveraging the Crowd for Dependency Management: An Empirical Study on the Dependabot Compatibility Score*. arXiv 2403.09012 (2024) | https://arxiv.org/abs/2403.09012 (abstract) | 579,206 Dependabot PRs, 618,045 compatibility-score records; scores cannot be computed for 83% of updates | Crowd evidence on update breakage; PDR measures resolution/install/test survival directly per repository |
| Mujahid, Abdalkareem, Shihab, McIntosh. *Using Others' Tests to Avoid Breaking Updates*. MSR 2020 (search index lists the ACM title as "...to Identify Breaking Updates", DOI 10.1145/3379597.3387476; reconcile before citing) | https://2020.msrconf.org/details/msr-2020-papers/37/Using-Others-Tests-to-Avoid-Breaking-Updates (abstract) | 391,553 npm packages; dependents' tests detect 6 of 10 breakage-inducing versions | Uses tests as a breakage oracle, as PDR's Layer 3 does; no provenance, no application lockfiles |
| Venturini, Cogo, Polato, Gerosa, Wiese. *I depended on you and you broke me: An empirical study of manifesting breaking changes in client packages*. TOSEM 2023 (arXiv 2301.04563) | https://arxiv.org/abs/2301.04563 (abstract) | npm clients: about 12% of dependents and 14% of their releases hit breaking changes in non-major updates; 44% of manifesting breaking changes are in minor/patch releases | Direct prior for why PDR's minor/patch tolerance does not make a switch harmless; motivates Layer 3 |
| Reyes, Gamage, Skoglund, Baudry, Monperrus. *BUMP: A Benchmark of Reproducible Breaking Dependency Updates*. SANER 2024 (arXiv 2401.09906) | https://arxiv.org/abs/2401.09906 (abstract) | 571 reproducible breaking updates from 153 Java/Maven projects | Java/Maven breaking-update benchmark; PDR is npm and measures provenance recovery |
| Maksymiuk. *How Reproducible Are Build and Test Outcomes of Dependency Updates in JavaScript/npm Projects?* BSc thesis, TU Delft, 2026-06-20 | https://repository.tudelft.nl/file/File_5ca45497-99f6-4280-aa7a-d64b15c86ce1 (full PDF; abstract read) | 2,777 Dependabot npm PRs, 3,142 experiments, 9,426 Dockerized runs; 4.8% of experiments and 4.0% of PRs non-reproducible, concentrated in tests and in browser, native-addon, peer-dependency and Yarn projects | Methodological evidence for T7 (single vs repeated test runs) and the hermetic screen; a bachelor thesis, cite as such |
| He, Vasilescu, Kästner. *Pinning Is Futile: You Need More Than Local Dependency Versioning to Defend against Supply Chain Attacks*. PACMSE 2 (FSE 2025), arXiv 2502.06662 | https://arxiv.org/abs/2502.06662 (abstract) | npm counterfactual simulation of pinned vs floating constraints; pinning direct deps increases exposure to malicious updates in larger graphs because of npm's resolution | Closest in method (counterfactual resolution under npm's rules); outcome is vulnerability/malicious-update exposure, not provenance recoverability. Possibly the untitled "counterfactual pinning" paper audit v1 mentioned (not confirmed) |
| Wang, Wang, Shen, Chang. *Understanding and Detecting Peer Dependency Resolving Loop in npm Ecosystem*. arXiv 2505.12676 (2025) | https://arxiv.org/abs/2505.12676 (abstract) | "PeerSpin": peer-dependency conflicts that loop npm; 5,662 packages / 72,968 versions affected | Background for PDR's `PEER_CONFLICT` outcome; not about provenance |

### B. Provenance, signing and release authority

| Work | URL (retrieved 2026-10-05) | What it measures | How PDR differs |
|---|---|---|---|
| Schorlemmer et al. *Signing in Four Public Software Package Registries: Quantity, Quality, and Influencing Factors*. IEEE S&P 2024 (arXiv 2401.14635) | https://arxiv.org/abs/2401.14635 (abstract) | Signing prevalence, quality and trends in Maven, PyPI, Docker Hub, Hugging Face; mandates raise quantity, tooling raises quality | Package-level adoption, **npm not covered**; PDR measures consumer-side recoverability |
| Solarin, Kalu, Davis, Amusuo. *Reproducibility is Not Enough: Artifact Verifiability in Decentralized-Build Package Ecosystems*. arXiv 2608.18180 (2026) | https://arxiv.org/html/2608.18180 (full HTML) | Crates.io, npm, PyPI, RubyGems; for npm, provenance raises rebuild completion from 50.9% to 72.4%, but with the package set held constant the direct gain is 1.5 points; most of the advantage reflects adopting projects' practices | Different construct ("recovery" of source state for rebuilds). Required threat to validity for PDR: provenance-bearing candidates come from projects with different practices (audit v2 condition 6) |
| Santos-Grueiro. *On Good Authority: Release-Authority Measurement for Registry-Mediated Package Ecosystems*. arXiv 2606.22593 (2026) | https://arxiv.org/abs/2606.22593 (abstract, 2026-10-05); full text v2 (30 Jun 2026) read 2026-10-08 via alphaXiv, body Sections 1-7 and ethics, appendices skimmed | **Producer-side, release-time.** 45,812 releases (3,427 npm) in a purposefully sampled Apr 2024-Jun 2026 cohort across npm, PyPI, Maven Central, crates.io, RubyGems (Go as a boundary adapter); each release compared with its immediate predecessor on publisher, repository, workflow, provenance, signing and mediation; 204 policy-triggering discontinuities form a review queue (npm: 66 triggers). User: a registry analyst or downstream reviewer triaging a new release before payload analysis. Explicitly treats dependency graphs as describing consumption, not production, and leaves them out | **PDR is consumer-side, resolution-time.** Unit = resolved edge in an application lockfile, not a release; asks what origin evidence a project can obtain under its own declared ranges and npm's resolver, and what switching costs (install, scripts, tests). Shared signal: provenance loss between adjacent releases (their trigger; our secondary RQ4 regression scan and, downstream, a deficient edge). Rates not comparable (share of sampled releases vs share of resolved edges) |
| Peruma, Choy, Lee, De Oliveira Santos. *Understanding npm Developers' Practices, Challenges, and Recommendations for Secure Package Development*. CHASE 2026 (arXiv 2601.20240) | https://arxiv.org/abs/2601.20240 (abstract) | Survey of 75 npm package developers; 40% satisfied with npm security tools | Producer-side perceptions; context only |
| pnpm `trustPolicy`, danielroe/provenance-action, vlt `reproduce` README | see `docs/audit_v2.md` (opened 2026-10-04, not re-opened 2026-10-05) | Enforcement/detection tooling and package-level adoption counts | Baselines; they block or detect, they do not search for in-range alternatives |

### Unverified: listed, not cited

- Decan and Mens, *What Do Package Dependencies Tell Us About Semantic
  Versioning?*, IEEE TSE 47 (2021) 1226-1240: bibliographic details seen only
  in search-index snippets; the CORE page returned 403. Open before citing.
- The "University of Bonn thesis, 63,827 versions / 23,648 packages" and the
  npm RFC 0049 statement from audit v1: still not found or opened.
- Exaforce adoption figure (secondary editorial only) and blog adoption
  figures surfaced by search (e.g. a zenn.dev post): not primary, not cited.
- MaxNPM's abstract numbers: re-confirmed only through search-index text this
  pass; audit v2 opened the author page and Zenodo artifact on 2026-10-04.

### Draft novelty statement (wording rule: CLAUDE.md #11)

> Prior work measures how updates flow through npm's semver ranges and how
> often they break clients (Pinckney et al.; Venturini et al.; He et al.;
> Rombaut et al.), how pinning interacts with npm's resolver (He, Vasilescu
> and Kästner), how to compute policy-optimal dependency sets (MaxNPM), how
> widely registries carry signatures or provenance (Schorlemmer et al.;
> Solarin et al.), and how release-authority evidence, including provenance,
> changes between adjacent releases at publication time (Santos-Grueiro, a
> producer-side, release-time study). In the searched corpus, no directly matching
> work was identified that measures, on real application lockfiles, whether a
> provenance-bearing version exists within a deficient dependency's declared
> range and how much of that apparent recovery survives npm's actual resolver,
> installation, and the repository's own tests, that is, provenance seen from
> the consumer at resolution time.

Search scope for this pass: general web search plus arXiv, conference and
institutional pages; no IEEE Xplore / ACM DL full-text access (ACM pages
returned 403). A Gate G sweep before submission is still required.
