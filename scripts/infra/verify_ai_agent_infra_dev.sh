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

LANGFUSE_NAMESPACE="${LANGFUSE_NAMESPACE:-default}"
LANGFUSE_SECRET_NAME="${LANGFUSE_SECRET_NAME:-langfuse-secrets}"

PRIVATE_ENDPOINT_DNS_ZONE_GROUP_NAME="default"

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

required_langfuse_k8s_secret_keys=(
  "langfuse-public-key"
  "langfuse-secret-key"
  "database-url"
  "azure-openai-api-key"
  "azure-openai-endpoint"
  "azure-openai-deployment"
)

failures=0

pass() {
  printf 'PASS: %s\n' "$1"
}

fail() {
  printf 'FAIL: %s\n' "$1"
  failures=$((failures + 1))
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    printf 'Missing required environment variable: %s\n' "$name" >&2
    exit 1
  fi
}

require_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "command available: $cmd"
  else
    printf 'Missing required command: %s\n' "$cmd" >&2
    exit 1
  fi
}

check_resource_exists() {
  local description="$1"
  shift

  local output
  output="$("$@" 2>/dev/null || true)"

  if [[ -n "$output" && "$output" != "{}" && "$output" != "[]" ]]; then
    pass "$description"
  else
    fail "$description"
  fi
}

check_value_equals() {
  local description="$1"
  local expected="$2"
  local actual="$3"

  if [[ "$actual" == "$expected" ]]; then
    pass "$description"
  else
    fail "$description (expected: $expected, actual: ${actual:-<empty>})"
  fi
}

check_value_not_equals() {
  local description="$1"
  local disallowed="$2"
  local actual="$3"

  if [[ "$actual" != "$disallowed" && -n "$actual" ]]; then
    pass "$description"
  else
    fail "$description (disallowed: $disallowed, actual: ${actual:-<empty>})"
  fi
}

main() {
  require_env "KEY_VAULT_NAME"

  require_cmd "az"
  require_cmd "kubectl"

  check_resource_exists \
    "OpenAI account exists ($OPENAI_ACCOUNT_NAME)" \
    az cognitiveservices account show -g "$RESOURCE_GROUP" -n "$OPENAI_ACCOUNT_NAME"

  local openai_public_network_access
  openai_public_network_access="$(az cognitiveservices account show -g "$RESOURCE_GROUP" -n "$OPENAI_ACCOUNT_NAME" --query properties.publicNetworkAccess -o tsv 2>/dev/null || true)"
  check_value_equals \
    "OpenAI public network access is disabled" \
    "Disabled" \
    "$openai_public_network_access"

  check_resource_exists \
    "PostgreSQL Flexible Server exists ($POSTGRES_SERVER_NAME)" \
    az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$POSTGRES_SERVER_NAME"

  local postgres_public_access
  postgres_public_access="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$POSTGRES_SERVER_NAME" --query network.publicNetworkAccess -o tsv 2>/dev/null || true)"
  check_value_equals \
    "PostgreSQL public access is disabled" \
    "Disabled" \
    "$postgres_public_access"

  check_resource_exists \
    "OpenAI private endpoint exists ($OPENAI_PRIVATE_ENDPOINT_NAME)" \
    az network private-endpoint show -g "$RESOURCE_GROUP" -n "$OPENAI_PRIVATE_ENDPOINT_NAME"

  check_resource_exists \
    "PostgreSQL private endpoint exists ($POSTGRES_PRIVATE_ENDPOINT_NAME)" \
    az network private-endpoint show -g "$RESOURCE_GROUP" -n "$POSTGRES_PRIVATE_ENDPOINT_NAME"

  check_resource_exists \
    "OpenAI private endpoint DNS zone group exists ($PRIVATE_ENDPOINT_DNS_ZONE_GROUP_NAME)" \
    az network private-endpoint dns-zone-group show -g "$RESOURCE_GROUP" --endpoint-name "$OPENAI_PRIVATE_ENDPOINT_NAME" -n "$PRIVATE_ENDPOINT_DNS_ZONE_GROUP_NAME"

  check_resource_exists \
    "PostgreSQL private endpoint DNS zone group exists ($PRIVATE_ENDPOINT_DNS_ZONE_GROUP_NAME)" \
    az network private-endpoint dns-zone-group show -g "$RESOURCE_GROUP" --endpoint-name "$POSTGRES_PRIVATE_ENDPOINT_NAME" -n "$PRIVATE_ENDPOINT_DNS_ZONE_GROUP_NAME"

  check_resource_exists \
    "OpenAI private DNS zone exists ($OPENAI_PRIVATE_DNS_ZONE)" \
    az network private-dns zone show -g "$RESOURCE_GROUP" -n "$OPENAI_PRIVATE_DNS_ZONE"

  check_resource_exists \
    "PostgreSQL private DNS zone exists ($POSTGRES_PRIVATE_DNS_ZONE)" \
    az network private-dns zone show -g "$RESOURCE_GROUP" -n "$POSTGRES_PRIVATE_DNS_ZONE"

  local openai_private_dns_zone_id
  openai_private_dns_zone_id="$(az network private-dns zone show -g "$RESOURCE_GROUP" -n "$OPENAI_PRIVATE_DNS_ZONE" --query id -o tsv 2>/dev/null || true)"
  check_value_not_equals \
    "OpenAI private DNS zone resolved to an ID" \
    "" \
    "$openai_private_dns_zone_id"

  local postgres_private_dns_zone_id
  postgres_private_dns_zone_id="$(az network private-dns zone show -g "$RESOURCE_GROUP" -n "$POSTGRES_PRIVATE_DNS_ZONE" --query id -o tsv 2>/dev/null || true)"
  check_value_not_equals \
    "PostgreSQL private DNS zone resolved to an ID" \
    "" \
    "$postgres_private_dns_zone_id"

  local openai_zone_group_has_expected_zone_id
  openai_zone_group_has_expected_zone_id="$(az network private-endpoint dns-zone-group show -g "$RESOURCE_GROUP" --endpoint-name "$OPENAI_PRIVATE_ENDPOINT_NAME" -n "$PRIVATE_ENDPOINT_DNS_ZONE_GROUP_NAME" --query "contains(privateDnsZoneConfigs[].privateDnsZoneId, '$openai_private_dns_zone_id')" -o tsv 2>/dev/null || true)"
  check_value_equals \
    "OpenAI private endpoint zone group includes expected DNS zone ID" \
    "true" \
    "$openai_zone_group_has_expected_zone_id"

  local openai_zone_group_has_expected_zone_name
  openai_zone_group_has_expected_zone_name="$(az network private-endpoint dns-zone-group show -g "$RESOURCE_GROUP" --endpoint-name "$OPENAI_PRIVATE_ENDPOINT_NAME" -n "$PRIVATE_ENDPOINT_DNS_ZONE_GROUP_NAME" --query "contains(privateDnsZoneConfigs[].name, '$OPENAI_PRIVATE_DNS_ZONE')" -o tsv 2>/dev/null || true)"
  check_value_equals \
    "OpenAI private endpoint zone group includes expected DNS zone name" \
    "true" \
    "$openai_zone_group_has_expected_zone_name"

  local postgres_zone_group_has_expected_zone_id
  postgres_zone_group_has_expected_zone_id="$(az network private-endpoint dns-zone-group show -g "$RESOURCE_GROUP" --endpoint-name "$POSTGRES_PRIVATE_ENDPOINT_NAME" -n "$PRIVATE_ENDPOINT_DNS_ZONE_GROUP_NAME" --query "contains(privateDnsZoneConfigs[].privateDnsZoneId, '$postgres_private_dns_zone_id')" -o tsv 2>/dev/null || true)"
  check_value_equals \
    "PostgreSQL private endpoint zone group includes expected DNS zone ID" \
    "true" \
    "$postgres_zone_group_has_expected_zone_id"

  local postgres_zone_group_has_expected_zone_name
  postgres_zone_group_has_expected_zone_name="$(az network private-endpoint dns-zone-group show -g "$RESOURCE_GROUP" --endpoint-name "$POSTGRES_PRIVATE_ENDPOINT_NAME" -n "$PRIVATE_ENDPOINT_DNS_ZONE_GROUP_NAME" --query "contains(privateDnsZoneConfigs[].name, '$POSTGRES_PRIVATE_DNS_ZONE')" -o tsv 2>/dev/null || true)"
  check_value_equals \
    "PostgreSQL private endpoint zone group includes expected DNS zone name" \
    "true" \
    "$postgres_zone_group_has_expected_zone_name"

  local expected_vnet_id
  expected_vnet_id="$(az network vnet show -g "$RESOURCE_GROUP" -n "$VNET_NAME" --query id -o tsv 2>/dev/null || true)"
  if [[ -n "$expected_vnet_id" ]]; then
    local openai_dns_link_name
    openai_dns_link_name="$(az network private-dns link vnet list -g "$RESOURCE_GROUP" -z "$OPENAI_PRIVATE_DNS_ZONE" --query "[?virtualNetwork.id=='$expected_vnet_id'].name | [0]" -o tsv 2>/dev/null || true)"
    check_value_not_equals \
      "OpenAI DNS zone has VNet link to expected VNet ($VNET_NAME)" \
      "" \
      "$openai_dns_link_name"

    local postgres_dns_link_name
    postgres_dns_link_name="$(az network private-dns link vnet list -g "$RESOURCE_GROUP" -z "$POSTGRES_PRIVATE_DNS_ZONE" --query "[?virtualNetwork.id=='$expected_vnet_id'].name | [0]" -o tsv 2>/dev/null || true)"
    check_value_not_equals \
      "PostgreSQL DNS zone has VNet link to expected VNet ($VNET_NAME)" \
      "" \
      "$postgres_dns_link_name"

    local openai_dns_link_vnet
    openai_dns_link_vnet="$(az network private-dns link vnet show -g "$RESOURCE_GROUP" -z "$OPENAI_PRIVATE_DNS_ZONE" -n "$openai_dns_link_name" --query virtualNetwork.id -o tsv 2>/dev/null || true)"
    check_value_equals \
      "OpenAI DNS link points to expected VNet ($VNET_NAME)" \
      "$expected_vnet_id" \
      "$openai_dns_link_vnet"

    local postgres_dns_link_vnet
    postgres_dns_link_vnet="$(az network private-dns link vnet show -g "$RESOURCE_GROUP" -z "$POSTGRES_PRIVATE_DNS_ZONE" -n "$postgres_dns_link_name" --query virtualNetwork.id -o tsv 2>/dev/null || true)"
    check_value_equals \
      "PostgreSQL DNS link points to expected VNet ($VNET_NAME)" \
      "$expected_vnet_id" \
      "$postgres_dns_link_vnet"
  else
    fail "Expected VNet exists ($VNET_NAME)"
  fi

  check_resource_exists \
    "Action group exists ($ACTION_GROUP_NAME)" \
    az monitor action-group show -g "$RESOURCE_GROUP" -n "$ACTION_GROUP_NAME"

  check_resource_exists \
    "Scheduled query alert exists ($ALERT_TRIAGE_READY_NAME)" \
    az resource show -g "$RESOURCE_GROUP" --resource-type "Microsoft.Insights/scheduledQueryRules" -n "$ALERT_TRIAGE_READY_NAME"

  check_resource_exists \
    "Scheduled query alert exists ($ALERT_APPROVAL_TIMEOUT_NAME)" \
    az resource show -g "$RESOURCE_GROUP" --resource-type "Microsoft.Insights/scheduledQueryRules" -n "$ALERT_APPROVAL_TIMEOUT_NAME"

  check_resource_exists \
    "Scheduled query alert exists ($ALERT_EXECUTION_FAILED_NAME)" \
    az resource show -g "$RESOURCE_GROUP" --resource-type "Microsoft.Insights/scheduledQueryRules" -n "$ALERT_EXECUTION_FAILED_NAME"

  local kv_probe_error
  kv_probe_error="$(az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name "azure-openai-api-key" --query id -o tsv 2>&1 >/dev/null || true)"
  if [[ "$kv_probe_error" == *"ForbiddenByConnection"* ]]; then
    fail "Key Vault private access is not reachable from current network context (ForbiddenByConnection)"
  else
    local secret_name
    for secret_name in "${required_secrets[@]}"; do
      check_resource_exists \
        "Key Vault secret exists ($secret_name)" \
        az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name "$secret_name"
    done
  fi

  if kubectl cluster-info >/dev/null 2>&1; then
    check_resource_exists \
      "LangFuse deployment rollout is ready in AKS namespace ${LANGFUSE_NAMESPACE} (langfuse)" \
      kubectl rollout status deployment/langfuse -n "$LANGFUSE_NAMESPACE" --timeout=120s

    check_resource_exists \
      "LangFuse internal service exists in AKS namespace ${LANGFUSE_NAMESPACE} (langfuse-internal)" \
      kubectl get service langfuse-internal -n "$LANGFUSE_NAMESPACE"

    local langfuse_service_type
    langfuse_service_type="$(kubectl get service langfuse-internal -n "$LANGFUSE_NAMESPACE" -o jsonpath='{.spec.type}' 2>/dev/null || true)"
    check_value_equals \
      "LangFuse internal service type is ClusterIP" \
      "ClusterIP" \
      "$langfuse_service_type"

    local langfuse_service_lb_ingress
    langfuse_service_lb_ingress="$(kubectl get service langfuse-internal -n "$LANGFUSE_NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress}' 2>/dev/null || true)"
    check_value_equals \
      "LangFuse internal service has no LoadBalancer ingress" \
      "" \
      "$langfuse_service_lb_ingress"

    local langfuse_ingress_resources
    langfuse_ingress_resources="$(kubectl get ingress -n "$LANGFUSE_NAMESPACE" -l app=langfuse -o name 2>/dev/null || true)"
    check_value_equals \
      "No Ingress resources expose LangFuse in namespace ${LANGFUSE_NAMESPACE}" \
      "" \
      "$langfuse_ingress_resources"

    check_resource_exists \
      "LangFuse runtime Secret exists in AKS namespace ${LANGFUSE_NAMESPACE} (${LANGFUSE_SECRET_NAME})" \
      kubectl get secret "$LANGFUSE_SECRET_NAME" -n "$LANGFUSE_NAMESPACE"

    local secret_key
    for secret_key in "${required_langfuse_k8s_secret_keys[@]}"; do
      local secret_value
      secret_value="$(kubectl get secret "$LANGFUSE_SECRET_NAME" -n "$LANGFUSE_NAMESPACE" -o "jsonpath={.data['$secret_key']}" 2>/dev/null || true)"
      check_value_not_equals \
        "LangFuse runtime Secret key exists (${LANGFUSE_SECRET_NAME}:$secret_key)" \
        "" \
        "$secret_value"
    done
  else
    fail "AKS API is not reachable from current network context"
  fi

  if (( failures > 0 )); then
    printf 'Verification completed with %d failure(s).\n' "$failures"
    exit 1
  fi

  echo "Verification completed with 0 failures."
}

main "$@"
