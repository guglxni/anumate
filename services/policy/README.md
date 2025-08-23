# Policy DSL Service

A comprehensive Domain Specific Language (DSL) for defining governance rules and data redaction policies in the Anumate platform.

## Overview

The Policy DSL provides a declarative way to define:
- **Governance Rules**: Access control, approval workflows, and compliance policies
- **Data Redaction**: Automatic PII detection and redaction
- **Audit Logging**: Comprehensive audit trails and compliance reporting
- **Alert Management**: Real-time alerts for policy violations

## Features

### 🔒 Security & Privacy
- Built-in PII detection (emails, phone numbers, SSNs, credit cards)
- Configurable redaction patterns and replacements
- Role-based access control with context awareness
- Geographic and time-based restrictions

### 🎯 Policy Engine
- Fast policy compilation and evaluation
- Rule priority system with conflict resolution
- Comprehensive validation and error reporting
- Extensive testing framework

### 📊 Observability
- Structured audit logging
- Real-time alerting with severity levels
- Performance metrics and evaluation timing
- Integration with OpenTelemetry

### 🧪 Testing & Validation
- Built-in policy testing framework
- Automated test case generation
- Comprehensive validation with best practice recommendations
- Multiple report formats (console, JSON, JUnit XML)

## Policy DSL Syntax

### Basic Structure

```policy
policy "Policy Name" {
    description: "Policy description"
    version: "1.0"
    author: "Policy Author"
    
    rule "Rule Name" {
        when <condition>
        then <action>
        priority: <number>
        enabled: <boolean>
    }
}
```

### Conditions

```policy
# Basic comparisons
when user.role == "admin"
when user.age >= 18
when user.score > 85.5

# String operations
when user.email contains "@company.com"
when user.name matches "^[A-Z][a-z]+ [A-Z][a-z]+$"
when user.username starts_with "admin"
when user.domain ends_with ".gov"

# Logical operations
when user.role == "admin" and user.active == true
when user.role == "guest" or user.role == "anonymous"
when not user.banned

# Collection operations
when user.role in ["admin", "moderator"]
when "sensitive" not_in data.tags

# Function calls
when is_email(user.email)
when len(user.password) >= 8
when contains_pii(data.content)
```

### Actions

```policy
# Access control
then allow()
then deny()

# Logging
then log(level="info", message="User accessed resource")

# Alerting
then alert(severity="high", message="Suspicious activity detected")

# Data redaction
then redact(field="email", replacement="[REDACTED]")
then redact(pattern="\\d{3}-\\d{3}-\\d{4}", replacement="XXX-XXX-XXXX")

# Approval workflows
then require_approval(approvers=["security-team", "manager"])

# Multiple actions
then {
    log(level="warning", message="PII access detected")
    redact(field="ssn", replacement="XXX-XX-XXXX")
    alert(severity="medium", message="PII redaction applied")
}
```

### Built-in Functions

#### PII Detection
- `is_email(text)` - Detect email addresses
- `is_phone(text)` - Detect phone numbers
- `is_ssn(text)` - Detect Social Security Numbers
- `is_credit_card(text)` - Detect credit card numbers
- `contains_pii(text)` - Detect any PII

#### String Functions
- `len(string)` - String length
- `lower(string)` - Convert to lowercase
- `upper(string)` - Convert to uppercase
- `strip(string)` - Remove whitespace
- `split(string, separator)` - Split string

#### Utility Functions
- `now()` - Current timestamp
- `today()` - Current date
- `uuid()` - Generate UUID

## Usage Examples

### Simple Access Control

```policy
policy "Basic Access Control" {
    rule "Admin Access" {
        when user.role == "admin"
        then allow()
        priority: 100
    }
    
    rule "Guest Restriction" {
        when user.role == "guest"
        then deny()
        priority: 50
    }
}
```

### PII Protection

```policy
policy "PII Protection" {
    rule "Email Redaction" {
        when is_email(data.content)
        then {
            log(level="info", message="Email PII detected")
            redact(pattern="[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}", 
                   replacement="[EMAIL_REDACTED]")
        }
        priority: 90
    }
    
    rule "Phone Redaction" {
        when is_phone(data.content)
        then redact(pattern="\\d{3}-\\d{3}-\\d{4}", replacement="XXX-XXX-XXXX")
        priority: 85
    }
}
```

### Context-Aware Policies

```policy
policy "Time-based Access" {
    rule "Business Hours Only" {
        when context.hour >= 9 and context.hour <= 17 and 
             context.day_of_week in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        then allow()
        priority: 80
    }
    
    rule "After Hours Approval" {
        when (context.hour < 9 or context.hour > 17) and user.role != "admin"
        then require_approval(approvers=["security-team"])
        priority: 70
    }
}
```

## Python API

### Basic Usage

```python
from services.policy.src.engine import PolicyEngine

# Create engine
engine = PolicyEngine()

# Compile policy
result = engine.compile_policy(policy_source, "my_policy")
if result.success:
    policy = result.policy
else:
    print(f"Compilation error: {result.error_message}")

# Evaluate policy
data = {"user": {"role": "admin"}, "action": "read"}
result = engine.evaluate_policy(policy, data)

if result.success:
    print(f"Decision: {'ALLOWED' if result.evaluation.allowed else 'DENIED'}")
    print(f"Matched rules: {result.evaluation.matched_rules}")
    print(f"Actions: {[a['type'] for a in result.evaluation.actions]}")
```

### Policy Testing

```python
from services.policy.src.test_framework import TestCase, TestReportFormatter

# Define test cases
test_cases = [
    TestCase(
        name="Admin Access Test",
        description="Test admin user access",
        input_data={"user": {"role": "admin"}},
        expected_allowed=True,
        expected_rules=["Admin Access"]
    ),
    TestCase(
        name="Guest Restriction Test", 
        description="Test guest user restriction",
        input_data={"user": {"role": "guest"}},
        expected_allowed=False,
        expected_rules=["Guest Restriction"]
    )
]

# Run tests
result = engine.test_policy(policy, test_cases, "Access Control Tests")

# Generate report
if result.success:
    report = TestReportFormatter.format_console(result.test_report)
    print(report)
```

### Policy Validation

```python
from services.policy.src.validator import PolicyValidator

validator = PolicyValidator()
validation_result = validator.validate(policy)

if validation_result.is_valid:
    print("✅ Policy is valid")
else:
    print("❌ Policy has errors:")
    for error in validation_result.errors:
        print(f"  - {error}")

if validation_result.warnings:
    print("⚠️ Warnings:")
    for warning in validation_result.warnings:
        print(f"  - {warning}")
```

## Architecture

### Components

1. **Lexer** (`lexer.py`) - Tokenizes Policy DSL source code
2. **Parser** (`parser.py`) - Converts tokens to Abstract Syntax Tree (AST)
3. **AST Nodes** (`ast_nodes.py`) - Defines AST node types and structure
4. **Evaluator** (`evaluator.py`) - Evaluates policies against input data
5. **Validator** (`validator.py`) - Validates policies for correctness and best practices
6. **Test Framework** (`test_framework.py`) - Comprehensive testing utilities
7. **Engine** (`engine.py`) - High-level API that orchestrates all components

### Evaluation Flow

```
Policy Source Code
       ↓
    Lexer (Tokenization)
       ↓
    Parser (AST Generation)
       ↓
    Validator (Validation)
       ↓
    Evaluator (Runtime Evaluation)
       ↓
    Results (Actions & Decisions)
```

## Performance

- **Compilation**: Policies are compiled once and cached for reuse
- **Evaluation**: Optimized evaluation engine with short-circuit logic
- **Memory**: Efficient AST representation with minimal overhead
- **Concurrency**: Thread-safe evaluation with isolated contexts

## Error Handling

### Compilation Errors
- Syntax errors with line/column information
- Semantic validation with detailed messages
- Best practice recommendations

### Runtime Errors
- Graceful error handling with context preservation
- Detailed error messages for debugging
- Fallback behavior for resilience

## Testing

Run the test suite:

```bash
# Run all tests
python -m pytest services/policy/tests/

# Run specific test file
python -m pytest services/policy/tests/test_engine.py

# Run with coverage
python -m pytest services/policy/tests/ --cov=services/policy/src/
```

## Examples

See the `examples/` directory for comprehensive examples:

- `pii_protection_policy.py` - Complete PII protection policy with testing

Run examples:

```bash
cd services/policy
python examples/pii_protection_policy.py
```

## Integration

### With Anumate Platform

The Policy DSL integrates with other Anumate services:

- **Registry Service**: Policies can be stored and versioned as Capsules
- **Orchestrator**: Policy evaluation during plan execution
- **Audit Service**: Policy decisions logged for compliance
- **Event Bus**: Policy violations trigger CloudEvents

### Configuration

```yaml
# Policy service configuration
policy:
  engine:
    cache_size: 1000
    evaluation_timeout: 5000  # milliseconds
  validation:
    strict_mode: true
    enable_warnings: true
  logging:
    level: INFO
    audit_enabled: true
```

## Security Considerations

- **Input Validation**: All inputs are validated and sanitized
- **Resource Limits**: Evaluation timeouts prevent DoS attacks
- **Audit Trail**: All policy evaluations are logged
- **Access Control**: Policy management requires appropriate permissions

## Contributing

1. Follow the existing code style and patterns
2. Add comprehensive tests for new features
3. Update documentation for API changes
4. Validate policies with the built-in validator

## License

This Policy DSL service is part of the Anumate platform and follows the same licensing terms.