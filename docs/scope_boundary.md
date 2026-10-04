# Scope boundary: provenance != safety

This project measures **origin/integrity evidence**, not software safety.
Every script and doc in this repo must respect the distinction below
(`tests/test_no_safety_claims.py` enforces the vocabulary mechanically):

- **Absent provenance** -- no signed link from package to source/build. Says
  nothing about whether the code is malicious; most of the npm ecosystem
  predates provenance and is neither more nor less safe for lacking it.
- **Invalid/failed provenance** -- a link was claimed but doesn't verify.
  Stronger signal than "absent", still not proof of malice.
- **Valid provenance for malicious code** -- a real, verifiable link from a
  compromised or intentionally malicious build to its source. Provenance
  answers "where did this come from", not "is this safe to run". A
  compromised CI pipeline, a malicious maintainer, or a trojaned dependency
  introduced upstream of the signing step can all produce valid provenance
  for harmful code.
- **Compromised build identity** vs **malicious source** vs **malicious
  dependency update** -- three different failure modes that provenance
  verification distinguishes to different degrees (it can catch a spoofed
  builder identity; it cannot catch a legitimate builder faithfully signing
  code that is itself malicious).

Concretely: `DEFICIENT_RESOLUTION_PRESERVING` in `pdr/policy.py` means "a
version exists that would add origin evidence without a large version
jump" -- it is never shorthand for "safe to adopt", and nothing in this
codebase should present it that way.

## In-scope / out-of-scope shape (per README)

- **In-scope (Mastra shape):** a package/version pair that is genuinely
  missing verifiable provenance, where the PDR pipeline's job is to measure
  how common that is and whether it's recoverable.
- **Out-of-scope (RedHatInsights valid-attestation shape):** cases with a
  *valid* attestation attached to a build that later turns out to be
  compromised or malicious. That is a real and important security question,
  but it is a different research question than PDR's (which is about
  measuring deficiency and recovery, not about attestation forgery or
  build-pipeline compromise detection). Builder/source-path change is
  treated here strictly as an *enrichment signal* for the secondary
  regression analysis (pdr/regression.py) -- never as proof of compromise
  on its own, without independent labels.
