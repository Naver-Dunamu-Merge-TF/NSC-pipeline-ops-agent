#!/usr/bin/env bash
set -euo pipefail

LANGFUSE_NAMESPACE="${LANGFUSE_NAMESPACE:-default}"
LANGFUSE_SERVICE_NAME="${LANGFUSE_SERVICE_NAME:-langfuse-internal}"
LANGFUSE_LOCAL_PORT="${LANGFUSE_LOCAL_PORT:-3000}"
LANGFUSE_REMOTE_PORT="${LANGFUSE_REMOTE_PORT:-3000}"
LANGFUSE_SMOKE_PATH="${LANGFUSE_SMOKE_PATH:-/}"
LANGFUSE_SMOKE_TIMEOUT_SECONDS="${LANGFUSE_SMOKE_TIMEOUT_SECONDS:-10}"
PORT_FORWARD_READY_TIMEOUT_SECONDS="${PORT_FORWARD_READY_TIMEOUT_SECONDS:-20}"
PORT_FORWARD_READY_POLL_SECONDS="${PORT_FORWARD_READY_POLL_SECONDS:-1}"
LANGFUSE_SMOKE_ARTIFACT_FILE="${LANGFUSE_SMOKE_ARTIFACT_FILE:-}"

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
RESPONSE_BODY_FILE="${TMP_DIR}/response.body"
PORT_FORWARD_PID=""

cleanup() {
  if [ -n "${PORT_FORWARD_PID}" ] && kill -0 "${PORT_FORWARD_PID}" >/dev/null 2>&1; then
    kill "${PORT_FORWARD_PID}" >/dev/null 2>&1 || true
    wait "${PORT_FORWARD_PID}" >/dev/null 2>&1 || true
  fi
  rm -rf "${TMP_DIR}"
}

trap cleanup EXIT

response_hash() {
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
if not path.exists():
    print(hashlib.sha256(b"").hexdigest())
else:
    print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
}

response_summary() {
  python3 - "$1" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = ""
if path.exists():
    text = path.read_text(encoding="utf-8", errors="replace")

text = re.sub(r"(?is)(set-cookie|cookie|token)\s*[:=]\s*[^\s;<>\"]+", "sensitive=[REDACTED]", text)
text = re.sub(r"(?is)(\"(?:set-cookie|cookie|token)\"\s*:\s*)\".*?\"", r"\1\"[REDACTED]\"", text)
text = re.sub(r"(?is)(set-cookie|cookie|token)", "sensitive", text)
text = re.sub(r"\s+", " ", text).strip()

if not text:
    print("<empty>")
else:
    print(text[:160])
PY
}

emit_artifact() {
  local http_code="$1"
  local result="$2"
  local utc_ts
  local hash
  local summary
  local artifact_line

  utc_ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  hash="$(response_hash "${RESPONSE_BODY_FILE}")"
  summary="$(response_summary "${RESPONSE_BODY_FILE}")"

  artifact_line="$(python3 - "${utc_ts}" "${LANGFUSE_NAMESPACE}" "${LANGFUSE_SERVICE_NAME}" "${http_code}" "${result}" "${hash}" "${summary}" <<'PY'
import json
import sys

data = {
    "event": "langfuse_ui_smoke",
    "utc": sys.argv[1],
    "namespace": sys.argv[2],
    "service": sys.argv[3],
    "http_code": int(sys.argv[4]) if sys.argv[4].isdigit() else sys.argv[4],
    "result": sys.argv[5],
    "response_sha256": sys.argv[6],
    "response_summary": sys.argv[7],
}
print(json.dumps(data, ensure_ascii=True, separators=(",", ":")))
PY
 )"

  if [ -n "${LANGFUSE_SMOKE_ARTIFACT_FILE}" ]; then
    printf '%s\n' "${artifact_line}" >> "${LANGFUSE_SMOKE_ARTIFACT_FILE}"
  fi

  printf '%s\n' "${artifact_line}"
}

SMOKE_URL="http://127.0.0.1:${LANGFUSE_LOCAL_PORT}${LANGFUSE_SMOKE_PATH}"

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

  http_code="$(curl -sS -o "${RESPONSE_BODY_FILE}" -w '%{http_code}' --max-time "${LANGFUSE_SMOKE_TIMEOUT_SECONDS}" "${SMOKE_URL}" || true)"
  if [ -n "${http_code}" ] && [ "${http_code}" != "000" ]; then
    ready=1
    break
  fi

  sleep "${PORT_FORWARD_READY_POLL_SECONDS}"
done

if [ "${ready}" -ne 1 ]; then
  emit_artifact "000" "fail"
  echo "FAIL: port-forward did not become ready within ${PORT_FORWARD_READY_TIMEOUT_SECONDS}s" >&2
  exit 1
fi

http_code="$(curl -sS -o "${RESPONSE_BODY_FILE}" -w '%{http_code}' --max-time "${LANGFUSE_SMOKE_TIMEOUT_SECONDS}" "${SMOKE_URL}" || true)"

if [ "${http_code}" = "200" ] || [ "${http_code}" = "302" ]; then
  emit_artifact "${http_code}" "pass"
  exit 0
fi

emit_artifact "${http_code:-000}" "fail"
echo "FAIL: expected HTTP 200 or 302, got ${http_code:-000}" >&2
exit 1
