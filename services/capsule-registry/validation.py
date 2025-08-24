"""Capsule YAML validation and canonical form generation."""

import json
import re
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass

import yaml
from anumate_planhash import generate_canonical_hash
from anumate_errors import ValidationError, ErrorCode


@dataclass
class ValidationIssue:
    """Represents a validation error or warning."""
    code: str
    message: str
    path: str
    severity: str = "error"  # "error" or "warning"


class CapsuleValidator:
    """Validates Capsule YAML content and generates canonical form."""
    
    # Allowed tool namespace pattern
    TOOL_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]*(\.[a-zA-Z][a-zA-Z0-9_-]*)*$')
    
    # Reserved tool namespaces
    RESERVED_NAMESPACES = {
        'system', 'anumate', 'internal', 'admin'
    }
    
    def __init__(self):
        self.issues: List[ValidationIssue] = []
    
    def validate(self, yaml_content: str) -> Tuple[bool, List[ValidationIssue], Optional[str]]:
        """
        Validate Capsule YAML and return canonical hash if valid.
        
        Returns:
            Tuple of (is_valid, issues_list, content_hash)
        """
        self.issues = []
        
        try:
            # Parse YAML
            capsule_data = self._parse_yaml(yaml_content)
            if not capsule_data:
                return False, self.issues, None
            
            # Validate structure
            self._validate_structure(capsule_data)
            
            # Validate metadata
            self._validate_metadata(capsule_data)
            
            # Validate steps
            self._validate_steps(capsule_data)
            
            # Validate allowed tools
            self._validate_allowed_tools(capsule_data)
            
            # Validate policy references
            self._validate_policy_refs(capsule_data)
            
            # Validate inputs
            self._validate_inputs(capsule_data)
            
            # Check for warnings
            self._check_warnings(capsule_data)
            
            # Generate content hash if no errors
            has_errors = any(issue.severity == "error" for issue in self.issues)
            if not has_errors:
                content_hash = self._generate_content_hash(capsule_data)
                return True, self.issues, content_hash
            else:
                return False, self.issues, None
                
        except Exception as e:
            self.issues.append(ValidationIssue(
                code="PARSE_ERROR",
                message=f"Failed to validate Capsule: {str(e)}",
                path="$"
            ))
            return False, self.issues, None
    
    def _parse_yaml(self, yaml_content: str) -> Optional[Dict[str, Any]]:
        """Parse YAML content safely."""
        try:
            # Use safe loader to prevent code execution
            data = yaml.safe_load(yaml_content)
            
            if not isinstance(data, dict):
                self.issues.append(ValidationIssue(
                    code="INVALID_ROOT",
                    message="Capsule must be a YAML object",
                    path="$"
                ))
                return None
                
            return data
            
        except yaml.YAMLError as e:
            self.issues.append(ValidationIssue(
                code="YAML_PARSE_ERROR",
                message=f"Invalid YAML syntax: {str(e)}",
                path="$"
            ))
            return None
    
    def _validate_structure(self, data: Dict[str, Any]):
        """Validate basic Capsule structure."""
        required_fields = ['name', 'version', 'steps']
        
        for field in required_fields:
            if field not in data:
                self.issues.append(ValidationIssue(
                    code="MISSING_REQUIRED_FIELD",
                    message=f"Required field '{field}' is missing",
                    path=f"$.{field}"
                ))
    
    def _validate_metadata(self, data: Dict[str, Any]):
        """Validate Capsule metadata fields."""
        # Name validation
        if 'name' in data:
            name = data['name']
            if not isinstance(name, str) or not name.strip():
                self.issues.append(ValidationIssue(
                    code="INVALID_NAME",
                    message="Capsule name must be a non-empty string",
                    path="$.name"
                ))
            elif not re.match(r'^[a-zA-Z0-9_-]+$', name):
                self.issues.append(ValidationIssue(
                    code="INVALID_NAME_FORMAT",
                    message="Capsule name must contain only alphanumeric characters, underscores, and hyphens",
                    path="$.name"
                ))
        
        # Version validation
        if 'version' in data:
            version = data['version']
            if not isinstance(version, str) or not version.strip():
                self.issues.append(ValidationIssue(
                    code="INVALID_VERSION",
                    message="Capsule version must be a non-empty string",
                    path="$.version"
                ))
            elif not re.match(r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$', version):
                self.issues.append(ValidationIssue(
                    code="INVALID_VERSION_FORMAT",
                    message="Version must follow semver format (e.g., '1.0.0' or '1.0.0-alpha')",
                    path="$.version"
                ))
        
        # Description validation (optional)
        if 'description' in data:
            desc = data['description']
            if not isinstance(desc, str):
                self.issues.append(ValidationIssue(
                    code="INVALID_DESCRIPTION",
                    message="Description must be a string",
                    path="$.description"
                ))
            elif len(desc) > 1024:
                self.issues.append(ValidationIssue(
                    code="DESCRIPTION_TOO_LONG",
                    message="Description must be 1024 characters or less",
                    path="$.description"
                ))
        
        # Tags validation (optional)
        if 'tags' in data:
            tags = data['tags']
            if not isinstance(tags, list):
                self.issues.append(ValidationIssue(
                    code="INVALID_TAGS",
                    message="Tags must be a list of strings",
                    path="$.tags"
                ))
            else:
                for i, tag in enumerate(tags):
                    if not isinstance(tag, str) or not tag.strip():
                        self.issues.append(ValidationIssue(
                            code="INVALID_TAG",
                            message=f"Tag at index {i} must be a non-empty string",
                            path=f"$.tags[{i}]"
                        ))
                    elif len(tag) > 50:
                        self.issues.append(ValidationIssue(
                            code="TAG_TOO_LONG",
                            message=f"Tag at index {i} must be 50 characters or less",
                            path=f"$.tags[{i}]"
                        ))
    
    def _validate_steps(self, data: Dict[str, Any]):
        """Validate Capsule steps."""
        if 'steps' not in data:
            return
            
        steps = data['steps']
        if not isinstance(steps, list):
            self.issues.append(ValidationIssue(
                code="INVALID_STEPS",
                message="Steps must be a list",
                path="$.steps"
            ))
            return
        
        if len(steps) == 0:
            self.issues.append(ValidationIssue(
                code="EMPTY_STEPS",
                message="At least one step is required",
                path="$.steps"
            ))
            return
        
        step_names = set()
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                self.issues.append(ValidationIssue(
                    code="INVALID_STEP",
                    message=f"Step at index {i} must be an object",
                    path=f"$.steps[{i}]"
                ))
                continue
            
            # Required fields
            if 'name' not in step:
                self.issues.append(ValidationIssue(
                    code="MISSING_STEP_NAME",
                    message=f"Step at index {i} is missing required 'name' field",
                    path=f"$.steps[{i}].name"
                ))
                continue
            
            if 'type' not in step:
                self.issues.append(ValidationIssue(
                    code="MISSING_STEP_TYPE",
                    message=f"Step at index {i} is missing required 'type' field",
                    path=f"$.steps[{i}].type"
                ))
                continue
            
            # Name uniqueness
            step_name = step['name']
            if step_name in step_names:
                self.issues.append(ValidationIssue(
                    code="DUPLICATE_STEP_NAME",
                    message=f"Step name '{step_name}' is not unique",
                    path=f"$.steps[{i}].name"
                ))
            else:
                step_names.add(step_name)
            
            # Name format
            if not isinstance(step_name, str) or not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', step_name):
                self.issues.append(ValidationIssue(
                    code="INVALID_STEP_NAME",
                    message=f"Step name '{step_name}' must start with a letter and contain only alphanumeric characters, underscores, and hyphens",
                    path=f"$.steps[{i}].name"
                ))
            
            # Type validation
            step_type = step['type']
            if not isinstance(step_type, str) or not step_type.strip():
                self.issues.append(ValidationIssue(
                    code="INVALID_STEP_TYPE",
                    message=f"Step type must be a non-empty string",
                    path=f"$.steps[{i}].type"
                ))
            
            # Config validation (optional)
            if 'config' in step and not isinstance(step['config'], dict):
                self.issues.append(ValidationIssue(
                    code="INVALID_STEP_CONFIG",
                    message=f"Step config must be an object",
                    path=f"$.steps[{i}].config"
                ))
    
    def _validate_allowed_tools(self, data: Dict[str, Any]):
        """Validate allowed_tools field."""
        if 'allowed_tools' not in data:
            # This is optional, but if steps are present, we should warn
            if 'steps' in data and data['steps']:
                self.issues.append(ValidationIssue(
                    code="MISSING_ALLOWED_TOOLS",
                    message="Consider specifying 'allowed_tools' for security",
                    path="$.allowed_tools",
                    severity="warning"
                ))
            return
        
        allowed_tools = data['allowed_tools']
        if not isinstance(allowed_tools, list):
            self.issues.append(ValidationIssue(
                code="INVALID_ALLOWED_TOOLS",
                message="allowed_tools must be a list of strings",
                path="$.allowed_tools"
            ))
            return
        
        for i, tool in enumerate(allowed_tools):
            if not isinstance(tool, str) or not tool.strip():
                self.issues.append(ValidationIssue(
                    code="INVALID_TOOL",
                    message=f"Tool at index {i} must be a non-empty string",
                    path=f"$.allowed_tools[{i}]"
                ))
                continue
            
            # Check format
            if not self.TOOL_PATTERN.match(tool):
                self.issues.append(ValidationIssue(
                    code="INVALID_TOOL_FORMAT",
                    message=f"Tool '{tool}' must follow namespace format (e.g., 'http.request')",
                    path=f"$.allowed_tools[{i}]"
                ))
                continue
            
            # Check for wildcards (not allowed)
            if '*' in tool:
                self.issues.append(ValidationIssue(
                    code="WILDCARD_NOT_ALLOWED",
                    message=f"Wildcards are not allowed in tool names: '{tool}'",
                    path=f"$.allowed_tools[{i}]"
                ))
                continue
            
            # Check for reserved namespaces
            namespace = tool.split('.')[0]
            if namespace in self.RESERVED_NAMESPACES:
                self.issues.append(ValidationIssue(
                    code="RESERVED_NAMESPACE",
                    message=f"Tool '{tool}' uses reserved namespace '{namespace}'",
                    path=f"$.allowed_tools[{i}]"
                ))
    
    def _validate_policy_refs(self, data: Dict[str, Any]):
        """Validate policy references."""
        if 'policies' not in data:
            return
        
        policies = data['policies']
        if not isinstance(policies, list):
            self.issues.append(ValidationIssue(
                code="INVALID_POLICIES",
                message="Policies must be a list of policy references",
                path="$.policies"
            ))
            return
        
        for i, policy_ref in enumerate(policies):
            if not isinstance(policy_ref, str) or not policy_ref.strip():
                self.issues.append(ValidationIssue(
                    code="INVALID_POLICY_REF",
                    message=f"Policy reference at index {i} must be a non-empty string",
                    path=f"$.policies[{i}]"
                ))
                continue
            
            # Basic format check (could be enhanced to validate actual policy existence)
            if not re.match(r'^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)*$', policy_ref):
                self.issues.append(ValidationIssue(
                    code="INVALID_POLICY_REF_FORMAT",
                    message=f"Policy reference '{policy_ref}' must follow namespace format",
                    path=f"$.policies[{i}]"
                ))
    
    def _validate_inputs(self, data: Dict[str, Any]):
        """Validate inputs schema."""
        if 'inputs' not in data:
            return
        
        inputs = data['inputs']
        if not isinstance(inputs, dict):
            self.issues.append(ValidationIssue(
                code="INVALID_INPUTS",
                message="Inputs must be an object",
                path="$.inputs"
            ))
            return
        
        for input_name, input_spec in inputs.items():
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', input_name):
                self.issues.append(ValidationIssue(
                    code="INVALID_INPUT_NAME",
                    message=f"Input name '{input_name}' must start with a letter and contain only alphanumeric characters and underscores",
                    path=f"$.inputs.{input_name}"
                ))
            
            if not isinstance(input_spec, dict):
                self.issues.append(ValidationIssue(
                    code="INVALID_INPUT_SPEC",
                    message=f"Input spec for '{input_name}' must be an object",
                    path=f"$.inputs.{input_name}"
                ))
                continue
            
            # Type is required
            if 'type' not in input_spec:
                self.issues.append(ValidationIssue(
                    code="MISSING_INPUT_TYPE",
                    message=f"Input '{input_name}' is missing required 'type' field",
                    path=f"$.inputs.{input_name}.type"
                ))
            else:
                valid_types = {'string', 'number', 'boolean', 'array', 'object'}
                if input_spec['type'] not in valid_types:
                    self.issues.append(ValidationIssue(
                        code="INVALID_INPUT_TYPE",
                        message=f"Input '{input_name}' has invalid type '{input_spec['type']}'. Must be one of: {valid_types}",
                        path=f"$.inputs.{input_name}.type"
                    ))
    
    def _check_warnings(self, data: Dict[str, Any]):
        """Add warnings for best practices."""
        # Check for description
        if 'description' not in data or not data['description'].strip():
            self.issues.append(ValidationIssue(
                code="MISSING_DESCRIPTION",
                message="Consider adding a description for better documentation",
                path="$.description",
                severity="warning"
            ))
        
        # Check for tags
        if 'tags' not in data or not data['tags']:
            self.issues.append(ValidationIssue(
                code="MISSING_TAGS",
                message="Consider adding tags for better organization",
                path="$.tags",
                severity="warning"
            ))
        
        # Check step documentation
        if 'steps' in data:
            for i, step in enumerate(data['steps']):
                if isinstance(step, dict) and 'description' not in step:
                    self.issues.append(ValidationIssue(
                        code="MISSING_STEP_DESCRIPTION",
                        message=f"Consider adding a description to step '{step.get('name', i)}'",
                        path=f"$.steps[{i}].description",
                        severity="warning"
                    ))
    
    def _generate_content_hash(self, data: Dict[str, Any]) -> str:
        """Generate canonical content hash for the Capsule."""
        try:
            return generate_canonical_hash(data)
        except Exception as e:
            raise ValidationError(
                error_code=ErrorCode.VALIDATION_ERROR,
                message=f"Failed to generate content hash: {str(e)}"
            )
