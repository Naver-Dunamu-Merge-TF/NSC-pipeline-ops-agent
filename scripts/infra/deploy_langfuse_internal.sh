#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${LANGFUSE_NAMESPACE:-default}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/k8s/langfuse"

# Internal deployment image default; override LANGFUSE_IMAGE for your ACR path/tag.
export LANGFUSE_IMAGE="${LANGFUSE_IMAGE:-your-acr-name.azurecr.io/langfuse:latest}"
export LANGFUSE_SECRET_NAME="${LANGFUSE_SECRET_NAME:-langfuse-secrets}"
LANGFUSE_ROLLOUT_TIMEOUT="${LANGFUSE_ROLLOUT_TIMEOUT:-120s}"

command -v kubectl >/dev/null 2>&1 || {
  echo "kubectl is required" >&2
  exit 1
}

command -v envsubst >/dev/null 2>&1 || {
  echo "envsubst is required" >&2
  exit 1
}

echo "Applying internal LangFuse Service (${NAMESPACE})"
kubectl apply -n "${NAMESPACE}" -f "${MANIFEST_DIR}/service.yaml"

echo "Applying internal LangFuse Deployment (${NAMESPACE})"
envsubst < "${MANIFEST_DIR}/deployment.yaml" | kubectl apply -n "${NAMESPACE}" -f -

echo "Waiting for rollout"
kubectl rollout status deployment/langfuse -n "${NAMESPACE}" --timeout="${LANGFUSE_ROLLOUT_TIMEOUT}"

echo "Done. Internal service: langfuse-internal (ClusterIP)"
