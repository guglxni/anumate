"""Demo script for the Plan Compiler service."""

import asyncio
from uuid import uuid4

from src.compiler import PlanCompiler, CapsuleDefinition
from src.models import CompilationRequest


async def main():
    """Run Plan Compiler demo."""
    
    print("🚀 Anumate Plan Compiler Demo")
    print("=" * 50)
    
    # Create a sample Capsule
    capsule = CapsuleDefinition(
        name="payment-processor",
        version="1.2.0",
        description="Process payment transactions with validation and notifications",
        automation={
            "workflow": {
                "id": "payment_flow",
                "name": "Payment Processing Workflow",
                "description": "Complete payment processing with validation",
                "steps": [
                    {
                        "id": "validate_payment",
                        "name": "Validate Payment Request",
                        "type": "action",
                        "action": "validate_payment_data",
                        "tool": "validator",
                        "parameters": {
                            "schema": "payment_v1",
                            "required_fields": ["amount", "currency", "payment_method"]
                        },
                        "timeout": 30,
                        "retry": {
                            "max_attempts": 3,
                            "backoff": {"strategy": "exponential", "base_delay": 1}
                        }
                    },
                    {
                        "id": "check_fraud",
                        "name": "Fraud Detection Check",
                        "type": "action",
                        "action": "fraud_check",
                        "tool": "fraud_detector",
                        "depends_on": ["validate_payment"],
                        "parameters": {
                            "risk_threshold": 0.8,
                            "check_velocity": True
                        },
                        "timeout": 45
                    },
                    {
                        "id": "process_payment",
                        "name": "Process Payment",
                        "type": "action",
                        "action": "charge_payment_method",
                        "tool": "payment_gateway",
                        "depends_on": ["validate_payment", "check_fraud"],
                        "parameters": {
                            "gateway": "stripe",
                            "capture": True
                        },
                        "timeout": 60,
                        "retry": {
                            "max_attempts": 2,
                            "backoff": {"strategy": "fixed", "delay": 5}
                        }
                    },
                    {
                        "id": "send_confirmation",
                        "name": "Send Confirmation",
                        "type": "action",
                        "action": "send_notification",
                        "tool": "notification",
                        "depends_on": ["process_payment"],
                        "parameters": {
                            "template": "payment_confirmation",
                            "channels": ["email", "sms"]
                        },
                        "timeout": 15
                    },
                    {
                        "id": "update_records",
                        "name": "Update Transaction Records",
                        "type": "action",
                        "action": "update_transaction",
                        "tool": "database",
                        "depends_on": ["process_payment"],
                        "parameters": {
                            "table": "transactions",
                            "update_inventory": True
                        },
                        "timeout": 20
                    }
                ],
                "parallel": True,
                "max_concurrency": 3,
                "on_failure": "rollback",
                "rollback_steps": ["refund_payment", "notify_failure"]
            }
        },
        tools=[
            "validator",
            "fraud_detector", 
            "payment_gateway",
            "notification",
            "database"
        ],
        policies=[
            "pci_compliance",
            "data_protection",
            "fraud_prevention"
        ],
        dependencies=[
            "payment-validator@>=2.1.0",
            "fraud-detector@~1.5.0",
            "notification-service@>=1.0.0"
        ],
        metadata={
            "required_capabilities": [
                "payment.process",
                "fraud.check",
                "notification.send",
                "data.write"
            ],
            "requires_approval": True,
            "approval_rules": ["payment_approval_policy"],
            "data_classification": "sensitive",
            "pii_handling": "encrypt_at_rest",
            "resources": {
                "cpu": "500m",
                "memory": "1Gi",
                "network_access": True,
                "external_services": ["stripe_api", "twilio_api"]
            }
        }
    )
    
    print(f"📦 Sample Capsule: {capsule.name} v{capsule.version}")
    print(f"   Description: {capsule.description}")
    print(f"   Tools: {', '.join(capsule.tools)}")
    print(f"   Dependencies: {len(capsule.dependencies)}")
    print(f"   Workflow Steps: {len(capsule.automation['workflow']['steps'])}")
    print()
    
    # Create Plan Compiler
    compiler = PlanCompiler()
    
    # Create compilation request
    request = CompilationRequest(
        capsule_id=uuid4(),
        optimization_level="aggressive",
        validate_dependencies=False,  # Skip for demo
        cache_result=True,
        variables={
            "environment": "production",
            "region": "us-east-1",
            "payment_gateway": "stripe"
        },
        configuration={
            "timeout_multiplier": 1.5,
            "enable_monitoring": True,
            "log_level": "info"
        }
    )
    
    print("⚙️  Compilation Settings:")
    print(f"   Optimization Level: {request.optimization_level}")
    print(f"   Variables: {request.variables}")
    print(f"   Configuration: {request.configuration}")
    print()
    
    # Compile the Capsule
    print("🔄 Compiling Capsule to ExecutablePlan...")
    
    tenant_id = uuid4()
    user_id = uuid4()
    
    result = await compiler.compile_capsule(
        capsule=capsule,
        tenant_id=tenant_id,
        compiled_by=user_id,
        request=request
    )
    
    print(f"✅ Compilation completed in {result.compilation_time:.2f}s")
    print()
    
    if result.success:
        plan = result.plan
        
        print("📋 ExecutablePlan Details:")
        print(f"   Plan Hash: {plan.plan_hash}")
        print(f"   Name: {plan.name} v{plan.version}")
        print(f"   Tenant ID: {plan.tenant_id}")
        print(f"   Flows: {len(plan.flows)}")
        print()
        
        # Show main flow details
        main_flow = plan.flows[0]
        print(f"🔀 Main Flow: {main_flow.name}")
        print(f"   Flow ID: {main_flow.flow_id}")
        print(f"   Steps: {len(main_flow.steps)}")
        print(f"   Parallel Execution: {main_flow.parallel_execution}")
        print(f"   Max Concurrency: {main_flow.max_concurrency}")
        print()
        
        # Show execution steps
        print("📝 Execution Steps:")
        for i, step in enumerate(main_flow.steps, 1):
            deps = f" (depends on: {', '.join(step.depends_on)})" if step.depends_on else ""
            print(f"   {i}. {step.name} [{step.step_id}]{deps}")
            print(f"      Tool: {step.tool}, Action: {step.action}")
            if step.timeout:
                print(f"      Timeout: {step.timeout}s")
        print()
        
        # Show security context
        print("🔒 Security Context:")
        print(f"   Allowed Tools: {', '.join(plan.security_context.allowed_tools)}")
        print(f"   Required Capabilities: {', '.join(plan.security_context.required_capabilities)}")
        print(f"   Requires Approval: {plan.security_context.requires_approval}")
        print(f"   Policy References: {', '.join(plan.security_context.policy_refs)}")
        print()
        
        # Show resource requirements
        print("💻 Resource Requirements:")
        print(f"   CPU: {plan.resource_requirements.cpu}")
        print(f"   Memory: {plan.resource_requirements.memory}")
        print(f"   Network Access: {plan.resource_requirements.network_access}")
        print(f"   External Services: {', '.join(plan.resource_requirements.external_services)}")
        print()
        
        # Show compilation metadata
        print("📊 Compilation Metadata:")
        print(f"   Compiler Version: {plan.metadata.compiler_version}")
        print(f"   Optimization Level: {plan.metadata.optimization_level}")
        print(f"   Compiled At: {plan.metadata.compiled_at}")
        print(f"   Source Capsule: {plan.metadata.source_capsule_name} v{plan.metadata.source_capsule_version}")
        if plan.metadata.optimization_notes:
            print(f"   Optimization Notes: {', '.join(plan.metadata.optimization_notes)}")
        print()
        
        # Validate the plan
        print("🔍 Validating ExecutablePlan...")
        from src.validator import PlanValidator
        
        validator = PlanValidator()
        validation_result = await validator.validate_plan(plan)
        
        print(f"   Valid: {validation_result.valid}")
        print(f"   Errors: {len(validation_result.errors)}")
        print(f"   Warnings: {len(validation_result.warnings)}")
        print(f"   Security Issues: {len(validation_result.security_issues)}")
        print(f"   Estimated Duration: {validation_result.estimated_duration}s")
        print(f"   Estimated Cost: ${validation_result.estimated_cost:.4f}")
        
        if validation_result.errors:
            print("\n❌ Validation Errors:")
            for error in validation_result.errors:
                print(f"   - {error}")
        
        if validation_result.warnings:
            print("\n⚠️  Validation Warnings:")
            for warning in validation_result.warnings:
                print(f"   - {warning}")
        
        if validation_result.security_issues:
            print("\n🔐 Security Issues:")
            for issue in validation_result.security_issues:
                print(f"   - {issue}")
        
        print()
        print("🎉 Plan Compiler Demo Complete!")
        
    else:
        print("❌ Compilation Failed!")
        print(f"   Errors: {len(result.errors)}")
        for error in result.errors:
            print(f"   - {error}")
        
        if result.warnings:
            print(f"   Warnings: {len(result.warnings)}")
            for warning in result.warnings:
                print(f"   - {warning}")


if __name__ == "__main__":
    asyncio.run(main())