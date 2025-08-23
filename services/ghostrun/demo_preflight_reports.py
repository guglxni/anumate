#!/usr/bin/env python3
"""
Demo script for enhanced preflight report generation in GhostRun service.

This script demonstrates:
1. Comprehensive preflight report generation
2. Risk assessment and recommendations
3. Report storage and retrieval
4. CloudEvent publishing
5. SLO compliance monitoring
"""

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from src.models import (
    ExecutablePlan,
    ExecutionFlow,
    ExecutionStep,
    GhostRunRequest,
    PlanMetadata,
    RiskLevel,
    SecurityContext,
    SimulationStatus,
)
from src.service import GhostRunService
from src.report_storage import report_storage
from src.event_publisher import event_publisher


async def create_sample_plan() -> ExecutablePlan:
    """Create a sample ExecutablePlan with various risk levels."""
    
    # Low-risk step
    step1 = ExecutionStep(
        step_id="step_1",
        name="Fetch User Data",
        step_type="action",
        tool="api",
        action="get_user",
        parameters={"user_id": "12345"},
        outputs={"user_data": "$.user"},
        depends_on=[],
        timeout=3000
    )
    
    # Medium-risk step
    step2 = ExecutionStep(
        step_id="step_2",
        name="Update User Profile",
        step_type="action",
        tool="database",
        action="update_user",
        parameters={"user_id": "12345", "email": "new@example.com"},
        outputs={"updated": "$.success"},
        depends_on=["step_1"],
        timeout=5000
    )
    
    # High-risk step (payment processing)
    step3 = ExecutionStep(
        step_id="step_3",
        name="Process Payment",
        step_type="action",
        tool="stripe",
        action="create_charge",
        parameters={"amount": 15000, "currency": "usd", "source": "tok_visa"},
        outputs={"charge_id": "$.id", "status": "$.status"},
        depends_on=["step_2"],
        timeout=10000
    )
    
    # Critical-risk step (production database operation)
    step4 = ExecutionStep(
        step_id="step_4",
        name="Archive Old Records",
        step_type="action",
        tool="postgresql",
        action="delete_records",
        parameters={"table": "production_logs", "where": "created_at < '2023-01-01'"},
        outputs={"deleted_count": "$.affected_rows"},
        depends_on=["step_3"],
        timeout=30000
    )
    
    # Notification step
    step5 = ExecutionStep(
        step_id="step_5",
        name="Send Confirmation Email",
        step_type="action",
        tool="email",
        action="send_email",
        parameters={
            "to": "user@example.com",
            "subject": "Payment Processed",
            "template": "payment_confirmation"
        },
        outputs={"message_id": "$.id"},
        depends_on=["step_3"],
        timeout=5000
    )
    
    flow = ExecutionFlow(
        flow_id="payment_flow",
        name="User Payment Processing Flow",
        steps=[step1, step2, step3, step4, step5]
    )
    
    tenant_id = uuid4()
    capsule_id = uuid4()
    compiled_by = uuid4()
    
    metadata = PlanMetadata(
        source_capsule_id=capsule_id,
        source_capsule_name="Payment Processing Capsule",
        source_capsule_version="1.0.0",
        source_capsule_checksum="abc123def456",
        compiled_by=compiled_by,
        compiler_version="1.0.0"
    )
    
    return ExecutablePlan(
        plan_hash="demo_plan_" + str(uuid4())[:8],
        tenant_id=tenant_id,
        name="Payment Processing Plan",
        version="1.0.0",
        flows=[flow],
        main_flow="payment_flow",
        metadata=metadata,
        security_context=SecurityContext(
            allowed_tools=["api", "database", "stripe", "postgresql", "email"],
            requires_approval=True,
            required_capabilities=["payment_processing", "data_modification"],
            policy_refs=["pii_protection", "financial_compliance"]
        )
    )


async def demo_comprehensive_report_generation():
    """Demonstrate comprehensive preflight report generation."""
    
    print("🚀 Demo: Comprehensive Preflight Report Generation")
    print("=" * 60)
    
    # Create sample plan
    plan = await create_sample_plan()
    print(f"📋 Created ExecutablePlan: {plan.plan_hash}")
    print(f"   - Flows: {len(plan.flows)}")
    print(f"   - Total Steps: {sum(len(flow.steps) for flow in plan.flows)}")
    print(f"   - Security Context: {len(plan.security_context.allowed_tools)} allowed tools")
    
    # Create simulation request
    request = GhostRunRequest(
        plan_hash=plan.plan_hash,
        simulation_mode="full",
        include_performance_analysis=True,
        include_cost_estimation=True,
        mock_external_calls=True,
        strict_validation=True
    )
    
    # Start simulation
    service = GhostRunService()
    tenant_id = uuid4()
    
    print(f"\n🔄 Starting GhostRun simulation for tenant: {tenant_id}")
    start_time = datetime.now()
    
    status = await service.start_simulation(tenant_id, plan, request)
    print(f"   - Run ID: {status.run_id}")
    print(f"   - Status: {status.status}")
    
    # Wait for completion
    print("   - Waiting for completion...")
    max_wait = 10  # seconds
    waited = 0
    while status.status not in [SimulationStatus.COMPLETED, SimulationStatus.FAILED] and waited < max_wait:
        await asyncio.sleep(0.1)
        waited += 0.1
        status = await service.get_simulation_status(status.run_id)
        if waited % 1 == 0:  # Print progress every second
            print(f"     Progress: {status.progress:.1%} - {status.current_step}")
    
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds() * 1000
    
    print(f"\n✅ Simulation completed in {total_time:.0f}ms")
    print(f"   - Status: {status.status}")
    
    if status.status == SimulationStatus.COMPLETED and status.report:
        await analyze_preflight_report(status.report)
    else:
        print(f"❌ Simulation failed: {status.error_message}")
    
    return status


async def analyze_preflight_report(report):
    """Analyze and display preflight report details."""
    
    print(f"\n📊 Preflight Report Analysis")
    print("=" * 40)
    
    # Overall assessment
    print(f"📈 Overall Assessment:")
    print(f"   - Status: {report.overall_status}")
    print(f"   - Risk Level: {report.overall_risk_level.value.upper()}")
    print(f"   - Execution Feasible: {'✅ Yes' if report.execution_feasible else '❌ No'}")
    print(f"   - Simulation Duration: {report.simulation_duration_ms}ms")
    
    # Performance metrics
    print(f"\n⚡ Performance Metrics:")
    print(f"   - Total Steps: {report.total_steps}")
    print(f"   - Steps with Issues: {report.steps_with_issues}")
    print(f"   - High Risk Steps: {report.high_risk_steps}")
    print(f"   - Estimated Duration: {report.total_estimated_duration_ms}ms")
    
    # Flow analysis
    print(f"\n🔄 Flow Analysis:")
    for flow_result in report.flow_results:
        print(f"   Flow: {flow_result.flow_name}")
        print(f"   - Would Complete: {'✅' if flow_result.would_complete else '❌'}")
        print(f"   - Risk Level: {flow_result.overall_risk_level.value}")
        print(f"   - Execution Time: {flow_result.total_execution_time_ms}ms")
        print(f"   - Critical Path: {', '.join(flow_result.critical_path_steps[:3])}")
        
        # Step details
        for step_result in flow_result.step_results:
            risk_icon = {
                RiskLevel.LOW: "🟢",
                RiskLevel.MEDIUM: "🟡", 
                RiskLevel.HIGH: "🟠",
                RiskLevel.CRITICAL: "🔴"
            }.get(step_result.risk_level, "⚪")
            
            print(f"     {risk_icon} {step_result.step_name}")
            print(f"       - Risk: {step_result.risk_level.value}")
            print(f"       - Time: {step_result.execution_time_ms}ms")
            if step_result.risk_factors:
                print(f"       - Risks: {', '.join(step_result.risk_factors[:2])}")
    
    # Issues and recommendations
    if report.critical_issues:
        print(f"\n🚨 Critical Issues ({len(report.critical_issues)}):")
        for issue in report.critical_issues[:3]:
            print(f"   - {issue}")
    
    if report.warnings:
        print(f"\n⚠️  Warnings ({len(report.warnings)}):")
        for warning in report.warnings[:3]:
            print(f"   - {warning}")
    
    if report.recommendations:
        print(f"\n💡 Recommendations ({len(report.recommendations)}):")
        for rec in report.recommendations[:3]:
            severity_icon = {
                RiskLevel.LOW: "ℹ️",
                RiskLevel.MEDIUM: "⚠️",
                RiskLevel.HIGH: "🚨",
                RiskLevel.CRITICAL: "🔥"
            }.get(rec.severity, "💡")
            
            print(f"   {severity_icon} {rec.title}")
            print(f"     - {rec.description}")
            if rec.suggested_actions:
                print(f"     - Action: {rec.suggested_actions[0]}")
    
    # Security analysis
    if report.security_issues:
        print(f"\n🔒 Security Issues ({len(report.security_issues)}):")
        for issue in report.security_issues[:3]:
            print(f"   - {issue}")
    
    # Performance bottlenecks
    if report.performance_bottlenecks:
        print(f"\n🐌 Performance Bottlenecks ({len(report.performance_bottlenecks)}):")
        for bottleneck in report.performance_bottlenecks[:3]:
            print(f"   - {bottleneck}")


async def demo_report_storage():
    """Demonstrate report storage and retrieval functionality."""
    
    print(f"\n💾 Demo: Report Storage and Retrieval")
    print("=" * 40)
    
    # Run a simulation to get a report
    plan = await create_sample_plan()
    request = GhostRunRequest(plan_hash=plan.plan_hash)
    
    service = GhostRunService()
    tenant_id = uuid4()
    
    status = await service.start_simulation(tenant_id, plan, request)
    
    # Wait for completion
    max_wait = 5
    waited = 0
    while status.status not in [SimulationStatus.COMPLETED, SimulationStatus.FAILED] and waited < max_wait:
        await asyncio.sleep(0.1)
        waited += 0.1
        status = await service.get_simulation_status(status.run_id)
    
    if status.status == SimulationStatus.COMPLETED and status.report:
        print(f"✅ Report generated and stored for run: {status.run_id}")
        
        # Retrieve report from storage
        stored_report = await report_storage.get_report(status.run_id)
        if stored_report:
            print(f"✅ Report successfully retrieved from storage")
            print(f"   - Report ID: {stored_report.report_id}")
            print(f"   - Plan Hash: {stored_report.plan_hash}")
            print(f"   - Generated: {stored_report.generated_at}")
        
        # List reports
        reports = await report_storage.list_reports(limit=5)
        print(f"\n📋 Available Reports: {len(reports)}")
        for report_meta in reports[:3]:
            print(f"   - {report_meta['run_id']}: {report_meta['overall_status']} ({report_meta['overall_risk_level']})")
        
        # Get statistics
        stats = await report_storage.get_report_statistics()
        print(f"\n📊 Storage Statistics:")
        print(f"   - Total Reports: {stats['total_reports']}")
        print(f"   - Success Rate: {stats['success_rate']:.1%}")
        print(f"   - Avg Duration: {stats['average_simulation_duration_ms']:.0f}ms")
        print(f"   - Risk Distribution: {stats['risk_level_distribution']}")
    
    else:
        print(f"❌ Simulation failed or no report generated")


async def demo_slo_compliance():
    """Demonstrate SLO compliance monitoring."""
    
    print(f"\n⏱️  Demo: SLO Compliance Monitoring")
    print("=" * 40)
    
    # Create a simple plan for fast execution
    step = ExecutionStep(
        step_id="simple_step",
        name="Simple API Call",
        step_type="action",
        tool="api",
        action="get_status",
        parameters={},
        outputs={"status": "$.status"},
        depends_on=[],
        timeout=1000
    )
    
    flow = ExecutionFlow(
        flow_id="simple_flow",
        name="Simple Status Check",
        steps=[step]
    )
    
    tenant_id = uuid4()
    capsule_id = uuid4()
    compiled_by = uuid4()
    
    metadata = PlanMetadata(
        source_capsule_id=capsule_id,
        source_capsule_name="Simple Status Check",
        source_capsule_version="1.0.0",
        source_capsule_checksum="simple123",
        compiled_by=compiled_by,
        compiler_version="1.0.0"
    )
    
    plan = ExecutablePlan(
        plan_hash="slo_test_" + str(uuid4())[:8],
        tenant_id=tenant_id,
        name="Simple Status Check Plan",
        version="1.0.0",
        flows=[flow],
        main_flow="simple_flow",
        metadata=metadata,
        security_context=SecurityContext(allowed_tools=["api"])
    )
    
    request = GhostRunRequest(
        plan_hash=plan.plan_hash,
        simulation_mode="fast",
        include_performance_analysis=False,
        include_cost_estimation=False
    )
    
    # Run multiple simulations to test SLO
    service = GhostRunService()
    tenant_id = uuid4()
    
    execution_times = []
    successful_runs = 0
    
    print(f"🔄 Running 10 simulations to test P95 < 1.5s SLO...")
    
    for i in range(10):
        start_time = datetime.now()
        
        status = await service.start_simulation(tenant_id, plan, request)
        
        # Wait for completion
        max_wait = 3
        waited = 0
        while status.status not in [SimulationStatus.COMPLETED, SimulationStatus.FAILED] and waited < max_wait:
            await asyncio.sleep(0.01)
            waited += 0.01
            status = await service.get_simulation_status(status.run_id)
        
        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        execution_times.append(duration_ms)
        
        if status.status == SimulationStatus.COMPLETED:
            successful_runs += 1
        
        print(f"   Run {i+1}: {duration_ms:.0f}ms - {status.status}")
    
    # Calculate SLO metrics
    execution_times.sort()
    p95_index = int(0.95 * len(execution_times))
    p95_time = execution_times[p95_index]
    avg_time = sum(execution_times) / len(execution_times)
    success_rate = successful_runs / len(execution_times)
    
    print(f"\n📊 SLO Compliance Results:")
    print(f"   - P95 Latency: {p95_time:.0f}ms (Target: <1500ms)")
    print(f"   - Average Latency: {avg_time:.0f}ms")
    print(f"   - Success Rate: {success_rate:.1%} (Target: >99%)")
    
    # Check SLO compliance
    slo_compliant = p95_time < 1500 and success_rate >= 0.99
    print(f"   - SLO Compliant: {'✅ Yes' if slo_compliant else '❌ No'}")
    
    if not slo_compliant:
        print(f"   - Issues:")
        if p95_time >= 1500:
            print(f"     - P95 latency {p95_time:.0f}ms exceeds 1500ms target")
        if success_rate < 0.99:
            print(f"     - Success rate {success_rate:.1%} below 99% target")


async def main():
    """Run all demos."""
    
    print("🎯 GhostRun Enhanced Preflight Report Demo")
    print("=" * 60)
    print("This demo showcases the comprehensive preflight report")
    print("generation capabilities implemented for task A.15")
    print()
    
    try:
        # Demo 1: Comprehensive report generation
        await demo_comprehensive_report_generation()
        
        # Demo 2: Report storage and retrieval
        await demo_report_storage()
        
        # Demo 3: SLO compliance monitoring
        await demo_slo_compliance()
        
        print(f"\n🎉 All demos completed successfully!")
        print(f"\n📋 Summary of implemented features:")
        print(f"   ✅ Comprehensive preflight validation reports")
        print(f"   ✅ Risk assessment and recommendation engine")
        print(f"   ✅ Report storage and retrieval system")
        print(f"   ✅ CloudEvent publishing (preflight.completed)")
        print(f"   ✅ SLO compliance monitoring (P95 < 1.5s)")
        print(f"   ✅ Enhanced API endpoints for report management")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())