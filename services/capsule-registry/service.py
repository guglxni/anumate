"""Business logic service for Capsule Registry operations."""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from anumate_redaction import RedactionProvider
from anumate_errors import ValidationError, ConflictError, NotFoundError, ErrorCode

from .models import Capsule, CapsuleVersion, CapsuleStatus, CapsuleVisibility
from .repo import CapsuleRepository
from .validation import CapsuleValidator, ValidationIssue
from .signing import CapsuleSigningProvider
from .worm_store import WormStorageProvider
from .events import CapsuleEventPublisher, NoOpEventPublisher
from .security import SecurityContext, Permission


class CapsuleRegistryService:
    """Business logic service for Capsule Registry operations."""
    
    def __init__(
        self,
        repository: CapsuleRepository,
        validator: CapsuleValidator,
        signing_provider: CapsuleSigningProvider,
        worm_storage: WormStorageProvider,
        event_publisher: Optional[CapsuleEventPublisher] = None,
        redaction_provider: Optional[RedactionProvider] = None,
        max_capsule_size: int = 1024 * 1024,
        max_versions_per_capsule: int = 1000
    ):
        self.repository = repository
        self.validator = validator
        self.signing_provider = signing_provider
        self.worm_storage = worm_storage
        self.event_publisher = event_publisher or NoOpEventPublisher()
        self.redaction_provider = redaction_provider
        self.max_capsule_size = max_capsule_size
        self.max_versions_per_capsule = max_versions_per_capsule
    
    async def create_capsule(
        self,
        security_context: SecurityContext,
        capsule_id: Optional[UUID],
        name: str,
        description: Optional[str],
        tags: List[str],
        owner: str,
        visibility: CapsuleVisibility,
        yaml_content: str,
        idempotency_key: str
    ) -> Dict[str, Any]:
        """Create new Capsule with validation and signing."""
        # Check permissions
        if not security_context.has_permission(Permission.CREATE_CAPSULES):
            raise ValidationError(
                error_code=ErrorCode.FORBIDDEN,
                message="Insufficient permissions to create Capsules"
            )
        
        # Size validation
        if len(yaml_content.encode('utf-8')) > self.max_capsule_size:
            raise ValidationError(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=f"Capsule size exceeds maximum of {self.max_capsule_size} bytes"
            )
        
        # Validate YAML content
        is_valid, issues, content_hash = self.validator.validate(yaml_content)
        if not is_valid:
            errors = [issue for issue in issues if issue.severity == "error"]
            raise ValidationError(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Capsule validation failed",
                details={"errors": [{"code": e.code, "message": e.message, "path": e.path} for e in errors]}
            )
        
        # Sign content
        signature = self.signing_provider.sign_content(content_hash)
        
        # Store in WORM storage
        uri = self.worm_storage.store_content(
            content_hash=content_hash,
            yaml_content=yaml_content,
            tenant_id=str(security_context.tenant_id)
        )
        
        # Create in database
        capsule, version, was_created = await self.repository.create_capsule(
            tenant_id=security_context.tenant_id,
            capsule_id=capsule_id,
            name=name,
            description=description,
            tags=tags,
            owner=owner,
            visibility=visibility,
            yaml_content=yaml_content,
            content_hash=content_hash,
            signature=signature,
            pubkey_id=self.signing_provider.public_key_id,
            uri=uri,
            actor=security_context.user_id,
            idempotency_key=idempotency_key
        )
        
        # Publish event if created
        if was_created:
            await self.event_publisher.publish_capsule_created(
                tenant_id=security_context.tenant_id,
                capsule_id=capsule.id,
                capsule_name=capsule.name,
                actor=security_context.user_id
            )
        
        return {
            "capsule_id": capsule.id,
            "version": version.version,
            "content_hash": content_hash,
            "signature": signature,
            "uri": uri,
            "created_at": version.created_at
        }
    
    async def publish_version(
        self,
        security_context: SecurityContext,
        capsule_id: UUID,
        yaml_content: str,
        message: Optional[str],
        idempotency_key: str
    ) -> Dict[str, Any]:
        """Publish new version of existing Capsule."""
        # Check permissions
        if not security_context.has_permission(Permission.PUBLISH_VERSIONS):
            raise ValidationError(
                error_code=ErrorCode.FORBIDDEN,
                message="Insufficient permissions to publish versions"
            )
        
        # Get existing Capsule for validation
        capsule = await self.repository.get_capsule_by_id(security_context.tenant_id, capsule_id)
        if not capsule:
            raise NotFoundError(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Capsule {capsule_id} not found"
            )
        
        # Check version limit
        if capsule.latest_version >= self.max_versions_per_capsule:
            raise ConflictError(
                error_code=ErrorCode.CONFLICT,
                message=f"Maximum versions per Capsule ({self.max_versions_per_capsule}) exceeded"
            )
        
        # Size validation
        if len(yaml_content.encode('utf-8')) > self.max_capsule_size:
            raise ValidationError(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=f"Capsule size exceeds maximum of {self.max_capsule_size} bytes"
            )
        
        # Validate YAML content
        is_valid, issues, content_hash = self.validator.validate(yaml_content)
        if not is_valid:
            errors = [issue for issue in issues if issue.severity == "error"]
            raise ValidationError(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Capsule validation failed",
                details={"errors": [{"code": e.code, "message": e.message, "path": e.path} for e in errors]}
            )
        
        # Sign content
        signature = self.signing_provider.sign_content(content_hash)
        
        # Store in WORM storage
        uri = self.worm_storage.store_content(
            content_hash=content_hash,
            yaml_content=yaml_content,
            tenant_id=str(security_context.tenant_id)
        )
        
        # Publish version
        version, was_created = await self.repository.publish_version(
            tenant_id=security_context.tenant_id,
            capsule_id=capsule_id,
            yaml_content=yaml_content,
            content_hash=content_hash,
            signature=signature,
            pubkey_id=self.signing_provider.public_key_id,
            uri=uri,
            actor=security_context.user_id,
            idempotency_key=idempotency_key,
            message=message
        )
        
        # Publish event if created
        if was_created:
            await self.event_publisher.publish_version_published(
                tenant_id=security_context.tenant_id,
                capsule_id=capsule_id,
                capsule_name=capsule.name,
                version=version.version,
                content_hash=content_hash,
                signature=signature,
                uri=uri,
                actor=security_context.user_id
            )
        
        return {
            "capsule_id": capsule_id,
            "version": version.version,
            "content_hash": content_hash,
            "signature": signature,
            "uri": uri,
            "created_at": version.created_at
        }
    
    async def get_capsule(
        self,
        security_context: SecurityContext,
        capsule_id: UUID
    ) -> Dict[str, Any]:
        """Get Capsule metadata."""
        # Check permissions
        if not security_context.has_permission(Permission.READ_CAPSULES):
            raise ValidationError(
                error_code=ErrorCode.FORBIDDEN,
                message="Insufficient permissions to read Capsules"
            )
        
        capsule = await self.repository.get_capsule_by_id(security_context.tenant_id, capsule_id)
        if not capsule:
            raise NotFoundError(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Capsule {capsule_id} not found"
            )
        
        # Apply visibility filtering
        if not self._can_access_capsule(security_context, capsule):
            raise NotFoundError(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Capsule {capsule_id} not found"
            )
        
        return {
            "id": capsule.id,
            "name": capsule.name,
            "description": capsule.description,
            "tags": capsule.tags,
            "owner": capsule.owner,
            "visibility": capsule.visibility,
            "status": capsule.status,
            "latest_version": capsule.latest_version,
            "created_at": capsule.created_at,
            "updated_at": capsule.updated_at,
            "etag": capsule.etag
        }
    
    async def list_capsules(
        self,
        security_context: SecurityContext,
        query: Optional[str] = None,
        status: Optional[CapsuleStatus] = None,
        tool: Optional[str] = None,
        updated_since: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """List Capsules with filtering and pagination."""
        # Check permissions
        if not security_context.has_permission(Permission.READ_CAPSULES):
            raise ValidationError(
                error_code=ErrorCode.FORBIDDEN,
                message="Insufficient permissions to read Capsules"
            )
        
        # Default to active status unless explicitly requested
        if status is None:
            status = CapsuleStatus.ACTIVE
        
        capsules, total_count = await self.repository.list_capsules(
            tenant_id=security_context.tenant_id,
            query=query,
            status=status,
            tool=tool,
            updated_since=updated_since,
            page=page,
            page_size=page_size
        )
        
        # Filter by visibility
        filtered_capsules = [
            c for c in capsules 
            if self._can_access_capsule(security_context, c)
        ]
        
        # Convert to response format
        items = []
        for capsule in filtered_capsules:
            items.append({
                "id": capsule.id,
                "name": capsule.name,
                "description": capsule.description,
                "tags": capsule.tags,
                "owner": capsule.owner,
                "visibility": capsule.visibility,
                "status": capsule.status,
                "latest_version": capsule.latest_version,
                "created_at": capsule.created_at,
                "updated_at": capsule.updated_at
            })
        
        total_pages = (total_count + page_size - 1) // page_size
        
        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": len(filtered_capsules),  # Filtered count
                "total_pages": total_pages
            }
        }
    
    async def get_capsule_versions(
        self,
        security_context: SecurityContext,
        capsule_id: UUID
    ) -> List[Dict[str, Any]]:
        """Get all versions for a Capsule."""
        # Check permissions and Capsule access
        capsule = await self._get_accessible_capsule(security_context, capsule_id)
        
        versions = await self.repository.get_capsule_versions(security_context.tenant_id, capsule_id)
        
        return [
            {
                "version": v.version,
                "content_hash": v.content_hash,
                "signature": v.signature,
                "uri": v.uri,
                "created_at": v.created_at,
                "created_by": v.created_by
            }
            for v in versions
        ]
    
    async def get_capsule_version(
        self,
        security_context: SecurityContext,
        capsule_id: UUID,
        version: int
    ) -> Dict[str, Any]:
        """Get specific Capsule version with YAML content."""
        # Check permissions and Capsule access
        capsule = await self._get_accessible_capsule(security_context, capsule_id)
        
        version_obj = await self.repository.get_capsule_version(
            security_context.tenant_id, capsule_id, version
        )
        if not version_obj:
            raise NotFoundError(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Version {version} not found for Capsule {capsule_id}"
            )
        
        # Retrieve YAML content
        blob = await self.repository.get_capsule_blob(
            security_context.tenant_id, version_obj.content_hash
        )
        if not blob:
            # Fallback to WORM storage
            yaml_content = self.worm_storage.retrieve_content(
                version_obj.content_hash, str(security_context.tenant_id)
            )
        else:
            yaml_content = blob.yaml_text
        
        if not yaml_content:
            raise NotFoundError(
                error_code=ErrorCode.NOT_FOUND,
                message=f"YAML content not found for version {version}"
            )
        
        # Apply redaction if configured
        if self.redaction_provider:
            yaml_content = self.redaction_provider.redact_content(
                yaml_content, security_context.user_id
            )
        
        return {
            "version": version_obj.version,
            "content_hash": version_obj.content_hash,
            "signature": version_obj.signature,
            "uri": version_obj.uri,
            "yaml": yaml_content,
            "created_at": version_obj.created_at,
            "created_by": version_obj.created_by
        }
    
    async def lint_capsule(
        self,
        security_context: SecurityContext,
        capsule_id: UUID,
        yaml_content: str
    ) -> Dict[str, Any]:
        """Validate Capsule YAML without publishing."""
        # Check permissions and Capsule access
        capsule = await self._get_accessible_capsule(security_context, capsule_id)
        
        # Validate content
        is_valid, issues, content_hash = self.validator.validate(yaml_content)
        
        errors = [
            {"code": issue.code, "message": issue.message, "path": issue.path}
            for issue in issues if issue.severity == "error"
        ]
        warnings = [
            {"code": issue.code, "message": issue.message, "path": issue.path}
            for issue in issues if issue.severity == "warning"
        ]
        
        # Publish lint event
        await self.event_publisher.publish_capsule_linted(
            tenant_id=security_context.tenant_id,
            capsule_id=capsule_id,
            capsule_name=capsule.name,
            is_valid=is_valid,
            error_count=len(errors),
            warning_count=len(warnings),
            content_hash=content_hash,
            actor=security_context.user_id
        )
        
        return {
            "valid": is_valid,
            "content_hash": content_hash,
            "errors": errors,
            "warnings": warnings
        }
    
    async def update_capsule_status(
        self,
        security_context: SecurityContext,
        capsule_id: UUID,
        status: CapsuleStatus,
        expected_etag: str
    ) -> Dict[str, Any]:
        """Update Capsule status (soft delete/restore)."""
        # Check permissions
        if not security_context.has_permission(Permission.UPDATE_CAPSULES):
            raise ValidationError(
                error_code=ErrorCode.FORBIDDEN,
                message="Insufficient permissions to update Capsules"
            )
        
        # Get and validate access
        capsule = await self._get_accessible_capsule(security_context, capsule_id)
        
        # Update status
        updated_capsule = await self.repository.update_capsule_status(
            tenant_id=security_context.tenant_id,
            capsule_id=capsule_id,
            status=status,
            actor=security_context.user_id,
            expected_etag=expected_etag
        )
        
        # Publish appropriate event
        if status == CapsuleStatus.DELETED:
            await self.event_publisher.publish_capsule_deleted(
                tenant_id=security_context.tenant_id,
                capsule_id=capsule_id,
                capsule_name=capsule.name,
                actor=security_context.user_id,
                hard_delete=False
            )
        elif status == CapsuleStatus.ACTIVE:
            await self.event_publisher.publish_capsule_restored(
                tenant_id=security_context.tenant_id,
                capsule_id=capsule_id,
                capsule_name=capsule.name,
                actor=security_context.user_id
            )
        
        return {
            "id": updated_capsule.id,
            "status": updated_capsule.status,
            "updated_at": updated_capsule.updated_at,
            "etag": updated_capsule.etag
        }
    
    async def delete_capsule(
        self,
        security_context: SecurityContext,
        capsule_id: UUID
    ):
        """Permanently delete Capsule (admin only)."""
        # Check permissions
        if not security_context.has_permission(Permission.DELETE_CAPSULES):
            raise ValidationError(
                error_code=ErrorCode.FORBIDDEN,
                message="Insufficient permissions to delete Capsules"
            )
        
        # Get Capsule for event data
        capsule = await self.repository.get_capsule_by_id(security_context.tenant_id, capsule_id)
        if not capsule:
            raise NotFoundError(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Capsule {capsule_id} not found"
            )
        
        # Hard delete
        await self.repository.hard_delete_capsule(
            tenant_id=security_context.tenant_id,
            capsule_id=capsule_id,
            actor=security_context.user_id
        )
        
        # Publish event
        await self.event_publisher.publish_capsule_deleted(
            tenant_id=security_context.tenant_id,
            capsule_id=capsule_id,
            capsule_name=capsule.name,
            actor=security_context.user_id,
            hard_delete=True
        )
    
    async def _get_accessible_capsule(self, security_context: SecurityContext, capsule_id: UUID) -> Capsule:
        """Get Capsule with access control validation."""
        if not security_context.has_permission(Permission.READ_CAPSULES):
            raise ValidationError(
                error_code=ErrorCode.FORBIDDEN,
                message="Insufficient permissions to read Capsules"
            )
        
        capsule = await self.repository.get_capsule_by_id(security_context.tenant_id, capsule_id)
        if not capsule or not self._can_access_capsule(security_context, capsule):
            raise NotFoundError(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Capsule {capsule_id} not found"
            )
        
        return capsule
    
    def _can_access_capsule(self, security_context: SecurityContext, capsule: Capsule) -> bool:
        """Check if user can access Capsule based on visibility rules."""
        if capsule.visibility == CapsuleVisibility.PRIVATE.value:
            # Private Capsules can only be accessed by owner or admins
            return (capsule.owner == security_context.user_id or 
                   security_context.has_role("admin"))
        elif capsule.visibility == CapsuleVisibility.ORG.value:
            # Org Capsules can be accessed by anyone in the tenant
            return True
        
        return False
