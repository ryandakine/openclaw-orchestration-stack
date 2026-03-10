"""
Command Runner

Execute commands from configuration and aggregate results.
"""

import asyncio
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class CommandStatus(Enum):
    """Status of a command execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class CommandCategory(Enum):
    """Category of command."""
    TEST = "test"
    LINT = "lint"
    TYPECHECK = "typecheck"
    FORMAT = "format"
    BUILD = "build"
    SECURITY_DEPENDENCY = "security_dependency"
    SECURITY_SECRET = "security_secret"
    SECURITY_SAST = "security_sast"


@dataclass
class CommandResult:
    """Result of a single command execution."""
    command: str
    category: CommandCategory
    status: CommandStatus
    return_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    error_message: Optional[str] = None
    workspace: Optional[str] = None  # Track which workspace this command ran in
    
    @property
    def success(self) -> bool:
        """Check if command was successful."""
        return self.status == CommandStatus.SUCCESS and self.return_code == 0
    
    @property
    def failed(self) -> bool:
        """Check if command failed."""
        return self.status in (CommandStatus.FAILED, CommandStatus.TIMEOUT)


@dataclass
class WorkspaceResult:
    """Result of running commands in a workspace."""
    workspace_name: str
    workspace_path: Path
    language: str
    results: list[CommandResult] = field(default_factory=list)
    total_duration_ms: int = 0
    
    @property
    def all_successful(self) -> bool:
        """Check if all commands in workspace were successful."""
        return all(r.success for r in self.results) and len(self.results) > 0
    
    @property
    def failed_count(self) -> int:
        """Count failed commands in workspace."""
        return sum(1 for r in self.results if r.failed)


@dataclass
class RunSummary:
    """Summary of all command executions."""
    total_commands: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    total_duration_ms: int = 0
    results: list[CommandResult] = field(default_factory=list)
    workspace_results: list[WorkspaceResult] = field(default_factory=list)
    
    @property
    def all_successful(self) -> bool:
        """Check if all commands were successful."""
        return self.failed == 0 and self.total_commands > 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_commands == 0:
            return 0.0
        return (self.successful / self.total_commands) * 100
    
    def get_by_category(self, category: CommandCategory) -> list[CommandResult]:
        """Get results filtered by category."""
        return [r for r in self.results if r.category == category]
    
    def get_by_workspace(self, workspace: str) -> list[CommandResult]:
        """Get results filtered by workspace."""
        return [r for r in self.results if r.workspace == workspace]
    
    def get_failed(self) -> list[CommandResult]:
        """Get all failed results."""
        return [r for r in self.results if r.failed]
    
    def get_workspace_summary(self) -> dict[str, dict]:
        """Get summary statistics per workspace."""
        summary = {}
        for ws_result in self.workspace_results:
            summary[ws_result.workspace_name] = {
                "path": str(ws_result.workspace_path),
                "language": ws_result.language,
                "total_commands": len(ws_result.results),
                "successful": sum(1 for r in ws_result.results if r.success),
                "failed": ws_result.failed_count,
                "duration_ms": ws_result.total_duration_ms,
            }
        return summary


class CommandRunner:
    """Runner for executing review commands."""
    
    def __init__(
        self,
        working_dir: Optional[Path] = None,
        timeout_seconds: int = 300,
        env: Optional[dict[str, str]] = None,
    ):
        """
        Initialize the command runner.
        
        Args:
            working_dir: Working directory for commands
            timeout_seconds: Default timeout for commands
            env: Additional environment variables
        """
        self.working_dir = working_dir or Path.cwd()
        self.timeout_seconds = timeout_seconds
        self.env = env or {}
        self._results: list[CommandResult] = []
        self._workspace_results: list[WorkspaceResult] = []
    
    async def run_command(
        self,
        command: str,
        category: CommandCategory,
        timeout: Optional[int] = None,
        workspace: Optional[str] = None,
    ) -> CommandResult:
        """
        Run a single command.
        
        Args:
            command: Command string to execute
            category: Category of the command
            timeout: Override timeout in seconds
            workspace: Optional workspace name this command belongs to
            
        Returns:
            CommandResult with execution details
        """
        import time
        
        timeout = timeout or self.timeout_seconds
        start_time = time.time()
        
        result = CommandResult(
            command=command,
            category=category,
            status=CommandStatus.RUNNING,
            workspace=workspace,
        )
        
        try:
            # Split command safely (handle quoted arguments)
            import shlex
            cmd_parts = shlex.split(command)
            
            # Merge environment
            env = {**self.env}
            
            # Run the command
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
                env={**asyncio.subprocess.os.environ, **env} if env else None,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                
                result.stdout = stdout.decode('utf-8', errors='replace')
                result.stderr = stderr.decode('utf-8', errors='replace')
                result.return_code = process.returncode or 0
                result.status = (
                    CommandStatus.SUCCESS if process.returncode == 0
                    else CommandStatus.FAILED
                )
                
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                result.status = CommandStatus.TIMEOUT
                result.error_message = f"Command timed out after {timeout}s"
                result.return_code = -1
        
        except FileNotFoundError as e:
            result.status = CommandStatus.FAILED
            result.error_message = f"Command not found: {e}"
            result.return_code = 127
        
        except Exception as e:
            result.status = CommandStatus.FAILED
            result.error_message = str(e)
            result.return_code = -1
        
        finally:
            result.duration_ms = int((time.time() - start_time) * 1000)
            self._results.append(result)
        
        return result
    
    async def run_commands(
        self,
        commands: list[str],
        category: CommandCategory,
        stop_on_failure: bool = False,
        workspace: Optional[str] = None,
    ) -> list[CommandResult]:
        """
        Run multiple commands of the same category.
        
        Args:
            commands: List of command strings
            category: Category for all commands
            stop_on_failure: Stop after first failure
            workspace: Optional workspace name these commands belong to
            
        Returns:
            List of CommandResult objects
        """
        results = []
        
        for cmd in commands:
            result = await self.run_command(cmd, category, workspace=workspace)
            results.append(result)
            
            if stop_on_failure and result.failed:
                break
        
        return results
    
    async def run_test_commands(
        self,
        commands: list[str],
        stop_on_failure: bool = False,
        workspace: Optional[str] = None,
    ) -> list[CommandResult]:
        """
        Execute test suite commands.
        
        Args:
            commands: List of test commands
            stop_on_failure: Stop after first failure
            workspace: Optional workspace name
            
        Returns:
            List of CommandResult objects
        """
        return await self.run_commands(
            commands,
            CommandCategory.TEST,
            stop_on_failure,
            workspace=workspace,
        )
    
    async def run_lint_commands(
        self,
        commands: list[str],
        stop_on_failure: bool = False,
        workspace: Optional[str] = None,
    ) -> list[CommandResult]:
        """
        Run linter commands.
        
        Args:
            commands: List of lint commands
            stop_on_failure: Stop after first failure
            workspace: Optional workspace name
            
        Returns:
            List of CommandResult objects
        """
        return await self.run_commands(
            commands,
            CommandCategory.LINT,
            stop_on_failure,
            workspace=workspace,
        )
    
    async def run_security_scans(
        self,
        dependency_scan: list[str] = None,
        secret_scan: list[str] = None,
        sast_scan: list[str] = None,
        stop_on_failure: bool = False,
        workspace: Optional[str] = None,
    ) -> list[CommandResult]:
        """
        Run all security scan commands.
        
        Args:
            dependency_scan: Dependency vulnerability scan commands
            secret_scan: Secret detection commands
            sast_scan: Static analysis security commands
            stop_on_failure: Stop after first failure
            workspace: Optional workspace name
            
        Returns:
            List of CommandResult objects
        """
        results = []
        
        # Dependency scans
        for cmd in (dependency_scan or []):
            result = await self.run_command(
                cmd,
                CommandCategory.SECURITY_DEPENDENCY,
                workspace=workspace,
            )
            results.append(result)
            if stop_on_failure and result.failed:
                return results
        
        # Secret scans
        for cmd in (secret_scan or []):
            result = await self.run_command(
                cmd,
                CommandCategory.SECURITY_SECRET,
                workspace=workspace,
            )
            results.append(result)
            if stop_on_failure and result.failed:
                return results
        
        # SAST scans
        for cmd in (sast_scan or []):
            result = await self.run_command(
                cmd,
                CommandCategory.SECURITY_SAST,
                workspace=workspace,
            )
            results.append(result)
            if stop_on_failure and result.failed:
                return results
        
        return results
    
    async def run_all_from_config(
        self,
        config: 'ReviewConfig',  # type: ignore
        skip_tests: bool = False,
        skip_lint: bool = False,
        skip_security: bool = False,
        skip_typecheck: bool = False,
    ) -> RunSummary:
        """
        Run all commands from a ReviewConfig.
        
        Args:
            config: ReviewConfig with commands
            skip_tests: Skip test commands
            skip_lint: Skip lint commands
            skip_security: Skip security scans
            skip_typecheck: Skip typecheck commands
            
        Returns:
            RunSummary with all results
        """
        all_results = []
        
        # Build commands
        if config.commands.build:
            results = await self.run_commands(
                config.commands.build,
                CommandCategory.BUILD,
            )
            all_results.extend(results)
        
        # Test commands
        if not skip_tests and config.commands.test:
            results = await self.run_test_commands(config.commands.test)
            all_results.extend(results)
        
        # Lint commands
        if not skip_lint and config.commands.lint:
            results = await self.run_lint_commands(config.commands.lint)
            all_results.extend(results)
        
        # Typecheck commands
        if not skip_typecheck and config.commands.typecheck:
            results = await self.run_commands(
                config.commands.typecheck,
                CommandCategory.TYPECHECK,
            )
            all_results.extend(results)
        
        # Format check commands
        if config.commands.format:
            results = await self.run_commands(
                config.commands.format,
                CommandCategory.FORMAT,
            )
            all_results.extend(results)
        
        # Security scans
        if not skip_security:
            results = await self.run_security_scans(
                dependency_scan=config.security.dependency_scan,
                secret_scan=config.security.secret_scan,
                sast_scan=config.security.sast_scan,
            )
            all_results.extend(results)
        
        return self._aggregate_results(all_results)
    
    def _aggregate_results(self, results: list[CommandResult]) -> RunSummary:
        """Aggregate results into a summary."""
        summary = RunSummary(
            total_commands=len(results),
            results=results,
            workspace_results=self._workspace_results,
        )
        
        for result in results:
            if result.status == CommandStatus.SUCCESS:
                summary.successful += 1
            elif result.status in (CommandStatus.FAILED, CommandStatus.TIMEOUT):
                summary.failed += 1
            elif result.status == CommandStatus.SKIPPED:
                summary.skipped += 1
            
            summary.total_duration_ms += result.duration_ms
        
        return summary
    
    def get_summary(self) -> RunSummary:
        """Get summary of all executed commands."""
        return self._aggregate_results(self._results)
    
    def clear_results(self) -> None:
        """Clear stored results."""
        self._results = []
        self._workspace_results = []
    
    # ============================================================================
    # MONOREPO WORKSPACE SUPPORT
    # ============================================================================
    
    async def run_workspace_commands(
        self,
        workspace_name: str,
        workspace_path: Path,
        language: str,
        commands: dict[str, list[str]],
        skip_tests: bool = False,
        skip_lint: bool = False,
        skip_security: bool = False,
        skip_typecheck: bool = False,
        skip_format: bool = False,
        skip_build: bool = False,
    ) -> WorkspaceResult:
        """
        Run commands for a specific workspace.
        
        Args:
            workspace_name: Name of the workspace
            workspace_path: Path to the workspace directory
            language: Programming language of the workspace
            commands: Dictionary of command categories to command lists
            skip_tests: Skip test commands
            skip_lint: Skip lint commands
            skip_security: Skip security commands
            skip_typecheck: Skip typecheck commands
            skip_format: Skip format commands
            skip_build: Skip build commands
            
        Returns:
            WorkspaceResult with all execution results
        """
        import time
        start_time = time.time()
        
        # Create a runner for this workspace
        workspace_runner = CommandRunner(
            working_dir=workspace_path,
            timeout_seconds=self.timeout_seconds,
            env=self.env,
        )
        
        all_results = []
        
        # Build commands
        if not skip_build and commands.get("build"):
            results = await workspace_runner.run_commands(
                commands["build"],
                CommandCategory.BUILD,
                workspace=workspace_name,
            )
            all_results.extend(results)
        
        # Test commands
        if not skip_tests and commands.get("test"):
            results = await workspace_runner.run_test_commands(
                commands["test"],
                workspace=workspace_name,
            )
            all_results.extend(results)
        
        # Lint commands
        if not skip_lint and commands.get("lint"):
            results = await workspace_runner.run_lint_commands(
                commands["lint"],
                workspace=workspace_name,
            )
            all_results.extend(results)
        
        # Typecheck commands
        if not skip_typecheck and commands.get("typecheck"):
            results = await workspace_runner.run_commands(
                commands["typecheck"],
                CommandCategory.TYPECHECK,
                workspace=workspace_name,
            )
            all_results.extend(results)
        
        # Format commands
        if not skip_format and commands.get("format"):
            results = await workspace_runner.run_commands(
                commands["format"],
                CommandCategory.FORMAT,
                workspace=workspace_name,
            )
            all_results.extend(results)
        
        # Security commands
        if not skip_security and commands.get("security"):
            results = await workspace_runner.run_security_scans(
                dependency_scan=commands.get("security", []),
                workspace=workspace_name,
            )
            all_results.extend(results)
        
        # Create workspace result
        workspace_result = WorkspaceResult(
            workspace_name=workspace_name,
            workspace_path=workspace_path,
            language=language,
            results=all_results,
            total_duration_ms=int((time.time() - start_time) * 1000),
        )
        
        self._workspace_results.append(workspace_result)
        self._results.extend(all_results)
        
        return workspace_result
    
    async def run_all_workspaces(
        self,
        workspaces: dict[str, dict],
        skip_tests: bool = False,
        skip_lint: bool = False,
        skip_security: bool = False,
        skip_typecheck: bool = False,
        skip_format: bool = False,
        skip_build: bool = False,
        parallel: bool = True,
    ) -> RunSummary:
        """
        Run commands for all workspaces.
        
        Args:
            workspaces: Dictionary mapping workspace names to workspace config dicts
                       Each dict should have: path, language, commands
            skip_tests: Skip test commands
            skip_lint: Skip lint commands
            skip_security: Skip security commands
            skip_typecheck: Skip typecheck commands
            skip_format: Skip format commands
            skip_build: Skip build commands
            parallel: Whether to run workspaces in parallel
            
        Returns:
            RunSummary with all workspace results
        """
        if parallel:
            # Run all workspaces in parallel
            tasks = []
            for name, config in workspaces.items():
                task = self.run_workspace_commands(
                    workspace_name=name,
                    workspace_path=Path(config["path"]),
                    language=config.get("language", "unknown"),
                    commands=config.get("commands", {}),
                    skip_tests=skip_tests,
                    skip_lint=skip_lint,
                    skip_security=skip_security,
                    skip_typecheck=skip_typecheck,
                    skip_format=skip_format,
                    skip_build=skip_build,
                )
                tasks.append(task)
            
            await asyncio.gather(*tasks)
        else:
            # Run workspaces sequentially
            for name, config in workspaces.items():
                await self.run_workspace_commands(
                    workspace_name=name,
                    workspace_path=Path(config["path"]),
                    language=config.get("language", "unknown"),
                    commands=config.get("commands", {}),
                    skip_tests=skip_tests,
                    skip_lint=skip_lint,
                    skip_security=skip_security,
                    skip_typecheck=skip_typecheck,
                    skip_format=skip_format,
                    skip_build=skip_build,
                )
        
        return self._aggregate_results(self._results)


def aggregate_workspace_results(workspace_results: list[WorkspaceResult]) -> RunSummary:
    """
    Aggregate results from multiple workspaces into a single summary.
    
    Args:
        workspace_results: List of WorkspaceResult objects
        
    Returns:
        RunSummary with combined results
    """
    all_results = []
    total_duration = 0
    
    for ws_result in workspace_results:
        all_results.extend(ws_result.results)
        total_duration += ws_result.total_duration_ms
    
    summary = RunSummary(
        total_commands=len(all_results),
        results=all_results,
        workspace_results=workspace_results,
        total_duration_ms=total_duration,
    )
    
    for result in all_results:
        if result.status == CommandStatus.SUCCESS:
            summary.successful += 1
        elif result.status in (CommandStatus.FAILED, CommandStatus.TIMEOUT):
            summary.failed += 1
        elif result.status == CommandStatus.SKIPPED:
            summary.skipped += 1
    
    return summary


def detect_changed_workspaces(
    repo_path: Path | str,
    workspaces: dict[str, dict],
    changed_files: list[str],
    include_dependents: bool = True,
) -> dict[str, dict]:
    """
    Detect which workspaces have changed based on file changes.
    
    This enables selective testing - only test workspaces that have
    actually changed or depend on changed workspaces.
    
    Args:
        repo_path: Path to repository root
        workspaces: Dictionary mapping workspace names to workspace configs
        changed_files: List of file paths that have changed (relative to repo root)
        include_dependents: Whether to also include workspaces that depend on
                          changed workspaces (requires dependency info)
        
    Returns:
        Filtered workspaces dictionary containing only changed workspaces
    """
    repo_path = Path(repo_path).resolve()
    changed_workspaces = {}
    
    for name, config in workspaces.items():
        workspace_path = Path(config["path"])
        if not workspace_path.is_absolute():
            workspace_path = repo_path / workspace_path
        
        # Normalize workspace path
        workspace_path = workspace_path.resolve()
        
        # Check if any changed file is in this workspace
        for changed_file in changed_files:
            changed_path = repo_path / changed_file
            changed_path = changed_path.resolve()
            
            # Check if file is in workspace or subdirectory
            try:
                changed_path.relative_to(workspace_path)
                # If we get here, changed_file is inside workspace
                changed_workspaces[name] = config
                break
            except ValueError:
                # File is not in this workspace
                pass
    
    # Include dependents if requested (simplified implementation)
    if include_dependents and changed_workspaces:
        # For a full implementation, we'd parse dependency information
        # from package.json, Cargo.toml, pyproject.toml, etc.
        # For now, we include shared libs that might be depended upon
        for name, config in workspaces.items():
            if name not in changed_workspaces:
                path_str = str(config.get("path", "")).lower()
                # Heuristic: shared/libs directories are likely dependencies
                if any(keyword in path_str for keyword in ["shared", "lib", "common", "core", "utils"]):
                    changed_workspaces[name] = config
    
    return changed_workspaces


def format_summary(summary: RunSummary) -> str:
    """
    Format a RunSummary as a human-readable string.
    
    Args:
        summary: RunSummary to format
        
    Returns:
        Formatted string
    """
    lines = [
        "═" * 60,
        "                    COMMAND EXECUTION SUMMARY",
        "═" * 60,
        "",
        f"  Total Commands: {summary.total_commands}",
        f"  Successful:     {summary.successful} ✓",
        f"  Failed:         {summary.failed} ✗",
        f"  Skipped:        {summary.skipped} ⊘",
        f"  Success Rate:   {summary.success_rate:.1f}%",
        f"  Total Time:     {summary.total_duration_ms / 1000:.2f}s",
        "",
    ]
    
    # Add workspace summary if available
    if summary.workspace_results:
        lines.extend([
            "─" * 60,
            "                        WORKSPACE SUMMARY",
            "─" * 60,
            "",
        ])
        
        for ws_result in summary.workspace_results:
            status = "✓" if ws_result.all_successful else "✗"
            lines.append(
                f"  [{status}] {ws_result.workspace_name} ({ws_result.language}) - "
                f"{len(ws_result.results)} commands, "
                f"{ws_result.failed_count} failed"
            )
        lines.append("")
    
    if summary.failed > 0:
        lines.extend([
            "─" * 60,
            "                         FAILED COMMANDS",
            "─" * 60,
            "",
        ])
        
        for result in summary.get_failed():
            workspace_info = f" [{result.workspace}]" if result.workspace else ""
            lines.extend([
                f"  [{result.category.value}]{workspace_info} {result.command}",
                f"    Status: {result.status.value}",
                f"    Return Code: {result.return_code}",
            ])
            if result.error_message:
                lines.append(f"    Error: {result.error_message}")
            if result.stderr:
                stderr_preview = result.stderr[:200].replace("\n", " ")
                lines.append(f"    Stderr: {stderr_preview}...")
            lines.append("")
    
    lines.append("═" * 60)
    
    if summary.all_successful:
        lines.append("                        ALL CHECKS PASSED ✓")
    else:
        lines.append("                         SOME CHECKS FAILED ✗")
    lines.append("═" * 60)
    
    return "\n".join(lines)


def format_workspace_summary(summary: RunSummary) -> str:
    """
    Format a workspace-focused summary.
    
    Args:
        summary: RunSummary with workspace results
        
    Returns:
        Formatted string focused on workspace breakdown
    """
    lines = [
        "═" * 70,
        "                    MONOREPO WORKSPACE RESULTS",
        "═" * 70,
        "",
    ]
    
    if not summary.workspace_results:
        lines.append("  No workspace results available.")
        lines.append("")
    else:
        for ws_result in summary.workspace_results:
            status_icon = "✓" if ws_result.all_successful else "✗"
            lines.extend([
                f"  {status_icon} {ws_result.workspace_name}",
                f"    Path: {ws_result.workspace_path}",
                f"    Language: {ws_result.language}",
                f"    Commands: {len(ws_result.results)} | "
                f"Passed: {len(ws_result.results) - ws_result.failed_count} | "
                f"Failed: {ws_result.failed_count}",
                f"    Duration: {ws_result.total_duration_ms / 1000:.2f}s",
                "",
            ])
            
            # Show failed commands per workspace
            failed = [r for r in ws_result.results if r.failed]
            if failed:
                lines.append("    Failed commands:")
                for result in failed:
                    lines.append(f"      - [{result.category.value}] {result.command}")
                lines.append("")
    
    lines.extend([
        "─" * 70,
        f"  Overall: {summary.successful}/{summary.total_commands} commands passed "
        f"({summary.success_rate:.1f}%)",
        "═" * 70,
    ])
    
    return "\n".join(lines)
