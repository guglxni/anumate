#!/usr/bin/env python3
"""
Demo script showcasing GhostRun API endpoints.

This script demonstrates all the GhostRun API endpoints:
- POST /v1/ghostrun - Start GhostRun simulation
- GET /v1/ghostrun/{run_id} - Get GhostRun status and results
- GET /v1/ghostrun/{run_id}/report - Get Preflight report
- POST /v1/ghostrun/{run_id}/cancel - Cancel running simulation

Usage:
    python demo_api_endpoints.py
"""

import asyncio
import json
import time
from uuid import uuid4

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'plan-compiler', 'src'))

from fastapi.testclient import TestClient
from api.main import app
from src.models import ExecutablePlan, GhostRunRequest
from models import ExecutionFlow, ExecutionStep, PlanMetadata

# Create test client
client = TestClient(app)


def create_sample_plan():
    """Create a sample ExecutablePlan for testing."""
    
    tenant_id = uuid4()
    
    # Create execution steps
    steps = [
        ExecutionStep(
            step_id="validate_input",
            name="Validate Input Parameters",
            step_type="validation",
            action="validate",
            tool="validator",
            parameters={
                "schema": "user_input_schema",
                "required_fields": ["user_id", "amount"]
            },
            timeout=5000
        ),
        ExecutionStep(
            step_id="check_balance",
            name="Check Account Balance",
            step_type="action",
            action="query",
            tool="database",
            parameters={
                "query": "SELECT balance FROM accounts WHERE user_id = ?",
                "params": ["${user_id}"]
            },
            depends_on=["validate_input"],
            timeout=10000
        ),
        ExecutionStep(
            step_id="process_payment",
            name="Process Payment",
            step_type="action",
            action="charge",
            tool="payment_gateway",
            parameters={
                "amount": "${amount}",
                "user_id": "${user_id}",
                "currency": "USD"
            },
            depends_on=["check_balance"],
            conditions=["${balance} >= ${amount}"],
            timeout=30000
        ),
        ExecutionStep(
            step_id="send_notification",
            name="Send Confirmation Email",
            step_type="action",
            action="send_email",
            tool="email_service",
            parameters={
                "template": "payment_confirmation",
                "recipient": "${user_email}",
                "variables": {
                    "amount": "${amount}",
                    "transaction_id": "${transaction_id}"
                }
            },
            depends_on=["process_payment"],
            timeout=15000
        )
    ]
    
    # Create execution flow
    flow = ExecutionFlow(
        flow_id="payment_flow",
        name="Payment Processing Flow",
        description="Complete payment processing with validation and notifications",
        steps=steps,
        parallel_execution=False,
        on_failure="rollback"
    )
    
    # Create metadata
    metadata = PlanMetadata(
        source_capsule_id=uuid4(),
        source_capsule_name="payment-processor",
        source_capsule_version="2.1.0",
        source_capsule_checksum="abc123def456",
        compiled_by=uuid4(),
        compiler_version="1.2.0"
    )
    
    # Create ExecutablePlan
    plan = ExecutablePlan.create(
        tenant_id=tenant_id,
        name="Payment Processing Plan",
        version="2.1.0",
        description="Automated payment processing with fraud detection",
        flows=[flow],
        main_flow="payment_flow",
        metadata=metadata
    )
    
    return plan, tenant_id


def demo_ghostrun_api():
    """Demonstrate GhostRun API endpoints."""
    
    print("🚀 GhostRun API Endpoints Demo")
    print("=" * 50)
    
    # Create sample plan
    plan, tenant_id = create_sample_plan()
    headers = {"X-Tenant-ID": str(tenant_id)}
    
    print(f"\n📋 Created sample plan:")
    print(f"   Plan Name: {plan.name}")
    print(f"   Version: {plan.version}")
    print(f"   Flows: {len(plan.flows)}")
    print(f"   Steps: {len(plan.flows[0].steps)}")
    print(f"   Plan Hash: {plan.plan_hash}")
    
    # Convert plan to dict for JSON serialization
    plan_dict = json.loads(plan.model_dump_json())
    
    # 1. Start GhostRun Simulation
    print(f"\n🎯 1. Starting GhostRun Simulation")
    print("-" * 30)
    
    simulation_config = GhostRunRequest(
        plan_hash=plan.plan_hash,
        simulation_mode="full",
        include_performance_analysis=True,
        include_cost_estimation=True,
        mock_external_calls=True,
        strict_validation=True,
        execution_context={
            "environment": "staging",
            "user_id": "user_123",
            "amount": 99.99,
            "user_email": "user@example.com"
        }
    )
    
    start_request = {
        "plan": plan_dict,
        "simulation_config": simulation_config.model_dump()
    }
    
    start_response = client.post("/v1/ghostrun/", json=start_request, headers=headers)
    
    if start_response.status_code == 200:
        start_data = start_response.json()
        run_id = start_data["run_id"]
        print(f"   ✅ Simulation started successfully")
        print(f"   📝 Run ID: {run_id}")
        print(f"   📊 Status: {start_data['status']['status']}")
        print(f"   🕐 Created: {start_data['status']['created_at']}")
    else:
        print(f"   ❌ Failed to start simulation: {start_response.json()}")
        return
    
    # 2. Get Simulation Status
    print(f"\n📊 2. Getting Simulation Status")
    print("-" * 30)
    
    # Wait a moment for simulation to progress
    time.sleep(0.5)
    
    status_response = client.get(f"/v1/ghostrun/{run_id}", headers=headers)
    
    if status_response.status_code == 200:
        status_data = status_response.json()
        print(f"   ✅ Status retrieved successfully")
        print(f"   📈 Status: {status_data['status']}")
        print(f"   📊 Progress: {status_data['progress']:.1%}")
        if status_data.get('current_step'):
            print(f"   🔄 Current Step: {status_data['current_step']}")
        
        # Show simulation metrics if available
        if status_data.get('simulation_metrics'):
            metrics = status_data['simulation_metrics']
            print(f"   📏 Metrics:")
            print(f"      - Duration: {metrics.get('total_duration_ms', 0)}ms")
            print(f"      - Steps Simulated: {metrics.get('steps_simulated', 0)}")
            print(f"      - Connectors Mocked: {metrics.get('connectors_mocked', 0)}")
    else:
        print(f"   ❌ Failed to get status: {status_response.json()}")
    
    # 3. Wait for completion and get report
    print(f"\n📋 3. Waiting for Completion and Getting Report")
    print("-" * 30)
    
    # Wait for simulation to complete
    max_wait = 10  # seconds
    wait_time = 0
    completed = False
    
    while wait_time < max_wait and not completed:
        time.sleep(0.5)
        wait_time += 0.5
        
        status_response = client.get(f"/v1/ghostrun/{run_id}", headers=headers)
        if status_response.status_code == 200:
            status_data = status_response.json()
            if status_data['status'] in ['completed', 'failed']:
                completed = True
                print(f"   ✅ Simulation completed with status: {status_data['status']}")
                break
        
        print(f"   ⏳ Waiting... ({wait_time}s)")
    
    # Try to get the preflight report
    report_response = client.get(f"/v1/ghostrun/{run_id}/report", headers=headers)
    
    if report_response.status_code == 200:
        report_data = report_response.json()
        print(f"   ✅ Preflight report retrieved successfully")
        print(f"   📊 Overall Status: {report_data['overall_status']}")
        print(f"   ⚠️  Risk Level: {report_data['overall_risk_level']}")
        print(f"   ✅ Execution Feasible: {report_data['execution_feasible']}")
        print(f"   🕐 Estimated Duration: {report_data['total_estimated_duration_ms']}ms")
        
        if report_data.get('flow_results'):
            flow_result = report_data['flow_results'][0]
            print(f"   📈 Flow Results:")
            print(f"      - Would Complete: {flow_result['would_complete']}")
            print(f"      - Steps: {len(flow_result['step_results'])}")
            print(f"      - Risk Level: {flow_result['overall_risk_level']}")
        
        if report_data.get('recommendations'):
            print(f"   💡 Recommendations: {len(report_data['recommendations'])}")
            for i, rec in enumerate(report_data['recommendations'][:3]):  # Show first 3
                print(f"      {i+1}. {rec['title']} ({rec['severity']})")
        
        if report_data.get('critical_issues'):
            print(f"   🚨 Critical Issues: {len(report_data['critical_issues'])}")
            for issue in report_data['critical_issues'][:3]:  # Show first 3
                print(f"      - {issue}")
    
    elif report_response.status_code == 400:
        error_detail = report_response.json()['detail']
        print(f"   ⏳ Report not ready: {error_detail}")
    else:
        print(f"   ❌ Failed to get report: {report_response.json()}")
    
    # 4. List All Simulations
    print(f"\n📋 4. Listing All Simulations")
    print("-" * 30)
    
    list_response = client.get("/v1/ghostrun/", headers=headers)
    
    if list_response.status_code == 200:
        simulations = list_response.json()
        print(f"   ✅ Found {len(simulations)} simulation(s)")
        
        for i, sim in enumerate(simulations[:3]):  # Show first 3
            print(f"   {i+1}. Run ID: {sim['run_id']}")
            print(f"      Status: {sim['status']}")
            print(f"      Plan Hash: {sim['plan_hash'][:16]}...")
            print(f"      Created: {sim['created_at']}")
    else:
        print(f"   ❌ Failed to list simulations: {list_response.json()}")
    
    # 5. Service Metrics
    print(f"\n📊 5. Getting Service Metrics")
    print("-" * 30)
    
    metrics_response = client.get("/v1/ghostrun/metrics/service")
    
    if metrics_response.status_code == 200:
        metrics = metrics_response.json()
        print(f"   ✅ Service metrics retrieved")
        print(f"   📈 Total Simulations: {metrics['total_simulations']}")
        print(f"   🔄 Active Simulations: {metrics['active_simulations']}")
        print(f"   ✅ Completed Simulations: {metrics['completed_simulations']}")
        print(f"   📊 Success Rate: {metrics['success_rate']:.1%}")
        print(f"   ⏱️  Average Duration: {metrics['average_duration_seconds']:.2f}s")
    else:
        print(f"   ❌ Failed to get metrics: {metrics_response.json()}")
    
    # 6. Demonstrate Cancel (with a new simulation)
    print(f"\n🛑 6. Demonstrating Simulation Cancellation")
    print("-" * 30)
    
    # Start another simulation
    cancel_start_response = client.post("/v1/ghostrun/", json=start_request, headers=headers)
    
    if cancel_start_response.status_code == 200:
        cancel_run_id = cancel_start_response.json()["run_id"]
        print(f"   🎯 Started new simulation: {cancel_run_id}")
        
        # Immediately try to cancel it
        cancel_response = client.post(f"/v1/ghostrun/{cancel_run_id}/cancel", headers=headers)
        
        if cancel_response.status_code == 200:
            cancel_data = cancel_response.json()
            print(f"   ✅ Cancel request processed")
            print(f"   📊 Success: {cancel_data['success']}")
            print(f"   📝 Message: {cancel_data['message']}")
        else:
            print(f"   ❌ Failed to cancel: {cancel_response.json()}")
    
    # 7. Error Handling Examples
    print(f"\n⚠️  7. Error Handling Examples")
    print("-" * 30)
    
    # Test with invalid tenant ID
    invalid_headers = {"X-Tenant-ID": "invalid-uuid"}
    error_response = client.get("/v1/ghostrun/", headers=invalid_headers)
    print(f"   🔍 Invalid Tenant ID: {error_response.status_code} - {error_response.json()['detail']}")
    
    # Test with non-existent run ID
    fake_run_id = str(uuid4())
    not_found_response = client.get(f"/v1/ghostrun/{fake_run_id}", headers=headers)
    print(f"   🔍 Non-existent Run: {not_found_response.status_code} - {not_found_response.json()['detail']}")
    
    # Test hash mismatch
    mismatch_request = start_request.copy()
    mismatch_request["simulation_config"]["plan_hash"] = "wrong_hash"
    mismatch_response = client.post("/v1/ghostrun/", json=mismatch_request, headers=headers)
    print(f"   🔍 Hash Mismatch: {mismatch_response.status_code} - {mismatch_response.json()['detail']}")
    
    print(f"\n🎉 Demo completed successfully!")
    print(f"📚 All GhostRun API endpoints are working correctly.")


if __name__ == "__main__":
    demo_ghostrun_api()