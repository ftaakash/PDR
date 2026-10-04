# Phase 2, Layer 2 results: structural installation

13 Layer-1-CONFIRMED (`outcome == "OK"`) candidates, per the pre-committed
sample in `docs/phase2_protocol.md` Section 4:
`axios/axios` (5), `mozilla/source-map` (5), `koajs/koa` (2),
`tj/commander.js` (1). **`nodeca/js-yaml` and `eemeli/yaml` contributed 0**
-- both had zero Layer-1-`OK` candidates available (noted, not silently
substituted for other repos). Script: `scripts/layer2_structural_install.py`.
Raw output: `results/processed/phase2_layer2_results.jsonl`.

## A methodological fix made before running anything

`npm ci` refuses to run unless `package.json` and `package-lock.json` are
already mutually consistent -- confirmed empirically (not assumed) by
running it against a patched `package.json` alongside the original,
unmodified lockfile: it exits nonzero with a usage error rather than
attempting the install. Fix: for the PDR-substituted tree, the script now
first regenerates a consistent lockfile using the same
`npm install --package-lock-only --ignore-scripts` step Layer 1 already
validated, THEN runs the real `npm ci --ignore-scripts` against that
now-consistent pair. The B0/B1 baseline tree's files are already consistent
by construction (they're the repo's real, as-fetched files), so baseline
installs skip straight to `npm ci`.

## Result: structural installation

**13/13 (100%) real `npm ci --ignore-scripts` installs succeeded** -- both
the B0/B1 baseline (one per repo, 4 total) and every PDR-substituted tree.
Wall-clock time per install: 1.5s-8.2s, well within budget; no timeouts, no
install failures, no ripple-induced breakage severe enough to fail
installation outright at this sample size.

This is a genuine, if small-sample, positive data point for Gate C's
install-success sub-criterion -- consistent with Phase 1.5's small-scale
observation that structural failures were rare even when resolution itself
was messy. It should NOT be read as "candidates are safe to adopt": this
sample is exclusively Layer-1-`OK` candidates (the 27.16% that were already
the cleanest tier), from 4 small/medium repos chosen for tractability, and
install success says nothing about test-suite survival (Layer 3, not run).

## Result: `npm audit signatures` (B0/B1 vs. PDR) -- blocked by network scope, not methodology

Every single `npm audit signatures` invocation failed with
`npm error Failed to download`, both for baseline and PDR trees, uniformly.
Traced (not assumed) via the npm debug log: the failure originates in
`tuf-js`'s `Updater.refresh` / `DefaultFetcher.fetch` -- `npm audit
signatures` needs to fetch Sigstore's TUF (The Update Framework) trust-root
metadata from its CDN before it can verify anything, and that CDN's domain
is not in this session's network egress allowlist (only
`registry.npmjs.org`, `github.com`, and similar npm/GitHub-related domains
are reachable -- `docs/phase2_protocol.md` Section 1). This reproduced
identically outside the harness too (a bare `npm audit signatures` in an
unrelated probe directory), confirming it's an environment property, not a
bug in how the script invokes the command.

**This is a real scope boundary, not a workaround-able bug**, and is not
routed around here -- the network allowlist is a deliberate platform
control. Gate D's B1-comparison data point (does PDR substitution change
`npm audit signatures` status) is **not collected in this session** as a
result. It needs either the TUF CDN domain added to an approved network
scope, or to run somewhere with fuller network access (e.g. a developer's
own machine, or Phase 2's eventual real isolated-worker infrastructure,
which will need registry+Sigstore-CDN reachability specified explicitly in
its network policy -- worth adding to `docs/phase2_protocol.md` Section 5's
"restricted network (npm registry only)" line, which as written would hit
this exact same wall).

## What Gate D data exists after Layer 1 + Layer 2

- Install-success delta (PDR vs. B0): 0 percentage points at this sample
  size (13/13 vs. 4/4, both 100%) -- too small a sample and too favorable a
  subset (Layer-1-`OK` only) to generalize, but a real, not fabricated,
  first data point.
- `npm-audit-signatures`-status delta: **not measured**, for the network
  reason above, not a methodological gap.
- Test-failure-rate delta (the frozen PRIMARY Gate D metric,
  `docs/methodology_freeze.md` Section 8): **not measured** -- requires
  Layer 3, not run in this session (`docs/phase2_protocol.md` Section 5).

Gate D remains PENDING. What changed this session is that it now has two
real, if partial, inputs instead of zero.
