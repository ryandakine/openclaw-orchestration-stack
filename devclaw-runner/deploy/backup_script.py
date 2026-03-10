#!/usr/bin/env python3
"""
Backup Script for OpenClaw Arbitrage Hunter

Backs up audit logs and task history.
Supports local backups, S3, and Docker volumes.
"""

import os
import sys
import gzip
import json
import shutil
import argparse
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class BackupResult:
    """Result of a backup operation."""
    success: bool
    source: str
    destination: str
    files_backed_up: int
    bytes_backed_up: int
    message: str
    timestamp: str


class BackupManager:
    """Manages backup operations."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.data_dir = project_root / "data"
        self.backup_dir = project_root / "data" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    def get_backup_filename(self, name: str) -> str:
        """Generate backup filename with timestamp."""
        return f"{name}_{self.timestamp}"
    
    def backup_audit_logs(self, destination: Path) -> BackupResult:
        """Backup audit logs directory."""
        source = self.data_dir / "audit_logs"
        files_backed_up = 0
        bytes_backed_up = 0
        
        if not source.exists():
            return BackupResult(
                success=True,
                source=str(source),
                destination=str(destination),
                files_backed_up=0,
                bytes_backed_up=0,
                message="No audit logs directory found",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        
        try:
            backup_file = destination / f"audit_logs_{self.timestamp}.tar.gz"
            
            # Create tar.gz archive
            with subprocess.Popen(
                ["tar", "-czf", str(backup_file), "-C", str(source.parent), source.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as proc:
                proc.wait()
                if proc.returncode != 0:
                    stderr = proc.stderr.read().decode() if proc.stderr else "Unknown error"
                    raise RuntimeError(f"tar failed: {stderr}")
            
            # Count stats
            for file in source.rglob("*"):
                if file.is_file():
                    files_backed_up += 1
                    bytes_backed_up += file.stat().st_size
            
            return BackupResult(
                success=True,
                source=str(source),
                destination=str(backup_file),
                files_backed_up=files_backed_up,
                bytes_backed_up=bytes_backed_up,
                message=f"Audit logs backed up: {backup_file.name}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            return BackupResult(
                success=False,
                source=str(source),
                destination=str(destination),
                files_backed_up=files_backed_up,
                bytes_backed_up=bytes_backed_up,
                message=f"Backup failed: {str(e)}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
    
    def backup_database(self, destination: Path) -> BackupResult:
        """Backup SQLite database."""
        db_files = list(self.data_dir.glob("*.db")) + list(self.data_dir.glob("*.sqlite"))
        files_backed_up = 0
        bytes_backed_up = 0
        
        if not db_files:
            return BackupResult(
                success=True,
                source=str(self.data_dir),
                destination=str(destination),
                files_backed_up=0,
                bytes_backed_up=0,
                message="No database files found",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        
        try:
            backup_file = destination / f"database_{self.timestamp}.tar.gz"
            
            with subprocess.Popen(
                ["tar", "-czf", str(backup_file)] + [str(f) for f in db_files],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as proc:
                proc.wait()
                if proc.returncode != 0:
                    stderr = proc.stderr.read().decode() if proc.stderr else "Unknown error"
                    raise RuntimeError(f"tar failed: {stderr}")
            
            for db_file in db_files:
                files_backed_up += 1
                bytes_backed_up += db_file.stat().st_size
            
            return BackupResult(
                success=True,
                source=str(self.data_dir),
                destination=str(backup_file),
                files_backed_up=files_backed_up,
                bytes_backed_up=bytes_backed_up,
                message=f"Database backed up: {backup_file.name}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            return BackupResult(
                success=False,
                source=str(self.data_dir),
                destination=str(destination),
                files_backed_up=files_backed_up,
                bytes_backed_up=bytes_backed_up,
                message=f"Backup failed: {str(e)}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
    
    def backup_config(self, destination: Path) -> BackupResult:
        """Backup configuration files."""
        config_files = [
            self.project_root / ".env",
            self.project_root / "config",
        ]
        files_backed_up = 0
        bytes_backed_up = 0
        
        existing = [f for f in config_files if f.exists()]
        
        if not existing:
            return BackupResult(
                success=True,
                source=str(self.project_root),
                destination=str(destination),
                files_backed_up=0,
                bytes_backed_up=0,
                message="No config files found",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        
        try:
            backup_file = destination / f"config_{self.timestamp}.tar.gz"
            
            with subprocess.Popen(
                ["tar", "-czf", str(backup_file)] + [str(f) for f in existing],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as proc:
                proc.wait()
                if proc.returncode != 0:
                    stderr = proc.stderr.read().decode() if proc.stderr else "Unknown error"
                    raise RuntimeError(f"tar failed: {stderr}")
            
            for config_file in existing:
                if config_file.is_file():
                    files_backed_up += 1
                    bytes_backed_up += config_file.stat().st_size
                elif config_file.is_dir():
                    for f in config_file.rglob("*"):
                        if f.is_file():
                            files_backed_up += 1
                            bytes_backed_up += f.stat().st_size
            
            return BackupResult(
                success=True,
                source=str(self.project_root),
                destination=str(backup_file),
                files_backed_up=files_backed_up,
                bytes_backed_up=bytes_backed_up,
                message=f"Config backed up: {backup_file.name}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            return BackupResult(
                success=False,
                source=str(self.project_root),
                destination=str(destination),
                files_backed_up=files_backed_up,
                bytes_backed_up=bytes_backed_up,
                message=f"Backup failed: {str(e)}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
    
    def upload_to_s3(self, local_file: Path, bucket: str, prefix: str) -> bool:
        """Upload backup to S3."""
        try:
            import boto3
            
            s3 = boto3.client("s3")
            s3_key = f"{prefix}/{local_file.name}"
            
            s3.upload_file(str(local_file), bucket, s3_key)
            return True
        except ImportError:
            print("boto3 not installed, skipping S3 upload")
            return False
        except Exception as e:
            print(f"S3 upload failed: {e}")
            return False
    
    def cleanup_old_backups(self, keep_days: int = 30) -> int:
        """Remove backups older than keep_days."""
        if not self.backup_dir.exists():
            return 0
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        removed = 0
        
        for backup_file in self.backup_dir.glob("*.tar.gz"):
            # Extract timestamp from filename
            try:
                stat = backup_file.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                
                if mtime < cutoff:
                    backup_file.unlink()
                    removed += 1
            except Exception:
                pass
        
        return removed
    
    def create_backup_manifest(self, results: List[BackupResult]) -> Path:
        """Create a manifest file for the backup."""
        manifest = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.2.1",
            "results": [asdict(r) for r in results],
        }
        
        manifest_file = self.backup_dir / f"manifest_{self.timestamp}.json"
        manifest_file.write_text(json.dumps(manifest, indent=2))
        
        return manifest_file


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Backup script for OpenClaw Arbitrage Hunter"
    )
    parser.add_argument(
        "--destination",
        "-d",
        help="Backup destination directory",
    )
    parser.add_argument(
        "--type",
        choices=["full", "audit", "database", "config"],
        default="full",
        help="Backup type (default: full)",
    )
    parser.add_argument(
        "--s3-bucket",
        help="S3 bucket for remote backup",
    )
    parser.add_argument(
        "--s3-prefix",
        default="openclaw-backups",
        help="S3 key prefix (default: openclaw-backups)",
    )
    parser.add_argument(
        "--cleanup",
        type=int,
        metavar="DAYS",
        help="Remove backups older than DAYS days",
    )
    parser.add_argument(
        "--project-root",
        help="Project root directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only output errors",
    )
    
    args = parser.parse_args()
    
    # Determine project root
    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        # Auto-detect
        script_dir = Path(__file__).resolve().parent
        project_root = script_dir.parent.parent
    
    # Setup backup manager
    manager = BackupManager(project_root)
    
    # Determine destination
    if args.destination:
        destination = Path(args.destination).resolve()
        destination.mkdir(parents=True, exist_ok=True)
    else:
        destination = manager.backup_dir
    
    # Run backups
    results: List[BackupResult] = []
    
    if args.type in ("full", "audit"):
        results.append(manager.backup_audit_logs(destination))
    
    if args.type in ("full", "database"):
        results.append(manager.backup_database(destination))
    
    if args.type in ("full", "config"):
        results.append(manager.backup_config(destination))
    
    # Upload to S3 if requested
    if args.s3_bucket:
        for result in results:
            if result.success and result.files_backed_up > 0:
                local_file = Path(result.destination)
                if manager.upload_to_s3(local_file, args.s3_bucket, args.s3_prefix):
                    result.message += f" (uploaded to s3://{args.s3_bucket}/{args.s3_prefix}/)"
    
    # Create manifest
    manifest = manager.create_backup_manifest(results)
    
    # Cleanup old backups
    if args.cleanup:
        removed = manager.cleanup_old_backups(args.cleanup)
        if not args.quiet:
            print(f"Cleaned up {removed} old backups")
    
    # Output results
    if args.json:
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": all(r.success for r in results),
            "results": [asdict(r) for r in results],
            "manifest": str(manifest),
        }
        print(json.dumps(output, indent=2))
    elif not args.quiet:
        print(f"\n{'=' * 60}")
        print("BACKUP RESULTS")
        print(f"{'=' * 60}")
        
        all_success = True
        for result in results:
            status = "✓" if result.success else "✗"
            size_mb = result.bytes_backed_up / (1024 * 1024)
            print(f"{status} {result.source}")
            print(f"  Files: {result.files_backed_up}, Size: {size_mb:.2f} MB")
            print(f"  {result.message}")
            if not result.success:
                all_success = False
        
        print(f"\nManifest: {manifest}")
        print(f"{'=' * 60}\n")
    
    # Exit with appropriate code
    sys.exit(0 if all(r.success for r in results) else 1)


if __name__ == "__main__":
    main()
