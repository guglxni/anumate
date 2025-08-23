#!/usr/bin/env python3
"""
Production Service Runner for CapTokens Service
===============================================

Sets up proper Python paths and environment for production service.
"""

import sys
import os
from pathlib import Path

# Setup project paths
project_root = Path(__file__).parent.parent.parent
packages_dir = project_root / "packages"

# Add package paths to Python path
sys.path.insert(0, str(packages_dir / "anumate-capability-tokens"))
sys.path.insert(0, str(packages_dir / "anumate-logging"))  
sys.path.insert(0, str(packages_dir / "anumate-errors"))
sys.path.insert(0, str(packages_dir / "anumate-core-config"))
sys.path.insert(0, str(packages_dir / "anumate-crypto"))

# Add service source to path
service_src = Path(__file__).parent / "src"
sys.path.insert(0, str(service_src))

print("✅ Python paths configured:")
for i, path in enumerate(sys.path[:10]):
    print(f"  {i}: {path}")
print()

# Test imports
print("🧪 Testing imports...")

try:
    import anumate_capability_tokens
    print("✅ anumate_capability_tokens imported successfully")
except Exception as e:
    print(f"❌ anumate_capability_tokens import failed: {e}")

try:
    import anumate_logging
    print("✅ anumate_logging imported successfully")  
except Exception as e:
    print(f"❌ anumate_logging import failed: {e}")

try:
    from anumate_captokens_service.models import CapabilityToken
    print("✅ Models imported successfully")
except Exception as e:
    print(f"❌ Models import failed: {e}")

try:
    from anumate_captokens_service.services import TokenService
    print("✅ Services imported successfully")
except Exception as e:
    print(f"❌ Services import failed: {e}")

try:
    from anumate_captokens_service.app_production import app
    print("✅ Production app imported successfully")
except Exception as e:
    print(f"❌ Production app import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n🚀 Starting production service...")

# Set environment variables for production
os.environ["DATABASE_URL"] = "postgresql+asyncpg://anumate_admin:admin_password@localhost:5432/anumate"

# Start uvicorn
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8001"))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"🌐 Starting server on {host}:{port}")
    
    uvicorn.run(
        "anumate_captokens_service.app_production:app",
        host=host,
        port=port,
        reload=False,  # Production mode
        log_level="info",
        access_log=True
    )
