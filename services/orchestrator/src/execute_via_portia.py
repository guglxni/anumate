"""Execute via Portia service function for orchestrator endpoint."""

import asyncio
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from .settings import get_settings
from .portia_client import PortiaClient
from .clarifications_bridge import open_approval, wait_for_approval
from .receipts_client import write_receipt
from .plan_transformer_new import to_portia_plan
from .captokens_client import verify_token

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Execution error."""
    pass


async def execute_via_portia(
    capsule_yaml: Optional[str] = None,
    capsule_id: Optional[str] = None,
    plan_hash: Optional[str] = None,
    require_approval: bool = True,
    capability_token: Optional[str] = None,
    engine: Optional[str] = None,
    razorpay: Optional[Dict[str, Any]] = None,
    tenant_id: str = "demo-tenant",
    actor: str = "system",
) -> Dict[str, Any]:
    """Execute a plan via Portia with human-in-loop clarifications and MCP support.
    
    This implements the 8-step workflow with MCP engine support:
    1. Verify capability token (if provided)
    2. Handle MCP engine execution OR transform capsule YAML to Portia plan format
    3. Create plan in Portia
    4. Start plan run
    5. Monitor for clarifications
    6. Bridge clarifications to Approvals service
    7. Resume execution after approval
    8. Write receipt when completed
    
    Args:
        capsule_yaml: The capsule YAML content (optional if engine is specified)
        capsule_id: The capsule identifier (optional if engine is specified)
        plan_hash: The plan hash for deterministic identification
        require_approval: Whether to require human approval for clarifications
        capability_token: Token for capability verification
        engine: MCP engine name (e.g., "razorpay_mcp_payment_link")
        razorpay: Razorpay parameters for MCP engines
        tenant_id: Tenant identifier
        actor: Actor performing the operation
        
    Returns:
        Dict with plan_id, plan_run_id, status, receipt_id, and mcp details
        
    Raises:
        ExecutionError: If execution fails at any step
    """
    settings = get_settings()
    plan_id = None
    plan_run_id = None
    receipt_id = None
    
    logger.info(f"🔍 Execute via Portia called with engine: {engine}, plan_hash: {plan_hash}")
    logger.info(f"🔍 Parameters: tenant_id={tenant_id}, actor={actor}, require_approval={require_approval}")
    
    try:
        # Step 1: Verify capability token if provided
        if capability_token:
            logger.info("Step 1: Verifying capability token")
            await verify_token(capability_token, ["plan_execution"])
            logger.info("Capability token verified successfully")
        else:
            logger.info("Step 1: No capability token provided, skipping verification")
        
        # Step 2: Handle MCP engine execution OR transform capsule YAML
        if engine and engine.startswith("razorpay_mcp_"):
            logger.info(f"Step 2: MCP engine execution - {engine}")
            from .service_mcp import execute_razorpay_mcp_payment_link, execute_razorpay_mcp_refund
            
            # Create Portia client with MCP registry
            portia_client = PortiaClient(
                api_key=settings.PORTIA_API_KEY
            )
            
            # Route to appropriate MCP handler
            if engine == "razorpay_mcp_payment_link":
                # Handle tenant_id - generate a UUID if it's not valid
                logger.info(f"Processing tenant_id: {tenant_id} (type: {type(tenant_id)})")
                try:
                    if isinstance(tenant_id, str) and len(tenant_id) == 36:
                        tenant_uuid = UUID(tenant_id)
                        logger.info(f"Successfully parsed tenant_id as UUID: {tenant_uuid}")
                    else:
                        # Generate a deterministic UUID from the tenant_id string
                        import uuid
                        tenant_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(tenant_id))
                        logger.info(f"Generated UUID from tenant_id: {tenant_uuid}")
                except (ValueError, TypeError) as e:
                    logger.error(f"UUID conversion error: {e}")
                    import uuid
                    tenant_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(tenant_id))
                    logger.info(f"Generated fallback UUID: {tenant_uuid}")
                
                logger.info(f"Calling MCP handler with tenant_uuid: {tenant_uuid}")
                result = await execute_razorpay_mcp_payment_link(
                    portia_client=portia_client,
                    tenant_id=tenant_uuid,
                    actor_id=actor,
                    amount=razorpay.get("amount"),
                    currency=razorpay.get("currency", "INR"),
                    description=razorpay.get("description", ""),
                    customer=razorpay.get("customer"),
                    require_approval=require_approval
                )
                
            elif engine == "razorpay_mcp_refund":
                # Handle tenant_id - generate a UUID if it's not valid
                try:
                    if isinstance(tenant_id, str) and len(tenant_id) == 36:
                        tenant_uuid = UUID(tenant_id)
                    else:
                        # Generate a deterministic UUID from the tenant_id string
                        import uuid
                        tenant_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(tenant_id))
                except (ValueError, TypeError):
                    import uuid
                    tenant_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(tenant_id))
                
                result = await execute_razorpay_mcp_refund(
                    portia_client=portia_client,
                    tenant_id=tenant_uuid,
                    actor_id=actor,
                    payment_id=razorpay.get("payment_id"),
                    amount=razorpay.get("amount"),
                    speed=razorpay.get("speed", "optimum"),
                    require_approval=require_approval
                )
            else:
                raise ExecutionError(f"Unsupported MCP engine: {engine}")
            
            logger.info(f"MCP execution completed: {result}")
            return result
        
        else:
            # Traditional capsule YAML execution
            logger.info("Step 2: Transforming capsule YAML to Portia plan")
            if not capsule_yaml:
                raise ExecutionError("capsule_yaml is required for traditional execution")
            
            portia_plan = to_portia_plan(
                capsule_yaml=capsule_yaml,
                capsule_id=capsule_id,
                plan_hash=plan_hash,
                inject_approval_gates=require_approval
            )
            logger.info(f"Transformed plan with ID: {portia_plan.get('id', 'unknown')}")
        
        # Step 3: Create plan in Portia
        logger.info("Step 3: Creating plan in Portia")
        portia_client = PortiaClient(api_key=settings.PORTIA_API_KEY)
        
        plan_response = await portia_client.create_plan(portia_plan)
        plan_id = plan_response["id"]
        logger.info(f"Created Portia plan: {plan_id}")
        
        # Step 4: Start plan run
        logger.info("Step 4: Starting plan run")
        run_response = await portia_client.start_run(plan_id)
        plan_run_id = run_response["id"]
        logger.info(f"Started plan run: {plan_run_id}")
        
        # Step 5: Monitor for clarifications
        logger.info("Step 5: Monitoring for clarifications")
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Check run status
            run_status = await portia_client.get_run(plan_run_id)
            current_status = run_status.get("status", "unknown")
            
            logger.info(f"Iteration {iteration}: Run status is {current_status}")
            
            if current_status in ["completed", "failed", "cancelled"]:
                logger.info(f"Run finished with status: {current_status}")
                break
            
            # Check for pending clarifications
            clarifications = await portia_client.list_clarifications(plan_run_id)
            pending_clarifications = [
                c for c in clarifications 
                if c.get("status") == "pending"
            ]
            
            if pending_clarifications and require_approval:
                logger.info(f"Found {len(pending_clarifications)} pending clarifications")
                
                for clarification in pending_clarifications:
                    await _process_clarification(
                        portia_client=portia_client,
                        plan_run_id=plan_run_id,
                        clarification=clarification
                    )
            
            # Wait before next check
            if current_status not in ["completed", "failed", "cancelled"]:
                await asyncio.sleep(5)
        
        # Get final status
        final_run_status = await portia_client.get_run(plan_run_id)
        final_status = final_run_status.get("status", "unknown")
        
        # Step 8: Write receipt when completed
        if final_status == "completed":
            logger.info("Step 8: Writing execution receipt")
            receipt_data = {
                "plan_id": plan_id,
                "plan_run_id": plan_run_id,
                "capsule_id": capsule_id,
                "plan_hash": plan_hash,
                "status": final_status,
                "execution_summary": final_run_status.get("results", {}),
                "total_iterations": iteration
            }
            
            receipt_id = await write_receipt(receipt_data)
            logger.info(f"Receipt written: {receipt_id}")
        
        return {
            "plan_id": plan_id,
            "plan_run_id": plan_run_id,
            "status": final_status,
            "receipt_id": receipt_id,
            "iterations": iteration
        }
        
    except Exception as e:
        import traceback
        error_msg = f"Execution failed: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Try to write error receipt
        if plan_id and plan_run_id:
            try:
                error_receipt_data = {
                    "plan_id": plan_id,
                    "plan_run_id": plan_run_id,
                    "capsule_id": capsule_id,
                    "plan_hash": plan_hash,
                    "status": "failed",
                    "error_message": error_msg,
                    "execution_summary": {}
                }
                receipt_id = await write_receipt(error_receipt_data)
                logger.info(f"Error receipt written: {receipt_id}")
            except Exception as receipt_error:
                logger.error(f"Failed to write error receipt: {receipt_error}")
        
        raise ExecutionError(error_msg)


async def _process_clarification(
    portia_client: PortiaClient,
    plan_run_id: str,
    clarification: Dict[str, Any]
) -> None:
    """Process a single clarification through the approval workflow.
    
    Steps 6-7: Bridge clarifications to Approvals service and resume execution.
    
    Args:
        portia_client: Portia client instance
        plan_run_id: The plan run ID
        clarification: Clarification data from Portia
    """
    clarification_id = clarification.get("id")
    clarification_text = clarification.get("message", "Unknown clarification")
    
    logger.info(f"Step 6: Processing clarification {clarification_id}: {clarification_text}")
    
    try:
        # Step 6: Bridge clarification to Approvals service
        approval_data = {
            "title": f"Plan Execution Clarification",
            "description": clarification_text,
            "request_type": "plan_clarification",
            "metadata": {
                "plan_run_id": plan_run_id,
                "clarification_id": clarification_id,
                "clarification_data": clarification
            }
        }
        
        approval_id = await open_approval(approval_data)
        logger.info(f"Opened approval request: {approval_id}")
        
        # Wait for approval decision
        approval_result = await wait_for_approval(
            approval_id=approval_id,
            timeout_seconds=3600,  # 1 hour timeout
            poll_interval_seconds=30
        )
        
        if approval_result["status"] == "approved":
            logger.info(f"Approval granted for clarification {clarification_id}")
            
            # Step 7: Resume execution after approval
            response_text = approval_result.get("response", "Approved")
            
            await portia_client.respond_clarification(
                plan_run_id=plan_run_id,
                clarification_id=clarification_id,
                response=response_text
            )
            
            logger.info(f"Responded to clarification {clarification_id} with: {response_text}")
            
        elif approval_result["status"] == "rejected":
            logger.info(f"Approval rejected for clarification {clarification_id}")
            
            # Respond with rejection
            rejection_text = approval_result.get("response", "Request rejected by approver")
            
            await portia_client.respond_clarification(
                plan_run_id=plan_run_id,
                clarification_id=clarification_id,
                response=rejection_text
            )
            
            logger.info(f"Responded to clarification {clarification_id} with rejection: {rejection_text}")
            
        else:
            # Timeout or other status
            timeout_text = f"Approval timed out or failed: {approval_result.get('status', 'unknown')}"
            logger.warning(timeout_text)
            
            await portia_client.respond_clarification(
                plan_run_id=plan_run_id,
                clarification_id=clarification_id,
                response=timeout_text
            )
    
    except Exception as e:
        error_msg = f"Failed to process clarification {clarification_id}: {str(e)}"
        logger.error(error_msg)
        
        # Try to respond with error message
        try:
            await portia_client.respond_clarification(
                plan_run_id=plan_run_id,
                clarification_id=clarification_id,
                response=f"Error processing approval: {error_msg}"
            )
        except Exception as response_error:
            logger.error(f"Failed to send error response to clarification: {response_error}")
        
        raise
