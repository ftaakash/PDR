#!/usr/bin/env python3
"""
isolated_worker/orchestrate.py -- host-side orchestrator for Phase 3 Layer 3.

SAFETY PROPERTIES (each enforced mechanically; see tests/test_isolated_worker.py):
  1. This file never runs npm, node, or any repository code. Its only
     subprocess executable is `docker`. Everything that executes third-party
     code happens inside a container built from isolated_worker/Dockerfile.
  2. Every `docker run` command is checked by assert_command_safe() BEFORE it
     is executed: required hardening flags must be present, forbidden flags
     (privileged, host network/pid/ipc, docker socket, extra capabilities,
     devices, writable host mounts) must be absent, and the only bind mount
     allowed is the pinned repo snapshot, read-only.
  3. There is NO fallback that runs the work on the host. If docker, the
     internal network, the proxy, or a passing network self-test for the
     current image is missing, the run stops (nothing is degraded silently).
  4. The cohort cannot be edited after the fact: the manifest's SHA-256 must
     match the committed hash file.

Usage:
  orchestrate.py --dry-run                 print every docker command, run nothing
  orchestrate.py --selftest                verify network isolation for the current image
  orchestrate.py [--limit N] [--repo R]    run the micro-pilot (resumable)

STATUS: written and unit-tested for command construction/safety, but NOT yet
executed against a live Docker daemon (none exists in the session that wrote
it). First real execution should be --selftest, then a --limit 2 trial.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr import phase3 as p3  # noqa: E402

MANIFEST = "configs/experiments/phase3_micropilot_manifest.json"
MANIFEST_HASH = "configs/experiments/phase3_micropilot_manifest.sha256"
PINS = "configs/experiments/phase3_micropilot_pins.json"
SNAP_DIR = "results/raw/phase3_snapshots"
OUT = "results/processed/phase3_micropilot_results.jsonl"
SELFTEST_OUT = "results/processed/phase3_selftest.json"

CFG = {
    "image": "pdr-worker:phase3-v1",
    "network": "pdr-internal",        # created with --internal: no route except via the proxy
    "proxy_container": "pdr-proxy",
    "proxy_url": "http://pdr-proxy:8888",
    "memory": "4g", "cpus": "2", "pids": "512",
    "tmpfs_work": "/work:rw,exec,nosuid,size=3g,uid=10001,gid=10001",   # exec needed: node_modules/.bin, native builds
    "tmpfs_tmp": "/tmp:rw,noexec,nosuid,size=512m",
    "user": "10001:10001",
    "timeouts": {"resolve": 300, "install": 600, "lifecycle": 600, "peer": 120, "audit": 180, "test": 900},
    "b0_test_runs": 2, "pdr_test_runs": 1,
    "container_wall_s": 3600,         # hard ceiling enforced by the orchestrator, independent of in-container timeouts
}

REQUIRED_TOKENS = ["--cap-drop=ALL", "--security-opt=no-new-privileges", "--read-only", "--pids-limit",
                   "--memory", "--memory-swap", "--cpus", "--user", "--pull=never", "--label", "--name"]
FORBIDDEN_SUBSTRINGS = ["--privileged", "--network=host", "--net=host", "--pid=host", "--ipc=host",
                        "--userns=host", "--cap-add", "--device", "docker.sock", "--security-opt=seccomp=unconfined",
                        "--security-opt=apparmor=unconfined", "--volumes-from", "--mount=type=volume"]


# ------------------------------------------------------------------- pure logic

def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_manifest(manifest: dict, expected_hash: str) -> None:
    got = canonical_sha256(manifest)
    if got != expected_hash.strip():
        raise SystemExit(f"REFUSING: manifest hash {got[:12]} != committed {expected_hash.strip()[:12]} "
                         "(the frozen cohort was modified after freezing)")


def build_docker_run_command(name: str, snapshot_dir: str, spec: dict, cfg: dict = CFG) -> list:
    if not os.path.isabs(snapshot_dir):
        snapshot_dir = os.path.abspath(snapshot_dir)
    proxy = cfg["proxy_url"]
    cmd = [
        "docker", "run", f"--name={name}", "--label", "pdr-worker=1", "--pull=never",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--read-only",
        f"--tmpfs={cfg['tmpfs_work']}", f"--tmpfs={cfg['tmpfs_tmp']}",
        "--pids-limit", cfg["pids"], "--memory", cfg["memory"], "--memory-swap", cfg["memory"], "--cpus", cfg["cpus"],
        "--ulimit", "nofile=4096:4096", "--user", cfg["user"],
        f"--network={cfg['network']}",
        "--mount", f"type=bind,source={snapshot_dir},target=/input/snapshot,readonly",
        "-e", f"HTTP_PROXY={proxy}", "-e", f"HTTPS_PROXY={proxy}", "-e", f"http_proxy={proxy}", "-e", f"https_proxy={proxy}",
        "-e", f"npm_config_proxy={proxy}", "-e", f"npm_config_https_proxy={proxy}",
        "-e", "NO_PROXY=", "-e", "no_proxy=",
        "-e", "PDR_SPEC=" + json.dumps(spec, separators=(",", ":")),
        cfg["image"],
    ]
    return cmd


def assert_no_forbidden(cmd: list) -> None:
    flat = " ".join(cmd)
    for bad in FORBIDDEN_SUBSTRINGS:
        if bad in flat:
            raise AssertionError(f"unsafe docker command: forbidden flag present: {bad}")
    net = next((a for a in cmd if a.startswith("--network=")), None)
    if net != f"--network={CFG['network']}":
        raise AssertionError(f"unsafe docker command: must be on the internal network only, got {net}")


def assert_command_safe(cmd: list) -> None:
    """Gate for every job container. Required flags must match EXACTLY (or as `flag=value`);
    prefix matching would let e.g. --memory-swap satisfy --memory."""
    for tok in REQUIRED_TOKENS:
        if not any(a == tok or a.startswith(tok + "=") for a in cmd):
            raise AssertionError(f"unsafe docker command: required flag missing: {tok}")
    assert_no_forbidden(cmd)
    mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a in ("--mount", "-v", "--volume")]
    if len(mounts) != 1:
        raise AssertionError(f"unsafe docker command: expected exactly 1 mount, found {len(mounts)}")
    m = mounts[0]
    if not (m.startswith("type=bind,") and m.endswith(",readonly") and "target=/input/snapshot" in m):
        raise AssertionError(f"unsafe docker command: mount must be the read-only snapshot only: {m}")
    for e in [cmd[i + 1] for i, a in enumerate(cmd) if a == "-e"]:
        k = e.split("=", 1)[0].upper()
        if any(w in k for w in ("TOKEN", "SECRET", "PASSWORD", "KEY", "CREDENTIAL", "NPM_AUTH")):
            raise AssertionError(f"unsafe docker command: credential-like env var: {k}")


_DENIED = re.compile(r'refused on filtered domain "?([^"\s]+)"?', re.I)


def parse_denied_hosts(proxy_log: str) -> list:
    return sorted({m.group(1).lower() for m in _DENIED.finditer(proxy_log or "")})


def evaluate_selftest(r: dict) -> dict:
    """Network isolation is VERIFIED per image, not assumed. Expectations:
       allowed hosts reachable through the proxy; a non-allowlisted host denied
       through the proxy; and a direct (proxy-bypassing) connection fails."""
    checks = {
        "registry_via_proxy_ok": r.get("registry_via_proxy") == "200",
        "tuf_cdn_via_proxy_ok": r.get("tuf_via_proxy") in ("200", "404"),   # any HTTP answer proves reachability
        "denied_host_blocked": r.get("denied_via_proxy") not in ("200", "301", "302"),
        "direct_connection_blocked": r.get("direct_registry") in ("000", "", None),
        # validates the assumption parse_denied_hosts() relies on (proxy log wording) on first real run
        "denied_host_is_logged": "example.com" in (r.get("denied_hosts_seen_in_proxy_log") or []),
    }
    return {"checks": checks, "passed": all(checks.values())}


# ---------------------------------------------------------------- docker plumbing

def sh(cmd, timeout=60):
    assert cmd[0] == "docker", "orchestrator may only invoke docker"
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        # docker binary absent: behave like a failed command so preflight()
        # prints its designed REFUSING message instead of a raw traceback.
        return subprocess.CompletedProcess(cmd, 127, "", "docker: command not found")


def preflight() -> str:
    """Refuse unless the isolation prerequisites exist; return the image ID."""
    if sh(["docker", "version"]).returncode != 0:
        raise SystemExit("REFUSING: docker daemon not available. Layer 3 never falls back to running on the host.")
    n = sh(["docker", "network", "inspect", CFG["network"], "--format", "{{.Internal}}"])
    if n.returncode != 0 or n.stdout.strip() != "true":
        raise SystemExit(f"REFUSING: docker network '{CFG['network']}' missing or not --internal (run isolated_worker/setup.sh)")
    if sh(["docker", "inspect", "-f", "{{.State.Running}}", CFG["proxy_container"]]).stdout.strip() != "true":
        raise SystemExit(f"REFUSING: proxy container '{CFG['proxy_container']}' is not running")
    i = sh(["docker", "image", "inspect", CFG["image"], "--format", "{{.Id}}"])
    if i.returncode != 0:
        raise SystemExit(f"REFUSING: image {CFG['image']} not built (run isolated_worker/setup.sh)")
    return i.stdout.strip()


def selftest_gate(image_id: str) -> None:
    try:
        st = json.load(open(SELFTEST_OUT))
    except OSError:
        raise SystemExit("REFUSING: no network self-test on record. Run: orchestrate.py --selftest")
    if not st.get("passed") or st.get("image_id") != image_id:
        raise SystemExit("REFUSING: network self-test missing/failed for the CURRENT image id; re-run --selftest")


def run_selftest(image_id: str) -> int:
    def curl(args):
        name = f"pdr-selftest-{uuid.uuid4().hex[:8]}"
        cmd = ["docker", "run", f"--name={name}", "--label", "pdr-worker=1", "--pull=never", "--cap-drop=ALL",
               "--security-opt=no-new-privileges", "--read-only", "--pids-limit", "64", "--memory", "256m",
               f"--network={CFG['network']}", "--entrypoint", "curl", CFG["image"],
               "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "20", *args]
        assert_no_forbidden(cmd)
        try:
            r = sh(cmd, timeout=60)
            return r.stdout.strip()
        finally:
            sh(["docker", "rm", "-f", name])
    P = ["--proxy", CFG["proxy_url"]]
    res = {"registry_via_proxy": curl(P + ["https://registry.npmjs.org/"]),
           "tuf_via_proxy": curl(P + ["https://tuf-repo-cdn.sigstore.dev/timestamp.json"]),
           "denied_via_proxy": curl(P + ["https://example.com/"]),
           "direct_registry": curl(["--noproxy", "*", "https://registry.npmjs.org/"])}
    logs = sh(["docker", "logs", CFG["proxy_container"]])
    res["denied_hosts_seen_in_proxy_log"] = parse_denied_hosts(logs.stdout + logs.stderr)
    ev = evaluate_selftest(res)
    out = {"image_id": image_id, "raw": res, **ev}
    json.dump(out, open(SELFTEST_OUT, "w"), indent=2)
    print(json.dumps(out, indent=2))
    return 0 if ev["passed"] else 1


def run_arm(arm: str, exp: dict, snapshot: str, dry: bool) -> dict:
    spec = {"arm": arm, "experiment": {"dep_name": exp["dep_name"], "candidate_version": exp["candidate_version"]},
            "test_command": exp["test_command"], "timeouts": CFG["timeouts"], "tail_bytes": 4000,
            "test_runs": CFG["b0_test_runs"] if arm == "b0" else CFG["pdr_test_runs"]}
    name = f"pdr-{arm}-{uuid.uuid4().hex[:10]}"
    cmd = build_docker_run_command(name, snapshot, spec)
    assert_command_safe(cmd)
    if dry:
        shown = [(a[:60] + "...") if a.startswith("PDR_SPEC=") else a for a in cmd]
        print("DRY-RUN:", " ".join(shown))
        return {}
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    t0, timed_out, out = time.time(), False, ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=CFG["container_wall_s"])
        out = r.stdout
    except subprocess.TimeoutExpired:
        timed_out = True
        sh(["docker", "kill", name])
    try:
        oom = sh(["docker", "inspect", "-f", "{{.State.OOMKilled}}", name]).stdout.strip() == "true"
        lg = sh(["docker", "logs", "--since", since, CFG["proxy_container"]])
        proxy_log = lg.stdout + lg.stderr
    finally:
        sh(["docker", "rm", "-f", name])          # disposable: every worker is destroyed after its single job
    line = next((ln for ln in reversed(out.splitlines()) if ln.startswith("PDR_RESULT_JSON:")), None)
    if line is None:
        return {"arm": arm, "stages": {}, "tree_versions": {}, "orchestrator_note": "no result line",
                "container_timed_out": timed_out, "container_oom": oom, "elapsed_s": round(time.time() - t0, 1)}
    res = json.loads(line[len("PDR_RESULT_JSON:"):])
    res.update(container_timed_out=timed_out, container_oom=oom, denied_hosts=parse_denied_hosts(proxy_log),
               elapsed_s=round(time.time() - t0, 1))
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--repo")
    args = ap.parse_args()

    manifest = json.load(open(MANIFEST))
    verify_manifest(manifest, open(MANIFEST_HASH).read())
    pins = json.load(open(PINS))
    exps = [e for e in manifest["selected"] if not args.repo or e["repo"] == args.repo]
    for e in exps:
        if pins.get(e["repo"], {}).get("status") != "PINNED":
            raise SystemExit(f"REFUSING: {e['repo']} has no pinned snapshot commit")

    image_id = "DRY-RUN-NO-IMAGE"
    if not args.dry_run:
        image_id = preflight()
        if args.selftest:
            return run_selftest(image_id)
        selftest_gate(image_id)
    elif args.selftest:
        raise SystemExit("--selftest needs a live docker daemon; it cannot be a dry run")

    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)["edge_id"] for l in open(OUT) if l.strip()}
    b0_cache: dict = {}
    n = 0
    for e in exps:
        eid = e["experiment_id"]
        if eid in done:
            continue
        if args.limit and n >= args.limit:
            break
        snap = os.path.join(SNAP_DIR, e["repo"].replace("/", "_"))
        if not args.dry_run and not os.path.isdir(snap):
            raise SystemExit(f"REFUSING: snapshot missing: {snap} (run scripts/phase3_pin_snapshots.py --materialize)")
        if e["repo"] not in b0_cache:
            b0_cache[e["repo"]] = run_arm("b0", e, snap, args.dry_run)
        pdr_arm = run_arm("pdr", e, snap, args.dry_run)
        n += 1
        if args.dry_run:
            continue
        rec = {"schema_version": p3.SCHEMA_VERSION, "edge_id": eid, "edge_ids": e["edge_ids"], "repo": e["repo"],
               "dep_name": e["dep_name"], "resolved_version": e["resolved_version"],
               "candidate_version": e["candidate_version"], "size_bucket": e["size_bucket"],
               "patch_mode": e["patch_mode"], "pinned_sha": pins[e["repo"]]["sha"], "image_id": image_id,
               "manifest_sha256": open(MANIFEST_HASH).read().strip(), "b0": b0_cache[e["repo"]], "pdr": pdr_arm}
        rec["classification"] = p3.classify_pair(rec["b0"], rec["pdr"])
        problems = p3.validate_record(rec)
        if problems:
            rec["schema_problems"] = problems
        with open(OUT, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[phase3] {eid}: {rec['classification']['outcome']}")
    print(f"[phase3] {'dry-run built' if args.dry_run else 'completed'} {n} experiments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
