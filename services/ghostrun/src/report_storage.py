"""Preflight report storage and retrieval service."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

from .models import PreflightReport, GhostRunStatus


class ReportStorage:
    """Handles storage and retrieval of preflight reports."""
    
    def __init__(self, storage_path: str = "data/ghostrun/reports") -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache for fast access
        self._report_cache: Dict[UUID, PreflightReport] = {}
        self._cache_timestamps: Dict[UUID, datetime] = {}
        
        # Load existing reports into cache
        self._load_existing_reports()
    
    async def store_report(
        self, 
        run_id: UUID, 
        report: PreflightReport
    ) -> None:
        """Store a preflight report."""
        
        # Store in cache
        self._report_cache[run_id] = report
        self._cache_timestamps[run_id] = datetime.now(timezone.utc)
        
        # Persist to disk
        await self._persist_report(run_id, report)
    
    async def get_report(self, run_id: UUID) -> Optional[PreflightReport]:
        """Retrieve a preflight report."""
        
        # Check cache first
        if run_id in self._report_cache:
            return self._report_cache[run_id]
        
        # Try to load from disk
        report = await self._load_report(run_id)
        if report:
            self._report_cache[run_id] = report
            self._cache_timestamps[run_id] = datetime.now(timezone.utc)
        
        return report
    
    async def list_reports(
        self, 
        tenant_id: Optional[UUID] = None,
        limit: int = 50
    ) -> List[Dict[str, any]]:
        """List available reports with metadata."""
        
        reports = []
        
        # Get reports from cache
        for run_id, report in self._report_cache.items():
            # Filter by tenant if specified
            if tenant_id and hasattr(report, 'tenant_id'):
                # Note: PreflightReport doesn't have tenant_id, would need to be added
                # For now, we'll include all reports
                pass
            
            reports.append({
                "run_id": run_id,
                "report_id": report.report_id,
                "plan_hash": report.plan_hash,
                "generated_at": report.generated_at,
                "overall_status": report.overall_status,
                "overall_risk_level": report.overall_risk_level.value,
                "execution_feasible": report.execution_feasible,
                "total_steps": report.total_steps,
                "steps_with_issues": report.steps_with_issues,
                "high_risk_steps": report.high_risk_steps,
                "simulation_duration_ms": report.simulation_duration_ms
            })
        
        # Sort by generation time (newest first)
        reports.sort(key=lambda x: x["generated_at"], reverse=True)
        
        return reports[:limit]
    
    async def delete_report(self, run_id: UUID) -> bool:
        """Delete a preflight report."""
        
        # Remove from cache
        if run_id in self._report_cache:
            del self._report_cache[run_id]
            del self._cache_timestamps[run_id]
        
        # Remove from disk
        report_file = self._get_report_file_path(run_id)
        if report_file.exists():
            report_file.unlink()
            return True
        
        return False
    
    async def cleanup_old_reports(self, max_age_hours: int = 168) -> int:
        """Clean up old reports (default: 7 days)."""
        
        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        cleaned_count = 0
        
        # Clean up cache
        expired_run_ids = []
        for run_id, timestamp in self._cache_timestamps.items():
            if timestamp.timestamp() < cutoff_time:
                expired_run_ids.append(run_id)
        
        for run_id in expired_run_ids:
            await self.delete_report(run_id)
            cleaned_count += 1
        
        # Clean up disk files
        for report_file in self.storage_path.glob("*.json"):
            if report_file.stat().st_mtime < cutoff_time:
                report_file.unlink()
                cleaned_count += 1
        
        return cleaned_count
    
    async def get_report_statistics(self) -> Dict[str, any]:
        """Get statistics about stored reports."""
        
        total_reports = len(self._report_cache)
        
        if total_reports == 0:
            return {
                "total_reports": 0,
                "average_simulation_duration_ms": 0,
                "success_rate": 0.0,
                "average_steps": 0,
                "risk_level_distribution": {}
            }
        
        # Calculate statistics
        total_duration = 0
        successful_reports = 0
        total_steps = 0
        risk_levels = {}
        
        for report in self._report_cache.values():
            total_duration += report.simulation_duration_ms
            if report.execution_feasible:
                successful_reports += 1
            total_steps += report.total_steps
            
            risk_level = report.overall_risk_level.value
            risk_levels[risk_level] = risk_levels.get(risk_level, 0) + 1
        
        return {
            "total_reports": total_reports,
            "average_simulation_duration_ms": total_duration / total_reports,
            "success_rate": successful_reports / total_reports,
            "average_steps": total_steps / total_reports,
            "risk_level_distribution": risk_levels
        }
    
    def _get_report_file_path(self, run_id: UUID) -> Path:
        """Get file path for a report."""
        return self.storage_path / f"{run_id}.json"
    
    async def _persist_report(self, run_id: UUID, report: PreflightReport) -> None:
        """Persist report to disk."""
        
        report_file = self._get_report_file_path(run_id)
        
        # Convert report to JSON
        report_data = report.model_dump(mode='json')
        
        # Write to file
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
    
    async def _load_report(self, run_id: UUID) -> Optional[PreflightReport]:
        """Load report from disk."""
        
        report_file = self._get_report_file_path(run_id)
        
        if not report_file.exists():
            return None
        
        try:
            with open(report_file, 'r') as f:
                report_data = json.load(f)
            
            return PreflightReport(**report_data)
        
        except Exception as e:
            print(f"Error loading report {run_id}: {e}")
            return None
    
    def _load_existing_reports(self) -> None:
        """Load existing reports from disk into cache."""
        
        if not self.storage_path.exists():
            return
        
        for report_file in self.storage_path.glob("*.json"):
            try:
                run_id = UUID(report_file.stem)
                
                with open(report_file, 'r') as f:
                    report_data = json.load(f)
                
                report = PreflightReport(**report_data)
                self._report_cache[run_id] = report
                
                # Use file modification time as cache timestamp
                mtime = datetime.fromtimestamp(report_file.stat().st_mtime, tz=timezone.utc)
                self._cache_timestamps[run_id] = mtime
                
            except Exception as e:
                print(f"Error loading report from {report_file}: {e}")
                continue


# Global report storage instance
report_storage = ReportStorage()