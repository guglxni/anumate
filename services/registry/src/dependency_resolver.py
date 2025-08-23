"""Capsule dependency resolution logic."""

import re
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

import structlog
from packaging import version

from .models import (
    Capsule, 
    DependencySpec, 
    ResolvedDependency, 
    DependencyResolutionResult
)
from .repository import CapsuleRepository

logger = structlog.get_logger(__name__)


class DependencyResolver:
    """Resolves Capsule dependencies with version constraints."""
    
    def __init__(self, repository: CapsuleRepository):
        """Initialize resolver with repository."""
        self.repository = repository
    
    def parse_version_constraint(self, constraint: str) -> Tuple[str, str]:
        """Parse version constraint into operator and version."""
        # Support constraints like: >=1.0.0, ~1.2.0, ^1.0.0, =1.0.0, 1.0.0
        patterns = [
            (r'^>=(.+)$', '>='),
            (r'^>(.+)$', '>'),
            (r'^<=(.+)$', '<='),
            (r'^<(.+)$', '<'),
            (r'^~(.+)$', '~'),  # Compatible within patch version
            (r'^\^(.+)$', '^'),  # Compatible within minor version
            (r'^=(.+)$', '='),
            (r'^(.+)$', '=')  # Default to exact match
        ]
        
        for pattern, operator in patterns:
            match = re.match(pattern, constraint.strip())
            if match:
                return operator, match.group(1)
        
        raise ValueError(f"Invalid version constraint: {constraint}")
    
    def version_satisfies_constraint(self, version_str: str, constraint: str) -> bool:
        """Check if a version satisfies a constraint."""
        try:
            operator, constraint_version = self.parse_version_constraint(constraint)
            v = version.parse(version_str)
            cv = version.parse(constraint_version)
            
            if operator == '>=':
                return v >= cv
            elif operator == '>':
                return v > cv
            elif operator == '<=':
                return v <= cv
            elif operator == '<':
                return v < cv
            elif operator == '=':
                return v == cv
            elif operator == '~':
                # Compatible within patch version (same major.minor)
                return v.major == cv.major and v.minor == cv.minor and v >= cv
            elif operator == '^':
                # Compatible within minor version (same major)
                return v.major == cv.major and v >= cv
            else:
                return False
                
        except Exception as e:
            logger.warning("Version constraint check failed", 
                          version=version_str, constraint=constraint, error=str(e))
            return False
    
    async def find_compatible_versions(self, name: str, constraint: str) -> List[Capsule]:
        """Find all versions of a Capsule that satisfy the constraint."""
        logger.debug("Finding compatible versions", 
                    name=name, constraint=constraint)
        
        # Get all versions of the capsule
        all_versions = await self.repository.list_by_name(name)
        
        # Filter by constraint
        compatible = []
        for capsule in all_versions:
            if self.version_satisfies_constraint(capsule.version, constraint):
                compatible.append(capsule)
        
        # Sort by version (newest first)
        compatible.sort(key=lambda c: version.parse(c.version), reverse=True)
        
        logger.debug("Found compatible versions", 
                    name=name, constraint=constraint, count=len(compatible))
        
        return compatible
    
    async def resolve_single_dependency(self, dep_spec: DependencySpec) -> Optional[ResolvedDependency]:
        """Resolve a single dependency to a specific version."""
        logger.debug("Resolving dependency", 
                    name=dep_spec.name, constraint=dep_spec.version_constraint)
        
        compatible_versions = await self.find_compatible_versions(
            dep_spec.name, dep_spec.version_constraint
        )
        
        if not compatible_versions:
            logger.warning("No compatible versions found", 
                          name=dep_spec.name, constraint=dep_spec.version_constraint)
            return None
        
        # Select the newest compatible version
        selected = compatible_versions[0]
        
        logger.debug("Resolved dependency", 
                    name=dep_spec.name, 
                    resolved_version=selected.version,
                    capsule_id=str(selected.capsule_id))
        
        return ResolvedDependency(
            name=dep_spec.name,
            version=selected.version,
            capsule_id=selected.capsule_id,
            optional=dep_spec.optional
        )
    
    async def resolve_dependencies(
        self, 
        dependencies: List[str], 
        visited: Optional[Set[str]] = None
    ) -> DependencyResolutionResult:
        """Resolve all dependencies recursively."""
        if visited is None:
            visited = set()
        
        logger.info("Resolving dependencies", 
                   dependency_count=len(dependencies))
        
        result = DependencyResolutionResult()
        
        # Parse dependency specifications
        dep_specs = []
        for dep_string in dependencies:
            try:
                dep_spec = DependencySpec.parse(dep_string)
                dep_specs.append(dep_spec)
            except ValueError as e:
                logger.warning("Invalid dependency format", 
                              dependency=dep_string, error=str(e))
                result.unresolved.append(dep_string)
        
        # Resolve each dependency
        for dep_spec in dep_specs:
            # Check for circular dependencies
            dep_key = f"{dep_spec.name}@{dep_spec.version_constraint}"
            if dep_key in visited:
                logger.warning("Circular dependency detected", dependency=dep_key)
                result.conflicts.append(f"Circular dependency: {dep_key}")
                continue
            
            visited.add(dep_key)
            
            try:
                resolved = await self.resolve_single_dependency(dep_spec)
                
                if resolved is None:
                    if not dep_spec.optional:
                        result.unresolved.append(dep_spec.name)
                    continue
                
                # Check for version conflicts with already resolved dependencies
                existing = next(
                    (r for r in result.resolved if r.name == resolved.name), 
                    None
                )
                
                if existing and existing.version != resolved.version:
                    conflict_msg = f"Version conflict for {resolved.name}: {existing.version} vs {resolved.version}"
                    logger.warning("Version conflict detected", 
                                  name=resolved.name,
                                  existing_version=existing.version,
                                  new_version=resolved.version)
                    result.conflicts.append(conflict_msg)
                    continue
                
                if not existing:
                    result.resolved.append(resolved)
                
                # Recursively resolve transitive dependencies
                dep_capsule = await self.repository.get_by_id(resolved.capsule_id)
                if dep_capsule and dep_capsule.definition.dependencies:
                    transitive_result = await self.resolve_dependencies(
                        dep_capsule.definition.dependencies, 
                        visited.copy()
                    )
                    
                    # Merge results
                    for transitive_dep in transitive_result.resolved:
                        existing_transitive = next(
                            (r for r in result.resolved if r.name == transitive_dep.name), 
                            None
                        )
                        if not existing_transitive:
                            result.resolved.append(transitive_dep)
                        elif existing_transitive.version != transitive_dep.version:
                            conflict_msg = f"Transitive version conflict for {transitive_dep.name}: {existing_transitive.version} vs {transitive_dep.version}"
                            result.conflicts.append(conflict_msg)
                    
                    result.unresolved.extend(transitive_result.unresolved)
                    result.conflicts.extend(transitive_result.conflicts)
                
            except Exception as e:
                logger.error("Failed to resolve dependency", 
                            dependency=dep_spec.name, error=str(e))
                result.unresolved.append(dep_spec.name)
            
            visited.discard(dep_key)
        
        logger.info("Dependency resolution completed", 
                   resolved_count=len(result.resolved),
                   unresolved_count=len(result.unresolved),
                   conflict_count=len(result.conflicts))
        
        return result
    
    async def get_dependency_tree(self, capsule: Capsule) -> Dict[str, any]:
        """Get the full dependency tree for a Capsule."""
        logger.debug("Building dependency tree", 
                    capsule_id=str(capsule.capsule_id))
        
        async def build_tree(current_capsule: Capsule, visited: Set[UUID]) -> Dict[str, any]:
            if current_capsule.capsule_id in visited:
                return {"name": current_capsule.name, "version": current_capsule.version, "circular": True}
            
            visited.add(current_capsule.capsule_id)
            
            tree = {
                "name": current_capsule.name,
                "version": current_capsule.version,
                "capsule_id": str(current_capsule.capsule_id),
                "dependencies": []
            }
            
            for dep_string in current_capsule.definition.dependencies:
                try:
                    dep_spec = DependencySpec.parse(dep_string)
                    resolved = await self.resolve_single_dependency(dep_spec)
                    
                    if resolved:
                        dep_capsule = await self.repository.get_by_id(resolved.capsule_id)
                        if dep_capsule:
                            subtree = await build_tree(dep_capsule, visited.copy())
                            tree["dependencies"].append(subtree)
                        else:
                            tree["dependencies"].append({
                                "name": resolved.name,
                                "version": resolved.version,
                                "error": "Capsule not found"
                            })
                    else:
                        tree["dependencies"].append({
                            "name": dep_spec.name,
                            "constraint": dep_spec.version_constraint,
                            "error": "Unresolved"
                        })
                        
                except Exception as e:
                    tree["dependencies"].append({
                        "dependency": dep_string,
                        "error": str(e)
                    })
            
            visited.discard(current_capsule.capsule_id)
            return tree
        
        return await build_tree(capsule, set())