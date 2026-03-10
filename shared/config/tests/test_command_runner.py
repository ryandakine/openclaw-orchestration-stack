"""
Tests for command_runner.py - Execute commands from config
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from shared.config.command_runner import (
    CommandStatus,
    CommandCategory,
    CommandResult,
    RunSummary,
    CommandRunner,
    format_summary,
)


class TestCommandResult:
    """Tests for CommandResult dataclass."""
    
    def test_success_property_true(self):
        """Test success property when command succeeds."""
        result = CommandResult(
            command="echo hello",
            category=CommandCategory.TEST,
            status=CommandStatus.SUCCESS,
            return_code=0,
        )
        assert result.success is True
        assert result.failed is False
    
    def test_success_property_false_on_failure(self):
        """Test success property when command fails."""
        result = CommandResult(
            command="false",
            category=CommandCategory.TEST,
            status=CommandStatus.FAILED,
            return_code=1,
        )
        assert result.success is False
        assert result.failed is True
    
    def test_failed_property_on_timeout(self):
        """Test failed property when command times out."""
        result = CommandResult(
            command="sleep 100",
            category=CommandCategory.TEST,
            status=CommandStatus.TIMEOUT,
            return_code=-1,
        )
        assert result.failed is True
        assert result.success is False
    
    def test_failed_property_on_pending(self):
        """Test failed property when command is pending."""
        result = CommandResult(
            command="echo hello",
            category=CommandCategory.TEST,
            status=CommandStatus.PENDING,
        )
        assert result.failed is False
        assert result.success is False  # Not yet successful


class TestRunSummary:
    """Tests for RunSummary dataclass."""
    
    def test_all_successful_true(self):
        """Test all_successful when all pass."""
        summary = RunSummary(
            total_commands=2,
            successful=2,
            failed=0,
            results=[
                CommandResult("cmd1", CommandCategory.TEST, CommandStatus.SUCCESS),
                CommandResult("cmd2", CommandCategory.TEST, CommandStatus.SUCCESS),
            ],
        )
        assert summary.all_successful is True
    
    def test_all_successful_false(self):
        """Test all_successful when some fail."""
        summary = RunSummary(
            total_commands=2,
            successful=1,
            failed=1,
            results=[
                CommandResult("cmd1", CommandCategory.TEST, CommandStatus.SUCCESS),
                CommandResult("cmd2", CommandCategory.TEST, CommandStatus.FAILED),
            ],
        )
        assert summary.all_successful is False
    
    def test_all_successful_empty(self):
        """Test all_successful when no commands."""
        summary = RunSummary(total_commands=0)
        assert summary.all_successful is False
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        summary = RunSummary(
            total_commands=4,
            successful=3,
            failed=1,
        )
        assert summary.success_rate == 75.0
    
    def test_success_rate_zero_commands(self):
        """Test success rate with zero commands."""
        summary = RunSummary(total_commands=0)
        assert summary.success_rate == 0.0
    
    def test_get_by_category(self):
        """Test filtering results by category."""
        summary = RunSummary(
            results=[
                CommandResult("cmd1", CommandCategory.TEST, CommandStatus.SUCCESS),
                CommandResult("cmd2", CommandCategory.LINT, CommandStatus.SUCCESS),
                CommandResult("cmd3", CommandCategory.TEST, CommandStatus.FAILED),
            ],
        )
        
        test_results = summary.get_by_category(CommandCategory.TEST)
        assert len(test_results) == 2
        assert all(r.category == CommandCategory.TEST for r in test_results)
    
    def test_get_failed(self):
        """Test getting failed results."""
        summary = RunSummary(
            results=[
                CommandResult("cmd1", CommandCategory.TEST, CommandStatus.SUCCESS),
                CommandResult("cmd2", CommandCategory.TEST, CommandStatus.FAILED),
                CommandResult("cmd3", CommandCategory.TEST, CommandStatus.TIMEOUT),
            ],
        )
        
        failed = summary.get_failed()
        assert len(failed) == 2
        assert all(r.failed for r in failed)


class TestCommandRunner:
    """Tests for CommandRunner class."""
    
    @pytest.fixture
    def runner(self, tmp_path):
        """Create a CommandRunner with temp working dir."""
        return CommandRunner(working_dir=tmp_path)
    
    @pytest.mark.asyncio
    async def test_run_simple_command(self, runner):
        """Test running a simple command."""
        result = await runner.run_command(
            "echo hello",
            CommandCategory.TEST,
        )
        
        assert result.command == "echo hello"
        assert result.category == CommandCategory.TEST
        assert result.status == CommandStatus.SUCCESS
        assert result.return_code == 0
        assert "hello" in result.stdout
    
    @pytest.mark.asyncio
    async def test_run_failing_command(self, runner):
        """Test running a failing command."""
        result = await runner.run_command(
            "sh -c 'exit 1'",
            CommandCategory.TEST,
        )
        
        assert result.status == CommandStatus.FAILED
        assert result.return_code == 1
        assert result.failed is True
    
    @pytest.mark.asyncio
    async def test_run_nonexistent_command(self, runner):
        """Test running a non-existent command."""
        result = await runner.run_command(
            "nonexistent_command_xyz",
            CommandCategory.TEST,
        )
        
        assert result.status == CommandStatus.FAILED
        assert result.return_code == 127
        assert "not found" in result.error_message.lower() or "Command not found" in result.error_message
    
    @pytest.mark.asyncio
    async def test_run_command_with_timeout(self, runner):
        """Test command timeout."""
        result = await runner.run_command(
            "sleep 10",
            CommandCategory.TEST,
            timeout=1,  # 1 second timeout
        )
        
        assert result.status == CommandStatus.TIMEOUT
        assert "timed out" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_run_multiple_commands(self, runner):
        """Test running multiple commands."""
        results = await runner.run_commands(
            ["echo hello", "echo world"],
            CommandCategory.TEST,
        )
        
        assert len(results) == 2
        assert results[0].status == CommandStatus.SUCCESS
        assert results[1].status == CommandStatus.SUCCESS
    
    @pytest.mark.asyncio
    async def test_run_commands_stop_on_failure(self, runner):
        """Test stopping on first failure."""
        results = await runner.run_commands(
            ["echo hello", "exit 1", "echo world"],
            CommandCategory.TEST,
            stop_on_failure=True,
        )
        
        # Should stop after the failing command
        assert len(results) == 2
        assert results[0].status == CommandStatus.SUCCESS
        assert results[1].status == CommandStatus.FAILED
    
    @pytest.mark.asyncio
    async def test_run_test_commands(self, runner):
        """Test running test commands."""
        results = await runner.run_test_commands(["echo test1", "echo test2"])
        
        assert len(results) == 2
        assert all(r.category == CommandCategory.TEST for r in results)
    
    @pytest.mark.asyncio
    async def test_run_lint_commands(self, runner):
        """Test running lint commands."""
        results = await runner.run_lint_commands(["echo lint1"])
        
        assert len(results) == 1
        assert results[0].category == CommandCategory.LINT
    
    @pytest.mark.asyncio
    async def test_run_security_scans(self, runner):
        """Test running security scans."""
        results = await runner.run_security_scans(
            dependency_scan=["echo dep_scan"],
            secret_scan=["echo secret_scan"],
            sast_scan=["echo sast_scan"],
        )
        
        assert len(results) == 3
        categories = [r.category for r in results]
        assert CommandCategory.SECURITY_DEPENDENCY in categories
        assert CommandCategory.SECURITY_SECRET in categories
        assert CommandCategory.SECURITY_SAST in categories
    
    def test_get_summary_empty(self, runner):
        """Test getting summary with no commands run."""
        summary = runner.get_summary()
        
        assert summary.total_commands == 0
        assert summary.successful == 0
        assert summary.failed == 0
    
    @pytest.mark.asyncio
    async def test_get_summary_after_run(self, runner):
        """Test getting summary after running commands."""
        await runner.run_command("echo hello", CommandCategory.TEST)
        await runner.run_command("exit 1", CommandCategory.LINT)
        
        summary = runner.get_summary()
        
        assert summary.total_commands == 2
        assert summary.successful == 1
        assert summary.failed == 1
    
    def test_clear_results(self, runner):
        """Test clearing results."""
        # First add a result by mocking
        runner._results.append(
            CommandResult("cmd", CommandCategory.TEST, CommandStatus.SUCCESS)
        )
        
        assert len(runner._results) == 1
        
        runner.clear_results()
        
        assert len(runner._results) == 0


class TestRunAllFromConfig:
    """Tests for run_all_from_config method."""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock ReviewConfig."""
        config = MagicMock()
        config.commands.build = []
        config.commands.test = []
        config.commands.lint = []
        config.commands.typecheck = []
        config.commands.format = []
        config.security.dependency_scan = []
        config.security.secret_scan = []
        config.security.sast_scan = []
        return config
    
    @pytest.mark.asyncio
    async def test_run_with_all_skipped(self, tmp_path, mock_config):
        """Test running with all categories skipped."""
        runner = CommandRunner(working_dir=tmp_path)
        
        summary = await runner.run_all_from_config(
            mock_config,
            skip_tests=True,
            skip_lint=True,
            skip_security=True,
            skip_typecheck=True,
        )
        
        assert summary.total_commands == 0
    
    @pytest.mark.asyncio
    async def test_run_tests_only(self, tmp_path, mock_config):
        """Test running only tests."""
        runner = CommandRunner(working_dir=tmp_path)
        mock_config.commands.test = ["echo test"]
        
        summary = await runner.run_all_from_config(
            mock_config,
            skip_lint=True,
            skip_security=True,
            skip_typecheck=True,
        )
        
        assert summary.total_commands == 1
        assert summary.successful == 1


class TestFormatSummary:
    """Tests for format_summary function."""
    
    def test_format_successful_summary(self):
        """Test formatting a successful summary."""
        summary = RunSummary(
            total_commands=3,
            successful=3,
            failed=0,
            total_duration_ms=5000,
        )
        
        formatted = format_summary(summary)
        
        assert "COMMAND EXECUTION SUMMARY" in formatted
        assert "Total Commands: 3" in formatted
        assert "3" in formatted and "Successful" in formatted
        assert "ALL CHECKS PASSED" in formatted
    
    def test_format_failed_summary(self):
        """Test formatting a summary with failures."""
        summary = RunSummary(
            total_commands=3,
            successful=2,
            failed=1,
            results=[
                CommandResult(
                    "cmd1",
                    CommandCategory.TEST,
                    CommandStatus.SUCCESS,
                ),
                CommandResult(
                    "cmd2",
                    CommandCategory.LINT,
                    CommandStatus.SUCCESS,
                ),
                CommandResult(
                    "failing_cmd",
                    CommandCategory.TEST,
                    CommandStatus.FAILED,
                    return_code=1,
                    error_message="Test failed",
                ),
            ],
        )
        
        formatted = format_summary(summary)
        
        assert "FAILED COMMANDS" in formatted
        assert "failing_cmd" in formatted
        assert "SOME CHECKS FAILED" in formatted
    
    def test_format_empty_summary(self):
        """Test formatting an empty summary."""
        summary = RunSummary(total_commands=0)
        
        formatted = format_summary(summary)
        
        assert "Total Commands: 0" in formatted
        assert "0.0%" in formatted and "Success Rate" in formatted


class TestCommandStatus:
    """Tests for CommandStatus enum."""
    
    def test_status_values(self):
        """Test status enum values."""
        assert CommandStatus.PENDING.value == "pending"
        assert CommandStatus.RUNNING.value == "running"
        assert CommandStatus.SUCCESS.value == "success"
        assert CommandStatus.FAILED.value == "failed"
        assert CommandStatus.TIMEOUT.value == "timeout"
        assert CommandStatus.SKIPPED.value == "skipped"


class TestCommandCategory:
    """Tests for CommandCategory enum."""
    
    def test_category_values(self):
        """Test category enum values."""
        assert CommandCategory.TEST.value == "test"
        assert CommandCategory.LINT.value == "lint"
        assert CommandCategory.TYPECHECK.value == "typecheck"
        assert CommandCategory.FORMAT.value == "format"
        assert CommandCategory.BUILD.value == "build"
        assert CommandCategory.SECURITY_DEPENDENCY.value == "security_dependency"
        assert CommandCategory.SECURITY_SECRET.value == "security_secret"
        assert CommandCategory.SECURITY_SAST.value == "security_sast"
