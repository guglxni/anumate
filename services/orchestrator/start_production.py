#!/usr/bin/env python3
"""
Production startup script for orchestrator service
Loads environment variables and starts the service with real API keys
"""

import os
import subprocess
import sys

# Load environment variables from the root .env file
def load_env_file():
    """Load .env file from project root."""
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if os.path.exists(env_path):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
            print(f"✅ Loaded environment from {env_path}")
        except ImportError:
            print("⚠️  dotenv not available, using system environment")
        except Exception as e:
            print(f"⚠️  Error loading .env: {e}")
    else:
        print("⚠️  .env file not found, using system environment")

def start_orchestrator():
    """Start the orchestrator service with production configuration."""
    
    # Load environment variables first
    load_env_file()
    
    # Validate required environment variables
    required_vars = [
        'PORTIA_API_KEY',
        'PORTIA_BASE_URL',
        'OPENAI_API_KEY', 
        'OPENAI_BASE_URL'
    ]
    
    for var in required_vars:
        if not os.getenv(var):
            print(f"❌ Missing required environment variable: {var}")
            sys.exit(1)
    
    # Set additional environment variables
    os.environ['OPENAI_MODEL'] = os.getenv('OPENAI_MODEL', 'moonshot-v1-8k')
    os.environ['APPROVALS_BASE_URL'] = os.getenv('APPROVALS_BASE_URL', 'http://localhost:8001')
    os.environ['RECEIPTS_BASE_URL'] = os.getenv('RECEIPTS_BASE_URL', 'http://localhost:8002')
    os.environ['ANUMATE_ENV'] = os.getenv('ANUMATE_ENV', 'dev')
    os.environ['PORTIA_MODE'] = os.getenv('PORTIA_MODE', 'sdk')
    
    print("🚀 Starting Production Orchestrator with real Portia SDK...")
    print(f"   - Portia API Key: {os.getenv('PORTIA_API_KEY')[:12]}...")
    print(f"   - Portia Base URL: {os.getenv('PORTIA_BASE_URL')}")
    print(f"   - OpenAI Endpoint: {os.getenv('OPENAI_BASE_URL')}")
    print(f"   - Model: {os.getenv('OPENAI_MODEL')}")
    print(f"   - Environment: {os.getenv('ANUMATE_ENV')}")
    print(f"   - Mode: SDK-only (hackathon)")
    
    # Start uvicorn with the loaded environment
    cmd = [
        sys.executable, '-m', 'uvicorn', 
        'api.main:app',
        '--host', '0.0.0.0',
        '--port', '8090',
        '--log-level', 'info'
    ]
    
    os.execvpe(cmd[0], cmd, os.environ)

if __name__ == '__main__':
    start_orchestrator()
