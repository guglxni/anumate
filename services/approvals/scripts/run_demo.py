#!/usr/bin/env python3
"""Run the Approvals service demo."""

import asyncio
import sys
import os

# Add the service directory to Python path  
service_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, service_dir)

from demo import demo_approvals_clarifications_integration, demo_approval_workflow_scenarios


async def main():
    """Run the complete demo."""
    try:
        await demo_approvals_clarifications_integration()
        await demo_approval_workflow_scenarios()
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
