# HashiCorp Vault Configuration for Anumate Secrets Management

# Storage backend
storage "file" {
  path = "/vault/data"
}

# Listener configuration
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1  # Disable TLS for development (enable in production)
}

# API address
api_addr = "http://0.0.0.0:8200"

# Cluster address (for HA setup)
cluster_addr = "http://0.0.0.0:8201"

# UI configuration
ui = true

# Logging
log_level = "INFO"
log_format = "json"

# Disable mlock for development (enable in production)
disable_mlock = true

# Plugin directory
plugin_directory = "/vault/plugins"

# Default lease TTL and max lease TTL
default_lease_ttl = "768h"
max_lease_ttl = "8760h"

# Entropy augmentation (for production)
# entropy "seal" {
#   mode = "augmentation"
# }

# Auto-unseal configuration (for production with cloud KMS)
# seal "awskms" {
#   region     = "us-east-1"
#   kms_key_id = "alias/vault-unseal-key"
# }

# Telemetry configuration
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname = true
  
  # StatsD configuration
  # statsd_address = "localhost:8125"
  
  # Circonus configuration
  # circonus_api_token = ""
  # circonus_api_app = "vault"
  # circonus_api_url = "https://api.circonus.com/v2"
  # circonus_submission_interval = "10s"
  # circonus_submission_url = ""
  # circonus_check_id = ""
  # circonus_check_force_metric_activation = "false"
  # circonus_check_instance_id = ""
  # circonus_check_search_tag = ""
  # circonus_check_display_name = ""
  # circonus_check_tags = ""
  # circonus_broker_id = ""
  # circonus_broker_select_tag = ""
}

# Performance configuration
# raw_storage_endpoint = true
# introspection_endpoint = true
# unauthenticated_metrics_access = false