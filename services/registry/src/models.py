"""Capsule Registry data models."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import yaml
from pydantic import BaseModel, Field, field_validator
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


class CapsuleDefinition(BaseModel):
    """Capsule YAML definition model."""
    
    name: str = Field(..., description="Capsule name")
    version: str = Field(..., description="Semantic version")
    description: Optional[str] = Field(None, description="Capsule description")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Capsule metadata")
    labels: Dict[str, str] = Field(default_factory=dict, description="Capsule labels")
    annotations: Dict[str, str] = Field(default_factory=dict, description="Capsule annotations")
    
    # Dependencies and composition
    dependencies: List[str] = Field(default_factory=list, description="Capsule dependencies")
    inherits_from: Optional[str] = Field(None, description="Parent capsule for inheritance")
    composed_of: List[str] = Field(default_factory=list, description="Capsules to compose into this one")
    
    # Automation definition
    automation: Dict[str, Any] = Field(..., description="Automation workflow definition")
    
    # Tool allowlist
    tools: List[str] = Field(default_factory=list, description="Allowed tools for this capsule")
    
    # Policy references
    policies: List[str] = Field(default_factory=list, description="Policy references")
    
    @field_validator('version')
    @classmethod
    def validate_version(cls, v):
        """Validate semantic version format."""
        import re
        semver_pattern = r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
        if not re.match(semver_pattern, v):
            raise ValueError('Version must follow semantic versioning (e.g., 1.0.0)')
        return v
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """Validate capsule name format."""
        import re
        if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', v):
            raise ValueError('Name must be lowercase alphanumeric with hyphens')
        return v
    
    def to_yaml(self) -> str:
        """Convert to YAML string."""
        return yaml.dump(self.model_dump(exclude_unset=True), default_flow_style=False)
    
    @classmethod
    def from_yaml(cls, yaml_content: str) -> "CapsuleDefinition":
        """Create from YAML string."""
        data = yaml.safe_load(yaml_content)
        return cls(**data)
    
    def calculate_checksum(self) -> str:
        """Calculate SHA-256 checksum of the definition."""
        # Convert to dict first, then to JSON with sorted keys
        data = self.model_dump(exclude_unset=True)
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()


class CapsuleSignature(BaseModel):
    """Capsule digital signature model."""
    
    algorithm: str = Field(default="Ed25519", description="Signature algorithm")
    public_key: str = Field(..., description="Base64 encoded public key")
    signature: str = Field(..., description="Base64 encoded signature")
    signed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Signature timestamp")
    signer: str = Field(..., description="Signer identifier")
    
    @classmethod
    def create_signature(
        cls, 
        capsule_definition: CapsuleDefinition, 
        private_key: ed25519.Ed25519PrivateKey,
        signer: str
    ) -> "CapsuleSignature":
        """Create a digital signature for a capsule definition."""
        # Create timestamp for signature
        signed_at = datetime.now(timezone.utc)
        
        # Create content to sign (checksum + metadata)
        content_to_sign = {
            "checksum": capsule_definition.calculate_checksum(),
            "name": capsule_definition.name,
            "version": capsule_definition.version,
            "timestamp": signed_at.isoformat()
        }
        
        message = json.dumps(content_to_sign, sort_keys=True).encode()
        signature = private_key.sign(message)
        
        public_key = private_key.public_key()
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        import base64
        return cls(
            public_key=base64.b64encode(public_key_bytes).decode(),
            signature=base64.b64encode(signature).decode(),
            signer=signer,
            signed_at=signed_at
        )
    
    def verify_signature(self, capsule_definition: CapsuleDefinition) -> bool:
        """Verify the signature against a capsule definition."""
        try:
            import base64
            
            # Reconstruct the signed content using the same timestamp as when signed
            content_to_verify = {
                "checksum": capsule_definition.calculate_checksum(),
                "name": capsule_definition.name,
                "version": capsule_definition.version,
                "timestamp": self.signed_at.isoformat()
            }
            
            message = json.dumps(content_to_verify, sort_keys=True).encode()
            
            # Decode public key and signature
            public_key_bytes = base64.b64decode(self.public_key)
            signature_bytes = base64.b64decode(self.signature)
            
            # Create public key object
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            # Verify signature
            public_key.verify(signature_bytes, message)
            return True
            
        except Exception as e:
            # For debugging - in production this should just return False
            print(f"Signature verification failed: {e}")
            return False


class Capsule(BaseModel):
    """Complete Capsule model with metadata."""
    
    capsule_id: UUID = Field(default_factory=uuid4, description="Unique capsule ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    name: str = Field(..., description="Capsule name")
    version: str = Field(..., description="Capsule version")
    
    # Definition and integrity
    definition: CapsuleDefinition = Field(..., description="Capsule definition")
    checksum: str = Field(..., description="SHA-256 checksum")
    signature: Optional[CapsuleSignature] = Field(None, description="Digital signature")
    
    # Metadata
    created_by: UUID = Field(..., description="Creator user ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    active: bool = Field(default=True, description="Active status")
    
    # Validation status
    validation_status: str = Field(default="pending", description="Validation status")
    validation_errors: List[str] = Field(default_factory=list, description="Validation errors")
    
    @field_validator('checksum')
    @classmethod
    def validate_checksum(cls, v, info):
        """Validate that checksum matches definition."""
        if info.data and 'definition' in info.data:
            expected_checksum = info.data['definition'].calculate_checksum()
            if v != expected_checksum:
                raise ValueError(f'Checksum mismatch: expected {expected_checksum}, got {v}')
        return v
    
    @classmethod
    def create(
        cls,
        tenant_id: UUID,
        definition: CapsuleDefinition,
        created_by: UUID,
        signature: Optional[CapsuleSignature] = None
    ) -> "Capsule":
        """Create a new Capsule instance."""
        checksum = definition.calculate_checksum()
        
        return cls(
            tenant_id=tenant_id,
            name=definition.name,
            version=definition.version,
            definition=definition,
            checksum=checksum,
            signature=signature,
            created_by=created_by
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "capsule_id": self.capsule_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "version": self.version,
            "definition": self.definition.model_dump(),
            "checksum": self.checksum,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "active": self.active
        }
    
    @classmethod
    def from_db_record(cls, record: Dict[str, Any]) -> "Capsule":
        """Create from database record."""
        definition = CapsuleDefinition(**record["definition"])
        
        return cls(
            capsule_id=record["capsule_id"],
            tenant_id=record["tenant_id"],
            name=record["name"],
            version=record["version"],
            definition=definition,
            checksum=record["checksum"],
            created_by=record["created_by"],
            created_at=record["created_at"],
            active=record["active"]
        )


class CapsuleCreateRequest(BaseModel):
    """Request model for creating a new Capsule."""
    
    yaml_content: str = Field(..., description="YAML content of the capsule")
    sign_capsule: bool = Field(default=False, description="Whether to sign the capsule")
    
    def to_capsule_definition(self) -> CapsuleDefinition:
        """Convert YAML content to CapsuleDefinition."""
        return CapsuleDefinition.from_yaml(self.yaml_content)


class CapsuleUpdateRequest(BaseModel):
    """Request model for updating a Capsule."""
    
    yaml_content: str = Field(..., description="Updated YAML content")
    sign_capsule: bool = Field(default=False, description="Whether to sign the capsule")
    
    def to_capsule_definition(self) -> CapsuleDefinition:
        """Convert YAML content to CapsuleDefinition."""
        return CapsuleDefinition.from_yaml(self.yaml_content)


class CapsuleVersionRequest(BaseModel):
    """Request model for publishing a new Capsule version."""
    
    yaml_content: str = Field(..., description="YAML content of the new version")
    sign_capsule: bool = Field(default=False, description="Whether to sign the capsule")
    
    def to_capsule_definition(self) -> CapsuleDefinition:
        """Convert YAML content to CapsuleDefinition."""
        return CapsuleDefinition.from_yaml(self.yaml_content)


class CapsuleListResponse(BaseModel):
    """Response model for listing Capsules."""
    
    capsules: List[Capsule] = Field(..., description="List of capsules")
    total: int = Field(..., description="Total number of capsules")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")


class CapsuleValidationResult(BaseModel):
    """Capsule validation result."""
    
    valid: bool = Field(..., description="Whether the capsule is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")


class DependencySpec(BaseModel):
    """Dependency specification with version constraints."""
    
    name: str = Field(..., description="Dependency name")
    version_constraint: str = Field(..., description="Version constraint (e.g., >=1.0.0, ~1.2.0)")
    optional: bool = Field(default=False, description="Whether dependency is optional")
    
    @classmethod
    def parse(cls, dep_string: str) -> "DependencySpec":
        """Parse dependency string like 'name@>=1.0.0' or 'name@~1.2.0?optional'."""
        parts = dep_string.split("@")
        if len(parts) != 2:
            raise ValueError(f"Invalid dependency format: {dep_string}")
        
        name = parts[0]
        version_part = parts[1]
        
        optional = version_part.endswith("?optional")
        if optional:
            version_part = version_part[:-9]  # Remove "?optional"
        
        return cls(name=name, version_constraint=version_part, optional=optional)


class ResolvedDependency(BaseModel):
    """Resolved dependency with specific version."""
    
    name: str = Field(..., description="Dependency name")
    version: str = Field(..., description="Resolved version")
    capsule_id: UUID = Field(..., description="Resolved capsule ID")
    optional: bool = Field(default=False, description="Whether dependency is optional")


class DependencyResolutionResult(BaseModel):
    """Result of dependency resolution."""
    
    resolved: List[ResolvedDependency] = Field(default_factory=list, description="Successfully resolved dependencies")
    unresolved: List[str] = Field(default_factory=list, description="Unresolved dependencies")
    conflicts: List[str] = Field(default_factory=list, description="Version conflicts")
    
    @property
    def success(self) -> bool:
        """Whether resolution was successful."""
        return len(self.unresolved) == 0 and len(self.conflicts) == 0


class CapsuleChange(BaseModel):
    """Represents a change in a Capsule."""
    
    field_path: str = Field(..., description="Path to changed field (e.g., 'automation.steps[0].name')")
    change_type: str = Field(..., description="Type of change: added, removed, modified")
    old_value: Optional[Any] = Field(None, description="Previous value")
    new_value: Optional[Any] = Field(None, description="New value")


class CapsuleDiff(BaseModel):
    """Diff between two Capsule versions."""
    
    from_version: str = Field(..., description="Source version")
    to_version: str = Field(..., description="Target version")
    changes: List[CapsuleChange] = Field(default_factory=list, description="List of changes")
    
    @property
    def has_changes(self) -> bool:
        """Whether there are any changes."""
        return len(self.changes) > 0


class ApprovalStatus(BaseModel):
    """Approval status for a Capsule."""
    
    status: str = Field(..., description="Approval status: pending, approved, rejected")
    approver_id: Optional[UUID] = Field(None, description="ID of approver")
    approved_at: Optional[datetime] = Field(None, description="Approval timestamp")
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection")
    approval_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional approval metadata")


class ComposedCapsule(BaseModel):
    """Result of composing multiple Capsules."""
    
    base_capsule: Capsule = Field(..., description="Base capsule")
    composed_definition: CapsuleDefinition = Field(..., description="Final composed definition")
    composition_chain: List[str] = Field(default_factory=list, description="Chain of composition")
    inheritance_chain: List[str] = Field(default_factory=list, description="Chain of inheritance")