# Portia SDK Configuration Guide

## Production-Grade Setup for WeMakeDevs AgentHack 2025

This document outlines the required configuration for production-grade Portia SDK integration.

## Required Environment Variables

### Essential Configuration

```bash
# Portia API Key (Required)
# Get from: https://app.portia.ai/settings/api-keys
# Format: pk_live_... or sk_live_...
export PORTIA_API_KEY="pk_live_your_actual_api_key_here"

# Portia Workspace (Required)
# Find in: https://app.portia.ai/settings/workspace
# Format: workspace UUID
export PORTIA_WORKSPACE="12345678-1234-1234-1234-123456789012"

# Portia Base URL (Optional - defaults to official API)
export PORTIA_BASE_URL="https://api.portia.ai"
```

### Development vs Production

```bash
# Development Environment
export PORTIA_API_KEY="pk_dev_your_dev_api_key"
export PORTIA_WORKSPACE="dev-workspace-uuid"

# Production Environment  
export PORTIA_API_KEY="pk_live_your_prod_api_key"
export PORTIA_WORKSPACE="prod-workspace-uuid"
```

## Configuration Validation

The `PortiaSDKClient` validates configuration at startup:

1. **API Key Validation**: 
   - Must be provided via `PORTIA_API_KEY` environment variable
   - Should start with `pk_` or `sk_`
   - No dummy keys allowed in production

2. **Workspace Validation**:
   - Must be provided via `PORTIA_WORKSPACE` environment variable
   - Should be a valid workspace UUID

3. **Connection Testing**:
   - Health check performed on initialization
   - Validates API key and workspace access

## Error Messages

### Missing API Key
```
PortiaConfigurationError: PORTIA_API_KEY environment variable must be set for production use.
Get your API key from https://app.portia.ai/settings/api-keys
```

### Missing Workspace
```
PortiaConfigurationError: PORTIA_WORKSPACE environment variable must be set for production use.
Find your workspace ID in https://app.portia.ai/settings/workspace
```

### Invalid API Key Format
```
WARNING: API key does not match expected format (pk_* or sk_*).
Please verify your PORTIA_API_KEY is correct.
```

## Setting Up for WeMakeDevs AgentHack 2025

1. **Create Portia Account**: Visit https://app.portia.ai
2. **Generate API Key**: Go to Settings → API Keys → Create New Key
3. **Get Workspace ID**: Go to Settings → Workspace → Copy Workspace ID
4. **Set Environment Variables**:
   ```bash
   echo 'export PORTIA_API_KEY="your_actual_key"' >> ~/.zshrc
   echo 'export PORTIA_WORKSPACE="your_workspace_id"' >> ~/.zshrc
   source ~/.zshrc
   ```

## Testing Configuration

```python
# Test configuration
from services.orchestrator.src.portia_sdk_client import PortiaSDKClient

async def test_portia_config():
    try:
        async with PortiaSDKClient() as client:
            health = await client.health_check()
            print(f"✅ Portia SDK configured correctly: {health}")
    except Exception as e:
        print(f"❌ Configuration error: {e}")
```

## Security Best Practices

1. **Never commit API keys to git**
2. **Use different keys for dev/staging/prod**
3. **Rotate keys regularly**
4. **Use environment-specific workspaces**
5. **Monitor API key usage**

## Troubleshooting

### Common Issues

1. **"Configuration error" on startup**:
   - Check environment variables are set: `echo $PORTIA_API_KEY`
   - Verify API key format
   - Test network connectivity to Portia API

2. **"Health check failed"**:
   - Verify API key is active
   - Check workspace permissions
   - Test with minimal request first

3. **Import errors**:
   - Ensure `portia-sdk-python` is installed
   - Check Python path includes orchestrator service

### Getting Help

1. **Portia Documentation**: https://docs.portia.ai
2. **API Reference**: https://api.portia.ai/docs
3. **Support**: support@portia.ai

## Production Deployment Checklist

- [ ] PORTIA_API_KEY set with production key
- [ ] PORTIA_WORKSPACE set with production workspace
- [ ] API key permissions verified
- [ ] Health check passes
- [ ] Error monitoring configured
- [ ] Key rotation schedule established
