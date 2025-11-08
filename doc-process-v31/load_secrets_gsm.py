#!/usr/bin/env python3
"""
Auto-generated secrets loader for Google Secret Manager
"""

import os
from google.cloud import secretmanager
from google.oauth2 import service_account
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class SecretsLoader:
    def __init__(self, project_id: str, credentials_path: str = None):
        """Initialize secrets loader"""
        self.project_id = project_id
        
        if credentials_path and os.path.exists(credentials_path):
            credentials = service_account.Credentials.from_service_account_file(credentials_path)
            self.client = secretmanager.SecretManagerServiceClient(credentials=credentials)
        else:
            self.client = secretmanager.SecretManagerServiceClient()
        
        self.parent = f"projects/{project_id}"
        self._cache = {}
    
    def get_secret(self, secret_name: str, use_cache: bool = True) -> Optional[str]:
        """Get a single secret value"""
        # Convert underscore to hyphen for GSM naming
        secret_id = secret_name.lower().replace('_', '-')
        
        if use_cache and secret_id in self._cache:
            return self._cache[secret_id]
        
        try:
            name = f"{self.parent}/secrets/{secret_id}/versions/latest"
            response = self.client.access_secret_version(request={"name": name})
            value = response.payload.data.decode("utf-8")
            
            if use_cache:
                self._cache[secret_id] = value
            
            return value
        except Exception as e:
            logger.error(f"Failed to get secret {secret_name}: {e}")
            return None
    
    def load_all_secrets(self) -> Dict[str, str]:
        """Load all secrets and return as dictionary"""
        secrets = {}
        try:
            request = {"parent": self.parent}
            page_result = self.client.list_secrets(request=request)
            
            for secret in page_result:
                secret_id = secret.name.split('/')[-1]
                value = self.get_secret(secret_id.replace('-', '_'))
                if value:
                    # Convert back to original naming convention
                    key = secret_id.upper().replace('-', '_')
                    secrets[key] = value
            
        except Exception as e:
            logger.error(f"Failed to load secrets: {e}")
        
        return secrets

# Convenience functions
def get_secret(secret_name: str, project_id: str = None, credentials_path: str = None) -> Optional[str]:
    """Get a single secret (convenience function)"""
    if not project_id:
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        if not project_id:
            raise ValueError("project_id must be provided or set GOOGLE_CLOUD_PROJECT")
    
    loader = SecretsLoader(project_id, credentials_path)
    return loader.get_secret(secret_name)

def load_secrets_to_env(project_id: str = None, credentials_path: str = None) -> Dict[str, str]:
    """Load all secrets and set as environment variables"""
    if not project_id:
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        if not project_id:
            raise ValueError("project_id must be provided or set GOOGLE_CLOUD_PROJECT")
    
    loader = SecretsLoader(project_id, credentials_path)
    secrets = loader.load_all_secrets()
    
    # Set as environment variables
    for key, value in secrets.items():
        os.environ[key] = value
    
    return secrets

if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python load_secrets.py <project_id> [credentials_path]")
        sys.exit(1)
    
    project_id = sys.argv[1]
    credentials_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    loader = SecretsLoader(project_id, credentials_path)
    secrets = loader.load_all_secrets()
    
    print(f"Loaded {len(secrets)} secrets:")
    for key in sorted(secrets.keys()):
        print(f"  - {key}")
