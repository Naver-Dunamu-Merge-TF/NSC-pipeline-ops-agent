from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
from pathlib import Path


SCRIPT_PATH = Path("scripts/infra/smoke_langfuse_trace_persistence.sh")


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_fake_bin(
    tmp_path: Path,
    *,
    curl_codes: str,
    curl_bodies: str,
    expected_auth: str,
    public_key: str,
    secret_key: str,
) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)

    public_b64 = base64.b64encode(public_key.encode("utf-8")).decode("ascii")
    secret_b64 = base64.b64encode(secret_key.encode("utf-8")).decode("ascii")

    _write_executable(
        fake_bin / "kubectl",
        f"""#!/usr/bin/env bash
set -euo pipefail
if [ "${{1:-}}" = "port-forward" ]; then
  trap 'exit 0' TERM INT
  while true; do
    sleep 1
  done
fi
if [ "${{1:-}}" = "get" ] && [ "${{2:-}}" = "secret" ]; then
  if [ "${{FAKE_KUBECTL_SECRET_FAIL:-0}}" = "1" ]; then
    echo "secret retrieval failed" >&2
    exit 1
  fi
  if [[ "$*" == *"langfuse-public-key"* ]]; then
    printf '%s' '{public_b64}'
    exit 0
  fi
  if [[ "$*" == *"langfuse-secret-key"* ]]; then
    printf '%s' '{secret_b64}'
    exit 0
  fi
fi
if [ "${{1:-}}" = "rollout" ] && [ "${{2:-}}" = "restart" ]; then
  if [ "${{FAKE_KUBECTL_ROLLOUT_FAIL_STAGE:-}}" = "restart" ]; then
    echo "rollout restart failed" >&2
    exit 1
  fi
  printf 'restart\\n' >> "${{FAKE_KUBECTL_LOG_FILE:?}}"
  exit 0
fi
if [ "${{1:-}}" = "rollout" ] && [ "${{2:-}}" = "status" ]; then
  if [ "${{FAKE_KUBECTL_ROLLOUT_FAIL_STAGE:-}}" = "status" ]; then
    echo "rollout status failed" >&2
    exit 1
  fi
  printf 'status\\n' >> "${{FAKE_KUBECTL_LOG_FILE:?}}"
  exit 0
fi
echo "unexpected kubectl args: $*" >&2
exit 1
""",
    )

    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
set -euo pipefail
counter_file="${FAKE_CURL_COUNTER_FILE:?}"
codes="${FAKE_CURL_CODES:?}"
bodies="${FAKE_CURL_BODIES:?}"
expected_auth="${FAKE_CURL_EXPECTED_AUTH:?}"

count=0
if [ -f "$counter_file" ]; then
  count="$(cat "$counter_file")"
fi
count=$((count + 1))
printf '%s' "$count" > "$counter_file"

code="$(printf '%s' "$codes" | cut -d',' -f"$count")"
[ -n "$code" ] || code="500"
body="$(printf '%s' "$bodies" | cut -d'|' -f"$count")"

out_file=""
auth=""
url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o)
      shift
      out_file="${1:-}"
      ;;
    -u)
      shift
      auth="${1:-}"
      ;;
    http://*|https://*)
      url="$1"
      ;;
  esac
  shift || true
done

printf '%s\\n' "$url" >> "${FAKE_CURL_URL_LOG_FILE:?}"

if [ -n "$url" ] && [[ "$url" == *"/api/public/"* ]]; then
  if [ "$auth" != "$expected_auth" ]; then
    echo "invalid auth" >&2
    exit 1
  fi
fi

if [ -n "$out_file" ]; then
  printf '%s' "$body" > "$out_file"
fi
printf '%s' "$code"
""",
    )

    _write_executable(
        fake_bin / "python3",
        """#!/usr/bin/env bash
exec /usr/bin/python3 "$@"
""",
    )

    return fake_bin


def _run_script(
    tmp_path: Path,
    *,
    curl_codes: str,
    curl_bodies: str,
    expected_auth: str,
    public_key: str,
    secret_key: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    fake_bin = _make_fake_bin(
        tmp_path,
        curl_codes=curl_codes,
        curl_bodies=curl_bodies,
        expected_auth=expected_auth,
        public_key=public_key,
        secret_key=secret_key,
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "LANGFUSE_NAMESPACE": "test-ns",
            "LANGFUSE_SECRET_NAME": "langfuse-secrets",
            "LANGFUSE_TRACE_ID": "trace-dev044-001",
            "PORT_FORWARD_READY_TIMEOUT_SECONDS": "1",
            "LANGFUSE_SMOKE_TIMEOUT_SECONDS": "2",
            "FAKE_CURL_COUNTER_FILE": str(tmp_path / "curl-counter"),
            "FAKE_CURL_CODES": curl_codes,
            "FAKE_CURL_BODIES": curl_bodies,
            "FAKE_CURL_EXPECTED_AUTH": expected_auth,
            "FAKE_CURL_URL_LOG_FILE": str(tmp_path / "curl-urls.log"),
            "FAKE_KUBECTL_LOG_FILE": str(tmp_path / "kubectl.log"),
        }
    )
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _parse_artifact(stdout: str) -> dict[str, object]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])


def test_trace_persistence_smoke_passes_and_emits_artifact(tmp_path: Path) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="200,202,200,200",
        curl_bodies='ready|{"success":true}|{"id":"trace-dev044-001"}|{"id":"trace-dev044-001"}',
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
    )

    assert result.returncode == 0
    artifact = _parse_artifact(result.stdout)
    assert artifact["event"] == "langfuse_trace_persistence_smoke"
    assert artifact["namespace"] == "test-ns"
    assert artifact["trace_id"] == "trace-dev044-001"
    assert artifact["ingest_http_code"] == 202
    assert artifact["fetch_before_http_code"] == 200
    assert artifact["fetch_after_http_code"] == 200
    assert artifact["result"] == "pass"

    kubectl_log = (tmp_path / "kubectl.log").read_text(encoding="utf-8")
    assert "restart" in kubectl_log
    assert "status" in kubectl_log

    curl_urls = (tmp_path / "curl-urls.log").read_text(encoding="utf-8")
    assert "/api/public/ingestion" in curl_urls
    assert "/api/public/traces/trace-dev044-001" in curl_urls


def test_trace_persistence_smoke_retries_before_restart_until_trace_exists(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="200,202,404,200,200",
        curl_bodies='ready|{"success":true}|{"error":"pending"}|{"id":"trace-dev044-001"}|{"id":"trace-dev044-001"}',
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
        extra_env={
            "LANGFUSE_TRACE_FETCH_RETRIES": "3",
            "LANGFUSE_TRACE_FETCH_RETRY_INTERVAL_SECONDS": "0",
        },
    )

    assert result.returncode == 0
    artifact = _parse_artifact(result.stdout)
    assert artifact["result"] == "pass"
    assert artifact["fetch_before_http_code"] == 200


def test_trace_persistence_smoke_fails_when_trace_not_retrievable_after_restart(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="200,202,200,404,404",
        curl_bodies='ready|{"success":true}|{"id":"trace-dev044-001"}|{"error":"missing"}|{"error":"missing"}',
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
        extra_env={
            "LANGFUSE_TRACE_FETCH_RETRIES": "2",
            "LANGFUSE_TRACE_FETCH_RETRY_INTERVAL_SECONDS": "0",
        },
    )

    assert result.returncode == 1
    artifact = _parse_artifact(result.stdout)
    assert artifact["result"] == "fail"
    assert artifact["stage"] == "fetch_after_restart"
    assert artifact["fetch_after_http_code"] == 404


def test_trace_persistence_smoke_retries_after_restart_until_trace_exists(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="200,202,200,404,200",
        curl_bodies='ready|{"success":true}|{"id":"trace-dev044-001"}|{"error":"pending"}|{"id":"trace-dev044-001"}',
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
        extra_env={
            "LANGFUSE_TRACE_FETCH_RETRIES": "2",
            "LANGFUSE_TRACE_FETCH_RETRY_INTERVAL_SECONDS": "0",
        },
    )

    assert result.returncode == 0
    artifact = _parse_artifact(result.stdout)
    assert artifact["result"] == "pass"
    assert artifact["fetch_after_http_code"] == 200


def test_trace_persistence_smoke_appends_artifact_file_when_configured(
    tmp_path: Path,
) -> None:
    artifact_file = tmp_path / "trace-smoke.jsonl"
    result = _run_script(
        tmp_path,
        curl_codes="200,202,200,200",
        curl_bodies='ready|{"success":true}|{"id":"trace-dev044-001"}|{"id":"trace-dev044-001"}',
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
        extra_env={"LANGFUSE_TRACE_SMOKE_ARTIFACT_FILE": str(artifact_file)},
    )

    assert result.returncode == 0
    lines = [
        line
        for line in artifact_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 1
    from_file = json.loads(lines[0])
    from_stdout = _parse_artifact(result.stdout)
    assert from_file == from_stdout


def test_trace_persistence_smoke_emits_artifact_when_secret_retrieval_fails(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="200",
        curl_bodies="ready",
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
        extra_env={"FAKE_KUBECTL_SECRET_FAIL": "1"},
    )

    assert result.returncode == 1
    artifact = _parse_artifact(result.stdout)
    assert artifact["result"] == "fail"
    assert artifact["stage"] == "secret_retrieval"


def test_trace_persistence_smoke_emits_artifact_when_rollout_restart_fails(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="200,202,200",
        curl_bodies='ready|{"success":true}|{"id":"trace-dev044-001"}',
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
        extra_env={"FAKE_KUBECTL_ROLLOUT_FAIL_STAGE": "restart"},
    )

    assert result.returncode == 1
    artifact = _parse_artifact(result.stdout)
    assert artifact["result"] == "fail"
    assert artifact["stage"] == "rollout_restart"


def test_trace_persistence_smoke_emits_artifact_when_rollout_status_fails(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="200,202,200",
        curl_bodies='ready|{"success":true}|{"id":"trace-dev044-001"}',
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
        extra_env={"FAKE_KUBECTL_ROLLOUT_FAIL_STAGE": "status"},
    )

    assert result.returncode == 1
    artifact = _parse_artifact(result.stdout)
    assert artifact["result"] == "fail"
    assert artifact["stage"] == "rollout_status"


def test_trace_persistence_smoke_emits_artifact_when_credentials_missing(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="",
        curl_bodies="",
        expected_auth="pk-dev:sk-dev",
        public_key="\n",
        secret_key="\n",
    )

    assert result.returncode == 1
    artifact = _parse_artifact(result.stdout)
    assert artifact["result"] == "fail"
    assert artifact["stage"] == "credentials"


def test_trace_persistence_smoke_emits_artifact_when_port_forward_fails(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="000,000",
        curl_bodies="|",
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
        extra_env={
            "PORT_FORWARD_READY_TIMEOUT_SECONDS": "1",
            "PORT_FORWARD_READY_POLL_SECONDS": "1",
            "LANGFUSE_SMOKE_TIMEOUT_SECONDS": "1",
        },
    )

    assert result.returncode == 1
    artifact = _parse_artifact(result.stdout)
    assert artifact["result"] == "fail"
    assert artifact["stage"] == "port_forward"


def test_trace_persistence_smoke_emits_artifact_when_ingest_fails(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="200,500",
        curl_bodies="ready|",
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
    )

    assert result.returncode == 1
    artifact = _parse_artifact(result.stdout)
    assert artifact["result"] == "fail"
    assert artifact["stage"] == "ingest"
    assert artifact["ingest_http_code"] == 500


def test_trace_persistence_smoke_emits_artifact_when_fetch_before_restart_fails(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="200,202,404,404",
        curl_bodies='ready|{"success":true}|{"error":"missing"}|{"error":"missing"}',
        expected_auth="pk-dev:sk-dev",
        public_key="pk-dev",
        secret_key="sk-dev",
        extra_env={
            "LANGFUSE_TRACE_FETCH_RETRIES": "2",
            "LANGFUSE_TRACE_FETCH_RETRY_INTERVAL_SECONDS": "0",
        },
    )

    assert result.returncode == 1
    artifact = _parse_artifact(result.stdout)
    assert artifact["result"] == "fail"
    assert artifact["stage"] == "fetch_before_restart"
    assert artifact["fetch_before_http_code"] == 404
