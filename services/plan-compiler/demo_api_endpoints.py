#!/usr/bin/env python3
"""
Demo script showing the Plan Compiler API endpoints in action.

This script demonstrates all four required API endpoints:
1. POST /v1/compile - Compile Capsule to ExecutablePlan
2. GET /v1/plans/{plan_hash} - Retrieve compiled ExecutablePlan
3. POST /v1/plans/{plan_hash}/validate - Validate ExecutablePlan
4. GET /v1/compile/status/{job_id} - Get compilation job status
"""

import asyncio
import json
import time
from uuid import uuid4

import httpx
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class PlanCompilerAPIDemo:
    """Demo client for Plan Compiler API endpoints."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.tenant_id = str(uuid4())
        self.user_id = str(uuid4())
        
        # Standard headers for all requests
        self.headers = {
            "X-Tenant-ID": self.tenant_id,
            "X-User-ID": self.user_id,
            "Content-Type": "application/json"
        }
        
        logger.info(
            "Demo client initialized",
            base_url=base_url,
            tenant_id=self.tenant_id,
            user_id=self.user_id
        )
    
    def create_sample_capsule(self) -> dict:
        """Create a sample Capsule definition for testing."""
        
        return {
            "id": str(uuid4()),
            "name": "payment-processing-capsule",
            "version": "1.2.0",
            "description": "Automated payment processing with fraud detection",
            "automation": {
                "steps": [
                    {
                        "id": "validate_payment",
                        "name": "Validate Payment Request",
                        "type": "action",
                        "action": "validate",
                        "tool": "validator",
                        "parameters": {
                            "schema": "payment_request_v1",
                            "required_fields": ["amount", "currency", "merchant_id"]
                        },
                        "timeout": 30
                    },
                    {
                        "id": "fraud_check",
                        "name": "Fraud Detection Check",
                        "type": "action",
                        "action": "analyze",
                        "tool": "fraud_detector",
                        "depends_on": ["validate_payment"],
                        "parameters": {
                            "risk_threshold": 0.7,
                            "check_velocity": True,
                            "check_geolocation": True
                        },
                        "timeout": 45
                    },
                    {
                        "id": "process_payment",
                        "name": "Process Payment",
                        "type": "action",
                        "action": "charge",
                        "tool": "payment_gateway",
                        "depends_on": ["fraud_check"],
                        "conditions": ["fraud_check.risk_score < 0.7"],
                        "parameters": {
                            "gateway": "stripe",
                            "capture": True
                        },
                        "retry_policy": {
                            "max_attempts": 3,
                            "backoff": {
                                "strategy": "exponential",
                                "initial_delay": 1,
                                "max_delay": 10
                            }
                        },
                        "timeout": 60
                    },
                    {
                        "id": "send_confirmation",
                        "name": "Send Payment Confirmation",
                        "type": "action",
                        "action": "notify",
                        "tool": "email",
                        "depends_on": ["process_payment"],
                        "parameters": {
                            "template": "payment_confirmation",
                            "recipient": "{{customer.email}}"
                        },
                        "timeout": 15
                    }
                ]
            },
            "tools": ["validator", "fraud_detector", "payment_gateway", "email"],
            "policies": ["pii_protection", "payment_compliance"],
            "dependencies": [
                {
                    "name": "payment-gateway-connector",
                    "version": "2.1.0",
                    "type": "connector"
                },
                {
                    "name": "fraud-detection-service",
                    "version": "1.5.2",
                    "type": "service"
                }
            ],
            "metadata": {
                "category": "payments",
                "tags": ["payment", "fraud-detection", "automation"],
                "author": "payments-team",
                "created_at": "2024-01-15T10:30:00Z"
            }
        }
    
    async def demo_async_compilation(self) -> tuple[str, str]:
        """Demo: Compile a Capsule asynchronously."""
        
        logger.info("=== Demo: Async Capsule Compilation ===")
        
        capsule = self.create_sample_capsule()
        
        compile_request = {
            "capsule_definition": capsule,
            "optimization_level": "standard",
            "validate_dependencies": True,
            "cache_result": True,
            "variables": {
                "environment": "production",
                "region": "us-east-1"
            },
            "configuration": {
                "max_parallel_steps": 3,
                "timeout_multiplier": 1.5
            }
        }
        
        async with httpx.AsyncClient() as client:
            # Start async compilation
            response = await client.post(
                f"{self.base_url}/v1/compile?async_compilation=true",
                json=compile_request,
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error("Compilation request failed", status_code=response.status_code, response=response.text)
                return None, None
            
            result = response.json()
            job_id = result["job_id"]
            
            logger.info(
                "Async compilation started",
                job_id=job_id,
                status=result["status"],
                message=result["message"]
            )
            
            return job_id, None
    
    async def demo_compilation_status(self, job_id: str) -> str:
        """Demo: Check compilation job status."""
        
        logger.info("=== Demo: Compilation Status Check ===")
        
        async with httpx.AsyncClient() as client:
            # Check status without result first
            response = await client.get(
                f"{self.base_url}/v1/compile/status/{job_id}?include_result=false",
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error("Status check failed", status_code=response.status_code, response=response.text)
                return None
            
            status_data = response.json()
            
            logger.info(
                "Compilation status (without result)",
                job_id=job_id,
                status=status_data["status"],
                progress=status_data["progress"],
                current_step=status_data.get("current_step")
            )
            
            # Wait a bit for compilation to complete
            await asyncio.sleep(2)
            
            # Check status with full result
            response = await client.get(
                f"{self.base_url}/v1/compile/status/{job_id}?include_result=true",
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error("Full status check failed", status_code=response.status_code, response=response.text)
                return None
            
            full_status = response.json()
            
            logger.info(
                "Compilation status (with result)",
                job_id=job_id,
                status=full_status["status"],
                progress=full_status["progress"],
                has_result=full_status.get("result") is not None
            )
            
            # Extract plan hash if compilation succeeded
            if full_status.get("result") and full_status["result"].get("plan"):
                plan_hash = full_status["result"]["plan"]["plan_hash"]
                logger.info("Compilation completed successfully", plan_hash=plan_hash)
                return plan_hash
            
            return None
    
    async def demo_sync_compilation(self) -> str:
        """Demo: Compile a Capsule synchronously."""
        
        logger.info("=== Demo: Sync Capsule Compilation ===")
        
        capsule = self.create_sample_capsule()
        capsule["name"] = "sync-payment-processing-capsule"  # Different name
        
        compile_request = {
            "capsule_definition": capsule,
            "optimization_level": "performance",
            "validate_dependencies": False,  # Skip for faster demo
            "cache_result": True
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Start sync compilation
            response = await client.post(
                f"{self.base_url}/v1/compile?async_compilation=false",
                json=compile_request,
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error("Sync compilation failed", status_code=response.status_code, response=response.text)
                return None
            
            result = response.json()
            
            logger.info(
                "Sync compilation completed",
                job_id=result["job_id"],
                status=result["status"],
                message=result["message"]
            )
            
            # Get the plan hash from the job status
            status_response = await client.get(
                f"{self.base_url}/v1/compile/status/{result['job_id']}?include_result=true",
                headers=self.headers
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data.get("result") and status_data["result"].get("plan"):
                    return status_data["result"]["plan"]["plan_hash"]
            
            return None
    
    async def demo_get_plan(self, plan_hash: str):
        """Demo: Retrieve a compiled ExecutablePlan."""
        
        logger.info("=== Demo: Get Compiled Plan ===")
        
        async with httpx.AsyncClient() as client:
            # Get plan without cache metadata
            response = await client.get(
                f"{self.base_url}/v1/plans/{plan_hash}",
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error("Get plan failed", status_code=response.status_code, response=response.text)
                return
            
            plan_data = response.json()
            
            logger.info(
                "Plan retrieved (without cache metadata)",
                plan_hash=plan_hash,
                plan_name=plan_data["plan"]["name"],
                plan_version=plan_data["plan"]["version"],
                flows_count=len(plan_data["plan"]["flows"])
            )
            
            # Get plan with cache metadata
            response = await client.get(
                f"{self.base_url}/v1/plans/{plan_hash}?include_cache_metadata=true",
                headers=self.headers
            )
            
            if response.status_code == 200:
                plan_with_metadata = response.json()
                
                logger.info(
                    "Plan retrieved (with cache metadata)",
                    plan_hash=plan_hash,
                    access_count=plan_with_metadata.get("cache_metadata", {}).get("access_count", 0),
                    cached_at=plan_with_metadata.get("cache_metadata", {}).get("cached_at")
                )
    
    async def demo_validate_plan(self, plan_hash: str):
        """Demo: Validate an ExecutablePlan."""
        
        logger.info("=== Demo: Plan Validation ===")
        
        async with httpx.AsyncClient() as client:
            # Validate with default options
            response = await client.post(
                f"{self.base_url}/v1/plans/{plan_hash}/validate",
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error("Plan validation failed", status_code=response.status_code, response=response.text)
                return
            
            validation_result = response.json()
            
            logger.info(
                "Plan validation (standard)",
                plan_hash=plan_hash,
                valid=validation_result["valid"],
                errors_count=len(validation_result["errors"]),
                warnings_count=len(validation_result["warnings"]),
                security_issues_count=len(validation_result["security_issues"])
            )
            
            # Validate with strict options
            strict_validation = {
                "validation_level": "strict",
                "include_performance_analysis": True,
                "check_security_policies": True,
                "validate_resource_requirements": True
            }
            
            response = await client.post(
                f"{self.base_url}/v1/plans/{plan_hash}/validate",
                json=strict_validation,
                headers=self.headers
            )
            
            if response.status_code == 200:
                strict_result = response.json()
                
                logger.info(
                    "Plan validation (strict)",
                    plan_hash=plan_hash,
                    valid=strict_result["valid"],
                    errors_count=len(strict_result["errors"]),
                    warnings_count=len(strict_result["warnings"]),
                    performance_warnings_count=len(strict_result["performance_warnings"])
                )
    
    async def demo_list_plans(self):
        """Demo: List cached plans."""
        
        logger.info("=== Demo: List Plans ===")
        
        async with httpx.AsyncClient() as client:
            # List all plans
            response = await client.get(
                f"{self.base_url}/v1/plans",
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error("List plans failed", status_code=response.status_code, response=response.text)
                return
            
            plans_data = response.json()
            
            logger.info(
                "Plans listed",
                total_plans=plans_data["total"],
                returned_plans=len(plans_data["plans"]),
                has_more=plans_data["has_more"]
            )
            
            # List with filters
            response = await client.get(
                f"{self.base_url}/v1/plans?name_filter=payment&optimization_level=standard&limit=5",
                headers=self.headers
            )
            
            if response.status_code == 200:
                filtered_data = response.json()
                
                logger.info(
                    "Plans listed (filtered)",
                    name_filter="payment",
                    optimization_level="standard",
                    total_plans=filtered_data["total"],
                    returned_plans=len(filtered_data["plans"])
                )
    
    async def run_full_demo(self):
        """Run the complete API demo."""
        
        logger.info("🚀 Starting Plan Compiler API Demo")
        
        try:
            # 1. Async compilation
            job_id, _ = await self.demo_async_compilation()
            if not job_id:
                logger.error("Async compilation demo failed")
                return
            
            # 2. Check compilation status
            plan_hash_async = await self.demo_compilation_status(job_id)
            
            # 3. Sync compilation
            plan_hash_sync = await self.demo_sync_compilation()
            
            # Use whichever plan hash we got
            plan_hash = plan_hash_async or plan_hash_sync
            
            if plan_hash:
                # 4. Get compiled plan
                await self.demo_get_plan(plan_hash)
                
                # 5. Validate plan
                await self.demo_validate_plan(plan_hash)
            
            # 6. List plans
            await self.demo_list_plans()
            
            logger.info("✅ Plan Compiler API Demo completed successfully!")
            
        except Exception as e:
            logger.error("Demo failed with exception", error=str(e), exc_info=True)


async def main():
    """Main demo function."""
    
    # Note: This demo assumes the Plan Compiler API is running on localhost:8000
    # To run the API server, use: uvicorn api.main:app --host 0.0.0.0 --port 8000
    
    demo = PlanCompilerAPIDemo("http://localhost:8000")
    await demo.run_full_demo()


if __name__ == "__main__":
    print("Plan Compiler API Endpoints Demo")
    print("=" * 50)
    print()
    print("This demo showcases all four required API endpoints:")
    print("1. POST /v1/compile - Compile Capsule to ExecutablePlan")
    print("2. GET /v1/plans/{plan_hash} - Retrieve compiled ExecutablePlan")
    print("3. POST /v1/plans/{plan_hash}/validate - Validate ExecutablePlan")
    print("4. GET /v1/compile/status/{job_id} - Get compilation job status")
    print()
    print("Make sure to start the API server first:")
    print("  cd services/plan-compiler")
    print("  uvicorn api.main:app --host 0.0.0.0 --port 8000")
    print()
    
    asyncio.run(main())