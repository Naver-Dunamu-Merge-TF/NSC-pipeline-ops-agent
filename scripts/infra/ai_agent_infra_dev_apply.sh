#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="2dt-final-team4"
VNET_NAME="nsc-vnet-dev"

OPENAI_ACCOUNT_NAME="nsc-aoai-dev"
POSTGRES_SERVER_NAME="nsc-pg-langfuse-dev"

OPENAI_PRIVATE_ENDPOINT_NAME="nsc-pe-openai"
POSTGRES_PRIVATE_ENDPOINT_NAME="nsc-pe-pg-langfuse"

OPENAI_PRIVATE_DNS_ZONE="privatelink.openai.azure.com"
POSTGRES_PRIVATE_DNS_ZONE="privatelink.postgres.database.azure.com"

OPENAI_DNS_LINK_NAME="nsc-link-openai-dev"
POSTGRES_DNS_LINK_NAME="nsc-link-pg-langfuse-dev"

ACTION_GROUP_NAME="nsc-ag-agent-dev"
ALERT_TRIAGE_READY_NAME="nsc-alert-triage-ready-dev"
ALERT_APPROVAL_TIMEOUT_NAME="nsc-alert-approval-timeout-dev"
ALERT_EXECUTION_FAILED_NAME="nsc-alert-execution-failed-dev"

required_secrets=(
  "azure-openai-api-key"
  "azure-openai-endpoint"
  "azure-openai-deployment"
  "langfuse-public-key"
  "langfuse-secret-key"
  "log-analytics-dcr-id"
  "agent-execute-mode"
  "databricks-agent-token"
)

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: $name" >&2
    exit 1
  fi
}

exists_cmd() {
  "$@" >/dev/null 2>&1
}

ensure_openai_account() {
  if exists_cmd az cognitiveservices account show -g "$RESOURCE_GROUP" -n "$OPENAI_ACCOUNT_NAME"; then
    echo "OpenAI account exists: $OPENAI_ACCOUNT_NAME"
  else
    echo "Creating OpenAI account: $OPENAI_ACCOUNT_NAME"
    az cognitiveservices account create \
      -g "$RESOURCE_GROUP" \
      -n "$OPENAI_ACCOUNT_NAME" \
      -l "$AZURE_LOCATION" \
      --kind OpenAI \
      --sku S0
  fi

  echo "Ensuring OpenAI public access is disabled"
  local openai_custom_domain
  openai_custom_domain="$(az cognitiveservices account show -g "$RESOURCE_GROUP" -n "$OPENAI_ACCOUNT_NAME" --query properties.customSubDomainName -o tsv)"
  if [[ -z "$openai_custom_domain" || "$openai_custom_domain" == "null" ]]; then
    openai_custom_domain="$OPENAI_ACCOUNT_NAME"
  fi

  echo "Ensuring OpenAI custom subdomain is set: $openai_custom_domain"
  az cognitiveservices account update \
    -g "$RESOURCE_GROUP" \
    -n "$OPENAI_ACCOUNT_NAME" \
    --custom-domain "$openai_custom_domain" >/dev/null

  local openai_id
  openai_id="$(az cognitiveservices account show -g "$RESOURCE_GROUP" -n "$OPENAI_ACCOUNT_NAME" --query id -o tsv)"
  az resource update \
    --ids "$openai_id" \
    --set properties.publicNetworkAccess=Disabled >/dev/null
}

ensure_postgres_server() {
  if exists_cmd az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$POSTGRES_SERVER_NAME"; then
    echo "PostgreSQL server exists: $POSTGRES_SERVER_NAME"
  else
    require_env "LANGFUSE_PG_ADMIN_USER"
    require_env "LANGFUSE_PG_ADMIN_PASSWORD"
    echo "Creating PostgreSQL Flexible Server: $POSTGRES_SERVER_NAME"
    az postgres flexible-server create \
      -g "$RESOURCE_GROUP" \
      -n "$POSTGRES_SERVER_NAME" \
      -l "$AZURE_LOCATION" \
      --admin-user "$LANGFUSE_PG_ADMIN_USER" \
      --admin-password "$LANGFUSE_PG_ADMIN_PASSWORD" \
      --sku-name Standard_B1ms \
      --tier Burstable \
      --version 15 \
      --public-access None
  fi

  echo "Ensuring PostgreSQL public access is disabled"
  az postgres flexible-server update \
    -g "$RESOURCE_GROUP" \
    -n "$POSTGRES_SERVER_NAME" \
    --public-access Disabled >/dev/null
}

ensure_private_dns_zone_and_link() {
  local zone_name="$1"
  local link_name="$2"
  local vnet_id

  vnet_id="$(az network vnet show -g "$RESOURCE_GROUP" -n "$VNET_NAME" --query id -o tsv)"

  if exists_cmd az network private-dns zone show -g "$RESOURCE_GROUP" -n "$zone_name"; then
    echo "Private DNS zone exists: $zone_name"
  else
    echo "Creating private DNS zone: $zone_name"
    az network private-dns zone create -g "$RESOURCE_GROUP" -n "$zone_name" >/dev/null
  fi

  if exists_cmd az network private-dns link vnet show -g "$RESOURCE_GROUP" -z "$zone_name" -n "$link_name"; then
    echo "VNet link exists: $link_name"
  else
    local existing_link_name
    existing_link_name="$(az network private-dns link vnet list -g "$RESOURCE_GROUP" -z "$zone_name" --query "[?virtualNetwork.id=='$vnet_id'].name | [0]" -o tsv)"

    if [[ -n "$existing_link_name" ]]; then
      echo "VNet link already exists for VNet $VNET_NAME in zone $zone_name: $existing_link_name"
      return
    fi

    echo "Creating VNet link: $link_name"
    az network private-dns link vnet create \
      -g "$RESOURCE_GROUP" \
      -z "$zone_name" \
      -n "$link_name" \
      -v "$vnet_id" \
      -e false >/dev/null
  fi
}

ensure_private_endpoint_with_dns() {
  local endpoint_name="$1"
  local target_resource_id="$2"
  local group_id="$3"
  local dns_zone_name="$4"

  if exists_cmd az network private-endpoint show -g "$RESOURCE_GROUP" -n "$endpoint_name"; then
    echo "Private endpoint exists: $endpoint_name"
  else
    echo "Creating private endpoint: $endpoint_name"
    az network private-endpoint create \
      -g "$RESOURCE_GROUP" \
      -n "$endpoint_name" \
      --vnet-name "$VNET_NAME" \
      --subnet "$PE_SUBNET_NAME" \
      --private-connection-resource-id "$target_resource_id" \
      --group-id "$group_id" \
      --connection-name "${endpoint_name}-conn" >/dev/null
  fi

  local dns_zone_id
  dns_zone_id="$(az network private-dns zone show -g "$RESOURCE_GROUP" -n "$dns_zone_name" --query id -o tsv)"

  if exists_cmd az network private-endpoint dns-zone-group show -g "$RESOURCE_GROUP" --endpoint-name "$endpoint_name" -n default; then
    echo "DNS zone group exists for private endpoint: $endpoint_name"
  else
    echo "Creating DNS zone group for private endpoint: $endpoint_name"
    az network private-endpoint dns-zone-group create \
      -g "$RESOURCE_GROUP" \
      --endpoint-name "$endpoint_name" \
      -n default \
      --private-dns-zone "$dns_zone_id" \
      --zone-name "$dns_zone_name" >/dev/null
  fi
}

ensure_action_group() {
  if exists_cmd az monitor action-group show -g "$RESOURCE_GROUP" -n "$ACTION_GROUP_NAME"; then
    echo "Action group exists: $ACTION_GROUP_NAME"
  else
    echo "Creating action group: $ACTION_GROUP_NAME"
    az monitor action-group create \
      -g "$RESOURCE_GROUP" \
      -n "$ACTION_GROUP_NAME" \
      --short-name "nscagdev" \
      --action email Ops "$ALERT_EMAIL" >/dev/null
  fi
}

ensure_scheduled_query_alert() {
  local rule_name="$1"
  local query="$2"
  local description="$3"
  local action_group_id="$4"
  local escaped_query

  escaped_query="${query//\"/\\\"}"

  if exists_cmd az monitor scheduled-query show -g "$RESOURCE_GROUP" -n "$rule_name"; then
    echo "Scheduled query alert exists: $rule_name"
    return
  fi

  echo "Creating scheduled query alert: $rule_name"
  az monitor scheduled-query create \
    -g "$RESOURCE_GROUP" \
    -n "$rule_name" \
    --description "$description" \
    --scopes "$LOG_ANALYTICS_WORKSPACE_ID" \
    --severity 2 \
    --evaluation-frequency 5m \
    --window-size 5m \
    --condition "count \"$escaped_query\" > 0" \
    --action-groups "$action_group_id" >/dev/null
}

verify_key_vault_secrets() {
  for secret_name in "${required_secrets[@]}"; do
    if exists_cmd az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name "$secret_name"; then
      echo "Key Vault secret exists: $secret_name"
    else
      echo "Missing required Key Vault secret: $secret_name" >&2
      exit 1
    fi
  done
}

main() {
  require_env "AZURE_LOCATION"
  require_env "KEY_VAULT_NAME"
  require_env "LOG_ANALYTICS_WORKSPACE_ID"
  require_env "ALERT_EMAIL"
  require_env "PE_SUBNET_NAME"

  ensure_openai_account
  ensure_postgres_server

  ensure_private_dns_zone_and_link "$OPENAI_PRIVATE_DNS_ZONE" "$OPENAI_DNS_LINK_NAME"
  ensure_private_dns_zone_and_link "$POSTGRES_PRIVATE_DNS_ZONE" "$POSTGRES_DNS_LINK_NAME"

  local openai_id
  local postgres_id
  openai_id="$(az cognitiveservices account show -g "$RESOURCE_GROUP" -n "$OPENAI_ACCOUNT_NAME" --query id -o tsv)"
  postgres_id="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$POSTGRES_SERVER_NAME" --query id -o tsv)"

  ensure_private_endpoint_with_dns "$OPENAI_PRIVATE_ENDPOINT_NAME" "$openai_id" "account" "$OPENAI_PRIVATE_DNS_ZONE"
  ensure_private_endpoint_with_dns "$POSTGRES_PRIVATE_ENDPOINT_NAME" "$postgres_id" "postgresqlServer" "$POSTGRES_PRIVATE_DNS_ZONE"

  verify_key_vault_secrets

  ensure_action_group
  local action_group_id
  action_group_id="$(az monitor action-group show -g "$RESOURCE_GROUP" -n "$ACTION_GROUP_NAME" --query id -o tsv)"

  ensure_scheduled_query_alert \
    "$ALERT_TRIAGE_READY_NAME" \
    "AppTraces | where Message has \"triage_ready\"" \
    "Triage-ready events detected" \
    "$action_group_id"

  ensure_scheduled_query_alert \
    "$ALERT_APPROVAL_TIMEOUT_NAME" \
    "AppTraces | where Message has \"approval_timeout\"" \
    "Approval timeout events detected" \
    "$action_group_id"

  ensure_scheduled_query_alert \
    "$ALERT_EXECUTION_FAILED_NAME" \
    "AppTraces | where Message has \"execution_failed\"" \
    "Execution-failed events detected" \
    "$action_group_id"

  echo "Done. AI agent infra (dev) is ensured."
}

main "$@"
