"""WORM (Write Once, Read Many) storage for Capsule YAML content."""

import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

from anumate_errors import StorageError, ErrorCode


class WormStorageProvider:
    """Write-Once-Read-Many storage provider for immutable Capsule content."""
    
    def __init__(self, bucket_url: str):
        """
        Initialize WORM storage provider.
        
        Args:
            bucket_url: Storage bucket URL (e.g., 'file://./_worm' for local filesystem)
        """
        self.bucket_url = bucket_url
        self._initialize_storage()
    
    def _initialize_storage(self):
        """Initialize storage backend based on URL scheme."""
        parsed = urlparse(self.bucket_url)
        
        if parsed.scheme == 'file':
            self.storage_type = 'filesystem'
            self.base_path = Path(parsed.path).resolve()
            self._ensure_directory_exists()
        else:
            raise StorageError(
                error_code=ErrorCode.STORAGE_ERROR,
                message=f"Unsupported storage scheme: {parsed.scheme}"
            )
    
    def _ensure_directory_exists(self):
        """Ensure base storage directory exists."""
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise StorageError(
                error_code=ErrorCode.STORAGE_ERROR,
                message=f"Failed to create storage directory: {str(e)}"
            )
    
    def store_content(self, content_hash: str, yaml_content: str, tenant_id: str) -> str:
        """
        Store YAML content in WORM storage.
        
        Args:
            content_hash: SHA-256 hash of content (hex)
            yaml_content: YAML content to store
            tenant_id: Tenant identifier for isolation
            
        Returns:
            Storage URI for the stored content
            
        Raises:
            StorageError: If content already exists or storage fails
        """
        if self.storage_type == 'filesystem':
            return self._store_filesystem(content_hash, yaml_content, tenant_id)
        else:
            raise StorageError(
                error_code=ErrorCode.STORAGE_ERROR,
                message=f"Storage type {self.storage_type} not implemented"
            )
    
    def _store_filesystem(self, content_hash: str, yaml_content: str, tenant_id: str) -> str:
        """Store content in filesystem with tenant isolation."""
        try:
            # Create tenant-specific path: tenant_id/first_2_chars/next_2_chars/content_hash.yaml
            tenant_path = self.base_path / tenant_id
            hash_prefix = content_hash[:2]
            hash_suffix = content_hash[2:4]
            storage_dir = tenant_path / hash_prefix / hash_suffix
            
            # Ensure directory exists
            storage_dir.mkdir(parents=True, exist_ok=True)
            
            # File path
            file_path = storage_dir / f"{content_hash}.yaml"
            
            # Check if file already exists (WORM constraint)
            if file_path.exists():
                # Verify content matches (idempotent operation)
                try:
                    existing_content = file_path.read_text(encoding='utf-8')
                    if existing_content != yaml_content:
                        raise StorageError(
                            error_code=ErrorCode.STORAGE_ERROR,
                            message=f"Content hash collision detected for {content_hash}"
                        )
                    # Content matches, return existing URI
                    return self._generate_uri(tenant_id, content_hash)
                except UnicodeDecodeError:
                    raise StorageError(
                        error_code=ErrorCode.STORAGE_ERROR,
                        message=f"Existing file {content_hash} is not valid UTF-8"
                    )
            
            # Write content atomically
            temp_path = file_path.with_suffix('.tmp')
            try:
                temp_path.write_text(yaml_content, encoding='utf-8')
                temp_path.replace(file_path)
            except Exception as e:
                # Clean up temp file if it exists
                if temp_path.exists():
                    temp_path.unlink()
                raise e
            
            # Make file read-only to enforce WORM
            try:
                file_path.chmod(0o444)  # Read-only for all
            except Exception:
                # Non-fatal on some filesystems
                pass
            
            return self._generate_uri(tenant_id, content_hash)
            
        except Exception as e:
            if isinstance(e, StorageError):
                raise
            raise StorageError(
                error_code=ErrorCode.STORAGE_ERROR,
                message=f"Failed to store content: {str(e)}"
            )
    
    def retrieve_content(self, content_hash: str, tenant_id: str) -> Optional[str]:
        """
        Retrieve YAML content from WORM storage.
        
        Args:
            content_hash: SHA-256 hash of content (hex)
            tenant_id: Tenant identifier
            
        Returns:
            YAML content if found, None if not found
        """
        if self.storage_type == 'filesystem':
            return self._retrieve_filesystem(content_hash, tenant_id)
        else:
            raise StorageError(
                error_code=ErrorCode.STORAGE_ERROR,
                message=f"Storage type {self.storage_type} not implemented"
            )
    
    def _retrieve_filesystem(self, content_hash: str, tenant_id: str) -> Optional[str]:
        """Retrieve content from filesystem."""
        try:
            # Reconstruct file path
            tenant_path = self.base_path / tenant_id
            hash_prefix = content_hash[:2]
            hash_suffix = content_hash[2:4]
            file_path = tenant_path / hash_prefix / hash_suffix / f"{content_hash}.yaml"
            
            if not file_path.exists():
                return None
            
            return file_path.read_text(encoding='utf-8')
            
        except Exception as e:
            raise StorageError(
                error_code=ErrorCode.STORAGE_ERROR,
                message=f"Failed to retrieve content: {str(e)}"
            )
    
    def content_exists(self, content_hash: str, tenant_id: str) -> bool:
        """
        Check if content exists in WORM storage.
        
        Args:
            content_hash: SHA-256 hash of content (hex)
            tenant_id: Tenant identifier
            
        Returns:
            True if content exists
        """
        try:
            content = self.retrieve_content(content_hash, tenant_id)
            return content is not None
        except StorageError:
            return False
    
    def _generate_uri(self, tenant_id: str, content_hash: str) -> str:
        """Generate storage URI for content."""
        if self.storage_type == 'filesystem':
            # Create relative URI that can be resolved later
            hash_prefix = content_hash[:2]
            hash_suffix = content_hash[2:4]
            relative_path = f"{tenant_id}/{hash_prefix}/{hash_suffix}/{content_hash}.yaml"
            return f"{self.bucket_url.rstrip('/')}/{relative_path}"
        else:
            raise StorageError(
                error_code=ErrorCode.STORAGE_ERROR,
                message=f"URI generation for {self.storage_type} not implemented"
            )
    
    def parse_uri(self, uri: str) -> tuple[str, str]:
        """
        Parse storage URI to extract tenant_id and content_hash.
        
        Args:
            uri: Storage URI
            
        Returns:
            Tuple of (tenant_id, content_hash)
        """
        try:
            parsed = urlparse(uri)
            
            if parsed.scheme == 'file':
                # Extract from path: /base/tenant_id/xx/yy/content_hash.yaml
                path_parts = Path(parsed.path).parts
                if len(path_parts) < 4:
                    raise ValueError("Invalid URI format")
                
                tenant_id = path_parts[-4]
                filename = path_parts[-1]
                content_hash = filename.replace('.yaml', '')
                
                return tenant_id, content_hash
            else:
                raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")
                
        except Exception as e:
            raise StorageError(
                error_code=ErrorCode.STORAGE_ERROR,
                message=f"Failed to parse URI {uri}: {str(e)}"
            )
    
    def get_storage_stats(self) -> dict:
        """Get storage statistics (for monitoring/debugging)."""
        if self.storage_type == 'filesystem':
            try:
                total_files = 0
                total_size = 0
                
                for file_path in self.base_path.rglob('*.yaml'):
                    if file_path.is_file():
                        total_files += 1
                        total_size += file_path.stat().st_size
                
                return {
                    'storage_type': self.storage_type,
                    'base_path': str(self.base_path),
                    'total_files': total_files,
                    'total_size_bytes': total_size
                }
            except Exception as e:
                return {
                    'storage_type': self.storage_type,
                    'error': str(e)
                }
        else:
            return {'storage_type': self.storage_type}


def create_worm_storage(bucket_url: str) -> WormStorageProvider:
    """Factory function to create WORM storage provider."""
    return WormStorageProvider(bucket_url)
