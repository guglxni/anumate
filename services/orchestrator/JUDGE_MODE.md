# 🎯 Judge Mode - WeMakeDevs AgentHack 2025

## Quick Demo Commands (Copy/Paste Ready)

### 1. Service Readiness Check
```bash
curl -s localhost:8090/readyz | jq .
```
**Expected Output:**
```json
{
  "ready": true,
  "service": "orchestrator-api", 
  "version": "0.1.0",
  "services": {
    "portia": "ready",
    "openai": "ready",
    "approvals_service": "configured"
  }
}
```

### 2. Create Payment Link via Razorpay MCP (₹10.00)
```bash
curl -sS -X POST http://localhost:8090/v1/execute/portia \
  -H 'Content-Type: application/json' \
  -d '{
    "plan_hash": "judge-demo-1",
    "engine": "razorpay_mcp_payment_link",
    "require_approval": false,
    "razorpay": {
      "amount": 1000,
      "currency": "INR", 
      "description": "Judge demo payment",
      "customer": {
        "name": "WeMakeDevs Judge",
        "email": "judge@wemakedevs.org"
      }
    }
  }' | jq .
```

**Expected Output Fields:**
- ✅ `status`: "SUCCEEDED"
- ✅ `receipt_id`: "receipt_run_xxxxx"  
- ✅ `plan_run_id`: "run_xxxxx"
- ✅ `mcp.short_url`: Payment link URL
- ✅ `mcp.live_execution`: true (not demo mode)

### 3. Idempotency Test (Same Request Twice)
```bash
# Set idempotency key
IDK=key-$(date +%s)

# First execution
curl -sS -X POST http://localhost:8090/v1/execute/portia \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $IDK" \
  -d '{
    "plan_hash": "idem-test", 
    "engine": "razorpay_mcp_payment_link",
    "require_approval": false,
    "razorpay": {
      "amount": 1500,
      "currency": "INR",
      "description": "Idempotency demo"
    }
  }' | jq .

# Second execution (same idempotency key) - should return identical result
curl -sS -X POST http://localhost:8090/v1/execute/portia \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $IDK" \
  -d '{
    "plan_hash": "idem-test",
    "engine": "razorpay_mcp_payment_link", 
    "require_approval": false,
    "razorpay": {
      "amount": 1500,
      "currency": "INR",
      "description": "Idempotency demo"
    }
  }' | jq .
```

**Expected Behavior:**
- ✅ Both calls return **identical** `receipt_id` and `plan_run_id`
- ✅ Second call logs: "Returning cached idempotent result"
- ✅ No duplicate payment link created

### 4. Create Refund via Razorpay MCP
```bash
curl -sS -X POST http://localhost:8090/v1/execute/portia \
  -H 'Content-Type: application/json' \
  -d '{
    "plan_hash": "judge-refund-1",
    "engine": "razorpay_mcp_refund",
    "require_approval": false,
    "razorpay": {
      "payment_id": "pay_judge_demo_12345",
      "amount": 500,
      "speed": "optimum"
    }
  }' | jq .
```

---

## 🎬 **Demo Script (30-40 seconds)**

**"Preview → Approve → Execute → Receipt is our contract."**

1. **"Portia runs the plan; Razorpay MCP is the tool. Here's a payment link generated safely."**
   - Show payment link creation with live MCP execution

2. **"We bind execution to the preview via plan-hash, and produce a signed receipt."**
   - Highlight `plan_hash` → `receipt_id` → tamper-evidence

3. **"Repeat with the same Idempotency-Key: no double action."**
   - Demonstrate idempotency preventing duplicate operations

**Key Callouts:**
- ✅ **Live MCP Integration**: `live_execution: true`
- ✅ **Receipt Generation**: Every execution produces signed receipt
- ✅ **Idempotency Safety**: Prevents accidental duplicate payments
- ✅ **Plan Hash Binding**: Deterministic execution tied to plan content

---

## 🏗️ **Architecture Highlights**

### Core Integration Stack
```
FastAPI Orchestrator → Portia SDK v0.7.2 → Razorpay Remote MCP
                    ↓
               Moonshot Kimi LLM (OpenAI-compatible)
                    ↓
           Signed Receipts + Idempotency Cache
```

### MCP Protocol Flow
1. **Tool Discovery**: `mcp.client.streamable_http:Negotiated protocol version: 2025-03-26`
2. **Tool Execution**: `razorpay.payment_links.create` via https://mcp.razorpay.com/mcp
3. **Response Binding**: Results tied to `plan_hash` for auditability
4. **Receipt Generation**: Cryptographically signed execution record

### Safety Features
- ✅ **Idempotency Keys**: Prevent duplicate operations
- ✅ **Plan Hash Binding**: Deterministic execution 
- ✅ **Live MCP Execution**: Real Razorpay API integration
- ✅ **Fallback Handling**: Graceful degradation on MCP failures
- ✅ **Secret Redaction**: All API keys/tokens masked in logs

---

## 🔍 **Verification Commands**

### Check Service Health
```bash
curl -s localhost:8090/health | jq .
```

### Inspect Logs (Security Check)
```bash
# Verify no secrets in logs
tail -20 orchestrator.log | grep -E "(Bearer|prt-|rzp_)" || echo "✅ No secrets leaked"
```

### Environment Validation
```bash
# Check .env is present and gitignored
test -f .env && echo "✅ .env exists"
git check-ignore .env && echo "✅ .env gitignored"
```

---

## 🚀 **Expected Demo Outcome**

**Success Criteria:**
- ✅ Payment links created via live Razorpay MCP
- ✅ Signed receipts generated for every operation
- ✅ Idempotency prevents duplicate operations
- ✅ MCP protocol negotiation successful
- ✅ All secrets properly redacted from logs

**Judge Validation Points:**
1. **Live API Integration**: Real Razorpay MCP responses (not demo stubs)
2. **Safety & Governance**: Idempotency + receipt generation working  
3. **Protocol Compliance**: MCP 2025-03-26 negotiated successfully
4. **Production Readiness**: Proper error handling, logging, security
