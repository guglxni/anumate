"""
Example: PII Protection Policy

This example demonstrates a comprehensive PII protection policy using the Policy DSL.
It shows how to detect, redact, and log various types of personally identifiable information.
"""

from services.policy.src.engine import PolicyEngine
from services.policy.src.test_framework import TestCase, TestReportFormatter


def main():
    """Run the PII protection policy example."""
    
    # Define a comprehensive PII protection policy
    pii_policy_source = '''
    policy "PII Protection Policy" {
        description: "Comprehensive policy for detecting and protecting PII data"
        version: "2.0"
        author: "Security Team"
        classification: "security"
        
        rule "Email Address Protection" {
            when is_email(data.content) or data.content matches "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}"
            then {
                log(level="info", message="Email PII detected in content")
                redact(pattern="[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}", replacement="[EMAIL_REDACTED]")
            }
            priority: 90
            enabled: true
        }
        
        rule "Phone Number Protection" {
            when is_phone(data.content) and len(data.content) >= 10
            then {
                log(level="info", message="Phone number PII detected")
                redact(pattern="\\d{3}-\\d{3}-\\d{4}", replacement="XXX-XXX-XXXX")
                redact(pattern="\\(\\d{3}\\)\\s*\\d{3}-\\d{4}", replacement="(XXX) XXX-XXXX")
            }
            priority: 85
        }
        
        rule "Social Security Number Protection" {
            when is_ssn(data.content)
            then {
                alert(severity="high", message="SSN detected - high sensitivity PII")
                log(level="warning", message="SSN PII detected and redacted")
                redact(pattern="\\d{3}-\\d{2}-\\d{4}", replacement="XXX-XX-XXXX")
            }
            priority: 95
        }
        
        rule "Credit Card Protection" {
            when is_credit_card(data.content)
            then {
                alert(severity="critical", message="Credit card number detected")
                log(level="error", message="Credit card PII detected")
                redact(pattern="\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}", replacement="XXXX-XXXX-XXXX-XXXX")
            }
            priority: 100
        }
        
        rule "Admin Override" {
            when user.role == "admin" and user.clearance_level >= 5 and context.override_requested == true
            then {
                log(level="warning", message="Admin PII access override granted")
                allow()
            }
            priority: 110
        }
        
        rule "Sensitive Data Context Check" {
            when contains_pii(data.content) and context.data_classification == "public"
            then {
                alert(severity="medium", message="PII found in public context")
                require_approval(approvers=["data-protection-officer", "security-team"])
            }
            priority: 80
        }
        
        rule "Audit Trail" {
            when user.role in ["analyst", "researcher"] and contains_pii(data.content)
            then {
                log(level="audit", message="PII access by analyst role", 
                    user_id=user.id, timestamp=now(), data_hash=data.hash)
            }
            priority: 70
        }
        
        rule "Geographic Restriction" {
            when contains_pii(data.content) and context.user_location not_in ["US", "CA", "EU"]
            then {
                alert(severity="high", message="PII access from restricted geography")
                deny()
            }
            priority: 105
        }
        
        rule "Time-based Access Control" {
            when contains_pii(data.content) and (context.hour < 8 or context.hour > 18)
            then {
                log(level="warning", message="PII access outside business hours")
                require_approval(approvers=["security-team"])
            }
            priority: 60
        }
        
        rule "Default Logging" {
            when true
            then log(level="debug", message="PII policy evaluation completed", 
                     policy_version="2.0", evaluation_time=now())
            priority: 1
        }
    }
    '''
    
    # Create policy engine and compile the policy
    engine = PolicyEngine()
    
    print("🔒 PII Protection Policy Example")
    print("=" * 50)
    
    # Compile the policy
    print("\n📝 Compiling PII protection policy...")
    compile_result = engine.compile_policy(pii_policy_source, "pii_protection")
    
    if not compile_result.success:
        print(f"❌ Compilation failed: {compile_result.error_message}")
        return
    
    print("✅ Policy compiled successfully!")
    
    # Validate the policy
    print("\n🔍 Validating policy...")
    validate_result = engine.validate_policy(compile_result.policy)
    
    if validate_result.success:
        print("✅ Policy validation passed!")
        if validate_result.validation.warnings:
            print(f"⚠️  {len(validate_result.validation.warnings)} warnings found:")
            for warning in validate_result.validation.warnings:
                print(f"   - {warning}")
    else:
        print("❌ Policy validation failed:")
        for error in validate_result.validation.errors:
            print(f"   - {error}")
        return
    
    # Test the policy with various data samples
    print("\n🧪 Testing policy with sample data...")
    
    test_cases = [
        TestCase(
            name="Email Detection Test",
            description="Test email PII detection and redaction",
            input_data={
                "data": {"content": "Contact me at john.doe@example.com for more info"},
                "user": {"role": "user", "id": "user123"},
                "context": {"data_classification": "internal", "hour": 14}
            },
            expected_allowed=True,
            expected_rules=["Email Address Protection", "Default Logging"]
        ),
        
        TestCase(
            name="Phone Number Test",
            description="Test phone number PII detection",
            input_data={
                "data": {"content": "Call me at 555-123-4567 or (555) 987-6543"},
                "user": {"role": "analyst", "id": "analyst456"},
                "context": {"data_classification": "internal", "hour": 15}
            },
            expected_allowed=True,
            expected_rules=["Phone Number Protection", "Audit Trail", "Default Logging"]
        ),
        
        TestCase(
            name="SSN Detection Test",
            description="Test SSN detection with high alert",
            input_data={
                "data": {"content": "SSN: 123-45-6789"},
                "user": {"role": "user", "id": "user789"},
                "context": {"data_classification": "confidential", "hour": 10}
            },
            expected_allowed=True,
            expected_rules=["Social Security Number Protection", "Default Logging"]
        ),
        
        TestCase(
            name="Credit Card Test",
            description="Test credit card detection with critical alert",
            input_data={
                "data": {"content": "Payment card: 4532-1234-5678-9012"},
                "user": {"role": "user", "id": "user101"},
                "context": {"data_classification": "restricted", "hour": 12}
            },
            expected_allowed=True,
            expected_rules=["Credit Card Protection", "Default Logging"]
        ),
        
        TestCase(
            name="Admin Override Test",
            description="Test admin override for PII access",
            input_data={
                "data": {"content": "Email: admin@company.com, Phone: 555-0123"},
                "user": {"role": "admin", "clearance_level": 5, "id": "admin001"},
                "context": {"override_requested": True, "hour": 11}
            },
            expected_allowed=True,
            expected_rules=["Admin Override", "Email Address Protection", "Phone Number Protection", "Default Logging"]
        ),
        
        TestCase(
            name="Geographic Restriction Test",
            description="Test geographic restriction for PII access",
            input_data={
                "data": {"content": "Personal info: john@example.com"},
                "user": {"role": "user", "id": "user202"},
                "context": {"user_location": "CN", "hour": 14}
            },
            expected_allowed=False,
            expected_rules=["Geographic Restriction", "Email Address Protection", "Default Logging"]
        ),
        
        TestCase(
            name="After Hours Access Test",
            description="Test after-hours PII access requiring approval",
            input_data={
                "data": {"content": "Contact: jane.smith@company.com"},
                "user": {"role": "researcher", "id": "researcher303"},
                "context": {"hour": 22, "data_classification": "internal"}
            },
            expected_allowed=True,
            expected_rules=["Time-based Access Control", "Email Address Protection", "Audit Trail", "Default Logging"]
        ),
        
        TestCase(
            name="Public Context PII Test",
            description="Test PII in public context requiring approval",
            input_data={
                "data": {"content": "Support email: help@company.com"},
                "user": {"role": "user", "id": "user404"},
                "context": {"data_classification": "public", "hour": 13}
            },
            expected_allowed=True,
            expected_rules=["Sensitive Data Context Check", "Email Address Protection", "Default Logging"]
        )
    ]
    
    # Run the tests
    test_result = engine.test_policy(compile_result.policy, test_cases, "PII Protection Test Suite")
    
    if test_result.success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
    
    # Display test report
    print("\n📊 Test Report:")
    print("-" * 30)
    
    report = test_result.test_report
    console_report = TestReportFormatter.format_console(report)
    print(console_report)
    
    # Demonstrate real-time policy evaluation
    print("\n🚀 Real-time Policy Evaluation Examples:")
    print("-" * 40)
    
    sample_data_sets = [
        {
            "description": "Customer support email",
            "data": {
                "data": {"content": "Customer complaint from sarah.johnson@email.com about order #12345"},
                "user": {"role": "support", "id": "support001"},
                "context": {"data_classification": "internal", "hour": 14, "user_location": "US"}
            }
        },
        {
            "description": "Financial document with multiple PII types",
            "data": {
                "data": {"content": "Account holder: John Smith, SSN: 987-65-4321, Phone: (555) 123-4567, Card: 4111-1111-1111-1111"},
                "user": {"role": "analyst", "id": "analyst002"},
                "context": {"data_classification": "restricted", "hour": 10, "user_location": "US"}
            }
        },
        {
            "description": "Clean data with no PII",
            "data": {
                "data": {"content": "Product catalog update: Widget A now costs $29.99"},
                "user": {"role": "user", "id": "user005"},
                "context": {"data_classification": "public", "hour": 15}
            }
        }
    ]
    
    for i, sample in enumerate(sample_data_sets, 1):
        print(f"\n{i}. {sample['description']}:")
        
        eval_result = engine.evaluate_policy(compile_result.policy, sample['data'])
        
        if eval_result.success:
            evaluation = eval_result.evaluation
            
            print(f"   Decision: {'✅ ALLOWED' if evaluation.allowed else '❌ DENIED'}")
            print(f"   Matched Rules: {', '.join(evaluation.matched_rules) if evaluation.matched_rules else 'None'}")
            
            if evaluation.actions:
                print("   Actions Triggered:")
                for action in evaluation.actions:
                    action_type = action['type'].upper()
                    params = action.get('parameters', {})
                    if params:
                        param_str = ', '.join([f"{k}={v}" for k, v in params.items()])
                        print(f"     - {action_type}({param_str})")
                    else:
                        print(f"     - {action_type}()")
        else:
            print(f"   ❌ Evaluation Error: {eval_result.error_message}")
    
    print("\n🎯 Policy DSL Features Demonstrated:")
    print("   ✓ PII detection functions (is_email, is_phone, is_ssn, is_credit_card)")
    print("   ✓ Pattern matching with regex")
    print("   ✓ Multiple action types (log, alert, redact, require_approval, deny)")
    print("   ✓ Rule priorities and conditional logic")
    print("   ✓ Context-aware evaluation")
    print("   ✓ Role-based access control")
    print("   ✓ Geographic and time-based restrictions")
    print("   ✓ Comprehensive testing framework")
    
    print("\n✨ Example completed successfully!")


if __name__ == "__main__":
    main()