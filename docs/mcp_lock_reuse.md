# Reusing PDR's attestation parsing in MCP-Lock

*Added 2026-10-08. MCP-Lock is a separate project; this note only records which
PDR modules it can reuse and under what caveats. Nothing here changes PDR's
frozen methodology or results.*

MCP servers are often distributed as npm packages, so MCP-Lock faces the same
low-level question PDR answers for every resolved edge: does this exact npm
version carry provenance, and does `npm audit signatures` verify it? PDR
already has tested code for that. Reuse it rather than rewriting it.

## What to reuse

| Need in MCP-Lock | PDR code | Status in PDR |
|---|---|---|
| Does `name@version` have npm provenance? | `pdr/provenance.py`: `fetch_packument(name, cache_dir)` returns a `Packument` whose `versions[v].has_provenance` is true iff the registry packument carries `dist.attestations` | Used for every edge in Phase 1 and scale_v1 (331,758 edges in total); verified live against packages with and without provenance before it was written |
| Publish time per version | same `Packument`, `versions[v].time` | Used by the regression scan |
| Provenance lost between adjacent releases | `pdr/regression.py`: `scan_package_regressions(pk)` and `package_regression_status(pk)` (`regressed` / `no_regression` / `NA`) | Unit-tested in `tests/test_regression_na.py`; NA is kept distinct from "no regression" |
| Full Sigstore bundle (SLSA predicate, DSSE envelope) for one version | `pdr/regression.py`: `fetch_attestation_bundle(name, version)` from `https://registry.npmjs.org/-/npm/v1/attestations/<name>@<version>` | Endpoint confirmed reachable; the function is an entry point only and was never run at scale in PDR |
| Parse `npm audit signatures` output | `pdr/phase3.py`: `parse_audit_signatures(text)` returns verified registry signatures, verified attestations, invalid and missing counts plus `parse_ok` | Checked against real worker output in the Phase 3 micro-pilot (`docs/phase3_micropilot_results.md`) and used in all 110 scale_v1 experiments; unit-tested in `tests/test_phase3_logic.py` |
| Scoped-name encoding for registry URLs | `pdr/provenance.py`: `_encode_name` | Used by both fetchers |

## How to reuse

Prefer importing over copying, so a fix lands in one place. Two options:

1. **Vendor as a dependency.** Add PDR as a git dependency pinned to a tag
   (for example `phase-4-paper-draft` or a later release tag) and import
   `pdr.provenance`, `pdr.regression` and `pdr.phase3.parse_audit_signatures`.
   These modules use only the Python standard library.
2. **Extract a small shared package** (for example `npm_attest`) holding
   `provenance.py`, the regression functions and `parse_audit_signatures`,
   with their tests (`test_regression_na.py` and the audit cases of
   `test_phase3_logic.py`), and make both PDR and MCP-Lock depend on it.
   Do this only after the PDR paper ships (see `TASKS.md`, "Deliberately later").

## Caveats to carry over

- **Presence is not verification.** `has_provenance` reads the registry's
  current `dist.attestations` field. It does not verify the Sigstore bundle.
  Verification comes from `npm audit signatures` (parsed by
  `parse_audit_signatures`) or from verifying the bundle yourself.
- **Current state, not publish-time state.** The registry record is read
  today (see the `pdr/provenance.py` docstring).
- **The audit parser reads the human-readable summary.** Its regexes match the
  summary lines produced by the npm in PDR's worker image. If MCP-Lock uses another npm
  version, re-check it on real output; `parse_ok` is false when nothing
  matched, and that must not be read as "no change".
- **Provenance is origin evidence, never a safety claim.** Keep that wording
  in MCP-Lock too; PDR enforces it with `tests/test_no_safety_claims.py`.
