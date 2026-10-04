# CLAUDE.md — PDR (Provenance Debt at Resolution)

You are continuing an empirical software-engineering research project that
was built in an earlier chat session. Read this file fully, then
`PILOT_RUN_REPORT.md` (phase log) and `TASKS.md` (what to do next).

## What the project is

An empirical study of **npm provenance recovery**: how often a resolved npm
dependency lacks build provenance, how often an in-range provenance-bearing
version exists, and how much of that apparent recovery survives (1) real npm
resolution, (2) installation, (3) lifecycle scripts + the repo's own tests.
The result is a *funnel with attrition at every stage*, not one number.
Owner: Aakash (CS student). Goal: an IEEE-quality paper, plus a public,
reproducible artifact. Provenance is **origin evidence, never a safety
claim** — `tests/test_no_safety_claims.py` enforces this in code and output.

## State at handoff (verify with `/verify`, do not trust this paragraph)

Done and data-backed: pilot (7 repos), Phase 1 (45 repos, 69,692 edges,
repo-clustered CIs), Layer 1 (2,349 candidates through the real npm
resolver), Layer 2 (13 structural installs). Built and unit-tested but
**never executed against a live Docker daemon**: the Phase 3 isolated worker
(`isolated_worker/`), `pdr/phase3.py`, the frozen 23-experiment micro-pilot
manifest. **No Layer 3 result exists.** Several things are unverified by
design — see `docs/phase3_protocol.md` Section 8.

## NON-NEGOTIABLE RULES

### A. Execution safety (this project runs untrusted third-party code)

1. **Never execute code from studied packages/repos on the host.** Allowed on
   the host: `npm install --package-lock-only --ignore-scripts`,
   `npm ci --ignore-scripts` (in a temp dir), and git *metadata* operations
   (clone/log/rev-parse/archive). **Forbidden on the host:** `npm install` or
   `npm ci` without `--ignore-scripts`, `npm test`, `npm run ...`,
   `npm rebuild`, or running `node`/`python` on any studied repo's files.
2. **Layer 3 (lifecycle scripts + tests) runs only through
   `python3 isolated_worker/orchestrate.py`**, which builds hardened
   `docker run` commands and refuses to run without a passing network
   self-test. Never call `docker run/exec/cp` directly. Never run
   `isolated_worker/runner.py` directly (it refuses, by design).
3. **Do not weaken the isolation.** Do not edit `assert_command_safe`,
   `REQUIRED_TOKENS`, `FORBIDDEN_SUBSTRINGS`, the proxy allowlist, or the
   Dockerfile hardening without stopping to ask the human, and never to make a
   failing run pass. If the sandbox blocks something, report it.
4. No secrets in the repo. A GitHub token, if provided, comes from the
   environment (`GITHUB_TOKEN`) only. Never print it, never commit it.
5. Do not `git push`, publish, or upload anything without explicit approval.

### B. Scientific integrity

6. **Frozen means frozen.** `docs/methodology_freeze.md`, the Phase 2/3
   protocol parameters, seeds, thresholds, and
   `configs/experiments/phase3_micropilot_manifest.{json,sha256}` are frozen.
   Changing one requires: a new dated section or experiment ID, a stated
   reason *before* looking at outcomes, and human approval. Never edit raw
   result files (`results/raw/**`, `*.jsonl`) by hand; scripts append, and the
   only precedent for rewriting is the documented Layer 1 reclassification.
7. **No post-hoc analysis dressed as pre-specified.** Anything chosen after
   seeing results is labelled *exploratory* where it is reported.
8. **Report negatives and limitations as prominently as positives.** If a
   result weakens the thesis, say so (the Outcome A/B/C rule in
   `docs/methodology_freeze.md` Section 2 applies).
9. **Both estimands, always with intervals:** edge-weighted and
   repo-weighted figures, with repository-clustered CIs. Edges within a repo
   are not independent. Never quote the pooled number alone.
10. **Every number in prose must be recomputable.** Run
    `python3 scripts/check_claims.py` (also a pytest). When data change,
    update `docs/claims.json` and every doc that quotes the number in the
    same commit. Never edit `claims.json` just to make the check pass.
11. **Citations:** only cite what you have actually opened. Record URL,
    title, and retrieval date in `docs/literature_matrix.md`. Never invent or
    "recall" a citation. Phrase novelty as "no directly matching work was
    identified in the searched corpus", never "first".
12. **Verify before asserting.** Several earlier errors were transcription
    slips (a repo count, a stale threshold). Re-read the file or re-run the
    command before writing a figure into a document.

### C. Engineering workflow

13. Loop: **design doc -> implement -> test -> commit -> verdict.** Write or
    amend the relevant `docs/*.md` *before* running anything expensive.
14. `python3 -m pytest tests -q` must pass before every commit. Put decision
    logic in pure functions with tests (see `pdr/phase3.py`,
    `tests/test_layer1_patch_logic.py`); keep execution thin.
15. Long jobs use the resumable pattern (append-only JSONL + skip-done), as in
    `scripts/layer1_resolution.py`. Run them in the background and poll.
16. Small commits with meaningful messages. Tag milestones:
    `git tag -a freeze/<name> -m "..."` *before* the run it freezes, so the
    pre-registration is verifiable from git history.
17. When you find a bug: root-cause it against real output, fix it, add a
    regression test, and document it in the relevant results doc — as
    Layer 1's EOVERRIDE and Phase 1's subprocess-batching bugs were.

## Autonomy boundaries — stop and ask the human when

- a task is marked `HUMAN-GATE` in `TASKS.md`;
- Docker/WSL setup, replacing the Dockerfile digest, or any `docker` command
  is needed (the human runs or explicitly approves these);
- a frozen parameter, the manifest, or isolation code would change;
- results contradict the working thesis in a way that changes the paper's
  framing (present the data and the options; do not pick a story);
- you would send anything off the machine, or need a credential;
- three consecutive attempts at the same problem fail.

## Environment notes

- Python 3.10+ (`python3`; on native Windows the README uses `py`). Node 20+
  needed for `scripts/semver_helper.js`: run `npm install` once in the repo
  root. Docker needed only for Layer 3.
- Recommended on Windows: WSL2 (Ubuntu) + Docker Desktop with WSL integration;
  run Claude Code inside WSL so `setup.sh`, paths, and `python3` behave as
  documented. `isolated_worker/setup.sh` is bash.
- Tool calls time out around 300 s in some environments: batch + resume.
- `results/raw/provenance*/packuments/` (about 1.4 GB) is a regenerable cache
  and is git-ignored; `check_provenance.py` refetches it.

## Command cheat sheet

```bash
python3 -m pytest tests -q                      # must pass
python3 scripts/check_claims.py                 # docs numbers vs data
python3 scripts/check_claims.py --show          # recomputed values
python3 scripts/fetch_corpus.py --config configs/experiments/kill_v1_phase1_n45.yaml --out-dir results/raw/resolve_phase1
python3 scripts/check_provenance.py --in results/raw/resolve_phase1 --out results/raw/provenance_phase1/edges.csv
python3 scripts/layer1_resolution.py --limit 200     # resumable
python3 scripts/phase3_select_micropilot.py          # deterministic; rewrites manifest + hash (frozen!)
python3 scripts/phase3_pin_snapshots.py --materialize
python3 isolated_worker/orchestrate.py --dry-run     # no docker needed
```

Slash commands in `.claude/commands/`: `/verify` (full consistency check),
`/next` (pick and run the next task per `TASKS.md`).
