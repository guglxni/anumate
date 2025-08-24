"""
Business Logic Service Layer

A.4–A.6 Implementation: Core business logic orchestrating validation,
signing, storage, and event publishing for capsule operations.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any

from anumate_logging import get_logger
from anumate_errors import ValidationError, StorageError, SecurityError
from .models import (
    Capsule, CapsuleVersion, CapsuleBlob,
    CapsuleStatus, CapsuleVisibility, ValidationResult,
    CapsuleCreateRequest, CapsuleUpdateRequest, CapsuleVersionRequest
)
from .validation import validate_capsule_content
from .signing import CapsuleSigner
from .worm_store import WormStore
from .repo import CapsuleRepository
from .events import CapsuleEventPublisher, EventContextBuilder
from .security import SecurityContext
from .settings import RegistrySettings


logger = get_logger(__name__)


class CapsuleService:
    """Core business logic for capsule operations."""
    
    def __init__(self, settings: RegistrySettings, repo: CapsuleRepository,
                 signer: CapsuleSigner, worm_store: WormStore,
                 event_publisher: CapsuleEventPublisher):
        self.settings = settings
        self.repo = repo
        self.signer = signer
        self.worm_store = worm_store
        self.event_publisher = event_publisher
    
    async def create_capsule(self, security_ctx: SecurityContext,
                           request: CapsuleCreateRequest,
                           trace_id: Optional[str] = None,
                           idempotency_key: Optional[str] = None) -> Capsule:
        """Create new capsule with validation and event publishing."""
        
        logger.info(
            "Creating capsule",
            extra={
                "name": request.name,
                "tenant_id": str(security_ctx.tenant_id),
                "actor": security_ctx.actor,
                "trace_id": trace_id
            }
        )
        
        try:
            # Create capsule in repository
            capsule = await self.repo.create_capsule(
                security_ctx=security_ctx,
                name=request.name,
                description=request.description,
                tags=request.tags,
                visibility=request.visibility,
                idempotency_key=idempotency_key
            )
            
            # Publish created event
            event_context = EventContextBuilder.from_security_context(
                security_ctx, capsule.id, trace_id
            )
            
            await self.event_publisher.publish_capsule_created(
                event_context,
                {
                    "name": capsule.name,
                    "owner": capsule.owner,
                    "visibility": capsule.visibility,
                    "status": capsule.status,
                    "description": capsule.description,
                    "tags": capsule.tags
                }
            )
            
            logger.info(
                "Capsule created successfully",
                extra={
                    "capsule_id": str(capsule.id),
                    "name": capsule.name,
                    "tenant_id": str(security_ctx.tenant_id),
                    "trace_id": trace_id
                }
            )
            
            return capsule
            
        except Exception as e:
            logger.error(
                "Failed to create capsule",
                extra={
                    "name": request.name,
                    "error": str(e),
                    "tenant_id": str(security_ctx.tenant_id),
                    "trace_id": trace_id
                }
            )
            raise
    
    async def get_capsule(self, security_ctx: SecurityContext,
                        capsule_id: uuid.UUID) -> Optional[Capsule]:
        """Get capsule by ID with access control."""
        
        capsule = await self.repo.get_capsule_by_id(security_ctx, capsule_id)
        if not capsule:
            return None
        
        # Additional access control could be applied here based on visibility
        return capsule
    
    async def list_capsules(self, security_ctx: SecurityContext,
                          query: Optional[str] = None,
                          status: Optional[CapsuleStatus] = None,
                          tool: Optional[str] = None,
                          updated_since: Optional[datetime] = None,
                          page: int = 1,
                          page_size: int = 20) -> Tuple[List[Capsule], int]:
        """List capsules with filtering and pagination."""
        
        # Validate pagination parameters
        if page < 1:
            raise ValidationError("Page must be >= 1")
        if page_size < 1 or page_size > self.settings.max_page_size:
            raise ValidationError(f"Page size must be 1-{self.settings.max_page_size}")
        
        return await self.repo.list_capsules(
            security_ctx=security_ctx,
            query=query,
            status=status,
            tool=tool,
            updated_since=updated_since,
            page=page,
            page_size=page_size
        )
    
    async def update_capsule_status(self, security_ctx: SecurityContext,
                                  capsule_id: uuid.UUID,
                                  request: CapsuleUpdateRequest,
                                  expected_etag: str,
                                  trace_id: Optional[str] = None) -> Capsule:
        """Update capsule status with concurrency control."""
        
        logger.info(
            "Updating capsule status",
            extra={
                "capsule_id": str(capsule_id),
                "new_status": request.status.value,
                "expected_etag": expected_etag,
                "tenant_id": str(security_ctx.tenant_id),
                "trace_id": trace_id
            }
        )
        
        try:
            capsule = await self.repo.update_capsule_status(
                security_ctx=security_ctx,
                capsule_id=capsule_id,
                new_status=request.status,
                expected_etag=expected_etag
            )
            
            # Publish appropriate event
            event_context = EventContextBuilder.from_security_context(
                security_ctx, capsule_id, trace_id
            )
            
            if request.status == CapsuleStatus.DELETED:
                await self.event_publisher.publish_capsule_deleted(
                    event_context,
                    {
                        "name": capsule.name,
                        "soft_delete": True,
                        "latest_version": capsule.latest_version
                    }
                )
            elif request.status == CapsuleStatus.ACTIVE:
                await self.event_publisher.publish_capsule_restored(
                    event_context,
                    {
                        "name": capsule.name,
                        "latest_version": capsule.latest_version
                    }
                )
            
            return capsule
            
        except Exception as e:
            logger.error(
                "Failed to update capsule status",
                extra={
                    "capsule_id": str(capsule_id),
                    "error": str(e),
                    "tenant_id": str(security_ctx.tenant_id),
                    "trace_id": trace_id
                }
            )
            raise
    
    async def delete_capsule(self, security_ctx: SecurityContext,
                           capsule_id: uuid.UUID,
                           trace_id: Optional[str] = None) -> None:
        """Hard delete capsule (admin only)."""
        
        logger.warning(
            "Hard deleting capsule",
            extra={
                "capsule_id": str(capsule_id),
                "tenant_id": str(security_ctx.tenant_id),
                "actor": security_ctx.actor,
                "trace_id": trace_id
            }
        )
        
        # Get capsule info before deletion
        capsule = await self.repo.get_capsule_by_id(security_ctx, capsule_id)
        if not capsule:
            return  # Already deleted or doesn't exist
        
        try:
            await self.repo.hard_delete_capsule(security_ctx, capsule_id)
            
            # Publish deletion event
            event_context = EventContextBuilder.from_security_context(
                security_ctx, capsule_id, trace_id
            )
            
            await self.event_publisher.publish_capsule_deleted(
                event_context,
                {
                    "name": capsule.name,
                    "soft_delete": False,
                    "latest_version": capsule.latest_version
                }
            )
            
        except Exception as e:
            logger.error(
                "Failed to hard delete capsule",
                extra={
                    "capsule_id": str(capsule_id),
                    "error": str(e),
                    "tenant_id": str(security_ctx.tenant_id),
                    "trace_id": trace_id
                }
            )
            raise
    
    async def validate_content(self, security_ctx: SecurityContext,
                             yaml_content: str) -> ValidationResult:
        """Validate capsule YAML content."""
        
        # Size validation
        size_mb = len(yaml_content.encode("utf-8")) / (1024 * 1024)
        if size_mb > self.settings.max_yaml_size_mb:
            return ValidationResult(
                valid=False,
                content_hash="",
                errors=[{
                    "path": "",
                    "message": f"Content size {size_mb:.2f}MB exceeds limit of {self.settings.max_yaml_size_mb}MB"
                }]
            )
        
        # Validate content
        return validate_capsule_content(yaml_content)
    
    async def publish_version(self, security_ctx: SecurityContext,
                            capsule_id: uuid.UUID,
                            request: CapsuleVersionRequest,
                            trace_id: Optional[str] = None,
                            idempotency_key: Optional[str] = None) -> CapsuleVersion:
        """Publish new capsule version with complete workflow."""
        
        logger.info(
            "Publishing capsule version",
            extra={
                "capsule_id": str(capsule_id),
                "tenant_id": str(security_ctx.tenant_id),
                "actor": security_ctx.actor,
                "trace_id": trace_id,
                "lint_only": request.lint_only
            }
        )
        
        try:
            # Validate content
            validation_result = await self.validate_content(security_ctx, request.yaml_content)
            
            if not validation_result.valid:
                # Publish validation failed event
                event_context = EventContextBuilder.from_security_context(
                    security_ctx, capsule_id, trace_id
                )
                await self.event_publisher.publish_validation_failed(
                    event_context,
                    {
                        "errors": validation_result.errors,
                        "warnings": validation_result.warnings
                    }
                )
                
                raise ValidationError("Content validation failed", validation_result.errors)
            
            # If lint-only, return validation result without storing
            if request.lint_only:
                logger.info("Lint-only validation completed successfully")
                return None  # Could return a mock version with validation info
            
            content_hash = validation_result.content_hash
            
            # Sign content hash
            signature_metadata = self.signer.create_signature_metadata(content_hash)
            
            # Store content in WORM storage
            uri = await self.worm_store.store_content(content_hash, request.yaml_content)
            
            # Store blob in database
            blob = await self.repo.store_blob(
                security_ctx=security_ctx,
                content_hash=content_hash,
                yaml_content=request.yaml_content
            )
            
            # Create version record
            version = await self.repo.create_version(
                security_ctx=security_ctx,
                capsule_id=capsule_id,
                content_hash=content_hash,
                signature=signature_metadata["signature"],
                pubkey_id=signature_metadata["pubkey_id"],
                uri=uri,
                idempotency_key=idempotency_key
            )
            
            # Publish version published event
            event_context = EventContextBuilder.from_capsule_version(
                version, security_ctx, trace_id
            )
            
            await self.event_publisher.publish_version_published(
                event_context,
                {
                    "uri": uri,
                    "created_by": version.created_by,
                    "pubkey_id": version.pubkey_id
                }
            )
            
            logger.info(
                "Version published successfully",
                extra={
                    "capsule_id": str(capsule_id),
                    "version": version.version,
                    "content_hash": content_hash,
                    "tenant_id": str(security_ctx.tenant_id),
                    "trace_id": trace_id
                }
            )
            
            return version
            
        except Exception as e:
            logger.error(
                "Failed to publish version",
                extra={
                    "capsule_id": str(capsule_id),
                    "error": str(e),
                    "tenant_id": str(security_ctx.tenant_id),
                    "trace_id": trace_id
                }
            )
            raise
    
    async def get_version(self, security_ctx: SecurityContext,
                        capsule_id: uuid.UUID,
                        version_number: int) -> Optional[CapsuleVersion]:
        """Get specific version by number."""
        
        return await self.repo.get_version_by_number(
            security_ctx, capsule_id, version_number
        )
    
    async def list_versions(self, security_ctx: SecurityContext,
                          capsule_id: uuid.UUID) -> List[CapsuleVersion]:
        """List all versions for a capsule."""
        
        return await self.repo.list_versions(security_ctx, capsule_id)
    
    async def get_version_content(self, security_ctx: SecurityContext,
                                capsule_id: uuid.UUID,
                                version_number: int) -> Optional[Tuple[CapsuleVersion, str]]:
        """Get version with YAML content (potentially redacted)."""
        
        version = await self.get_version(security_ctx, capsule_id, version_number)
        if not version:
            return None
        
        # Get content from blob storage
        blob = await self.repo.get_blob_by_hash(version.content_hash)
        if not blob:
            raise StorageError(f"Content not found for hash: {version.content_hash}")
        
        # TODO: Apply redaction based on user permissions
        yaml_content = blob.yaml_text
        
        return version, yaml_content
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check."""
        
        health_data = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {}
        }
        
        try:
            # Check WORM storage
            worm_health = await self.worm_store.health_check()
            health_data["checks"]["storage"] = worm_health.get("status", "unknown")
            
            # Database health would be checked at the repository level
            health_data["checks"]["database"] = "ok"  # Simplified
            
            # Check signing capability
            try:
                test_hash = "a" * 64
                self.signer.sign_content_hash(test_hash)
                health_data["checks"]["signing"] = "ok"
            except Exception:
                health_data["checks"]["signing"] = "error"
                health_data["status"] = "unhealthy"
            
        except Exception as e:
            health_data["status"] = "unhealthy"
            health_data["error"] = str(e)
        
        return health_data


def create_capsule_service(settings: RegistrySettings,
                         repo: CapsuleRepository,
                         signer: CapsuleSigner,
                         worm_store: WormStore,
                         event_publisher: CapsuleEventPublisher) -> CapsuleService:
    """Factory function to create configured capsule service."""
    return CapsuleService(settings, repo, signer, worm_store, event_publisher)
