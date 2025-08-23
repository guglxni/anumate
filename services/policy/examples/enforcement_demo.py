"""
Policy Enforcement System Demo

This example demonstrates the complete policy enforcement system including:
- Policy middleware for API endpoints
- Data redaction based on policy rules
- Drift detection for policy compliance
- Policy violation reporting and alerting

Run this demo to see the enforcement system in action.
"""

import asyncio
import time
import json
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# Import policy enforcement components
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from enforcement import create_enforcement_system, setup_fastapi_enforcement
from middleware import PolicyViolation
from violation_reporter import AlertRule, AlertChannel
from drift_detector import DriftAlert


def create_demo_policies() -> Dict[str, str]:
    """Create demonstration policies for the enforcement system."""
    
    policies = {
        'api_access_control': '''policy "API Access Control" {
                description: "Controls access to API endpoints based on user roles and context"
                version: "1.0"
                
                rule "Admin Full Access" {
                    when user.role == "admin" and user.active == true
                    then {
                        allow()
                        log(level="info", message="Admin access granted")
                    }
                    priority: 100
                    enabled: true
                }
                
                rule "User Read Access" {
                    when user.role == "user" and request.method == "GET"
                    then {
                        allow()
                        log(level="info", message="User read access granted")
                    }
                    priority: 80
                }
                
                rule "Block Inactive Users" {
                    when user.active == false
                    then {
                        deny()
                        alert(severity="medium", message="Inactive user attempted access")
                        log(level="warning", message="Access denied for inactive user")
                    }
                    priority: 90
                }
                
                rule "Rate Limit Exceeded" {
                    when context.request_count > 100
                    then {
                        deny()
                        alert(severity="high", message="Rate limit exceeded")
                    }
                    priority: 95
                }
                
                rule "Suspicious Activity" {
                    when context.failed_attempts >= 5
                    then {
                        deny()
                        alert(severity="critical", message="Multiple failed attempts detected")
                        require_approval(approvers=["security-team"])
                    }
                    priority: 110
                }
            }
        ''',
        
        'data_protection': '''policy "Data Protection Policy" {
                description: "Protects sensitive data through detection and redaction"
                version: "2.0"
                
                rule "PII Detection and Redaction" {
                    when contains_pii(data.content) or is_email(data.content) or is_phone(data.content)
                    then {
                        alert(severity="medium", message="PII detected in data")
                        log(level="warning", message="PII access logged for audit")
                        redact(pattern="[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}", replacement="[EMAIL_REDACTED]")
                        redact(pattern="\\d{3}-\\d{3}-\\d{4}", replacement="XXX-XXX-XXXX")
                    }
                    priority: 95
                }
                
                rule "Credit Card Protection" {
                    when is_credit_card(data.content)
                    then {
                        alert(severity="critical", message="Credit card number detected")
                        log(level="error", message="Credit card PII detected")
                        redact(pattern="\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}", replacement="XXXX-XXXX-XXXX-XXXX")
                        require_approval(approvers=["data-protection-officer"])
                    }
                    priority: 100
                }
                
                rule "SSN Protection" {
                    when is_ssn(data.content)
                    then {
                        alert(severity="critical", message="SSN detected")
                        deny()
                    }
                    priority: 105
                }
                
                rule "Admin Override" {
                    when user.role == "admin" and context.override_requested == true
                    then {
                        allow()
                        log(level="warning", message="Admin override for sensitive data access")
                    }
                    priority: 120
                }
            }
        ''',
        
        'compliance_monitoring': '''policy "Compliance Monitoring" {
                description: "Monitors system compliance and generates audit events"
                version: "1.0"
                
                rule "Audit All Admin Actions" {
                    when user.role == "admin"
                    then {
                        log(level="audit", message="Admin action logged", 
                            user_id=user.id, action=request.method, resource=request.path)
                    }
                    priority: 50
                }
                
                rule "Geographic Restrictions" {
                    when context.user_location not_in ["US", "CA", "EU"] and data.classification == "restricted"
                    then {
                        deny()
                        alert(severity="high", message="Geographic restriction violation")
                    }
                    priority: 85
                }
                
                rule "Business Hours Check" {
                    when (context.hour < 8 or context.hour > 18) and data.classification == "confidential"
                    then {
                        alert(severity="medium", message="After-hours access to confidential data")
                        require_approval(approvers=["manager"])
                    }
                    priority: 70
                }
                
                rule "Compliance Logging" {
                    when true
                    then log(level="debug", message="Policy evaluation completed", 
                             timestamp=now(), policy_version="1.0")
                    priority: 1
                }
            }
        '''
    }
    
    return policies


def create_demo_alert_rules():
    """Create demonstration alert rules."""
    
    return [
        AlertRule(
            rule_id="critical_violations",
            name="Critical Policy Violations",
            description="Immediate alerts for critical violations",
            severity_levels=["CRITICAL"],
            channels=[AlertChannel.LOG],
            rate_limit=5,
            escalation_threshold=2
        ),
        
        AlertRule(
            rule_id="pii_violations",
            name="PII Protection Violations",
            description="Alerts for PII-related violations",
            policy_patterns=["*data_protection*"],
            violation_types=["DATA_EXPOSURE", "PII_DETECTED"],
            channels=[AlertChannel.LOG],
            rate_limit=10
        ),
        
        AlertRule(
            rule_id="access_violations",
            name="Access Control Violations",
            description="Alerts for access control violations",
            policy_patterns=["*access_control*"],
            violation_types=["ACCESS_DENIED", "UNAUTHORIZED_ACCESS"],
            channels=[AlertChannel.LOG],
            escalation_threshold=5
        ),
        
        AlertRule(
            rule_id="suspicious_activity",
            name="Suspicious Activity Detection",
            description="Alerts for suspicious user behavior",
            min_severity="HIGH",
            escalation_threshold=3,
            channels=[AlertChannel.LOG]
        )
    ]


async def demo_violation_handler(violation: PolicyViolation):
    """Custom violation handler for demo."""
    print(f"\n🚨 VIOLATION DETECTED:")
    print(f"   Policy: {violation.policy_name}")
    print(f"   Type: {violation.violation_type}")
    print(f"   Severity: {violation.severity}")
    print(f"   User: {violation.user_id}")
    print(f"   Resource: {violation.resource_path}")
    print(f"   Message: {violation.message}")
    print(f"   Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(violation.timestamp))}")


async def demo_drift_handler(alert: DriftAlert):
    """Custom drift alert handler for demo."""
    print(f"\n📊 DRIFT ALERT:")
    print(f"   Policy: {alert.policy_name}")
    print(f"   Drift Type: {alert.drift_type.value}")
    print(f"   Severity: {alert.severity.value}")
    print(f"   Metric: {alert.metric_name}")
    print(f"   Current: {alert.current_value:.3f}")
    print(f"   Expected: {alert.expected_value:.3f}")
    print(f"   Drift: {alert.drift_percentage:.1f}%")
    print(f"   Description: {alert.description}")


def create_demo_app():
    """Create FastAPI demo application with policy enforcement."""
    
    app = FastAPI(title="Policy Enforcement Demo", version="1.0.0")
    
    # Create enforcement system
    policies = create_demo_policies()
    enforcement_system = setup_fastapi_enforcement(
        app=app,
        policies=policies,
        enable_drift_detection=True,
        enable_violation_reporting=True,
        redaction_enabled=True
    )
    
    # Add custom alert rules
    for rule in create_demo_alert_rules():
        enforcement_system.add_alert_rule(rule)
    
    # Add custom handlers
    if enforcement_system.violation_reporter:
        # Note: violation handlers are added via middleware, not directly to reporter
        pass
    
    if enforcement_system.drift_detector:
        enforcement_system.drift_detector.add_alert_handler(demo_drift_handler)
    
    # Mock user authentication middleware
    @app.middleware("http")
    async def mock_auth_middleware(request: Request, call_next):
        # Mock user based on headers
        user_role = request.headers.get("X-User-Role", "user")
        user_id = request.headers.get("X-User-ID", "demo_user")
        user_active = request.headers.get("X-User-Active", "true").lower() == "true"
        
        # Create mock user object
        class MockUser:
            def __init__(self, user_id, role, active):
                self.user_id = user_id
                self.id = user_id
                self.role = role
                self.active = active
                self.tenant_id = "demo_tenant"
                self.permissions = ["read", "write"] if role == "admin" else ["read"]
        
        request.state.user = MockUser(user_id, user_role, user_active)
        request.state.tenant_id = "demo_tenant"
        
        response = await call_next(request)
        return response
    
    # Demo endpoints
    @app.get("/")
    async def root():
        return {"message": "Policy Enforcement Demo API", "version": "1.0.0"}
    
    @app.get("/api/public")
    async def public_endpoint():
        return {"message": "This is a public endpoint", "data": "No sensitive information"}
    
    @app.get("/api/user-data")
    async def user_data(request: Request):
        # This endpoint returns user data that might contain PII
        user = request.state.user
        
        sample_data = {
            "user_id": user.user_id,
            "profile": {
                "name": "John Doe",
                "email": "john.doe@example.com",
                "phone": "555-123-4567",
                "address": "123 Main St, Anytown, USA"
            },
            "preferences": {
                "notifications": True,
                "marketing": False
            }
        }
        
        # Apply redaction policies
        redacted_data = enforcement_system.redact_data(
            data=sample_data,
            policies=['data_protection'],
            context={
                'user': {'role': user.role, 'id': user.user_id},
                'request': {'path': '/api/user-data', 'method': 'GET'}
            }
        )
        
        return redacted_data
    
    @app.post("/api/sensitive-data")
    async def sensitive_data(request: Request, data: dict):
        # This endpoint processes potentially sensitive data
        user = request.state.user
        
        # Evaluate data protection policy
        policy_result = enforcement_system.evaluate_policy(
            'data_protection',
            {
                'data': data,
                'user': {'role': user.role, 'id': user.user_id, 'active': user.active},
                'request': {'method': 'POST', 'path': '/api/sensitive-data'},
                'context': {'classification': 'confidential'}
            }
        )
        
        if not policy_result.get('allowed', True):
            raise HTTPException(status_code=403, detail="Access denied by data protection policy")
        
        return {
            "message": "Data processed successfully",
            "policy_evaluation": {
                "allowed": policy_result.get('allowed'),
                "matched_rules": policy_result.get('matched_rules', []),
                "actions_triggered": len(policy_result.get('actions', []))
            }
        }
    
    @app.get("/api/admin-only")
    async def admin_only(request: Request):
        # This endpoint requires admin access
        user = request.state.user
        
        # Evaluate access control policy
        policy_result = enforcement_system.evaluate_policy(
            'api_access_control',
            {
                'user': {'role': user.role, 'id': user.user_id, 'active': user.active},
                'request': {'method': 'GET', 'path': '/api/admin-only'},
                'context': {'request_count': 50, 'failed_attempts': 0}
            }
        )
        
        if not policy_result.get('allowed', False):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        return {
            "message": "Admin endpoint accessed successfully",
            "sensitive_config": {
                "database_url": "[REDACTED]",
                "api_keys": "[REDACTED]",
                "admin_email": "admin@company.com"
            }
        }
    
    @app.get("/policy/evaluate/{policy_name}")
    async def evaluate_policy_endpoint(policy_name: str, request: Request):
        """Endpoint to manually evaluate a policy."""
        user = request.state.user
        
        test_data = {
            'user': {'role': user.role, 'id': user.user_id, 'active': user.active},
            'request': {'method': 'GET', 'path': f'/policy/evaluate/{policy_name}'},
            'data': {'content': 'Test data for evaluation'},
            'context': {'hour': 14, 'user_location': 'US'}
        }
        
        result = enforcement_system.evaluate_policy(policy_name, test_data)
        return result
    
    @app.get("/policy/metrics/{policy_name}")
    async def policy_metrics(policy_name: str):
        """Get metrics for a specific policy."""
        metrics = enforcement_system.get_policy_metrics(policy_name)
        return metrics
    
    @app.get("/policy/drift-alerts")
    async def drift_alerts():
        """Get active drift alerts."""
        alerts = enforcement_system.get_drift_alerts()
        return {
            "active_alerts": len(alerts),
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "policy_name": alert.policy_name,
                    "drift_type": alert.drift_type.value,
                    "severity": alert.severity.value,
                    "drift_percentage": alert.drift_percentage,
                    "description": alert.description
                }
                for alert in alerts
            ]
        }
    
    @app.get("/policy/violation-report")
    async def violation_report():
        """Generate a violation report."""
        end_time = time.time()
        start_time = end_time - 3600  # Last hour
        
        report = enforcement_system.get_violation_report(
            start_time=start_time,
            end_time=end_time,
            title="Demo Violation Report"
        )
        
        if report:
            return {
                "report_id": report.report_id,
                "title": report.title,
                "period": f"{time.strftime('%H:%M:%S', time.localtime(start_time))} - {time.strftime('%H:%M:%S', time.localtime(end_time))}",
                "total_violations": report.total_violations,
                "unique_policies": report.unique_policies,
                "violations_by_policy": report.violations_by_policy,
                "violations_by_severity": report.violations_by_severity,
                "recommendations": report.recommendations
            }
        else:
            return {"message": "Violation reporting not enabled"}
    
    return app, enforcement_system


async def run_demo_scenarios(enforcement_system):
    """Run demonstration scenarios to show enforcement in action."""
    
    print("\n" + "="*60)
    print("🛡️  POLICY ENFORCEMENT SYSTEM DEMO")
    print("="*60)
    
    # Scenario 1: Admin access (should be allowed)
    print("\n📋 Scenario 1: Admin Access Test")
    print("-" * 30)
    
    admin_data = {
        'user': {'role': 'admin', 'id': 'admin123', 'active': True},
        'request': {'method': 'GET', 'path': '/api/admin-only'},
        'context': {'request_count': 10, 'failed_attempts': 0}
    }
    
    result = enforcement_system.evaluate_policy('api_access_control', admin_data)
    print(f"✅ Admin access result: {'ALLOWED' if result.get('allowed') else 'DENIED'}")
    print(f"   Matched rules: {result.get('matched_rules', [])}")
    
    # Scenario 2: Inactive user (should be denied)
    print("\n📋 Scenario 2: Inactive User Test")
    print("-" * 30)
    
    inactive_data = {
        'user': {'role': 'user', 'id': 'user456', 'active': False},
        'request': {'method': 'GET', 'path': '/api/user-data'},
        'context': {'request_count': 5, 'failed_attempts': 0}
    }
    
    result = enforcement_system.evaluate_policy('api_access_control', inactive_data)
    print(f"❌ Inactive user result: {'ALLOWED' if result.get('allowed') else 'DENIED'}")
    print(f"   Matched rules: {result.get('matched_rules', [])}")
    
    # Scenario 3: PII detection and redaction
    print("\n📋 Scenario 3: PII Detection and Redaction")
    print("-" * 30)
    
    pii_data = {
        'data': {'content': 'Customer info: john.doe@example.com, phone: 555-123-4567, SSN: 123-45-6789'},
        'user': {'role': 'user', 'id': 'user789'},
        'context': {'classification': 'confidential'}
    }
    
    result = enforcement_system.evaluate_policy('data_protection', pii_data)
    print(f"🔍 PII detection result: {'ALLOWED' if result.get('allowed') else 'DENIED'}")
    print(f"   Matched rules: {result.get('matched_rules', [])}")
    print(f"   Actions triggered: {len(result.get('actions', []))}")
    
    # Test redaction
    original_text = "Contact support at help@company.com or call 800-555-0123"
    redacted_text = enforcement_system.redact_data(
        data=original_text,
        policies=['data_protection'],
        context={'user': {'role': 'user'}}
    )
    print(f"   Original: {original_text}")
    print(f"   Redacted: {redacted_text}")
    
    # Scenario 4: Rate limiting violation
    print("\n📋 Scenario 4: Rate Limiting Test")
    print("-" * 30)
    
    rate_limit_data = {
        'user': {'role': 'user', 'id': 'user999', 'active': True},
        'request': {'method': 'GET', 'path': '/api/data'},
        'context': {'request_count': 150, 'failed_attempts': 0}  # Exceeds limit
    }
    
    result = enforcement_system.evaluate_policy('api_access_control', rate_limit_data)
    print(f"⚡ Rate limit result: {'ALLOWED' if result.get('allowed') else 'DENIED'}")
    print(f"   Matched rules: {result.get('matched_rules', [])}")
    
    # Scenario 5: Suspicious activity detection
    print("\n📋 Scenario 5: Suspicious Activity Detection")
    print("-" * 30)
    
    suspicious_data = {
        'user': {'role': 'user', 'id': 'suspicious_user', 'active': True},
        'request': {'method': 'POST', 'path': '/api/login'},
        'context': {'request_count': 10, 'failed_attempts': 6}  # Multiple failures
    }
    
    result = enforcement_system.evaluate_policy('api_access_control', suspicious_data)
    print(f"🚨 Suspicious activity result: {'ALLOWED' if result.get('allowed') else 'DENIED'}")
    print(f"   Matched rules: {result.get('matched_rules', [])}")
    
    # Generate some drift by simulating policy degradation
    print("\n📋 Scenario 6: Drift Detection Simulation")
    print("-" * 30)
    
    if enforcement_system.drift_detector:
        print("🔄 Simulating policy evaluations for drift detection...")
        
        # Simulate baseline establishment
        for i in range(20):
            mock_evaluation = type('MockEval', (), {
                'allowed': True,
                'matched_rules': ['Admin Access'],
                'actions': []
            })()
            
            enforcement_system.drift_detector.record_evaluation(
                policy_name='api_access_control',
                evaluation_result=mock_evaluation,
                evaluation_time=0.05,
                context={}
            )
        
        # Force baseline update
        enforcement_system.drift_detector._update_baselines()
        
        # Simulate drift with slower evaluations
        for i in range(10):
            mock_evaluation = type('MockEval', (), {
                'allowed': True,
                'matched_rules': ['Admin Access'],
                'actions': []
            })()
            
            enforcement_system.drift_detector.record_evaluation(
                policy_name='api_access_control',
                evaluation_result=mock_evaluation,
                evaluation_time=0.5,  # Much slower
                context={}
            )
        
        # Check for drift alerts
        alerts = enforcement_system.get_drift_alerts('api_access_control')
        print(f"📊 Drift alerts generated: {len(alerts)}")
        
        for alert in alerts:
            print(f"   - {alert.drift_type.value}: {alert.drift_percentage:.1f}% drift")
    
    # Show system statistics
    print("\n📊 System Statistics")
    print("-" * 30)
    
    stats = enforcement_system.get_system_stats()
    print(f"   Total evaluations: {stats.total_evaluations}")
    print(f"   Total violations: {stats.total_violations}")
    print(f"   Policies loaded: {stats.policies_loaded}")
    print(f"   Enforcement enabled: {stats.enforcement_enabled}")
    print(f"   Drift detection enabled: {stats.drift_detection_enabled}")
    
    # Generate violation report
    if enforcement_system.violation_reporter:
        print("\n📋 Violation Report Sample")
        print("-" * 30)
        
        end_time = time.time()
        start_time = end_time - 3600
        
        report = enforcement_system.get_violation_report(
            start_time=start_time,
            end_time=end_time,
            title="Demo Report"
        )
        
        if report and report.total_violations > 0:
            print(f"   Report ID: {report.report_id}")
            print(f"   Total violations: {report.total_violations}")
            print(f"   Unique policies: {report.unique_policies}")
            print(f"   Recommendations: {len(report.recommendations)}")
        else:
            print("   No violations recorded in the last hour")
    
    print("\n✨ Demo scenarios completed!")
    print("   Check the logs above for violation and drift alerts.")


def main():
    """Main demo function."""
    
    print("🚀 Starting Policy Enforcement System Demo...")
    
    # Create demo application
    app, enforcement_system = create_demo_app()
    
    # Run demo scenarios
    asyncio.run(run_demo_scenarios(enforcement_system))
    
    print("\n" + "="*60)
    print("🌐 FastAPI Demo Server")
    print("="*60)
    print("\nTo test the API endpoints, run:")
    print("   uvicorn enforcement_demo:app --reload")
    print("\nThen try these endpoints:")
    print("   GET  /                           - Root endpoint")
    print("   GET  /api/public                 - Public endpoint")
    print("   GET  /api/user-data              - User data (with redaction)")
    print("   POST /api/sensitive-data         - Sensitive data processing")
    print("   GET  /api/admin-only             - Admin-only endpoint")
    print("   GET  /policy/health              - Policy system health")
    print("   GET  /policy/stats               - Policy system statistics")
    print("   GET  /policy/drift-alerts        - Active drift alerts")
    print("   GET  /policy/violation-report    - Violation report")
    print("\nUse these headers to simulate different users:")
    print("   X-User-Role: admin|user|guest")
    print("   X-User-ID: your_user_id")
    print("   X-User-Active: true|false")
    print("\nExample curl commands:")
    print('   curl -H "X-User-Role: admin" http://localhost:8000/api/admin-only')
    print('   curl -H "X-User-Role: user" http://localhost:8000/api/user-data')
    print('   curl -H "X-User-Role: guest" http://localhost:8000/api/public')


# FastAPI app instance for uvicorn
app, _ = create_demo_app()


if __name__ == "__main__":
    main()