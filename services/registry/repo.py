"""
Repository Layer for Capsule Registry

A.4–A.6 Implementation: Data access layer with tenant isolation, idempotency,
and concurrency control using SQLAlchemy with async support.
"""

import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func, desc
from sqlalchemy.orm import selectinload, joinedload

from anumate_idempotency import IdempotencyManager, IdempotencyResult
from anumate_errors import NotFoundError, ConflictError, ValidationError
from .models import (
    Capsule, CapsuleVersion, CapsuleBlob, CapsuleAuditLog,
    CapsuleStatus, CapsuleVisibility, CapsuleRole
)
from .security import SecurityContext


class CapsuleRepository:
    """Repository for capsule data access operations."""
    
    def __init__(self, db_session: AsyncSession, idempotency: IdempotencyManager):
        self.db = db_session
        self.idempotency = idempotency
    
    async def create_capsule(self, security_ctx: SecurityContext,
                           name: str, description: Optional[str] = None,
                           tags: Optional[List[str]] = None,
                           visibility: CapsuleVisibility = CapsuleVisibility.PRIVATE,
                           idempotency_key: Optional[str] = None) -> Capsule:
        """Create new capsule with idempotency support."""
        
        # Check idempotency first
        if idempotency_key:
            cached_result = await self.idempotency.get_result(idempotency_key)
            if cached_result:
                return cached_result.data
        
        # Check if name already exists in tenant
        existing = await self._find_capsule_by_name(security_ctx.tenant_id, name)
        if existing:
            raise ConflictError(f"Capsule with name '{name}' already exists")
        
        # Generate ETag for new capsule
        etag = self._generate_etag(name, security_ctx.actor)
        
        capsule = Capsule(
            id=uuid.uuid4(),
            name=name,
            owner=security_ctx.actor,
            status=CapsuleStatus.DRAFT.value,
            visibility=visibility.value,
            description=description,
            tags=tags or [],
            latest_version=0,
            etag=etag,
            tenant_id=security_ctx.tenant_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        self.db.add(capsule)
        
        # Add audit log
        await self._add_audit_log(
            capsule_id=capsule.id,
            actor=security_ctx.actor,
            action="create",
            tenant_id=security_ctx.tenant_id,
            details={
                "name": name,
                "visibility": visibility.value,
                "description": description,
                "tags": tags
            }
        )
        
        await self.db.commit()
        await self.db.refresh(capsule)
        
        # Cache result for idempotency
        if idempotency_key:
            await self.idempotency.store_result(
                idempotency_key,
                IdempotencyResult(data=capsule, status_code=201)
            )
        
        return capsule
    
    async def get_capsule_by_id(self, security_ctx: SecurityContext,
                              capsule_id: uuid.UUID) -> Optional[Capsule]:
        """Get capsule by ID with tenant isolation."""
        stmt = select(Capsule).where(
            and_(
                Capsule.id == capsule_id,
                Capsule.tenant_id == security_ctx.tenant_id
            )
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_capsules(self, security_ctx: SecurityContext,
                          query: Optional[str] = None,
                          status: Optional[CapsuleStatus] = None,
                          tool: Optional[str] = None,
                          updated_since: Optional[datetime] = None,
                          page: int = 1,
                          page_size: int = 20) -> Tuple[List[Capsule], int]:
        """List capsules with filtering and pagination."""
        
        base_query = select(Capsule).where(
            Capsule.tenant_id == security_ctx.tenant_id
        )
        
        # Apply filters
        if status:
            base_query = base_query.where(Capsule.status == status.value)
        else:
            # Hide deleted by default unless explicitly requested
            base_query = base_query.where(Capsule.status != CapsuleStatus.DELETED.value)
        
        if query:
            # Search in name, description, and tags
            search_filter = or_(
                Capsule.name.ilike(f"%{query}%"),
                Capsule.description.ilike(f"%{query}%"),
                func.array_to_string(Capsule.tags, " ").ilike(f"%{query}%")
            )
            base_query = base_query.where(search_filter)
        
        if updated_since:
            base_query = base_query.where(Capsule.updated_at >= updated_since)
        
        # TODO: Tool filtering would require joining with versions/content
        
        # Get total count
        count_stmt = select(func.count()).select_from(base_query.subquery())
        count_result = await self.db.execute(count_stmt)
        total_count = count_result.scalar()
        
        # Apply pagination and ordering
        offset = (page - 1) * page_size
        list_query = (
            base_query
            .order_by(desc(Capsule.updated_at))
            .offset(offset)
            .limit(page_size)
        )
        
        result = await self.db.execute(list_query)
        capsules = result.scalars().all()
        
        return list(capsules), total_count
    
    async def update_capsule_status(self, security_ctx: SecurityContext,
                                  capsule_id: uuid.UUID,
                                  new_status: CapsuleStatus,
                                  expected_etag: str) -> Capsule:
        """Update capsule status with ETag concurrency control."""
        
        capsule = await self.get_capsule_by_id(security_ctx, capsule_id)
        if not capsule:
            raise NotFoundError("Capsule not found")
        
        # Check ETag for concurrency control
        if capsule.etag != expected_etag:
            raise ConflictError(f"ETag mismatch: expected {expected_etag}, got {capsule.etag}")
        
        # Update status and generate new ETag
        old_status = capsule.status
        new_etag = self._generate_etag(capsule.name, security_ctx.actor, str(new_status.value))
        
        stmt = (
            update(Capsule)
            .where(
                and_(
                    Capsule.id == capsule_id,
                    Capsule.tenant_id == security_ctx.tenant_id
                )
            )
            .values(
                status=new_status.value,
                etag=new_etag,
                updated_at=datetime.now(timezone.utc)
            )
        )
        
        await self.db.execute(stmt)
        
        # Add audit log
        await self._add_audit_log(
            capsule_id=capsule_id,
            actor=security_ctx.actor,
            action="status_change",
            tenant_id=security_ctx.tenant_id,
            details={
                "old_status": old_status,
                "new_status": new_status.value,
                "etag": new_etag
            }
        )
        
        await self.db.commit()
        
        # Refresh capsule data
        updated_capsule = await self.get_capsule_by_id(security_ctx, capsule_id)
        return updated_capsule
    
    async def hard_delete_capsule(self, security_ctx: SecurityContext,
                                capsule_id: uuid.UUID) -> None:
        """Hard delete capsule and all related data."""
        
        capsule = await self.get_capsule_by_id(security_ctx, capsule_id)
        if not capsule:
            raise NotFoundError("Capsule not found")
        
        # Add final audit log before deletion
        await self._add_audit_log(
            capsule_id=capsule_id,
            actor=security_ctx.actor,
            action="hard_delete",
            tenant_id=security_ctx.tenant_id,
            details={
                "name": capsule.name,
                "latest_version": capsule.latest_version
            }
        )
        
        # Delete capsule (cascade will handle versions and audit logs)
        stmt = delete(Capsule).where(
            and_(
                Capsule.id == capsule_id,
                Capsule.tenant_id == security_ctx.tenant_id
            )
        )
        
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def create_version(self, security_ctx: SecurityContext,
                           capsule_id: uuid.UUID,
                           content_hash: str,
                           signature: str,
                           pubkey_id: str,
                           uri: str,
                           idempotency_key: Optional[str] = None) -> CapsuleVersion:
        """Create new capsule version."""
        
        # Check idempotency first
        if idempotency_key:
            cached_result = await self.idempotency.get_result(idempotency_key)
            if cached_result:
                return cached_result.data
        
        capsule = await self.get_capsule_by_id(security_ctx, capsule_id)
        if not capsule:
            raise NotFoundError("Capsule not found")
        
        # Check if content hash already exists for this tenant
        existing_version = await self._find_version_by_hash(security_ctx.tenant_id, content_hash)
        if existing_version:
            if idempotency_key:
                # Return existing version for idempotent request
                await self.idempotency.store_result(
                    idempotency_key,
                    IdempotencyResult(data=existing_version, status_code=200)
                )
            return existing_version
        
        # Create new version
        next_version = capsule.latest_version + 1
        
        version = CapsuleVersion(
            id=uuid.uuid4(),
            capsule_id=capsule_id,
            version=next_version,
            content_hash=content_hash,
            signature=signature,
            pubkey_id=pubkey_id,
            uri=uri,
            tenant_id=security_ctx.tenant_id,
            created_by=security_ctx.actor,
            created_at=datetime.now(timezone.utc)
        )
        
        self.db.add(version)
        
        # Update capsule latest version and ETag
        new_etag = self._generate_etag(capsule.name, security_ctx.actor, content_hash)
        stmt = (
            update(Capsule)
            .where(Capsule.id == capsule_id)
            .values(
                latest_version=next_version,
                etag=new_etag,
                updated_at=datetime.now(timezone.utc)
            )
        )
        
        await self.db.execute(stmt)
        
        # Add audit log
        await self._add_audit_log(
            capsule_id=capsule_id,
            version=next_version,
            actor=security_ctx.actor,
            action="version_create",
            tenant_id=security_ctx.tenant_id,
            details={
                "content_hash": content_hash,
                "signature": signature,
                "pubkey_id": pubkey_id,
                "uri": uri
            }
        )
        
        await self.db.commit()
        await self.db.refresh(version)
        
        # Cache result for idempotency
        if idempotency_key:
            await self.idempotency.store_result(
                idempotency_key,
                IdempotencyResult(data=version, status_code=201)
            )
        
        return version
    
    async def get_version_by_number(self, security_ctx: SecurityContext,
                                  capsule_id: uuid.UUID,
                                  version_number: int) -> Optional[CapsuleVersion]:
        """Get specific version by number."""
        stmt = select(CapsuleVersion).where(
            and_(
                CapsuleVersion.capsule_id == capsule_id,
                CapsuleVersion.version == version_number,
                CapsuleVersion.tenant_id == security_ctx.tenant_id
            )
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_versions(self, security_ctx: SecurityContext,
                          capsule_id: uuid.UUID) -> List[CapsuleVersion]:
        """List all versions for a capsule."""
        stmt = (
            select(CapsuleVersion)
            .where(
                and_(
                    CapsuleVersion.capsule_id == capsule_id,
                    CapsuleVersion.tenant_id == security_ctx.tenant_id
                )
            )
            .order_by(desc(CapsuleVersion.version))
        )
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def store_blob(self, security_ctx: SecurityContext,
                       content_hash: str,
                       yaml_content: str) -> CapsuleBlob:
        """Store YAML blob content."""
        
        # Check if blob already exists
        existing = await self._find_blob_by_hash(content_hash)
        if existing:
            return existing
        
        size_bytes = len(yaml_content.encode("utf-8"))
        
        blob = CapsuleBlob(
            id=uuid.uuid4(),
            content_hash=content_hash,
            yaml_text=yaml_content,
            size_bytes=size_bytes,
            tenant_id=security_ctx.tenant_id,
            created_at=datetime.now(timezone.utc)
        )
        
        self.db.add(blob)
        await self.db.commit()
        await self.db.refresh(blob)
        
        return blob
    
    async def get_blob_by_hash(self, content_hash: str) -> Optional[CapsuleBlob]:
        """Get blob by content hash."""
        return await self._find_blob_by_hash(content_hash)
    
    # Private helper methods
    
    async def _find_capsule_by_name(self, tenant_id: uuid.UUID, name: str) -> Optional[Capsule]:
        """Find capsule by name within tenant."""
        stmt = select(Capsule).where(
            and_(
                Capsule.tenant_id == tenant_id,
                Capsule.name == name
            )
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _find_version_by_hash(self, tenant_id: uuid.UUID, content_hash: str) -> Optional[CapsuleVersion]:
        """Find version by content hash within tenant."""
        stmt = select(CapsuleVersion).where(
            and_(
                CapsuleVersion.tenant_id == tenant_id,
                CapsuleVersion.content_hash == content_hash
            )
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _find_blob_by_hash(self, content_hash: str) -> Optional[CapsuleBlob]:
        """Find blob by content hash."""
        stmt = select(CapsuleBlob).where(CapsuleBlob.content_hash == content_hash)
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _add_audit_log(self, capsule_id: uuid.UUID, actor: str,
                           action: str, tenant_id: uuid.UUID,
                           details: Dict[str, Any],
                           version: Optional[int] = None) -> None:
        """Add audit log entry."""
        
        audit_log = CapsuleAuditLog(
            id=uuid.uuid4(),
            capsule_id=capsule_id,
            version=version,
            actor=actor,
            action=action,
            details=details,
            tenant_id=tenant_id,
            timestamp=datetime.now(timezone.utc)
        )
        
        self.db.add(audit_log)
    
    def _generate_etag(self, *components: str) -> str:
        """Generate ETag from components."""
        content = "|".join(str(c) for c in components)
        return hashlib.md5(content.encode()).hexdigest()[:16]


def create_repository(db_session: AsyncSession,
                     idempotency: IdempotencyManager) -> CapsuleRepository:
    """Factory function to create repository instance."""
    return CapsuleRepository(db_session, idempotency)
