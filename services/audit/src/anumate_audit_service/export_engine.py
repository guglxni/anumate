"""
SIEM Export Engine
=================

A.27 Implementation: Multi-format SIEM export engine supporting JSON, CSV, 
Syslog, and CEF formats with compression and secure download URLs.
"""

import asyncio
import json
import csv
import gzip
import zipfile
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, IO
from pathlib import Path
import tempfile
import io

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, and_, func, desc

from .models import AuditEvent, AuditExport

logger = logging.getLogger(__name__)


class ExportEngine:
    """
    Handles SIEM export generation in multiple formats.
    
    Supported formats:
    - JSON: Structured JSON with full event data
    - CSV: Comma-separated values for spreadsheet analysis
    - Syslog: RFC 3164/5424 compliant syslog format
    - CEF: Common Event Format for enterprise security tools
    """
    
    def __init__(self, session_factory: async_sessionmaker, export_directory: str = "/tmp/audit_exports"):
        self.session_factory = session_factory
        self.export_directory = Path(export_directory)
        self.export_directory.mkdir(exist_ok=True)
        
    async def process_export_request(self, export_id: str) -> bool:
        """
        Process an export request asynchronously.
        
        Returns:
            True if successful, False otherwise
        """
        async with self.session_factory() as session:
            try:
                # Get export job
                export_query = select(AuditExport).where(AuditExport.export_id == export_id)
                export_result = await session.execute(export_query)
                export_job = export_result.scalar_one_or_none()
                
                if not export_job:
                    logger.error(f"Export job {export_id} not found")
                    return False
                    
                # Update status to processing
                export_job.status = "processing"
                export_job.started_at = datetime.now(timezone.utc)
                await session.commit()
                
                # Generate export file
                success = await self._generate_export_file(export_job, session)
                
                # Update final status
                if success:
                    export_job.status = "completed"
                    export_job.completed_at = datetime.now(timezone.utc)
                    export_job.url_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                    export_job.download_url = f"/api/v1/audit/export/{export_id}/download"
                else:
                    export_job.status = "failed"
                    
                await session.commit()
                return success
                
            except Exception as e:
                logger.error(f"Error processing export {export_id}: {e}")
                
                # Update status to failed
                export_job.status = "failed"
                export_job.error_message = str(e)
                await session.commit()
                
                return False
                
    async def _generate_export_file(self, export_job: AuditExport, session: AsyncSession) -> bool:
        """Generate the actual export file."""
        try:
            # Build query for events to export
            query = select(AuditEvent).where(
                and_(
                    AuditEvent.tenant_id == export_job.tenant_id,
                    AuditEvent.event_timestamp >= export_job.start_date,
                    AuditEvent.event_timestamp <= export_job.end_date
                )
            )
            
            # Apply event type filters
            if export_job.event_types:
                query = query.where(AuditEvent.event_type.in_(export_job.event_types))
                
            # Apply additional filters
            if export_job.filters:
                query = await self._apply_export_filters(query, export_job.filters)
                
            # Order by timestamp
            query = query.order_by(desc(AuditEvent.event_timestamp))
            
            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total_count = total_result.scalar()
            
            export_job.total_records = total_count
            await session.commit()
            
            # Generate filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"audit_export_{export_job.tenant_id}_{timestamp}.{export_job.export_format}"
            file_path = self.export_directory / filename
            
            # Export data in batches
            batch_size = 1000
            exported_count = 0
            
            with open(file_path, 'w', encoding='utf-8') as output_file:
                # Write format-specific headers
                await self._write_export_header(output_file, export_job.export_format)
                
                # Process in batches
                offset = 0
                while offset < total_count:
                    batch_query = query.offset(offset).limit(batch_size)
                    batch_result = await session.execute(batch_query)
                    events = batch_result.scalars().all()
                    
                    if not events:
                        break
                        
                    # Write events in specified format
                    batch_exported = await self._write_events_batch(
                        output_file, events, export_job.export_format, export_job.include_pii
                    )
                    
                    exported_count += batch_exported
                    offset += batch_size
                    
                    # Update progress
                    export_job.exported_records = exported_count
                    await session.commit()
                    
                # Write format-specific footers
                await self._write_export_footer(output_file, export_job.export_format)
                
            # Apply compression if requested
            if export_job.compression:
                compressed_path = await self._compress_file(file_path, export_job.compression)
                file_path.unlink()  # Remove uncompressed file
                file_path = compressed_path
                
            # Calculate file metadata
            file_size = file_path.stat().st_size
            file_checksum = await self._calculate_file_checksum(file_path)
            
            # Update export job with file details
            export_job.file_path = str(file_path)
            export_job.file_size_bytes = file_size
            export_job.file_checksum = file_checksum
            export_job.exported_records = exported_count
            
            logger.info(f"Successfully generated export file: {file_path} ({file_size} bytes, {exported_count} records)")
            return True
            
        except Exception as e:
            logger.error(f"Error generating export file: {e}")
            return False
            
    async def _apply_export_filters(self, query, filters: Dict[str, Any]):
        """Apply additional export filters to the query."""
        if "severities" in filters:
            query = query.where(AuditEvent.event_severity.in_(filters["severities"]))
            
        if "service_names" in filters:
            query = query.where(AuditEvent.service_name.in_(filters["service_names"]))
            
        if "user_ids" in filters:
            query = query.where(AuditEvent.user_id.in_(filters["user_ids"]))
            
        if "success_only" in filters:
            query = query.where(AuditEvent.success == filters["success_only"])
            
        if "correlation_id" in filters:
            query = query.where(AuditEvent.correlation_id == filters["correlation_id"])
            
        return query
        
    async def _write_export_header(self, file: IO, export_format: str):
        """Write format-specific headers."""
        if export_format == "csv":
            writer = csv.writer(file)
            writer.writerow([
                "event_id", "tenant_id", "event_timestamp", "event_type", "event_category",
                "event_action", "event_severity", "service_name", "user_id", "client_ip",
                "event_description", "success", "error_code", "error_message",
                "correlation_id", "request_id", "processing_time_ms"
            ])
        elif export_format == "json":
            file.write('{"audit_events": [\n')
            
    async def _write_export_footer(self, file: IO, export_format: str):
        """Write format-specific footers."""
        if export_format == "json":
            file.write('\n]}\n')
            
    async def _write_events_batch(self, file: IO, events: List[AuditEvent], export_format: str, include_pii: bool) -> int:
        """Write a batch of events in the specified format."""
        if export_format == "json":
            return await self._write_json_events(file, events, include_pii)
        elif export_format == "csv":
            return await self._write_csv_events(file, events, include_pii)
        elif export_format == "syslog":
            return await self._write_syslog_events(file, events, include_pii)
        elif export_format == "cef":
            return await self._write_cef_events(file, events, include_pii)
        else:
            raise ValueError(f"Unsupported export format: {export_format}")
            
    async def _write_json_events(self, file: IO, events: List[AuditEvent], include_pii: bool) -> int:
        """Write events in JSON format."""
        for i, event in enumerate(events):
            if i > 0:
                file.write(',\n')
                
            event_data = {
                "event_id": str(event.event_id),
                "tenant_id": str(event.tenant_id),
                "event_timestamp": event.event_timestamp.isoformat(),
                "event_type": event.event_type,
                "event_category": event.event_category,
                "event_action": event.event_action,
                "event_severity": event.event_severity,
                "service_name": event.service_name,
                "service_version": event.service_version,
                "endpoint": event.endpoint,
                "method": event.method,
                "user_id": event.user_id,
                "user_type": event.user_type,
                "session_id": event.session_id,
                "client_ip": event.client_ip,
                "user_agent": event.user_agent,
                "authentication_method": event.authentication_method,
                "event_description": event.event_description,
                "success": event.success,
                "error_code": event.error_code,
                "error_message": event.error_message,
                "correlation_id": event.correlation_id,
                "parent_event_id": str(event.parent_event_id) if event.parent_event_id else None,
                "request_id": event.request_id,
                "response_code": event.response_code,
                "processing_time_ms": event.processing_time_ms,
                "tags": event.tags,
                "compliance_tags": event.compliance_tags,
                "pii_redacted": event.pii_redacted,
                "created_at": event.created_at.isoformat(),
                "source_system": event.source_system,
                "environment": event.environment
            }
            
            # Include sensitive data only if explicitly requested
            if include_pii:
                event_data.update({
                    "request_data": event.request_data,
                    "response_data": event.response_data,
                    "event_data": event.event_data,
                    "authorization_context": event.authorization_context
                })
                
            json.dump(event_data, file, default=str)
            
        return len(events)
        
    async def _write_csv_events(self, file: IO, events: List[AuditEvent], include_pii: bool) -> int:
        """Write events in CSV format."""
        writer = csv.writer(file)
        
        for event in events:
            writer.writerow([
                str(event.event_id),
                str(event.tenant_id),
                event.event_timestamp.isoformat(),
                event.event_type,
                event.event_category,
                event.event_action,
                event.event_severity,
                event.service_name,
                event.user_id or "",
                event.client_ip or "",
                event.event_description,
                event.success,
                event.error_code or "",
                event.error_message or "",
                event.correlation_id or "",
                event.request_id or "",
                event.processing_time_ms or ""
            ])
            
        return len(events)
        
    async def _write_syslog_events(self, file: IO, events: List[AuditEvent], include_pii: bool) -> int:
        """Write events in Syslog format (RFC 5424)."""
        for event in events:
            # Map severity to syslog priority
            severity_map = {"info": 6, "warning": 4, "error": 3, "critical": 2}
            priority = 16 * 8 + severity_map.get(event.event_severity, 6)  # facility 16 (local0)
            
            timestamp = event.event_timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            hostname = event.source_system or "anumate-audit"
            app_name = event.service_name
            proc_id = str(event.event_id)[:8]
            
            # Structured data
            structured_data = []
            if event.correlation_id:
                structured_data.append(f'correlation_id="{event.correlation_id}"')
            if event.user_id:
                structured_data.append(f'user_id="{event.user_id}"')
            if event.client_ip:
                structured_data.append(f'client_ip="{event.client_ip}"')
                
            sd_string = f"[audit {' '.join(structured_data)}]" if structured_data else "[audit]"
            
            message = f"{event.event_type}: {event.event_description}"
            
            syslog_line = f"<{priority}>1 {timestamp} {hostname} {app_name} {proc_id} - {sd_string} {message}\n"
            file.write(syslog_line)
            
        return len(events)
        
    async def _write_cef_events(self, file: IO, events: List[AuditEvent], include_pii: bool) -> int:
        """Write events in Common Event Format (CEF)."""
        for event in events:
            # CEF Header
            cef_version = "0"
            device_vendor = "Anumate"
            device_product = "Audit Service"
            device_version = "1.0"
            signature_id = event.event_type
            name = event.event_action
            severity = {"info": "1", "warning": "4", "error": "7", "critical": "10"}.get(event.event_severity, "1")
            
            # CEF Extensions
            extensions = []
            if event.event_timestamp:
                extensions.append(f"rt={int(event.event_timestamp.timestamp() * 1000)}")
            if event.user_id:
                extensions.append(f"suser={event.user_id}")
            if event.client_ip:
                extensions.append(f"src={event.client_ip}")
            if event.service_name:
                extensions.append(f"dhost={event.service_name}")
            if event.endpoint:
                extensions.append(f"request={event.endpoint}")
            if event.method:
                extensions.append(f"requestMethod={event.method}")
            if event.response_code:
                extensions.append(f"response={event.response_code}")
            if event.success is not None:
                extensions.append(f"outcome={'SUCCESS' if event.success else 'FAILURE'}")
            if event.correlation_id:
                extensions.append(f"cs1={event.correlation_id} cs1Label=CorrelationId")
            if event.error_message:
                extensions.append(f"msg={event.error_message}")
                
            extension_string = " ".join(extensions)
            
            cef_line = f"CEF:{cef_version}|{device_vendor}|{device_product}|{device_version}|{signature_id}|{name}|{severity}|{extension_string}\n"
            file.write(cef_line)
            
        return len(events)
        
    async def _compress_file(self, file_path: Path, compression: str) -> Path:
        """Compress the export file."""
        if compression == "gzip":
            compressed_path = file_path.with_suffix(file_path.suffix + ".gz")
            with open(file_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    f_out.writelines(f_in)
            return compressed_path
            
        elif compression == "zip":
            compressed_path = file_path.with_suffix(".zip")
            with zipfile.ZipFile(compressed_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(file_path, file_path.name)
            return compressed_path
            
        else:
            raise ValueError(f"Unsupported compression format: {compression}")
            
    async def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of the file."""
        hash_sha256 = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
                
        return hash_sha256.hexdigest()
        
    async def cleanup_expired_exports(self):
        """Clean up expired export files."""
        async with self.session_factory() as session:
            # Find expired exports
            expired_query = select(AuditExport).where(
                and_(
                    AuditExport.url_expires_at < datetime.now(timezone.utc),
                    AuditExport.status == "completed"
                )
            )
            
            expired_result = await session.execute(expired_query)
            expired_exports = expired_result.scalars().all()
            
            cleaned_count = 0
            
            for export_job in expired_exports:
                try:
                    if export_job.file_path:
                        file_path = Path(export_job.file_path)
                        if file_path.exists():
                            file_path.unlink()
                            
                    # Update database record
                    export_job.file_path = None
                    export_job.download_url = None
                    export_job.status = "expired"
                    
                    cleaned_count += 1
                    
                except Exception as e:
                    logger.error(f"Error cleaning up export {export_job.export_id}: {e}")
                    
            if cleaned_count > 0:
                await session.commit()
                logger.info(f"Cleaned up {cleaned_count} expired export files")
                
            return cleaned_count
