#!/usr/bin/env python3
"""Demo script for orchestrator API endpoints."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

import httpx

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API configuration
API_BASE_URL = "http://localhost:8000"
TENANT_ID = str(uuid4())


async def demo_orchestrator_api():
    """Demonstrate orchestrator API endpoints."""
    
    logger.info("=== Anumate Orchestrator API Demo ===")
    logger.info(f"API Base URL: {API_BASE_URL}")
    logger.info(f"Tenant ID: {TENANT_ID}")
    
    # Sample ExecutablePlan
    executable_plan = {
        "plan_hash": "demo-plan-hash-123",
        "version": "1.0.0",
        "metadata": {
            "name": "Demo Plan",
            "description": "A simple demo plan for testing",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "flows": [
            {
                "name": "main_flow",
                "description": "Main execution flow",
                "steps": [
                    {
                        "name": "fetch_data",
                        "tool": "http_request",
                        "parameters": {
                            "url": "https://jsonplaceholder.typicode.com/posts/1",
                            "method": "GET",
                            "headers": {
                                "Content-Type": "application/json"
                            }
                        },
                        "timeout": 30
                    },
                    {
                        "name": "process_data",
                        "tool": "data_transformer",
                        "parameters": {
                            "input": "{{steps.fetch_data.response.body}}",
                            "transformation": "extract_title"
                        }
                    },
                    {
                        "name": "send_notification",
                        "tool": "notification",
                        "parameters": {
                            "message": "Processing completed: {{steps.process_data.result}}",
                            "channel": "email"
                        }
                    }
                ]
            }
        ],
        "security_context": {
            "required_capabilities": [
                "http_request",
                "data_transformer", 
                "notification"
            ],
            "allowed_tools": [
                "http_request",
                "data_transformer",
                "notification"
            ]
        },
        "variables": {
            "notification_email": "demo@example.com",
            "timeout_seconds": 300
        }
    }
    
    async with httpx.AsyncClient() as client:
        
        # 1. Health Check
        logger.info("\n1. Testing Health Check...")
        try:
            response = await client.get(f"{API_BASE_URL}/health")
            logger.info(f"Health Status: {response.status_code}")
            if response.status_code == 200:
                logger.info(f"Health Response: {response.json()}")
            else:
                logger.error(f"Health check failed: {response.text}")
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return
        
        # 2. Execute Plan
        logger.info("\n2. Testing Plan Execution...")
        execution_request = {
            "plan_hash": "demo-plan-hash-123",
            "executable_plan": executable_plan,
            "parameters": {
                "user_id": "demo-user-123",
                "environment": "demo"
            },
            "variables": {
                "notification_email": "demo-override@example.com"
            },
            "dry_run": False,
            "async_execution": True,
            "validate_capabilities": True,
            "timeout": 600,
            "triggered_by": str(uuid4()),
            "correlation_id": f"demo-{uuid4()}"
        }
        
        try:
            response = await client.post(
                f"{API_BASE_URL}/v1/execute",
                json=execution_request,
                headers={"X-Tenant-ID": TENANT_ID}
            )
            logger.info(f"Execute Status: {response.status_code}")
            
            if response.status_code == 202:
                execution_response = response.json()
                logger.info(f"Execution Response: {json.dumps(execution_response, indent=2)}")
                run_id = execution_response.get("run_id")
                
                if run_id:
                    # 3. Get Execution Status
                    logger.info(f"\n3. Testing Execution Status (Run ID: {run_id})...")
                    await asyncio.sleep(1)  # Brief delay
                    
                    status_response = await client.get(
                        f"{API_BASE_URL}/v1/executions/{run_id}",
                        headers={"X-Tenant-ID": TENANT_ID}
                    )
                    logger.info(f"Status Check: {status_response.status_code}")
                    
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        logger.info(f"Status Response: {json.dumps(status_data, indent=2)}")
                    elif status_response.status_code == 404:
                        logger.info("Execution not found (expected in demo mode)")
                    else:
                        logger.error(f"Status check failed: {status_response.text}")
                    
                    # 4. Test Pause Execution
                    logger.info(f"\n4. Testing Execution Pause (Run ID: {run_id})...")
                    pause_response = await client.post(
                        f"{API_BASE_URL}/v1/executions/{run_id}/pause",
                        headers={"X-Tenant-ID": TENANT_ID}
                    )
                    logger.info(f"Pause Status: {pause_response.status_code}")
                    
                    if pause_response.status_code == 200:
                        pause_data = pause_response.json()
                        logger.info(f"Pause Response: {json.dumps(pause_data, indent=2)}")
                    elif pause_response.status_code == 409:
                        logger.info("Pause failed (expected in demo mode)")
                    else:
                        logger.error(f"Pause failed: {pause_response.text}")
                    
                    # 5. Test Resume Execution
                    logger.info(f"\n5. Testing Execution Resume (Run ID: {run_id})...")
                    resume_response = await client.post(
                        f"{API_BASE_URL}/v1/executions/{run_id}/resume",
                        headers={"X-Tenant-ID": TENANT_ID}
                    )
                    logger.info(f"Resume Status: {resume_response.status_code}")
                    
                    if resume_response.status_code == 200:
                        resume_data = resume_response.json()
                        logger.info(f"Resume Response: {json.dumps(resume_data, indent=2)}")
                    elif resume_response.status_code == 409:
                        logger.info("Resume failed (expected in demo mode)")
                    else:
                        logger.error(f"Resume failed: {resume_response.text}")
                    
                    # 6. Test Cancel Execution
                    logger.info(f"\n6. Testing Execution Cancel (Run ID: {run_id})...")
                    cancel_response = await client.post(
                        f"{API_BASE_URL}/v1/executions/{run_id}/cancel",
                        headers={"X-Tenant-ID": TENANT_ID}
                    )
                    logger.info(f"Cancel Status: {cancel_response.status_code}")
                    
                    if cancel_response.status_code == 200:
                        cancel_data = cancel_response.json()
                        logger.info(f"Cancel Response: {json.dumps(cancel_data, indent=2)}")
                    elif cancel_response.status_code == 409:
                        logger.info("Cancel failed (expected in demo mode)")
                    else:
                        logger.error(f"Cancel failed: {cancel_response.text}")
                
            else:
                logger.error(f"Execution failed: {response.text}")
                
        except Exception as e:
            logger.error(f"Execution error: {e}")
        
        # 7. Test Error Cases
        logger.info("\n7. Testing Error Cases...")
        
        # Invalid tenant ID
        try:
            response = await client.post(
                f"{API_BASE_URL}/v1/execute",
                json=execution_request,
                headers={"X-Tenant-ID": "invalid-uuid"}
            )
            logger.info(f"Invalid Tenant ID Status: {response.status_code} (expected 400)")
        except Exception as e:
            logger.error(f"Invalid tenant ID test error: {e}")
        
        # Missing required fields
        try:
            invalid_request = {"plan_hash": ""}  # Missing required fields
            response = await client.post(
                f"{API_BASE_URL}/v1/execute",
                json=invalid_request,
                headers={"X-Tenant-ID": TENANT_ID}
            )
            logger.info(f"Invalid Request Status: {response.status_code} (expected 422)")
        except Exception as e:
            logger.error(f"Invalid request test error: {e}")
        
        # Non-existent execution
        try:
            response = await client.get(
                f"{API_BASE_URL}/v1/executions/non-existent-run-id",
                headers={"X-Tenant-ID": TENANT_ID}
            )
            logger.info(f"Non-existent Execution Status: {response.status_code} (expected 404)")
        except Exception as e:
            logger.error(f"Non-existent execution test error: {e}")
    
    logger.info("\n=== Demo Complete ===")


async def demo_dry_run():
    """Demonstrate dry run execution."""
    
    logger.info("\n=== Dry Run Demo ===")
    
    # Simple plan for dry run
    simple_plan = {
        "plan_hash": "dry-run-plan-123",
        "version": "1.0.0",
        "flows": [
            {
                "name": "validation_flow",
                "steps": [
                    {
                        "name": "validate_input",
                        "tool": "validator",
                        "parameters": {"schema": "user_schema"}
                    }
                ]
            }
        ],
        "security_context": {
            "required_capabilities": ["validator"],
            "allowed_tools": ["validator"]
        }
    }
    
    dry_run_request = {
        "plan_hash": "dry-run-plan-123",
        "executable_plan": simple_plan,
        "dry_run": True,  # Enable dry run
        "validate_capabilities": False,  # Skip capability validation for demo
        "triggered_by": str(uuid4()),
        "correlation_id": f"dry-run-{uuid4()}"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/v1/execute",
                json=dry_run_request,
                headers={"X-Tenant-ID": TENANT_ID}
            )
            logger.info(f"Dry Run Status: {response.status_code}")
            
            if response.status_code == 202:
                dry_run_response = response.json()
                logger.info(f"Dry Run Response: {json.dumps(dry_run_response, indent=2)}")
            else:
                logger.error(f"Dry run failed: {response.text}")
                
        except Exception as e:
            logger.error(f"Dry run error: {e}")


def main():
    """Main demo function."""
    print("Starting Orchestrator API Demo...")
    print("Make sure the orchestrator API server is running on http://localhost:8000")
    print("You can start it with: python -m services.orchestrator.api.main")
    print()
    
    try:
        # Run main demo
        asyncio.run(demo_orchestrator_api())
        
        # Run dry run demo
        asyncio.run(demo_dry_run())
        
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    except Exception as e:
        print(f"Demo failed: {e}")


if __name__ == "__main__":
    main()