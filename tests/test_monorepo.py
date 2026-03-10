"""
Tests for monorepo support - Mixed language workspace detection and execution
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from shared.config.language_detector import (
    Language,
    detect_monorepo_structure,
    get_workspace_packages,
    detect_languages_per_directory,
)
from shared.config.command_runner import (
    CommandRunner,
    CommandStatus,
    CommandCategory,
    WorkspaceResult,
    aggregate_workspace_results,
    detect_changed_workspaces,
    format_workspace_summary,
)


class TestWorkspaceDetection:
    """Tests for workspace detection in monorepos."""
    
    def test_detect_npm_workspaces(self, tmp_path):
        """Test detecting npm workspaces."""
        # Create root package.json with workspaces
        (tmp_path / "package.json").write_text('''
{
    "name": "monorepo-root",
    "workspaces": ["packages/*"]
}
''')
        # Create workspace packages
        pkg1 = tmp_path / "packages" / "frontend"
        pkg1.mkdir(parents=True)
        (pkg1 / "package.json").write_text('{"name": "frontend", "version": "1.0.0"}')
        
        pkg2 = tmp_path / "packages" / "backend"
        pkg2.mkdir(parents=True)
        (pkg2 / "package.json").write_text('{"name": "backend", "version": "1.0.0"}')
        
        result = detect_monorepo_structure(tmp_path)
        
        assert result.is_monorepo is True
        assert result.workspace_type == "npm"
        assert "frontend" in result.packages
        assert "backend" in result.packages
        assert result.language_per_package["frontend"] == Language.NODE
        assert result.language_per_package["backend"] == Language.NODE
    
    def test_detect_cargo_workspace(self, tmp_path):
        """Test detecting Cargo workspace."""
        # Create root Cargo.toml with workspace
        (tmp_path / "Cargo.toml").write_text('''
[workspace]
members = ["apps/frontend", "apps/backend"]
''')
        # Create member directories
        (tmp_path / "apps" / "frontend").mkdir(parents=True)
        (tmp_path / "apps" / "backend").mkdir(parents=True)
        
        result = detect_monorepo_structure(tmp_path)
        
        assert result.is_monorepo is True
        assert result.workspace_type == "cargo"
    
    def test_get_workspace_packages_npm(self, tmp_path):
        """Test getting workspace packages for npm."""
        (tmp_path / "package.json").write_text('''
{
    "name": "monorepo",
    "workspaces": ["packages/*"]
}
''')
        pkg1 = tmp_path / "packages" / "app1"
        pkg1.mkdir(parents=True)
        (pkg1 / "package.json").write_text('{"name": "@myorg/app1"}')
        
        packages = get_workspace_packages(tmp_path)
        
        assert "@myorg/app1" in packages
        assert packages["@myorg/app1"]["language"] == Language.NODE
        assert packages["@myorg/app1"]["workspace_type"] == "npm"
    
    def test_get_workspace_packages_cargo(self, tmp_path):
        """Test getting workspace packages for Cargo."""
        (tmp_path / "Cargo.toml").write_text('''
[workspace]
members = ["crates/lib1", "crates/lib2"]
''')
        (tmp_path / "crates" / "lib1").mkdir(parents=True)
        (tmp_path / "crates" / "lib1" / "Cargo.toml").write_text('''
[package]
name = "my-lib"
version = "0.1.0"
''')
        (tmp_path / "crates" / "lib2").mkdir(parents=True)
        
        packages = get_workspace_packages(tmp_path)
        
        assert "my-lib" in packages
        assert packages["my-lib"]["language"] == Language.RUST
        assert packages["my-lib"]["workspace_type"] == "cargo"
    
    def test_detect_languages_per_directory(self, tmp_path):
        """Test detecting languages per directory."""
        # Create mixed structure
        apps = tmp_path / "apps"
        apps.mkdir()
        
        frontend = apps / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text('{"name": "frontend"}')
        
        backend = apps / "backend"
        backend.mkdir()
        (backend / "requirements.txt").write_text("flask\n")
        
        libs = tmp_path / "libs"
        libs.mkdir()
        
        shared = libs / "shared"
        shared.mkdir()
        (shared / "Cargo.toml").write_text("[package]\nname = \"shared\"")
        
        dir_languages = detect_languages_per_directory(tmp_path)
        
        assert dir_languages.get(frontend) == Language.NODE
        assert dir_languages.get(backend) == Language.PYTHON
        assert dir_languages.get(shared) == Language.RUST
    
    def test_detect_languages_per_directory_empty(self, tmp_path):
        """Test detecting languages in empty directory."""
        dir_languages = detect_languages_per_directory(tmp_path)
        assert dir_languages == {}


class TestMixedLanguageExecution:
    """Tests for mixed language command execution."""
    
    @pytest.fixture
    def runner(self, tmp_path):
        """Create a CommandRunner with temp working dir."""
        return CommandRunner(working_dir=tmp_path)
    
    @pytest.mark.asyncio
    async def test_run_workspace_commands(self, tmp_path, runner):
        """Test running commands for a specific workspace."""
        workspace_path = tmp_path / "workspace1"
        workspace_path.mkdir()
        
        result = await runner.run_workspace_commands(
            workspace_name="test-workspace",
            workspace_path=workspace_path,
            language="python",
            commands={
                "test": ["echo 'test passed'"],
            },
        )
        
        assert result.workspace_name == "test-workspace"
        assert result.workspace_path == workspace_path
        assert result.language == "python"
        assert len(result.results) == 1
        assert result.results[0].success is True
        assert "test passed" in result.results[0].stdout
    
    @pytest.mark.asyncio
    async def test_run_workspace_commands_with_failures(self, tmp_path, runner):
        """Test running workspace commands with some failures."""
        workspace_path = tmp_path / "workspace1"
        workspace_path.mkdir()
        
        result = await runner.run_workspace_commands(
            workspace_name="failing-workspace",
            workspace_path=workspace_path,
            language="python",
            commands={
                "test": ["echo 'test passed'", "exit 1"],
            },
        )
        
        assert result.workspace_name == "failing-workspace"
        assert len(result.results) == 2
        assert result.results[0].success is True
        assert result.results[1].failed is True
        assert result.all_successful is False
    
    @pytest.mark.asyncio
    async def test_run_all_workspaces(self, tmp_path):
        """Test running commands for all workspaces."""
        # Create workspace directories
        ws1 = tmp_path / "frontend"
        ws1.mkdir()
        ws2 = tmp_path / "backend"
        ws2.mkdir()
        
        runner = CommandRunner(working_dir=tmp_path)
        
        workspaces = {
            "frontend": {
                "path": str(ws1),
                "language": "node",
                "commands": {"test": ["echo 'frontend test'"]},
            },
            "backend": {
                "path": str(ws2),
                "language": "python",
                "commands": {"test": ["echo 'backend test'"]},
            },
        }
        
        summary = await runner.run_all_workspaces(
            workspaces,
            parallel=False,  # Sequential for predictable tests
        )
        
        assert summary.total_commands == 2
        assert summary.successful == 2
        assert len(summary.workspace_results) == 2
        
        workspace_names = [ws.workspace_name for ws in summary.workspace_results]
        assert "frontend" in workspace_names
        assert "backend" in workspace_names
    
    @pytest.mark.asyncio
    async def test_run_all_workspaces_parallel(self, tmp_path):
        """Test running workspaces in parallel."""
        ws1 = tmp_path / "ws1"
        ws1.mkdir()
        ws2 = tmp_path / "ws2"
        ws2.mkdir()
        
        runner = CommandRunner(working_dir=tmp_path)
        
        workspaces = {
            "ws1": {
                "path": str(ws1),
                "language": "python",
                "commands": {"test": ["echo 'ws1'"]},
            },
            "ws2": {
                "path": str(ws2),
                "language": "python",
                "commands": {"test": ["echo 'ws2'"]},
            },
        }
        
        summary = await runner.run_all_workspaces(
            workspaces,
            parallel=True,
        )
        
        assert summary.total_commands == 2
        assert summary.successful == 2


class TestWorkspaceResultAggregation:
    """Tests for aggregating workspace results."""
    
    def test_aggregate_workspace_results(self):
        """Test aggregating multiple workspace results."""
        from shared.config.command_runner import CommandResult
        
        ws1 = WorkspaceResult(
            workspace_name="frontend",
            workspace_path=Path("/frontend"),
            language="node",
            results=[
                CommandResult("echo test", CommandCategory.TEST, CommandStatus.SUCCESS),
            ],
            total_duration_ms=100,
        )
        
        ws2 = WorkspaceResult(
            workspace_name="backend",
            workspace_path=Path("/backend"),
            language="python",
            results=[
                CommandResult("pytest", CommandCategory.TEST, CommandStatus.SUCCESS),
                CommandResult("flake8", CommandCategory.LINT, CommandStatus.FAILED),
            ],
            total_duration_ms=200,
        )
        
        summary = aggregate_workspace_results([ws1, ws2])
        
        assert summary.total_commands == 3
        assert summary.successful == 2
        assert summary.failed == 1
        assert summary.total_duration_ms == 300
        assert len(summary.workspace_results) == 2
    
    def test_aggregate_empty_results(self):
        """Test aggregating empty results."""
        summary = aggregate_workspace_results([])
        
        assert summary.total_commands == 0
        assert summary.successful == 0
        assert summary.failed == 0
        assert summary.success_rate == 0.0


class TestSelectiveTesting:
    """Tests for selective testing based on changed files."""
    
    def test_detect_changed_workspaces_single(self, tmp_path):
        """Test detecting single changed workspace."""
        workspaces = {
            "frontend": {"path": tmp_path / "apps" / "frontend"},
            "backend": {"path": tmp_path / "apps" / "backend"},
        }
        
        # Create directories
        workspaces["frontend"]["path"].mkdir(parents=True)
        workspaces["backend"]["path"].mkdir(parents=True)
        
        changed_files = ["apps/frontend/src/index.js"]
        
        result = detect_changed_workspaces(tmp_path, workspaces, changed_files)
        
        assert "frontend" in result
        assert "backend" not in result
    
    def test_detect_changed_workspaces_multiple(self, tmp_path):
        """Test detecting multiple changed workspaces."""
        workspaces = {
            "frontend": {"path": tmp_path / "apps" / "frontend"},
            "backend": {"path": tmp_path / "apps" / "backend"},
            "shared": {"path": tmp_path / "libs" / "shared"},
        }
        
        for ws in workspaces.values():
            ws["path"].mkdir(parents=True)
        
        changed_files = [
            "apps/frontend/src/index.js",
            "apps/backend/main.py",
        ]
        
        # Without including dependents
        result = detect_changed_workspaces(tmp_path, workspaces, changed_files, include_dependents=False)
        
        assert "frontend" in result
        assert "backend" in result
        assert "shared" not in result
        
        # With including dependents, shared should be included because it's a shared lib
        result_with_deps = detect_changed_workspaces(tmp_path, workspaces, changed_files, include_dependents=True)
        assert "shared" in result_with_deps
    
    def test_detect_changed_workspaces_with_shared_libs(self, tmp_path):
        """Test that shared libs are included when include_dependents is True."""
        workspaces = {
            "frontend": {"path": tmp_path / "apps" / "frontend"},
            "shared": {"path": tmp_path / "libs" / "shared"},
        }
        
        for ws in workspaces.values():
            ws["path"].mkdir(parents=True)
        
        changed_files = ["apps/frontend/src/index.js"]
        
        result = detect_changed_workspaces(
            tmp_path, workspaces, changed_files, include_dependents=True
        )
        
        # Both frontend and shared should be included
        assert "frontend" in result
        assert "shared" in result  # Included because it's a shared lib
    
    def test_detect_changed_workspaces_no_dependents(self, tmp_path):
        """Test without including dependents."""
        workspaces = {
            "frontend": {"path": tmp_path / "apps" / "frontend"},
            "shared": {"path": tmp_path / "libs" / "shared"},
        }
        
        for ws in workspaces.values():
            ws["path"].mkdir(parents=True)
        
        changed_files = ["apps/frontend/src/index.js"]
        
        result = detect_changed_workspaces(
            tmp_path, workspaces, changed_files, include_dependents=False
        )
        
        # Only frontend should be included
        assert "frontend" in result
        assert "shared" not in result
    
    def test_detect_changed_workspaces_nested(self, tmp_path):
        """Test detecting changes in nested directories."""
        workspaces = {
            "app": {"path": tmp_path / "packages" / "myapp"},
        }
        workspaces["app"]["path"].mkdir(parents=True)
        
        changed_files = [
            "packages/myapp/src/components/Button.tsx",
            "packages/myapp/src/utils/helpers.ts",
        ]
        
        result = detect_changed_workspaces(tmp_path, workspaces, changed_files)
        
        assert "app" in result


class TestWorkspaceFormatting:
    """Tests for workspace result formatting."""
    
    def test_format_workspace_summary(self):
        """Test formatting workspace summary."""
        from shared.config.command_runner import CommandResult
        
        ws1 = WorkspaceResult(
            workspace_name="frontend",
            workspace_path=Path("/frontend"),
            language="node",
            results=[
                CommandResult("npm test", CommandCategory.TEST, CommandStatus.SUCCESS),
            ],
            total_duration_ms=1500,
        )
        
        ws2 = WorkspaceResult(
            workspace_name="backend",
            workspace_path=Path("/backend"),
            language="python",
            results=[
                CommandResult("pytest", CommandCategory.TEST, CommandStatus.FAILED),
            ],
            total_duration_ms=2500,
        )
        
        summary = aggregate_workspace_results([ws1, ws2])
        formatted = format_workspace_summary(summary)
        
        assert "MONOREPO WORKSPACE RESULTS" in formatted
        assert "frontend" in formatted
        assert "backend" in formatted
        assert "node" in formatted
        assert "python" in formatted
        assert "1.50s" in formatted or "1500" in formatted
    
    def test_format_workspace_summary_empty(self):
        """Test formatting empty workspace summary."""
        summary = aggregate_workspace_results([])
        formatted = format_workspace_summary(summary)
        
        assert "No workspace results available" in formatted


class TestWorkspaceResultClass:
    """Tests for WorkspaceResult dataclass."""
    
    def test_workspace_result_success(self):
        """Test all_successful property."""
        from shared.config.command_runner import CommandResult
        
        ws = WorkspaceResult(
            workspace_name="test",
            workspace_path=Path("/test"),
            language="python",
            results=[
                CommandResult("cmd1", CommandCategory.TEST, CommandStatus.SUCCESS),
                CommandResult("cmd2", CommandCategory.LINT, CommandStatus.SUCCESS),
            ],
        )
        
        assert ws.all_successful is True
        assert ws.failed_count == 0
    
    def test_workspace_result_failure(self):
        """Test failure detection."""
        from shared.config.command_runner import CommandResult
        
        ws = WorkspaceResult(
            workspace_name="test",
            workspace_path=Path("/test"),
            language="python",
            results=[
                CommandResult("cmd1", CommandCategory.TEST, CommandStatus.SUCCESS),
                CommandResult("cmd2", CommandCategory.LINT, CommandStatus.FAILED),
            ],
        )
        
        assert ws.all_successful is False
        assert ws.failed_count == 1
    
    def test_workspace_result_empty(self):
        """Test empty workspace result."""
        ws = WorkspaceResult(
            workspace_name="test",
            workspace_path=Path("/test"),
            language="python",
            results=[],
        )
        
        assert ws.all_successful is False  # No commands ran
        assert ws.failed_count == 0


class TestRunSummaryWorkspaceMethods:
    """Tests for RunSummary workspace-related methods."""
    
    def test_get_by_workspace(self):
        """Test filtering results by workspace."""
        from shared.config.command_runner import CommandResult, RunSummary
        
        summary = RunSummary(
            results=[
                CommandResult("cmd1", CommandCategory.TEST, CommandStatus.SUCCESS, workspace="ws1"),
                CommandResult("cmd2", CommandCategory.TEST, CommandStatus.SUCCESS, workspace="ws2"),
                CommandResult("cmd3", CommandCategory.LINT, CommandStatus.FAILED, workspace="ws1"),
            ],
        )
        
        ws1_results = summary.get_by_workspace("ws1")
        assert len(ws1_results) == 2
        assert all(r.workspace == "ws1" for r in ws1_results)
        
        ws2_results = summary.get_by_workspace("ws2")
        assert len(ws2_results) == 1
    
    def test_get_workspace_summary(self):
        """Test getting workspace summary statistics."""
        from shared.config.command_runner import CommandResult, RunSummary
        
        ws1 = WorkspaceResult(
            workspace_name="frontend",
            workspace_path=Path("/frontend"),
            language="node",
            results=[
                CommandResult("cmd1", CommandCategory.TEST, CommandStatus.SUCCESS),
            ],
            total_duration_ms=100,
        )
        
        ws2 = WorkspaceResult(
            workspace_name="backend",
            workspace_path=Path("/backend"),
            language="python",
            results=[
                CommandResult("cmd2", CommandCategory.TEST, CommandStatus.FAILED),
            ],
            total_duration_ms=200,
        )
        
        summary = RunSummary(workspace_results=[ws1, ws2])
        ws_summary = summary.get_workspace_summary()
        
        assert "frontend" in ws_summary
        assert "backend" in ws_summary
        assert ws_summary["frontend"]["language"] == "node"
        assert ws_summary["backend"]["failed"] == 1


class TestMixedMonorepoIntegration:
    """Integration tests for mixed monorepo support."""
    
    @pytest.mark.asyncio
    async def test_full_monorepo_workflow(self, tmp_path):
        """Test full workflow: detection -> selective testing -> execution."""
        # Create a mixed monorepo structure
        apps = tmp_path / "apps"
        apps.mkdir()
        
        frontend = apps / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text('{"name": "frontend"}')
        
        backend = apps / "backend"
        backend.mkdir()
        (backend / "requirements.txt").write_text("flask\n")
        
        shared = tmp_path / "libs" / "shared"
        shared.mkdir(parents=True)
        (shared / "Cargo.toml").write_text("[package]\nname = \"shared\"")
        
        # Step 1: Detect workspaces
        workspaces = {
            "frontend": {
                "path": frontend,
                "language": "node",
                "commands": {"test": ["echo 'frontend-test'"]},
            },
            "backend": {
                "path": backend,
                "language": "python",
                "commands": {"test": ["echo 'backend-test'"]},
            },
            "shared": {
                "path": shared,
                "language": "rust",
                "commands": {"test": ["echo 'shared-test'"]},
            },
        }
        
        # Step 2: Detect changed workspaces
        changed_files = ["apps/frontend/src/index.js"]
        changed = detect_changed_workspaces(tmp_path, workspaces, changed_files)
        
        # Should include frontend and shared (as dependent)
        assert "frontend" in changed
        assert "shared" in changed
        
        # Step 3: Run commands for changed workspaces
        runner = CommandRunner(working_dir=tmp_path)
        summary = await runner.run_all_workspaces(changed, parallel=False)
        
        assert summary.total_commands == 2  # frontend + shared
        assert summary.successful == 2
    
    @pytest.mark.asyncio
    async def test_monorepo_with_failures(self, tmp_path):
        """Test monorepo with some failing workspaces."""
        ws1 = tmp_path / "good"
        ws1.mkdir()
        ws2 = tmp_path / "bad"
        ws2.mkdir()
        
        workspaces = {
            "good": {
                "path": str(ws1),
                "language": "python",
                "commands": {"test": ["echo 'good'"]},
            },
            "bad": {
                "path": str(ws2),
                "language": "python",
                "commands": {"test": ["exit 1"]},
            },
        }
        
        runner = CommandRunner(working_dir=tmp_path)
        summary = await runner.run_all_workspaces(workspaces, parallel=False)
        
        assert summary.total_commands == 2
        assert summary.successful == 1
        assert summary.failed == 1
        assert summary.all_successful is False
