"""Demo script for GhostRun simulation engine."""

import asyncio
from uuid import uuid4

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plan-compiler', 'src'))

from models import (
    ExecutablePlan,
    ExecutionFlow,
    ExecutionStep,
    PlanMetadata,
    ResourceRequirement,
    SecurityContext,
)
from src.models import GhostRunRequest
from src.service import GhostRunService


async def create_sample_payment_plan() -> ExecutablePlan:
    """Create a sample payment processing plan."""
    
    # Define execution steps
    steps = [
        ExecutionStep(
            step_id="validate_payment",
            name="Validate Payment Details",
            step_type="action",
            action="validate",
            tool="stripe",
            parameters={
                "card_number": "4242424242424242",
                "amount": 2500,  # $25.00
                "currency": "usd"
            },
            timeout=5000,
            retry_policy={"max_attempts": 3, "delay": 1000}
        ),
        ExecutionStep(
            step_id="charge_payment",
            name="Process Payment Charge",
            step_type="action",
            action="charge",
            tool="stripe",
            parameters={
                "amount": 2500,
                "currency": "usd",
                "description": "Demo payment processing"
            },
            depends_on=["validate_payment"],
            timeout=10000,
            retry_policy={"max_attempts": 2, "delay": 2000}
        ),
        ExecutionStep(
            step_id="send_confirmation",
            name="Send Confirmation Email",
            step_type="action",
            action="send",
            tool="sendgrid",
            parameters={
                "to": "customer@example.com",
                "subject": "Payment Confirmation",
                "template": "payment_confirmation"
            },
            depends_on=["charge_payment"],
            timeout=3000
        ),
        ExecutionStep(
            step_id="update_database",
            name="Update Payment Records",
            step_type="action",
            action="insert",
            tool="postgresql",
            parameters={
                "table": "payments",
                "data": {
                    "amount": 2500,
                    "status": "completed",
                    "timestamp": "now()"
                }
            },
            depends_on=["charge_payment"],
            timeout=2000
        ),
        ExecutionStep(
            step_id="send_slack_notification",
            name="Notify Team on Slack",
            step_type="action",
            action="send",
            tool="slack",
            parameters={
                "channel": "#payments",
                "message": "Payment of $25.00 processed successfully"
            },
            depends_on=["update_database", "send_confirmation"],
            timeout=3000
        )
    ]
    
    # Create execution flow
    flow = ExecutionFlow(
        flow_id="payment_processing_flow",
        name="Payment Processing Workflow",
        description="Complete payment processing with notifications",
        steps=steps,
        parallel_execution=True,
        max_concurrency=3,
        on_failure="rollback"
    )
    
    # Create plan metadata
    metadata = PlanMetadata(
        source_capsule_id=uuid4(),
        source_capsule_name="payment-processor-v2",
        source_capsule_version="2.1.0",
        source_capsule_checksum="sha256:abc123def456",
        compiled_by=uuid4(),
        compiler_version="1.2.0",
        estimated_duration=15,
        estimated_cost=0.05
    )
    
    # Define resource requirements
    resource_requirements = ResourceRequirement(
        cpu="200m",
        memory="256Mi",
        network_access=True,
        external_services=["stripe", "sendgrid", "postgresql", "slack"]
    )
    
    # Define security context
    security_context = SecurityContext(
        allowed_tools=["stripe", "sendgrid", "postgresql", "slack"],
        required_capabilities=["payment_processing", "email_sending"],
        requires_approval=True,
        approval_rules=["payment_amount_over_1000"],
        data_classification="sensitive",
        pii_handling="redact"
    )
    
    # Create the executable plan
    plan = ExecutablePlan.create(
        tenant_id=uuid4(),
        name="Payment Processing Plan",
        version="2.1.0",
        description="Comprehensive payment processing with error handling and notifications",
        flows=[flow],
        main_flow="payment_processing_flow",
        metadata=metadata,
        resource_requirements=resource_requirements,
        security_context=security_context,
        configuration={
            "environment": "staging",
            "retry_enabled": True,
            "notifications_enabled": True
        },
        variables={
            "payment_gateway": "stripe",
            "notification_channel": "#payments",
            "database_timeout": 5000
        }
    )
    
    return plan


async def create_high_risk_plan() -> ExecutablePlan:
    """Create a plan with high-risk operations for testing."""
    
    steps = [
        ExecutionStep(
            step_id="delete_production_data",
            name="Delete Production Database",
            step_type="action",
            action="delete",
            tool="postgresql",
            parameters={
                "database": "production",
                "table": "all_user_data",
                "where": "created_at < '2023-01-01'"
            },
            timeout=30000  # 30 seconds
        ),
        ExecutionStep(
            step_id="large_refund",
            name="Process Large Refund",
            step_type="action",
            action="refund",
            tool="stripe",
            parameters={
                "amount": 100000,  # $1,000.00
                "reason": "bulk_refund"
            },
            depends_on=["delete_production_data"],
            timeout=15000
        ),
        ExecutionStep(
            step_id="terminate_instances",
            name="Terminate All EC2 Instances",
            step_type="action",
            action="terminate_instance",
            tool="aws",
            parameters={
                "instance_ids": ["all"],
                "force": True
            },
            depends_on=["large_refund"],
            timeout=60000
        )
    ]
    
    flow = ExecutionFlow(
        flow_id="high_risk_flow",
        name="High Risk Operations",
        steps=steps,
        on_failure="stop"
    )
    
    metadata = PlanMetadata(
        source_capsule_id=uuid4(),
        source_capsule_name="dangerous-operations",
        source_capsule_version="1.0.0",
        source_capsule_checksum="danger123",
        compiled_by=uuid4(),
        compiler_version="1.0.0"
    )
    
    security_context = SecurityContext(
        allowed_tools=["postgresql", "stripe", "aws"],
        requires_approval=True,
        approval_rules=["critical_operations", "production_access"]
    )
    
    plan = ExecutablePlan.create(
        tenant_id=uuid4(),
        name="High Risk Operations Plan",
        version="1.0.0",
        flows=[flow],
        main_flow="high_risk_flow",
        metadata=metadata,
        security_context=security_context
    )
    
    return plan


async def demo_basic_simulation():
    """Demonstrate basic GhostRun simulation."""
    
    print("🚀 GhostRun Demo: Basic Payment Processing Simulation")
    print("=" * 60)
    
    # Create sample plan
    plan = await create_sample_payment_plan()
    print(f"📋 Created plan: {plan.name} v{plan.version}")
    print(f"   - Plan hash: {plan.plan_hash[:16]}...")
    print(f"   - Total steps: {sum(len(flow.steps) for flow in plan.flows)}")
    print(f"   - Main flow: {plan.main_flow}")
    
    # Create simulation request
    request = GhostRunRequest(
        plan_hash=plan.plan_hash,
        simulation_mode="full",
        include_performance_analysis=True,
        include_cost_estimation=True,
        mock_external_calls=True,
        connector_overrides={
            "stripe": {
                "typical_latency_ms": 150,
                "risk_level": "medium"
            },
            "sendgrid": {
                "typical_latency_ms": 100,
                "risk_level": "low"
            }
        }
    )
    
    # Start simulation
    service = GhostRunService()
    tenant_id = uuid4()
    
    print(f"\n🔄 Starting simulation for tenant: {tenant_id}")
    status = await service.start_simulation(tenant_id, plan, request)
    print(f"   - Run ID: {status.run_id}")
    print(f"   - Status: {status.status}")
    
    # Wait for completion (in real scenario, this would be polled)
    print("\n⏳ Waiting for simulation to complete...")
    await asyncio.sleep(2)  # Give time for background processing
    
    # Get final status
    final_status = await service.get_simulation_status(status.run_id)
    if final_status:
        print(f"   - Final status: {final_status.status}")
        
        if final_status.report:
            report = final_status.report
            print(f"\n📊 Simulation Results:")
            print(f"   - Overall status: {report.overall_status}")
            print(f"   - Risk level: {report.overall_risk_level}")
            print(f"   - Execution feasible: {report.execution_feasible}")
            print(f"   - Total estimated duration: {report.total_estimated_duration_ms}ms")
            print(f"   - Steps with issues: {report.steps_with_issues}/{report.total_steps}")
            
            if report.critical_issues:
                print(f"\n⚠️  Critical Issues:")
                for issue in report.critical_issues[:3]:
                    print(f"   - {issue}")
            
            if report.warnings:
                print(f"\n⚡ Warnings:")
                for warning in report.warnings[:3]:
                    print(f"   - {warning}")
            
            if report.recommendations:
                print(f"\n💡 Recommendations:")
                for rec in report.recommendations[:2]:
                    print(f"   - {rec.title}: {rec.description}")
            
            # Show flow results
            print(f"\n🔍 Flow Analysis:")
            for flow_result in report.flow_results:
                print(f"   Flow: {flow_result.flow_name}")
                print(f"   - Would complete: {flow_result.would_complete}")
                print(f"   - Execution time: {flow_result.total_execution_time_ms}ms")
                print(f"   - Risk level: {flow_result.overall_risk_level}")
                
                # Show step details
                for step_result in flow_result.step_results[:3]:  # Show first 3 steps
                    print(f"     Step: {step_result.step_name}")
                    print(f"     - Would execute: {step_result.would_execute}")
                    print(f"     - Execution time: {step_result.execution_time_ms}ms")
                    print(f"     - Risk level: {step_result.risk_level}")
                    
                    if step_result.connector_responses:
                        for response in step_result.connector_responses:
                            print(f"     - Connector: {response.connector_name} ({response.response_time_ms}ms)")


async def demo_high_risk_simulation():
    """Demonstrate high-risk operation simulation."""
    
    print("\n\n🔥 GhostRun Demo: High-Risk Operations Simulation")
    print("=" * 60)
    
    # Create high-risk plan
    plan = await create_high_risk_plan()
    print(f"⚠️  Created high-risk plan: {plan.name}")
    print(f"   - Contains dangerous operations: DELETE, REFUND, TERMINATE")
    
    # Create simulation request
    request = GhostRunRequest(
        plan_hash=plan.plan_hash,
        simulation_mode="security",  # Focus on security analysis
        strict_validation=True,
        mock_external_calls=True
    )
    
    # Start simulation
    service = GhostRunService()
    tenant_id = uuid4()
    
    print(f"\n🔄 Starting high-risk simulation...")
    status = await service.start_simulation(tenant_id, plan, request)
    
    # Wait for completion
    await asyncio.sleep(2)
    
    # Get results
    final_status = await service.get_simulation_status(status.run_id)
    if final_status and final_status.report:
        report = final_status.report
        
        print(f"\n🚨 High-Risk Analysis Results:")
        print(f"   - Overall risk level: {report.overall_risk_level}")
        print(f"   - Execution feasible: {report.execution_feasible}")
        print(f"   - High-risk steps: {report.high_risk_steps}")
        
        print(f"\n🔒 Security Analysis:")
        if report.security_issues:
            for issue in report.security_issues:
                print(f"   - {issue}")
        
        if report.critical_issues:
            print(f"\n💥 Critical Issues:")
            for issue in report.critical_issues:
                print(f"   - {issue}")
        
        print(f"\n🛡️  Recommendations:")
        for rec in report.recommendations:
            if rec.severity in ["high", "critical"]:
                print(f"   - {rec.title} ({rec.severity})")
                print(f"     {rec.description}")
                if rec.suggested_actions:
                    print(f"     Actions: {', '.join(rec.suggested_actions[:2])}")


async def demo_service_metrics():
    """Demonstrate service metrics and management."""
    
    print("\n\n📈 GhostRun Demo: Service Metrics")
    print("=" * 60)
    
    service = GhostRunService()
    
    # Get service metrics
    metrics = await service.get_simulation_metrics()
    
    print(f"📊 Service Statistics:")
    print(f"   - Total simulations: {metrics['total_simulations']}")
    print(f"   - Active simulations: {metrics['active_simulations']}")
    print(f"   - Completed simulations: {metrics['completed_simulations']}")
    print(f"   - Success rate: {metrics['success_rate']:.2%}")
    print(f"   - Average duration: {metrics['average_duration_seconds']:.2f}s")
    
    # List simulations for a tenant
    tenant_id = uuid4()
    simulations = await service.list_simulations(tenant_id)
    print(f"\n📋 Simulations for tenant {str(tenant_id)[:8]}...")
    print(f"   - Found {len(simulations)} simulations")
    
    # Cleanup old runs
    cleaned = await service.cleanup_old_runs(max_age_hours=1)
    print(f"\n🧹 Cleanup Results:")
    print(f"   - Cleaned up {cleaned} old simulation runs")


async def main():
    """Run all demos."""
    
    print("🎯 GhostRun Simulation Engine Demo")
    print("Demonstrating dry-run simulation capabilities for ExecutablePlans")
    
    try:
        await demo_basic_simulation()
        await demo_high_risk_simulation()
        await demo_service_metrics()
        
        print("\n\n✅ Demo completed successfully!")
        print("\nKey GhostRun Features Demonstrated:")
        print("  ✓ ExecutablePlan simulation without side effects")
        print("  ✓ Mock connector responses with realistic latencies")
        print("  ✓ Risk analysis and security validation")
        print("  ✓ Performance bottleneck identification")
        print("  ✓ Comprehensive preflight reports")
        print("  ✓ Service metrics and management")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())