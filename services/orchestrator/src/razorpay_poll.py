"""
Razorpay API-only polling utilities for payment tracking.
Provides polling functionality for payment links and refunds without requiring webhooks.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from enum import Enum

import httpx
from pydantic import BaseModel

from .settings import Settings

# Configure logging
logger = logging.getLogger(__name__)


class PaymentStatus(str, Enum):
    """Razorpay payment status enum."""
    CREATED = "created"
    ATTEMPTED = "attempted"
    PAID = "paid"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RefundStatus(str, Enum):
    """Razorpay refund status enum."""
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class PaymentPollResult(BaseModel):
    """Result of payment polling operation."""
    payment_link_id: str
    status: PaymentStatus
    payment_id: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = None
    method: Optional[str] = None
    fee: Optional[int] = None
    tax: Optional[int] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    raw_response: Dict[str, Any]


class RefundPollResult(BaseModel):
    """Result of refund polling operation."""
    refund_id: str
    payment_id: str
    status: RefundStatus
    amount: Optional[int] = None
    currency: Optional[str] = None
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    raw_response: Dict[str, Any]


class RazorpayPoller:
    """Razorpay API poller for tracking payments and refunds."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = "https://api.razorpay.com/v1"
        
        # Create HTTP client with basic auth
        auth = (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0)
        
        self.client = httpx.AsyncClient(
            auth=auth,
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": f"anumate-orchestrator/1.0"
            }
        )
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """Make authenticated request to Razorpay API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        logger.debug(f"Making {method} request to {url}")
        
        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            
            result = response.json()
            logger.debug(f"API response: {result}")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise
    
    async def get_payment_link_status(self, payment_link_id: str) -> PaymentPollResult:
        """Get current status of a payment link."""
        response = await self._make_request("GET", f"payment_links/{payment_link_id}")
        
        # Extract payment information if available
        payment_id = None
        payment_data = {}
        
        if response.get("payments"):
            # Get the latest payment
            payments = response["payments"]
            if payments:
                latest_payment = payments[0]  # Assuming sorted by creation time
                payment_id = latest_payment.get("id")
                payment_data = latest_payment
        
        return PaymentPollResult(
            payment_link_id=payment_link_id,
            status=PaymentStatus(response.get("status", "created")),
            payment_id=payment_id,
            amount=payment_data.get("amount") or response.get("amount"),
            currency=payment_data.get("currency") or response.get("currency"),
            method=payment_data.get("method"),
            fee=payment_data.get("fee"),
            tax=payment_data.get("tax"),
            created_at=self._parse_timestamp(response.get("created_at")),
            completed_at=self._parse_timestamp(payment_data.get("created_at")) if payment_data else None,
            raw_response=response
        )
    
    async def get_refund_status(self, refund_id: str) -> RefundPollResult:
        """Get current status of a refund."""
        response = await self._make_request("GET", f"refunds/{refund_id}")
        
        return RefundPollResult(
            refund_id=refund_id,
            payment_id=response.get("payment_id"),
            status=RefundStatus(response.get("status", "pending")),
            amount=response.get("amount"),
            currency=response.get("currency"),
            created_at=self._parse_timestamp(response.get("created_at")),
            processed_at=self._parse_timestamp(response.get("processed_at")),
            raw_response=response
        )
    
    def _parse_timestamp(self, timestamp: Optional[int]) -> Optional[datetime]:
        """Parse Unix timestamp to datetime."""
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    
    async def poll_payment_completion(
        self, 
        payment_link_id: str,
        timeout_sec: Optional[int] = None,
        interval_sec: Optional[int] = None
    ) -> PaymentPollResult:
        """
        Poll a payment link until completion or timeout.
        
        Args:
            payment_link_id: Razorpay payment link ID
            timeout_sec: Max time to wait (defaults to settings)
            interval_sec: Poll interval (defaults to settings)
            
        Returns:
            PaymentPollResult with final status
            
        Raises:
            asyncio.TimeoutError: If polling times out
            Exception: If API errors occur
        """
        timeout_sec = timeout_sec or self.settings.RAZORPAY_POLL_TIMEOUT_SEC
        interval_sec = interval_sec or self.settings.RAZORPAY_POLL_INTERVAL_SEC
        
        logger.info(f"Starting payment poll for {payment_link_id} "
                   f"(timeout: {timeout_sec}s, interval: {interval_sec}s)")
        
        start_time = datetime.now(timezone.utc)
        
        try:
            async with asyncio.timeout(timeout_sec):
                while True:
                    result = await self.get_payment_link_status(payment_link_id)
                    
                    # Terminal states
                    if result.status in [PaymentStatus.PAID, PaymentStatus.CANCELLED, PaymentStatus.EXPIRED]:
                        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                        logger.info(f"Payment {payment_link_id} completed with status {result.status} "
                                   f"after {elapsed:.1f}s")
                        return result
                    
                    # Log progress
                    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                    logger.debug(f"Payment {payment_link_id} status: {result.status} "
                                f"(elapsed: {elapsed:.1f}s)")
                    
                    # Wait before next poll
                    await asyncio.sleep(interval_sec)
                    
        except asyncio.TimeoutError:
            logger.warning(f"Payment polling timed out for {payment_link_id} after {timeout_sec}s")
            # Return final status
            final_result = await self.get_payment_link_status(payment_link_id)
            raise asyncio.TimeoutError(f"Payment polling timed out. Final status: {final_result.status}")
    
    async def poll_refund_completion(
        self,
        refund_id: str,
        timeout_sec: Optional[int] = None,
        interval_sec: Optional[int] = None
    ) -> RefundPollResult:
        """
        Poll a refund until completion or timeout.
        
        Args:
            refund_id: Razorpay refund ID
            timeout_sec: Max time to wait (defaults to settings)
            interval_sec: Poll interval (defaults to settings)
            
        Returns:
            RefundPollResult with final status
            
        Raises:
            asyncio.TimeoutError: If polling times out
            Exception: If API errors occur
        """
        timeout_sec = timeout_sec or self.settings.RAZORPAY_POLL_TIMEOUT_SEC
        interval_sec = interval_sec or self.settings.RAZORPAY_POLL_INTERVAL_SEC
        
        logger.info(f"Starting refund poll for {refund_id} "
                   f"(timeout: {timeout_sec}s, interval: {interval_sec}s)")
        
        start_time = datetime.now(timezone.utc)
        
        try:
            async with asyncio.timeout(timeout_sec):
                while True:
                    result = await self.get_refund_status(refund_id)
                    
                    # Terminal states
                    if result.status in [RefundStatus.PROCESSED, RefundStatus.FAILED]:
                        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                        logger.info(f"Refund {refund_id} completed with status {result.status} "
                                   f"after {elapsed:.1f}s")
                        return result
                    
                    # Log progress
                    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                    logger.debug(f"Refund {refund_id} status: {result.status} "
                                f"(elapsed: {elapsed:.1f}s)")
                    
                    # Wait before next poll
                    await asyncio.sleep(interval_sec)
                    
        except asyncio.TimeoutError:
            logger.warning(f"Refund polling timed out for {refund_id} after {timeout_sec}s")
            # Return final status
            final_result = await self.get_refund_status(refund_id)
            raise asyncio.TimeoutError(f"Refund polling timed out. Final status: {final_result.status}")


async def poll_payment_link(
    payment_link_id: str,
    settings: Settings,
    timeout_sec: Optional[int] = None,
    interval_sec: Optional[int] = None
) -> PaymentPollResult:
    """
    Convenience function to poll a payment link completion.
    
    Usage:
        result = await poll_payment_link("plink_abc123", settings)
        if result.status == PaymentStatus.PAID:
            print(f"Payment completed: {result.payment_id}")
    """
    async with RazorpayPoller(settings) as poller:
        return await poller.poll_payment_completion(
            payment_link_id, 
            timeout_sec, 
            interval_sec
        )


async def poll_refund(
    refund_id: str,
    settings: Settings,
    timeout_sec: Optional[int] = None,
    interval_sec: Optional[int] = None
) -> RefundPollResult:
    """
    Convenience function to poll a refund completion.
    
    Usage:
        result = await poll_refund("rfnd_abc123", settings)
        if result.status == RefundStatus.PROCESSED:
            print(f"Refund processed: {result.amount}")
    """
    async with RazorpayPoller(settings) as poller:
        return await poller.poll_refund_completion(
            refund_id,
            timeout_sec,
            interval_sec
        )


def create_receipt_payload(
    payment_result: PaymentPollResult,
    original_request: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create receipt payload from payment poll result.
    
    Args:
        payment_result: Result from payment polling
        original_request: Original request that triggered payment
        
    Returns:
        Receipt payload with payment details
    """
    return {
        "transaction_id": payment_result.payment_id or payment_result.payment_link_id,
        "payment_link_id": payment_result.payment_link_id,
        "status": payment_result.status.value,
        "amount": payment_result.amount,
        "currency": payment_result.currency,
        "method": payment_result.method,
        "fee": payment_result.fee,
        "tax": payment_result.tax,
        "created_at": payment_result.created_at.isoformat() if payment_result.created_at else None,
        "completed_at": payment_result.completed_at.isoformat() if payment_result.completed_at else None,
        "original_request": original_request,
        "raw_razorpay_response": payment_result.raw_response,
        "polling_metadata": {
            "poll_completed": True,
            "final_status": payment_result.status.value
        }
    }
