#!/usr/bin/env python3
"""
Systemd Service Generator for Prediction Market Arbitrage Scanner

Generates pred-market-arb.service file with proper paths and configurations.
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional


SYSTEMD_SERVICE_TEMPLATE = """[Unit]
Description=Prediction Market Arbitrage Scanner
After=network.target

[Service]
Type=oneshot
WorkingDirectory={working_dir}
Environment=PYTHONPATH={pythonpath}
EnvironmentFile={env_file}
ExecStart={python_exec} -m devclaw_runner.src.prediction_markets.arb_scanner
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pred-market-arb

# Safety settings
User={user}
Group={group}
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={data_dir}

# Resource limits
MemoryMax=512M
CPUQuota=50%
TasksMax=50

# Timeouts
TimeoutStartSec=300
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
"""


def get_default_user() -> str:
    """Get default user from environment."""
    return os.environ.get("USER", os.environ.get("USERNAME", "openclaw"))


def find_project_root() -> Path:
    """Find the project root directory."""
    current = Path(__file__).resolve().parent
    # Go up to project root (devclaw-runner/deploy -> devclaw-runner -> project root)
    return current.parent.parent


def generate_service_file(
    working_dir: Optional[str] = None,
    user: Optional[str] = None,
    group: Optional[str] = None,
    python_exec: str = "/usr/bin/python3",
    env_file: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    """
    Generate the systemd service file content.
    
    Args:
        working_dir: Project working directory (default: auto-detect)
        user: System user to run as (default: current user)
        group: System group to run as (default: same as user)
        python_exec: Python executable path
        env_file: Path to environment file
        output_path: Where to write the service file
        
    Returns:
        Generated service file content
    """
    project_root = find_project_root()
    
    working_dir = working_dir or str(project_root)
    user = user or get_default_user()
    group = group or user
    env_file = env_file or str(project_root / ".env")
    data_dir = str(project_root / "data")
    
    content = SYSTEMD_SERVICE_TEMPLATE.format(
        working_dir=working_dir,
        pythonpath=working_dir,
        env_file=env_file,
        python_exec=python_exec,
        user=user,
        group=group,
        data_dir=data_dir,
    )
    
    if output_path:
        output = Path(output_path)
        output.write_text(content)
        print(f"Service file written to: {output}")
        
        # Set permissions
        os.chmod(output, 0o644)
        print(f"Permissions set to 644")
    
    return content


def validate_service_file(service_path: str) -> bool:
    """Validate the generated service file using systemd-analyze."""
    import subprocess
    
    try:
        result = subprocess.run(
            ["systemd-analyze", "verify", service_path],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            print("✓ Service file validation passed")
            return True
        else:
            print(f"✗ Validation errors:\n{result.stderr}")
            return False
    except FileNotFoundError:
        print("⚠ systemd-analyze not found, skipping validation")
        return True


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate systemd service file for Prediction Market Arbitrage Scanner"
    )
    parser.add_argument(
        "--working-dir",
        help="Project working directory (default: auto-detect)",
    )
    parser.add_argument(
        "--user",
        help=f"System user (default: {get_default_user()})",
    )
    parser.add_argument(
        "--group",
        help="System group (default: same as user)",
    )
    parser.add_argument(
        "--python",
        default="/usr/bin/python3",
        help="Python executable path (default: /usr/bin/python3)",
    )
    parser.add_argument(
        "--env-file",
        help="Path to environment file",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output path (default: stdout)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate generated file with systemd-analyze",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install to /etc/systemd/system/ (requires sudo)",
    )
    
    args = parser.parse_args()
    
    # Generate output path if installing
    output = args.output
    if args.install and not output:
        output = "/etc/systemd/system/pred-market-arb.service"
    
    content = generate_service_file(
        working_dir=args.working_dir,
        user=args.user,
        group=args.group,
        python_exec=args.python,
        env_file=args.env_file,
        output_path=output,
    )
    
    if not output:
        print(content)
    
    # Validate if requested
    if args.validate and output:
        validate_service_file(output)
    
    # Reload systemd if installing
    if args.install:
        import subprocess
        try:
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            print("✓ Systemd daemon reloaded")
            print("\nTo enable the service:")
            print("  sudo systemctl enable pred-market-arb.service")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to reload systemd: {e}")
            sys.exit(1)
        except FileNotFoundError:
            print("⚠ systemctl not found, skipping daemon-reload")


if __name__ == "__main__":
    main()
