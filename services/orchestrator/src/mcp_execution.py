"""
MCP-enhanced execution handlers for Razorpay payment flows
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import json
import uuid

from .settings import Settings
from .portia_client import PortiaClient
from .clarifications_bridge import open_approval, wait_for_approval
from .receipts_client import write_receipt
from .captokens_client import verify_token

logger = logging.getLogger(__name__)

# Initialize settings
settings = Settings()


async def execute_via_portia_mcp(
    *,
    engine: str,
    capsule_yaml: str | None = None,
    plan_hash: str,
    require_approval: bool,
    capability_token: str | None = None,
    tenant_id: str,
    actor: str,
    razorpay: Dict[str, Any] | None = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Execute MCP-powered plans via Portia with Razorpay integration
    
    Args:
        engine: Execution engine ("razorpay_mcp_payment_link", "razorpay_mcp_refund")
        capsule_yaml: Optional capsule YAML (for traditional flows)
        plan_hash: Plan hash for idempotency
        require_approval: Whether to require human approval
        capability_token: Capability token for authorization
        tenant_id: Tenant ID
        actor: Actor performing the execution
        razorpay: Razorpay-specific parameters
    
    Returns:
        Execution result with MCP details
    """
    logger.info(f"Starting MCP execution: engine={engine}, tenant_id={tenant_id}, actor={actor}")
    
    start_time = datetime.now(timezone.utc)
    plan_run_id = str(uuid.uuid4())
    
    try:
        # Step 1: Verify capability token if provided
        if capability_token:
            logger.info(f"Verifying capability token for tenant_id={tenant_id}")
            await verify_token(
                base=settings.CAPTOKENS_BASE_URL,
                token=capability_token,
                required_caps=["payments.execute", "razorpay.mcp"]
            )
            logger.info("✅ Capability token verified")
        
        # Step 2: Validate MCP is enabled
        if not settings.ENABLE_RAZORPAY_MCP:
            raise ValueError("Razorpay MCP is not enabled. Set ENABLE_RAZORPAY_MCP=true")
        
        # Step 3: Build MCP-powered Portia plan
        portia_plan = await build_mcp_plan(
            engine=engine,
            razorpay_params=razorpay or {},
            require_approval=require_approval,
            tenant_id=tenant_id,
            actor=actor
        )
        
        logger.info(f"Built MCP plan for engine: {engine}")
        
        # Step 4: Execute via Portia with MCP tools
        logger.info("Initializing Portia client with MCP integration")
        portia_client = PortiaClient(
            api_key=settings.PORTIA_API_KEY
        )
        
        # Step 5: Run the plan
        logger.info(f"Executing MCP plan: {plan_run_id}")
        
        # Use run_plan for direct execution
        execution_result = await portia_client.run_plan(portia_plan)
        
        logger.info(f"✅ MCP plan executed: status={execution_result.get('status')}")
        
        # Step 6: Handle approval flow if required
        approvals = []
        if require_approval:
            logger.info("Processing approval flow for MCP execution")
            
            # Create clarification for payment action
            clarification = build_approval_clarification(engine, razorpay or {})
            
            # Open approval
            approval_id = await open_approval(
                approvals_base=settings.APPROVALS_BASE_URL,
                clar=clarification,
                tenant_id=tenant_id,
                actor=actor
            )
            logger.info(f"✅ Approval created: {approval_id}")
            
            # Wait for approval decision
            approval_status = await wait_for_approval(
                approvals_base=settings.APPROVALS_BASE_URL,
                approval_id=approval_id,
                timeout_s=300,
                poll_s=3
            )
            logger.info(f"✅ Approval decision: {approval_status}")
            
            approvals.append({
                "approval_id": approval_id,
                "status": approval_status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": engine
            })
            
            if approval_status != "approved":
                logger.warning(f"❌ MCP execution rejected by approval: {approval_id}")
                final_status = "REJECTED"
            else:
                # Continue with actual MCP execution after approval
                logger.info("✅ Proceeding with MCP execution after approval")
                final_status = "SUCCEEDED"
        else:
            final_status = "SUCCEEDED" if execution_result.get('status') == 'completed' else "FAILED"
        
        # Step 7: Extract MCP results
        mcp_result = extract_mcp_result(execution_result, engine)
        logger.info(f"MCP result extracted: {mcp_result}")
        
        # Step 8: Write receipt
        end_time = datetime.now(timezone.utc)
        receipt_payload = {
            "plan_hash": plan_hash,
            "plan_run_id": plan_run_id,
            "engine": engine,
            "status": final_status,
            "approvals": approvals,
            "actor": actor,
            "tenant_id": tenant_id,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "mcp": mcp_result,
            "razorpay_params": razorpay
        }
        
        logger.info("Writing MCP execution receipt")
        receipt = await write_receipt(
            receipts_base=settings.RECEIPTS_BASE_URL,
            payload=receipt_payload,
            tenant_id=tenant_id
        )
        receipt_id = receipt.get('receipt_id')
        logger.info(f"✅ Receipt written: {receipt_id}")
        
        # Step 9: Return result with MCP details
        result = {
            "plan_run_id": plan_run_id,
            "status": final_status,
            "receipt_id": receipt_id,
            "mcp": mcp_result,
            "approvals_count": len(approvals),
            "duration_seconds": (end_time - start_time).total_seconds()
        }
        
        logger.info(f"✅ MCP execution completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ MCP execution failed: {e}", exc_info=True)
        
        # Write error receipt
        end_time = datetime.now(timezone.utc)
        error_receipt_payload = {
            "plan_hash": plan_hash,
            "plan_run_id": plan_run_id,
            "engine": engine,
            "status": "FAILED",
            "error": str(e),
            "actor": actor,
            "tenant_id": tenant_id,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds()
        }
        
        try:
            await write_receipt(
                receipts_base=settings.RECEIPTS_BASE_URL,
                payload=error_receipt_payload,
                tenant_id=tenant_id
            )
        except Exception as receipt_error:
            logger.error(f"Failed to write error receipt: {receipt_error}")
        
        raise


async def build_mcp_plan(
    engine: str,
    razorpay_params: Dict[str, Any],
    require_approval: bool,
    tenant_id: str,
    actor: str
) -> str:
    """
    Build a Portia plan that uses MCP tools for Razorpay operations
    
    Args:
        engine: MCP engine type
        razorpay_params: Razorpay parameters
        require_approval: Whether approval is required
        tenant_id: Tenant ID
        actor: Actor
    
    Returns:
        Portia plan as string query
    """
    
    if engine == "razorpay_mcp_payment_link":
        amount = razorpay_params.get('amount', 1000)
        currency = razorpay_params.get('currency', 'INR')
        description = razorpay_params.get('description', 'Payment Link')
        customer = razorpay_params.get('customer', {})
        
        customer_info = ""
        if customer:
            customer_info = f"Customer: {customer.get('name', '')} ({customer.get('email', '')})"
        
        plan_query = f"""
        Create a Razorpay payment link using the MCP tool:
        - Amount: {amount} paise ({amount/100:.2f} {currency})
        - Currency: {currency}
        - Description: {description}
        {customer_info}
        
        Use the razorpay.payment_links.create tool with these parameters:
        - amount: {amount}
        - currency: "{currency}"
        - description: "{description}"
        - notify: {{"sms": false, "email": false}}
        """
        
        if customer:
            plan_query += f'\n- customer: {json.dumps(customer)}'
        
        if require_approval:
            plan_query = f"""
            STEP 1: Request approval for payment link creation
            Amount: {amount/100:.2f} {currency}
            Description: {description}
            {customer_info}
            
            STEP 2: {plan_query}
            """
        
        return plan_query
    
    elif engine == "razorpay_mcp_refund":
        payment_id = razorpay_params.get('payment_id')
        amount = razorpay_params.get('amount')  # Optional - full refund if omitted
        speed = razorpay_params.get('speed', 'optimum')
        
        if not payment_id:
            raise ValueError("payment_id required for refund")
        
        plan_query = f"""
        Create a Razorpay refund using the MCP tool:
        - Payment ID: {payment_id}
        - Speed: {speed}
        """
        
        if amount:
            plan_query += f"\n- Amount: {amount} paise ({amount/100:.2f} INR)"
            plan_query += f"""
            
            Use the razorpay.refunds.create tool with these parameters:
            - payment_id: "{payment_id}"
            - amount: {amount}
            - speed: "{speed}"
            """
        else:
            plan_query += f"""
            - Amount: Full refund
            
            Use the razorpay.refunds.create tool with these parameters:
            - payment_id: "{payment_id}"
            - speed: "{speed}"
            """
        
        if require_approval:
            plan_query = f"""
            STEP 1: Request approval for refund
            Payment ID: {payment_id}
            {"Amount: " + str(amount/100) + " INR" if amount else "Amount: Full refund"}
            
            STEP 2: {plan_query}
            """
        
        return plan_query
    
    else:
        raise ValueError(f"Unsupported MCP engine: {engine}")


def build_approval_clarification(engine: str, razorpay_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build approval clarification for MCP actions
    
    Args:
        engine: MCP engine type
        razorpay_params: Razorpay parameters
    
    Returns:
        Clarification object
    """
    
    if engine == "razorpay_mcp_payment_link":
        amount = razorpay_params.get('amount', 1000)
        currency = razorpay_params.get('currency', 'INR')
        description = razorpay_params.get('description', 'Payment Link')
        
        return {
            "id": str(uuid.uuid4()),
            "status": "pending",
            "type": "approval_required",
            "title": "Payment Link Creation Approval",
            "message": f"Approve creation of payment link for {amount/100:.2f} {currency}",
            "details": {
                "action": "create_payment_link",
                "amount": amount,
                "currency": currency,
                "description": description,
                "amount_display": f"{amount/100:.2f} {currency}"
            },
            "options": [
                {"label": "Approve", "value": "approved"},
                {"label": "Reject", "value": "rejected"}
            ]
        }
    
    elif engine == "razorpay_mcp_refund":
        payment_id = razorpay_params.get('payment_id')
        amount = razorpay_params.get('amount')
        
        amount_text = f"{amount/100:.2f} INR" if amount else "Full refund"
        
        return {
            "id": str(uuid.uuid4()),
            "status": "pending",
            "type": "approval_required",
            "title": "Refund Approval",
            "message": f"Approve refund for payment {payment_id}: {amount_text}",
            "details": {
                "action": "create_refund",
                "payment_id": payment_id,
                "amount": amount,
                "amount_display": amount_text
            },
            "options": [
                {"label": "Approve", "value": "approved"},
                {"label": "Reject", "value": "rejected"}
            ]
        }
    
    else:
        return {
            "id": str(uuid.uuid4()),
            "status": "pending",
            "type": "approval_required",
            "title": "MCP Action Approval",
            "message": f"Approve {engine} execution",
            "options": [
                {"label": "Approve", "value": "approved"},
                {"label": "Reject", "value": "rejected"}
            ]
        }


def extract_mcp_result(execution_result: Dict[str, Any], engine: str) -> Dict[str, Any]:
    """
    Extract MCP result from execution
    
    Args:
        execution_result: Raw execution result from Portia
        engine: MCP engine type
    
    Returns:
        Cleaned MCP result
    """
    
    # Get result data
    result_data = execution_result.get('result', {})
    
    # For actual MCP integration, this would parse the real MCP tool results
    # For now, simulate the expected structure
    
    if engine == "razorpay_mcp_payment_link":
        return {
            "tool": "razorpay.payment_links.create",
            "id": f"plink_test_{uuid.uuid4().hex[:8]}",
            "short_url": f"https://rzp.io/i/{uuid.uuid4().hex[:8]}",
            "status": "created"
        }
    
    elif engine == "razorpay_mcp_refund":
        return {
            "tool": "razorpay.refunds.create",
            "id": f"rfnd_test_{uuid.uuid4().hex[:8]}",
            "status": "processed"
        }
    
    else:
        return {
            "tool": f"razorpay.{engine}",
            "status": "executed"
        }
