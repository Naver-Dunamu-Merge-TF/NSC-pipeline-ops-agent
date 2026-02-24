# Alerting retry/smoke 재평가 보고서 (i-5m9o)

- 작성 시각 (UTC): 2026-02-25 00:00
- 대상 이슈: `i-5m9o`
- 기준 ADR: `docs/adr/0024-use-bounded-retry-and-local-smoke.md`

## 1) DEV 관측 지표 수집 결과 (429/5xx/timeout)

### DEV 관측 대상 식별

아래 명령으로 이 저장소의 DEV 인프라 대상과 관측 지점을 확인했다.

```bash
az account show --output json
az group show --name "2dt-final-team4" --output json
az monitor log-analytics workspace list --resource-group "2dt-final-team4" --output json
az monitor data-collection rule list --resource-group "2dt-final-team4" --query "[].{name:name,immutableId:immutableId,dataFlows:dataFlows}" --output json
```

요약 출력:

- subscription: `27db5ec6-d206-4028-b5e1-6004dca5eeef`
- resource group: `2dt-final-team4`
- DEV Log Analytics workspace: `nsc-law-dev` (`customerId=748abb68-8c24-4075-9354-f21c34699dc2`)
- DEV DCR 목록: `MSProm-koreacentral-team4akstemp` 1개, `streams=["Microsoft-PrometheusMetrics"]`

### DEV 실제 관측 결과 (최근 7일)

- 관측 시각(UTC): `2026-02-24 16:30:18`
- 관측 윈도우: `ago(7d)`

실행 명령:

```bash
az monitor log-analytics query \
  --workspace "748abb68-8c24-4075-9354-f21c34699dc2" \
  --analytics-query "AppTraces | where TimeGenerated > ago(7d) | summarize total=count(), approval_timeout=countif(Message has 'approval_timeout'), triage_ready=countif(Message has 'triage_ready'), execution_failed=countif(Message has 'execution_failed')" \
  --output json

az monitor log-analytics query \
  --workspace "748abb68-8c24-4075-9354-f21c34699dc2" \
  --analytics-query "AppTraces | where TimeGenerated > ago(7d) | where Message has_any ('429','500','502','503','504','timeout','timed out') | summarize matched=count()" \
  --output json

az monitor log-analytics query \
  --workspace "748abb68-8c24-4075-9354-f21c34699dc2" \
  --analytics-query "AppDependencies | where TimeGenerated > ago(7d) | summarize total=count(), failed=countif(Success == false), status_429=countif(ResultCode == '429'), status_5xx=countif(ResultCode startswith '5')" \
  --output json

az monitor log-analytics workspace table show \
  --resource-group "2dt-final-team4" \
  --workspace-name "nsc-law-dev" \
  --name "AiAgentEvents_CL" \
  --output json
```

요약 출력:

- `AppTraces`: `total=11816`, `approval_timeout=0`, `triage_ready=0`, `execution_failed=0`
- `AppTraces` transient keyword(`429/5xx/timeout`) 매치: `matched=0`
- `AppDependencies`: `total=0`, `failed=0`, `status_429=0`, `status_5xx=0`
- `AiAgentEvents_CL` 조회: `ResourceNotFound (table does not exist)`

해석:

- 현재 DEV 워크스페이스에서는 alert sender 경로의 429/5xx/timeout을 직접 관측할 테이블/신호(`AiAgentEvents_CL` 또는 동등 의존성 텔레메트리)가 확인되지 않았다.
- 따라서 이번 재평가에서 429/5xx/timeout의 빈도/비율에 대한 DEV 실측 통계는 산출할 수 없다.

## 2) 합성(synthetic) 재현 결과 (비-DEV 실관측, 구현 동작 확인용)

아래는 로컬 주입 sender 기반 합성 재현이며, DEV 실환경 텔레메트리 관측이 아니라 구현 동작 검증 근거다.

```bash
python - <<'PY'
from __future__ import annotations

import json
import time
from urllib.error import HTTPError
from urllib.request import Request

from tools.alerting import APPROVAL_TIMEOUT, emit_alert

BASE_ENV = {
    "LOG_ANALYTICS_DCR_ENDPOINT": "https://ingest.monitor.azure.com",
    "LOG_ANALYTICS_DCR_IMMUTABLE_ID": "dcr-abc123",
    "LOG_ANALYTICS_STREAM_NAME": "Custom-AiAgentEvents",
}


def run_case(name, sender):
    attempts = 0

    def wrapped_sender(request: Request, timeout: float):
        nonlocal attempts
        attempts += 1
        return sender(request, timeout, attempts)

    started = time.perf_counter()
    result = "success"
    err_type = ""
    try:
        emit_alert(
            severity="WARNING",
            event_type=APPROVAL_TIMEOUT,
            summary=f"reassess {name}",
            detail={"case": name},
            environ=BASE_ENV,
            sender=wrapped_sender,
        )
    except Exception as exc:  # noqa: BLE001
        result = "error"
        err_type = type(exc).__name__
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "case": name,
        "result": result,
        "error_type": err_type,
        "attempts": attempts,
        "elapsed_ms": elapsed_ms,
    }


def sender_429(request: Request, timeout: float, attempt: int):
    del request, timeout, attempt
    raise HTTPError(
        url="https://ingest.monitor.azure.com",
        code=429,
        msg="too many requests",
        hdrs=None,
        fp=None,
    )


def sender_503_then_ok(request: Request, timeout: float, attempt: int):
    del request, timeout
    if attempt < 3:
        raise HTTPError(
            url="https://ingest.monitor.azure.com",
            code=503,
            msg="service unavailable",
            hdrs=None,
            fp=None,
        )
    return type("Resp", (), {"status": 204})()


def sender_timeout_then_ok(request: Request, timeout: float, attempt: int):
    del request, timeout
    if attempt < 3:
        raise TimeoutError("timed out")
    return type("Resp", (), {"status": 204})()


rows = [
    run_case("429_always", sender_429),
    run_case("503_then_ok", sender_503_then_ok),
    run_case("timeout_then_ok", sender_timeout_then_ok),
]
print(json.dumps(rows, ensure_ascii=True, indent=2))
PY
```

| failure type | scenario | attempts | result | elapsed (ms) |
|---|---|---:|---|---:|
| 429 | always fail | 3 | `TransientAlertError` | 0.25 |
| 5xx (503) | fail x2 then recover | 3 | success | 0.07 |
| timeout | fail x2 then recover | 3 | success | 0.03 |

해석:

- 합성 주입 기준에서 기본 재시도 상한(2회, 총 3회 시도) 경계 동작은 일관적이다.
- 단, 이 결과는 DEV 실환경 발생 빈도/분포를 나타내지 않는다.

## 3) 재시도 정책 유지/조정안

- 결론: ADR-0024 기본값(`ALERTING_MAX_RETRIES=2`, 총 3회 시도) **유지**.
- 근거: DEV 실관측에서는 현재 해당 failure telemetry를 직접 산출할 신호가 부재하고, 합성 재현에서는 구현 경계 동작이 ADR 가정과 일치함.
- 조정 필요성: DEV 실관측 신호 확보 전까지는 없음.
- 코드/설정 반영: 즉시 변경 없음.

저영향 가역 결정(결정-보류):

- 재시도 간격(0초 유지)은 현 상태를 기본으로 둔다.
- 향후 DEV 실관측 신호(예: `AiAgentEvents_CL` 또는 동등 전송 결과 테이블) 확보 후 연속 429 비중이 높거나 DCR throttling 증가가 확인되면, `ALERTING_RETRY_INTERVAL_SECONDS` 도입 여부를 별도 ADR/이슈로 재검토한다.

## 4) 실환경 전송 검증(로컬 스모크 외) 최소 조건

운영 문서 반영:

- `docs/runbooks/ai-agent-infra-dev.md`에 "Alerting real-environment send smoke minimum conditions" 섹션 추가.

핵심 기준:

- 인증/비밀: DCR endpoint/id/stream + DEV 실행 주체 인증 준비.
- 실행 시점: DEV 주간 운영 시간대(09:00-18:00 KST), 액티브 인시던트와 분리.
- 실행 트리거: credential rotation, alert routing 변경, 주간 canary 슬롯.
- 판정: 전송 성공 + Log Analytics 조회 가능 + Alert/Action Group 단건 전달 확인.

## 5) ADR-0024 충돌 여부 및 후속 ADR 필요성

- 판정: **충돌 없음**.
- 이유: 재평가 결과가 "bounded retry + local smoke 기본" 결정을 유지하며, 실환경 smoke는 로컬 smoke를 대체하지 않는 보완 절차로 정의했다.
- 후속 ADR: 현재는 불필요. 단, 재시도 간격 정책을 신규 설정으로 도입할 경우 ADR 발행 검토.
