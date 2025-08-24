# Anumate Platform MVP

A comprehensive microservices platform for policy automation, capability management, and secure receipt genera   - **Portia Cloud**: `ptk_LIVE_17294723472394731827431724372317...` ✅ **Real API Key**
   - **Moonshot Kimi LLM**: `sk-E7MvG...CqjL` ✅ **Real API Key**on with tamper-evident cryptographic guarantees.

## 🏆 **JUDGE MODE - WeMakeDevs AgentHack 2025**

**Quick Start for Judges:**
```bash
# 1. One-command setup and demo
make judge

# 2. Or manual Razorpay MCP demo
cd services/orchestrator
./demo.sh

# 3. Test specific payment creation
curl -sS -X POST http://localhost:8090/v1/execute/portia \
  -H 'Content-Type: application/json' \
  -d '{
    "plan_hash": "judge-demo",
    "engine": "razorpay_mcp_payment_link",
    "require_approval": false,
    "razorpay": {
      "amount": 10000,
      "currency": "INR",
      "description": "Judge Demo ₹100",
      "customer": {"name": "Judge", "email": "judge@wemakedevs.org"}
    }
  }' | jq .
```

**Expected Output:**
```json
{
  "plan_run_id": "run_1756066296",
  "status": "SUCCEEDED", 
  "receipt_id": "receipt_1756066296",
  "mcp": {
    "tool": "razorpay.payment_links.create",
    "id": "plink_10000_1756066296",
    "short_url": "https://rzp.io/...",
    "status": "created",
    "live_execution": true
  }
}
```

**Key Features Demonstrated:**
- ✅ **Real Razorpay MCP Integration** - Live API calls via `https://mcp.razorpay.com/mcp`
- ✅ **Portia SDK v0.7.2** - Production-grade execution runtime
- ✅ **MCP Protocol v2025-03-26** - Latest protocol negotiation
- ✅ **Idempotency Safety** - Duplicate prevention with `Idempotency-Key` header
- ✅ **Signed Receipts** - Tamper-evident execution records
- ✅ **Fallback Resilience** - Graceful degradation on errors

**Judge Documentation:**
- 📋 [`JUDGE_MODE.md`](services/orchestrator/JUDGE_MODE.md) - Copy/paste ready commands
- 🚀 [`PRODUCTION_READY.md`](services/orchestrator/PRODUCTION_READY.md) - Technical summary
- 🧪 [`test_razorpay_mcp.py`](services/orchestrator/tests/test_razorpay_mcp.py) - Comprehensive tests

---

## 🚀 Overview

The Anumate Platform MVP provides enterprise-grade microservices for:

- **Policy Automation**: Advanced policy compilation and enforcement
- **Capability Tokens**: Secure, time-bound authorization tokens
- **Receipt Generation**: Tamper-evident receipts with Ed25519 digital signatures
- **Multi-tenant Architecture**: Complete tenant isolation with Row-Level Security (RLS)
- **WORM Storage Integration**: Immutable storage for compliance requirements
- **Comprehensive Audit Logging**: Full audit trails for regulatory compliance

## 🏗️ Architecture

### Microservices
- **Policy Service** (`services/policy/`) - Policy compilation and evaluation
- **CapTokens Service** (`services/captokens/`) - Capability token management
- **Receipt Service** (`services/receipt/`) - Tamper-evident receipt generation
- **Orchestrator Service** (`services/orchestrator/`) - Workflow orchestration
- **Registry Service** (`services/registry/`) - Service discovery and configuration

### Shared Packages
- **anumate-capability-tokens** - Core capability token library
- **anumate-errors** - Standardized error handling
- **anumate-core-config** - Configuration management
- **anumate-crypto** - Cryptographic utilities
- **anumate-events** - Event streaming and messaging
- **anumate-logging** - Structured logging
- **anumate-tracing** - Distributed tracing
- **anumate-http** - HTTP utilities and middleware

### Infrastructure
- **PostgreSQL** - Primary database with multi-tenant support
- **NATS** - Event streaming and message queuing
- **Redis** - Caching and session storage
- **Vault** - Secrets management
- **Docker** - Containerized deployment
- **Kubernetes** - Container orchestration

## 🔐 Security Features

### Cryptographic Security
- **Ed25519 Digital Signatures** - Enterprise-grade cryptographic signing
- **SHA-256 Content Hashing** - Tamper detection and verification
- **JWT Token Security** - Secure capability token implementation
- **Multi-tenant Isolation** - Row-Level Security (RLS) policies

### Compliance & Audit
- **WORM Storage Integration** - Write-Once-Read-Many storage for compliance
- **Comprehensive Audit Trails** - Full activity logging for regulatory requirements
- **SIEM Export Capabilities** - Security Information and Event Management integration
- **Retention Policy Management** - Automated data lifecycle management

## 🚦 Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL 14+

### Judge Mode (90 seconds) 🏆

**For WeMakeDevs AgentHack 2025 judges - complete production-grade end-to-end demo:**

#### Prerequisites
1. **Environment Setup**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual production API keys
   ```

2. **Required API Keys** (no mocks - production only):
   - **Portia API Key**: `prt-o4EmiQBe...L0` ✅ **Real API Key**
   - **Moonshot Kimi LLM**: `sk-E7MvG...CqjL` ✅ **Real API Key**
   - **OpenAI Base URL**: `https://api.moonshot.cn/v1` (OpenAI-compatible protocol)

#### Production Demo Commands
```bash
# 1. Start production-grade core services
make up-core

# 2. Run real Portia SDK demo (no mocks!)
make demo
```

#### Production Workflow You'll See:
1. **Real API Validation**: Validates production Portia and Moonshot API keys
2. **Capsule Submission**: Submits real payment refund capsule to orchestrator
3. **Portia SDK Integration**: Uses genuine Portia SDK v0.7.2 with cloud endpoint
4. **Approval Workflow**: Production approvals service (human-in-loop step)
5. **LLM Processing**: Real Moonshot Kimi model processes the execution
6. **Receipt Generation**: Ed25519-signed tamper-evident receipt created
7. **WORM Storage**: Immutable storage with cryptographic integrity

#### Expected Production Output:
```
🚀 PRODUCTION PORTIA DEMO - WeMakeDevs AgentHack 2025
============================================================
🏢 Tenant: demo
💰 Amount: 1000 paise (INR)
📋 Capsule: demo_refund
🔗 Orchestrator: http://localhost:8090
🔑 Using real Portia API key: prt-o4EmiQBe...

✅ Execution submitted to production Portia!
PlanRun: plan_run_abc123def456

⏳ Waiting for approval...
   (Real human approval step - production approvals service)

🏁 PRODUCTION DEMO SUCCESS!
✅ status=SUCCEEDED receipt_id=receipt_xyz789 worm_uri=worm://immutable/receipt_xyz789.json
```

#### Production Verification:
```bash
# Check all services are healthy
make accept

# Verify orchestrator readiness with real API keys
curl -s localhost:8090/readyz | jq .
```

#### Production Features Demonstrated:
- ✅ **Real Portia SDK**: No mocks, genuine API integration
- ✅ **Production LLM**: Moonshot Kimi via OpenAI-compatible protocol  
- ✅ **Cryptographic Receipts**: Ed25519 digital signatures
- ✅ **Tamper-Evident Storage**: WORM compliance with integrity verification
- ✅ **Multi-tenant Architecture**: Production-grade tenant isolation
- ✅ **Fail-Fast Validation**: No dummy defaults, real credentials required

**Total time: ~60-90 seconds for complete production workflow**

---

### Quick Start

1. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd anumate
   ```

2. **Start Infrastructure**
   ```bash
   docker-compose -f ops/docker-compose.infrastructure.yml up -d
   ```

3. **Install Dependencies**
   ```bash
   # Install Python packages
   pip install -e packages/anumate-*
   
   # Install service dependencies
   cd services/captokens && pip install -r requirements.txt
   cd ../receipt && pip install -r requirements.txt
   ```

4. **Start Services**
   ```bash
   # CapTokens Service
   cd services/captokens
   python -m uvicorn src.anumate_captokens_service.app_production:app --port 8083
   
   # Receipt Service  
   cd services/receipt/src
   RECEIPT_SIGNING_KEY="<base64-encoded-key>" uvicorn anumate_receipt_service.app_production:app --port 8001
   ```

### API Endpoints

#### CapTokens Service (Port 8083)
- `POST /v1/captokens` - Create capability token
- `GET /v1/captokens/{token_id}` - Get token details
- `POST /v1/captokens/{token_id}/verify` - Verify token
- `POST /v1/captokens/{token_id}/revoke` - Revoke token

#### Receipt Service (Port 8001)
- `POST /v1/receipts` - Create tamper-evident receipt
- `GET /v1/receipts/{receipt_id}` - Get receipt details
- `POST /v1/receipts/{receipt_id}/verify` - Verify receipt integrity
- `GET /v1/receipts/audit` - Export audit logs
- `POST /v1/receipts/{receipt_id}/worm` - Store in WORM storage

## 🧪 Testing

### Example: Create a Capability Token
```bash
curl -X POST http://localhost:8083/v1/captokens \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: 12345678-1234-1234-1234-123456789012" \
  -d '{
    "subject": "user123",
    "capabilities": ["read", "write"],
    "ttl_seconds": 3600
  }'
```

### Example: Create a Receipt
```bash
curl -X POST http://localhost:8001/v1/receipts \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
  -d '{
    "receipt_type": "approval",
    "subject": "Document approval receipt",
    "receipt_data": {
      "decision": "approved",
      "reason": "meets all criteria"
    }
  }'
```

## 📁 Project Structure

```
anumate/
├── docs/                          # Documentation
├── ops/                          # Operations & Infrastructure
│   ├── docker-compose.yml        # Service orchestration
│   ├── kubernetes/               # K8s manifests
│   ├── terraform/               # Infrastructure as Code
│   └── helm/                    # Helm charts
├── packages/                     # Shared Python packages
│   ├── anumate-capability-tokens/
│   ├── anumate-errors/
│   ├── anumate-core-config/
│   └── ...
├── services/                     # Microservices
│   ├── captokens/               # Capability token service
│   ├── receipt/                 # Receipt generation service
│   ├── policy/                  # Policy automation service
│   └── ...
└── schemas/                      # API schemas & validation
```

## 🛠️ Development

### Adding a New Service
1. Create service directory in `services/`
2. Set up FastAPI application with standard structure
3. Implement database models with multi-tenant support
4. Add API endpoints with proper validation
5. Include comprehensive error handling
6. Add audit logging for all operations

### Database Migrations
Database schema management is handled through direct SQL execution and SQLAlchemy models. Each service manages its own database schema.

### Multi-tenant Development
All services implement Row-Level Security (RLS) for tenant isolation:
- All database tables include `tenant_id` column
- RLS policies enforce tenant access controls
- API endpoints validate tenant headers

## 📊 Monitoring & Observability

### Health Checks
- Service health endpoints at `/health`
- Database connectivity monitoring
- Storage system health validation

### Logging
- Structured JSON logging
- Distributed tracing support
- Audit event logging for compliance

### Metrics
- Performance metrics collection
- Business metrics tracking
- Infrastructure monitoring

## 🔧 Configuration

Configuration is managed through:
- Environment variables for runtime config
- `anumate-core-config` package for shared settings
- Service-specific configuration files

### Required Environment Variables
```bash
# Receipt Service
RECEIPT_SIGNING_KEY=<base64-encoded-ed25519-private-key>

# Database
DATABASE_URL=postgresql://user:pass@localhost/anumate

# Infrastructure
NATS_URL=nats://localhost:4222
REDIS_URL=redis://localhost:6379
VAULT_URL=http://localhost:8200
```

## 🚀 Deployment

### Docker Deployment
```bash
docker-compose up -d
```

### Kubernetes Deployment
```bash
kubectl apply -f ops/kubernetes/
```

### Helm Deployment
```bash
helm install anumate ops/helm/anumate-platform/
```

## 📋 Implementation Status

- ✅ **A.22** - Capability Token Service (Complete)
- ✅ **A.23** - Multi-tenant Infrastructure (Complete) 
- ✅ **A.24** - Capability Enforcement (Complete)
- ✅ **A.25** - Receipt Service with Ed25519 signatures (Complete)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with comprehensive tests
4. Submit a pull request

## 📜 License

This project is proprietary software. All rights reserved.

## 🔗 Links

- [API Documentation](http://localhost:8001/docs)
- [Architecture Decision Records](docs/)
- [Deployment Guide](ops/README.md)
- [Development Guide](docs/DEVELOPMENT.md)
