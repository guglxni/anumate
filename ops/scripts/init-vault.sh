#!/bin/bash
# Initialize HashiCorp Vault for Anumate

set -e

# Configuration
VAULT_ADDR=${VAULT_ADDR:-"http://localhost:8200"}
VAULT_TOKEN=${VAULT_ROOT_TOKEN:-"dev-root-token"}

echo "Initializing Vault for Anumate..."

# Wait for Vault to be ready
echo "Waiting for Vault to be ready..."
until curl -s "$VAULT_ADDR/v1/sys/health" > /dev/null 2>&1; do
    echo "Waiting for Vault..."
    sleep 2
done

# Set Vault address and token
export VAULT_ADDR
export VAULT_TOKEN

# Enable audit logging
echo "Enabling audit logging..."
vault audit enable file file_path=/vault/logs/audit.log || true

# Enable KV v2 secrets engine
echo "Enabling KV v2 secrets engine..."
vault secrets enable -path=secret kv-v2 || true

# Enable Transit secrets engine for encryption
echo "Enabling Transit secrets engine..."
vault secrets enable transit || true

# Enable PKI secrets engine for certificates
echo "Enabling PKI secrets engine..."
vault secrets enable pki || true

# Configure PKI
echo "Configuring PKI..."
vault secrets tune -max-lease-ttl=87600h pki || true
vault write pki/root/generate/internal \
    common_name="Anumate Internal CA" \
    ttl=87600h || true

vault write pki/config/urls \
    issuing_certificates="$VAULT_ADDR/v1/pki/ca" \
    crl_distribution_points="$VAULT_ADDR/v1/pki/crl" || true

vault write pki/roles/anumate-role \
    allowed_domains="anumate.local,localhost" \
    allow_subdomains=true \
    max_ttl=72h || true

# Create encryption keys
echo "Creating encryption keys..."
vault write -f transit/keys/anumate-master || true
vault write -f transit/keys/anumate-database || true
vault write -f transit/keys/anumate-config || true

# Create policies
echo "Creating Vault policies..."
vault policy write anumate-app /vault/policies/anumate-app-policy.hcl || true
vault policy write anumate-admin /vault/policies/anumate-admin-policy.hcl || true

# Enable Kubernetes auth method (for production)
echo "Enabling Kubernetes auth method..."
vault auth enable kubernetes || true

# Create application secrets
echo "Creating application secrets..."
vault kv put secret/anumate/config/database \
    host="postgres" \
    port="5432" \
    database="anumate" \
    username="anumate_app" \
    password="app_password" || true

vault kv put secret/anumate/config/redis \
    host="redis" \
    port="6379" \
    password="" || true

vault kv put secret/anumate/config/nats \
    host="nats" \
    port="4222" \
    username="anumate_app" \
    password="app_password" || true

vault kv put secret/anumate/config/jwt \
    secret_key="$(openssl rand -base64 32)" \
    algorithm="HS256" \
    expiry="3600" || true

# Create application token
echo "Creating application token..."
APP_TOKEN=$(vault write -field=token auth/token/create \
    policies="anumate-app" \
    ttl="24h" \
    renewable=true)

echo "Application token: $APP_TOKEN"
echo "Store this token securely for application use"

# Create sample tenant encryption key
echo "Creating sample tenant encryption key..."
vault write -f transit/keys/tenant-00000000-0000-0000-0000-000000000001 || true

echo "Vault initialization complete!"
echo "Vault UI available at: $VAULT_ADDR/ui"
echo "Root token: $VAULT_TOKEN"