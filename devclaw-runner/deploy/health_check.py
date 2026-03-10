#!/usr/bin/env python3
"""
Health Check Endpoint for OpenClaw Arbitrage Hunter

Provides HTTP endpoint and CLI for checking system health:
- API connectivity (Polymarket, Kalshi, PredictIt)
- Database connectivity
- Disk space
- Memory usage
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn


# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class HealthStatus:
    """Health check result."""
    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    response_time_ms: float
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class HealthReport:
    """Complete health report."""
    timestamp: str
    overall_status: str
    version: str
    checks: List[HealthStatus]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "overall_status": self.overall_status,
            "version": self.version,
            "checks": [asdict(c) for c in self.checks],
        }


class HealthChecker:
    """Performs health checks on system components."""
    
    VERSION = "1.2.1"
    
    # API endpoints for health checks
    APIS = {
        "polymarket": {
            "url": "https://gamma-api.polymarket.com/markets",
            "params": {"active": "true", "limit": 1},
            "timeout": 10.0,
        },
        "kalshi": {
            "url": "https://api.elections.kalshi.com/trade-api/v2/markets",
            "params": {"limit": 1},
            "timeout": 10.0,
        },
        "predictit": {
            "url": "https://www.predictit.org/api/marketdata/all/",
            "timeout": 10.0,
        },
    }
    
    def __init__(self):
        self.results: List[HealthStatus] = []
    
    async def check_api(self, name: str, config: Dict[str, Any]) -> HealthStatus:
        """Check API health."""
        start = datetime.now(timezone.utc)
        
        try:
            async with httpx.AsyncClient(timeout=config["timeout"]) as client:
                response = await client.get(
                    config["url"],
                    params=config.get("params"),
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                
                return HealthStatus(
                    name=f"api_{name}",
                    status="healthy",
                    response_time_ms=round(elapsed, 2),
                    message=f"{name.capitalize()} API responding",
                    details={"status_code": response.status_code},
                )
        except httpx.TimeoutException:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return HealthStatus(
                name=f"api_{name}",
                status="degraded",
                response_time_ms=round(elapsed, 2),
                message=f"{name.capitalize()} API timeout",
            )
        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return HealthStatus(
                name=f"api_{name}",
                status="unhealthy",
                response_time_ms=round(elapsed, 2),
                message=f"{name.capitalize()} API error: {str(e)}",
            )
    
    async def check_database(self) -> HealthStatus:
        """Check database connectivity."""
        start = datetime.now(timezone.utc)
        
        try:
            # Try to import and check database
            from shared.db import get_connection
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            conn.close()
            
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            
            return HealthStatus(
                name="database",
                status="healthy",
                response_time_ms=round(elapsed, 2),
                message="Database connection successful",
            )
        except ImportError:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return HealthStatus(
                name="database",
                status="healthy",
                response_time_ms=round(elapsed, 2),
                message="Database module not available (optional)",
            )
        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return HealthStatus(
                name="database",
                status="degraded",
                response_time_ms=round(elapsed, 2),
                message=f"Database error: {str(e)}",
            )
    
    def check_disk_space(self) -> HealthStatus:
        """Check disk space."""
        import shutil
        
        start = datetime.now(timezone.utc)
        
        try:
            # Check data directory or project root
            check_path = project_root / "data"
            if not check_path.exists():
                check_path = project_root
            
            stat = shutil.disk_usage(check_path)
            free_gb = stat.free / (1024**3)
            total_gb = stat.total / (1024**3)
            used_pct = (stat.used / stat.total) * 100
            
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            
            status = "healthy"
            if used_pct > 90:
                status = "unhealthy"
            elif used_pct > 80:
                status = "degraded"
            
            return HealthStatus(
                name="disk_space",
                status=status,
                response_time_ms=round(elapsed, 2),
                message=f"{free_gb:.1f} GB free of {total_gb:.1f} GB",
                details={
                    "free_gb": round(free_gb, 2),
                    "total_gb": round(total_gb, 2),
                    "used_percent": round(used_pct, 1),
                },
            )
        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return HealthStatus(
                name="disk_space",
                status="degraded",
                response_time_ms=round(elapsed, 2),
                message=f"Disk check error: {str(e)}",
            )
    
    def check_memory(self) -> HealthStatus:
        """Check memory usage."""
        try:
            import psutil
            
            start = datetime.now(timezone.utc)
            
            mem = psutil.virtual_memory()
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            
            status = "healthy"
            if mem.percent > 90:
                status = "unhealthy"
            elif mem.percent > 80:
                status = "degraded"
            
            return HealthStatus(
                name="memory",
                status=status,
                response_time_ms=round(elapsed, 2),
                message=f"{mem.percent}% used ({mem.available // (1024**2)} MB available)",
                details={
                    "total_mb": mem.total // (1024**2),
                    "available_mb": mem.available // (1024**2),
                    "percent_used": mem.percent,
                },
            )
        except ImportError:
            return HealthStatus(
                name="memory",
                status="healthy",
                response_time_ms=0,
                message="Memory check not available (psutil not installed)",
            )
        except Exception as e:
            return HealthStatus(
                name="memory",
                status="degraded",
                response_time_ms=0,
                message=f"Memory check error: {str(e)}",
            )
    
    async def run_all_checks(self) -> HealthReport:
        """Run all health checks."""
        self.results = []
        
        # Run API checks concurrently
        api_tasks = [
            self.check_api(name, config)
            for name, config in self.APIS.items()
        ]
        api_results = await asyncio.gather(*api_tasks, return_exceptions=True)
        
        for result in api_results:
            if isinstance(result, Exception):
                self.results.append(HealthStatus(
                    name="unknown",
                    status="unhealthy",
                    response_time_ms=0,
                    message=f"Check failed: {str(result)}",
                ))
            else:
                self.results.append(result)
        
        # Run other checks
        self.results.append(await self.check_database())
        self.results.append(self.check_disk_space())
        self.results.append(self.check_memory())
        
        # Determine overall status
        statuses = [r.status for r in self.results]
        if "unhealthy" in statuses:
            overall = "unhealthy"
        elif "degraded" in statuses:
            overall = "degraded"
        else:
            overall = "healthy"
        
        return HealthReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            overall_status=overall,
            version=self.VERSION,
            checks=self.results,
        )


# FastAPI app for HTTP endpoint
app = FastAPI(
    title="OpenClaw Health Check",
    description="Health check endpoint for Arbitrage Hunter",
    version="1.2.1",
)


@app.get("/health")
async def health_endpoint():
    """Health check endpoint."""
    checker = HealthChecker()
    report = await checker.run_all_checks()
    
    status_code = 200
    if report.overall_status == "unhealthy":
        status_code = 503
    elif report.overall_status == "degraded":
        status_code = 200  # Still OK for load balancers
    
    return JSONResponse(
        content=report.to_dict(),
        status_code=status_code,
    )


@app.get("/ready")
async def readiness_endpoint():
    """Readiness check for Kubernetes."""
    checker = HealthChecker()
    report = await checker.run_all_checks()
    
    # Only fail if critical services are down
    critical_checks = ["api_polymarket", "api_kalshi"]
    critical_results = [c for c in report.checks if c.name in critical_checks]
    
    if any(c.status == "unhealthy" for c in critical_results):
        raise HTTPException(status_code=503, detail="Critical services unavailable")
    
    return {"status": "ready", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/live")
async def liveness_endpoint():
    """Liveness check for Kubernetes."""
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Health check for OpenClaw Arbitrage Hunter"
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Run HTTP server",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Server port (default: 8080)",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Docker health check mode (exit 0 if healthy, 1 otherwise)",
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
    
    if args.server:
        uvicorn.run(app, host=args.host, port=args.port)
        return
    
    # Run checks
    checker = HealthChecker()
    report = asyncio.run(checker.run_all_checks())
    
    # Docker mode - exit with appropriate code
    if args.docker:
        sys.exit(0 if report.overall_status == "healthy" else 1)
    
    # Output results
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    elif not args.quiet:
        print(f"\n{'=' * 60}")
        print(f"Health Check Report - {report.overall_status.upper()}")
        print(f"{'=' * 60}")
        print(f"Version: {report.version}")
        print(f"Timestamp: {report.timestamp}")
        print(f"\nChecks:")
        for check in report.checks:
            icon = "✓" if check.status == "healthy" else "⚠" if check.status == "degraded" else "✗"
            print(f"  {icon} {check.name}: {check.status} ({check.response_time_ms:.0f}ms)")
            if check.message and not args.quiet:
                print(f"     {check.message}")
        print(f"{'=' * 60}\n")
    
    # Exit with error code if unhealthy
    if report.overall_status == "unhealthy":
        sys.exit(1)


if __name__ == "__main__":
    main()
