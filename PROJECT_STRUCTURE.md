# Anumate Platform Project Structure

This document describes the organized microservices project structure for the Anumate automation platform.

> **📁 For detailed architecture and organization, see [`ARCHITECTURE.md`](ARCHITECTURE.md)**

## 🗂️ Current Organization (Post-Cleanup)

```
anumate/
├── README.md                   # Main project documentation  
├── ARCHITECTURE.md             # Detailed architecture overview
├── Makefile                    # Build and development commands
├── pyproject.toml             # Python project configuration
├── requirements.txt           # Python dependencies
│
├── 📂 services/               # Microservices
│   ├── orchestrator/          # Main orchestration service (FastAPI)
│   ├── approvals/             # Human-in-the-loop approvals
│   ├── captokens/             # Capability tokens management
│   ├── receipt/               # Receipt generation & validation
│   ├── registry/              # Capsule registry
│   ├── policy/                # Policy engine
│   └── ...                    # Other services
│
├── 📂 packages/               # Shared Python packages
│   ├── anumate-core-config/   # Core configuration utilities
│   ├── anumate-crypto/        # Cryptographic functions
│   ├── anumate-events/        # Event handling
│   └── ...                    # Other shared packages
│
├── 📂 ops/                    # Operations & infrastructure
│   ├── docker-compose.yml     # Local development stack
│   ├── kubernetes/            # K8s manifests
│   ├── helm/                  # Helm charts
│   └── terraform/             # Infrastructure as code
│
├── 📂 schemas/                # Data schemas & validation
│   ├── events/                # Event schemas
│   ├── models/                # Data models
│   └── openapi/               # API specifications
│
├── 📂 docs/                   # Documentation
├── 📂 scripts/                # Utility scripts
├── 📂 tests/                  # Global test suite
│
├── 📂 archive/                # Archived & legacy content ✨ NEW
│   ├── implementation-reports/# Historical implementation docs
│   └── legacy-tests/          # Deprecated test files
│
├── 📂 build/                  # Build artifacts ✨ NEW
│   ├── dist/                  # Distribution packages  
│   └── repomix-output.xml     # Repomix submission package
│
└── 📂 logs/                   # Application logs ✨ NEW
    ├── service.log            # Main service logs
    └── receipt_service.log    # Receipt service logs
```

## 🧹 Cleanup Summary

### Files Moved to Archive:
- `A22_IMPLEMENTATION_SUMMARY.md` → `archive/implementation-reports/`
- `A23_IMPLEMENTATION_SUMMARY.md` → `archive/implementation-reports/`  
- `A26_IMPLEMENTATION_REPORT.md` → `archive/implementation-reports/`
- `PORTIA_SDK_MIGRATION_COMPLETE.md` → `archive/implementation-reports/`
- `PRODUCTION_AUDIT.md` → `archive/implementation-reports/`
- `SHARED_UTILITIES_IMPLEMENTATION.md` → `archive/implementation-reports/`
- `CHATGPT_TROUBLESHOOTING_PROMPT.md` → `archive/`

### Files Moved to Archive/Legacy Tests:
- `test_a22_simple.py` → `archive/legacy-tests/`
- `test_a23_api.py` → `archive/legacy-tests/`
- `test_a23_service.py` → `archive/legacy-tests/`
- `test_a26_endpoints.py` → `archive/legacy-tests/`
- `test_individual_modules.py` → `archive/legacy-tests/`
- `test_new_utilities.py` → `archive/legacy-tests/`
- `test_shared_utilities.py` → `archive/legacy-tests/`
- `debug_token.py` → `archive/legacy-tests/`

### Files Moved to Build:
- `repomix-output.xml` → `build/`
- `dist/` → `build/dist/`

### Files Moved to Logs:
- `receipt_service.log` → `logs/`
- `service.log` → `logs/`

## 🎯 Benefits

1. **Cleaner Root**: Essential files only at repository root
2. **Logical Organization**: Files grouped by purpose and lifecycle
3. **Historical Preservation**: Implementation reports archived but accessible
4. **Better Navigation**: Clear separation of active vs legacy content
5. **Judge-Friendly**: Clean structure for WeMakeDevs AgentHack 2025 evaluation

## 🚀 Quick Commands

```bash
# Core development
make up-core                   # Start services
make demo                      # Run production demo
make demo-razorpay-link       # Razorpay MCP demo
make accept                   # Run acceptance tests

# Build & submission
make evidence                 # Capture evidence
repomix                       # Generate submission (outputs to build/)
```
│   ├── anumate-core-config/
│   ├── anumate-crypto/
│   ├── anumate-errors/
│   ├── anumate-events/
│   ├── anumate-http/
│   ├── anumate-idempotency/
│   ├── anumate-logging/
│   ├── anumate-oidc/
│   ├── anumate-planhash/
│   ├── anumate-policy/
│   ├── anumate-receipt/
│   ├── anumate-redaction/
│   ├── anumate-tenancy/
│   └── anumate-tracing/
├── schemas/                    # Shared schemas and contracts
│   ├── openapi/                # OpenAPI specifications
│   ├── events/                 # CloudEvents schemas
│   ├── models/                 # Pydantic models
│   ├── validation/             # JSON Schema files
│   └── proto/                  # Protocol Buffer definitions
└── services/                   # Microservices
    ├── approvals/              # Approval workflow service
    ├── captokens/              # Capability tokens service
    ├── ghostrun/               # Preflight simulation service
    ├── orchestrator/           # Execution orchestration service
    ├── plan-compiler/          # Capsule compilation service
    ├── policy/                 # Policy DSL service
    ├── receipt/                # Audit and receipt service
    └── registry/               # Capsule registry service
```

## Service Structure

Each service follows a standard microservices structure:

```
service-name/
├── src/                        # Source code
│   ├── main.py                 # FastAPI application entry point
│   ├── api/                    # API route handlers
│   ├── models/                 # Data models
│   ├── services/               # Business logic
│   ├── repositories/           # Data access layer
│   └── utils/                  # Utility functions
├── tests/                      # Unit and integration tests
├── api/                        # OpenAPI specifications
├── config/                     # Configuration files
├── scripts/                    # Build and deployment scripts
├── Dockerfile                  # Container definition
├── pyproject.toml              # Python project configuration
└── README.md                   # Service documentation
```

## Shared Components

### Packages
The `packages/` directory contains reusable Python packages that provide common functionality across services:

- **anumate-capability-tokens**: Capability token management
- **anumate-core-config**: Configuration management
- **anumate-crypto**: Cryptographic utilities
- **anumate-errors**: Error handling and definitions
- **anumate-events**: Event publishing and handling
- **anumate-http**: HTTP client utilities
- **anumate-idempotency**: Idempotency handling
- **anumate-logging**: Structured logging
- **anumate-oidc**: OIDC authentication
- **anumate-planhash**: Plan hashing utilities
- **anumate-policy**: Policy evaluation
- **anumate-receipt**: Receipt generation
- **anumate-redaction**: PII redaction
- **anumate-tenancy**: Multi-tenant utilities
- **anumate-tracing**: Distributed tracing

### Schemas
The `schemas/` directory contains shared data contracts:

- **openapi/**: OpenAPI 3.0 specifications for all services
- **events/**: CloudEvents schemas for event-driven architecture
- **models/**: Shared Pydantic models for data validation
- **validation/**: JSON Schema files for configuration validation
- **proto/**: Protocol Buffer definitions for high-performance communication

## Operations

### Infrastructure
- **kubernetes/**: Raw Kubernetes manifests for service deployment
- **helm/**: Helm charts with configurable values for different environments
- **terraform/**: Infrastructure as Code for cloud resource provisioning
- **scripts/**: Deployment automation and operational scripts

### Development
- **docker-compose.yml**: Local development environment with all services
- Configuration directories for development tools (Kiro, Gemini, MCP)

## Architecture Principles

1. **Microservices**: Each service is independently deployable and scalable
2. **Shared Libraries**: Common functionality is packaged as reusable libraries
3. **Contract-First**: APIs are defined using OpenAPI specifications
4. **Event-Driven**: Services communicate via CloudEvents on message bus
5. **Multi-Tenant**: All services support tenant isolation via RLS
6. **Observability**: Comprehensive tracing, metrics, and logging
7. **Infrastructure as Code**: All infrastructure is version-controlled and automated

## Getting Started

1. **Local Development**: `docker-compose up -d`
2. **Service Development**: Each service can be developed independently
3. **Testing**: Run tests with `pytest` in each service directory
4. **Deployment**: Use Helm charts for Kubernetes deployment

This structure supports the enterprise-grade requirements while maintaining developer productivity and operational excellence.