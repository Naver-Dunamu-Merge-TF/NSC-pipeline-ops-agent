# AI Agent Infra (dev)

This directory contains a minimal Azure CLI provisioning script for AI agent infrastructure in dev.

## Prerequisites

- Azure CLI installed and authenticated (`az login`).
- Active subscription selected for this environment (`az account set --subscription <subscription-id-or-name>`).
- `kubectl` installed with access to the target AKS cluster and `LANGFUSE_NAMESPACE` (or `default` when unset) for deploy/verify checks.
- `envsubst` available (required by `deploy_langfuse_internal.sh` manifest rendering).
- Kubernetes context already set to the target AKS cluster before running deploy/verify workflows.
- Run verification from a network context that can reach private endpoints (for example the Bastion-accessed jumpbox in `nsc-vnet-dev`).
- Existing network/container resources used by the script:
  - Resource group: `2dt-final-team4`
  - VNet: `nsc-vnet-dev`
  - Subnet passed through `PE_SUBNET_NAME` (for private endpoints)
- Permissions to read/create the resources managed here (resource group, networking/private endpoint + private DNS, OpenAI, PostgreSQL Flexible Server, Monitor alerts/action groups, and Key Vault secret metadata reads).

## Files

- `ai_agent_infra_dev.env.example`: Example environment variables required by the apply script.
- `ai_agent_infra_dev_apply.sh`: Idempotent script that ensures required Azure resources exist.
- `verify_ai_agent_infra_dev.sh`: Verification script that checks expected dev infra resources and hardening state.

## What the script ensures

Behavior note: this script is intentionally create-if-absent for most resources. If a resource already exists, the script reuses it instead of remediating full configuration drift. It explicitly enforces public access hardening for OpenAI and PostgreSQL, and checks required Key Vault secret names exist.

- Resource group target: `2dt-final-team4`
- VNet target: `nsc-vnet-dev`
- OpenAI account: `nsc-aoai-dev` (public network access disabled)
- PostgreSQL Flexible Server: `nsc-pg-langfuse-dev` (public access disabled)
- Private DNS zones and VNet links:
  - `privatelink.openai.azure.com`
  - `privatelink.postgres.database.azure.com`
- Private endpoints with DNS zone groups:
  - `nsc-pe-openai`
  - `nsc-pe-pg-langfuse`
- Action group: `nsc-ag-agent-dev`
- Scheduled query alerts:
  - `nsc-alert-triage-ready-dev`
  - `nsc-alert-approval-timeout-dev`
  - `nsc-alert-execution-failed-dev`
- Key Vault secret name checks (existence only, no values written):
  - `azure-openai-api-key`
  - `azure-openai-endpoint`
  - `azure-openai-deployment`
  - `langfuse-public-key`
  - `langfuse-secret-key`
  - `log-analytics-dcr-id`
  - `agent-execute-mode`
  - `databricks-agent-token`

## Usage

1. Copy and edit env file:

```bash
cp scripts/infra/ai_agent_infra_dev.env.example scripts/infra/ai_agent_infra_dev.env
```

2. Load environment variables:

```bash
set -a
source scripts/infra/ai_agent_infra_dev.env
set +a
```

3. Run the script:

```bash
bash scripts/infra/ai_agent_infra_dev_apply.sh
```

4. Run automatic verification checks:

```bash
bash scripts/infra/verify_ai_agent_infra_dev.sh
```

Verification notes:

- Requires `KEY_VAULT_NAME` in environment and access to read that vault.
- Uses `LANGFUSE_NAMESPACE` for AKS checks (`default` if unset).
- Uses `LANGFUSE_SECRET_NAME` for AKS LangFuse runtime secret checks (`langfuse-secrets` if unset).
- Verifies private endpoint DNS zone-group (`default`) bindings for OpenAI and PostgreSQL include the expected zone IDs and zone names.
- Verifies LangFuse deployment rollout readiness (`kubectl rollout status`) rather than deployment existence only.
- Verifies required LangFuse runtime Secret keys exist in Kubernetes (`langfuse-public-key`, `langfuse-secret-key`, `database-url`, `azure-openai-api-key`, `azure-openai-endpoint`, `azure-openai-deployment`).
- Prints `PASS:`/`FAIL:` lines per check and exits non-zero when any required check fails.

## LangFuse internal AKS deployment

This deployment is internal-only in AKS:

- Deployment: `langfuse`
- Service: `langfuse-internal` (`ClusterIP` only)
- Manifests: `scripts/infra/k8s/langfuse/deployment.yaml` and `scripts/infra/k8s/langfuse/service.yaml`

Required Kubernetes Secret values (in `LANGFUSE_SECRET_NAME`, default `langfuse-secrets`):

- `langfuse-public-key`
- `langfuse-secret-key`
- `database-url`
- `azure-openai-api-key`
- `azure-openai-endpoint`
- `azure-openai-deployment`

Deploy:

```bash
export LANGFUSE_NAMESPACE=default
export LANGFUSE_IMAGE=your-acr-name.azurecr.io/langfuse:latest
export LANGFUSE_SECRET_NAME=langfuse-secrets
export LANGFUSE_ROLLOUT_TIMEOUT=120s
bash scripts/infra/deploy_langfuse_internal.sh
```

Rollout check:

```bash
kubectl rollout status deployment/langfuse -n "${LANGFUSE_NAMESPACE:-default}" --timeout="${LANGFUSE_ROLLOUT_TIMEOUT:-120s}"
```

Rollback:

```bash
kubectl rollout undo deployment/langfuse -n "${LANGFUSE_NAMESPACE:-default}"
kubectl rollout status deployment/langfuse -n "${LANGFUSE_NAMESPACE:-default}"
```
