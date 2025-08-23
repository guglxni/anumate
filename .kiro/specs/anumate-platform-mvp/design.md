# Enterprise Non-Functional Requirements Design

## Overview

This design document outlines the architecture and implementation approach for Anumate's enterprise-grade non-functional requirements. The design focuses on multi-tenant security, privacy protection, comprehensive observability, and operational excellence while maintaining the specific SLOs defined in the requirements.

## Architecture

### High-Level Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        UI[Web UI]
        API_CLIENT[API Clients]
        WEBHOOK[Webhook Consumers]
    end
    
    subgraph "Edge Layer"
        LB[Load Balancer]
        WAF[Web Application Firewall]
        CDN[Content Delivery Network]
    end
    
    subgraph "Application Layer"
        AUTH[Auth Service]
        CORE[Core API]
        WEBHOOK_SVC[Webhook Service]
        WORKER[Background Workers]
    end
    
    subgraph "Security Layer"
        VAULT[HashiCorp Vault]
        KMS[Per-Tenant KMS]
        SSO[SSO/SCIM Gateway]
    end
    
    subgraph "Data Layer"
        PRIMARY_DB[(Primary Database)]
        AUDIT_DB[(Audit Database)]
        CACHE[(Redis Cache)]
        WORM[(WORM Storage)]
    end
    
    subgraph "Observability Layer"
        OTEL[OpenTelemetry Collector]
        METRICS[Metrics Store]
        LOGS[Log Aggregation]
        TRACES[Trace Storage]
    end
    
    UI --> LB
    API_CLIENT --> LB
    LB --> WAF
    WAF --> AUTH
    AUTH --> SSO
    AUTH --> VAULT
    CORE --> PRIMARY_DB
    CORE --> CACHE
    CORE --> KMS
    WORKER --> AUDIT_DB
    AUDIT_DB --> WORM
    
    CORE --> OTEL
    AUTH --> OTEL
    WORKER --> OTEL
    OTEL --> METRICS
    OTEL --> LOGS
    OTEL --> TRACES
```

### Multi-Tenant Data Architecture

```mermaid
erDiagram
    TENANTS {
        uuid tenant_id PK
        string name
        string slug
        jsonb settings
        string data_residency_region
        timestamp created_at
        timestamp updated_at
        boolean active
    }
    
    USERS {
        uuid user_id PK
        uuid tenant_id FK
        string external_id
        string email
        jsonb profile
        timestamp created_at
        timestamp last_login
        boolean active
    }
    
    TEAMS {
        uuid team_id PK
        uuid tenant_id FK
        string name
        string description
        uuid parent_team_id FK
        timestamp created_at
        timestamp updated_at
    }
    
    ROLES {
        uuid role_id PK
        uuid tenant_id FK
        string name
        jsonb permissions
        string scope
        timestamp created_at
        timestamp updated_at
    }
    
    USER_ROLES {
        uuid user_id FK
        uuid role_id FK
        uuid team_id FK
        timestamp granted_at
        timestamp expires_at
    }
    
    CAPSULES {
        uuid capsule_id PK
        uuid tenant_id FK
        string name
        string version
        jsonb definition
        string checksum
        uuid created_by FK
        timestamp created_at
        boolean active
    }
    
    PLANS {
        uuid plan_id PK
        uuid tenant_id FK
        uuid capsule_id FK
        string version
        jsonb compiled_definition
        string checksum
        uuid created_by FK
        timestamp created_at
        string status
    }
    
    RUNS {
        uuid run_id PK
        uuid tenant_id FK
        uuid plan_id FK
        string external_run_id
        jsonb parameters
        string status
        jsonb results
        uuid triggered_by FK
        timestamp started_at
        timestamp completed_at
    }
    
    APPROVALS {
        uuid approval_id PK
        uuid tenant_id FK
        uuid run_id FK
        uuid approver_id FK
        string status
        jsonb metadata
        timestamp requested_at
        timestamp responded_at
        string response_reason
    }
    
    CAPABILITY_TOKENS {
        uuid token_id PK
        uuid tenant_id FK
        string token_hash
        jsonb capabilities
        uuid created_by FK
        timestamp created_at
        timestamp expires_at
        timestamp last_used_at
        boolean active
    }
    
    CONNECTORS {
        uuid connector_id PK
        uuid tenant_id FK
        string name
        string type
        jsonb configuration_encrypted
        uuid kms_key_id
        uuid created_by FK
        timestamp created_at
        timestamp updated_at
        boolean active
    }
    
    EVENTS {
        uuid event_id PK
        uuid tenant_id FK
        string event_type
        uuid entity_id
        string entity_type
        jsonb payload
        uuid actor_id FK
        timestamp occurred_at
        string correlation_id
    }
    
    RECEIPTS {
        uuid receipt_id PK
        uuid tenant_id FK
        string receipt_type
        jsonb content_hash
        jsonb digital_signature
        timestamp created_at
        string immutable_reference
    }
    
    USAGE {
        uuid usage_id PK
        uuid tenant_id FK
        string metric_name
        decimal value
        jsonb dimensions
        timestamp recorded_at
        string billing_period
    }
    
    TENANTS ||--o{ USERS : "has"
    TENANTS ||--o{ TEAMS : "contains"
    TENANTS ||--o{ ROLES : "defines"
    TENANTS ||--o{ CAPSULES : "owns"
    TENANTS ||--o{ PLANS : "creates"
    TENANTS ||--o{ RUNS : "executes"
    TENANTS ||--o{ APPROVALS : "manages"
    TENANTS ||--o{ CAPABILITY_TOKENS : "issues"
    TENANTS ||--o{ CONNECTORS : "configures"
    TENANTS ||--o{ EVENTS : "generates"
    TENANTS ||--o{ RECEIPTS : "maintains"
    TENANTS ||--o{ USAGE : "tracks"
    
    USERS ||--o{ USER_ROLES : "assigned"
    ROLES ||--o{ USER_ROLES : "grants"
    TEAMS ||--o{ USER_ROLES : "scopes"
    TEAMS ||--o{ TEAMS : "parent_of"
    
    CAPSULES ||--o{ PLANS : "compiled_into"
    PLANS ||--o{ RUNS : "executed_as"
    RUNS ||--o{ APPROVALS : "requires"
    
    USERS ||--o{ CAPSULES : "creates"
    USERS ||--o{ PLANS : "compiles"
    USERS ||--o{ RUNS : "triggers"
    USERS ||--o{ APPROVALS : "approves"
    USERS ||--o{ CAPABILITY_TOKENS : "creates"
    USERS ||--o{ CONNECTORS : "configures"
    USERS ||--o{ EVENTS : "performs"
```

## Components and Interfaces

### Authentication and Authorization Service

**Purpose**: Handles SSO integration, SCIM provisioning, and tenant-aware authorization

**Key Components**:
- OIDC/SAML authentication handlers
- SCIM 2.0 provisioning endpoints
- JWT token management with tenant context
- Role-based access control (RBAC) engine

**Interfaces**:
```
POST /auth/sso/initiate
POST /auth/sso/callback
GET /auth/userinfo
POST /auth/logout

POST /scim/v2/Users
GET /scim/v2/Users
PUT /scim/v2/Users/{id}
DELETE /scim/v2/Users/{id}
```

### Multi-Tenant Data Service

**Purpose**: Enforces RLS policies and manages tenant data isolation

**Key Components**:
- Database connection pooling with tenant context
- RLS policy enforcement engine
- Tenant-aware query builders
- Data residency compliance checker

**RLS Implementation**:
```sql
-- Example RLS policy for users table
CREATE POLICY tenant_isolation ON users
    FOR ALL TO application_role
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

### Secrets Management Service

**Purpose**: Integrates with HashiCorp Vault and manages per-tenant KMS keys

**Key Components**:
- Vault authentication and token management
- Per-tenant KMS key provisioning
- Secret rotation automation
- Encrypted configuration management

**Vault Integration**:
```
vault auth -method=kubernetes
vault kv get -mount=secret tenants/{tenant_id}/config
vault transit encrypt -key={tenant_id} plaintext={data}
```

### Privacy Protection Service

**Purpose**: Detects and redacts PII across all system outputs

**Key Components**:
- PII detection engine using regex and ML models
- Log sanitization middleware
- Data export redaction filters
- Privacy compliance reporting

**PII Detection Patterns**:
- Email addresses: `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`
- Phone numbers: `\b\d{3}-\d{3}-\d{4}\b`
- SSN: `\b\d{3}-\d{2}-\d{4}\b`
- Credit cards: `\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b`

### Observability Service

**Purpose**: Implements OpenTelemetry tracing, metrics, and structured logging

**Key Components**:
- OpenTelemetry SDK integration
- Custom metrics collectors
- Structured logging middleware
- Distributed tracing context propagation

**Telemetry Configuration**:
```yaml
otel:
  service_name: anumate-api
  traces:
    endpoint: http://jaeger:14268/api/traces
  metrics:
    endpoint: http://prometheus:9090/api/v1/write
  logs:
    endpoint: http://loki:3100/loki/api/v1/push
```

### Audit Service

**Purpose**: Manages immutable audit logs with WORM storage

**Key Components**:
- Event capture middleware
- WORM storage integration
- Audit trail query engine
- Compliance reporting generator

**Audit Event Schema**:
```json
{
  "event_id": "uuid",
  "tenant_id": "uuid",
  "timestamp": "ISO8601",
  "actor": {
    "user_id": "uuid",
    "ip_address": "string",
    "user_agent": "string"
  },
  "action": "string",
  "resource": {
    "type": "string",
    "id": "uuid"
  },
  "outcome": "success|failure",
  "metadata": {}
}
```

## Data Models

### Entity Specifications

#### Tenants
- **Fields**: tenant_id (PK), name, slug, settings, data_residency_region, created_at, updated_at, active
- **Relationships**: One-to-many with all other entities
- **Tenancy Boundary**: Root entity - defines tenant boundary
- **Retention Policy**: Indefinite (business entity)
- **Access Rules**: System administrators only

#### Users
- **Fields**: user_id (PK), tenant_id (FK), external_id, email, profile, created_at, last_login, active
- **Relationships**: Belongs to tenant, has many roles through user_roles
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: 7 years after account deletion
- **Access Rules**: Self-read, tenant admins full access

#### Teams
- **Fields**: team_id (PK), tenant_id (FK), name, description, parent_team_id (FK), created_at, updated_at
- **Relationships**: Belongs to tenant, self-referential hierarchy
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: 3 years after team dissolution
- **Access Rules**: Team members read, team admins write

#### Roles/Permissions
- **Fields**: role_id (PK), tenant_id (FK), name, permissions (JSONB), scope, created_at, updated_at
- **Relationships**: Belongs to tenant, many-to-many with users
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: 5 years after role deletion
- **Access Rules**: Tenant admins only

#### Capsules (Versioned)
- **Fields**: capsule_id (PK), tenant_id (FK), name, version, definition (JSONB), checksum, created_by (FK), created_at, active
- **Relationships**: Belongs to tenant, created by user, has many plans
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: Indefinite (business logic)
- **Access Rules**: Creator and authorized team members

#### Plans (Compiled)
- **Fields**: plan_id (PK), tenant_id (FK), capsule_id (FK), version, compiled_definition (JSONB), checksum, created_by (FK), created_at, status
- **Relationships**: Belongs to tenant and capsule, created by user
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: 2 years after last execution
- **Access Rules**: Plan executors and approvers

#### Runs (PlanRun Mirror)
- **Fields**: run_id (PK), tenant_id (FK), plan_id (FK), external_run_id, parameters (JSONB), status, results (JSONB), triggered_by (FK), started_at, completed_at
- **Relationships**: Belongs to tenant and plan, triggered by user
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: 5 years for compliance
- **Access Rules**: Run participants and auditors

#### Approvals
- **Fields**: approval_id (PK), tenant_id (FK), run_id (FK), approver_id (FK), status, metadata (JSONB), requested_at, responded_at, response_reason
- **Relationships**: Belongs to tenant and run, assigned to user
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: 7 years for audit compliance
- **Access Rules**: Approver and audit trail viewers

#### Capability Tokens
- **Fields**: token_id (PK), tenant_id (FK), token_hash, capabilities (JSONB), created_by (FK), created_at, expires_at, last_used_at, active
- **Relationships**: Belongs to tenant, created by user
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: 1 year after expiration
- **Access Rules**: Token creator and tenant admins

#### Connectors (Per Tenant)
- **Fields**: connector_id (PK), tenant_id (FK), name, type, configuration_encrypted (JSONB), kms_key_id, created_by (FK), created_at, updated_at, active
- **Relationships**: Belongs to tenant, created by user
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: 3 years after deletion
- **Access Rules**: Connector admins only

#### Events
- **Fields**: event_id (PK), tenant_id (FK), event_type, entity_id, entity_type, payload (JSONB), actor_id (FK), occurred_at, correlation_id
- **Relationships**: Belongs to tenant, performed by user
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: 10 years for audit compliance
- **Access Rules**: Audit viewers and compliance officers

#### Receipts (Immutable)
- **Fields**: receipt_id (PK), tenant_id (FK), receipt_type, content_hash (JSONB), digital_signature (JSONB), created_at, immutable_reference
- **Relationships**: Belongs to tenant
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: Permanent (legal requirement)
- **Access Rules**: Read-only, compliance officers only

#### Usage
- **Fields**: usage_id (PK), tenant_id (FK), metric_name, value (decimal), dimensions (JSONB), recorded_at, billing_period
- **Relationships**: Belongs to tenant
- **Tenancy Boundary**: Isolated by tenant_id
- **Retention Policy**: 7 years for billing compliance
- **Access Rules**: Billing admins and tenant owners

## Error Handling

### Error Classification
- **Authentication Errors**: 401 Unauthorized with specific error codes
- **Authorization Errors**: 403 Forbidden with tenant context
- **Validation Errors**: 400 Bad Request with field-level details
- **Rate Limiting**: 429 Too Many Requests with retry headers
- **System Errors**: 500 Internal Server Error with correlation IDs

### Error Response Format
```json
{
  "error": {
    "code": "TENANT_ACCESS_DENIED",
    "message": "Access to resource denied for tenant",
    "correlation_id": "uuid",
    "timestamp": "ISO8601",
    "details": {}
  }
}
```

### Circuit Breaker Implementation
- **Vault Integration**: 5 failures in 60 seconds triggers 30-second circuit break
- **Database Connections**: 10 failures in 30 seconds triggers 60-second circuit break
- **External APIs**: 3 failures in 10 seconds triggers 20-second circuit break

## Testing Strategy

### Security Testing
- **Tenant Isolation Tests**: Automated tests verifying RLS policy enforcement
- **Authentication Tests**: SSO integration testing with mock identity providers
- **Authorization Tests**: RBAC policy validation across all endpoints
- **Penetration Testing**: Quarterly third-party security assessments

### Performance Testing
- **Load Testing**: Simulate 10x expected load to validate SLO compliance
- **Stress Testing**: Push system to failure points to identify bottlenecks
- **Chaos Engineering**: Random failure injection to test resilience
- **SLO Validation**: Continuous monitoring of all defined service level objectives

### Compliance Testing
- **PII Detection**: Automated scanning for PII in logs and outputs
- **Audit Trail**: Verification of complete audit trail coverage
- **Data Residency**: Validation of geographic data constraints
- **Retention Policy**: Automated testing of data lifecycle management

### Integration Testing
- **Multi-Tenant Scenarios**: Cross-tenant isolation validation
- **Disaster Recovery**: Regular DR procedure testing
- **Backup/Restore**: Automated backup integrity verification
- **Observability**: End-to-end tracing and metrics validation