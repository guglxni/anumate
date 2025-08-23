"""Capsule Registry Service - Business logic layer."""

from typing import List, Optional, Tuple
from uuid import UUID

import structlog
from cryptography.hazmat.primitives.asymmetric import ed25519
from anumate_infrastructure.database import DatabaseManager
from anumate_infrastructure.tenant_context import get_current_tenant_id

from .models import (
    Capsule, 
    CapsuleDefinition, 
    CapsuleSignature,
    CapsuleCreateRequest,
    CapsuleUpdateRequest,
    CapsuleValidationResult,
    DependencyResolutionResult,
    CapsuleDiff,
    ComposedCapsule,
    ApprovalStatus
)
from .repository import CapsuleRepository
from .validation import capsule_validator
from .dependency_resolver import DependencyResolver
from .composition import CapsuleComposer
from .diff_tracker import CapsuleDiffTracker
from .approval_workflow import ApprovalWorkflowManager

logger = structlog.get_logger(__name__)


class CapsuleRegistryService:
    """Service layer for Capsule Registry operations."""
    
    def __init__(self, db_manager: DatabaseManager, event_bus=None):
        """Initialize service with database manager and optional event bus."""
        self.db_manager = db_manager
        self.repository = CapsuleRepository(db_manager)
        self.dependency_resolver = DependencyResolver(self.repository)
        self.composer = CapsuleComposer(self.repository)
        self.diff_tracker = CapsuleDiffTracker(self.repository)
        self.approval_manager = ApprovalWorkflowManager(db_manager, event_bus)
    
    async def create_capsule(
        self, 
        request: CapsuleCreateRequest, 
        created_by: UUID,
        signing_key: Optional[ed25519.Ed25519PrivateKey] = None
    ) -> Capsule:
        """Create a new Capsule with validation and optional signing."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        logger.info("Creating new capsule", 
                   tenant_id=str(tenant_id), 
                   created_by=str(created_by))
        
        # 1. Validate YAML content
        validation_result = capsule_validator.validate_complete(request.yaml_content)
        if not validation_result.valid:
            logger.warning("Capsule validation failed", 
                          errors=validation_result.errors)
            raise ValueError(f"Validation failed: {'; '.join(validation_result.errors)}")
        
        # 2. Parse definition
        definition = request.to_capsule_definition()
        
        # 3. Check if capsule already exists
        existing = await self.repository.get_by_name_version(definition.name, definition.version)
        if existing is not None:
            raise ValueError(f"Capsule {definition.name}@{definition.version} already exists")
        
        # 4. Create signature if requested
        signature = None
        if request.sign_capsule and signing_key is not None:
            signature = CapsuleSignature.create_signature(
                definition, 
                signing_key, 
                str(created_by)
            )
            logger.info("Capsule signed", 
                       capsule_name=definition.name,
                       signer=str(created_by))
        
        # 5. Create Capsule instance
        capsule = Capsule.create(
            tenant_id=tenant_id,
            definition=definition,
            created_by=created_by,
            signature=signature
        )
        
        # 6. Store in database
        async with self.db_manager.transaction() as conn:
            created_capsule = await self.repository.create(capsule)
        
        logger.info("Capsule created successfully", 
                   capsule_id=str(created_capsule.capsule_id),
                   name=created_capsule.name,
                   version=created_capsule.version)
        
        return created_capsule
    
    async def get_capsule(self, capsule_id: UUID) -> Optional[Capsule]:
        """Get a Capsule by ID."""
        logger.debug("Fetching capsule", capsule_id=str(capsule_id))
        
        capsule = await self.repository.get_by_id(capsule_id)
        
        if capsule is None:
            logger.debug("Capsule not found", capsule_id=str(capsule_id))
        
        return capsule
    
    async def get_capsule_by_name_version(self, name: str, version: str) -> Optional[Capsule]:
        """Get a Capsule by name and version."""
        logger.debug("Fetching capsule by name/version", 
                    name=name, version=version)
        
        capsule = await self.repository.get_by_name_version(name, version)
        
        if capsule is None:
            logger.debug("Capsule not found", name=name, version=version)
        
        return capsule
    
    async def list_capsules(
        self, 
        page: int = 1, 
        page_size: int = 50,
        name_filter: Optional[str] = None
    ) -> Tuple[List[Capsule], int]:
        """List Capsules with pagination and filtering."""
        logger.debug("Listing capsules", 
                    page=page, page_size=page_size, name_filter=name_filter)
        
        # Validate pagination parameters
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 50
        
        capsules, total = await self.repository.list_all(
            page=page,
            page_size=page_size,
            name_filter=name_filter,
            active_only=True
        )
        
        logger.debug("Listed capsules", 
                    count=len(capsules), total=total)
        
        return capsules, total
    
    async def list_capsule_versions(self, name: str) -> List[Capsule]:
        """List all versions of a Capsule."""
        logger.debug("Listing capsule versions", name=name)
        
        versions = await self.repository.list_by_name(name)
        
        logger.debug("Found capsule versions", 
                    name=name, count=len(versions))
        
        return versions
    
    async def update_capsule(
        self, 
        capsule_id: UUID, 
        request: CapsuleUpdateRequest,
        signing_key: Optional[ed25519.Ed25519PrivateKey] = None
    ) -> Capsule:
        """Update an existing Capsule (creates new version)."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set")
        
        logger.info("Updating capsule", 
                   capsule_id=str(capsule_id),
                   tenant_id=str(tenant_id))
        
        # 1. Get existing capsule
        existing_capsule = await self.repository.get_by_id(capsule_id)
        if existing_capsule is None:
            raise ValueError(f"Capsule {capsule_id} not found")
        
        # 2. Validate new YAML content
        validation_result = capsule_validator.validate_complete(request.yaml_content)
        if not validation_result.valid:
            logger.warning("Capsule validation failed", 
                          errors=validation_result.errors)
            raise ValueError(f"Validation failed: {'; '.join(validation_result.errors)}")
        
        # 3. Parse new definition
        new_definition = request.to_capsule_definition()
        
        # 4. Check if this creates a new version
        if new_definition.version != existing_capsule.version:
            # This is a new version - check if it already exists
            existing_version = await self.repository.get_by_name_version(
                new_definition.name, new_definition.version
            )
            if existing_version is not None:
                raise ValueError(f"Version {new_definition.version} already exists")
        
        # 5. Create signature if requested
        signature = None
        if request.sign_capsule and signing_key is not None:
            signature = CapsuleSignature.create_signature(
                new_definition, 
                signing_key, 
                str(existing_capsule.created_by)
            )
        
        # 6. Update capsule
        existing_capsule.definition = new_definition
        existing_capsule.checksum = new_definition.calculate_checksum()
        existing_capsule.signature = signature
        
        # 7. Store updated capsule
        async with self.db_manager.transaction() as conn:
            updated_capsule = await self.repository.update(existing_capsule)
        
        logger.info("Capsule updated successfully", 
                   capsule_id=str(updated_capsule.capsule_id))
        
        return updated_capsule
    
    async def delete_capsule(self, capsule_id: UUID) -> bool:
        """Soft delete a Capsule."""
        logger.info("Deleting capsule", capsule_id=str(capsule_id))
        
        # Check if capsule exists
        existing_capsule = await self.repository.get_by_id(capsule_id)
        if existing_capsule is None:
            logger.warning("Capsule not found for deletion", 
                          capsule_id=str(capsule_id))
            return False
        
        # Perform soft delete
        success = await self.repository.soft_delete(capsule_id)
        
        if success:
            logger.info("Capsule deleted successfully", 
                       capsule_id=str(capsule_id))
        
        return success
    
    async def validate_capsule_yaml(self, yaml_content: str) -> CapsuleValidationResult:
        """Validate Capsule YAML without creating it."""
        logger.debug("Validating capsule YAML")
        
        result = capsule_validator.validate_complete(yaml_content)
        
        logger.debug("Validation completed", 
                    valid=result.valid, 
                    error_count=len(result.errors),
                    warning_count=len(result.warnings))
        
        return result
    
    async def verify_capsule_signature(self, capsule_id: UUID) -> bool:
        """Verify the digital signature of a Capsule."""
        logger.debug("Verifying capsule signature", 
                    capsule_id=str(capsule_id))
        
        capsule = await self.repository.get_by_id(capsule_id)
        if capsule is None:
            logger.warning("Capsule not found for signature verification", 
                          capsule_id=str(capsule_id))
            return False
        
        if capsule.signature is None:
            logger.debug("Capsule has no signature", 
                        capsule_id=str(capsule_id))
            return False
        
        is_valid = capsule.signature.verify_signature(capsule.definition)
        
        logger.debug("Signature verification completed", 
                    capsule_id=str(capsule_id), 
                    valid=is_valid)
        
        return is_valid
    
    async def get_capsule_dependencies(self, capsule_id: UUID) -> List[Capsule]:
        """Get all dependencies for a Capsule."""
        logger.debug("Fetching capsule dependencies", 
                    capsule_id=str(capsule_id))
        
        dependencies = await self.repository.get_dependencies(capsule_id)
        
        logger.debug("Found dependencies", 
                    capsule_id=str(capsule_id), 
                    count=len(dependencies))
        
        return dependencies
    
    async def get_latest_version(self, name: str) -> Optional[Capsule]:
        """Get the latest version of a Capsule by name."""
        logger.debug("Fetching latest version", name=name)
        
        capsule = await self.repository.get_latest_version(name)
        
        if capsule is None:
            logger.debug("No versions found", name=name)
        else:
            logger.debug("Found latest version", 
                        name=name, version=capsule.version)
        
        return capsule
    
    async def check_capsule_integrity(self, capsule_id: UUID) -> bool:
        """Check the integrity of a Capsule (checksum validation)."""
        logger.debug("Checking capsule integrity", 
                    capsule_id=str(capsule_id))
        
        capsule = await self.repository.get_by_id(capsule_id)
        if capsule is None:
            logger.warning("Capsule not found for integrity check", 
                          capsule_id=str(capsule_id))
            return False
        
        # Recalculate checksum and compare
        expected_checksum = capsule.definition.calculate_checksum()
        is_valid = expected_checksum == capsule.checksum
        
        if not is_valid:
            logger.warning("Capsule integrity check failed", 
                          capsule_id=str(capsule_id),
                          expected=expected_checksum,
                          actual=capsule.checksum)
        else:
            logger.debug("Capsule integrity check passed", 
                        capsule_id=str(capsule_id))
        
        return is_valid
    
    # Dependency Resolution Methods
    
    async def resolve_capsule_dependencies(self, capsule_id: UUID) -> DependencyResolutionResult:
        """Resolve all dependencies for a Capsule."""
        logger.debug("Resolving capsule dependencies", 
                    capsule_id=str(capsule_id))
        
        capsule = await self.repository.get_by_id(capsule_id)
        if capsule is None:
            raise ValueError(f"Capsule {capsule_id} not found")
        
        return await self.dependency_resolver.resolve_dependencies(
            capsule.definition.dependencies
        )
    
    async def get_dependency_tree(self, capsule_id: UUID) -> Dict[str, any]:
        """Get the full dependency tree for a Capsule."""
        capsule = await self.repository.get_by_id(capsule_id)
        if capsule is None:
            raise ValueError(f"Capsule {capsule_id} not found")
        
        return await self.dependency_resolver.get_dependency_tree(capsule)
    
    # Composition and Inheritance Methods
    
    async def compose_capsule(self, capsule_id: UUID) -> ComposedCapsule:
        """Compose a Capsule with its inheritance and composition chain."""
        logger.debug("Composing capsule", capsule_id=str(capsule_id))
        
        capsule = await self.repository.get_by_id(capsule_id)
        if capsule is None:
            raise ValueError(f"Capsule {capsule_id} not found")
        
        return await self.composer.compose_capsule(capsule)
    
    async def validate_capsule_composition(self, capsule_id: UUID) -> List[str]:
        """Validate that a Capsule's composition is valid."""
        capsule = await self.repository.get_by_id(capsule_id)
        if capsule is None:
            raise ValueError(f"Capsule {capsule_id} not found")
        
        return await self.composer.validate_composition(capsule)
    
    # Diff and Change Tracking Methods
    
    async def get_capsule_diff(
        self, 
        name: str, 
        from_version: str, 
        to_version: str
    ) -> Optional[CapsuleDiff]:
        """Get diff between two versions of a Capsule."""
        return await self.diff_tracker.get_diff_between_versions(
            name, from_version, to_version
        )
    
    async def get_capsule_changelog(self, name: str, limit: Optional[int] = None) -> List[CapsuleDiff]:
        """Get the complete changelog for a Capsule."""
        return await self.diff_tracker.get_changelog(name, limit)
    
    async def get_version_history(self, name: str) -> List[Capsule]:
        """Get the version history for a Capsule."""
        return await self.diff_tracker.get_version_history(name)
    
    # Approval Workflow Methods
    
    async def request_capsule_approval(
        self, 
        capsule_id: UUID, 
        requester_id: UUID,
        approval_metadata: Optional[Dict[str, Any]] = None
    ) -> ApprovalStatus:
        """Request approval for a Capsule."""
        capsule = await self.repository.get_by_id(capsule_id)
        if capsule is None:
            raise ValueError(f"Capsule {capsule_id} not found")
        
        return await self.approval_manager.create_approval_request(
            capsule, requester_id, approval_metadata
        )
    
    async def approve_capsule(
        self, 
        capsule_id: UUID, 
        approver_id: UUID,
        approval_comments: Optional[str] = None
    ) -> bool:
        """Approve a Capsule."""
        return await self.approval_manager.approve_capsule(
            capsule_id, approver_id, approval_comments
        )
    
    async def reject_capsule(
        self, 
        capsule_id: UUID, 
        approver_id: UUID,
        rejection_reason: str
    ) -> bool:
        """Reject a Capsule."""
        return await self.approval_manager.reject_capsule(
            capsule_id, approver_id, rejection_reason
        )
    
    async def get_approval_status(self, capsule_id: UUID) -> Optional[ApprovalStatus]:
        """Get the current approval status for a Capsule."""
        return await self.approval_manager.get_approval_status(capsule_id)
    
    async def list_pending_approvals(
        self, 
        page: int = 1, 
        page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """List all pending approval requests."""
        return await self.approval_manager.list_pending_approvals(page, page_size)
    
    async def get_approval_history(self, capsule_id: UUID) -> List[Dict[str, Any]]:
        """Get the approval history for a Capsule."""
        return await self.approval_manager.get_approval_history(capsule_id)
    
    # Enhanced Create Method with Business Logic
    
    async def create_capsule_with_workflow(
        self, 
        request: CapsuleCreateRequest, 
        created_by: UUID,
        signing_key: Optional[ed25519.Ed25519PrivateKey] = None,
        auto_approve: bool = True
    ) -> Tuple[Capsule, Optional[ApprovalStatus]]:
        """Create a Capsule with full workflow including validation, composition check, and approval."""
        logger.info("Creating capsule with workflow", 
                   created_by=str(created_by), auto_approve=auto_approve)
        
        # 1. Create the capsule using existing logic
        capsule = await self.create_capsule(request, created_by, signing_key)
        
        # 2. Validate composition if applicable
        if capsule.definition.inherits_from or capsule.definition.composed_of:
            composition_errors = await self.validate_capsule_composition(capsule.capsule_id)
            if composition_errors:
                logger.warning("Composition validation failed", 
                              errors=composition_errors)
                # Update validation status
                capsule.validation_status = "failed"
                capsule.validation_errors = composition_errors
                await self.repository.update(capsule)
                raise ValueError(f"Composition validation failed: {'; '.join(composition_errors)}")
        
        # 3. Check if approval is required
        approval_status = None
        if await self.approval_manager.check_approval_required(capsule):
            if auto_approve and await self.approval_manager.auto_approve_if_eligible(capsule, created_by):
                approval_status = await self.get_approval_status(capsule.capsule_id)
            else:
                approval_status = await self.request_capsule_approval(capsule, created_by)
        else:
            # No approval required, mark as approved
            capsule.validation_status = "approved"
            await self.repository.update(capsule)
        
        logger.info("Capsule created with workflow", 
                   capsule_id=str(capsule.capsule_id),
                   approval_required=approval_status is not None)
        
        return capsule, approval_status