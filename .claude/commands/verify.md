---
description: Full consistency check — tests, claims registry, frozen-file integrity, stale terminology
---
Run the project's consistency checks and report results plainly. Do not fix
anything until you have reported.

1. `python3 -m pytest tests -q` — report the pass count.
2. `python3 scripts/check_claims.py` — if it fails, list each mismatch; do NOT
   edit `docs/claims.json` to silence it (see CLAUDE.md rule 10).
3. Recompute the manifest hash and compare it with the committed one:
   `python3 -c "import json,hashlib;m=json.load(open('configs/experiments/phase3_micropilot_manifest.json'));print(hashlib.sha256(json.dumps(m,sort_keys=True,separators=(',',':')).encode()).hexdigest())"`
   against `configs/experiments/phase3_micropilot_manifest.sha256`.
4. `grep -rn "C_deployability_gap\|PILOT SCALE" scripts tests` — must be empty.
5. `git status --short` — list uncommitted changes.
6. Summarize: what passes, what fails, and the single most important thing to
   fix next. Do not claim anything is verified that you did not run.
