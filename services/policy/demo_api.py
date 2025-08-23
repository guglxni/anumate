"""Demo script for Policy Service API endpoints."""

import asyncio
import json
from uuid import uuid4

from src.engine import PolicyEngine
from src.policy_service import PolicyService


async def demo_policy_api():
    """Demonstrate Policy Service functionality."""
    print("=== Policy Service API Demo ===\n")
    
    # Create a policy engine
    engine = PolicyEngine()
    
    # Demo 1: Policy Compilation
    print("1. Policy Compilation Demo")
    print("-" * 30)
    
    sample_policy = '''
policy "access-control" {
    description: "Basic access control policy"
    
    rule "allow-admins" {
        priority: 100
        when user.role == "admin"
        then allow()
    }
    
    rule "allow-read-for-users" {
        priority: 50
        when user.role == "user" and action == "read"
        then allow()
    }
    
    rule "deny-write-for-users" {
        priority: 50
        when user.role == "user" and action == "write"
        then deny()
    }
    
    rule "require-approval-for-sensitive" {
        priority: 75
        when resource.sensitive == true
        then {
            require_approval(approvers=["security-team"])
            log(message="Sensitive resource access requested")
        }
    }
}
    '''.strip()
    
    compile_result = engine.compile_policy(sample_policy)
    if compile_result.success:
        print("✅ Policy compiled successfully!")
        print(f"   Policy name: {compile_result.policy.name}")
        print(f"   Number of rules: {len(compile_result.policy.rules)}")
    else:
        print(f"❌ Compilation failed: {compile_result.error_message}")
    
    print()
    
    # Demo 2: Policy Validation
    print("2. Policy Validation Demo")
    print("-" * 30)
    
    validate_result = engine.validate_policy(compile_result.policy)
    if validate_result.success:
        print("✅ Policy validation passed!")
        if validate_result.validation and validate_result.validation.issues:
            print(f"   Issues found: {len(validate_result.validation.issues)}")
            for issue in validate_result.validation.issues:
                print(f"   - {issue.level.value}: {issue.message}")
        else:
            print("   No validation issues found")
    else:
        print(f"❌ Validation failed: {validate_result.error_message}")
    
    print()
    
    # Demo 3: Policy Evaluation
    print("3. Policy Evaluation Demo")
    print("-" * 30)
    
    test_cases = [
        {
            "name": "Admin access",
            "data": {"user": {"role": "admin"}, "action": "write", "resource": {"id": "doc1"}},
            "expected": True
        },
        {
            "name": "User read access",
            "data": {"user": {"role": "user"}, "action": "read", "resource": {"id": "doc1"}},
            "expected": True
        },
        {
            "name": "User write access",
            "data": {"user": {"role": "user"}, "action": "write", "resource": {"id": "doc1"}},
            "expected": False
        },
        {
            "name": "Sensitive resource access",
            "data": {"user": {"role": "user"}, "action": "read", "resource": {"id": "secret", "sensitive": True}},
            "expected": True  # Allowed but requires approval
        }
    ]
    
    for test_case in test_cases:
        print(f"Testing: {test_case['name']}")
        
        eval_result = engine.evaluate_policy(sample_policy, test_case["data"])
        if eval_result.success:
            result = eval_result.evaluation
            print(f"   Result: {'✅ ALLOWED' if result.allowed else '❌ DENIED'}")
            print(f"   Matched rules: {', '.join(result.matched_rules)}")
            if result.actions:
                print(f"   Actions: {len(result.actions)} action(s)")
                for action in result.actions:
                    print(f"     - {action['type']}")
        else:
            print(f"   ❌ Evaluation failed: {eval_result.error_message}")
        
        print()
    
    # Demo 4: Policy Testing Framework
    print("4. Policy Testing Framework Demo")
    print("-" * 40)
    
    from src.test_framework import TestCase
    
    test_cases_framework = [
        TestCase(
            name="Admin should have full access",
            description="Administrators should be allowed to perform any action",
            input_data={"user": {"role": "admin"}, "action": "delete"},
            expected_result=True
        ),
        TestCase(
            name="Users can read but not write",
            description="Regular users should be able to read but not write",
            input_data={"user": {"role": "user"}, "action": "read"},
            expected_result=True
        ),
        TestCase(
            name="Users cannot write",
            description="Regular users should not be able to write",
            input_data={"user": {"role": "user"}, "action": "write"},
            expected_result=False
        )
    ]
    
    test_result = engine.test_policy(sample_policy, test_cases_framework, "Access Control Test Suite")
    
    if test_result.success:
        report = test_result.test_report
        print(f"✅ Test suite completed!")
        print(f"   Suite: {report.suite_name}")
        print(f"   Total tests: {report.total_tests}")
        print(f"   Passed: {report.passed_tests}")
        print(f"   Failed: {report.failed_tests}")
        print(f"   Overall result: {'✅ PASSING' if report.is_passing else '❌ FAILING'}")
        
        if not report.is_passing:
            print("\n   Failed tests:")
            for test_result in report.test_results:
                if not test_result.passed:
                    print(f"     - {test_result.test_name}: {test_result.error_message}")
    else:
        print(f"❌ Testing failed: {test_result.error_message}")
    
    print()
    
    # Demo 5: PII Detection
    print("5. PII Detection Demo")
    print("-" * 25)
    
    pii_policy = '''
policy "pii-protection" {
    description: "Protect PII in log messages"
    
    rule "block-email-in-logs" {
        when is_email(log_message)
        then {
            deny()
            redact(fields=["log_message"])
            alert(severity="high", message="PII detected in logs")
        }
    }
    
    rule "block-phone-in-logs" {
        when is_phone(log_message)
        then {
            deny()
            redact(fields=["log_message"])
        }
    }
    
    rule "allow-clean-logs" {
        when not contains_pii(log_message)
        then allow()
    }
}
    '''.strip()
    
    pii_test_cases = [
        {
            "name": "Clean log message",
            "data": {"log_message": "User logged in successfully"},
        },
        {
            "name": "Log with email",
            "data": {"log_message": "User john.doe@example.com logged in"},
        },
        {
            "name": "Log with phone number",
            "data": {"log_message": "Contact support at 555-123-4567"},
        },
        {
            "name": "Log with multiple PII",
            "data": {"log_message": "User john.doe@example.com (phone: 555-123-4567) updated profile"},
        }
    ]
    
    for test_case in pii_test_cases:
        print(f"Testing: {test_case['name']}")
        
        eval_result = engine.evaluate_policy(pii_policy, test_case["data"])
        if eval_result.success:
            result = eval_result.evaluation
            print(f"   Result: {'✅ ALLOWED' if result.allowed else '❌ BLOCKED (PII detected)'}")
            if result.matched_rules:
                print(f"   Matched rules: {', '.join(result.matched_rules)}")
            if result.actions:
                action_types = [action['type'] for action in result.actions]
                print(f"   Actions: {', '.join(action_types)}")
        else:
            print(f"   ❌ Evaluation failed: {eval_result.error_message}")
        
        print()
    
    print("=== Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(demo_policy_api())