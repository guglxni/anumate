# Anumate Platform Architecture

## 📁 Repository Structure

```
anumate/
├── README.md                    # Main project documentation
├── Makefile                     # Build and development commands
├── pyproject.toml              # Python project configuration
├── requirements.txt            # Python dependencies
│
├── 📂 services/                # Microservices
│   ├── orchestrator/           # Main orchestration service
│   ├── approvals/              # Human-in-the-loop approvals
│   ├── captokens/              # Capability tokens management
│   ├── receipt/                # Receipt generation & validation
│   ├── registry/               # Capsule registry
│   ├── policy/                 # Policy engine
│   └── ...                     # Other services
│
├── 📂 packages/                # Shared Python packages
│   ├── anumate-core-config/    # Core configuration utilities
│   ├── anumate-crypto/         # Cryptographic functions
│   ├── anumate-events/         # Event handling
│   ├── anumate-http/           # HTTP utilities
│   ├── anumate-logging/        # Logging framework
│   └── ...                     # Other shared packages
│
├── 📂 ops/                     # Operations & infrastructure
│   ├── docker-compose.yml      # Local development stack
│   ├── kubernetes/             # K8s manifests
│   ├── helm/                   # Helm charts
│   ├── terraform/              # Infrastructure as code
│   └── scripts/                # Operational scripts
│
├── 📂 schemas/                 # Data schemas & validation
│   ├── events/                 # Event schemas
│   ├── models/                 # Data models
│   ├── openapi/                # API specifications
│   ├── proto/                  # Protocol buffer definitions
│   └── validation/             # Validation schemas
│
├── 📂 docs/                    # Documentation
│   ├── DEVELOPMENT.md          # Development guide
│   ├── INFRA_DOCKER_SETUP.md  # Infrastructure setup
│   └── ...                     # Additional documentation
│
├── 📂 scripts/                 # Utility scripts
│   ├── run_portia_demo.py      # Demo script
│   ├── capture_evidence.py     # Evidence capture
│   └── verify_receipt.py       # Receipt verification
│
├── 📂 tests/                   # Global test suite
│   └── ...                     # Integration tests
│
├── 📂 archive/                 # Archived & legacy content
│   ├── implementation-reports/ # Historical implementation docs
│   └── legacy-tests/           # Deprecated test files
│
├── 📂 build/                   # Build artifacts
│   ├── dist/                   # Distribution packages
│   └── repomix-output.xml      # Repomix output
│
└── 📂 logs/                    # Application logs
    ├── service.log             # Main service logs
    └── receipt_service.log     # Receipt service logs
```

## 🏗️ Architecture Overview

### Core Services
- **Orchestrator**: Main API gateway and workflow coordination
- **Approvals**: Human-in-the-loop approval workflows  
- **Captokens**: Capability token management and validation
- **Receipt**: Tamper-evident receipt generation
- **Registry**: Capsule and MCP registry

### Integration Layer
- **Portia SDK v0.7.2**: Cloud execution platform
- **Razorpay MCP**: Payment processing via Model Context Protocol
- **Moonshot Kimi LLM**: AI processing backend

### Security & Compliance
- **Ed25519 Signatures**: Cryptographic receipt signing
- **WORM Storage**: Write-once-read-many evidence storage
- **Secret Redaction**: Comprehensive API key masking
- **Idempotency**: Duplicate request prevention

## 🚀 Quick Start

```bash
# Start core services
make up-core

# Run production demo
make demo

# Run Razorpay MCP demo
make demo-razorpay-link

# Run acceptance tests
make accept

# Capture evidence for verification
make evidence
```

## 🔧 Development

See `docs/DEVELOPMENT.md` for detailed development setup and guidelines.

## 📋 Judge Mode

For WeMakeDevs AgentHack 2025 evaluation, see `services/orchestrator/JUDGE_MODE.md`.
