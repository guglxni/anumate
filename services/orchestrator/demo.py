"""Demo of Orchestrator service Portia integration."""

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from src.models import ExecutionRequest, RetryPolicy, ExecutionHook
from src.service import OrchestratorService


async def demo_portia_integration():
    """Demonstrate Portia Runtime integration."""
    print("🚀 Anumate Orchestrator - Portia Integration Demo")
    print("=" * 50)
    
    # Initialize orchestrator service
    orchestrator = OrchestratorService()
    
    # Sample ExecutablePlan (from plan-compiler)
    executable_plan = {
        "plan_id": str(uuid4()),
        "plan_hash": "demo123abc456def",
        "tenant_id": str(uuid4()),
        "name": "Demo Automation Plan",
        "version": "1.0.0",
        "description": "Demo plan for Portia integration testing",
        "flows": [
            {
                "flow_id": "main_flow",
                "name": "Main Automation Flow",
                "description": "Primary execution flow",
                "steps": [
                    {
                        "step_id": "validate_input",
                        "name": "Validate Input Data",
                        "description": "Validate incoming request data",
                        "step_type": "action",
                        "action": "validate_data",
                        "tool": "data_validator",
                        "parameters": {
                            "schema": "user_registration",
                            "strict": True
                        },
                        "timeout": 30,
                        "retry_policy": {
                            "max_attempts": 2,
                            "initial_delay": 1.0
                        }
                    },
                    {
                        "step_id": "send_welcome_email",
                        "name": "Send Welcome Email",
                        "description": "Send welcome email to new user",
                        "step_type": "action",
                        "action": "send_email",
                        "tool": "email_connector",
                        "parameters": {
                            "template": "welcome_email",
                            "personalize": True
                        },
                        "depends_on": ["validate_input"],
                        "conditions": ["validate_input.success == true"],
                        "timeout": 60
                    },
                    {
                        "step_id": "create_user_account",
                        "name": "Create User Account",
                        "description": "Create user account in system",
                        "step_type": "action",
                        "action": "create_account",
                        "tool": "user_management",
                        "parameters": {
                            "auto_activate": True,
                            "send_confirmation": False
                        },
                        "depends_on": ["validate_input"],
                        "timeout": 45
                    },
                    {
                        "step_id": "log_completion",
                        "name": "Log Completion",
                        "description": "Log successful user registration",
                        "step_type": "action",
                        "action": "log_event",
                        "tool": "audit_logger",
                        "parameters": {
                            "event_type": "user_registered",
                            "level": "info"
                        },
                        "depends_on": ["send_welcome_email", "create_user_account"],
                        "conditions": [
                            "send_welcome_email.success == true",
                            "create_user_account.success == true"
                        ]
                    }
                ],
                "parallel_execution": True,
                "max_concurrency": 2
            }
        ],
        "main_flow": "main_flow",
        "resource_requirements": {
            "cpu": "100m",
            "memory": "256Mi",
            "network_access": True,
            "external_services": ["email_service", "user_db"]
        },
        "security_context": {
            "allowed_tools": [
                "data_validator",
                "email_connector", 
                "user_management",
                "audit_logger"
            ],
            "required_capabilities": [
                "execute_plan",
                "send_notification",
                "write_data"
            ],
            "requires_approval": False
        },
        "variables": {
            "environment": "demo",
            "debug_mode": True,
            "notification_enabled": True
        },
        "configuration": {
            "timeout": 300,
            "retry_policy": {
                "max_attempts": 3,
                "initial_delay": 2.0,
                "max_delay": 30.0,
                "exponential_base": 2.0,
                "jitter": True
            }
        }
    }
    
    # Create execution request
    tenant_id = uuid4()
    user_id = uuid4()
    
    execution_request = ExecutionRequest(
        plan_hash=executable_plan["plan_hash"],
        tenant_id=tenant_id,
        parameters={
            "user_email": "demo@example.com",
            "user_name": "Demo User",
            "registration_source": "web_form"
        },
        variables={
            "custom_greeting": "Welcome to our platform!",
            "locale": "en_US"
        },
        dry_run=False,
        async_execution=True,
        hooks=[
            ExecutionHook(
                hook_type="pre_execution",
                enabled=True,
                configuration={"log_level": "info"}
            ),
            ExecutionHook(
                hook_type="post_execution", 
                enabled=True,
                configuration={"notify_completion": True}
            )
        ],
        validate_capabilities=True,
        retry_policy=RetryPolicy(
            max_attempts=2,
            initial_delay=1.0,
            max_delay=10.0
        ),
        timeout=180,
        triggered_by=user_id,
        correlation_id=f"demo-{uuid4()}"
    )
    
    print(f"📋 ExecutablePlan: {executable_plan['name']}")
    print(f"   Plan Hash: {executable_plan['plan_hash']}")
    print(f"   Flows: {len(executable_plan['flows'])}")
    print(f"   Steps: {len(executable_plan['flows'][0]['steps'])}")
    print()
    
    print(f"🎯 Execution Request:")
    print(f"   Tenant ID: {tenant_id}")
    print(f"   User ID: {user_id}")
    print(f"   Correlation ID: {execution_request.correlation_id}")
    print(f"   Validate Capabilities: {execution_request.validate_capabilities}")
    print(f"   Hooks: {len(execution_request.hooks)}")
    print()
    
    try:
        print("🔄 Starting plan execution...")
        
        # Execute the plan
        response = await orchestrator.execute_plan(
            request=execution_request,
            executable_plan=executable_plan
        )
        
        print(f"✅ Execution Response:")
        print(f"   Success: {response.success}")
        print(f"   Run ID: {response.run_id}")
        print(f"   Status: {response.status}")
        print(f"   Correlation ID: {response.correlation_id}")
        
        if response.error_message:
            print(f"   Error: {response.error_message}")
        
        print()
        
        if response.success and response.run_id:
            print("📊 Checking execution status...")
            
            # Get execution status
            status = await orchestrator.get_execution_status(
                run_id=response.run_id,
                tenant_id=tenant_id
            )
            
            if status:
                print(f"   Run ID: {status.run_id}")
                print(f"   Status: {status.status}")
                print(f"   Progress: {status.progress:.1%}")
                print(f"   Current Step: {status.current_step}")
                print(f"   Started At: {status.started_at}")
                
                if status.pending_clarifications:
                    print(f"   Pending Clarifications: {len(status.pending_clarifications)}")
                    for clarification in status.pending_clarifications:
                        print(f"     - {clarification.title}")
            
            print()
            
            # Demo pause/resume functionality
            print("⏸️  Testing pause/resume functionality...")
            
            paused = await orchestrator.pause_execution(response.run_id, tenant_id)
            print(f"   Paused: {paused}")
            
            if paused:
                await asyncio.sleep(1)  # Brief pause
                
                resumed = await orchestrator.resume_execution(response.run_id, tenant_id)
                print(f"   Resumed: {resumed}")
        
    except Exception as e:
        print(f"❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("🎉 Demo completed!")


if __name__ == "__main__":
    asyncio.run(demo_portia_integration())