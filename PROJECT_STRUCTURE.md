# Anumate Platform Project Structure

This document describes the microservices project structure for the Anumate automation platform.

## Directory Structure

```
anumate/
├── .gemini/                    # Gemini CLI configuration
│   ├── config/                 # CLI configuration files
│   ├── templates/              # Code generation templates
│   ├── prompts/                # Custom prompts
│   └── workflows/              # Automated workflows
├── .kiro/                      # Kiro IDE configuration
│   ├── specs/                  # Feature specifications
│   ├── settings/               # IDE settings
│   ├── steering/               # Steering rules
│   └── hooks/                  # Agent hooks
├── .mcp/                       # Model Context Protocol config
│   ├── servers/                # MCP server configs
│   ├── connectors/             # Connector definitions
│   └── tools/                  # Custom MCP tools
├── docs/                       # Documentation
├── ops/                        # Operations and infrastructure
│   ├── kubernetes/             # K8s manifests
│   ├── helm/                   # Helm charts
│   ├── terraform/              # Infrastructure as Code
│   ├── scripts/                # Deployment scripts
│   └── docker-compose.yml      # Local development
├── packages/                   # Shared Python packages
│   ├── anumate-capability-tokens/
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