"""Capsule Registry API endpoints."""

from typing import Annotated, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from ..dependencies import (
    get_capsule_service,
    get_current_tenant,
    get_current_user,
    get_optional_signing_key
)
from src.service import CapsuleRegistryService
from src.models import (
    Capsule,
    CapsuleCreateRequest,
    CapsuleUpdateRequest,
    CapsuleListResponse,
    CapsuleValidationResult
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=Capsule,
    status_code=status.HTTP_201_CREATED,
    summary="Create new Capsule",
    description="Create a new Capsule from YAML definition with optional signing"
)
async def create_capsule(
    request: CapsuleCreateRequest,
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_user: Annotated[UUID, Depends(get_current_user)],
    signing_key: Annotated[Optional[object], Depends(get_optional_signing_key)]
) -> Capsule:
    """Create a new Capsule."""
    try:
        logger.info("Creating new capsule", user_id=str(current_user))
        
        capsule = await service.create_capsule(
            request=request,
            created_by=current_user,
            signing_key=signing_key
        )
        
        logger.info("Capsule created successfully", 
                   capsule_id=str(capsule.capsule_id),
                   name=capsule.name,
                   version=capsule.version)
        
        return capsule
        
    except ValueError as e:
        logger.warning("Capsule creation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Unexpected error creating capsule", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "",
    response_model=CapsuleListResponse,
    summary="List Capsules",
    description="List Capsules with pagination and optional name filtering"
)
async def list_capsules(
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    name: Annotated[Optional[str], Query(description="Filter by name (partial match)")] = None
) -> CapsuleListResponse:
    """List Capsules with pagination and filtering."""
    try:
        logger.debug("Listing capsules", 
                    tenant_id=str(current_tenant),
                    page=page, 
                    page_size=page_size,
                    name_filter=name)
        
        capsules, total = await service.list_capsules(
            page=page,
            page_size=page_size,
            name_filter=name
        )
        
        logger.debug("Listed capsules successfully", 
                    count=len(capsules),
                    total=total)
        
        return CapsuleListResponse(
            capsules=capsules,
            total=total,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error("Error listing capsules", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/{capsule_id}",
    response_model=Capsule,
    summary="Get Capsule by ID",
    description="Get a specific Capsule by its ID"
)
async def get_capsule(
    capsule_id: UUID,
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> Capsule:
    """Get a specific Capsule by ID."""
    try:
        logger.debug("Fetching capsule", 
                    capsule_id=str(capsule_id),
                    tenant_id=str(current_tenant))
        
        capsule = await service.get_capsule(capsule_id)
        
        if capsule is None:
            logger.warning("Capsule not found", capsule_id=str(capsule_id))
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Capsule {capsule_id} not found"
            )
        
        logger.debug("Capsule fetched successfully", 
                    capsule_id=str(capsule_id))
        
        return capsule
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching capsule", 
                    capsule_id=str(capsule_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.put(
    "/{capsule_id}",
    response_model=Capsule,
    summary="Update Capsule",
    description="Update an existing Capsule (creates new version if version changed)"
)
async def update_capsule(
    capsule_id: UUID,
    request: CapsuleUpdateRequest,
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)],
    signing_key: Annotated[Optional[object], Depends(get_optional_signing_key)]
) -> Capsule:
    """Update an existing Capsule."""
    try:
        logger.info("Updating capsule", 
                   capsule_id=str(capsule_id),
                   tenant_id=str(current_tenant))
        
        capsule = await service.update_capsule(
            capsule_id=capsule_id,
            request=request,
            signing_key=signing_key
        )
        
        logger.info("Capsule updated successfully", 
                   capsule_id=str(capsule_id))
        
        return capsule
        
    except ValueError as e:
        logger.warning("Capsule update failed", 
                      capsule_id=str(capsule_id),
                      error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating capsule", 
                    capsule_id=str(capsule_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete(
    "/{capsule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Capsule",
    description="Soft delete a Capsule (sets active=false)"
)
async def delete_capsule(
    capsule_id: UUID,
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> None:
    """Soft delete a Capsule."""
    try:
        logger.info("Deleting capsule", 
                   capsule_id=str(capsule_id),
                   tenant_id=str(current_tenant))
        
        success = await service.delete_capsule(capsule_id)
        
        if not success:
            logger.warning("Capsule not found for deletion", 
                          capsule_id=str(capsule_id))
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Capsule {capsule_id} not found"
            )
        
        logger.info("Capsule deleted successfully", 
                   capsule_id=str(capsule_id))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting capsule", 
                    capsule_id=str(capsule_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


# Additional endpoints for enhanced functionality

@router.get(
    "/by-name/{name}",
    response_model=List[Capsule],
    summary="Get Capsule versions by name",
    description="Get all versions of a Capsule by name"
)
async def get_capsule_versions(
    name: str,
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> List[Capsule]:
    """Get all versions of a Capsule by name."""
    try:
        logger.debug("Fetching capsule versions", 
                    name=name,
                    tenant_id=str(current_tenant))
        
        versions = await service.list_capsule_versions(name)
        
        logger.debug("Capsule versions fetched successfully", 
                    name=name,
                    count=len(versions))
        
        return versions
        
    except Exception as e:
        logger.error("Error fetching capsule versions", 
                    name=name,
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/by-name/{name}/latest",
    response_model=Capsule,
    summary="Get latest Capsule version",
    description="Get the latest version of a Capsule by name"
)
async def get_latest_capsule_version(
    name: str,
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> Capsule:
    """Get the latest version of a Capsule by name."""
    try:
        logger.debug("Fetching latest capsule version", 
                    name=name,
                    tenant_id=str(current_tenant))
        
        capsule = await service.get_latest_version(name)
        
        if capsule is None:
            logger.warning("Capsule not found", name=name)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Capsule '{name}' not found"
            )
        
        logger.debug("Latest capsule version fetched successfully", 
                    name=name,
                    version=capsule.version)
        
        return capsule
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching latest capsule version", 
                    name=name,
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/validate",
    response_model=CapsuleValidationResult,
    summary="Validate Capsule YAML",
    description="Validate Capsule YAML without creating it"
)
async def validate_capsule_yaml(
    yaml_content: str,
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> CapsuleValidationResult:
    """Validate Capsule YAML without creating it."""
    try:
        logger.debug("Validating capsule YAML", 
                    tenant_id=str(current_tenant))
        
        result = await service.validate_capsule_yaml(yaml_content)
        
        logger.debug("Capsule YAML validation completed", 
                    valid=result.valid,
                    error_count=len(result.errors))
        
        return result
        
    except Exception as e:
        logger.error("Error validating capsule YAML", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/{capsule_id}/verify-signature",
    response_model=dict,
    summary="Verify Capsule signature",
    description="Verify the digital signature of a Capsule"
)
async def verify_capsule_signature(
    capsule_id: UUID,
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> dict:
    """Verify the digital signature of a Capsule."""
    try:
        logger.debug("Verifying capsule signature", 
                    capsule_id=str(capsule_id),
                    tenant_id=str(current_tenant))
        
        is_valid = await service.verify_capsule_signature(capsule_id)
        
        logger.debug("Capsule signature verification completed", 
                    capsule_id=str(capsule_id),
                    valid=is_valid)
        
        return {
            "capsule_id": str(capsule_id),
            "signature_valid": is_valid
        }
        
    except Exception as e:
        logger.error("Error verifying capsule signature", 
                    capsule_id=str(capsule_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/{capsule_id}/dependencies",
    response_model=List[Capsule],
    summary="Get Capsule dependencies",
    description="Get all dependencies for a Capsule"
)
async def get_capsule_dependencies(
    capsule_id: UUID,
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> List[Capsule]:
    """Get all dependencies for a Capsule."""
    try:
        logger.debug("Fetching capsule dependencies", 
                    capsule_id=str(capsule_id),
                    tenant_id=str(current_tenant))
        
        dependencies = await service.get_capsule_dependencies(capsule_id)
        
        logger.debug("Capsule dependencies fetched successfully", 
                    capsule_id=str(capsule_id),
                    count=len(dependencies))
        
        return dependencies
        
    except Exception as e:
        logger.error("Error fetching capsule dependencies", 
                    capsule_id=str(capsule_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/{capsule_id}/check-integrity",
    response_model=dict,
    summary="Check Capsule integrity",
    description="Check the integrity of a Capsule (checksum validation)"
)
async def check_capsule_integrity(
    capsule_id: UUID,
    service: Annotated[CapsuleRegistryService, Depends(get_capsule_service)],
    current_tenant: Annotated[UUID, Depends(get_current_tenant)]
) -> dict:
    """Check the integrity of a Capsule."""
    try:
        logger.debug("Checking capsule integrity", 
                    capsule_id=str(capsule_id),
                    tenant_id=str(current_tenant))
        
        is_valid = await service.check_capsule_integrity(capsule_id)
        
        logger.debug("Capsule integrity check completed", 
                    capsule_id=str(capsule_id),
                    valid=is_valid)
        
        return {
            "capsule_id": str(capsule_id),
            "integrity_valid": is_valid
        }
        
    except Exception as e:
        logger.error("Error checking capsule integrity", 
                    capsule_id=str(capsule_id),
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )