"""
WORM (Write-Once-Read-Many) Storage Implementation

A.4–A.6 Implementation: Immutable blob storage for capsule content with
file-based and S3 backend support.
"""

import os
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import aiofiles
import aiofiles.os

from anumate_errors import StorageError, ValidationError
from .settings import RegistrySettings


class WormStore:
    """Write-Once-Read-Many storage for capsule blobs."""
    
    def __init__(self, settings: RegistrySettings):
        """Initialize WORM store with configuration."""
        self.settings = settings
        self.bucket_uri = settings.worm_bucket
        self.base_path = settings.worm_base_path
        
        # Parse storage backend from URI
        parsed = urlparse(self.bucket_uri)
        self.backend = parsed.scheme
        
        if self.backend == "file":
            self.file_path = Path(parsed.path or self.base_path)
        elif self.backend == "s3":
            self.s3_bucket = parsed.netloc
            self.s3_prefix = parsed.path.lstrip("/") if parsed.path else ""
        else:
            raise ValidationError(f"Unsupported WORM backend: {self.backend}")
    
    async def initialize(self) -> None:
        """Initialize storage backend."""
        if self.backend == "file":
            await self._initialize_file_storage()
        elif self.backend == "s3":
            await self._initialize_s3_storage()
    
    async def _initialize_file_storage(self) -> None:
        """Initialize file-based storage."""
        try:
            # Create base directory if it doesn't exist
            await aiofiles.os.makedirs(self.file_path, exist_ok=True)
            
            # Create subdirectories for hash-based partitioning
            for i in range(16):  # 0-f
                subdir = self.file_path / f"{i:x}"
                await aiofiles.os.makedirs(subdir, exist_ok=True)
                
        except Exception as e:
            raise StorageError(f"Failed to initialize file storage: {e}")
    
    async def _initialize_s3_storage(self) -> None:
        """Initialize S3 storage (validate connectivity)."""
        # For now, assume S3 credentials are configured via environment
        # In production, this would validate S3 connectivity
        pass
    
    def _get_storage_path(self, content_hash: str) -> str:
        """Get storage path for content hash."""
        if len(content_hash) != 64:
            raise ValueError("Content hash must be 64 characters")
        
        # Use first character for partitioning
        partition = content_hash[0]
        filename = f"{content_hash}.yaml"
        
        if self.backend == "file":
            return str(self.file_path / partition / filename)
        elif self.backend == "s3":
            prefix = f"{self.s3_prefix}/" if self.s3_prefix else ""
            return f"s3://{self.s3_bucket}/{prefix}{partition}/{filename}"
        else:
            raise StorageError(f"Unsupported backend: {self.backend}")
    
    def _get_public_uri(self, content_hash: str) -> str:
        """Get public URI for stored content."""
        if self.backend == "file":
            # For file storage, return file:// URI
            path = self._get_storage_path(content_hash)
            return f"file://{path}"
        elif self.backend == "s3":
            # Return S3 URI (could be HTTPS URL in production)
            return self._get_storage_path(content_hash)
        else:
            raise StorageError(f"Unsupported backend: {self.backend}")
    
    async def store_content(self, content_hash: str, yaml_content: str) -> str:
        """
        Store YAML content with given hash.
        Returns URI of stored content.
        Raises StorageError if content already exists (WORM constraint).
        """
        # Verify hash matches content
        computed_hash = hashlib.sha256(yaml_content.encode("utf-8")).hexdigest()
        if computed_hash != content_hash:
            raise ValidationError(
                f"Content hash mismatch: expected {content_hash}, got {computed_hash}"
            )
        
        storage_path = self._get_storage_path(content_hash)
        
        if self.backend == "file":
            return await self._store_file_content(storage_path, yaml_content)
        elif self.backend == "s3":
            return await self._store_s3_content(storage_path, yaml_content)
        else:
            raise StorageError(f"Unsupported backend: {self.backend}")
    
    async def _store_file_content(self, storage_path: str, yaml_content: str) -> str:
        """Store content to file system."""
        try:
            path = Path(storage_path)
            
            # WORM constraint: refuse if file already exists
            if await aiofiles.os.path.exists(path):
                raise StorageError(f"Content already exists (WORM violation): {storage_path}")
            
            # Ensure parent directory exists
            await aiofiles.os.makedirs(path.parent, exist_ok=True)
            
            # Write content atomically
            temp_path = Path(f"{storage_path}.tmp")
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(yaml_content)
            
            # Atomic rename
            await aiofiles.os.rename(temp_path, path)
            
            # Make file read-only to enforce immutability
            await aiofiles.os.chmod(path, 0o444)
            
            return f"file://{storage_path}"
            
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to store file content: {e}")
    
    async def _store_s3_content(self, storage_path: str, yaml_content: str) -> str:
        """Store content to S3 (simplified implementation)."""
        # In production, this would use aiobotocore or similar
        # For now, raise error to indicate S3 not fully implemented
        raise StorageError("S3 backend not yet implemented")
    
    async def retrieve_content(self, content_hash: str) -> Optional[str]:
        """Retrieve content by hash. Returns None if not found."""
        storage_path = self._get_storage_path(content_hash)
        
        if self.backend == "file":
            return await self._retrieve_file_content(storage_path)
        elif self.backend == "s3":
            return await self._retrieve_s3_content(storage_path)
        else:
            raise StorageError(f"Unsupported backend: {self.backend}")
    
    async def _retrieve_file_content(self, storage_path: str) -> Optional[str]:
        """Retrieve content from file system."""
        try:
            path = Path(storage_path)
            if not await aiofiles.os.path.exists(path):
                return None
            
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                return await f.read()
                
        except Exception as e:
            raise StorageError(f"Failed to retrieve file content: {e}")
    
    async def _retrieve_s3_content(self, storage_path: str) -> Optional[str]:
        """Retrieve content from S3."""
        raise StorageError("S3 backend not yet implemented")
    
    async def content_exists(self, content_hash: str) -> bool:
        """Check if content exists in storage."""
        storage_path = self._get_storage_path(content_hash)
        
        if self.backend == "file":
            return await aiofiles.os.path.exists(storage_path)
        elif self.backend == "s3":
            # S3 existence check would go here
            return False
        else:
            return False
    
    async def get_content_info(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """Get metadata about stored content."""
        if not await self.content_exists(content_hash):
            return None
        
        storage_path = self._get_storage_path(content_hash)
        
        try:
            if self.backend == "file":
                path = Path(storage_path)
                stat = await aiofiles.os.stat(path)
                
                return {
                    "content_hash": content_hash,
                    "uri": self._get_public_uri(content_hash),
                    "size_bytes": stat.st_size,
                    "created_at": stat.st_ctime,
                    "backend": "file",
                    "path": storage_path
                }
            else:
                return {
                    "content_hash": content_hash,
                    "uri": self._get_public_uri(content_hash),
                    "backend": self.backend
                }
                
        except Exception as e:
            raise StorageError(f"Failed to get content info: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on storage backend."""
        try:
            if self.backend == "file":
                # Check if base directory is writable
                test_file = self.file_path / ".health_check"
                async with aiofiles.open(test_file, "w") as f:
                    await f.write("health check")
                await aiofiles.os.unlink(test_file)
                
                return {
                    "backend": "file",
                    "status": "healthy",
                    "base_path": str(self.file_path),
                    "writable": True
                }
            else:
                return {
                    "backend": self.backend,
                    "status": "unknown",
                    "message": "Health check not implemented for this backend"
                }
                
        except Exception as e:
            return {
                "backend": self.backend,
                "status": "unhealthy",
                "error": str(e)
            }


def create_worm_store(settings: RegistrySettings) -> WormStore:
    """Factory function to create configured WORM store."""
    return WormStore(settings)
