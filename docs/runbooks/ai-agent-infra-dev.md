# AI Agent Infra Dev Runbook

## Purpose

Provision, verify, and roll back the dev AI agent infrastructure baseline for LangFuse + private-path Azure dependencies.

## Scope

- Scripts in `scripts/infra/` only.
- DEV-043/DEV-044/DEV-045 infra readiness checks and operator evidence points.
- Automatic checks only for resource/config validation; smoke checks remain manual.

## Preconditions

1. Azure CLI login and subscription context are set (`az login`, `az account set ...`).
2. `KEY_VAULT_NAME` is exported in your shell.
3. Kubernetes context points to the target AKS cluster.
4. Optional: `LANGFUSE_NAMESPACE` exported (defaults to `default`).

## Phase 1: Apply Baseline

1. Prepare env file:

```bash
cp scripts/infra/ai_agent_infra_dev.env.example scripts/infra/ai_agent_infra_dev.env
set -a
source scripts/infra/ai_agent_infra_dev.env
set +a
```

2. Apply Azure infra baseline:

```bash
bash scripts/infra/ai_agent_infra_dev_apply.sh
```

3. Apply internal LangFuse deployment:

```bash
bash scripts/infra/deploy_langfuse_internal.sh
```

## Phase 2: Automatic Verification

Run:

```bash
bash scripts/infra/verify_ai_agent_infra_dev.sh
```

Expected result:

- Each required check prints `PASS:`.
- Any missing/misconfigured requirement prints `FAIL:`.
- Script exits non-zero if one or more required checks fail.

## Phase 3: Manual Smoke and Evidence Capture

These checks are intentionally manual and should be attached as operator evidence (ticket comment, run log path, screenshots, or CLI output snippets).

### Databricks real-environment secret smoke (ADR-0015)

Secret resolution convention to verify:

- `get_secret` lookup order is env stub first, then Databricks secret scope.
- env stub key mapping is `SECRET_<NORMALIZED_KEY>` where `NORMALIZED_KEY` is uppercase, non-alnum -> `_`, repeated `_` collapsed, and leading/trailing `_` trimmed.
- scope env precedence is `DATABRICKS_SECRET_SCOPE` first, fallback `KEY_VAULT_SECRET_SCOPE`.

Required env vars (operator shell; scope vars required for step 3):

- `DATABRICKS_HOST`
- `DATABRICKS_TOKEN`
- `DATABRICKS_SECRET_SCOPE` (preferred) or `KEY_VAULT_SECRET_SCOPE` (fallback)
- `SECRET_SMOKE_KEY` (example: `azure-openai-endpoint`)
- `GET_SECRET_CALLABLE` (example: `module.path:get_secret`)

Execution commands:

```bash
# 1) Confirm Databricks auth context
databricks current-user me

# Shared env-stub key derivation (ADR-0015 normalization contract)
ENV_STUB_KEY="$(python - <<'PY'
import os
import re

key = os.environ["SECRET_SMOKE_KEY"].upper()
key = re.sub(r"[^A-Z0-9]+", "_", key)
key = re.sub(r"_+", "_", key).strip("_")
print(f"SECRET_{key}")
PY
)"

# 2) Env-first path (must succeed even if scope read would fail)
ORIG_DATABRICKS_SECRET_SCOPE="${DATABRICKS_SECRET_SCOPE-__UNSET__}"
ORIG_KEY_VAULT_SECRET_SCOPE="${KEY_VAULT_SECRET_SCOPE-__UNSET__}"
export DATABRICKS_SECRET_SCOPE="__invalid_scope_for_env_first_check__"
export KEY_VAULT_SECRET_SCOPE="__invalid_scope_for_env_first_check__"
export "$ENV_STUB_KEY=https://env-stub.example"
python -c "import importlib, os; module_path, func_name = os.environ['GET_SECRET_CALLABLE'].split(':', 1); get_secret = getattr(importlib.import_module(module_path), func_name); print(get_secret(os.environ['SECRET_SMOKE_KEY']))"

# 3) Scope-fallback path (env unset -> scope read)
unset "$ENV_STUB_KEY"
if [ "$ORIG_DATABRICKS_SECRET_SCOPE" = "__UNSET__" ]; then unset DATABRICKS_SECRET_SCOPE; else export DATABRICKS_SECRET_SCOPE="$ORIG_DATABRICKS_SECRET_SCOPE"; fi
if [ "$ORIG_KEY_VAULT_SECRET_SCOPE" = "__UNSET__" ]; then unset KEY_VAULT_SECRET_SCOPE; else export KEY_VAULT_SECRET_SCOPE="$ORIG_KEY_VAULT_SECRET_SCOPE"; fi
python -c "import importlib, os; module_path, func_name = os.environ['GET_SECRET_CALLABLE'].split(':', 1); get_secret = getattr(importlib.import_module(module_path), func_name); print(get_secret(os.environ['SECRET_SMOKE_KEY']))"
```

Success criteria:

- Step 2 prints env stub value and does not require scope read success.
- Step 3 prints non-empty scope value when `DATABRICKS_SECRET_SCOPE` (or fallback scope) is valid.
- Missing scope/secret and 403/404 are classified as `Permanent`; 429/5xx/timeouts are classified as `Transient`.

Failure criteria:

- Env stub present but scope read is attempted or env value is not returned.
- `DATABRICKS_SECRET_SCOPE` is set but implementation reads fallback scope first.
- Failure classification does not match: 403/404/missing secret -> `Permanent`; 429/5xx/timeouts -> `Transient`.

Evidence/log recording expectations:

- Attach executed commands, UTC timestamp, operator, workspace URL, and target branch/worktree.
- Attach stdout/stderr for both step 2 and step 3.
- Record the resolved scope variable source (`DATABRICKS_SECRET_SCOPE` vs `KEY_VAULT_SECRET_SCOPE`).
- Record one explicit pass/fail verdict per criterion above.

### Alert/Event smoke checklist

- [ ] `TRIAGE_READY`: inject a test event path, confirm Azure Monitor alert trigger and notification delivery.
- [ ] `APPROVAL_TIMEOUT`: run timeout scenario (30/60 minute policy), confirm reminder/escalation behavior.
- [ ] `EXECUTION_FAILED`: inject a controlled failed execution event and confirm alert trigger.

### Alerting real-environment send smoke minimum conditions (ADR-0024 reassessment)

Use this only when local smoke (`tests/smoke/test_alerting_smoke.py`) passes and one of the following is true:

- Production-like credential rotation or DCR endpoint change is pending.
- Alert rule/action group routing changed in DEV.
- Weekly alerting canary slot (one controlled send per week) is due.

Required auth/secrets:

- `LOG_ANALYTICS_DCR_ENDPOINT`
- `LOG_ANALYTICS_DCR_IMMUTABLE_ID`
- `LOG_ANALYTICS_STREAM_NAME`
- Databricks runtime identity/token that can call Azure Monitor Data Collection API in DEV

Execution timing guardrails:

- Run in DEV weekday daytime window (`09:00-18:00 KST`) so on-call can verify action-group delivery.
- Do not run during active incident handling unless the incident commander requested it.
- Keep one test event per `event_type` per run to avoid duplicate noise.

Execution example:

```bash
python - <<'PY'
from tools.alerting import TRIAGE_READY, emit_alert

emit_alert(
    severity="INFO",
    event_type=TRIAGE_READY,
    summary="dev real-path smoke",
    detail={"env": "dev", "smoke": "real-path", "operator": "<id>"},
)
print("sent")
PY
```

Pass criteria:

- `emit_alert` returns without exception.
- Corresponding custom log is queryable in Log Analytics within 5 minutes.
- Matching Azure Monitor alert fires exactly once and action-group notification is delivered.

### DEV-012 fingerprint smoke execution policy (ADR-0027)

Use `tests/smoke/test_incident_fingerprint_smoke.py` as the single execution entrypoint.

Execution command:

```bash
RUN_DEV012_FINGERPRINT_SMOKE=1 pytest tests/smoke/test_incident_fingerprint_smoke.py -rA -s
```

- `-s` preserves the emitted JSON line so `runtime_input_path` evidence is visible in stdout.
- `-rA` preserves skip-reason text in pytest's summary output.

Input path policy:

- Default fixture path: `tests/fixtures/runtime_inputs/<DEV012_SMOKE_ENV>_incident_input.json`
- `DEV012_SMOKE_ENV` default: `dev` (allowed values: `dev`, `staging`)
- Optional env override: `DEV012_RUNTIME_INPUT_PATH=/abs/path/to/input.json`

Opt-in gate policy:

- Smoke executes only when `RUN_DEV012_FINGERPRINT_SMOKE=1`.
- Without opt-in, the test is skipped by design.

Operator checklist (record evidence in ticket/PR note):

- [ ] Default fixture mode: run command above without `DEV012_RUNTIME_INPUT_PATH`; output `runtime_input_path` points to `tests/fixtures/runtime_inputs/dev_incident_input.json` or `staging_incident_input.json`.
- [ ] Override mode: rerun with `DEV012_RUNTIME_INPUT_PATH` and confirm output `runtime_input_path` equals the provided path.
- [ ] Gate mode: run once without `RUN_DEV012_FINGERPRINT_SMOKE=1` using `pytest tests/smoke/test_incident_fingerprint_smoke.py -rA -s` and confirm skip message appears.
- [ ] Rationale trace: keep ADR-0027 rejected alternatives in evidence notes (fixture-only rejected for low flexibility, real-env default rejected for low reproducibility, always-on rejected for unnecessary cost/dependency exposure).

### Private-path-only validation checklist

- [ ] Databricks job path reaches LangFuse via private network route only.
- [ ] LangFuse runtime reaches PostgreSQL via private endpoint only.
- [ ] No required runtime dependency succeeds via public endpoint fallback.

### Staging LangFuse UI smoke (internal-only)

Run this from a host inside the staging VNet (for example AKS jumpbox).

```bash
LANGFUSE_NAMESPACE=${LANGFUSE_NAMESPACE:-default} bash scripts/infra/smoke_langfuse_internal_ui.sh
```

Success criteria:

- Script exits `0`.
- JSON-line evidence includes `utc`, `namespace`, `http_code`, `response_sha256`, and sanitized `response_summary`.
- `http_code` is `200` or `302`.

Optional file evidence capture:

```bash
LANGFUSE_NAMESPACE=${LANGFUSE_NAMESPACE:-default} LANGFUSE_SMOKE_ARTIFACT_FILE=/tmp/langfuse-ui-smoke.jsonl bash scripts/infra/smoke_langfuse_internal_ui.sh
```

Latest staging evidence (2026-02-24 UTC):

- Evidence directory: `.agents/logs/verification/20260224T165252Z_i-3hl4_staging_langfuse_smoke/`
- Evidence path tracking: `.agents/logs/verification/**` is explicitly unignored in `.gitignore` for reproducible audit commits.
- Default stdout JSONL smoke: `12_smoke_stdout_default_rerun.log` (`exit_code: 0`, `http_code: 200`, `result: pass`)
- File append smoke: `13_smoke_with_artifact_file_rerun.log` + `langfuse-ui-smoke.jsonl` (`exit_code: 0`)
- Append/parity check: `14_artifact_append_validation.log` (`artifact_line_count:2`, `latest_line_matches_rerun_stdout:True`, `latest_http_code:200`)
- Sensitive raw marker scan: `15_sensitive_scan_rerun.log` (`token/cookie/set-cookie` raw marker `NOT_FOUND` in evidence targets)
- `.specs/` impact: none (operation evidence and runbook note only)

### Trace persistence checklist

- [ ] Write trace data through runtime path.
- [ ] Restart LangFuse pod.
- [ ] Confirm previously written trace remains queryable.

## DoD Mapping (Plan -> Evidence Source)

| Plan DoD item | Evidence source |
| --- | --- |
| DEV-043: LangFuse deployment manifest exists (Deployment + ClusterIP) | Automated: `scripts/infra/verify_ai_agent_infra_dev.sh` (`langfuse` deployment + `langfuse-internal` ClusterIP checks) |
| DEV-043: ACR image usage procedure is fixed | Manual/document evidence: `scripts/infra/README.md` + `deploy_langfuse_internal.sh` usage |
| DEV-043: internal-only access confirmation | Manual smoke: private-path-only checklist |
| DEV-043: staging LangFuse UI smoke | Manual smoke evidence |
| DEV-043: rollback procedure documented | Runbook rollback section below |
| DEV-044: PostgreSQL Flexible Server provisioning procedure exists | Automated + docs: apply script presence and verification check for `nsc-pg-langfuse-dev` |
| DEV-044: LangFuse connected to dedicated DB with migration success | Manual smoke evidence |
| DEV-044: trace persistence after pod restart | Manual smoke: trace persistence checklist |
| DEV-044: DB credentials managed via secrets/Key Vault | Automated: required Key Vault secret-name checks |
| DEV-044: staging end-to-end trace storage smoke | Manual smoke evidence |
| DEV-045: private DNS/records defined for OpenAI/Postgres | Automated: private DNS zones + VNet links + private endpoint checks |
| DEV-045: NSG rules align with network policy | Manual validation evidence |
| DEV-045: Databricks -> LangFuse -> PostgreSQL private-path smoke | Manual smoke evidence |
| DEV-045: rollback plan documented | Runbook rollback section below |

## Rollback

Use rollback scope matching the failed phase.

1. LangFuse workload rollback:

```bash
kubectl rollout undo deployment/langfuse -n "${LANGFUSE_NAMESPACE:-default}"
kubectl rollout status deployment/langfuse -n "${LANGFUSE_NAMESPACE:-default}"
```

2. Full LangFuse removal (if required):

```bash
kubectl delete deployment langfuse -n "${LANGFUSE_NAMESPACE:-default}"
kubectl delete service langfuse-internal -n "${LANGFUSE_NAMESPACE:-default}"
```

3. Azure resource rollback is manual and change-ticket controlled:

- Revert private endpoint, private DNS link/zone, and alert/action-group changes in reverse apply order.
- Validate rollback state with explicit absence checks for removed resources (for example `az resource show ...` returning NotFound and `kubectl get deployment/langfuse -n "${LANGFUSE_NAMESPACE:-default}"` returning NotFound when full LangFuse removal is intended).

## Operational Guardrails

- Never record plaintext secrets in docs, tickets, or command history artifacts.
- Treat verification script failures as release blockers for this infra scope.
- Keep manual smoke evidence with timestamp, operator, and environment.
