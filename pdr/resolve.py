"""
pdr.resolve
============
Turns a real `package-lock.json` (lockfile v2/v3) into a flat list of
RESOLVED EDGES: (parent, dep_name, declared_range, resolved_version, resolved_path).

This is the "resolved" layer at the bottom of the operational ladder in
README.md. Every downstream construct (OPG, semantic recovery, resolution-
preserving recovery) is computed on top of these edges, so correctness here
matters more than anywhere else in the pipeline.

Node module resolution order (Kill Test 11 / definitional honesty):
  For a package installed at path P = "node_modules/A/node_modules/B",
  looking up a bare dependency name "C" declared in B's own package.json,
  Node/npm search order is:
      node_modules/A/node_modules/B/node_modules/C
      node_modules/A/node_modules/C
      node_modules/C                      (root)
  We reproduce that search order exactly (`_search_chain`) instead of
  assuming every dependency hoists to the root, which would silently
  mis-resolve edges in any tree with real version conflicts.

KNOWN LIMITATION (declared, not hidden): this module only sees what a single
lockfile records. It cannot see git/file/link dependencies' internal deps,
and it does not attempt to reconstruct *why* npm chose a particular resolved
version among conflicting requesters -- it only records what npm already
decided. That is intentional: RESOLVE answers "what is resolved", not
"why". The "why" (resolution-preserving recovery) is handled in pdr/policy.py
using this module's output plus semver_helper.js.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Edge:
    repo: str
    parent_path: str          # lockfile "packages" key of the requester, "" = root
    parent_name: str
    dep_name: str
    declared_range: str
    dep_kind: str              # "dependencies" | "devDependencies" | "peerDependencies" | "optionalDependencies"
    resolved_path: Optional[str]     # lockfile key of the resolved target, or None if unresolved
    resolved_version: Optional[str]  # version string, or None if unresolved (e.g. link:/git/file dep, or missing)
    resolved_kind: Optional[str]     # "registry" | "link" | "git" | "file" | "workspace" | "missing"
    is_dev: bool
    is_optional: bool
    is_peer: bool
    depth: int                 # number of node_modules nesting levels of the PARENT (0 = root)


def _pkg_name_from_path(path: str, entry: Optional[dict] = None) -> str:
    """Derive a bare package name from a lockfile 'packages' key. Prefers the
    entry's own declared 'name' (present on workspace-root entries such as
    "docs" -> name "@npmcli/docs", where the path itself is not the name),
    falling back to the path's last node_modules segment."""
    if entry and entry.get("name"):
        return entry["name"]
    if path == "" or path is None:
        return "<root>"
    if "node_modules/" not in path:
        # bare workspace-root path with no declared "name" field (rare) --
        # use the path itself, e.g. "packages/foo".
        return path
    idx = path.rfind("node_modules/")
    return path[idx + len("node_modules/"):]


def _workspace_roots(packages: Dict[str, dict]) -> List[str]:
    """npm workspaces are recorded as extra top-level entries keyed by their
    on-disk path (e.g. "docs", "workspaces/arborist") rather than a
    "node_modules/..." key. Detected as: not "", no "node_modules/" segment
    anywhere in the key. Sorted longest-first so a nested-looking workspace
    path is matched by its most specific root."""
    roots = [k for k in packages if k != "" and "node_modules/" not in k]
    return sorted(roots, key=len, reverse=True)


def _decompose(path: str, workspace_roots: List[str]) -> tuple:
    """Split a 'packages' key into (base, segments):
    ""                                          -> ("", [])
    "node_modules/a"                             -> ("", ["a"])
    "node_modules/a/node_modules/@scope/b"       -> ("", ["a", "@scope/b"])
    "docs"                                       -> ("docs", [])
    "docs/node_modules/entities"                 -> ("docs", ["entities"])
    "workspaces/arborist/node_modules/x/node_modules/y" -> ("workspaces/arborist", ["x","y"])
    """
    if path == "":
        return "", []
    if path.startswith("node_modules/"):
        rest = path[len("node_modules/"):]
        return "", rest.split("/node_modules/")
    for root in workspace_roots:
        if path == root:
            return root, []
        if path.startswith(root + "/node_modules/"):
            rest = path[len(root) + len("/node_modules/"):]
            return root, rest.split("/node_modules/")
    # Shouldn't happen if workspace_roots was computed from the same
    # packages dict, but degrade gracefully rather than crash the run.
    return path, []


def _segments(path: str, workspace_roots: Optional[List[str]] = None) -> List[str]:
    """Nesting depth helper used for the 'depth' field. workspace_roots may
    be omitted by callers that only care about true-root-relative paths."""
    _, segs = _decompose(path, workspace_roots or [])
    return segs


def _search_chain(parent_path: str, dep_name: str, workspace_roots: List[str]) -> List[str]:
    """Ordered list of lockfile keys to probe, matching real Node resolution
    order: parent's own node_modules first, then each ancestor's node_modules
    within the same workspace (or root), and -- if the parent lives inside a
    workspace -- finally the true repo-root node_modules (npm workspaces
    hoist everything there by default; a workspace-local node_modules entry
    only exists in the lockfile for genuine local overrides, which the
    earlier, more specific candidates already cover).
    """
    base, segs = _decompose(parent_path, workspace_roots)
    chain = []
    prefix_root = f"{base}/" if base else ""
    for i in range(len(segs), -1, -1):
        seg_prefix = "/node_modules/".join(segs[:i])
        nm = f"{prefix_root}node_modules/{seg_prefix}/node_modules/" if seg_prefix else f"{prefix_root}node_modules/"
        chain.append(nm + dep_name)
    if base:
        chain.append(f"node_modules/{dep_name}")
    return chain


_DEP_KIND_FIELDS = ["dependencies", "peerDependencies", "optionalDependencies"]
# devDependencies are only declared at the ROOT in npm lockfiles (nested
# packages' own devDependencies are never installed), so we read them once
# from the root entry only -- see parse_lockfile().


def parse_lockfile(repo: str, lock: dict) -> List[Edge]:
    packages: Dict[str, dict] = lock.get("packages", {})
    if not packages:
        raise ValueError(f"[{repo}] lockfile has no 'packages' section "
                          f"(lockfileVersion={lock.get('lockfileVersion')}); "
                          f"v1 lockfiles are out of scope for this parser.")

    edges: List[Edge] = []
    workspace_roots = _workspace_roots(packages)

    for parent_path, entry in packages.items():
        parent_name = _pkg_name_from_path(parent_path, entry)
        depth = len(_segments(parent_path, workspace_roots))

        kind_fields = list(_DEP_KIND_FIELDS)
        # devDependencies are installed for the root AND for each workspace
        # root (npm workspaces treat every workspace as a first-class
        # package with its own devDependencies), but never for a plain
        # nested node_modules entry.
        if parent_path == "" or parent_path in workspace_roots:
            kind_fields = ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]

        for kind in kind_fields:
            deps = entry.get(kind) or {}
            for dep_name, declared_range in deps.items():
                resolved_path = None
                resolved_version = None
                resolved_kind = "missing"

                for candidate in _search_chain(parent_path, dep_name, workspace_roots):
                    if candidate in packages:
                        resolved_path = candidate
                        target = packages[candidate]
                        if "link" in target and target.get("link"):
                            resolved_kind = "link"
                        elif "resolved" in target and str(target["resolved"]).startswith("git"):
                            resolved_kind = "git"
                        elif "version" in target:
                            resolved_version = target["version"]
                            resolved_kind = "registry"
                        else:
                            resolved_kind = "file"
                        break

                edges.append(Edge(
                    repo=repo,
                    parent_path=parent_path,
                    parent_name=parent_name,
                    dep_name=dep_name,
                    declared_range=declared_range,
                    dep_kind=kind,
                    resolved_path=resolved_path,
                    resolved_version=resolved_version,
                    resolved_kind=resolved_kind,
                    is_dev=(kind == "devDependencies"),
                    is_optional=(kind == "optionalDependencies") or bool(entry.get("optional")),
                    is_peer=(kind == "peerDependencies"),
                    depth=depth,
                ))

    return edges


def load_and_parse(repo: str, path: str) -> List[Edge]:
    with open(path, "r", encoding="utf-8") as f:
        lock = json.load(f)
    if lock.get("lockfileVersion", 0) < 2:
        raise ValueError(f"[{repo}] lockfileVersion {lock.get('lockfileVersion')} "
                          f"(v1) not supported -- v1 lockfiles lack the flat "
                          f"'packages' map this parser relies on.")
    return parse_lockfile(repo, lock)
