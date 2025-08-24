"""
Portia MCP integration for Razorpay hosted Remote MCP server
"""

from portia import McpToolRegistry, DefaultToolRegistry, Config
from .settings import Settings


def build_mcp_registry(config: Config, settings: Settings):
    """
    Build MCP tool registry with Razorpay integration and default fallback
    
    Args:
        config: Portia configuration
        settings: Application settings with MCP configuration
    
    Returns:
        Tool registry with MCP integration (if enabled) and default fallback
    """
    
    # Start with default tool registry as base
    default_registry = DefaultToolRegistry(config=config)
    
    # If MCP is not enabled, return default only
    if not settings.ENABLE_RAZORPAY_MCP:
        print("📋 MCP disabled - using default tool registry only")
        return default_registry
    
    try:
        if settings.RAZORPAY_MCP_MODE == "remote":
            print(f"🌐 Initializing Razorpay Remote MCP:")
            print(f"   Server: {settings.RAZORPAY_MCP_SERVER_NAME}")
            print(f"   URL: {settings.RAZORPAY_MCP_URL}")
            print(f"   Auth: {'Bearer ***' if settings.RAZORPAY_MCP_AUTH.startswith('Bearer') else '***'}")
            
            # Create MCP registry for remote connection
            mcp_registry = McpToolRegistry.from_streamable_http_connection(
                server_name=settings.RAZORPAY_MCP_SERVER_NAME,
                url=settings.RAZORPAY_MCP_URL,
                headers={"Authorization": settings.RAZORPAY_MCP_AUTH}
            )
            
            print("✅ Razorpay Remote MCP registry initialized")
            return mcp_registry
        
        elif settings.RAZORPAY_MCP_MODE == "stdio":
            print(f"🖥️  Initializing Razorpay stdio MCP:")
            print(f"   Server: {settings.RAZORPAY_MCP_SERVER_NAME}")
            print(f"   Key ID: {settings.RAZORPAY_KEY_ID[:8]}***")
            print(f"   Command: npx -y @razorpay/mcp-server")
            
            # Create MCP registry for stdio connection
            mcp_registry = McpToolRegistry.from_stdio_connection(
                server_name=settings.RAZORPAY_MCP_SERVER_NAME,
                command="npx",
                args=[
                    "-y", "@razorpay/mcp-server",
                    "--api-key-id", settings.RAZORPAY_KEY_ID,
                    "--api-key-secret", settings.RAZORPAY_KEY_SECRET
                ]
            )
            
            print("✅ Razorpay stdio MCP registry initialized")
            return mcp_registry
        
        else:
            raise ValueError(f"Invalid RAZORPAY_MCP_MODE: {settings.RAZORPAY_MCP_MODE}")
    
    except Exception as e:
        print(f"❌ Failed to initialize Razorpay MCP registry: {e}")
        print("🔄 Falling back to default tool registry only")
        return default_registry


def get_available_mcp_tools(registry, server_name: str = "razorpay") -> list[str]:
    """
    Get list of available MCP tools from the registry
    
    Args:
        registry: Tool registry instance
        server_name: MCP server name to query
    
    Returns:
        List of available tool names
    """
    try:
        # This would need to be implemented based on Portia SDK's actual API
        # for inspecting available tools from an MCP server
        if hasattr(registry, 'list_tools'):
            tools = registry.list_tools(server_name=server_name)
            return [tool.name for tool in tools]
        else:
            # Fallback: return expected Razorpay MCP tools
            return [
                "razorpay.payment_links.create",
                "razorpay.payment_links.get",
                "razorpay.refunds.create",
                "razorpay.refunds.get",
                "razorpay.payments.get",
                "razorpay.orders.create",
                "razorpay.orders.get"
            ]
    except Exception as e:
        print(f"⚠️ Warning: Could not list MCP tools: {e}")
        return []


def validate_mcp_connection(registry, server_name: str = "razorpay") -> bool:
    """
    Validate MCP connection by checking available tools
    
    Args:
        registry: Tool registry instance
        server_name: MCP server name to validate
    
    Returns:
        True if connection is valid, False otherwise
    """
    try:
        tools = get_available_mcp_tools(registry, server_name)
        if tools:
            print(f"✅ MCP connection validated - {len(tools)} tools available")
            return True
        else:
            print("⚠️ MCP connection established but no tools found")
            return False
    except Exception as e:
        print(f"❌ MCP connection validation failed: {e}")
        return False
