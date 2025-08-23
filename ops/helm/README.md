# Helm Charts

Helm charts for deploying the Anumate platform with configurable values.

## Structure

- `anumate-platform/` - Main platform chart
- `charts/` - Dependency charts
- `values/` - Environment-specific values files

## Usage

```bash
# Install with default values
helm install anumate ./anumate-platform

# Install with custom values
helm install anumate ./anumate-platform -f values/production.yaml

# Upgrade
helm upgrade anumate ./anumate-platform
```