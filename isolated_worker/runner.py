#!/usr/bin/env python3
"""
isolated_worker/runner.py -- runs INSIDE the disposable worker container only.

This is the one place in the project where third-party npm lifecycle scripts
and repository test suites execute. It therefore refuses to start unless it
can prove it is inside the purpose-built image: the image bakes in a marker
file and an environment flag (see Dockerfile). Neither exists on a developer
machine or in an analysis session, so running this file directly on a host
exits with status 3 before touching npm. That is defense in depth against
ACCIDENTAL host execution; it is not the isolation itself -- the isolation is
the container boundary the orchestrator builds (orchestrate.py).

Contract: read one JSON spec from $PDR_SPEC, run one arm (b0 | pdr) of one
experiment, print exactly one final line `PDR_RESULT_JSON:<json>` on stdout.
No host mounts are writable; the repo snapshot is copied from the read-only
/input/snapshot into tmpfs /work.

Stages (docs/phase3_protocol.md Section 4): resolve (pdr only) -> install
(`npm ci --ignore-scripts`) -> lifecycle (`npm rebuild` + root `prepare`) ->
peer (`npm ls --all --json`) -> audit (`npm audit signatures`) -> test.
A resolve/install failure stops the arm (nothing to run on); later failures
are recorded and the arm continues where meaningful.
"""
from __future__ import annotations

import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import time

MARKER = "/opt/pdr-worker-image-marker"
RUNNER_VERSION = "phase3.runner.v1"
NET_PATTERN = re.compile(r"ENOTFOUND|ECONNREFUSED|ECONNRESET|ETIMEDOUT|EAI_AGAIN|tunneling socket|"
                         r"Proxying refused|403 Forbidden|Failed to download|getaddrinfo", re.I)


def refuse_if_not_worker() -> None:
    if not os.path.exists(MARKER) or os.environ.get("PDR_ISOLATED_WORKER") != "1":
        sys.stderr.write(
            "REFUSING TO RUN: this runner executes third-party install scripts and test suites and "
            "must only run inside the isolated worker image (marker file / PDR_ISOLATED_WORKER missing). "
            "Use isolated_worker/orchestrate.py.\n")
        sys.exit(3)


def tail(path: str, n: int) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - n))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def run_stage(cmd, cwd, timeout, env, tail_bytes, shell=False) -> dict:
    """Run one command with output to files (never held in memory), own process
    group (so a timeout kills grandchildren too), and a hard wall-clock limit."""
    out_p, err_p = f"/tmp/stage_{time.time_ns()}.out", f"/tmp/stage_{time.time_ns()}.err"
    t0 = time.time()
    timed_out = False
    with open(out_p, "wb") as fo, open(err_p, "wb") as fe:
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=fo, stderr=fe, start_new_session=True, shell=shell)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
    rc = None if timed_out else p.returncode
    res = {
        "ran": True, "exit_code": rc, "timed_out": timed_out,
        "oom": (rc in (-9, 137)) and not timed_out,          # SIGKILL not from our timeout: likely OOM-killer
        "elapsed_s": round(time.time() - t0, 2),
        "peak_rss_kb_children_cumulative": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "stdout_tail": tail(out_p, tail_bytes), "stderr_tail": tail(err_p, tail_bytes),
    }
    res["network_failure_suspected"] = bool(NET_PATTERN.search(res["stdout_tail"] + res["stderr_tail"]))
    for p_ in (out_p, err_p):
        try:
            os.remove(p_)
        except OSError:
            pass
    return res


def collect_problems(node, acc: set) -> None:
    if isinstance(node, dict):
        for p in node.get("problems") or []:
            acc.add(str(p)[:300])
        for v in node.values():
            collect_problems(v, acc)
    elif isinstance(node, list):
        for v in node:
            collect_problems(v, acc)


def tree_versions(repo_dir: str) -> dict:
    try:
        lock = json.load(open(os.path.join(repo_dir, "package-lock.json")))
    except Exception:  # noqa: BLE001
        return {}
    return {k: v["version"] for k, v in (lock.get("packages") or {}).items() if k and "version" in v}


def main() -> int:
    refuse_if_not_worker()
    spec = json.loads(os.environ["PDR_SPEC"])
    arm, T, tb = spec["arm"], spec["timeouts"], spec.get("tail_bytes", 4000)
    work = "/work/repo"
    os.makedirs("/work/home", exist_ok=True)
    shutil.copytree("/input/snapshot", work, symlinks=True)
    env = dict(os.environ, HOME="/work/home", CI="true", HUSKY="0", npm_config_update_notifier="false",
               npm_config_fund="false", npm_config_loglevel="warn")
    stages: dict = {}

    def go(name, cmd, timeout, shell=False, tail_override=None):
        stages[name] = run_stage(cmd, work, timeout, env, tail_override or tb, shell=shell)
        return stages[name]

    def failed(s):
        return s["timed_out"] or s["oom"] or s["exit_code"] != 0

    result = {"runner_version": RUNNER_VERSION, "arm": arm, "stages": stages, "tree_versions": {}}
    ver = lambda c: subprocess.run(c, capture_output=True, text=True).stdout.strip()  # noqa: E731
    result["tool_versions"] = {"node": ver(["node", "--version"]), "npm": ver(["npm", "--version"])}

    try:
        if arm == "pdr":
            sys.path.insert(0, "/opt/pdr")
            from pdr.sandbox import patch_package_json_for_candidate
            pj_path = os.path.join(work, "package.json")
            pkg = json.load(open(pj_path))
            e = spec["experiment"]
            json.dump(patch_package_json_for_candidate(pkg, e["dep_name"], e["candidate_version"]), open(pj_path, "w"))
            if failed(go("resolve", ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"], T["resolve"])):
                return emit(result)
        if failed(go("install", ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], T["install"])):
            return emit(result)
        result["tree_versions"] = tree_versions(work)
        go("lifecycle", "npm rebuild && npm run --if-present prepare", T["lifecycle"], shell=True)

        # Peer stage needs the FULL `npm ls` output (large trees exceed the normal tail), so read up to 8 MB
        # here, extract the problem list, then keep only a short excerpt in the record.
        s = go("peer", ["npm", "ls", "--all", "--json"], T["peer"], tail_override=8_000_000)
        problems: set = set()
        try:
            collect_problems(json.loads(s["stdout_tail"]), problems)
            s["json_parse_ok"] = True
        except Exception:  # noqa: BLE001
            s["json_parse_ok"] = False
            t = run_stage(["npm", "ls", "--all"], work, T["peer"], env, 8_000_000)
            problems |= {ln.strip()[:300] for ln in (t["stdout_tail"] + t["stderr_tail"]).splitlines()
                         if re.search(r"invalid|missing|extraneous|UNMET|peer dep", ln, re.I)}
        s["problems"] = sorted(problems)[:300]
        s["stdout_tail"] = s["stdout_tail"][:500]

        a = go("audit", ["npm", "audit", "signatures"], T["audit"])
        j = run_stage(["npm", "audit", "signatures", "--json"], work, T["audit"], env, tb)
        a["json_stdout_tail"], a["json_exit_code"] = j["stdout_tail"], j["exit_code"]

        runs = []
        for _ in range(spec["test_runs"]):
            r = run_stage(spec["test_command"], work, T["test"], env, tb, shell=True)
            runs.append(r)
            if r["timed_out"] or r["oom"]:
                break
        stages["test"] = {"ran": True, "test_command": spec["test_command"], "runs": runs}
    except Exception as e:  # noqa: BLE001 -- infrastructure error: record, never crash silently
        result["runner_error"] = f"{type(e).__name__}: {e}"
    return emit(result)


def emit(result: dict) -> int:
    print("PDR_RESULT_JSON:" + json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
