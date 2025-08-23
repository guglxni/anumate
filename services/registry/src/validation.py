"""Capsule validation and schema enforcement."""

import json
from typing import Any, Dict, List, Optional

import jsonschema
import yaml
from pydantic import ValidationError

from .models import CapsuleDefinition, CapsuleValidationResult


class CapsuleValidator:
    """Validates Capsule definitions against schema and business rules."""
    
    def __init__(self):
        """Initialize validator with schema."""
        self.schema = self._load_capsule_schema()
    
    def _load_capsule_schema(self) -> Dict[str, Any]:
        """Load the Capsule JSON schema."""
        # Define the Capsule schema
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["name", "version", "automation"],
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
                    "minLength": 1,
                    "maxLength": 100,
                    "description": "Capsule name (lowercase, alphanumeric, hyphens)"
                },
                "version": {
                    "type": "string",
                    "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-((?:0|[1-9]\\d*|\\d*[a-zA-Z-][0-9a-zA-Z-]*)))?(?:\\+([0-9a-zA-Z-]+(?:\\.[0-9a-zA-Z-]+)*))?$",
                    "description": "Semantic version"
                },
                "description": {
                    "type": "string",
                    "maxLength": 1000,
                    "description": "Capsule description"
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Capsule metadata"
                },
                "labels": {
                    "type": "object",
                    "patternProperties": {
                        "^[a-z0-9]([a-z0-9-]*[a-z0-9])?$": {
                            "type": "string",
                            "maxLength": 100
                        }
                    },
                    "additionalProperties": False,
                    "description": "Capsule labels"
                },
                "annotations": {
                    "type": "object",
                    "patternProperties": {
                        "^[a-z0-9]([a-z0-9-./]*[a-z0-9])?$": {
                            "type": "string",
                            "maxLength": 500
                        }
                    },
                    "additionalProperties": False,
                    "description": "Capsule annotations"
                },
                "dependencies": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": "^[a-z0-9]([a-z0-9-]*[a-z0-9])?@(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)$"
                    },
                    "uniqueItems": True,
                    "maxItems": 50,
                    "description": "Capsule dependencies (name@version)"
                },
                "automation": {
                    "type": "object",
                    "required": ["steps"],
                    "properties": {
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["name", "action"],
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "minLength": 1,
                                        "maxLength": 100
                                    },
                                    "action": {
                                        "type": "string",
                                        "minLength": 1,
                                        "maxLength": 100
                                    },
                                    "parameters": {
                                        "type": "object",
                                        "additionalProperties": True
                                    },
                                    "conditions": {
                                        "type": "object",
                                        "additionalProperties": True
                                    },
                                    "retry": {
                                        "type": "object",
                                        "properties": {
                                            "attempts": {
                                                "type": "integer",
                                                "minimum": 1,
                                                "maximum": 10
                                            },
                                            "delay": {
                                                "type": "integer",
                                                "minimum": 1,
                                                "maximum": 300
                                            }
                                        }
                                    }
                                }
                            },
                            "minItems": 1,
                            "maxItems": 100
                        },
                        "triggers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["type"],
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["manual", "schedule", "webhook", "event"]
                                    },
                                    "config": {
                                        "type": "object",
                                        "additionalProperties": True
                                    }
                                }
                            }
                        },
                        "variables": {
                            "type": "object",
                            "patternProperties": {
                                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": ["string", "number", "boolean", "array", "object"]
                                        },
                                        "default": True,
                                        "required": {
                                            "type": "boolean"
                                        },
                                        "description": {
                                            "type": "string"
                                        }
                                    }
                                }
                            },
                            "additionalProperties": False
                        }
                    },
                    "description": "Automation workflow definition"
                },
                "tools": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": "^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"
                    },
                    "uniqueItems": True,
                    "maxItems": 100,
                    "description": "Allowed tools"
                },
                "policies": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": "^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"
                    },
                    "uniqueItems": True,
                    "maxItems": 50,
                    "description": "Policy references"
                }
            },
            "additionalProperties": False
        }
    
    def validate_yaml_syntax(self, yaml_content: str) -> CapsuleValidationResult:
        """Validate YAML syntax."""
        errors = []
        warnings = []
        
        try:
            yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            errors.append(f"Invalid YAML syntax: {str(e)}")
        
        return CapsuleValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def validate_schema(self, definition_dict: Dict[str, Any]) -> CapsuleValidationResult:
        """Validate against JSON schema."""
        errors = []
        warnings = []
        
        try:
            jsonschema.validate(definition_dict, self.schema)
        except jsonschema.ValidationError as e:
            errors.append(f"Schema validation error: {e.message}")
        except jsonschema.SchemaError as e:
            errors.append(f"Schema error: {str(e)}")
        
        return CapsuleValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def validate_pydantic_model(self, definition_dict: Dict[str, Any]) -> CapsuleValidationResult:
        """Validate using Pydantic model."""
        errors = []
        warnings = []
        
        try:
            CapsuleDefinition(**definition_dict)
        except ValidationError as e:
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                errors.append(f"Field '{field}': {error['msg']}")
        
        return CapsuleValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def validate_business_rules(self, definition: CapsuleDefinition) -> CapsuleValidationResult:
        """Validate business rules and constraints."""
        errors = []
        warnings = []
        
        # Check for circular dependencies
        if self._has_circular_dependencies(definition.dependencies):
            errors.append("Circular dependency detected")
        
        # Validate automation steps
        step_names = [step.get("name", "") for step in definition.automation.get("steps", [])]
        if len(step_names) != len(set(step_names)):
            errors.append("Duplicate step names found")
        
        # Check tool allowlist
        if not definition.tools:
            warnings.append("No tools specified in allowlist - capsule may not be executable")
        
        # Validate step actions reference allowed tools
        for step in definition.automation.get("steps", []):
            action = step.get("action", "")
            if action and not any(tool in action for tool in definition.tools):
                warnings.append(f"Step '{step.get('name')}' uses action '{action}' not in tool allowlist")
        
        # Check for required metadata
        if not definition.description:
            warnings.append("No description provided")
        
        # Validate version constraints
        if definition.version.startswith("0."):
            warnings.append("Pre-release version (0.x.x) - consider using stable version")
        
        return CapsuleValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _has_circular_dependencies(self, dependencies: List[str]) -> bool:
        """Check for circular dependencies."""
        # Simplified check - in real implementation would need dependency graph
        # For now, just check for obvious self-references
        dep_names = [dep.split("@")[0] for dep in dependencies]
        return len(dep_names) != len(set(dep_names))
    
    def validate_complete(self, yaml_content: str) -> CapsuleValidationResult:
        """Perform complete validation of a Capsule YAML."""
        all_errors = []
        all_warnings = []
        
        # 1. Validate YAML syntax
        yaml_result = self.validate_yaml_syntax(yaml_content)
        all_errors.extend(yaml_result.errors)
        all_warnings.extend(yaml_result.warnings)
        
        if not yaml_result.valid:
            return CapsuleValidationResult(
                valid=False,
                errors=all_errors,
                warnings=all_warnings
            )
        
        # 2. Parse YAML
        try:
            definition_dict = yaml.safe_load(yaml_content)
        except Exception as e:
            all_errors.append(f"Failed to parse YAML: {str(e)}")
            return CapsuleValidationResult(
                valid=False,
                errors=all_errors,
                warnings=all_warnings
            )
        
        # 3. Validate JSON schema
        schema_result = self.validate_schema(definition_dict)
        all_errors.extend(schema_result.errors)
        all_warnings.extend(schema_result.warnings)
        
        # 4. Validate Pydantic model
        pydantic_result = self.validate_pydantic_model(definition_dict)
        all_errors.extend(pydantic_result.errors)
        all_warnings.extend(pydantic_result.warnings)
        
        # 5. Validate business rules (only if basic validation passes)
        if len(all_errors) == 0:
            try:
                definition = CapsuleDefinition(**definition_dict)
                business_result = self.validate_business_rules(definition)
                all_errors.extend(business_result.errors)
                all_warnings.extend(business_result.warnings)
            except Exception as e:
                all_errors.append(f"Business rule validation failed: {str(e)}")
        
        return CapsuleValidationResult(
            valid=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings
        )


# Global validator instance
capsule_validator = CapsuleValidator()