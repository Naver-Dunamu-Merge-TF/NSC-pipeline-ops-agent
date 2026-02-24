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

### Alert/Event smoke checklist

- [ ] `TRIAGE_READY`: inject a test event path, confirm Azure Monitor alert trigger and notification delivery.
- [ ] `APPROVAL_TIMEOUT`: run timeout scenario (30/60 minute policy), confirm reminder/escalation behavior.
- [ ] `EXECUTION_FAILED`: inject a controlled failed execution event and confirm alert trigger.

### Private-path-only validation checklist

- [ ] Databricks job path reaches LangFuse via private network route only.
- [ ] LangFuse runtime reaches PostgreSQL via private endpoint only.
- [ ] No required runtime dependency succeeds via public endpoint fallback.

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
