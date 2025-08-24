"""
CLI tool for Anumate Integration Service

Command-line interface for managing service integration patterns,
service registry, health checks, and gateway configuration.
"""

import asyncio
import json
import sys
import time
from typing import Optional, List, Dict, Any

import typer
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress
from rich import box

from .service_registry import ServiceRegistry, ServiceCapability
from .app import IntegrationServiceConfig


app = typer.Typer(help="Anumate Integration Service CLI")
console = Console()

# Configuration
DEFAULT_INTEGRATION_URL = "http://localhost:8090"
DEFAULT_REGISTRY_URL = "redis://localhost:6379"


def get_client(base_url: str = DEFAULT_INTEGRATION_URL) -> httpx.AsyncClient:
    """Get HTTP client for integration service"""
    return httpx.AsyncClient(base_url=base_url, timeout=30.0)


@app.command()
def info():
    """Show integration service information"""
    console.print(Panel.fit(
        "[bold cyan]Anumate Integration Service[/bold cyan]\n"
        "Production-grade service integration patterns for microservices\n\n"
        "[yellow]Features:[/yellow]\n"
        "• Service Registry with Redis backend\n"
        "• Circuit Breaker protection\n"
        "• API Gateway with load balancing\n"
        "• Health check management\n"
        "• Service discovery and routing\n"
        "• Comprehensive monitoring",
        title="Integration Service",
        border_style="blue"
    ))


@app.command()
def start(
    port: int = typer.Option(8090, "--port", "-p", help="Service port"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Service host"),
    redis_url: str = typer.Option(DEFAULT_REGISTRY_URL, "--redis", "-r", help="Redis URL"),
    gateway: bool = typer.Option(True, "--gateway/--no-gateway", help="Enable API Gateway"),
    health_manager: bool = typer.Option(True, "--health/--no-health", help="Enable Health Manager"),
    log_level: str = typer.Option("info", "--log-level", "-l", help="Log level")
):
    """Start the integration service"""
    try:
        import uvicorn
        from .app import create_app
        
        config = IntegrationServiceConfig(
            host=host,
            port=port,
            redis_url=redis_url,
            gateway_enabled=gateway,
            health_manager_enabled=health_manager
        )
        
        app_instance = create_app(config)
        
        console.print(f"🚀 Starting Integration Service on {host}:{port}")
        console.print(f"📊 Service Registry: {redis_url}")
        console.print(f"🌐 API Gateway: {'enabled' if gateway else 'disabled'}")
        console.print(f"💓 Health Manager: {'enabled' if health_manager else 'disabled'}")
        
        uvicorn.run(
            app_instance,
            host=host,
            port=port,
            log_level=log_level.lower(),
            access_log=True
        )
        
    except KeyboardInterrupt:
        console.print("\n👋 Integration service stopped")
    except Exception as e:
        console.print(f"❌ Failed to start service: {e}", style="red")
        sys.exit(1)


@app.command()
def status(
    url: str = typer.Option(DEFAULT_INTEGRATION_URL, "--url", "-u", help="Integration service URL")
):
    """Check integration service status"""
    async def check_status():
        try:
            async with get_client(url) as client:
                # Get service health
                health_response = await client.get("/health")
                health_data = health_response.json()
                
                # Get metrics
                try:
                    metrics_response = await client.get("/v1/metrics")
                    metrics_data = metrics_response.json()
                except:
                    metrics_data = {}
                
                # Display status
                status = health_data.get("status", "unknown")
                status_color = "green" if status == "healthy" else "red" if status == "unhealthy" else "yellow"
                
                console.print(Panel(
                    f"[{status_color}]Status: {status.upper()}[/{status_color}]\n"
                    f"Service: {health_data.get('service', 'unknown')}\n"
                    f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(health_data.get('timestamp', 0)))}\n\n"
                    f"[bold]Components:[/bold]\n" +
                    "\n".join([f"• {comp}: {status}" for comp, status in health_data.get('components', {}).items()]),
                    title="Integration Service Status",
                    border_style=status_color
                ))
                
                # Show metrics if available
                if metrics_data:
                    registry_stats = metrics_data.get('service_registry', {})
                    lb_stats = metrics_data.get('load_balancer', {})
                    
                    if registry_stats or lb_stats:
                        console.print("\n[bold]Quick Stats:[/bold]")
                        
                        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
                        table.add_column("Component", style="cyan")
                        table.add_column("Metric", style="cyan")
                        table.add_column("Value", style="green")
                        
                        if registry_stats:
                            table.add_row("Registry", "Total Services", str(registry_stats.get('total_services', 0)))
                            table.add_row("Registry", "Active Heartbeats", str(registry_stats.get('active_heartbeats', 0)))
                        
                        if lb_stats:
                            table.add_row("Load Balancer", "Active Instances", str(lb_stats.get('active_instances', 0)))
                            table.add_row("Load Balancer", "Total Selections", str(lb_stats.get('total_selections', 0)))
                        
                        console.print(table)
                
        except httpx.ConnectError:
            console.print(f"❌ Cannot connect to integration service at {url}", style="red")
        except Exception as e:
            console.print(f"❌ Error checking status: {e}", style="red")
    
    asyncio.run(check_status())


# Service Registry commands
services_app = typer.Typer(help="Service registry management")
app.add_typer(services_app, name="services")


@services_app.command("list")
def list_services(
    url: str = typer.Option(DEFAULT_INTEGRATION_URL, "--url", "-u", help="Integration service URL"),
    service_name: Optional[str] = typer.Option(None, "--name", "-n", help="Filter by service name"),
    capability: Optional[str] = typer.Option(None, "--capability", "-c", help="Filter by capability"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output")
):
    """List registered services"""
    async def list_services_async():
        try:
            async with get_client(url) as client:
                params = {}
                if service_name:
                    params['service_name'] = service_name
                if capability:
                    params['capability'] = capability
                if status:
                    params['status'] = status
                
                response = await client.get("/v1/services", params=params)
                data = response.json()
                
                if json_output:
                    console.print(json.dumps(data, indent=2))
                    return
                
                services = data.get('services', [])
                
                if not services:
                    console.print("No services found", style="yellow")
                    return
                
                table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
                table.add_column("Name", style="cyan")
                table.add_column("Instance ID", style="blue")
                table.add_column("Version", style="green")
                table.add_column("Status", style="yellow")
                table.add_column("Endpoints", style="magenta")
                table.add_column("Capabilities", style="cyan")
                
                for service in services:
                    endpoints = list(service.get('endpoints', {}).keys())
                    capabilities = service.get('capabilities', [])
                    
                    status_style = "green" if service.get('status') == 'healthy' else "red"
                    
                    table.add_row(
                        service.get('name', 'unknown'),
                        service.get('instance_id', 'unknown')[:12] + "...",
                        service.get('version', 'unknown'),
                        f"[{status_style}]{service.get('status', 'unknown')}[/{status_style}]",
                        ", ".join(endpoints),
                        ", ".join(capabilities[:2]) + ("..." if len(capabilities) > 2 else "")
                    )
                
                console.print(f"\n[bold]Found {len(services)} services[/bold]")
                console.print(table)
                
        except Exception as e:
            console.print(f"❌ Error listing services: {e}", style="red")
    
    asyncio.run(list_services_async())


@services_app.command("register")
def register_service(
    name: str = typer.Option(..., "--name", "-n", help="Service name"),
    version: str = typer.Option("1.0.0", "--version", "-v", help="Service version"),
    instance_id: Optional[str] = typer.Option(None, "--instance", "-i", help="Instance ID"),
    endpoint: List[str] = typer.Option([], "--endpoint", "-e", help="Endpoint (format: name:protocol:host:port)"),
    capability: List[str] = typer.Option([], "--capability", "-c", help="Service capability"),
    tag: List[str] = typer.Option([], "--tag", "-t", help="Service tag"),
    url: str = typer.Option(DEFAULT_INTEGRATION_URL, "--url", "-u", help="Integration service URL")
):
    """Register a service manually"""
    async def register_service_async():
        try:
            # Parse endpoints
            endpoints = {}
            for ep in endpoint:
                parts = ep.split(':')
                if len(parts) != 4:
                    console.print(f"❌ Invalid endpoint format: {ep}. Use name:protocol:host:port", style="red")
                    return
                
                ep_name, protocol, host, port = parts
                endpoints[ep_name] = {
                    "protocol": protocol,
                    "host": host,
                    "port": int(port)
                }
            
            async with get_client(url) as client:
                data = {
                    "name": name,
                    "version": version,
                    "endpoints": endpoints,
                    "capabilities": capability,
                    "tags": tag
                }
                
                if instance_id:
                    data["instance_id"] = instance_id
                
                response = await client.post("/v1/services/register", json=data)
                result = response.json()
                
                console.print(f"✅ Service registered successfully", style="green")
                console.print(f"Instance ID: {result.get('instance_id')}")
                
        except Exception as e:
            console.print(f"❌ Error registering service: {e}", style="red")
    
    asyncio.run(register_service_async())


@services_app.command("deregister")
def deregister_service(
    name: str = typer.Option(..., "--name", "-n", help="Service name"),
    instance_id: str = typer.Option(..., "--instance", "-i", help="Instance ID"),
    url: str = typer.Option(DEFAULT_INTEGRATION_URL, "--url", "-u", help="Integration service URL")
):
    """Deregister a service"""
    async def deregister_service_async():
        try:
            async with get_client(url) as client:
                response = await client.delete(f"/v1/services/{name}/{instance_id}")
                result = response.json()
                
                console.print(f"✅ Service deregistered successfully", style="green")
                console.print(result.get('message', ''))
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                console.print(f"❌ Service not found: {name}:{instance_id}", style="red")
            else:
                console.print(f"❌ Error deregistering service: {e}", style="red")
        except Exception as e:
            console.print(f"❌ Error deregistering service: {e}", style="red")
    
    asyncio.run(deregister_service_async())


# Health management commands
health_app = typer.Typer(help="Health check management")
app.add_typer(health_app, name="health")


@health_app.command("status")
def health_status(
    url: str = typer.Option(DEFAULT_INTEGRATION_URL, "--url", "-u", help="Integration service URL"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output")
):
    """Show health status of all services"""
    async def health_status_async():
        try:
            async with get_client(url) as client:
                response = await client.get("/v1/health/status")
                data = response.json()
                
                if json_output:
                    console.print(json.dumps(data, indent=2))
                    return
                
                checkers = data.get('health_checkers', {})
                
                if not checkers:
                    console.print("No health checkers found", style="yellow")
                    return
                
                console.print(f"[bold]Health Status Summary[/bold]")
                console.print(f"Total Services: {data.get('total_services', 0)}")
                console.print(f"Healthy: [green]{data.get('healthy_services', 0)}[/green]")
                console.print(f"Unhealthy: [red]{data.get('unhealthy_services', 0)}[/red]")
                
                table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
                table.add_column("Service", style="cyan")
                table.add_column("Instance", style="blue")
                table.add_column("Status", style="yellow")
                table.add_column("Success Rate", style="green")
                table.add_column("Last Check", style="magenta")
                
                for checker_id, checker_data in checkers.items():
                    service_name = checker_data.get('service_name', 'unknown')
                    instance_id = checker_data.get('instance_id', 'unknown')
                    status = checker_data.get('current_status', 'unknown')
                    success_rate = f"{checker_data.get('success_rate', 0):.1%}"
                    last_check = checker_data.get('last_check_time', 0)
                    
                    status_style = "green" if status == 'healthy' else "red"
                    last_check_str = time.strftime('%H:%M:%S', time.localtime(last_check)) if last_check else 'never'
                    
                    table.add_row(
                        service_name,
                        instance_id[:12] + "...",
                        f"[{status_style}]{status}[/{status_style}]",
                        success_rate,
                        last_check_str
                    )
                
                console.print(table)
                
        except Exception as e:
            console.print(f"❌ Error getting health status: {e}", style="red")
    
    asyncio.run(health_status_async())


# Circuit breaker commands
circuit_app = typer.Typer(help="Circuit breaker management")
app.add_typer(circuit_app, name="circuit")


@circuit_app.command("list")
def list_circuit_breakers(
    url: str = typer.Option(DEFAULT_INTEGRATION_URL, "--url", "-u", help="Integration service URL"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output")
):
    """List all circuit breakers"""
    async def list_circuit_breakers_async():
        try:
            async with get_client(url) as client:
                response = await client.get("/v1/circuit-breakers")
                data = response.json()
                
                if json_output:
                    console.print(json.dumps(data, indent=2))
                    return
                
                if not data:
                    console.print("No circuit breakers found", style="yellow")
                    return
                
                table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
                table.add_column("Name", style="cyan")
                table.add_column("State", style="yellow")
                table.add_column("Failures", style="red")
                table.add_column("Success Rate", style="green")
                table.add_column("Last State Change", style="magenta")
                
                for cb_name, cb_data in data.items():
                    state = cb_data.get('state', 'unknown')
                    failure_count = cb_data.get('failure_count', 0)
                    
                    metrics = cb_data.get('metrics', {})
                    success_rate = f"{metrics.get('success_rate', 0):.1%}"
                    
                    last_change = cb_data.get('last_state_change', 0)
                    last_change_str = time.strftime('%H:%M:%S', time.localtime(last_change)) if last_change else 'unknown'
                    
                    state_style = "green" if state == 'closed' else "red" if state == 'open' else "yellow"
                    
                    table.add_row(
                        cb_name,
                        f"[{state_style}]{state.upper()}[/{state_style}]",
                        str(failure_count),
                        success_rate,
                        last_change_str
                    )
                
                console.print(table)
                
        except Exception as e:
            console.print(f"❌ Error listing circuit breakers: {e}", style="red")
    
    asyncio.run(list_circuit_breakers_async())


@circuit_app.command("reset")
def reset_circuit_breaker(
    name: str = typer.Option(..., "--name", "-n", help="Circuit breaker name"),
    url: str = typer.Option(DEFAULT_INTEGRATION_URL, "--url", "-u", help="Integration service URL")
):
    """Reset a circuit breaker"""
    async def reset_circuit_breaker_async():
        try:
            async with get_client(url) as client:
                response = await client.post(f"/v1/circuit-breakers/{name}/reset")
                result = response.json()
                
                console.print(f"✅ Circuit breaker reset successfully", style="green")
                console.print(result.get('message', ''))
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                console.print(f"❌ Circuit breaker not found: {name}", style="red")
            else:
                console.print(f"❌ Error resetting circuit breaker: {e}", style="red")
        except Exception as e:
            console.print(f"❌ Error resetting circuit breaker: {e}", style="red")
    
    asyncio.run(reset_circuit_breaker_async())


# Main CLI entry point
def main():
    """Main CLI entry point"""
    app()


if __name__ == "__main__":
    main()
