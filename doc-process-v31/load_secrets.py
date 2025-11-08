"""
Load secrets from local secrets file
Use this at the top of your scripts to load project-specific secrets
"""

import os
from pathlib import Path


def load_secrets(secrets_file: str = None):
    """
    Load secrets from centralized secrets_global file
    
    Args:
        secrets_file: Path to secrets file. If None, uses default location.
    """
    if secrets_file is None:
        # Default location - centralized secrets file
        secrets_file = Path("E:/00_dev_1/01_secrets/secrets_global")
    else:
        secrets_file = Path(secrets_file)
    
    if not secrets_file.exists():
        print(f"[WARN] Secrets file not found: {secrets_file}")
        return False
    
    loaded_count = 0
    
    with open(secrets_file, 'r') as f:
        for line in f:
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Parse key=value
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                
                # Set environment variable
                os.environ[key] = value
                loaded_count += 1
    
    print(f"[OK] Loaded {loaded_count} secrets from {secrets_file.name}")
    return True


def get_neo4j_credentials():
    """Get Neo4j credentials from environment"""
    return {
        'uri': os.getenv('NEO4J_URI'),
        'user': os.getenv('NEO4J_USER'),
        'password': os.getenv('NEO4J_PASSWORD')
    }


def get_openai_key():
    """Get OpenAI API key from environment"""
    return os.getenv('OPENAI_API_KEY')


def get_gemini_key():
    """Get Gemini API key from environment"""
    return os.getenv('GEMINI_API_KEY')


def get_anthropic_key():
    """Get Anthropic API key from environment"""
    return os.getenv('ANTHROPIC_API_KEY')


def get_gcp_config():
    """Get GCP Document AI configuration from environment"""
    return {
        'project_id': os.getenv('GCP_PROJECT_ID'),
        'processor_id': os.getenv('GCP_PROCESSOR_ID'),
        'location': os.getenv('GCP_LOCATION', 'us'),
        'credentials_path': os.getenv('GCP_CREDENTIALS_PATH'),
        'service_account': os.getenv('GCP_SERVICE_ACCOUNT')
    }


if __name__ == "__main__":
    # Test loading secrets
    print("\nTesting secrets loading...")
    print("=" * 60)
    
    if load_secrets():
        print("\nNeo4j Configuration:")
        neo4j = get_neo4j_credentials()
        print(f"  URI: {neo4j['uri']}")
        print(f"  User: {neo4j['user']}")
        print(f"  Password: {'*' * 20}")
        
        print("\nOpenAI:")
        openai_key = get_openai_key()
        if openai_key:
            print(f"  API Key: {openai_key[:20]}...{openai_key[-4:]}")
        
        print("\nGCP Document AI:")
        gcp = get_gcp_config()
        print(f"  Project ID: {gcp['project_id']}")
        print(f"  Processor ID: {gcp['processor_id']}")
        print(f"  Location: {gcp['location']}")
        print(f"  Service Account: {gcp['service_account']}")
        
        print("\n" + "=" * 60)
        print("[OK] All secrets loaded successfully!")
    else:
        print("[FAIL] Failed to load secrets")

