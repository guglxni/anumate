"""
CLI for CapTokens Service
========================

Production-grade CLI for service management and operations.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from . import create_app
from .services import CleanupService, AuditService
from .database import get_async_session
from anumate_logging import get_logger

app = typer.Typer(help="Anumate CapTokens Service CLI")
console = Console()
logger = get_logger(__name__)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to bind to"),
    workers: int = typer.Option(1, help="Number of worker processes"),
    reload: bool = typer.Option(False, help="Enable auto-reload for development"),
    log_level: str = typer.Option("info", help="Log level"),
) -> None:
    """Start the CapTokens API server."""
    
    console.print(f"🚀 Starting CapTokens Service on {host}:{port}", style="bold green")
    console.print(f"📊 Workers: {workers}", style="cyan")
    console.print(f"🔄 Reload: {reload}", style="cyan")
    console.print(f"📝 Log Level: {log_level}", style="cyan")
    
    fastapi_app = create_app()
    
    uvicorn.run(
        "anumate_captokens_service.app:create_app",
        factory=True,
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        log_level=log_level,
        access_log=True,
    )


@app.command()
def cleanup(
    type: str = typer.Option("expired", help="Cleanup type: expired, replay, all"),
    batch_size: int = typer.Option(1000, help="Batch size for processing"),
    max_age_days: int = typer.Option(30, help="Maximum age in days for expired tokens"),
    dry_run: bool = typer.Option(False, help="Dry run - don't actually delete"),
) -> None:
    """Run cleanup operations on tokens and related data."""
    
    async def run_cleanup():
        console.print(f"🧹 Starting cleanup operation: {type}", style="bold yellow")
        
        async with get_async_session() as session:
            cleanup_service = CleanupService(session)
            
            if type in ["expired", "all"]:
                console.print("🗑️  Cleaning up expired tokens...", style="yellow")
                results = await cleanup_service.cleanup_expired_tokens(
                    batch_size=batch_size,
                    max_age_days=max_age_days,
                    dry_run=dry_run,
                )
                
                table = Table(title="Expired Token Cleanup Results")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="magenta")
                
                table.add_row("Job ID", results["job_id"])
                table.add_row("Status", results["status"])
                table.add_row("Tokens Processed", str(results["tokens_processed"]))
                table.add_row("Tokens Cleaned", str(results["tokens_cleaned"]))
                table.add_row("Errors", str(results["errors_encountered"]))
                table.add_row("Duration (s)", str(results["duration_seconds"]))
                table.add_row("Dry Run", str(results["dry_run"]))
                
                console.print(table)
            
            if type in ["replay", "all"]:
                console.print("🔒 Cleaning up replay protection records...", style="yellow")
                results = await cleanup_service.cleanup_replay_protection(
                    batch_size=batch_size
                )
                
                table = Table(title="Replay Protection Cleanup Results")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="magenta")
                
                table.add_row("Job ID", results["job_id"])
                table.add_row("Status", results["status"])
                table.add_row("Records Cleaned", str(results["records_cleaned"]))
                table.add_row("Duration (s)", str(results["duration_seconds"]))
                
                console.print(table)
        
        console.print("✅ Cleanup completed successfully!", style="bold green")
    
    asyncio.run(run_cleanup())


@app.command()
def stats(
    days: int = typer.Option(7, help="Number of days to analyze"),
    show_jobs: bool = typer.Option(False, help="Show recent cleanup jobs"),
) -> None:
    """Display service statistics and metrics."""
    
    async def show_stats():
        console.print(f"📊 Retrieving statistics for last {days} days...", style="bold cyan")
        
        async with get_async_session() as session:
            cleanup_service = CleanupService(session)
            audit_service = AuditService(session)
            
            # Get cleanup statistics
            cleanup_stats = await cleanup_service.get_cleanup_statistics(days=days)
            
            # Cleanup stats table
            cleanup_table = Table(title=f"Cleanup Statistics ({days} days)")
            cleanup_table.add_column("Metric", style="cyan")
            cleanup_table.add_column("Value", style="magenta")
            
            cleanup_table.add_row("Total Jobs", str(cleanup_stats["total_jobs"]))
            cleanup_table.add_row("Completed Jobs", str(cleanup_stats["completed_jobs"]))
            cleanup_table.add_row("Failed Jobs", str(cleanup_stats["failed_jobs"]))
            cleanup_table.add_row("Success Rate", f"{cleanup_stats['success_rate_percent']}%")
            cleanup_table.add_row("Total Tokens Cleaned", str(cleanup_stats["total_tokens_cleaned"]))
            cleanup_table.add_row("Avg Duration (s)", str(cleanup_stats["average_duration_seconds"]))
            
            console.print(cleanup_table)
            
            # Get audit statistics
            audit_stats = await audit_service.get_audit_statistics(days=days)
            
            # Audit stats table
            audit_table = Table(title=f"Audit Statistics ({days} days)")
            audit_table.add_column("Metric", style="cyan")
            audit_table.add_column("Value", style="magenta")
            
            audit_table.add_row("Total Operations", str(audit_stats["total_operations"]))
            audit_table.add_row("Avg Duration (ms)", str(audit_stats["average_duration_ms"]))
            
            console.print(audit_table)
            
            # Operations by type
            if audit_stats["operations_by_type"]:
                ops_table = Table(title="Operations by Type")
                ops_table.add_column("Operation", style="cyan")
                ops_table.add_column("Count", style="magenta")
                
                for op, count in audit_stats["operations_by_type"].items():
                    ops_table.add_row(op, str(count))
                
                console.print(ops_table)
            
            # Show recent jobs if requested
            if show_jobs and cleanup_stats["recent_jobs"]:
                jobs_table = Table(title="Recent Cleanup Jobs")
                jobs_table.add_column("Job ID", style="cyan")
                jobs_table.add_column("Type", style="green")
                jobs_table.add_column("Status", style="yellow")
                jobs_table.add_column("Tokens Cleaned", style="magenta")
                jobs_table.add_column("Duration (s)", style="blue")
                jobs_table.add_column("Created", style="dim")
                
                for job in cleanup_stats["recent_jobs"]:
                    jobs_table.add_row(
                        job["job_id"][:8] + "...",
                        job["job_type"],
                        job["status"],
                        str(job["tokens_cleaned"]),
                        str(job["duration_seconds"] or "N/A"),
                        job["created_at"][:19],
                    )
                
                console.print(jobs_table)
    
    asyncio.run(show_stats())


@app.command()
def health() -> None:
    """Check service health and connectivity."""
    
    async def check_health():
        console.print("🏥 Checking service health...", style="bold cyan")
        
        health_table = Table(title="Health Check Results")
        health_table.add_column("Component", style="cyan")
        health_table.add_column("Status", style="green")
        health_table.add_column("Details", style="dim")
        
        try:
            # Test database connection
            async with get_async_session() as session:
                await session.execute("SELECT 1")
                health_table.add_row("Database", "✅ Healthy", "PostgreSQL connection successful")
        except Exception as e:
            health_table.add_row("Database", "❌ Unhealthy", f"Error: {str(e)}")
        
        try:
            # Test Redis connection  
            import redis.asyncio as redis
            redis_client = redis.from_url("redis://localhost:6379")
            await redis_client.ping()
            await redis_client.close()
            health_table.add_row("Redis", "✅ Healthy", "Redis connection successful")
        except Exception as e:
            health_table.add_row("Redis", "❌ Unhealthy", f"Error: {str(e)}")
        
        # Check anumate packages
        try:
            import anumate_capability_tokens
            health_table.add_row("Core Package", "✅ Healthy", f"anumate-capability-tokens loaded")
        except ImportError as e:
            health_table.add_row("Core Package", "❌ Unhealthy", f"Import error: {str(e)}")
        
        console.print(health_table)
    
    asyncio.run(check_health())


@app.command()
def version() -> None:
    """Display version information."""
    from . import __version__, __author__, __email__
    
    console.print(f"🏷️  CapTokens Service v{__version__}", style="bold green")
    console.print(f"👨‍💻 Author: {__author__}", style="cyan")
    console.print(f"📧 Email: {__email__}", style="cyan")
    console.print(f"🐍 Python: {sys.version.split()[0]}", style="dim")


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
