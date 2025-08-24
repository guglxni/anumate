# Orchestrator Service

The Orchestrator service manages ExecutablePlan execution via Portia Runtime integration.

## 🏆 Hackathon Production Mode

**This build runs SDK-only with fallback disabled by design for WeMakeDevs AgentHack 2025.**

- ✅ **SDK-Only**: Only Portia SDK v0.7.2 is used - no HTTP fallback in dev/stage/prod
- ✅ **Fail-Fast**: Missing/invalid credentials cause immediate startup failure
- ✅ **Production-Grade**: Real API keys required, no dummy defaults allowed
- ✅ **Strict Validation**: Environment constraints enforced at startup

### Quick Start (Hackathon)

```bash
# SHOULD FAIL (no SDK installed)
export ANUMATE_ENV=dev
export PORTIA_BASE_URL="https://api.portia.sh" 
export PORTIA_API_KEY="your-real-api-key"
uvicorn services.orchestrator.api.main:app --port 8090

# SHOULD START (when SDK installed)
pip install portia-sdk-python
uvicorn services.orchestrator.api.main:app --port 8090 --reload
curl -sS http://localhost:8090/readyz  # expect {"portia":"ready",...}
```

### Environment Configuration

| Variable | Required | Values | Notes |
|----------|----------|---------|-------|
| `ANUMATE_ENV` | Yes | `dev`\|`stage`\|`prod`\|`test` | Controls SDK enforcement |
| `PORTIA_MODE` | Yes | `sdk`\|`http` | Must be `sdk` in dev/stage/prod |
| `PORTIA_API_KEY` | Yes | Real API key | No dummy defaults |
| `PORTIA_BASE_URL` | Yes | Real Portia URL | Always required |
| `ALLOW_PORTIA_HTTP_FALLBACK` | No | `true`\|`false` | Only `true` in test env |

### Guardrails

1. **SDK-Only Enforcement**: `PORTIA_MODE=http` fails in dev/stage/prod
2. **Missing SDK**: Import failure crashes app with installation guidance
3. **Missing Credentials**: Startup fails with clear error messages
4. **HTTP Fallback**: Only allowed in test environment with explicit flag
5. **Readiness Probe**: `/readyz` includes `"portia":"ready"` only when SDK working

## Razorpay MCP Integration

The Orchestrator service supports Razorpay's hosted Remote MCP server for payment operations via Portia SDK.

### Configuration

#### Remote MCP Mode (Recommended)

```bash
# Enable Razorpay MCP
ENABLE_RAZORPAY_MCP=true
RAZORPAY_MCP_MODE=remote
RAZORPAY_MCP_URL=https://mcp.razorpay.com/mcp

# Base64 encode your Razorpay credentials: base64(key_id:key_secret)
RAZORPAY_MCP_AUTH=Bearer cnpwX3Rlc3RfWW91cktleUlkOllvdXJLZXlTZWNyZXQ=
```

#### stdio Mode (Local)

```bash
ENABLE_RAZORPAY_MCP=true
RAZORPAY_MCP_MODE=stdio
RAZORPAY_KEY_ID=rzp_test_R9CtqNaKq7Oav8
RAZORPAY_KEY_SECRET=7AmZf4QxAyn1ueeOfS3VhVQz
```

### MCP Engines

#### Payment Link Creation

```bash
curl -X POST http://localhost:8090/v1/execute/portia \
  -H "Content-Type: application/json" \
  -d '{
    "plan_hash": "payment_link_demo_001",
    "engine": "razorpay_mcp_payment_link",
    "require_approval": true,
    "razorpay": {
      "amount": 1000,
      "currency": "INR",
      "description": "Demo payment link",
      "customer": {
        "name": "Judge",
        "email": "judge@example.com"
      }
    }
  }'
```

Expected response:
```json
{
  "plan_run_id": "run_12345",
  "status": "SUCCEEDED", 
  "receipt_id": "rcpt_67890",
  "mcp": {
    "tool": "razorpay.payment_links.create",
    "id": "plink_test_abc123",
    "short_url": "https://rzp.io/i/xyz789",
    "status": "created"
  },
  "approvals_count": 1,
  "duration_seconds": 5.2
}
```

#### Refund Creation

```bash
curl -X POST http://localhost:8090/v1/execute/portia \
  -H "Content-Type: application/json" \
  -d '{
    "plan_hash": "refund_demo_002", 
    "engine": "razorpay_mcp_refund",
    "require_approval": true,
    "razorpay": {
      "payment_id": "pay_test_123456",
      "amount": 500,
      "speed": "optimum"
    }
  }'
```

Expected response:
```json
{
  "plan_run_id": "run_67890",
  "status": "SUCCEEDED",
  "receipt_id": "rcpt_13579", 
  "mcp": {
    "tool": "razorpay.refunds.create",
    "id": "rfnd_test_def456",
    "status": "processed"
  },
  "approvals_count": 1,
  "duration_seconds": 3.8
}
```

### MCP Features

- **Hosted Remote MCP**: Uses Razorpay's official `https://mcp.razorpay.com/mcp` server
- **SDK Integration**: MCP tools registered with Portia SDK via `McpToolRegistry`
- **Approval Flow**: Human-in-loop approvals before payment operations
- **Receipt Generation**: WORM receipts with MCP execution details
- **Error Handling**: Graceful fallback to default tools if MCP unavailable
- **Security**: HMAC signature verification for webhook events

### Available MCP Tools

When MCP is enabled, the following Razorpay tools are available:

- `razorpay.payment_links.create` - Create payment links
- `razorpay.payment_links.get` - Retrieve payment link details  
- `razorpay.refunds.create` - Process refunds
- `razorpay.refunds.get` - Retrieve refund details
- `razorpay.payments.get` - Get payment information
- `razorpay.orders.create` - Create orders
- `razorpay.orders.get` - Retrieve order details

### stdio Mode Setup

For local MCP server development:

```bash
# Install Razorpay MCP server globally
npm install -g @razorpay/mcp-server

# Test MCP tools directly
npx @razorpay/mcp-server \
  --api-key-id rzp_test_R9CtqNaKq7Oav8 \
  --api-key-secret 7AmZf4QxAyn1ueeOfS3VhVQz
```

### Test Credentials

```bash
# Test API keys provided for hackathon
RAZORPAY_KEY_ID=rzp_test_R9CtqNaKq7Oav8
RAZORPAY_KEY_SECRET=7AmZf4QxAyn1ueeOfS3VhVQz

# Base64 encoded for MCP auth
RAZORPAY_MCP_AUTH=Bearer cnpwX3Rlc3RfUjlDdHFOYUtxN09hdjg6N0FtWmY0UXhBeW4xdWVlT2ZTM1ZoVlF6
```

## Razorpay Webhook Integration

### Setup Public HTTPS Tunnel

For Razorpay webhooks to reach your local development server, you need a public HTTPS URL:

#### Option A: ngrok (Recommended)

```bash
# Install ngrok (macOS)
brew install ngrok

# Sign up at https://ngrok.com and get your authtoken
ngrok config add-authtoken YOUR_NGROK_AUTHTOKEN

# Start your orchestrator service
cd services/orchestrator
python start_production.py

# In another terminal, create public tunnel
ngrok http 8090
```

You'll see output like:
```
Forwarding    https://abcd-1234.ngrok-free.app -> http://localhost:8090
```

#### Configure Razorpay Dashboard

1. Go to Razorpay Dashboard → Settings → Webhooks
2. Create new webhook with:
   - **URL**: `https://abcd-1234.ngrok-free.app/integrations/razorpay/webhook`
   - **Events**: Select `payment.link.paid`, `refund.processed`, etc.
   - **Secret**: Generate a secure secret (e.g., `whsec_abc123...`)
3. Save the webhook

#### Update Environment Variables

```bash
# Add to .env
ENABLE_RAZORPAY=true
RAZORPAY_KEY_ID=rzp_test_YOUR_KEY_ID
RAZORPAY_KEY_SECRET=your-secret-key
RAZORPAY_WEBHOOK_SECRET=whsec_your-webhook-secret
```

#### Test Webhook

```bash
# Check webhook health
curl https://abcd-1234.ngrok-free.app/integrations/razorpay/webhook/health

# Send test webhook from Razorpay dashboard
# Check orchestrator logs for: "✅ Received Razorpay webhook: payment.link.paid"
```

### Alternative: Cloudflare Tunnel

```bash
# Install cloudflared
brew install cloudflared

# Authenticate
cloudflared tunnel login

# Create tunnel
cloudflared tunnel --url http://localhost:8090
```

Use the provided `trycloudflare.com` URL in Razorpay dashboard.

## Responsibilities

- Portia Runtime integration (SDK-only for hackathon)
- Execution monitoring and hooks
- Retry logic and idempotency
- Capability token validation
- Razorpay webhook processing