"""
Razorpay Webhook Integration
Handles incoming webhook events from Razorpay with HMAC SHA256 verification
"""
import hmac
import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post("/razorpay/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(default=None, alias="X-Razorpay-Signature")
):
    """
    Razorpay webhook endpoint with HMAC SHA256 signature verification.
    
    Args:
        request: FastAPI request object
        x_razorpay_signature: HMAC signature from Razorpay headers
        
    Returns:
        JSON response with success status
        
    Raises:
        HTTPException: 400 for invalid signature, 500 for configuration issues
    """
    # Import settings here to avoid circular imports
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
    from src.settings import Settings
    
    settings = Settings()
    
    # Check webhook secret configuration
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        logger.error("❌ Razorpay webhook secret not configured")
        raise HTTPException(
            status_code=500, 
            detail="Webhook secret not configured"
        )
    
    # Get raw request body for signature verification
    try:
        raw_body = await request.body()
    except Exception as e:
        logger.error(f"❌ Failed to read request body: {e}")
        raise HTTPException(
            status_code=400,
            detail="Failed to read request body"
        )
    
    # Verify HMAC signature
    if not x_razorpay_signature:
        logger.warning("❌ Missing X-Razorpay-Signature header")
        raise HTTPException(
            status_code=400,
            detail="Missing signature header"
        )
    
    # Compute HMAC SHA256 digest
    try:
        expected_digest = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures securely
        if not hmac.compare_digest(expected_digest, x_razorpay_signature):
            logger.warning("❌ Invalid webhook signature")
            raise HTTPException(
                status_code=400,
                detail="Invalid signature"
            )
            
    except Exception as e:
        logger.error(f"❌ Signature verification failed: {e}")
        raise HTTPException(
            status_code=400,
            detail="Signature verification failed"
        )
    
    # Parse webhook payload
    try:
        webhook_data = await request.json()
        event_type = webhook_data.get("event")
        
        logger.info(f"✅ Received Razorpay webhook: {event_type}")
        
        # TODO: Handle specific webhook events
        # - payment.link.paid
        # - refund.processed
        # - payment.captured
        # etc.
        
        # For now, just log the event for debugging
        logger.info(f"📋 Webhook payload keys: {list(webhook_data.keys())}")
        
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Webhook processed successfully",
                "event": event_type
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to process webhook payload: {e}")
        raise HTTPException(
            status_code=400,
            detail="Failed to process webhook payload"
        )


@router.get("/razorpay/webhook/health")
async def webhook_health():
    """Health check endpoint for webhook integration."""
    return {
        "status": "healthy",
        "service": "razorpay-webhook", 
        "endpoint": "/integrations/razorpay/webhook"
    }
