# Vault policy for Anumate application services

# KV v2 secrets engine for application configuration
path "secret/data/anumate/config/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/anumate/config/*" {
  capabilities = ["list", "read", "delete"]
}

# Per-tenant secrets
path "secret/data/tenants/+/config/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/tenants/+/config/*" {
  capabilities = ["list", "read", "delete"]
}

# Database credentials
path "secret/data/anumate/database/*" {
  capabilities = ["read"]
}

# Transit engine for encryption/decryption
path "transit/encrypt/anumate-*" {
  capabilities = ["update"]
}

path "transit/decrypt/anumate-*" {
  capabilities = ["update"]
}

path "transit/datakey/plaintext/anumate-*" {
  capabilities = ["update"]
}

path "transit/datakey/wrapped/anumate-*" {
  capabilities = ["update"]
}

# Per-tenant encryption keys
path "transit/encrypt/tenant-*" {
  capabilities = ["update"]
}

path "transit/decrypt/tenant-*" {
  capabilities = ["update"]
}

# PKI for certificate management
path "pki/issue/anumate-role" {
  capabilities = ["update"]
}

path "pki/cert/ca" {
  capabilities = ["read"]
}

# Auth methods
path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/revoke-self" {
  capabilities = ["update"]
}

# System capabilities for health checks
path "sys/health" {
  capabilities = ["read", "sudo"]
}

path "sys/capabilities-self" {
  capabilities = ["update"]
}