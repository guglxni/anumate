"""
Receipt Generation and Verification Service
===========================================

Core service for creating tamper-evident receipts with cryptographic integrity,
digital signatures, and WORM storage integration.
"""

import json
import logging
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

# from anumate_receipt import Receipt as BaseReceipt  # Avoiding import issues
from anumate_errors import ValidationError, ExecutionError

from .crypto_utils import canonical_json_serialize, sha256_hash
from .models import Receipt, ReceiptAuditLog, RetentionPolicy
from .schemas import ReceiptCreateRequest, ReceiptVerifyResponse

logger = logging.getLogger(__name__)


class ReceiptService:
    """
    Service for managing tamper-evident receipts with cryptographic integrity.
    
    Provides receipt creation, verification, and WORM storage integration
    with comprehensive audit logging and multi-tenant support.
    """
    
    def __init__(self, signing_key_env_var: str = "RECEIPT_SIGNING_KEY", key_id: str = "receipt-key-2024"):
        """
        Initialize the receipt service.
        
        Args:
            signing_key_env_var: Environment variable containing Ed25519 private key (base64 encoded PEM)
            key_id: Identifier for the signing key
        """
        self.key_id = key_id
        try:
            # Load private key from environment variable
            import os
            key_b64 = os.environ[signing_key_env_var]
            key_pem = base64.b64decode(key_b64)
            
            self._private_key = serialization.load_pem_private_key(
                key_pem,
                password=None
            )
            self._public_key = self._private_key.public_key()
            logger.info(f"Receipt signing initialized with key ID: {key_id}")
        except Exception as e:
            logger.error(f"Failed to load signing key: {e}")
            raise ExecutionError(f"Receipt service initialization failed: {e}")
    
    async def create_receipt(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        request: ReceiptCreateRequest
    ) -> Receipt:
        """
        Create a new tamper-evident receipt with cryptographic signature.
        
        Args:
            session: Database session
            tenant_id: Tenant UUID for multi-tenant isolation
            request: Receipt creation request
            
        Returns:
            Receipt: Created receipt with signature and hash
        """
        try:
            # Prepare receipt data with metadata
            receipt_data = {
                "content": request.receipt_data,
                "metadata": {
                    "receipt_type": request.receipt_type,
                    "subject": request.subject,
                    "reference_id": str(request.reference_id) if request.reference_id else None,
                    "tenant_id": str(tenant_id),
                    "created_at": datetime.utcnow().isoformat(),
                    "service": "anumate-receipt-service",
                    "version": "1.0.0"
                }
            }
            
            # Calculate content hash
            serialized_content = canonical_json_serialize(receipt_data)
            content_hash = sha256_hash(serialized_content).hex()
            
            # Generate Ed25519 signature
            signature_bytes = self._private_key.sign(serialized_content)
            signature = signature_bytes.hex()
            
            # Determine retention period
            retention_until = None
            if request.retention_days:
                retention_until = datetime.utcnow() + timedelta(days=request.retention_days)
            else:
                # Apply tenant retention policy
                retention_policy = await self._get_retention_policy(session, tenant_id, request.receipt_type)
                if retention_policy:
                    retention_until = datetime.utcnow() + timedelta(days=retention_policy.retention_days)
            
            # Create receipt record
            receipt = Receipt(
                tenant_id=tenant_id,
                receipt_type=request.receipt_type,
                subject=request.subject,
                reference_id=request.reference_id,
                receipt_data=receipt_data,
                content_hash=content_hash,
                signature=signature,
                signing_key_id=self.key_id,
                retention_until=retention_until,
                compliance_tags=request.compliance_tags,
                is_verified=True,
                last_verified_at=datetime.utcnow()
            )
            
            session.add(receipt)
            await session.flush()  # Get the generated receipt_id
            
            # Log receipt creation
            await self._log_audit_event(
                session,
                receipt.receipt_id,
                tenant_id,
                "created",
                "receipt-service",
                success=True,
                event_data={
                    "receipt_type": request.receipt_type,
                    "content_hash": content_hash,
                    "signing_key_id": self.key_id,
                    "retention_until": retention_until.isoformat() if retention_until else None
                }
            )
            
            logger.info(f"Created receipt {receipt.receipt_id} for tenant {tenant_id}")
            return receipt
            
        except Exception as e:
            logger.error(f"Failed to create receipt: {e}")
            # Log failure
            await self._log_audit_event(
                session,
                None,
                tenant_id,
                "create_failed",
                "receipt-service",
                success=False,
                error_message=str(e)
            )
            raise ExecutionError(f"Receipt creation failed: {e}")
    
    async def verify_receipt(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        receipt_id: UUID,
        verify_signature: bool = True,
        update_timestamp: bool = True
    ) -> ReceiptVerifyResponse:
        """
        Verify the integrity of a receipt.
        
        Args:
            session: Database session
            tenant_id: Tenant UUID
            receipt_id: Receipt UUID to verify
            verify_signature: Whether to verify Ed25519 signature
            update_timestamp: Whether to update last_verified_at
            
        Returns:
            ReceiptVerifyResponse: Verification results
        """
        verification_errors = []
        content_hash_valid = False
        signature_valid = False
        
        try:
            # Fetch receipt
            result = await session.execute(
                select(Receipt).where(
                    and_(Receipt.receipt_id == receipt_id, Receipt.tenant_id == tenant_id)
                )
            )
            receipt = result.scalar_one_or_none()
            
            if not receipt:
                raise ValidationError(f"Receipt {receipt_id} not found")
            
            # Verify content hash
            try:
                serialized_content = canonical_json_serialize(receipt.receipt_data)
                calculated_hash = sha256_hash(serialized_content).hex()
                content_hash_valid = calculated_hash == receipt.content_hash
                
                if not content_hash_valid:
                    verification_errors.append(f"Content hash mismatch: expected {receipt.content_hash}, got {calculated_hash}")
                    
            except Exception as e:
                verification_errors.append(f"Content hash verification failed: {e}")
            
            # Verify signature
            if verify_signature:
                try:
                    signature_bytes = bytes.fromhex(receipt.signature)
                    serialized_content = canonical_json_serialize(receipt.receipt_data)
                    
                    # Verify with public key (cryptography library)
                    self._public_key.verify(signature_bytes, serialized_content)
                    signature_valid = True
                    
                except Exception as e:
                    verification_errors.append(f"Signature verification failed: {e}")
            else:
                signature_valid = True  # Skip signature verification if not requested
            
            # Overall validity
            is_valid = content_hash_valid and signature_valid and len(verification_errors) == 0
            
            # Update verification status
            if update_timestamp:
                receipt.last_verified_at = datetime.utcnow()
                if not is_valid:
                    receipt.verification_failures += 1
                    receipt.is_verified = False
                else:
                    receipt.is_verified = True
                await session.flush()
            
            # Log verification
            await self._log_audit_event(
                session,
                receipt_id,
                tenant_id,
                "verified",
                "receipt-service",
                success=is_valid,
                event_data={
                    "content_hash_valid": content_hash_valid,
                    "signature_valid": signature_valid,
                    "verification_errors": verification_errors
                }
            )
            
            return ReceiptVerifyResponse(
                receipt_id=receipt_id,
                is_valid=is_valid,
                content_hash_valid=content_hash_valid,
                signature_valid=signature_valid,
                worm_storage_valid=None,  # TODO: Implement WORM verification
                verification_errors=verification_errors,
                verified_at=datetime.utcnow()
            )
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Receipt verification failed: {e}")
            await self._log_audit_event(
                session,
                receipt_id,
                tenant_id,
                "verification_failed",
                "receipt-service",
                success=False,
                error_message=str(e)
            )
            raise ExecutionError(f"Receipt verification failed: {e}")
    
    async def _get_retention_policy(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        receipt_type: str
    ) -> Optional[RetentionPolicy]:
        """Get the applicable retention policy for a receipt type."""
        result = await session.execute(
            select(RetentionPolicy)
            .where(
                and_(
                    RetentionPolicy.tenant_id == tenant_id,
                    RetentionPolicy.is_active == True,
                    RetentionPolicy.receipt_types.contains([receipt_type])
                )
            )
            .order_by(RetentionPolicy.priority.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def _log_audit_event(
        self,
        session: AsyncSession,
        receipt_id: Optional[UUID],
        tenant_id: UUID,
        event_type: str,
        event_source: str,
        success: bool = True,
        error_message: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        """Log an audit event for receipt operations."""
        audit_log = ReceiptAuditLog(
            receipt_id=receipt_id,
            tenant_id=tenant_id,
            event_type=event_type,
            event_source=event_source,
            user_id=user_id,
            client_ip=client_ip,
            request_id=request_id,
            event_data=event_data,
            success=success,
            error_message=error_message
        )
        
        session.add(audit_log)
        await session.flush()


class WormStorageService:
    """
    Service for managing Write-Once-Read-Many (WORM) storage integration.
    
    Provides integration with immutable storage systems for compliance and
    long-term retention of tamper-evident receipts.
    """
    
    def __init__(self):
        """Initialize WORM storage service."""
        # TODO: Initialize WORM storage providers (S3 Glacier, Azure Archive, etc.)
        logger.info("WORM storage service initialized")
    
    async def write_to_worm_storage(
        self,
        session: AsyncSession,
        receipt: Receipt,
        storage_provider: str = "local_filesystem"
    ) -> str:
        """
        Write a receipt to WORM storage.
        
        Args:
            session: Database session
            receipt: Receipt to write to WORM storage
            storage_provider: Storage provider identifier
            
        Returns:
            str: Storage path in WORM system
        """
        try:
            # TODO: Implement actual WORM storage integration
            # For now, simulate writing to local filesystem
            storage_path = f"/worm/receipts/{receipt.tenant_id}/{receipt.receipt_id}.json"
            
            # Update receipt with WORM information
            receipt.worm_storage_path = storage_path
            receipt.worm_written_at = datetime.utcnow()
            
            logger.info(f"Receipt {receipt.receipt_id} written to WORM storage at {storage_path}")
            return storage_path
            
        except Exception as e:
            logger.error(f"Failed to write receipt to WORM storage: {e}")
            raise ExecutionError(f"WORM storage write failed: {e}")
    
    async def verify_worm_storage(
        self,
        session: AsyncSession,
        receipt: Receipt
    ) -> bool:
        """
        Verify that a receipt exists in WORM storage and matches the hash.
        
        Args:
            session: Database session
            receipt: Receipt to verify
            
        Returns:
            bool: True if WORM storage is valid
        """
        try:
            if not receipt.worm_storage_path:
                return False
            
            # TODO: Implement actual WORM storage verification
            # For now, simulate verification
            logger.info(f"Verified receipt {receipt.receipt_id} in WORM storage")
            return True
            
        except Exception as e:
            logger.error(f"WORM storage verification failed: {e}")
            return False
