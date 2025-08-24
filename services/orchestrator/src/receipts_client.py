"""
Receipts service client for writing execution receipts.
"""

import logging
from typing import Dict, Any

import httpx

logger = logging.getLogger(__name__)


async def write_receipt(
    receipts_base: str, 
    payload: Dict[str, Any], 
    tenant_id: str
) -> Dict[str, Any]:
    """
    Write execution receipt to Receipts service.
    
    Args:
        receipts_base: Base URL of Receipts service
        payload: Receipt data to write
        tenant_id: Tenant ID for receipt
        
    Returns:
        Created receipt with receipt_id and metadata
        
    Raises:
        httpx.HTTPStatusError: If receipt creation fails
    """
    logger.info(f"Writing receipt for tenant={tenant_id}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{receipts_base.rstrip('/')}/v1/receipts",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Tenant-ID": tenant_id
            }
        )
        response.raise_for_status()
        
        result = response.json()
        receipt_id = result.get("receipt_id", result.get("id"))
        
        logger.info(f"Receipt written: {receipt_id}")
        return result
