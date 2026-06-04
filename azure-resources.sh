#!/usr/bin/env bash
# One-time infrastructure setup for SwarmIQ on Azure Container Apps.
#
# Prerequisites:
#   - az CLI installed and logged in (az login)
#   - Docker available
#   - A local .env file with the secrets below (gitignored), OR be ready to type
#     them at the prompts
#
# Required env vars (script will read from .env automatically, or prompt for
# anything missing):
#   LLM_API_KEY                 — GitHub PAT (models:read scope) OR Azure OpenAI key
#   TAVILY_API_KEY              — Tavily search API key
#
# Optional env vars (script falls back to defaults if unset):
#   LLM_BASE_URL                — default: https://models.github.ai/inference
#   LLM_MODEL                   — default: openai/gpt-4o-mini
#   AZURE_AD_TENANT_ID          — default: ""  (auth disabled if blank)
#   AZURE_AD_CLIENT_ID          — default: ""
#   AZURE_AD_CLIENT_SECRET      — default: ""
#   COSMOS_DB_CONNECTION_STRING — default: ""  (history disabled if blank)
#   COSMOS_DB_DATABASE_NAME     — default: swarmiq
#   LOCATION                    — default: eastus  (use centralindia for student sub)
#   RESOURCE_GROUP              — default: swarmiq-rg
#   ACR_NAME                    — default: swarmiqlacr
#   KV_NAME                     — default: swarmiq-kv
#   ENVIRONMENT                 — default: swarmiq-env
#   APP_NAME                    — default: swarmiq-app
#
# Usage:
#   bash azure-resources.sh

set -euo pipefail

# ── Load local .env (gitignored) ──────────────────────────────────────────────
if [ -f .env ]; then
  echo "Loading secrets from .env"
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Accept GITHUB_TOKEN as an alias for LLM_API_KEY (matches the runtime fallback in tools.py)
if [ -z "${LLM_API_KEY:-}" ] && [ -n "${GITHUB_TOKEN:-}" ]; then
  LLM_API_KEY="$GITHUB_TOKEN"
fi

# ── Interactive prompt for anything still missing ─────────────────────────────
prompt_secret() {
  local var_name="$1"
  local prompt_label="$2"
  if [ -z "${!var_name:-}" ]; then
    echo ""
    read -rsp "Enter ${prompt_label}: " value
    echo ""
    if [ -z "$value" ]; then
      echo "ERROR: ${var_name} is required." >&2
      exit 1
    fi
    export "${var_name}=${value}"
  fi
}

prompt_secret LLM_API_KEY    "LLM_API_KEY (GitHub PAT with models:read scope)"
prompt_secret TAVILY_API_KEY "TAVILY_API_KEY"

# ── Defaults for everything else ──────────────────────────────────────────────
LLM_BASE_URL="${LLM_BASE_URL:-https://models.github.ai/inference}"
LLM_MODEL="${LLM_MODEL:-openai/gpt-4o-mini}"

AZURE_AD_TENANT_ID="${AZURE_AD_TENANT_ID:-}"
AZURE_AD_CLIENT_ID="${AZURE_AD_CLIENT_ID:-}"
AZURE_AD_CLIENT_SECRET="${AZURE_AD_CLIENT_SECRET:-}"
COSMOS_DB_CONNECTION_STRING="${COSMOS_DB_CONNECTION_STRING:-}"
COSMOS_DB_DATABASE_NAME="${COSMOS_DB_DATABASE_NAME:-swarmiq}"

MAIL_ID="${MAIL_ID:-}"
MAIL_APP_PASSWORD="${MAIL_APP_PASSWORD:-}"
MAIL_FROM_NAME="${MAIL_FROM_NAME:-SwarmIQ}"

LOCATION="${LOCATION:-eastus}"
RESOURCE_GROUP="${RESOURCE_GROUP:-swarmiq-rg}"
ACR_NAME="${ACR_NAME:-swarmiqlacr}"
KV_NAME="${KV_NAME:-swarmiq-kv}"
ENVIRONMENT="${ENVIRONMENT:-swarmiq-env}"
APP_NAME="${APP_NAME:-swarmiq-app}"
IMAGE="${ACR_NAME}.azurecr.io/swarmiq:latest"

echo ""
echo "Provisioning with:"
echo "  RESOURCE_GROUP = $RESOURCE_GROUP"
echo "  LOCATION       = $LOCATION"
echo "  ACR_NAME       = $ACR_NAME"
echo "  KV_NAME        = $KV_NAME"
echo "  APP_NAME       = $APP_NAME"
echo ""

# ── Resource Group ─────────────────────────────────────────────────────────────
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

# ── Azure Container Registry ───────────────────────────────────────────────────
if az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "ACR $ACR_NAME already exists — skipping create"
else
  az acr create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" \
    --sku Basic \
    --admin-enabled false
fi

# ── Azure Key Vault ────────────────────────────────────────────────────────────
if az keyvault show --name "$KV_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "Key Vault $KV_NAME already exists — skipping create"
else
  az keyvault create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$KV_NAME" \
    --location "$LOCATION" \
    --enable-rbac-authorization true
fi

KV_ID=$(az keyvault show --name "$KV_NAME" --query id -o tsv)
KV_URI="https://${KV_NAME}.vault.azure.net"

# Assign yourself Secrets Officer so you can populate secrets (idempotent)
MY_OID=$(az ad signed-in-user show --query id -o tsv)
az role assignment create \
  --role "Key Vault Secrets Officer" \
  --assignee "$MY_OID" \
  --scope "$KV_ID" 2>&1 | grep -v "RoleAssignmentExists" || true

# Wait a moment for RBAC propagation
sleep 15

# ── Store application secrets ─────────────────────────────────────────────────
# Values come from env vars (loaded from .env or prompted above).
# Nothing sensitive is hardcoded in this script.

az keyvault secret set --vault-name "$KV_NAME" --name "llm-base-url"                --value "$LLM_BASE_URL"          --output none
az keyvault secret set --vault-name "$KV_NAME" --name "llm-api-key"                 --value "$LLM_API_KEY"           --output none
az keyvault secret set --vault-name "$KV_NAME" --name "llm-model"                   --value "$LLM_MODEL"             --output none
az keyvault secret set --vault-name "$KV_NAME" --name "tavily-api-key"              --value "$TAVILY_API_KEY"        --output none
az keyvault secret set --vault-name "$KV_NAME" --name "redis-url"                   --value "redis://localhost:6379" --output none
az keyvault secret set --vault-name "$KV_NAME" --name "azure-ad-tenant-id"          --value "${AZURE_AD_TENANT_ID:-disabled}"          --output none
az keyvault secret set --vault-name "$KV_NAME" --name "azure-ad-client-id"          --value "${AZURE_AD_CLIENT_ID:-disabled}"          --output none
az keyvault secret set --vault-name "$KV_NAME" --name "azure-ad-client-secret"      --value "${AZURE_AD_CLIENT_SECRET:-disabled}"      --output none
az keyvault secret set --vault-name "$KV_NAME" --name "cosmos-db-connection-string" --value "${COSMOS_DB_CONNECTION_STRING:-disabled}" --output none
az keyvault secret set --vault-name "$KV_NAME" --name "cosmos-db-database-name"     --value "$COSMOS_DB_DATABASE_NAME"                 --output none
az keyvault secret set --vault-name "$KV_NAME" --name "mail-id"                     --value "${MAIL_ID:-disabled}"                     --output none
az keyvault secret set --vault-name "$KV_NAME" --name "mail-app-password"           --value "${MAIL_APP_PASSWORD:-disabled}"           --output none
az keyvault secret set --vault-name "$KV_NAME" --name "mail-from-name"              --value "$MAIL_FROM_NAME"                          --output none

echo "Secrets written to Key Vault: $KV_NAME"

# ── Container Apps Environment ─────────────────────────────────────────────────
if az containerapp env show --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "Container Apps Environment $ENVIRONMENT already exists — skipping create"
else
  az containerapp env create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ENVIRONMENT" \
    --location "$LOCATION"
fi

# ── Container App (initial deployment with placeholder image) ─────────────────
# We use mcr.microsoft.com/azuredocs/containerapps-helloworld:latest as a placeholder
# because the real image hasn't been pushed yet. GitHub Actions will replace it on
# first deploy.
if az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "Container App $APP_NAME already exists — skipping create"
else
  az containerapp create \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT" \
    --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
    --min-replicas 1 \
    --max-replicas 5 \
    --cpu 1.0 \
    --memory 2Gi \
    --target-port 8000 \
    --ingress external \
    --system-assigned
fi

# ── Grant Container App managed identity access to Key Vault secrets ───────────
PRINCIPAL_ID=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "identity.principalId" -o tsv)

az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee "$PRINCIPAL_ID" \
  --scope "$KV_ID" 2>&1 | grep -v "RoleAssignmentExists" || true

# ── Grant Container App managed identity ACR pull access ──────────────────────
ACR_ID=$(az acr show --name "$ACR_NAME" --query id -o tsv)
az role assignment create \
  --role "AcrPull" \
  --assignee "$PRINCIPAL_ID" \
  --scope "$ACR_ID" 2>&1 | grep -v "RoleAssignmentExists" || true

# Wait for RBAC propagation before wiring KV refs (otherwise secret resolution fails)
sleep 30

# ── Configure Container App to use managed identity for ACR pulls ─────────────
az containerapp registry set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --server "${ACR_NAME}.azurecr.io" \
  --identity system

# ── Wire Container App secrets to Key Vault references ────────────────────────
az containerapp secret set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --secrets \
    "llm-base-url=keyvaultref:${KV_URI}/secrets/llm-base-url,identityref:system" \
    "llm-api-key=keyvaultref:${KV_URI}/secrets/llm-api-key,identityref:system" \
    "llm-model=keyvaultref:${KV_URI}/secrets/llm-model,identityref:system" \
    "tavily-api-key=keyvaultref:${KV_URI}/secrets/tavily-api-key,identityref:system" \
    "redis-url=keyvaultref:${KV_URI}/secrets/redis-url,identityref:system" \
    "azure-ad-tenant-id=keyvaultref:${KV_URI}/secrets/azure-ad-tenant-id,identityref:system" \
    "azure-ad-client-id=keyvaultref:${KV_URI}/secrets/azure-ad-client-id,identityref:system" \
    "azure-ad-client-secret=keyvaultref:${KV_URI}/secrets/azure-ad-client-secret,identityref:system" \
    "cosmos-db-connection-string=keyvaultref:${KV_URI}/secrets/cosmos-db-connection-string,identityref:system" \
    "cosmos-db-database-name=keyvaultref:${KV_URI}/secrets/cosmos-db-database-name,identityref:system" \
    "mail-id=keyvaultref:${KV_URI}/secrets/mail-id,identityref:system" \
    "mail-app-password=keyvaultref:${KV_URI}/secrets/mail-app-password,identityref:system" \
    "mail-from-name=keyvaultref:${KV_URI}/secrets/mail-from-name,identityref:system"

# ── Map Container App secrets to environment variables ────────────────────────
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --set-env-vars \
    "LLM_BASE_URL=secretref:llm-base-url" \
    "LLM_API_KEY=secretref:llm-api-key" \
    "LLM_MODEL=secretref:llm-model" \
    "TAVILY_API_KEY=secretref:tavily-api-key" \
    "REDIS_URL=secretref:redis-url" \
    "AZURE_AD_TENANT_ID=secretref:azure-ad-tenant-id" \
    "AZURE_AD_CLIENT_ID=secretref:azure-ad-client-id" \
    "AZURE_AD_CLIENT_SECRET=secretref:azure-ad-client-secret" \
    "COSMOS_DB_CONNECTION_STRING=secretref:cosmos-db-connection-string" \
    "COSMOS_DB_DATABASE_NAME=secretref:cosmos-db-database-name" \
    "MAIL_ID=secretref:mail-id" \
    "MAIL_APP_PASSWORD=secretref:mail-app-password" \
    "MAIL_FROM_NAME=secretref:mail-from-name"

# ── Done ───────────────────────────────────────────────────────────────────────
APP_URL=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "Infrastructure setup complete."
echo "App URL (placeholder image right now): https://${APP_URL}"
echo ""
echo "Next steps:"
echo "  1. Create the GitHub Actions service principal:"
echo "       az ad sp create-for-rbac --name swarmiq-deploy --role contributor \\"
echo "         --scopes /subscriptions/<SUB_ID>/resourceGroups/${RESOURCE_GROUP} --sdk-auth"
echo "  2. Paste the JSON output as 'AZURE_CREDENTIALS' in:"
echo "       GitHub repo → Settings → Secrets and variables → Actions"
echo "  3. Push to main (or re-run the failed workflow) — Actions will build, push to ACR,"
echo "     and update the Container App with the real image."
