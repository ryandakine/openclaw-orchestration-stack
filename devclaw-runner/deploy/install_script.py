#!/usr/bin/env python3
"""
OpenClaw Arbitrage Hunter - Installation Script

Installs the application with systemd integration.
Creates directories, copies files, and enables systemd services.
"""

import os
import sys
import shutil
import argparse
import subprocess
import getpass
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class InstallConfig:
    """Installation configuration."""
    project_root: Path
    install_user: str
    install_group: str
    python_exec: str
    skip_systemd: bool
    skip_docker: bool
    backup_existing: bool
    create_env: bool


class Installer:
    """Handles the installation process."""
    
    REQUIRED_DIRS = [
        "data",
        "data/audit_logs",
        "data/backups",
        "data/cache",
        "logs",
    ]
    
    REQUIRED_FILES = [
        ".env.example",
        "pyproject.toml",
        "requirements.txt",
    ]
    
    SYSTEMD_FILES = [
        ("systemd/pred-market-arb.service", "/etc/systemd/system/pred-market-arb.service"),
        ("systemd/pred-market-arb.timer", "/etc/systemd/system/pred-market-arb.timer"),
    ]
    
    def __init__(self, config: InstallConfig):
        self.config = config
        self.logger = self._setup_logging()
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def _setup_logging(self):
        """Setup simple logging."""
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        return logging.getLogger(__name__)
    
    def check_prerequisites(self) -> bool:
        """Check that prerequisites are met."""
        self.logger.info("Checking prerequisites...")
        
        # Check Python version
        version = sys.version_info
        if version < (3, 11):
            self.errors.append(f"Python 3.11+ required, found {version.major}.{version.minor}")
            return False
        self.logger.info(f"✓ Python version: {version.major}.{version.minor}.{version.micro}")
        
        # Check if running as root for systemd install
        if os.geteuid() != 0 and not self.config.skip_systemd:
            self.warnings.append("Not running as root. Systemd installation may fail.")
        
        # Check required commands
        for cmd in ["python3", "pip3"]:
            if not shutil.which(cmd):
                self.errors.append(f"Required command not found: {cmd}")
        
        if shutil.which("systemctl"):
            self.logger.info("✓ systemctl available")
        elif not self.config.skip_systemd:
            self.warnings.append("systemctl not found, skipping systemd setup")
            self.config.skip_systemd = True
        
        return len(self.errors) == 0
    
    def create_directories(self) -> bool:
        """Create required directories."""
        self.logger.info("Creating directories...")
        
        for dir_name in self.REQUIRED_DIRS:
            dir_path = self.config.project_root / dir_name
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                # Set ownership if running as root
                if os.geteuid() == 0:
                    import pwd
                    import grp
                    uid = pwd.getpwnam(self.config.install_user).pw_uid
                    gid = grp.getgrnam(self.config.install_group).gr_gid
                    os.chown(dir_path, uid, gid)
                self.logger.info(f"✓ Created: {dir_path}")
            except Exception as e:
                self.errors.append(f"Failed to create {dir_path}: {e}")
                return False
        
        return True
    
    def setup_virtual_environment(self) -> bool:
        """Setup Python virtual environment and install dependencies."""
        self.logger.info("Setting up Python environment...")
        
        venv_path = self.config.project_root / ".venv"
        
        # Create venv if it doesn't exist
        if not venv_path.exists():
            try:
                subprocess.run(
                    [self.config.python_exec, "-m", "venv", str(venv_path)],
                    check=True,
                    capture_output=True,
                )
                self.logger.info(f"✓ Created virtual environment: {venv_path}")
            except subprocess.CalledProcessError as e:
                self.errors.append(f"Failed to create venv: {e}")
                return False
        else:
            self.logger.info(f"✓ Virtual environment exists: {venv_path}")
        
        # Install dependencies
        pip_path = venv_path / "bin" / "pip"
        requirements = self.config.project_root / "requirements.txt"
        
        if requirements.exists():
            try:
                subprocess.run(
                    [str(pip_path), "install", "-r", str(requirements)],
                    check=True,
                    capture_output=True,
                )
                self.logger.info("✓ Installed requirements.txt")
            except subprocess.CalledProcessError as e:
                self.errors.append(f"Failed to install requirements: {e}")
                return False
        
        # Install package in editable mode if pyproject.toml exists
        pyproject = self.config.project_root / "pyproject.toml"
        if pyproject.exists():
            try:
                subprocess.run(
                    [str(pip_path), "install", "-e", str(self.config.project_root)],
                    check=True,
                    capture_output=True,
                )
                self.logger.info("✓ Installed package in editable mode")
            except subprocess.CalledProcessError as e:
                self.warnings.append(f"Failed to install package: {e}")
        
        return True
    
    def create_environment_file(self) -> bool:
        """Create .env file from example if it doesn't exist."""
        if not self.config.create_env:
            return True
        
        env_file = self.config.project_root / ".env"
        env_example = self.config.project_root / ".env.example"
        
        if env_file.exists():
            self.logger.info("✓ .env file exists")
            return True
        
        if not env_example.exists():
            self.warnings.append("No .env.example found, skipping .env creation")
            return True
        
        try:
            shutil.copy(env_example, env_file)
            self.logger.info(f"✓ Created .env from example")
            self.logger.warning("⚠ Please edit .env and configure your API keys!")
        except Exception as e:
            self.errors.append(f"Failed to create .env: {e}")
            return False
        
        return True
    
    def install_systemd_files(self) -> bool:
        """Install systemd service and timer files."""
        if self.config.skip_systemd:
            self.logger.info("Skipping systemd installation")
            return True
        
        self.logger.info("Installing systemd files...")
        
        for src_rel, dest in self.SYSTEMD_FILES:
            src = self.config.project_root / src_rel
            
            if not src.exists():
                # Try to generate it
                self.logger.info(f"Generating {src_rel}...")
                if "service" in src_rel:
                    from systemd_service import generate_service_file
                    generate_service_file(
                        working_dir=str(self.config.project_root),
                        user=self.config.install_user,
                        group=self.config.install_group,
                        output_path=src,
                    )
                else:
                    from systemd_timer import generate_timer_file
                    generate_timer_file(output_path=src)
            
            try:
                shutil.copy(src, dest)
                os.chmod(dest, 0o644)
                self.logger.info(f"✓ Installed: {dest}")
            except PermissionError:
                self.errors.append(f"Permission denied installing {dest}. Run with sudo.")
                return False
            except Exception as e:
                self.errors.append(f"Failed to install {dest}: {e}")
                return False
        
        return True
    
    def enable_systemd_services(self) -> bool:
        """Enable and start systemd services."""
        if self.config.skip_systemd:
            return True
        
        self.logger.info("Enabling systemd services...")
        
        commands = [
            (["systemctl", "daemon-reload"], "Reload systemd"),
            (["systemctl", "enable", "pred-market-arb.timer"], "Enable timer"),
            (["systemctl", "start", "pred-market-arb.timer"], "Start timer"),
        ]
        
        for cmd, desc in commands:
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                self.logger.info(f"✓ {desc}")
            except subprocess.CalledProcessError as e:
                self.errors.append(f"Failed to {desc.lower()}: {e}")
                return False
        
        return True
    
    def verify_installation(self) -> bool:
        """Verify the installation."""
        self.logger.info("Verifying installation...")
        
        # Check Python can import the module
        try:
            python_path = self.config.project_root / ".venv" / "bin" / "python"
            if not python_path.exists():
                python_path = Path(self.config.python_exec)
            
            result = subprocess.run(
                [str(python_path), "-c", "import devclaw_runner.src.prediction_markets.arb_scanner"],
                cwd=str(self.config.project_root),
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(self.config.project_root)},
            )
            if result.returncode == 0:
                self.logger.info("✓ Module imports successfully")
            else:
                self.warnings.append(f"Module import test failed: {result.stderr}")
        except Exception as e:
            self.warnings.append(f"Could not verify module import: {e}")
        
        # Check systemd status
        if not self.config.skip_systemd:
            try:
                result = subprocess.run(
                    ["systemctl", "is-enabled", "pred-market-arb.timer"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    self.logger.info("✓ Timer is enabled")
                else:
                    self.warnings.append("Timer is not enabled")
            except Exception as e:
                self.warnings.append(f"Could not check timer status: {e}")
        
        return True
    
    def print_summary(self):
        """Print installation summary."""
        print("\n" + "=" * 60)
        print("INSTALLATION SUMMARY")
        print("=" * 60)
        
        if self.errors:
            print("\n❌ ERRORS:")
            for error in self.errors:
                print(f"  • {error}")
        
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  • {warning}")
        
        if not self.errors:
            print("\n✅ Installation completed successfully!")
            print(f"\nProject root: {self.config.project_root}")
            print(f"User: {self.config.install_user}")
            
            if not self.config.skip_systemd:
                print("\nSystemd commands:")
                print("  Check timer:  systemctl list-timers pred-market-arb.timer")
                print("  View logs:    journalctl -u pred-market-arb.service -f")
                print("  Run manually: systemctl start pred-market-arb.service")
            
            print("\nNext steps:")
            if self.config.create_env:
                print("  1. Edit .env and configure your API keys")
            print("  2. Run health check: python deploy/health_check.py")
        
        print("=" * 60)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Install OpenClaw Arbitrage Hunter"
    )
    parser.add_argument(
        "--user",
        default=getpass.getuser(),
        help="User to run service as",
    )
    parser.add_argument(
        "--group",
        help="Group to run service as (default: same as user)",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use",
    )
    parser.add_argument(
        "--skip-systemd",
        action="store_true",
        help="Skip systemd installation",
    )
    parser.add_argument(
        "--skip-venv",
        action="store_true",
        help="Skip virtual environment setup",
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Skip Docker setup (always skipped if not available)",
    )
    parser.add_argument(
        "--no-env",
        action="store_true",
        help="Don't create .env file",
    )
    parser.add_argument(
        "--project-root",
        help="Project root directory (default: auto-detect)",
    )
    
    args = parser.parse_args()
    
    # Determine project root
    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        # Auto-detect: go up from deploy/ to project root
        project_root = Path(__file__).resolve().parent.parent.parent
    
    config = InstallConfig(
        project_root=project_root,
        install_user=args.user,
        install_group=args.group or args.user,
        python_exec=args.python,
        skip_systemd=args.skip_systemd,
        skip_docker=args.skip_docker,
        backup_existing=False,
        create_env=not args.no_env,
    )
    
    installer = Installer(config)
    
    # Run installation steps
    success = True
    
    if not installer.check_prerequisites():
        success = False
    
    if success and not installer.create_directories():
        success = False
    
    if success and not args.skip_venv:
        if not installer.setup_virtual_environment():
            success = False
    
    if success:
        installer.create_environment_file()
    
    if success:
        installer.install_systemd_files()
        installer.enable_systemd_services()
    
    installer.verify_installation()
    installer.print_summary()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
