"""
pdr.semver_client
==================
npm dependency ranges use npm's own semver grammar (^, ~, x-ranges, ||,
pre-release rules, etc). Re-implementing that in Python would be a second,
divergent implementation of the exact thing we're trying to measure
precisely -- so instead we shell out, in large batches, to Node's `semver`
package (the same library npm itself depends on) via scripts/semver_helper.js.

Batching matters: with thousands of edges, spawning one Node process per
comparison would dominate runtime. This wrapper queues tasks and flushes
them in a single subprocess call per `run_batch()`.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

HELPER_PATH = Path(__file__).resolve().parent.parent / "scripts" / "semver_helper.js"


def run_batch(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not tasks:
        return []
    proc = subprocess.run(
        ["node", str(HELPER_PATH)],
        input=json.dumps(tasks),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"semver_helper.js failed: {proc.stderr}")
    return json.loads(proc.stdout)
