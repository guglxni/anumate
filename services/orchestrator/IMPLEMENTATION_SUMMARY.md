# Orchestrator Service - Portia Integration Implementation

## Overview

This implementation provides the core Portia Runtime integration for the Anumate Orchestrator service, enabling ExecutablePlan execution with comprehensive hooks, retry logic, and idempotency handling.

## Implemented Components

### 1. Core Models (`src/models.py`)

**Key Models:**
- `ExecutionStatusEnum`: Status enumeration for plan executions
- `PortiaPlan`: Portia plan representation with steps and metadata
- `PortiaPlanRun`: Portia execution run with status tracking
- `Clarification`: Approval request model for Portia clarifications
- `ExecutionRequest`: Request model for plan execution
- `ExecutionResponse`: Response model with execution details
- `RetryPolicy`: Configurable retry behavior
- `ExecutionHook`: Pre/post execution hooks
- `CapabilityValidation`: Capability token validation results
- `IdempotencyKey`: Idempotency tracking for requests

### 2. Portia Client (`src/portia_client.py`)

**Features:**
- Async HTTP client for Portia Runtime API
- Plan creation and management
- Run lifecycle management (create, pause, resume, cancel)
- Clarification handling for approvals
- Retry logic with exponential backoff
- Health check monitoring
- Comprehensive error handling

**Key Methods:**
- `create_plan()`: Create plans in Portia Runtime
- `create_run()`: Start plan execution
- `get_run()`: Get execution status
- `pause_run()` / `resume_run()` / `cancel_run()`: Control execution
- `get_clarifications()`: Retrieve approval requests
- `respond_to_clarification()`: Handle approval responses

### 3. Plan Transformer (`src/plan_transformer.py`)

**Functionality:**
- Converts ExecutablePlans to Portia Plan format
- Maps execution flows to Portia steps
- Preserves step dependencies and conditions
- Extracts timeout and retry policies
- Handles variable and parameter mapping
- Maintains security context information

**Transformation Features:**
- Step type mapping (action, condition, loop)
- Dependency resolution
- Parameter and input/output mapping
- Timeout and retry policy extraction
- Metadata preservation

### 4. Capability Validator (`src/capability_validator.py`)

**Security Features:**
- Capability token validation (mock implementation)
- Tool allowlist enforcement
- Token expiry checking
- Development vs production validation modes
- Integration ready for CapTokens service

**Validation Types:**
- Execution capability validation
- Tool allowlist checking
- Token expiry monitoring
- Security context enforcement

### 5. Clarifications Bridge (`src/clarifications_bridge.py`)

**Approval Integration:**
- Bridges Portia Clarifications with Anumate Approvals
- Creates approval requests from clarifications
- Polls approval status
- Responds to clarifications with approval decisions
- Event publishing for approval lifecycle
- Mock implementation ready for Approvals service

### 6. Retry Handler (`src/retry_handler.py`)

**Resilience Features:**
- Configurable retry policies
- Exponential backoff with jitter
- Idempotency key generation and checking
- Redis-based idempotency storage
- Request deduplication
- Automatic cleanup of expired keys

**Idempotency:**
- SHA-256 request hashing
- Redis-based storage with TTL
- Cached response handling
- Duplicate request detection

### 7. Main Orchestrator Service (`src/service.py`)

**Core Orchestration:**
- ExecutablePlan execution via Portia
- Pre/post execution hooks
- Capability validation integration
- Idempotency handling
- Event publishing
- Execution status monitoring
- Error handling and recovery

**Execution Flow:**
1. Idempotency check
2. Capability validation
3. Pre-execution hooks
4. Plan transformation
5. Portia execution
6. Post-execution hooks
7. Event publishing
8. Status monitoring

## Key Features Implemented

### ✅ Portia Plans/PlanRuns from ExecutablePlans
- Complete transformation from ExecutablePlan format to Portia format
- Preserves all execution logic, dependencies, and metadata
- Handles complex execution flows with multiple steps
- Maps security contexts and resource requirements

### ✅ Clarifications Bridge for Approvals
- Seamless integration between Portia clarifications and Anumate approvals
- Event-driven approval workflow
- Mock implementation ready for Approvals service integration
- Approval status polling and response handling

### ✅ Execution Hooks for Capability Token Validation
- Pre-execution capability validation
- Tool allowlist enforcement
- Token expiry checking
- Security context validation
- Integration hooks for CapTokens service

### ✅ Retry Logic and Idempotency Handling
- Configurable retry policies with exponential backoff
- Redis-based idempotency storage
- Request deduplication
- Automatic cleanup and TTL management
- Comprehensive error handling

## Testing and Validation

### Demo Implementation
- `simple_demo.py`: Demonstrates core transformation logic
- Shows ExecutablePlan → Portia Plan conversion
- Validates capability checking
- Demonstrates retry policy handling
- Shows idempotency key generation

### Test Coverage
- Portia client tests with mocked HTTP responses
- Plan transformer unit tests
- Capability validation tests
- Retry logic and idempotency tests

## Integration Points

### Ready for Integration:
- **Plan Compiler**: Consumes ExecutablePlans via plan_hash lookup
- **CapTokens Service**: Capability validation via HTTP API
- **Approvals Service**: Approval workflow via clarifications bridge
- **Event Bus**: CloudEvents publishing for execution lifecycle
- **Redis**: Idempotency storage and caching

### Mock Implementations:
- Capability validation (development mode allows all)
- Approval creation and polling (auto-approval in dev)
- Portia Runtime API (will connect to actual Portia when available)

## Configuration

### Environment Variables:
- `PORTIA_BASE_URL`: Portia Runtime endpoint
- `ANUMATE_ENV`: Environment mode (development/production)
- Redis connection for idempotency storage
- Event bus configuration for notifications

### Dependencies:
- FastAPI for API endpoints (next phase)
- httpx for HTTP client communication
- tenacity for retry logic
- Redis for idempotency storage
- Shared Anumate packages for infrastructure

## Next Steps

The implementation is ready for:
1. **API Endpoints** (Task A.17): REST API for execution management
2. **Approvals Integration**: Connect to actual Approvals service
3. **CapTokens Integration**: Connect to actual CapTokens service
4. **Event Bus Integration**: CloudEvents publishing
5. **Monitoring Integration**: Execution metrics and observability

## Requirements Satisfied

✅ **Clean Portia integration with hooks**: Complete integration with execution hooks
✅ **Create Portia Plans/PlanRuns from ExecutablePlans**: Full transformation implemented
✅ **Implement Clarifications bridge for approvals**: Bridge with event publishing
✅ **Add execution hooks for capability token validation**: Pre-execution validation
✅ **Build retry logic and idempotency handling**: Comprehensive resilience features

The implementation provides a robust foundation for ExecutablePlan execution via Portia Runtime with enterprise-grade reliability, security, and observability features.