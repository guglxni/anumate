"""Secrets management using HashiCorp Vault."""

import os
from typing import Any, Dict, Optional
from uuid import UUID

import hvac
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from .tenant_context import get_current_tenant_id

logger = structlog.get_logger(__name__)


class SecretsManager:
    """HashiCorp Vault secrets manager with tenant isolation."""
    
    def __init__(
        self, 
        vault_url: Optional[str] = None,
        vault_token: Optional[str] = None,
    ) -> None:
        """Initialize secrets manager."""
        self.vault_url = vault_url or os.getenv("VAULT_ADDR", "http://localhost:8200")
        self.vault_token = vault_token or os.getenv("VAULT_TOKEN")
        self._client: Optional[hvac.Client] = None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def get_client(self) -> hvac.Client:
        """Get or create Vault client."""
        if self._client is None:
            self._client = hvac.Client(
                url=self.vault_url,
                token=self.vault_token,
            )
            
            # Verify authentication
            if not self._client.is_authenticated():
                raise ValueError("Vault authentication failed")
            
            logger.info("Vault client created and authenticated")
        
        return self._client
    
    def _get_tenant_path(self, path: str) -> str:
        """Get tenant-specific secret path."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set. Use TenantContext manager.")
        return f"tenants/{tenant_id}/{path}"
    
    def _get_global_path(self, path: str) -> str:
        """Get global (non-tenant) secret path."""
        return f"anumate/{path}"
    
    async def get(
        self, 
        path: str, 
        key: Optional[str] = None,
        global_secret: bool = False,
    ) -> Any:
        """Get secret from Vault."""
        client = self.get_client()
        
        if global_secret:
            full_path = self._get_global_path(path)
        else:
            full_path = self._get_tenant_path(path)
        
        try:
            response = client.secrets.kv.v2.read_secret_version(
                path=full_path,
                mount_point="secret",
            )
            
            data = response["data"]["data"]
            
            if key:
                result = data.get(key)
            else:
                result = data
            
            logger.debug("Retrieved secret", path=full_path, key=key)
            return result
            
        except hvac.exceptions.InvalidPath:
            logger.warning("Secret not found", path=full_path, key=key)
            return None
        except Exception as e:
            logger.error("Error retrieving secret", path=full_path, error=str(e))
            raise
    
    async def set(
        self, 
        path: str, 
        data: Dict[str, Any],
        global_secret: bool = False,
    ) -> None:
        """Set secret in Vault."""
        client = self.get_client()
        
        if global_secret:
            full_path = self._get_global_path(path)
        else:
            full_path = self._get_tenant_path(path)
        
        try:
            client.secrets.kv.v2.create_or_update_secret(
                path=full_path,
                secret=data,
                mount_point="secret",
            )
            
            logger.info("Secret stored", path=full_path, keys=list(data.keys()))
            
        except Exception as e:
            logger.error("Error storing secret", path=full_path, error=str(e))
            raise
    
    async def delete(self, path: str, global_secret: bool = False) -> None:
        """Delete secret from Vault."""
        client = self.get_client()
        
        if global_secret:
            full_path = self._get_global_path(path)
        else:
            full_path = self._get_tenant_path(path)
        
        try:
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=full_path,
                mount_point="secret",
            )
            
            logger.info("Secret deleted", path=full_path)
            
        except Exception as e:
            logger.error("Error deleting secret", path=full_path, error=str(e))
            raise
    
    async def encrypt(
        self, 
        data: str, 
        key_name: Optional[str] = None,
        tenant_key: bool = True,
    ) -> str:
        """Encrypt data using Vault Transit engine."""
        client = self.get_client()
        
        if tenant_key:
            tenant_id = get_current_tenant_id()
            if tenant_id is None:
                raise ValueError("No tenant context set. Use TenantContext manager.")
            encryption_key = key_name or f"tenant-{tenant_id}"
        else:
            encryption_key = key_name or "anumate-master"
        
        try:
            response = client.secrets.transit.encrypt_data(
                name=encryption_key,
                plaintext=data,
                mount_point="transit",
            )
            
            ciphertext = response["data"]["ciphertext"]
            logger.debug("Data encrypted", key=encryption_key)
            return ciphertext
            
        except Exception as e:
            logger.error("Error encrypting data", key=encryption_key, error=str(e))
            raise
    
    async def decrypt(
        self, 
        ciphertext: str, 
        key_name: Optional[str] = None,
        tenant_key: bool = True,
    ) -> str:
        """Decrypt data using Vault Transit engine."""
        client = self.get_client()
        
        if tenant_key:
            tenant_id = get_current_tenant_id()
            if tenant_id is None:
                raise ValueError("No tenant context set. Use TenantContext manager.")
            encryption_key = key_name or f"tenant-{tenant_id}"
        else:
            encryption_key = key_name or "anumate-master"
        
        try:
            response = client.secrets.transit.decrypt_data(
                name=encryption_key,
                ciphertext=ciphertext,
                mount_point="transit",
            )
            
            plaintext = response["data"]["plaintext"]
            logger.debug("Data decrypted", key=encryption_key)
            return plaintext
            
        except Exception as e:
            logger.error("Error decrypting data", key=encryption_key, error=str(e))
            raise
    
    async def create_tenant_key(self, tenant_id: UUID) -> None:
        """Create encryption key for tenant."""
        client = self.get_client()
        key_name = f"tenant-{tenant_id}"
        
        try:
            client.secrets.transit.create_key(
                name=key_name,
                key_type="aes256-gcm96",
                mount_point="transit",
            )
            
            logger.info("Created tenant encryption key", tenant_id=tenant_id, key=key_name)
            
        except Exception as e:
            logger.error(
                "Error creating tenant key", 
                tenant_id=tenant_id, 
                key=key_name, 
                error=str(e)
            )
            raise
    
    async def rotate_key(
        self, 
        key_name: Optional[str] = None,
        tenant_key: bool = True,
    ) -> None:
        """Rotate encryption key."""
        client = self.get_client()
        
        if tenant_key:
            tenant_id = get_current_tenant_id()
            if tenant_id is None:
                raise ValueError("No tenant context set. Use TenantContext manager.")
            encryption_key = key_name or f"tenant-{tenant_id}"
        else:
            encryption_key = key_name or "anumate-master"
        
        try:
            client.secrets.transit.rotate_key(
                name=encryption_key,
                mount_point="transit",
            )
            
            logger.info("Rotated encryption key", key=encryption_key)
            
        except Exception as e:
            logger.error("Error rotating key", key=encryption_key, error=str(e))
            raise