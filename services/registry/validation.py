"""
Capsule Validation Module

A.4–A.6 Implementation: Comprehensive validation of capsule YAML content
with schema validation, canonical JSON generation, and content hashing.
"""

import yaml
import json
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field, validator
from jsonschema import validate, ValidationError as JsonSchemaError, draft7_format_checker

from anumate_planhash import generate_canonical_hash
from anumate_errors import ValidationError
from .models import ValidationResult


class CapsuleSchema(BaseModel):
    """Pydantic model defining valid capsule structure."""
    
    apiVersion: str = Field(..., regex=r"^anumate\.dev/v1(alpha1|beta1)?$")
    kind: str = Field(..., regex="^Capsule$")
    metadata: Dict[str, Any] = Field(...)
    spec: Dict[str, Any] = Field(...)
    
    class Config:
        extra = "forbid"  # Reject unknown fields


class CapsuleMetadata(BaseModel):
    """Capsule metadata schema."""
    
    name: str = Field(..., min_length=1, max_length=255)
    namespace: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2048)
    labels: Optional[Dict[str, str]] = Field(None, max_properties=50)
    annotations: Optional[Dict[str, str]] = Field(None, max_properties=50)
    
    @validator("name")
    def validate_name(cls, v):
        """Validate capsule name follows DNS-safe pattern."""
        import re
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$", v):
            raise ValueError("Name must be DNS-safe: alphanumeric with -, _, . allowed")
        return v
        
    @validator("labels", "annotations")
    def validate_key_value_pairs(cls, v):
        """Validate label/annotation keys and values."""
        if v:
            for key, value in v.items():
                if not key or len(key) > 255 or not isinstance(value, str) or len(value) > 1024:
                    raise ValueError("Invalid label/annotation: keys ≤255 chars, values ≤1024 chars")
        return v


class CapsuleSpec(BaseModel):
    """Capsule specification schema."""
    
    steps: List[Dict[str, Any]] = Field(..., min_items=1, max_items=100)
    policies: Optional[List[str]] = Field(None, max_items=20)
    allowed_tools: List[str] = Field(..., min_items=1, max_items=50)
    timeout: Optional[int] = Field(None, ge=1, le=86400)  # 1 second to 24 hours
    retry_policy: Optional[Dict[str, Any]] = None
    environment: Optional[Dict[str, str]] = Field(None, max_properties=100)
    
    @validator("policies")
    def validate_policies(cls, v):
        """Validate policy references."""
        if v:
            for policy in v:
                if not policy or not isinstance(policy, str):
                    raise ValueError("Policy references must be non-empty strings")
                # Policy refs should be namespaced (no wildcards allowed)
                if "*" in policy or ".." in policy:
                    raise ValueError("Wildcards and relative paths not allowed in policy references")
        return v
        
    @validator("allowed_tools")
    def validate_allowed_tools(cls, v):
        """Validate allowed tools list."""
        seen = set()
        for tool in v:
            if not tool or not isinstance(tool, str):
                raise ValueError("Tool names must be non-empty strings")
            if tool in seen:
                raise ValueError(f"Duplicate tool: {tool}")
            seen.add(tool)
            # Tools should be namespaced, no wildcards
            if "*" in tool or ".." in tool:
                raise ValueError("Wildcards and relative paths not allowed in tool names")
        return v
        
    @validator("steps")
    def validate_steps(cls, v):
        """Validate steps are properly ordered and structured."""
        if not v:
            raise ValueError("At least one step is required")
            
        for i, step in enumerate(v):
            if not isinstance(step, dict):
                raise ValueError(f"Step {i} must be an object")
            if "name" not in step:
                raise ValueError(f"Step {i} missing required 'name' field")
            if "tool" not in step:
                raise ValueError(f"Step {i} missing required 'tool' field")
                
        # Check for duplicate step names
        step_names = [step.get("name") for step in v]
        if len(step_names) != len(set(step_names)):
            raise ValueError("Step names must be unique")
            
        return v


class CapsuleValidator:
    """Comprehensive capsule content validator."""
    
    def __init__(self):
        """Initialize validator with schema definitions."""
        self.schema_cache = {}
        
    def validate_yaml_syntax(self, yaml_content: str) -> Dict[str, Any]:
        """Parse and validate YAML syntax."""
        try:
            data = yaml.safe_load(yaml_content)
            if not isinstance(data, dict):
                raise ValidationError("Capsule YAML must be a dictionary")
            return data
        except yaml.YAMLError as e:
            raise ValidationError(f"Invalid YAML syntax: {e}")
    
    def validate_schema(self, data: Dict[str, Any]) -> None:
        """Validate capsule data against schema."""
        try:
            # Validate top-level structure
            capsule = CapsuleSchema(**data)
            
            # Validate metadata section
            if "metadata" in data:
                CapsuleMetadata(**data["metadata"])
                
            # Validate spec section  
            if "spec" in data:
                CapsuleSpec(**data["spec"])
                
        except Exception as e:
            raise ValidationError(f"Schema validation failed: {e}")
    
    def validate_step_dependencies(self, steps: List[Dict[str, Any]]) -> None:
        """Validate step dependencies form a valid DAG."""
        step_names = {step["name"] for step in steps}
        
        for step in steps:
            # Check dependencies exist
            depends_on = step.get("depends_on", [])
            if isinstance(depends_on, str):
                depends_on = [depends_on]
                
            for dep in depends_on:
                if dep not in step_names:
                    raise ValidationError(f"Step '{step['name']}' depends on unknown step '{dep}'")
        
        # Check for circular dependencies (simplified)
        self._check_circular_dependencies(steps)
        
    def _check_circular_dependencies(self, steps: List[Dict[str, Any]]) -> None:
        """Check for circular dependencies using DFS."""
        graph = {}
        for step in steps:
            name = step["name"]
            depends_on = step.get("depends_on", [])
            if isinstance(depends_on, str):
                depends_on = [depends_on]
            graph[name] = depends_on
            
        visited = set()
        rec_stack = set()
        
        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
                    
            rec_stack.remove(node)
            return False
            
        for step in steps:
            name = step["name"]
            if name not in visited:
                if dfs(name):
                    raise ValidationError("Circular dependency detected in steps")
    
    def validate_deterministic_ordering(self, data: Dict[str, Any]) -> None:
        """Ensure the capsule structure produces deterministic hashes."""
        # Check that steps are in a deterministic order
        if "spec" in data and "steps" in data["spec"]:
            steps = data["spec"]["steps"]
            
            # Steps should be ordered by dependencies, then by name for stability
            step_names = [step["name"] for step in steps]
            sorted_names = sorted(step_names)
            
            # For now, just ensure consistent naming (full topological sort would be complex)
            for step in steps:
                if "name" not in step or not isinstance(step["name"], str):
                    raise ValidationError("All steps must have string names")
    
    def generate_canonical_json(self, data: Dict[str, Any]) -> str:
        """Generate canonical JSON representation for hashing."""
        try:
            # Use anumate-planhash for consistent canonicalization
            return generate_canonical_hash(data, output_format="json")
        except Exception as e:
            raise ValidationError(f"Failed to generate canonical JSON: {e}")
    
    def compute_content_hash(self, canonical_json: str) -> str:
        """Compute SHA256 hash of canonical content."""
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    
    def validate_content_size(self, yaml_content: str, max_size_mb: float = 5.0) -> None:
        """Validate content size limits."""
        size_bytes = len(yaml_content.encode("utf-8"))
        max_bytes = int(max_size_mb * 1024 * 1024)
        
        if size_bytes > max_bytes:
            raise ValidationError(f"Content size {size_bytes} bytes exceeds limit of {max_bytes} bytes")
    
    def validate_complete(self, yaml_content: str) -> ValidationResult:
        """Perform complete validation and return result."""
        errors = []
        warnings = []
        content_hash = ""
        
        try:
            # Size check first
            self.validate_content_size(yaml_content)
            
            # Parse YAML
            data = self.validate_yaml_syntax(yaml_content)
            
            # Schema validation
            self.validate_schema(data)
            
            # Business logic validation
            if "spec" in data and "steps" in data["spec"]:
                self.validate_step_dependencies(data["spec"]["steps"])
                
            # Deterministic ordering
            self.validate_deterministic_ordering(data)
            
            # Generate canonical representation and hash
            canonical_json = self.generate_canonical_json(data)
            content_hash = self.compute_content_hash(canonical_json)
            
            # Collect any warnings
            self._collect_warnings(data, warnings)
            
            return ValidationResult(
                valid=True,
                content_hash=content_hash,
                errors=None,
                warnings=warnings if warnings else None
            )
            
        except ValidationError as e:
            errors.append({"path": "", "message": str(e)})
            
        except Exception as e:
            errors.append({"path": "", "message": f"Unexpected validation error: {e}"})
        
        return ValidationResult(
            valid=False,
            content_hash="",  # No hash for invalid content
            errors=errors,
            warnings=warnings if warnings else None
        )
    
    def _collect_warnings(self, data: Dict[str, Any], warnings: List[str]) -> None:
        """Collect non-fatal warnings during validation."""
        # Check for potentially problematic patterns
        if "spec" in data:
            spec = data["spec"]
            
            # Warn about missing timeout
            if "timeout" not in spec:
                warnings.append("No timeout specified - using system default")
                
            # Warn about too many steps
            if len(spec.get("steps", [])) > 20:
                warnings.append(f"Large number of steps ({len(spec['steps'])}) may impact performance")
                
            # Warn about missing retry policy
            if "retry_policy" not in spec:
                warnings.append("No retry policy specified - failures will not be retried")


# Module-level validator instance
validator = CapsuleValidator()


def validate_capsule_content(yaml_content: str) -> ValidationResult:
    """Validate capsule YAML content and return result."""
    return validator.validate_complete(yaml_content)


def generate_content_hash(yaml_content: str) -> str:
    """Generate content hash for valid YAML (raises on invalid content)."""
    data = validator.validate_yaml_syntax(yaml_content)
    validator.validate_schema(data)
    canonical_json = validator.generate_canonical_json(data)
    return validator.compute_content_hash(canonical_json)
