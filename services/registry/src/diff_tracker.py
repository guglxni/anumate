"""Capsule diff and change tracking logic."""

import json
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

import structlog

from .models import Capsule, CapsuleChange, CapsuleDiff
from .repository import CapsuleRepository

logger = structlog.get_logger(__name__)


class CapsuleDiffTracker:
    """Tracks changes and generates diffs between Capsule versions."""
    
    def __init__(self, repository: CapsuleRepository):
        """Initialize diff tracker with repository."""
        self.repository = repository
    
    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get a nested value from a dictionary using dot notation path."""
        keys = path.split('.')
        current = data
        
        for key in keys:
            # Handle array indices like 'steps[0]'
            if '[' in key and key.endswith(']'):
                array_key, index_str = key.split('[', 1)
                index = int(index_str[:-1])  # Remove the ']'
                
                if array_key not in current or not isinstance(current[array_key], list):
                    return None
                
                if index >= len(current[array_key]):
                    return None
                
                current = current[array_key][index]
            else:
                if not isinstance(current, dict) or key not in current:
                    return None
                current = current[key]
        
        return current
    
    def _set_nested_value(self, data: Dict[str, Any], path: str, value: Any) -> None:
        """Set a nested value in a dictionary using dot notation path."""
        keys = path.split('.')
        current = data
        
        for i, key in enumerate(keys[:-1]):
            # Handle array indices
            if '[' in key and key.endswith(']'):
                array_key, index_str = key.split('[', 1)
                index = int(index_str[:-1])
                
                if array_key not in current:
                    current[array_key] = []
                
                # Extend array if necessary
                while len(current[array_key]) <= index:
                    current[array_key].append({})
                
                current = current[array_key][index]
            else:
                if key not in current:
                    current[key] = {}
                current = current[key]
        
        # Set the final value
        final_key = keys[-1]
        if '[' in final_key and final_key.endswith(']'):
            array_key, index_str = final_key.split('[', 1)
            index = int(index_str[:-1])
            
            if array_key not in current:
                current[array_key] = []
            
            while len(current[array_key]) <= index:
                current[array_key].append(None)
            
            current[array_key][index] = value
        else:
            current[final_key] = value
    
    def _compare_values(self, old_val: Any, new_val: Any, path: str) -> List[CapsuleChange]:
        """Compare two values and generate changes."""
        changes = []
        
        if old_val == new_val:
            return changes
        
        # Handle different types
        if type(old_val) != type(new_val):
            changes.append(CapsuleChange(
                field_path=path,
                change_type="modified",
                old_value=old_val,
                new_value=new_val
            ))
            return changes
        
        # Handle dictionaries
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            all_keys = set(old_val.keys()) | set(new_val.keys())
            
            for key in all_keys:
                key_path = f"{path}.{key}" if path else key
                
                if key not in old_val:
                    changes.append(CapsuleChange(
                        field_path=key_path,
                        change_type="added",
                        old_value=None,
                        new_value=new_val[key]
                    ))
                elif key not in new_val:
                    changes.append(CapsuleChange(
                        field_path=key_path,
                        change_type="removed",
                        old_value=old_val[key],
                        new_value=None
                    ))
                else:
                    changes.extend(self._compare_values(old_val[key], new_val[key], key_path))
        
        # Handle lists
        elif isinstance(old_val, list) and isinstance(new_val, list):
            max_len = max(len(old_val), len(new_val))
            
            for i in range(max_len):
                item_path = f"{path}[{i}]"
                
                if i >= len(old_val):
                    changes.append(CapsuleChange(
                        field_path=item_path,
                        change_type="added",
                        old_value=None,
                        new_value=new_val[i]
                    ))
                elif i >= len(new_val):
                    changes.append(CapsuleChange(
                        field_path=item_path,
                        change_type="removed",
                        old_value=old_val[i],
                        new_value=None
                    ))
                else:
                    changes.extend(self._compare_values(old_val[i], new_val[i], item_path))
        
        # Handle primitive values
        else:
            changes.append(CapsuleChange(
                field_path=path,
                change_type="modified",
                old_value=old_val,
                new_value=new_val
            ))
        
        return changes
    
    def generate_diff(self, old_capsule: Capsule, new_capsule: Capsule) -> CapsuleDiff:
        """Generate a diff between two Capsule versions."""
        logger.debug("Generating diff", 
                    old_version=old_capsule.version,
                    new_version=new_capsule.version)
        
        # Convert definitions to dictionaries for comparison
        old_data = old_capsule.definition.model_dump()
        new_data = new_capsule.definition.model_dump()
        
        # Generate changes
        changes = self._compare_values(old_data, new_data, "")
        
        logger.debug("Diff generated", 
                    old_version=old_capsule.version,
                    new_version=new_capsule.version,
                    change_count=len(changes))
        
        return CapsuleDiff(
            from_version=old_capsule.version,
            to_version=new_capsule.version,
            changes=changes
        )
    
    async def get_version_history(self, name: str) -> List[Capsule]:
        """Get the version history for a Capsule, sorted by creation time."""
        logger.debug("Getting version history", name=name)
        
        versions = await self.repository.list_by_name(name)
        
        # Sort by creation time (oldest first)
        versions.sort(key=lambda c: c.created_at)
        
        logger.debug("Retrieved version history", 
                    name=name, version_count=len(versions))
        
        return versions
    
    async def get_diff_between_versions(
        self, 
        name: str, 
        from_version: str, 
        to_version: str
    ) -> Optional[CapsuleDiff]:
        """Get diff between two specific versions of a Capsule."""
        logger.debug("Getting diff between versions", 
                    name=name, from_version=from_version, to_version=to_version)
        
        old_capsule = await self.repository.get_by_name_version(name, from_version)
        new_capsule = await self.repository.get_by_name_version(name, to_version)
        
        if not old_capsule or not new_capsule:
            logger.warning("One or both versions not found", 
                          name=name, from_version=from_version, to_version=to_version)
            return None
        
        return self.generate_diff(old_capsule, new_capsule)
    
    async def get_changelog(self, name: str, limit: Optional[int] = None) -> List[CapsuleDiff]:
        """Get the complete changelog for a Capsule."""
        logger.debug("Getting changelog", name=name, limit=limit)
        
        versions = await self.get_version_history(name)
        
        if len(versions) < 2:
            logger.debug("Not enough versions for changelog", 
                        name=name, version_count=len(versions))
            return []
        
        changelog = []
        
        for i in range(1, len(versions)):
            if limit and len(changelog) >= limit:
                break
            
            diff = self.generate_diff(versions[i-1], versions[i])
            changelog.append(diff)
        
        # Reverse to show newest changes first
        changelog.reverse()
        
        logger.debug("Generated changelog", 
                    name=name, diff_count=len(changelog))
        
        return changelog
    
    def apply_changes(self, base_data: Dict[str, Any], changes: List[CapsuleChange]) -> Dict[str, Any]:
        """Apply a list of changes to base data."""
        logger.debug("Applying changes", change_count=len(changes))
        
        result = json.loads(json.dumps(base_data))  # Deep copy
        
        for change in changes:
            if change.change_type == "added" or change.change_type == "modified":
                self._set_nested_value(result, change.field_path, change.new_value)
            elif change.change_type == "removed":
                # For removal, we need to handle it carefully
                try:
                    path_parts = change.field_path.split('.')
                    if len(path_parts) == 1:
                        # Top-level key
                        if path_parts[0] in result:
                            del result[path_parts[0]]
                    else:
                        # Nested key - get parent and remove child
                        parent_path = '.'.join(path_parts[:-1])
                        parent = self._get_nested_value(result, parent_path)
                        if isinstance(parent, dict):
                            final_key = path_parts[-1]
                            if '[' in final_key and final_key.endswith(']'):
                                array_key, index_str = final_key.split('[', 1)
                                index = int(index_str[:-1])
                                if array_key in parent and isinstance(parent[array_key], list):
                                    if 0 <= index < len(parent[array_key]):
                                        parent[array_key].pop(index)
                            else:
                                if final_key in parent:
                                    del parent[final_key]
                except Exception as e:
                    logger.warning("Failed to apply removal change", 
                                  field_path=change.field_path, error=str(e))
        
        logger.debug("Changes applied successfully")
        return result
    
    def get_change_summary(self, diff: CapsuleDiff) -> Dict[str, int]:
        """Get a summary of changes in a diff."""
        summary = {"added": 0, "removed": 0, "modified": 0}
        
        for change in diff.changes:
            if change.change_type in summary:
                summary[change.change_type] += 1
        
        return summary
    
    def filter_changes_by_path(self, diff: CapsuleDiff, path_prefix: str) -> List[CapsuleChange]:
        """Filter changes by field path prefix."""
        return [
            change for change in diff.changes 
            if change.field_path.startswith(path_prefix)
        ]