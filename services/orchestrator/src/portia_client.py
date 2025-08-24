"""
Portia SDK Client - SDK-only implementation with MCP integration
Integrates with Moonshot Kimi API as OpenAI-compatible backend and Razorpay MCP
"""
import os
import asyncio
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from .settings import Settings
from .portia_mcp import build_mcp_registry

# Load environment variables
load_dotenv()

try:
    from portia import Portia, Config, DefaultToolRegistry
    from portia.plan import Plan
    PORTIA_SDK_AVAILABLE = True
    _import_error = None
except ImportError as e:
    PORTIA_SDK_AVAILABLE = False
    _import_error = str(e)

logger = logging.getLogger(__name__)


class PortiaClient:
    """
    SDK-only Portia client with MCP integration for hackathon environment.
    Configured to use Moonshot Kimi API as OpenAI-compatible backend.
    """
    
    def __init__(self, api_key: str):
        if not PORTIA_SDK_AVAILABLE:
            raise ImportError(
                f"❌ Portia SDK not available: {_import_error}\n"
                f"💡 Install with: pip install portia-sdk-python\n"
                f"📚 Docs: https://docs.portialabs.ai/install"
            )
        
        self.api_key = api_key
        self._portia = None
        self._tool_registry = None
        
        # Validate environment for Moonshot Kimi
        self._validate_kimi_config()
        self._initialize_portia()
    
    def _validate_kimi_config(self):
        """Validate Moonshot Kimi configuration"""
        openai_key = os.getenv("OPENAI_API_KEY")
        openai_base = os.getenv("OPENAI_BASE_URL")
        
        if not openai_key:
            raise ValueError("❌ OPENAI_API_KEY required for Moonshot Kimi integration")
        
        if not openai_base:
            raise ValueError("❌ OPENAI_BASE_URL required for Moonshot Kimi integration")
        
        if "moonshot" not in openai_base.lower():
            raise ValueError(f"❌ Expected Moonshot base URL, got: {openai_base}")
        
        print(f"✅ Moonshot Kimi config validated:")
        print(f"   Base URL: {openai_base}")
        print(f"   Model: {os.getenv('OPENAI_MODEL', 'moonshot-v1-8k')}")
    
    def _initialize_portia(self):
        """Initialize Portia with default config and Moonshot Kimi backend"""
        try:
            # Use default configuration - will automatically use cloud storage
            config = Config.from_default(
                llm_provider="openai",
                default_model=f"openai/{os.getenv('OPENAI_MODEL', 'moonshot-v1-8k')}"
            )
            
            # Get settings for MCP integration
            from .settings import get_settings
            settings = get_settings()
            
            # Build MCP registry with fallback to default tools
            self._tool_registry = build_mcp_registry(config, settings)
            
            # Initialize Portia with MCP-enabled tools
            self._portia = Portia(config=config, tools=self._tool_registry)
            
            if settings.ENABLE_RAZORPAY_MCP:
                print("✅ Portia SDK initialized with default config + Moonshot Kimi + Razorpay MCP")
            else:
                print("✅ Portia SDK initialized with default config + Moonshot Kimi backend")
            
        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize Portia SDK: {e}")
    
    async def _perform_readiness_probe(self) -> bool:
        """Perform readiness probe for Portia SDK"""
        try:
            # Simple plan creation as readiness check
            plan = self._portia.plan("ping")
            return isinstance(plan, Plan)
        except Exception as e:
            print(f"⚠️  Portia readiness probe failed: {e}")
            return False
    
    def is_ready(self) -> bool:
        """Check if Portia client is ready (synchronous)"""
        if not self._portia:
            return False
        
        try:
            # Run async readiness probe
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._perform_readiness_probe())
            loop.close()
            return result
        except Exception:
            return False
    
    async def create_plan(self, query: str) -> Dict[str, Any]:
        """Create a plan from a query using Moonshot Kimi"""
        if not self._portia:
            raise RuntimeError("Portia not initialized")
        
        try:
            plan = self._portia.plan(query)
            return {
                "status": "created",
                "plan_id": str(plan.uuid) if hasattr(plan, 'uuid') else "unknown",
                "query": query,
                "backend": "moonshot-kimi"
            }
        except Exception as e:
            raise RuntimeError(f"Failed to create plan: {e}")
    
    async def run_plan(self, plan_or_query: str) -> Dict[str, Any]:
        """Run a plan using Moonshot Kimi backend"""
        if not self._portia:
            raise RuntimeError("Portia not initialized")
        
        try:
            # Use the run method for direct query execution
            run_result = self._portia.run(plan_or_query)
            
            return {
                "status": "completed",
                "query": plan_or_query,
                "backend": "moonshot-kimi",
                "result": run_result.model_dump() if hasattr(run_result, 'model_dump') else str(run_result)
            }
        except Exception as e:
            raise RuntimeError(f"Failed to run plan: {e}")
    
    async def execute_plan(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a plan - main method for orchestrator integration"""
        query = plan_data.get("query") or plan_data.get("description", "Execute plan")
        return await self.run_plan(query)
    
    def get_tool_registry(self):
        """Get the tool registry (for testing and introspection)"""
        return self._tool_registry


# Factory function for settings integration
def create_portia_client(api_key: str) -> PortiaClient:
    """Factory function to create PortiaClient instance with cloud config"""
    return PortiaClient(api_key=api_key)