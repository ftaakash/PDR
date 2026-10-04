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
