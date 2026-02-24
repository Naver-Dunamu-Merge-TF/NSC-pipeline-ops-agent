from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


SCRIPT_PATH = Path("scripts/infra/smoke_langfuse_internal_ui.sh")


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_fake_bin(tmp_path: Path, curl_codes: str, curl_body: str) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)

    _write_executable(
        fake_bin / "kubectl",
        """#!/usr/bin/env bash
set -euo pipefail
if [ \"${1:-}\" = \"port-forward\" ]; then
  trap 'exit 0' TERM INT
  while true; do
    sleep 1
  done
fi
echo \"unexpected kubectl args: $*\" >&2
exit 1
""",
    )

    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
set -euo pipefail
counter_file=\"${FAKE_CURL_COUNTER_FILE:?}\"
codes=\"${FAKE_CURL_CODES:?}\"
body=\"${FAKE_CURL_BODY:?}\"
count=0
if [ -f \"$counter_file\" ]; then
  count=\"$(cat \"$counter_file\")\"
fi
count=$((count + 1))
printf '%s' \"$count\" > \"$counter_file\"
code=\"$(printf '%s' \"$codes\" | cut -d',' -f\"$count\")\"
[ -n \"$code\" ] || code=\"500\"

out_file=\"\"
while [ $# -gt 0 ]; do
  case \"$1\" in
    -o)
      shift
      out_file=\"${1:-}\"
      ;;
  esac
  shift || true
done

if [ -n \"$out_file\" ]; then
  printf '%s' \"$body\" > \"$out_file\"
fi
printf '%s' \"$code\"
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
    tmp_path: Path, curl_codes: str, curl_body: str
) -> subprocess.CompletedProcess[str]:
    fake_bin = _make_fake_bin(tmp_path, curl_codes=curl_codes, curl_body=curl_body)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "LANGFUSE_NAMESPACE": "test-ns",
            "FAKE_CURL_COUNTER_FILE": str(tmp_path / "curl-counter"),
            "FAKE_CURL_CODES": curl_codes,
            "FAKE_CURL_BODY": curl_body,
            "PORT_FORWARD_READY_TIMEOUT_SECONDS": "1",
            "LANGFUSE_SMOKE_TIMEOUT_SECONDS": "2",
        }
    )
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


def test_langfuse_ui_smoke_treats_302_as_success_and_masks_sensitive_markers(
    tmp_path: Path,
) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="302,302",
        curl_body="<html>token=abc cookie=xyz set-cookie: sid=123</html>",
    )

    assert result.returncode == 0
    artifact = _parse_artifact(result.stdout)
    assert artifact["namespace"] == "test-ns"
    assert artifact["http_code"] == 302
    assert artifact["result"] == "pass"
    assert "response_sha256" in artifact
    summary = str(artifact["response_summary"])
    assert "cookie" not in summary.lower()
    assert "token" not in summary.lower()


def test_langfuse_ui_smoke_fails_for_non_200_302_status(tmp_path: Path) -> None:
    result = _run_script(
        tmp_path,
        curl_codes="500,500",
        curl_body="<html>error</html>",
    )

    assert result.returncode == 1
    artifact = _parse_artifact(result.stdout)
    assert artifact["http_code"] == 500
    assert artifact["result"] == "fail"
