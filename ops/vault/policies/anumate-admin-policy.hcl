# Vault policy for Anumate administrators

# Full access to application secrets
path "secret/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Transit engine management
path "transit/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# PKI management
path "pki/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Auth method management
path "auth/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Policy management
path "sys/policies/acl/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Mount management
path "sys/mounts/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Audit management
path "sys/audit/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# System configuration
path "sys/config/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Health and metrics
path "sys/health" {
  capabilities = ["read", "sudo"]
}

path "sys/metrics" {
  capabilities = ["read"]
}

# Seal/unseal operations
path "sys/seal" {
  capabilities = ["update", "sudo"]
}

path "sys/unseal" {
  capabilities = ["update", "sudo"]
}

# Key management
path "sys/key-status" {
  capabilities = ["read", "sudo"]
}

path "sys/rotate" {
  capabilities = ["update", "sudo"]
}

# Token management
path "auth/token/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}