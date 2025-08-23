"""Capsule Repository for database operations."""

import json
from typing import List, Optional, Dict, Any
from uuid import UUID

import structlog
from anumate_infrastructure.database import DatabaseManager
from anumate_infrastructure.tenant_context import get_current_tenant_id

from .models import Capsule, CapsuleDefinition

logger = structlog.get_logger(__name__)


class CapsuleRepository:
    """Repository for Capsule database operations with tenant isolation."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize repository with database manager."""
        self.db = db_manager
    
    async def create(self, capsule: Capsule) -> Capsule:
        """Create a new Capsule in the database."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        logger.info("Creating capsule", 
                   capsule_id=str(capsule.capsule_id),
                   name=capsule.name,
                   version=capsule.version,
                   tenant_id=str(tenant_id))
        
        query = """
            INSERT INTO capsules (
                capsule_id, tenant_id, name, version, definition, 
                checksum, created_by, created_at, active
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
        """
        
        result = await self.db.fetchrow(
            query,
            capsule.capsule_id,
            capsule.tenant_id,
            capsule.name,
            capsule.version,
            json.dumps(capsule.definition.model_dump()),
            capsule.checksum,
            capsule.created_by,
            capsule.created_at,
            capsule.active
        )
        
        if result is None:
            raise RuntimeError("Failed to create capsule")
        
        logger.info("Capsule created successfully", 
                   capsule_id=str(capsule.capsule_id))
        
        return Capsule.from_db_record(dict(result))
    
    async def get_by_id(self, capsule_id: UUID) -> Optional[Capsule]:
        """Get a Capsule by ID."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        logger.debug("Fetching capsule by ID", 
                    capsule_id=str(capsule_id),
                    tenant_id=str(tenant_id))
        
        query = """
            SELECT * FROM capsules 
            WHERE capsule_id = $1 AND active = true
        """
        
        result = await self.db.fetchrow(query, capsule_id)
        
        if result is None:
            logger.debug("Capsule not found", capsule_id=str(capsule_id))
            return None
        
        return Capsule.from_db_record(dict(result))
    
    async def get_by_name_version(self, name: str, version: str) -> Optional[Capsule]:
        """Get a Capsule by name and version."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        logger.debug("Fetching capsule by name and version", 
                    name=name, version=version, tenant_id=str(tenant_id))
        
        query = """
            SELECT * FROM capsules 
            WHERE name = $1 AND version = $2 AND active = true
        """
        
        result = await self.db.fetchrow(query, name, version)
        
        if result is None:
            logger.debug("Capsule not found", name=name, version=version)
            return None
        
        return Capsule.from_db_record(dict(result))
    
    async def list_by_name(self, name: str) -> List[Capsule]:
        """List all versions of a Capsule by name."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        logger.debug("Listing capsule versions", 
                    name=name, tenant_id=str(tenant_id))
        
        query = """
            SELECT * FROM capsules 
            WHERE name = $1 AND active = true
            ORDER BY created_at DESC
        """
        
        results = await self.db.fetch(query, name)
        
        capsules = [Capsule.from_db_record(dict(row)) for row in results]
        
        logger.debug("Found capsule versions", 
                    name=name, count=len(capsules))
        
        return capsules
    
    async def list_all(
        self, 
        page: int = 1, 
        page_size: int = 50,
        name_filter: Optional[str] = None,
        active_only: bool = True
    ) -> tuple[List[Capsule], int]:
        """List all Capsules with pagination and filtering."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        logger.debug("Listing capsules", 
                    page=page, page_size=page_size, 
                    name_filter=name_filter, tenant_id=str(tenant_id))
        
        # Build WHERE clause
        where_conditions = []
        params = []
        param_count = 0
        
        if active_only:
            param_count += 1
            where_conditions.append(f"active = ${param_count}")
            params.append(True)
        
        if name_filter:
            param_count += 1
            where_conditions.append(f"name ILIKE ${param_count}")
            params.append(f"%{name_filter}%")
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Count total records
        count_query = f"SELECT COUNT(*) FROM capsules {where_clause}"
        total = await self.db.fetchval(count_query, *params)
        
        # Fetch paginated results
        offset = (page - 1) * page_size
        param_count += 1
        limit_param = f"${param_count}"
        params.append(page_size)
        
        param_count += 1
        offset_param = f"${param_count}"
        params.append(offset)
        
        query = f"""
            SELECT * FROM capsules 
            {where_clause}
            ORDER BY created_at DESC
            LIMIT {limit_param} OFFSET {offset_param}
        """
        
        results = await self.db.fetch(query, *params)
        
        capsules = [Capsule.from_db_record(dict(row)) for row in results]
        
        logger.debug("Listed capsules", 
                    count=len(capsules), total=total, page=page)
        
        return capsules, total
    
    async def update(self, capsule: Capsule) -> Capsule:
        """Update an existing Capsule."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        logger.info("Updating capsule", 
                   capsule_id=str(capsule.capsule_id),
                   name=capsule.name,
                   version=capsule.version,
                   tenant_id=str(tenant_id))
        
        query = """
            UPDATE capsules 
            SET definition = $2, checksum = $3, active = $4
            WHERE capsule_id = $1
            RETURNING *
        """
        
        result = await self.db.fetchrow(
            query,
            capsule.capsule_id,
            json.dumps(capsule.definition.model_dump()),
            capsule.checksum,
            capsule.active
        )
        
        if result is None:
            raise RuntimeError(f"Capsule {capsule.capsule_id} not found or update failed")
        
        logger.info("Capsule updated successfully", 
                   capsule_id=str(capsule.capsule_id))
        
        return Capsule.from_db_record(dict(result))
    
    async def soft_delete(self, capsule_id: UUID) -> bool:
        """Soft delete a Capsule by setting active=false."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        logger.info("Soft deleting capsule", 
                   capsule_id=str(capsule_id),
                   tenant_id=str(tenant_id))
        
        query = """
            UPDATE capsules 
            SET active = false
            WHERE capsule_id = $1
        """
        
        result = await self.db.execute(query, capsule_id)
        
        # Check if any rows were affected
        rows_affected = int(result.split()[-1]) if result else 0
        success = rows_affected > 0
        
        if success:
            logger.info("Capsule soft deleted successfully", 
                       capsule_id=str(capsule_id))
        else:
            logger.warning("Capsule not found for deletion", 
                          capsule_id=str(capsule_id))
        
        return success
    
    async def exists(self, name: str, version: str) -> bool:
        """Check if a Capsule with given name and version exists."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        query = """
            SELECT EXISTS(
                SELECT 1 FROM capsules 
                WHERE name = $1 AND version = $2 AND active = true
            )
        """
        
        result = await self.db.fetchval(query, name, version)
        return bool(result)
    
    async def get_latest_version(self, name: str) -> Optional[Capsule]:
        """Get the latest version of a Capsule by name."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        logger.debug("Fetching latest version", 
                    name=name, tenant_id=str(tenant_id))
        
        query = """
            SELECT * FROM capsules 
            WHERE name = $1 AND active = true
            ORDER BY created_at DESC
            LIMIT 1
        """
        
        result = await self.db.fetchrow(query, name)
        
        if result is None:
            logger.debug("No versions found", name=name)
            return None
        
        return Capsule.from_db_record(dict(result))
    
    async def get_dependencies(self, capsule_id: UUID) -> List[Capsule]:
        """Get all dependencies for a Capsule."""
        capsule = await self.get_by_id(capsule_id)
        if capsule is None:
            return []
        
        dependencies = []
        for dep in capsule.definition.dependencies:
            # Parse dependency string (name@version)
            if "@" in dep:
                dep_name, dep_version = dep.split("@", 1)
                dep_capsule = await self.get_by_name_version(dep_name, dep_version)
                if dep_capsule:
                    dependencies.append(dep_capsule)
        
        return dependencies