#!/usr/bin/env python3
"""
Receipt Service Startup Script
==============================

Simple script to start the Receipt service without full app initialization for testing.
"""

import os
import sys
import uvicorn

# Add packages to path
sys.path.insert(0, '/Users/aaryanguglani/anumate/packages/anumate-crypto')
sys.path.insert(0, '/Users/aaryanguglani/anumate/packages/anumate-receipt') 
sys.path.insert(0, '/Users/aaryanguglani/anumate/packages/anumate-errors')
sys.path.insert(0, '/Users/aaryanguglani/anumate/packages/anumate-core-config')
sys.path.insert(0, '/Users/aaryanguglani/anumate/services/receipt/src')

# Set environment variables
os.environ['RECEIPT_SIGNING_KEY'] = 'LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1DNENBUUF3QlFZREsyVndCQ0lFSUlsMjJXYzFzeDN5aU11bWgwQmFiS2E2dTkzL1JCSUMNMVBJOG9LcU9EWlEKLS0tLS1FTkQgUFJJVkFURSBLRVktLS0tLQo='

if __name__ == "__main__":
    try:
        print("🚀 Starting Receipt service...")
        print("🔑 Signing key loaded from environment")
        
        # Run the FastAPI app
        uvicorn.run(
            "anumate_receipt_service.app_production:app",
            host="0.0.0.0",
            port=8001,
            reload=False,
            log_level="info"
        )
        
    except Exception as e:
        print(f"❌ Failed to start Receipt service: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
