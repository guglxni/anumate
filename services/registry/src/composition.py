"""Capsule composition and inheritance logic."""

import copy
from typing import Dict, List, Optional, Any
from uuid import UUID

import structlog

from .models import Capsule, CapsuleDefinition, ComposedCapsule
from .repository import CapsuleRepository

logger = structlog.get_logger(__name__)


class CapsuleComposer:
    """Handles Capsule composition and inheritance."""
    
    def __init__(self, repository: CapsuleRepository):
        """Initialize composer with repository."""
        self.repository = repository
    
    def merge_metadata(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Merge metadata dictionaries, with override taking precedence."""
        result = copy.deepcopy(base)
        result.update(override)
        return result
    
    def merge_lists(self, base: List[Any], additional: List[Any], unique: bool = True) -> List[Any]:
        """Merge two lists, optionally ensuring uniqueness."""
        result = copy.deepcopy(base)
        
        if unique:
            # Add items that aren't already in the base list
            for item in additional:
                if item not in result:
                    result.append(item)
        else:
            result.extend(additional)
        
        return result
    
    def merge_automation_workflows(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Merge automation workflow definitions."""
        result = copy.deepcopy(base)
        
        # Merge steps - override can add new steps or replace existing ones
        if "steps" in override:
            if "steps" not in result:
                result["steps"] = []
            
            # Create a map of existing steps by name for easy lookup
            existing_steps = {step.get("name", f"step_{i}"): i for i, step in enumerate(result["steps"])}
            
            for new_step in override["steps"]:
                step_name = new_step.get("name", f"step_{len(result['steps'])}")
                
                if step_name in existing_steps:
                    # Replace existing step
                    result["steps"][existing_steps[step_name]] = new_step
                else:
                    # Add new step
                    result["steps"].append(new_step)
        
        # Merge other workflow properties
        for key, value in override.items():
            if key != "steps":
                result[key] = value
        
        return result
    
    async def resolve_inheritance_chain(self, capsule: Capsule) -> List[Capsule]:
        """Resolve the full inheritance chain for a Capsule."""
        chain = []
        current = capsule
        visited = set()
        
        while current and current.definition.inherits_from:
            if current.capsule_id in visited:
                logger.warning("Circular inheritance detected", 
                              capsule_id=str(current.capsule_id))
                break
            
            visited.add(current.capsule_id)
            
            # Parse parent reference (name@version)
            parent_ref = current.definition.inherits_from
            if "@" in parent_ref:
                parent_name, parent_version = parent_ref.split("@", 1)
            else:
                # If no version specified, use latest
                parent_name = parent_ref
                parent_version = None
            
            # Find parent capsule
            if parent_version:
                parent = await self.repository.get_by_name_version(parent_name, parent_version)
            else:
                parent = await self.repository.get_latest_version(parent_name)
            
            if not parent:
                logger.warning("Parent capsule not found", 
                              parent_ref=parent_ref,
                              child_capsule=str(current.capsule_id))
                break
            
            chain.append(parent)
            current = parent
        
        return chain
    
    async def resolve_composition_chain(self, capsule: Capsule) -> List[Capsule]:
        """Resolve all Capsules that this Capsule is composed of."""
        composed_capsules = []
        
        for composed_ref in capsule.definition.composed_of:
            # Parse composed reference (name@version)
            if "@" in composed_ref:
                composed_name, composed_version = composed_ref.split("@", 1)
            else:
                # If no version specified, use latest
                composed_name = composed_ref
                composed_version = None
            
            # Find composed capsule
            if composed_version:
                composed = await self.repository.get_by_name_version(composed_name, composed_version)
            else:
                composed = await self.repository.get_latest_version(composed_name)
            
            if composed:
                composed_capsules.append(composed)
            else:
                logger.warning("Composed capsule not found", 
                              composed_ref=composed_ref,
                              capsule_id=str(capsule.capsule_id))
        
        return composed_capsules
    
    async def compose_capsule(self, capsule: Capsule) -> ComposedCapsule:
        """Compose a Capsule with its inheritance and composition chain."""
        logger.info("Composing capsule", 
                   capsule_id=str(capsule.capsule_id),
                   name=capsule.name,
                   version=capsule.version)
        
        # Start with the base capsule definition
        composed_definition = copy.deepcopy(capsule.definition)
        
        # Resolve inheritance chain (from root to current)
        inheritance_chain = await self.resolve_inheritance_chain(capsule)
        inheritance_chain.reverse()  # Start from root parent
        
        # Apply inheritance
        for parent in inheritance_chain:
            logger.debug("Applying inheritance", 
                        parent_name=parent.name,
                        parent_version=parent.version)
            
            # Merge metadata
            composed_definition.metadata = self.merge_metadata(
                parent.definition.metadata, 
                composed_definition.metadata
            )
            
            # Merge labels
            composed_definition.labels = self.merge_metadata(
                parent.definition.labels, 
                composed_definition.labels
            )
            
            # Merge annotations
            composed_definition.annotations = self.merge_metadata(
                parent.definition.annotations, 
                composed_definition.annotations
            )
            
            # Merge dependencies
            composed_definition.dependencies = self.merge_lists(
                parent.definition.dependencies,
                composed_definition.dependencies,
                unique=True
            )
            
            # Merge tools
            composed_definition.tools = self.merge_lists(
                parent.definition.tools,
                composed_definition.tools,
                unique=True
            )
            
            # Merge policies
            composed_definition.policies = self.merge_lists(
                parent.definition.policies,
                composed_definition.policies,
                unique=True
            )
            
            # Merge automation (child overrides parent)
            if parent.definition.automation:
                composed_definition.automation = self.merge_automation_workflows(
                    parent.definition.automation,
                    composed_definition.automation
                )
        
        # Resolve composition chain
        composition_chain = await self.resolve_composition_chain(capsule)
        
        # Apply composition
        for composed_capsule in composition_chain:
            logger.debug("Applying composition", 
                        composed_name=composed_capsule.name,
                        composed_version=composed_capsule.version)
            
            # For composition, we merge the composed capsule's definition into ours
            # Composed capsules contribute their automation steps and tools
            
            # Merge dependencies
            composed_definition.dependencies = self.merge_lists(
                composed_definition.dependencies,
                composed_capsule.definition.dependencies,
                unique=True
            )
            
            # Merge tools
            composed_definition.tools = self.merge_lists(
                composed_definition.tools,
                composed_capsule.definition.tools,
                unique=True
            )
            
            # Merge policies
            composed_definition.policies = self.merge_lists(
                composed_definition.policies,
                composed_capsule.definition.policies,
                unique=True
            )
            
            # Merge automation workflows
            if composed_capsule.definition.automation:
                composed_definition.automation = self.merge_automation_workflows(
                    composed_definition.automation,
                    composed_capsule.definition.automation
                )
        
        # Create inheritance and composition chain names
        inheritance_names = [f"{c.name}@{c.version}" for c in inheritance_chain]
        composition_names = [f"{c.name}@{c.version}" for c in composition_chain]
        
        logger.info("Capsule composition completed", 
                   capsule_id=str(capsule.capsule_id),
                   inheritance_chain_length=len(inheritance_names),
                   composition_chain_length=len(composition_names))
        
        return ComposedCapsule(
            base_capsule=capsule,
            composed_definition=composed_definition,
            inheritance_chain=inheritance_names,
            composition_chain=composition_names
        )
    
    async def validate_composition(self, capsule: Capsule) -> List[str]:
        """Validate that a Capsule's composition is valid."""
        errors = []
        
        # Check inheritance chain for cycles
        try:
            inheritance_chain = await self.resolve_inheritance_chain(capsule)
            capsule_names = {c.name for c in inheritance_chain}
            if capsule.name in capsule_names:
                errors.append(f"Circular inheritance detected involving {capsule.name}")
        except Exception as e:
            errors.append(f"Failed to resolve inheritance chain: {str(e)}")
        
        # Check composition references
        for composed_ref in capsule.definition.composed_of:
            try:
                if "@" in composed_ref:
                    composed_name, composed_version = composed_ref.split("@", 1)
                    composed = await self.repository.get_by_name_version(composed_name, composed_version)
                else:
                    composed_name = composed_ref
                    composed = await self.repository.get_latest_version(composed_name)
                
                if not composed:
                    errors.append(f"Composed capsule not found: {composed_ref}")
                elif composed.capsule_id == capsule.capsule_id:
                    errors.append(f"Capsule cannot compose itself: {composed_ref}")
                    
            except Exception as e:
                errors.append(f"Invalid composition reference '{composed_ref}': {str(e)}")
        
        # Check inheritance reference
        if capsule.definition.inherits_from:
            try:
                parent_ref = capsule.definition.inherits_from
                if "@" in parent_ref:
                    parent_name, parent_version = parent_ref.split("@", 1)
                    parent = await self.repository.get_by_name_version(parent_name, parent_version)
                else:
                    parent_name = parent_ref
                    parent = await self.repository.get_latest_version(parent_name)
                
                if not parent:
                    errors.append(f"Parent capsule not found: {parent_ref}")
                elif parent.capsule_id == capsule.capsule_id:
                    errors.append(f"Capsule cannot inherit from itself: {parent_ref}")
                    
            except Exception as e:
                errors.append(f"Invalid inheritance reference '{capsule.definition.inherits_from}': {str(e)}")
        
        return errors