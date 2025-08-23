"""Dependency resolution for Capsules."""

import re
from typing import Any, Dict, List, Optional
from uuid import UUID

import semver
import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class DependencySpec(BaseModel):
    """Dependency specification with version constraints."""
    
    name: str
    version_constraint: str
    optional: bool = False
    
    @classmethod
    def parse(cls, dep_string: str) -> "DependencySpec":
        """Parse dependency string like 'name@>=1.0.0' or 'name@~1.2.0?optional'."""
        
        # Handle optional dependencies
        optional = dep_string.endswith("?optional")
        if optional:
            dep_string = dep_string[:-9]  # Remove "?optional"
        
        # Split name and version constraint
        if "@" in dep_string:
            name, version_constraint = dep_string.split("@", 1)
        else:
            name = dep_string
            version_constraint = "*"  # Any version
        
        return cls(
            name=name.strip(),
            version_constraint=version_constraint.strip(),
            optional=optional
        )


class ResolvedDependency(BaseModel):
    """Resolved dependency with specific version."""
    
    name: str
    version: str
    capsule_id: UUID
    optional: bool = False
    checksum: Optional[str] = None


class DependencyResolutionResult(BaseModel):
    """Result of dependency resolution."""
    
    success: bool
    resolved: List[Dict[str, Any]]
    unresolved_dependencies: List[str]
    conflicts: List[str]


class DependencyResolver:
    """Resolves Capsule dependencies."""
    
    def __init__(self, registry_client: Optional[Any] = None):
        self.registry_client = registry_client
        self._dependency_cache: Dict[str, List[Dict[str, Any]]] = {}
    
    async def resolve_dependencies(
        self,
        dependencies: List[str],
        tenant_id: UUID
    ) -> DependencyResolutionResult:
        """Resolve a list of dependency specifications."""
        
        logger.info(
            "Resolving dependencies",
            dependencies=dependencies,
            tenant_id=str(tenant_id)
        )
        
        resolved = []
        unresolved = []
        conflicts = []
        
        # Parse dependency specifications
        dependency_specs = []
        for dep_string in dependencies:
            try:
                spec = DependencySpec.parse(dep_string)
                dependency_specs.append(spec)
            except Exception as e:
                logger.error(
                    "Failed to parse dependency",
                    dependency=dep_string,
                    error=str(e)
                )
                unresolved.append(dep_string)
        
        # Resolve each dependency
        for spec in dependency_specs:
            try:
                resolved_dep = await self._resolve_single_dependency(spec, tenant_id)
                if resolved_dep:
                    resolved.append({
                        "name": resolved_dep.name,
                        "version": resolved_dep.version,
                        "capsule_id": str(resolved_dep.capsule_id),
                        "optional": resolved_dep.optional,
                        "checksum": resolved_dep.checksum
                    })
                elif not spec.optional:
                    unresolved.append(f"{spec.name}@{spec.version_constraint}")
            except Exception as e:
                logger.error(
                    "Failed to resolve dependency",
                    dependency=spec.name,
                    error=str(e)
                )
                if not spec.optional:
                    unresolved.append(f"{spec.name}@{spec.version_constraint}")
        
        # Check for version conflicts
        conflicts = self._detect_version_conflicts(resolved)
        
        success = len(unresolved) == 0 and len(conflicts) == 0
        
        logger.info(
            "Dependency resolution completed",
            success=success,
            resolved_count=len(resolved),
            unresolved_count=len(unresolved),
            conflicts_count=len(conflicts)
        )
        
        return DependencyResolutionResult(
            success=success,
            resolved=resolved,
            unresolved_dependencies=unresolved,
            conflicts=conflicts
        )
    
    async def _resolve_single_dependency(
        self,
        spec: DependencySpec,
        tenant_id: UUID
    ) -> Optional[ResolvedDependency]:
        """Resolve a single dependency specification."""
        
        # Get available versions for the dependency
        available_versions = await self._get_available_versions(spec.name, tenant_id)
        
        if not available_versions:
            logger.warning(
                "No versions found for dependency",
                dependency=spec.name,
                tenant_id=str(tenant_id)
            )
            return None
        
        # Find the best matching version
        matching_version = self._find_best_matching_version(
            spec.version_constraint,
            available_versions
        )
        
        if not matching_version:
            logger.warning(
                "No matching version found for dependency",
                dependency=spec.name,
                constraint=spec.version_constraint,
                available_versions=available_versions
            )
            return None
        
        # Get the capsule info for the resolved version
        capsule_info = await self._get_capsule_info(
            spec.name,
            matching_version,
            tenant_id
        )
        
        if not capsule_info:
            return None
        
        return ResolvedDependency(
            name=spec.name,
            version=matching_version,
            capsule_id=capsule_info["capsule_id"],
            optional=spec.optional,
            checksum=capsule_info.get("checksum")
        )
    
    async def _get_available_versions(
        self,
        capsule_name: str,
        tenant_id: UUID
    ) -> List[str]:
        """Get available versions for a Capsule."""
        
        # Check cache first
        cache_key = f"{tenant_id}:{capsule_name}"
        if cache_key in self._dependency_cache:
            return [v["version"] for v in self._dependency_cache[cache_key]]
        
        # In a real implementation, this would query the Registry service
        # For now, return mock data
        mock_versions = {
            "payment-processor": ["1.0.0", "1.1.0", "1.2.0", "2.0.0"],
            "notification-sender": ["0.9.0", "1.0.0", "1.0.1"],
            "data-validator": ["2.1.0", "2.2.0", "3.0.0"],
        }
        
        versions = mock_versions.get(capsule_name, [])
        
        # Cache the result
        self._dependency_cache[cache_key] = [
            {"version": v, "capsule_id": UUID('00000000-0000-0000-0000-000000000000')}
            for v in versions
        ]
        
        return versions
    
    async def _get_capsule_info(
        self,
        capsule_name: str,
        version: str,
        tenant_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Get Capsule information for a specific version."""
        
        # In a real implementation, this would query the Registry service
        # For now, return mock data
        return {
            "capsule_id": UUID('00000000-0000-0000-0000-000000000000'),
            "name": capsule_name,
            "version": version,
            "checksum": f"mock_checksum_{capsule_name}_{version}"
        }
    
    def _find_best_matching_version(
        self,
        constraint: str,
        available_versions: List[str]
    ) -> Optional[str]:
        """Find the best matching version for a constraint."""
        
        if constraint == "*":
            # Return the latest version
            return max(available_versions, key=lambda v: semver.VersionInfo.parse(v))
        
        # Parse constraint
        constraint_match = re.match(r'^([><=~^]*)(.+)$', constraint.strip())
        if not constraint_match:
            # Exact version match
            return constraint if constraint in available_versions else None
        
        operator = constraint_match.group(1) or "="
        target_version = constraint_match.group(2)
        
        try:
            target_semver = semver.VersionInfo.parse(target_version)
        except ValueError:
            logger.error("Invalid target version", target_version=target_version)
            return None
        
        matching_versions = []
        
        for version in available_versions:
            try:
                version_semver = semver.VersionInfo.parse(version)
                
                if self._version_matches_constraint(version_semver, operator, target_semver):
                    matching_versions.append(version)
                    
            except ValueError:
                logger.warning("Invalid version format", version=version)
                continue
        
        if not matching_versions:
            return None
        
        # Return the latest matching version
        return max(matching_versions, key=lambda v: semver.VersionInfo.parse(v))
    
    def _version_matches_constraint(
        self,
        version: semver.VersionInfo,
        operator: str,
        target: semver.VersionInfo
    ) -> bool:
        """Check if a version matches a constraint."""
        
        if operator == "=" or operator == "":
            return version == target
        elif operator == ">":
            return version > target
        elif operator == ">=":
            return version >= target
        elif operator == "<":
            return version < target
        elif operator == "<=":
            return version <= target
        elif operator == "~":
            # Compatible within patch version
            return (
                version.major == target.major and
                version.minor == target.minor and
                version >= target
            )
        elif operator == "^":
            # Compatible within minor version
            return (
                version.major == target.major and
                version >= target
            )
        else:
            logger.warning("Unknown version operator", operator=operator)
            return False
    
    def _detect_version_conflicts(self, resolved: List[Dict[str, Any]]) -> List[str]:
        """Detect version conflicts in resolved dependencies."""
        
        conflicts = []
        name_versions = {}
        
        # Group by dependency name
        for dep in resolved:
            name = dep["name"]
            version = dep["version"]
            
            if name in name_versions:
                existing_version = name_versions[name]
                if existing_version != version:
                    conflicts.append(
                        f"Version conflict for {name}: {existing_version} vs {version}"
                    )
            else:
                name_versions[name] = version
        
        return conflicts