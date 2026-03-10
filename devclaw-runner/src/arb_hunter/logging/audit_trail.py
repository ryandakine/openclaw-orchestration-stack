"""
audit_trail.py - Write complete audit.json per run with all artifacts.

Creates comprehensive audit trails for each arbitrage hunting run,
including all data, decisions, and outcomes for compliance and debugging.
"""

import json
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List

import structlog

from .logger_config import get_logger


@dataclass
class AuditArtifact:
    """Represents an artifact in the audit trail."""
    artifact_type: str  # markets, matches, opportunities, alerts, rejects, errors
    file_path: Optional[str]
    record_count: int
    checksum: Optional[str] = None
    size_bytes: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "file_path": self.file_path,
            "record_count": self.record_count,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes
        }


@dataclass
class AuditRecord:
    """Complete audit record for a run."""
    run_id: str
    correlation_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    # System info
    version: str = "unknown"
    environment: str = "unknown"
    hostname: Optional[str] = None
    # Configuration
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    # Execution
    scan_parameters: Dict[str, Any] = field(default_factory=dict)
    # Results
    artifacts: List[AuditArtifact] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    # Compliance
    data_retention_days: int = 90
    gdpr_classification: str = "business_data"
    # Integrity
    audit_checksum: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with ISO timestamps."""
        return {
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "version": self.version,
            "environment": self.environment,
            "hostname": self.hostname,
            "config_snapshot": self.config_snapshot,
            "scan_parameters": self.scan_parameters,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "summary": self.summary,
            "data_retention_days": self.data_retention_days,
            "gdpr_classification": self.gdpr_classification,
            "audit_checksum": self.audit_checksum
        }


class AuditTrail:
    """
    Comprehensive audit trail generator.
    
    Creates a complete audit.json file for each run containing all
    artifacts, configuration, and outcomes for compliance and debugging.
    """
    
    def __init__(self, audit_dir: Path, version: str = "unknown"):
        self.logger = get_logger("audit_trail")
        self.audit_dir = Path(audit_dir)
        self.version = version
        self._current_audit: Optional[AuditRecord] = None
        
        # Ensure audit directory exists
        self.audit_dir.mkdir(parents=True, exist_ok=True)
    
    def start_audit(
        self,
        run_id: str,
        correlation_id: str,
        config_snapshot: Optional[Dict[str, Any]] = None,
        scan_parameters: Optional[Dict[str, Any]] = None,
        environment: str = "production",
        hostname: Optional[str] = None
    ) -> AuditRecord:
        """
        Start a new audit trail for a run.
        
        Args:
            run_id: Run identifier
            correlation_id: Correlation ID for tracing
            config_snapshot: Snapshot of configuration used
            scan_parameters: Parameters for this scan
            environment: Environment name (dev/staging/prod)
            hostname: Hostname of the executing machine
            
        Returns:
            The AuditRecord
        """
        self._current_audit = AuditRecord(
            run_id=run_id,
            correlation_id=correlation_id,
            started_at=datetime.now(timezone.utc),
            version=self.version,
            environment=environment,
            hostname=hostname or self._get_hostname(),
            config_snapshot=config_snapshot or {},
            scan_parameters=scan_parameters or {}
        )
        
        self.logger.info(
            "audit_trail_started",
            run_id=run_id,
            correlation_id=correlation_id,
            version=self.version,
            environment=environment
        )
        
        return self._current_audit
    
    def add_artifact(
        self,
        artifact_type: str,
        file_path: Optional[Path] = None,
        record_count: int = 0,
        data: Optional[List[Dict]] = None
    ) -> AuditArtifact:
        """
        Add an artifact to the audit trail.
        
        Args:
            artifact_type: Type of artifact (markets, matches, etc.)
            file_path: Path to the artifact file
            record_count: Number of records
            data: Optional data to calculate checksum from
            
        Returns:
            The AuditArtifact
        """
        if not self._current_audit:
            raise RuntimeError("No active audit. Call start_audit() first.")
        
        checksum = None
        size_bytes = None
        
        if file_path and file_path.exists():
            size_bytes = file_path.stat().st_size
            checksum = self._calculate_file_checksum(file_path)
        elif data:
            checksum = self._calculate_data_checksum(data)
        
        artifact = AuditArtifact(
            artifact_type=artifact_type,
            file_path=str(file_path) if file_path else None,
            record_count=record_count,
            checksum=checksum,
            size_bytes=size_bytes
        )
        
        self._current_audit.artifacts.append(artifact)
        
        self.logger.debug(
            "audit_artifact_added",
            run_id=self._current_audit.run_id,
            artifact_type=artifact_type,
            record_count=record_count,
            checksum=checksum
        )
        
        return artifact
    
    def update_summary(self, summary: Dict[str, Any]) -> None:
        """Update the summary section of the audit."""
        if not self._current_audit:
            raise RuntimeError("No active audit.")
        
        self._current_audit.summary.update(summary)
    
    def complete_audit(
        self,
        final_summary: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Complete the audit and write the audit.json file.
        
        Args:
            final_summary: Final summary to include
            
        Returns:
            Path to the written audit.json file
        """
        if not self._current_audit:
            raise RuntimeError("No active audit to complete.")
        
        self._current_audit.completed_at = datetime.now(timezone.utc)
        
        if final_summary:
            self._current_audit.summary.update(final_summary)
        
        # Calculate audit checksum
        self._current_audit.audit_checksum = self._calculate_audit_checksum()
        
        # Write audit file
        audit_path = self._write_audit_file()
        
        self.logger.info(
            "audit_trail_completed",
            run_id=self._current_audit.run_id,
            artifact_count=len(self._current_audit.artifacts),
            audit_file=str(audit_path),
            checksum=self._current_audit.audit_checksum
        )
        
        return audit_path
    
    def create_complete_audit(
        self,
        run_id: str,
        correlation_id: str,
        run_record: Optional[Dict[str, Any]] = None,
        market_records: Optional[List[Dict]] = None,
        match_records: Optional[List[Dict]] = None,
        reject_records: Optional[List[Dict]] = None,
        alert_records: Optional[List[Dict]] = None,
        error_records: Optional[List[Dict]] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
        scan_parameters: Optional[Dict[str, Any]] = None,
        environment: str = "production"
    ) -> Path:
        """
        Create a complete audit trail with all provided data.
        
        This is a convenience method for creating a full audit in one call.
        
        Args:
            run_id: Run identifier
            correlation_id: Correlation ID
            run_record: Run execution record
            market_records: Market fetch records
            match_records: Match records
            reject_records: Rejected opportunity records
            alert_records: Alert records
            error_records: Error records
            config_snapshot: Configuration snapshot
            scan_parameters: Scan parameters
            environment: Environment name
            
        Returns:
            Path to the written audit.json file
        """
        self.start_audit(
            run_id=run_id,
            correlation_id=correlation_id,
            config_snapshot=config_snapshot,
            scan_parameters=scan_parameters,
            environment=environment
        )
        
        # Add artifacts
        if run_record:
            self.add_artifact(
                artifact_type="run",
                data=[run_record],
                record_count=1
            )
        
        if market_records:
            self.add_artifact(
                artifact_type="markets",
                data=market_records,
                record_count=len(market_records)
            )
        
        if match_records:
            self.add_artifact(
                artifact_type="matches",
                data=match_records,
                record_count=len(match_records)
            )
        
        if reject_records:
            self.add_artifact(
                artifact_type="rejects",
                data=reject_records,
                record_count=len(reject_records)
            )
        
        if alert_records:
            self.add_artifact(
                artifact_type="alerts",
                data=alert_records,
                record_count=len(alert_records)
            )
        
        if error_records:
            self.add_artifact(
                artifact_type="errors",
                data=error_records,
                record_count=len(error_records)
            )
        
        # Build summary
        summary = {
            "total_markets": len(market_records) if market_records else 0,
            "total_matches": len(match_records) if match_records else 0,
            "total_rejects": len(reject_records) if reject_records else 0,
            "total_alerts": len(alert_records) if alert_records else 0,
            "total_errors": len(error_records) if error_records else 0
        }
        
        return self.complete_audit(final_summary=summary)
    
    def get_audit_path(self, run_id: str) -> Optional[Path]:
        """Get the path to an audit file for a run."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        audit_file = self.audit_dir / date_str / f"{run_id}_audit.json"
        if audit_file.exists():
            return audit_file
        
        # Search in all date directories
        for date_dir in self.audit_dir.iterdir():
            if date_dir.is_dir():
                audit_file = date_dir / f"{run_id}_audit.json"
                if audit_file.exists():
                    return audit_file
        
        return None
    
    def load_audit(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Load an audit file for a run."""
        audit_path = self.get_audit_path(run_id)
        if not audit_path:
            return None
        
        try:
            with open(audit_path, "r") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(
                "failed_to_load_audit",
                run_id=run_id,
                file=str(audit_path),
                error=str(e)
            )
            return None
    
    def verify_integrity(self, run_id: str) -> bool:
        """
        Verify the integrity of an audit file.
        
        Args:
            run_id: Run identifier
            
        Returns:
            True if integrity check passes
        """
        audit = self.load_audit(run_id)
        if not audit:
            return False
        
        stored_checksum = audit.get("audit_checksum")
        if not stored_checksum:
            return False
        
        # Recalculate checksum without the stored checksum field
        audit_copy = {k: v for k, v in audit.items() if k != "audit_checksum"}
        calculated = hashlib.sha256(
            json.dumps(audit_copy, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        return calculated == stored_checksum
    
    def list_audits(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        List available audit files with basic info.
        
        Args:
            start_date: Filter from date
            end_date: Filter to date
            
        Returns:
            List of audit summaries
        """
        audits = []
        
        for date_dir in self.audit_dir.iterdir():
            if not date_dir.is_dir():
                continue
            
            for audit_file in date_dir.glob("*_audit.json"):
                try:
                    with open(audit_file, "r") as f:
                        audit = json.load(f)
                        audits.append({
                            "run_id": audit.get("run_id"),
                            "started_at": audit.get("started_at"),
                            "environment": audit.get("environment"),
                            "artifact_count": len(audit.get("artifacts", [])),
                            "file_path": str(audit_file)
                        })
                except Exception:
                    pass
        
        return sorted(audits, key=lambda x: x.get("started_at", ""), reverse=True)
    
    def _write_audit_file(self) -> Path:
        """Write the current audit to disk."""
        if not self._current_audit:
            raise RuntimeError("No active audit.")
        
        # Organize by date
        date_str = self._current_audit.started_at.strftime("%Y-%m-%d")
        run_dir = self.audit_dir / date_str
        run_dir.mkdir(parents=True, exist_ok=True)
        
        audit_file = run_dir / f"{self._current_audit.run_id}_audit.json"
        
        with open(audit_file, "w") as f:
            json.dump(self._current_audit.to_dict(), f, indent=2, default=str)
        
        return audit_file
    
    def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()[:16]
    
    def _calculate_data_checksum(self, data: List[Dict]) -> str:
        """Calculate checksum of data."""
        return hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()[:16]
    
    def _calculate_audit_checksum(self) -> str:
        """Calculate checksum of the audit record."""
        if not self._current_audit:
            return ""
        
        audit_dict = self._current_audit.to_dict()
        # Remove the checksum field itself
        del audit_dict["audit_checksum"]
        
        return hashlib.sha256(
            json.dumps(audit_dict, sort_keys=True).encode()
        ).hexdigest()[:16]
    
    def _get_hostname(self) -> Optional[str]:
        """Get the system hostname."""
        try:
            import socket
            return socket.gethostname()
        except Exception:
            return None


# Singleton instance
_audit_trail_instance: Optional[AuditTrail] = None


def initialize_audit_trail(audit_dir: Path, version: str = "unknown") -> AuditTrail:
    """Initialize the global audit trail instance."""
    global _audit_trail_instance
    _audit_trail_instance = AuditTrail(audit_dir=audit_dir, version=version)
    return _audit_trail_instance


def get_audit_trail() -> AuditTrail:
    """Get the global audit trail instance."""
    if _audit_trail_instance is None:
        raise RuntimeError("Audit trail not initialized. Call initialize_audit_trail() first.")
    return _audit_trail_instance
