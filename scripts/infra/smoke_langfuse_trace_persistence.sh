#!/usr/bin/env bash
set -euo pipefail

LANGFUSE_NAMESPACE="${LANGFUSE_NAMESPACE:-default}"
LANGFUSE_SERVICE_NAME="${LANGFUSE_SERVICE_NAME:-langfuse-internal}"
LANGFUSE_DEPLOYMENT_NAME="${LANGFUSE_DEPLOYMENT_NAME:-langfuse}"
LANGFUSE_SECRET_NAME="${LANGFUSE_SECRET_NAME:-langfuse-secrets}"
LANGFUSE_LOCAL_PORT="${LANGFUSE_LOCAL_PORT:-3000}"
LANGFUSE_REMOTE_PORT="${LANGFUSE_REMOTE_PORT:-3000}"
LANGFUSE_SMOKE_TIMEOUT_SECONDS="${LANGFUSE_SMOKE_TIMEOUT_SECONDS:-10}"
PORT_FORWARD_READY_TIMEOUT_SECONDS="${PORT_FORWARD_READY_TIMEOUT_SECONDS:-20}"
PORT_FORWARD_READY_POLL_SECONDS="${PORT_FORWARD_READY_POLL_SECONDS:-1}"
LANGFUSE_ROLLOUT_TIMEOUT="${LANGFUSE_ROLLOUT_TIMEOUT:-180s}"
LANGFUSE_TRACE_FETCH_RETRIES="${LANGFUSE_TRACE_FETCH_RETRIES:-5}"
LANGFUSE_TRACE_FETCH_RETRY_INTERVAL_SECONDS="${LANGFUSE_TRACE_FETCH_RETRY_INTERVAL_SECONDS:-1}"
LANGFUSE_TRACE_ID="${LANGFUSE_TRACE_ID:-}"
LANGFUSE_TRACE_SMOKE_ARTIFACT_FILE="${LANGFUSE_TRACE_SMOKE_ARTIFACT_FILE:-}"

command -v kubectl >/dev/null 2>&1 || {
  echo "kubectl is required" >&2
  exit 1
}

command -v curl >/dev/null 2>&1 || {
  echo "curl is required" >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required" >&2
  exit 1
}

TMP_DIR="$(mktemp -d)"
PORT_FORWARD_LOG="${TMP_DIR}/port-forward.log"
INGEST_BODY_FILE="${TMP_DIR}/ingest.body"
FETCH_BEFORE_BODY_FILE="${TMP_DIR}/fetch-before.body"
FETCH_AFTER_BODY_FILE="${TMP_DIR}/fetch-after.body"
INGEST_PAYLOAD_FILE="${TMP_DIR}/ingest-payload.json"
PORT_FORWARD_PID=""

cleanup() {
  if [ -n "${PORT_FORWARD_PID}" ] && kill -0 "${PORT_FORWARD_PID}" >/dev/null 2>&1; then
    kill "${PORT_FORWARD_PID}" >/dev/null 2>&1 || true
    wait "${PORT_FORWARD_PID}" >/dev/null 2>&1 || true
  fi
  rm -rf "${TMP_DIR}"
}

trap cleanup EXIT

decode_b64() {
  python3 - "$1" <<'PY'
import base64
import sys

value = sys.argv[1]
if not value:
    print("")
else:
    print(base64.b64decode(value).decode("utf-8"))
PY
}

body_has_trace_id() {
  python3 - "$1" "$2" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
trace_id = sys.argv[2]

if not path.exists():
    raise SystemExit(1)

text = path.read_text(encoding="utf-8", errors="replace")
if trace_id in text:
    raise SystemExit(0)

try:
    payload = json.loads(text)
except json.JSONDecodeError:
    raise SystemExit(1)

if isinstance(payload, dict):
    if payload.get("id") == trace_id:
        raise SystemExit(0)
    if payload.get("traceId") == trace_id:
        raise SystemExit(0)

raise SystemExit(1)
PY
}

fetch_trace_with_retry() {
  local out_file="$1"
  local attempt=0
  local code="000"

  while [ "${attempt}" -lt "${LANGFUSE_TRACE_FETCH_RETRIES}" ]; do
    attempt=$((attempt + 1))
    code="$(curl -sS -u "${PUBLIC_KEY}:${SECRET_KEY}" -o "${out_file}" -w '%{http_code}' --max-time "${LANGFUSE_SMOKE_TIMEOUT_SECONDS}" "${FETCH_URL}" || true)"

    if [ "${code}" = "200" ] && body_has_trace_id "${out_file}" "${LANGFUSE_TRACE_ID}"; then
      printf '%s' "${code}"
      return 0
    fi

    if [ "${attempt}" -lt "${LANGFUSE_TRACE_FETCH_RETRIES}" ]; then
      sleep "${LANGFUSE_TRACE_FETCH_RETRY_INTERVAL_SECONDS}"
    fi
  done

  printf '%s' "${code:-000}"
  return 1
}

emit_artifact() {
  local result="$1"
  local stage="$2"
  local ingest_code="$3"
  local fetch_before_code="$4"
  local fetch_after_code="$5"
  local restart_performed="$6"
  local artifact_line
  local utc_ts

  utc_ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

  artifact_line="$(python3 - "${utc_ts}" "${LANGFUSE_NAMESPACE}" "${LANGFUSE_SERVICE_NAME}" "${LANGFUSE_DEPLOYMENT_NAME}" "${LANGFUSE_TRACE_ID}" "${result}" "${stage}" "${ingest_code}" "${fetch_before_code}" "${fetch_after_code}" "${restart_performed}" <<'PY'
import json
import sys

def as_code(raw: str):
    return int(raw) if raw.isdigit() else raw

data = {
    "event": "langfuse_trace_persistence_smoke",
    "utc": sys.argv[1],
    "namespace": sys.argv[2],
    "service": sys.argv[3],
    "deployment": sys.argv[4],
    "trace_id": sys.argv[5],
    "result": sys.argv[6],
    "stage": sys.argv[7],
    "ingest_http_code": as_code(sys.argv[8]),
    "fetch_before_http_code": as_code(sys.argv[9]),
    "fetch_after_http_code": as_code(sys.argv[10]),
    "restart_performed": sys.argv[11] == "true",
}
print(json.dumps(data, ensure_ascii=True, separators=(",", ":")))
PY
 )"

  if [ -n "${LANGFUSE_TRACE_SMOKE_ARTIFACT_FILE}" ]; then
    printf '%s\n' "${artifact_line}" >> "${LANGFUSE_TRACE_SMOKE_ARTIFACT_FILE}"
  fi

  printf '%s\n' "${artifact_line}"
}

if [ -z "${LANGFUSE_TRACE_ID}" ]; then
  LANGFUSE_TRACE_ID="$(python3 - <<'PY'
import uuid
print(f"trace-dev044-{uuid.uuid4().hex[:12]}")
PY
 )"
fi

PUBLIC_KEY_B64="$(kubectl get secret "${LANGFUSE_SECRET_NAME}" -n "${LANGFUSE_NAMESPACE}" -o "jsonpath={.data['langfuse-public-key']}" 2>/dev/null || true)"
SECRET_KEY_B64="$(kubectl get secret "${LANGFUSE_SECRET_NAME}" -n "${LANGFUSE_NAMESPACE}" -o "jsonpath={.data['langfuse-secret-key']}" 2>/dev/null || true)"

if [ -z "${PUBLIC_KEY_B64}" ] || [ -z "${SECRET_KEY_B64}" ]; then
  emit_artifact "fail" "secret_retrieval" "000" "000" "000" "false"
  echo "FAIL: unable to read langfuse keys from secret ${LANGFUSE_SECRET_NAME}" >&2
  exit 1
fi

PUBLIC_KEY="$(decode_b64 "${PUBLIC_KEY_B64}")"
SECRET_KEY="$(decode_b64 "${SECRET_KEY_B64}")"

if [ -z "${PUBLIC_KEY}" ] || [ -z "${SECRET_KEY}" ]; then
  emit_artifact "fail" "credentials" "000" "000" "000" "false"
  echo "FAIL: missing langfuse public/secret key from secret ${LANGFUSE_SECRET_NAME}" >&2
  exit 1
fi

BASE_URL="http://127.0.0.1:${LANGFUSE_LOCAL_PORT}"
INGEST_URL="${BASE_URL}/api/public/ingestion"
FETCH_URL="${BASE_URL}/api/public/traces/${LANGFUSE_TRACE_ID}"

kubectl port-forward \
  -n "${LANGFUSE_NAMESPACE}" \
  "service/${LANGFUSE_SERVICE_NAME}" \
  "${LANGFUSE_LOCAL_PORT}:${LANGFUSE_REMOTE_PORT}" \
  >"${PORT_FORWARD_LOG}" 2>&1 &
PORT_FORWARD_PID=$!

ready=0
deadline=$((SECONDS + PORT_FORWARD_READY_TIMEOUT_SECONDS))
while [ "${SECONDS}" -lt "${deadline}" ]; do
  if ! kill -0 "${PORT_FORWARD_PID}" >/dev/null 2>&1; then
    break
  fi

  ready_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time "${LANGFUSE_SMOKE_TIMEOUT_SECONDS}" "${BASE_URL}" || true)"
  if [ -n "${ready_code}" ] && [ "${ready_code}" != "000" ]; then
    ready=1
    break
  fi

  sleep "${PORT_FORWARD_READY_POLL_SECONDS}"
done

if [ "${ready}" -ne 1 ]; then
  emit_artifact "fail" "port_forward" "000" "000" "000" "false"
  echo "FAIL: port-forward did not become ready within ${PORT_FORWARD_READY_TIMEOUT_SECONDS}s" >&2
  exit 1
fi

python3 - "${LANGFUSE_TRACE_ID}" >"${INGEST_PAYLOAD_FILE}" <<'PY'
import json
import sys
from datetime import datetime, timezone

trace_id = sys.argv[1]
timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
payload = {
    "batch": [
        {
            "id": f"evt-{trace_id}",
            "type": "trace-create",
            "timestamp": timestamp,
            "body": {
                "id": trace_id,
                "name": "dev044-trace-persistence-smoke",
                "timestamp": timestamp,
            },
        }
    ]
}
print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
PY

ingest_code="$(curl -sS -u "${PUBLIC_KEY}:${SECRET_KEY}" -H 'Content-Type: application/json' -o "${INGEST_BODY_FILE}" -w '%{http_code}' --max-time "${LANGFUSE_SMOKE_TIMEOUT_SECONDS}" -X POST --data-binary "@${INGEST_PAYLOAD_FILE}" "${INGEST_URL}" || true)"

if [ "${ingest_code}" != "200" ] && [ "${ingest_code}" != "201" ] && [ "${ingest_code}" != "202" ]; then
  emit_artifact "fail" "ingest" "${ingest_code:-000}" "000" "000" "false"
  echo "FAIL: trace ingestion failed with HTTP ${ingest_code:-000}" >&2
  exit 1
fi

fetch_before_code="000"
if ! fetch_before_code="$(fetch_trace_with_retry "${FETCH_BEFORE_BODY_FILE}")"; then
  emit_artifact "fail" "fetch_before_restart" "${ingest_code}" "${fetch_before_code:-000}" "000" "false"
  echo "FAIL: trace not retrievable before restart (HTTP ${fetch_before_code:-000})" >&2
  exit 1
fi

if ! kubectl rollout restart "deployment/${LANGFUSE_DEPLOYMENT_NAME}" -n "${LANGFUSE_NAMESPACE}"; then
  emit_artifact "fail" "rollout_restart" "${ingest_code}" "${fetch_before_code}" "000" "false"
  echo "FAIL: rollout restart failed for deployment/${LANGFUSE_DEPLOYMENT_NAME}" >&2
  exit 1
fi

if ! kubectl rollout status "deployment/${LANGFUSE_DEPLOYMENT_NAME}" -n "${LANGFUSE_NAMESPACE}" --timeout "${LANGFUSE_ROLLOUT_TIMEOUT}"; then
  emit_artifact "fail" "rollout_status" "${ingest_code}" "${fetch_before_code}" "000" "true"
  echo "FAIL: rollout status failed for deployment/${LANGFUSE_DEPLOYMENT_NAME}" >&2
  exit 1
fi

fetch_after_code="000"
if ! fetch_after_code="$(fetch_trace_with_retry "${FETCH_AFTER_BODY_FILE}")"; then
  emit_artifact "fail" "fetch_after_restart" "${ingest_code}" "${fetch_before_code}" "${fetch_after_code:-000}" "true"
  echo "FAIL: trace not retrievable after restart (HTTP ${fetch_after_code:-000})" >&2
  exit 1
fi

emit_artifact "pass" "complete" "${ingest_code}" "${fetch_before_code}" "${fetch_after_code}" "true"
exit 0
