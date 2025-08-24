"""Database repository for Capsule Registry operations."""

from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, func, select, update, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from anumate_idempotency import IdempotencyProvider, IdempotencyResult
from anumate_errors import NotFoundError, ConflictError, ValidationError, ErrorCode
from anumate_tracing import get_trace_id

from .models import (
    Capsule, CapsuleVersion, CapsuleBlob, CapsuleAudit,
    CapsuleStatus, CapsuleVisibility, AuditAction
)


class CapsuleRepository:
    """Repository for Capsule data access operations."""
    
    def __init__(self, session: AsyncSession, idempotency_provider: IdempotencyProvider):
        self.session = session
        self.idempotency = idempotency_provider
    
    async def create_capsule(
        self,
        tenant_id: UUID,
        capsule_id: Optional[UUID],
        name: str,
        description: Optional[str],
        tags: List[str],
        owner: str,
        visibility: CapsuleVisibility,
        yaml_content: str,
        content_hash: str,
        signature: str,
        pubkey_id: str,
        uri: str,
        actor: str,
        idempotency_key: str
    ) -> Tuple[Capsule, CapsuleVersion, bool]:
        """
        Create new Capsule with initial version.
        
        Returns:
            Tuple of (capsule, version, was_created)
        """
        # Check idempotency
        idempotency_result = await self.idempotency.get_result(idempotency_key)
        if idempotency_result.exists:
            # Return existing result
            existing_capsule = await self.get_capsule_by_id(
                tenant_id, UUID(idempotency_result.result["capsule_id"])
            )
            if not existing_capsule:
                raise NotFoundError(
                    error_code=ErrorCode.NOT_FOUND,
                    message="Idempotent result references non-existent Capsule"
                )
            latest_version = await self.get_capsule_version(
                tenant_id, existing_capsule.id, existing_capsule.latest_version
            )
            return existing_capsule, latest_version, False
        
        # Generate ID if not provided
        if not capsule_id:
            capsule_id = uuid4()
        
        # Check for name uniqueness within tenant
        existing = await self.get_capsule_by_name(tenant_id, name)
        if existing and existing.status == CapsuleStatus.ACTIVE:
            raise ConflictError(
                error_code=ErrorCode.CONFLICT,
                message=f"Capsule with name '{name}' already exists"
            )
        
        try:
            # Create Capsule
            capsule = Capsule(
                id=capsule_id,
                tenant_id=tenant_id,
                name=name,
                description=description,
                tags=tags,
                owner=owner,
                visibility=visibility.value,
                status=CapsuleStatus.ACTIVE.value,
                latest_version=1
            )
            self.session.add(capsule)
            
            # Store YAML blob
            await self._store_blob(tenant_id, content_hash, yaml_content)
            
            # Create first version
            version = CapsuleVersion(
                tenant_id=tenant_id,
                capsule_id=capsule_id,
                version=1,
                content_hash=content_hash,
                signature=signature,
                pubkey_id=pubkey_id,
                uri=uri,
                created_by=actor
            )
            self.session.add(version)
            
            # Create audit log
            audit = CapsuleAudit(
                tenant_id=tenant_id,
                capsule_id=capsule_id,
                version=1,
                actor=actor,
                action=AuditAction.CREATE.value,
                details={
                    "name": name,
                    "visibility": visibility.value,
                    "content_hash": content_hash
                },
                trace_id=get_trace_id()
            )
            self.session.add(audit)
            
            await self.session.commit()
            
            # Store idempotency result
            result = {
                "capsule_id": str(capsule_id),
                "version": 1,
                "content_hash": content_hash,
                "signature": signature,
                "uri": uri,
                "created_at": capsule.created_at.isoformat()
            }
            await self.idempotency.store_result(idempotency_key, result)
            
            return capsule, version, True
            
        except Exception as e:
            await self.session.rollback()
            raise e
    
    async def publish_version(
        self,
        tenant_id: UUID,
        capsule_id: UUID,
        yaml_content: str,
        content_hash: str,
        signature: str,
        pubkey_id: str,
        uri: str,
        actor: str,
        idempotency_key: str,
        message: Optional[str] = None
    ) -> Tuple[CapsuleVersion, bool]:
        """
        Publish new version of existing Capsule.
        
        Returns:
            Tuple of (version, was_created)
        """
        # Check idempotency
        idempotency_result = await self.idempotency.get_result(idempotency_key)
        if idempotency_result.exists:
            # Return existing result
            result_data = idempotency_result.result
            existing_version = await self.get_capsule_version(
                tenant_id, capsule_id, result_data["version"]
            )
            if not existing_version:
                raise NotFoundError(
                    error_code=ErrorCode.NOT_FOUND,
                    message="Idempotent result references non-existent version"
                )
            return existing_version, False
        
        # Get existing Capsule
        capsule = await self.get_capsule_by_id(tenant_id, capsule_id)
        if not capsule:
            raise NotFoundError(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Capsule {capsule_id} not found"
            )
        
        if capsule.status == CapsuleStatus.DELETED:
            raise ConflictError(
                error_code=ErrorCode.CONFLICT,
                message="Cannot publish version of deleted Capsule"
            )
        
        try:
            # Calculate next version number
            next_version = capsule.latest_version + 1
            
            # Check for duplicate content hash in this Capsule
            existing_version = await self._get_version_by_content_hash(
                tenant_id, capsule_id, content_hash
            )
            if existing_version:
                raise ConflictError(
                    error_code=ErrorCode.CONFLICT,
                    message=f"Content already published as version {existing_version.version}"
                )
            
            # Store YAML blob
            await self._store_blob(tenant_id, content_hash, yaml_content)
            
            # Create new version
            version = CapsuleVersion(
                tenant_id=tenant_id,
                capsule_id=capsule_id,
                version=next_version,
                content_hash=content_hash,
                signature=signature,
                pubkey_id=pubkey_id,
                uri=uri,
                created_by=actor
            )
            self.session.add(version)
            
            # Update Capsule latest version
            capsule.latest_version = next_version
            capsule.updated_at = datetime.utcnow()
            # Generate new ETag
            capsule.etag = str(uuid4())
            
            # Create audit log
            audit = CapsuleAudit(
                tenant_id=tenant_id,
                capsule_id=capsule_id,
                version=next_version,
                actor=actor,
                action=AuditAction.PUBLISH_VERSION.value,
                details={
                    "content_hash": content_hash,
                    "message": message
                },
                trace_id=get_trace_id()
            )
            self.session.add(audit)
            
            await self.session.commit()
            
            # Store idempotency result
            result = {
                "capsule_id": str(capsule_id),
                "version": next_version,
                "content_hash": content_hash,
                "signature": signature,
                "uri": uri,
                "created_at": version.created_at.isoformat()
            }
            await self.idempotency.store_result(idempotency_key, result)
            
            return version, True
            
        except Exception as e:
            await self.session.rollback()
            raise e
    
    async def update_capsule_status(
        self,
        tenant_id: UUID,
        capsule_id: UUID,
        status: CapsuleStatus,
        actor: str,
        expected_etag: str
    ) -> Capsule:
        """Update Capsule status with ETag validation."""
        capsule = await self.get_capsule_by_id(tenant_id, capsule_id)
        if not capsule:
            raise NotFoundError(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Capsule {capsule_id} not found"
            )
        
        # ETag validation
        if capsule.etag != expected_etag:
            raise ConflictError(
                error_code=ErrorCode.CONFLICT,
                message="ETag mismatch - Capsule was modified"
            )
        
        try:
            # Update status
            old_status = capsule.status
            capsule.status = status.value
            capsule.updated_at = datetime.utcnow()
            capsule.etag = str(uuid4())  # New ETag
            
            # Create audit log
            action = AuditAction.RESTORE if status == CapsuleStatus.ACTIVE else AuditAction.DELETE
            audit = CapsuleAudit(
                tenant_id=tenant_id,
                capsule_id=capsule_id,
                actor=actor,
                action=action.value,
                details={
                    "old_status": old_status,
                    "new_status": status.value
                },
                trace_id=get_trace_id()
            )
            self.session.add(audit)
            
            await self.session.commit()
            return capsule
            
        except Exception as e:
            await self.session.rollback()
            raise e
    
    async def hard_delete_capsule(self, tenant_id: UUID, capsule_id: UUID, actor: str):
        """Permanently delete Capsule and all versions."""
        capsule = await self.get_capsule_by_id(tenant_id, capsule_id)
        if not capsule:
            raise NotFoundError(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Capsule {capsule_id} not found"
            )
        
        try:
            # Create final audit log
            audit = CapsuleAudit(
                tenant_id=tenant_id,
                capsule_id=capsule_id,
                actor=actor,
                action=AuditAction.DELETE.value,
                details={"hard_delete": True, "name": capsule.name},
                trace_id=get_trace_id()
            )
            self.session.add(audit)
            
            # Delete Capsule (cascade will delete versions and audit logs)
            await self.session.delete(capsule)
            await self.session.commit()
            
        except Exception as e:
            await self.session.rollback()
            raise e
    
    async def get_capsule_by_id(self, tenant_id: UUID, capsule_id: UUID) -> Optional[Capsule]:
        """Get Capsule by ID."""
        result = await self.session.execute(
            select(Capsule)
            .where(and_(Capsule.tenant_id == tenant_id, Capsule.id == capsule_id))
        )
        return result.scalar_one_or_none()
    
    async def get_capsule_by_name(self, tenant_id: UUID, name: str) -> Optional[Capsule]:
        """Get Capsule by name."""
        result = await self.session.execute(
            select(Capsule)
            .where(and_(Capsule.tenant_id == tenant_id, Capsule.name == name))
        )
        return result.scalar_one_or_none()
    
    async def list_capsules(
        self,
        tenant_id: UUID,
        query: Optional[str] = None,
        status: Optional[CapsuleStatus] = None,
        tool: Optional[str] = None,
        updated_since: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Capsule], int]:
        """List Capsules with filtering and pagination."""
        # Build query conditions
        conditions = [Capsule.tenant_id == tenant_id]
        
        if query:
            search_condition = or_(
                Capsule.name.ilike(f"%{query}%"),
                Capsule.description.ilike(f"%{query}%")
            )
            conditions.append(search_condition)
        
        if status:
            conditions.append(Capsule.status == status.value)
        
        if updated_since:
            conditions.append(Capsule.updated_at >= updated_since)
        
        # TODO: Tool filtering requires parsing YAML content or indexing
        if tool:
            # This would require a more sophisticated implementation
            # with either YAML parsing or pre-computed tool indexes
            pass
        
        # Count total items
        count_result = await self.session.execute(
            select(func.count(Capsule.id)).where(and_(*conditions))
        )
        total_count = count_result.scalar()
        
        # Get paginated results
        offset = (page - 1) * page_size
        result = await self.session.execute(
            select(Capsule)
            .where(and_(*conditions))
            .order_by(desc(Capsule.updated_at))
            .offset(offset)
            .limit(page_size)
        )
        
        capsules = result.scalars().all()
        return list(capsules), total_count
    
    async def get_capsule_versions(self, tenant_id: UUID, capsule_id: UUID) -> List[CapsuleVersion]:
        """Get all versions for a Capsule."""
        result = await self.session.execute(
            select(CapsuleVersion)
            .where(and_(
                CapsuleVersion.tenant_id == tenant_id,
                CapsuleVersion.capsule_id == capsule_id
            ))
            .order_by(desc(CapsuleVersion.version))
        )
        return list(result.scalars().all())
    
    async def get_capsule_version(
        self, 
        tenant_id: UUID, 
        capsule_id: UUID, 
        version: int
    ) -> Optional[CapsuleVersion]:
        """Get specific Capsule version."""
        result = await self.session.execute(
            select(CapsuleVersion)
            .where(and_(
                CapsuleVersion.tenant_id == tenant_id,
                CapsuleVersion.capsule_id == capsule_id,
                CapsuleVersion.version == version
            ))
        )
        return result.scalar_one_or_none()
    
    async def get_capsule_blob(self, tenant_id: UUID, content_hash: str) -> Optional[CapsuleBlob]:
        """Get Capsule YAML content by hash."""
        result = await self.session.execute(
            select(CapsuleBlob)
            .where(and_(
                CapsuleBlob.tenant_id == tenant_id,
                CapsuleBlob.content_hash == content_hash
            ))
        )
        return result.scalar_one_or_none()
    
    async def _store_blob(self, tenant_id: UUID, content_hash: str, yaml_content: str):
        """Store YAML blob with deduplication."""
        # Check if blob already exists
        existing_blob = await self.get_capsule_blob(tenant_id, content_hash)
        if existing_blob:
            return existing_blob
        
        # Create new blob
        blob = CapsuleBlob(
            tenant_id=tenant_id,
            content_hash=content_hash,
            yaml_text=yaml_content,
            size_bytes=len(yaml_content.encode('utf-8'))
        )
        self.session.add(blob)
        return blob
    
    async def _get_version_by_content_hash(
        self, 
        tenant_id: UUID, 
        capsule_id: UUID, 
        content_hash: str
    ) -> Optional[CapsuleVersion]:
        """Get version by content hash within a specific Capsule."""
        result = await self.session.execute(
            select(CapsuleVersion)
            .where(and_(
                CapsuleVersion.tenant_id == tenant_id,
                CapsuleVersion.capsule_id == capsule_id,
                CapsuleVersion.content_hash == content_hash
            ))
        )
        return result.scalar_one_or_none()
