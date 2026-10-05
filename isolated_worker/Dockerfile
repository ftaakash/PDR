# isolated_worker/Dockerfile
#
# Pinned by digest, not tag: "node:20-bookworm-slim" can be repointed by
# upstream; the digest cannot. Update this pin deliberately (and re-run
# `orchestrate.py --selftest`, which is gated on image ID) rather than
# floating to "latest 20-bookworm-slim" on every rebuild.
#
# Digest resolved 2026-10-05 from registry-1.docker.io (manifest-list digest
# of library/node:20-bookworm-slim), approved by the project owner (TASKS.md T5).
# isolated_worker/setup.sh still refuses to build if a placeholder returns.
FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0

# Pin npm to the exact version recorded in data_manifest/tool_lock.json so a
# worker rebuild months from now can't silently change dependency
# resolution or provenance-verification behavior underneath already-frozen
# results. If tool_lock.json's npm_version changes, this line must change
# with it, on purpose, in the same commit.
RUN npm install -g npm@10.9.7 && npm cache clean --force

# curl: used only by orchestrate.py's --selftest to prove network isolation
# actually works, from inside a throwaway container of this same image --
# not used by runner.py during a real experiment.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# Non-root, fixed UID/GID matching orchestrate.py's --user 10001:10001 --
# --read-only plus a non-root user means even a fully compromised lifecycle
# script cannot write outside the tmpfs mounts orchestrate.py provides.
RUN groupadd -g 10001 pdr && useradd -u 10001 -g pdr -M -s /usr/sbin/nologin pdr

# The host-execution guard in runner.py checks for this file. Its presence
# is necessary but not sufficient for safety -- the container boundary
# (read-only rootfs, dropped capabilities, no host mounts but the one
# read-only snapshot, internal-only network) is the actual isolation;
# this marker only stops someone from running runner.py directly on a dev
# machine by mistake.
RUN mkdir -p /opt/pdr-worker-image-marker && touch /opt/pdr-worker-image-marker/marker
ENV PDR_ISOLATED_WORKER=1

# pdr/sandbox.py (patch_package_json_for_candidate) and pdr/phase3.py are
# baked in read-only, matching the exact code versions tested in
# tests/test_layer1_patch_logic.py and tests/test_phase3_logic.py on the
# host -- not re-fetched or re-written at container start.
COPY pdr/__init__.py pdr/sandbox.py pdr/phase3.py /opt/pdr/pdr/

COPY isolated_worker/runner.py /opt/pdr/runner.py
RUN chmod 555 /opt/pdr/runner.py

WORKDIR /work
ENTRYPOINT ["python3", "/opt/pdr/runner.py"]
