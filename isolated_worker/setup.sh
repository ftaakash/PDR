#!/usr/bin/env bash
# isolated_worker/setup.sh -- builds the Phase 3 isolation infrastructure.
# Every step fails loudly (set -euo pipefail) rather than continuing past a
# problem; there is no "skip and hope" path anywhere in this script.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[setup] checking docker daemon..."
docker version >/dev/null || { echo "REFUSING: docker not available"; exit 1; }

if grep -q "UNVERIFIED" isolated_worker/Dockerfile; then
  echo "REFUSING: isolated_worker/Dockerfile still has the placeholder base-image digest."
  echo "  This session had no reachable Docker registry to resolve a real digest against."
  echo "  Before building for real: pull node:20-bookworm-slim, get its digest with"
  echo "  'docker inspect --format={{index .RepoDigests 0}} node:20-bookworm-slim', and"
  echo "  replace the FROM line. This check exists so a real build can never proceed"
  echo "  against a never-verified base image by accident."
  exit 1
fi

echo "[setup] creating internal-only network (no route to the outside world except via the proxy)..."
docker network inspect pdr-internal >/dev/null 2>&1 || \
  docker network create --internal pdr-internal

echo "[setup] starting the allowlisting proxy (registry.npmjs.org + Sigstore TUF CDN only)..."
docker rm -f pdr-proxy >/dev/null 2>&1 || true
# The proxy container is the ONLY thing on both the internal network and a
# normal (outside-reaching) network -- that dual attachment is what lets
# workers reach the real internet, filtered, without being on it directly.
docker run -d --name pdr-proxy \
  --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$(pwd)/isolated_worker/proxy_allowlist.py:/addon.py:ro" \
  mitmproxy/mitmproxy:12.2.3@sha256:00b77b5d8804c8ad18cb6caefbf9d5849e895e8986c5ce011f4ae30f4385962f \
  mitmdump -s /addon.py --mode regular --listen-port 8888 --set block_global=false
docker network connect pdr-internal pdr-proxy
docker network connect bridge pdr-proxy 2>/dev/null || true   # best-effort; may already be attached at creation

echo "[setup] building the worker image..."
docker build -t pdr-worker:phase3-v1 -f isolated_worker/Dockerfile .

echo "[setup] done. Next: python3 isolated_worker/orchestrate.py --selftest"
