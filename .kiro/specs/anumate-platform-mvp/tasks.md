# Anumate Platform MVP Implementation Plan

## Current State Analysis

**Existing Implementation:**
- Legacy refund service code that needs to be completely replaced
- Basic project structure that needs reorganization for microservices
- No Anumate platform components implemented yet

**Target Architecture:**
- Multi-tenant automation platform with Capsules (YAML configs)
- Policy DSL for governance and redaction
- Plan Compiler (Capsule → ExecutablePlan)
- GhostRun simulator for preflight validation
- Orchestrator with Portia Runtime integration
- Connector Hub with MCP-first approach
- Event-driven architecture with CloudEvents

## Implementation Strategy

**Phase A: Platform Core**
- Services: Registry, Policy, Plan-Compiler, GhostRun, Orchestrator(+Portia), Approvals, CapTokens, Receipt
- Deliverables: OpenAPI specs, mocks, unit tests, golden path E2E (mock connectors)
- Use Kiro for spec/task orchestration; Gemini CLI for codegen + tests

**Phase B: Connectors & Multi-Tenant**
- Services: Connector-Hub with MCP servers (payments, comms); Tenant/Identity (SSO/SCIM)
- Harden secrets & RLS; add metering/billing

**Phase C: Console & CI**
- Admin Console MVP; Gemini CLI GitHub Action to enforce PR hygiene and test coverage gates

---

# Phase A: Platform Core Services

**Goal**: Build the core Anumate platform services with proper microservices architecture

**Acceptance Criteria**:
- All core services running with OpenAPI specs
- Capsule → Plan compilation working
- GhostRun preflight simulation functional
- Portia integration for plan execution
- Event bus with CloudEvents

## A.1: Project Structure & Foundation

- [x] A.1 Create proper microservices project structure
  - Set up services/ directory with individual service folders
  - Create shared schemas/ package for contracts
  - Set up .mcp/, .kiro/, .gemini/ configuration directories
  - Add ops/ directory for k8s/Helm and Terraform
  - _Requirements: Microservices architecture foundation_

- [x] A.2 Set up shared infrastructure components
  - Configure PostgreSQL with multi-tenant RLS setup
  - Set up Redis for caching and rate limiting
  - Configure NATS/Kafka for event bus with CloudEvents
  - Add HashiCorp Vault for secrets management
  - _Requirements: Multi-tenant data isolation and event-driven architecture_

- [x] A.3 Create shared libraries and utilities
  - Implement tenant context middleware
  - Create OpenTelemetry tracing utilities
  - Add structured logging with correlation IDs
  - Build common authentication/authorization helpers
  - _Requirements: Observability and security foundation_

## A.2: Capsule Registry Service

- [ ] A.4 Implement Capsule Registry core functionality
  - Create Capsule model with versioning and YAML storage
  - Implement CRUD operations for Capsule lifecycle
  - Add Capsule validation and schema enforcement
  - Build Capsule signing and integrity verification
  - _Requirements: Config-first architecture with versioned YAML_

- [ ] A.5 Add Capsule Registry API endpoints
  - POST /v1/capsules - Create new Capsule
  - GET /v1/capsules - List Capsules with filtering
  - GET /v1/capsules/{id} - Get specific Capsule version
  - PUT /v1/capsules/{id} - Update Capsule (creates new version)
  - DELETE /v1/capsules/{id} - Soft delete Capsule
  - _Requirements: RESTful API for Capsule management_

- [ ] A.6 Implement Capsule Registry business logic
  - Add Capsule dependency resolution
  - Implement Capsule inheritance and composition
  - Create Capsule diff and change tracking
  - Add Capsule approval workflow integration
  - _Requirements: Enterprise Capsule lifecycle management_

## A.3: Policy Service

- [ ] A.7 Create Policy DSL engine
  - Design Policy DSL syntax for governance rules
  - Implement Policy parser and AST generation
  - Create Policy evaluation engine
  - Add Policy validation and testing framework
  - _Requirements: Policy DSL for governance and redaction_

- [ ] A.8 Implement Policy enforcement mechanisms
  - Create Policy middleware for API endpoints
  - Add data redaction based on Policy rules
  - Implement drift detection for Policy compliance
  - Build Policy violation reporting and alerting
  - _Requirements: Policy enforcement and compliance monitoring_

- [ ] A.9 Add Policy service API endpoints
  - POST /v1/policies - Create new Policy
  - GET /v1/policies - List Policies
  - GET /v1/policies/{id} - Get specific Policy
  - POST /v1/policies/{id}/evaluate - Evaluate Policy against data
  - POST /v1/policies/{id}/test - Test Policy with sample data
  - _Requirements: Policy management and testing API_

## A.4: Plan Compiler Service

- [ ] A.10 Implement Capsule to ExecutablePlan compilation
  - Create Plan Compiler that transforms Capsules to ExecutablePlans
  - Generate plan_hash for ExecutablePlan integrity
  - Implement dependency resolution and optimization
  - Add compilation validation and error reporting
  - _Requirements: Capsule → ExecutablePlan transformation_

- [ ] A.11 Add Plan Compiler API endpoints
  - POST /v1/compile - Compile Capsule to ExecutablePlan
  - GET /v1/plans/{plan_hash} - Retrieve compiled ExecutablePlan
  - POST /v1/plans/{plan_hash}/validate - Validate ExecutablePlan
  - GET /v1/compile/status/{job_id} - Get compilation job status
  - _Requirements: Plan compilation API with async support_

- [ ] A.12 Implement Plan optimization and caching
  - Add ExecutablePlan caching by plan_hash
  - Implement Plan optimization for performance
  - Create Plan dependency graph analysis
  - Add Plan execution cost estimation
  - _Requirements: Efficient Plan compilation and caching_

## A.5: GhostRun Simulator Service

- [ ] A.13 Create GhostRun dry-run simulation engine
  - Implement ExecutablePlan simulation without side effects
  - Create mock connector responses for simulation
  - Generate Preflight reports with validation results
  - Add simulation performance metrics and timing
  - _Requirements: Preflight validation with dry-run simulation_

- [ ] A.14 Add GhostRun API endpoints
  - POST /v1/ghostrun - Start GhostRun simulation
  - GET /v1/ghostrun/{run_id} - Get GhostRun status and results
  - GET /v1/ghostrun/{run_id}/report - Get Preflight report
  - POST /v1/ghostrun/{run_id}/cancel - Cancel running simulation
  - _Requirements: GhostRun simulation API_

- [ ] A.15 Implement Preflight report generation
  - Create comprehensive Preflight validation reports
  - Add risk assessment and recommendation engine
  - Implement Preflight report storage and retrieval
  - Generate preflight.completed CloudEvents
  - _Requirements: Preflight P95 < 1.5s SLO and reporting_

## A.6: Orchestrator Service (Portia Integration)

- [ ] A.16 Implement Portia Runtime integration
  - Create Portia Plans/PlanRuns from ExecutablePlans
  - Implement Clarifications bridge for approvals
  - Add execution hooks for capability token validation
  - Build retry logic and idempotency handling
  - _Requirements: Clean Portia integration with hooks_

- [ ] A.17 Add Orchestrator API endpoints
  - POST /v1/execute - Execute ExecutablePlan via Portia
  - GET /v1/executions/{run_id} - Get execution status
  - POST /v1/executions/{run_id}/pause - Pause execution
  - POST /v1/executions/{run_id}/resume - Resume execution
  - POST /v1/executions/{run_id}/cancel - Cancel execution
  - _Requirements: Execution orchestration API_

- [ ] A.18 Implement execution monitoring and hooks
  - Add pre-execution capability token validation
  - Implement execution progress tracking
  - Create execution.completed CloudEvent emission
  - Add execution failure handling and rollback
  - _Requirements: Execute success ≥ 99% SLO and monitoring_

## A.7: Approvals Service

- [ ] A.19 Create Clarifications bridge for approvals
  - Implement Portia Clarifications integration
  - Create approval request generation from Plans
  - Add approver notification system (email/Slack)
  - Build approval UI for decision making
  - _Requirements: Approval propagation < 2s SLO_

- [ ] A.20 Add Approvals API endpoints
  - GET /v1/approvals - List pending approvals
  - GET /v1/approvals/{approval_id} - Get approval details
  - POST /v1/approvals/{approval_id}/approve - Approve request
  - POST /v1/approvals/{approval_id}/reject - Reject request
  - POST /v1/approvals/{approval_id}/delegate - Delegate approval
  - _Requirements: Approval management API_

- [ ] A.21 Implement approval workflow engine
  - Create multi-step approval workflows
  - Add approval escalation and timeout handling
  - Implement approval audit trail
  - Generate approval.granted CloudEvents
  - _Requirements: Enterprise approval workflows_

## A.8: Capability Tokens Service

- [ ] A.22 Implement Ed25519/JWT capability tokens
  - Create short-lived capability tokens (≤5m expiry)
  - Implement Ed25519 signing for token integrity
  - Add capability-based access control
  - Build token verification service
  - _Requirements: Short-lived capability tokens for security_

- [ ] A.23 Add CapTokens API endpoints
  - POST /v1/captokens - Issue new capability token
  - POST /v1/captokens/verify - Verify token and capabilities
  - POST /v1/captokens/refresh - Refresh token before expiry
  - GET /v1/captokens/audit - Get token usage audit trail
  - _Requirements: Capability token management API_

- [ ] A.24 Implement capability enforcement
  - Add capability checking middleware
  - Implement tool allow-lists from Capsules
  - Create capability violation logging
  - Add capability token usage tracking
  - _Requirements: Strict tool allow-lists and capability enforcement_

## A.9: Receipt & Audit Service

- [ ] A.25 Create tamper-evident receipt system
  - Implement immutable Receipt generation with hashing
  - Add digital signatures for Receipt integrity
  - Create WORM storage integration for compliance
  - Build Receipt verification and audit trails
  - _Requirements: Immutable Receipts with hash + WORM_

- [ ] A.26 Add Receipt API endpoints
  - POST /v1/receipts - Create new Receipt
  - GET /v1/receipts/{receipt_id} - Get Receipt details
  - POST /v1/receipts/{receipt_id}/verify - Verify Receipt integrity
  - GET /v1/receipts/audit - Export audit logs to SIEM
  - _Requirements: Receipt management and audit API_

- [ ] A.27 Implement comprehensive audit logging
  - Create audit event capture for all operations
  - Add per-tenant retention policy enforcement
  - Implement access log export for SIEM systems
  - Build audit trail correlation and search
  - _Requirements: Per-tenant retention and SIEM export_

## A.10: Event Bus & Integration

- [ ] A.28 Implement CloudEvents event bus
  - Set up NATS/Kafka with CloudEvents format
  - Create event publishers for all services
  - Implement event subscribers and routing
  - Add event replay and dead letter handling
  - _Requirements: Event-driven architecture with CloudEvents_

- [ ] A.29 Create service integration patterns
  - Implement service discovery and health checks
  - Add circuit breakers for service resilience
  - Create API Gateway for external access
  - Build service mesh configuration
  - _Requirements: Microservices integration and resilience_

- [ ] A.30 Add end-to-end golden path testing
  - Create E2E test for Capsule → Plan → GhostRun → Execute flow
  - Implement mock connectors for testing
  - Add performance testing for SLO validation
  - Build integration test automation
  - _Requirements: Golden path E2E with mock connectors_
  - _Status: TODO - Need to implement after core services are built_

---

# Implementation Notes

## Technology Stack

**Core Technologies:**
- **API Framework**: FastAPI for all services
- **Database**: PostgreSQL with RLS for multi-tenancy
- **Event Bus**: NATS with CloudEvents format
- **Secrets**: HashiCorp Vault
- **Observability**: OpenTelemetry + Prometheus + Grafana
- **Infrastructure**: Kubernetes + Helm + Terraform

**Service-Specific Libraries:**
- **Capsule Registry**: PyYAML, jsonschema for validation
- **Policy Service**: Custom DSL parser, AST evaluation
- **Plan Compiler**: Dependency resolution, graph algorithms
- **GhostRun**: Simulation engine, mock frameworks
- **Orchestrator**: Portia SDK, async execution
- **Approvals**: Email/Slack integrations, workflow engine
- **CapTokens**: Ed25519 cryptography, JWT handling
- **Receipt**: Cryptographic hashing, WORM storage

## Service Communication

**API Contracts**: OpenAPI 3.0 specs for all services
**Events**: CloudEvents on NATS (plan.created, preflight.completed, approval.granted, execution.completed)
**Authentication**: JWT tokens with tenant context
**Authorization**: Capability tokens for service-to-service calls

## SLO Targets

- **Preflight P95**: < 1.5s (GhostRun simulation)
- **Approval Propagation**: < 2s (Approvals service)
- **Execute Success**: ≥ 99% (Orchestrator reliability)
- **Webhook Lag P95**: < 5s (Event processing)

## Success Criteria

**Phase A Success:**
- All 8 core services deployed and operational
- OpenAPI specs published and validated
- Golden path E2E test passing
- SLO monitoring and alerting configured
- Mock connectors working for development

This implementation plan builds the complete Anumate platform core with proper microservices architecture, focusing on the automation platform capabilities rather than any refund-specific functionality.