#!/usr/bin/env bash
# One-time infrastructure setup for SwarmIQ on Azure Container Apps.
# Prerequisites: az CLI installed and logged in (az login), Docker available.
# Edit the REPLACE_ME values before running.
set -euo pipefail

RESOURCE_GROUP="swarmiq-rg"
LOCATION="eastus"
ACR_NAME="swarmiqlacr"
KV_NAME="swarmiq-kv"
ENVIRONMENT="swarmiq-env"
APP_NAME="swarmiq-app"
IMAGE="${ACR_NAME}.azurecr.io/swarmiq:latest"

# ── Resource Group ─────────────────────────────────────────────────────────────
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

# ── Azure Container Registry ───────────────────────────────────────────────────
az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled false

# ── Azure Key Vault ────────────────────────────────────────────────────────────
az keyvault create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$KV_NAME" \
  --location "$LOCATION" \
  --enable-rbac-authorization true

KV_ID=$(az keyvault show --name "$KV_NAME" --query id -o tsv)
KV_URI="https://${KV_NAME}.vault.azure.net"

# Assign yourself Secrets Officer so you can populate secrets
MY_OID=$(az ad signed-in-user show --query id -o tsv)
az role assignment create \
  --role "Key Vault Secrets Officer" \
  --assignee "$MY_OID" \
  --scope "$KV_ID"

# Store application secrets — fill in real values before running
az keyvault secret set --vault-name "$KV_NAME" --name "azure-openai-endpoint"        --value "https://REPLACE_ME.openai.azure.com/"
az keyvault secret set --vault-name "$KV_NAME" --name "azure-openai-api-key"         --value "REPLACE_ME"
az keyvault secret set --vault-name "$KV_NAME" --name "azure-openai-deployment"      --value "gpt-4o"
az keyvault secret set --vault-name "$KV_NAME" --name "azure-openai-api-version"     --value "2024-02-01"
az keyvault secret set --vault-name "$KV_NAME" --name "tavily-api-key"               --value "REPLACE_ME"
az keyvault secret set --vault-name "$KV_NAME" --name "redis-url"                    --value "redis://localhost:6379"
az keyvault secret set --vault-name "$KV_NAME" --name "azure-ad-tenant-id"           --value "REPLACE_ME"
az keyvault secret set --vault-name "$KV_NAME" --name "azure-ad-client-id"           --value "REPLACE_ME"
az keyvault secret set --vault-name "$KV_NAME" --name "azure-ad-client-secret"       --value "REPLACE_ME"
az keyvault secret set --vault-name "$KV_NAME" --name "cosmos-db-connection-string"  --value "REPLACE_ME"
az keyvault secret set --vault-name "$KV_NAME" --name "cosmos-db-database-name"      --value "swarmiq"

# ── Container Apps Environment ─────────────────────────────────────────────────
az containerapp env create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ENVIRONMENT" \
  --location "$LOCATION"

# ── Container App (initial deployment) ────────────────────────────────────────
az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --image "$IMAGE" \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --min-replicas 1 \
  --max-replicas 5 \
  --cpu 1.0 \
  --memory 2Gi \
  --target-port 8000 \
  --ingress external \
  --system-assigned

# ── Grant Container App managed identity access to Key Vault secrets ───────────
PRINCIPAL_ID=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "identity.principalId" -o tsv)

az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee "$PRINCIPAL_ID" \
  --scope "$KV_ID"

# ── Grant Container App managed identity ACR pull access ──────────────────────
ACR_ID=$(az acr show --name "$ACR_NAME" --query id -o tsv)
az role assignment create \
  --role "AcrPull" \
  --assignee "$PRINCIPAL_ID" \
  --scope "$ACR_ID"

# ── Wire Container App secrets to Key Vault references ────────────────────────
az containerapp secret set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --secrets \
    "azure-openai-endpoint=keyvaultref:${KV_URI}/secrets/azure-openai-endpoint,identityref:system" \
    "azure-openai-api-key=keyvaultref:${KV_URI}/secrets/azure-openai-api-key,identityref:system" \
    "azure-openai-deployment=keyvaultref:${KV_URI}/secrets/azure-openai-deployment,identityref:system" \
    "azure-openai-api-version=keyvaultref:${KV_URI}/secrets/azure-openai-api-version,identityref:system" \
    "tavily-api-key=keyvaultref:${KV_URI}/secrets/tavily-api-key,identityref:system" \
    "redis-url=keyvaultref:${KV_URI}/secrets/redis-url,identityref:system" \
    "azure-ad-tenant-id=keyvaultref:${KV_URI}/secrets/azure-ad-tenant-id,identityref:system" \
    "azure-ad-client-id=keyvaultref:${KV_URI}/secrets/azure-ad-client-id,identityref:system" \
    "azure-ad-client-secret=keyvaultref:${KV_URI}/secrets/azure-ad-client-secret,identityref:system" \
    "cosmos-db-connection-string=keyvaultref:${KV_URI}/secrets/cosmos-db-connection-string,identityref:system" \
    "cosmos-db-database-name=keyvaultref:${KV_URI}/secrets/cosmos-db-database-name,identityref:system"

# ── Map Container App secrets to environment variables ────────────────────────
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --set-env-vars \
    "AZURE_OPENAI_ENDPOINT=secretref:azure-openai-endpoint" \
    "AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key" \
    "AZURE_OPENAI_DEPLOYMENT_NAME=secretref:azure-openai-deployment" \
    "AZURE_OPENAI_API_VERSION=secretref:azure-openai-api-version" \
    "TAVILY_API_KEY=secretref:tavily-api-key" \
    "REDIS_URL=secretref:redis-url" \
    "AZURE_AD_TENANT_ID=secretref:azure-ad-tenant-id" \
    "AZURE_AD_CLIENT_ID=secretref:azure-ad-client-id" \
    "AZURE_AD_CLIENT_SECRET=secretref:azure-ad-client-secret" \
    "COSMOS_DB_CONNECTION_STRING=secretref:cosmos-db-connection-string" \
    "COSMOS_DB_DATABASE_NAME=secretref:cosmos-db-database-name"

# ── Done ───────────────────────────────────────────────────────────────────────
APP_URL=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "Infrastructure setup complete."
echo "App URL: https://${APP_URL}"
echo ""
echo "Next steps:"
echo "  1. Add AZURE_CREDENTIALS to your GitHub repository secrets."
echo "     Generate with: az ad sp create-for-rbac --name swarmiq-deploy --role contributor \\"
echo "                      --scopes /subscriptions/<SUB_ID>/resourceGroups/${RESOURCE_GROUP} --sdk-auth"
echo "  2. Push to main — the GitHub Actions workflow will build and deploy automatically."
