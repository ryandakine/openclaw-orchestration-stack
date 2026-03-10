"""
Unit tests for Task 1: Initialize project structure and repository
"""
import os
import subprocess
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


class TestProjectStructure:
    """Test suite for project initialization"""
    
    def test_project_root_exists(self):
        """Verify project root directory exists"""
        assert os.path.isdir(PROJECT_ROOT), f"Project root {PROJECT_ROOT} does not exist"
    
    def test_openclaw_directory_structure(self):
        """Verify openclaw/ conductor directory exists with subdirectories"""
        openclaw_dir = os.path.join(PROJECT_ROOT, "openclaw")
        assert os.path.isdir(openclaw_dir), "openclaw/ directory missing"
        assert os.path.isdir(os.path.join(openclaw_dir, "src")), "openclaw/src/ missing"
        assert os.path.isdir(os.path.join(openclaw_dir, "config")), "openclaw/config/ missing"
        assert os.path.isdir(os.path.join(openclaw_dir, "prompts")), "openclaw/prompts/ missing"
    
    def test_devclaw_runner_directory_structure(self):
        """Verify devclaw-runner/ executor directory exists"""
        devclaw_dir = os.path.join(PROJECT_ROOT, "devclaw-runner")
        assert os.path.isdir(devclaw_dir), "devclaw-runner/ directory missing"
        assert os.path.isdir(os.path.join(devclaw_dir, "src")), "devclaw-runner/src/ missing"
        assert os.path.isdir(os.path.join(devclaw_dir, "workers")), "devclaw-runner/workers/ missing"
        assert os.path.isdir(os.path.join(devclaw_dir, "templates")), "devclaw-runner/templates/ missing"
    
    def test_symphony_bridge_directory_structure(self):
        """Verify symphony-bridge/ PR manager directory exists"""
        symphony_dir = os.path.join(PROJECT_ROOT, "symphony-bridge")
        assert os.path.isdir(symphony_dir), "symphony-bridge/ directory missing"
        assert os.path.isdir(os.path.join(symphony_dir, "src")), "symphony-bridge/src/ missing"
        assert os.path.isdir(os.path.join(symphony_dir, "github")), "symphony-bridge/github/ missing"
        assert os.path.isdir(os.path.join(symphony_dir, "review")), "symphony-bridge/review/ missing"
    
    def test_n8n_workflows_directory_structure(self):
        """Verify n8n-workflows/ directory exists"""
        n8n_dir = os.path.join(PROJECT_ROOT, "n8n-workflows")
        assert os.path.isdir(n8n_dir), "n8n-workflows/ directory missing"
        assert os.path.isdir(os.path.join(n8n_dir, "workflows")), "n8n-workflows/workflows/ missing"
        assert os.path.isdir(os.path.join(n8n_dir, "credentials")), "n8n-workflows/credentials/ missing"
        assert os.path.isdir(os.path.join(n8n_dir, "audit")), "n8n-workflows/audit/ missing"
    
    def test_shared_directory_structure(self):
        """Verify shared/ common utilities directory exists"""
        shared_dir = os.path.join(PROJECT_ROOT, "shared")
        assert os.path.isdir(shared_dir), "shared/ directory missing"
        assert os.path.isdir(os.path.join(shared_dir, "models")), "shared/models/ missing"
        assert os.path.isdir(os.path.join(shared_dir, "schemas")), "shared/schemas/ missing"
        assert os.path.isdir(os.path.join(shared_dir, "utils")), "shared/utils/ missing"
    
    def test_docs_directory_structure(self):
        """Verify docs/ documentation directory exists"""
        docs_dir = os.path.join(PROJECT_ROOT, "docs")
        assert os.path.isdir(docs_dir), "docs/ directory missing"
        assert os.path.isdir(os.path.join(docs_dir, "architecture")), "docs/architecture/ missing"
        assert os.path.isdir(os.path.join(docs_dir, "api")), "docs/api/ missing"
        assert os.path.isdir(os.path.join(docs_dir, "guides")), "docs/guides/ missing"
    
    def test_tests_directory_structure(self):
        """Verify tests/ test suite directory exists"""
        tests_dir = os.path.join(PROJECT_ROOT, "tests")
        assert os.path.isdir(tests_dir), "tests/ directory missing"
        assert os.path.isdir(os.path.join(tests_dir, "unit")), "tests/unit/ missing"
        assert os.path.isdir(os.path.join(tests_dir, "integration")), "tests/integration/ missing"
        assert os.path.isdir(os.path.join(tests_dir, "e2e")), "tests/e2e/ missing"


class TestGitRepository:
    """Test suite for git repository initialization"""
    
    def test_git_directory_exists(self):
        """Verify .git/ directory exists"""
        git_dir = os.path.join(PROJECT_ROOT, ".git")
        assert os.path.isdir(git_dir), ".git/ directory missing - git not initialized"
    
    def test_git_config_exists(self):
        """Verify git config file exists"""
        git_config = os.path.join(PROJECT_ROOT, ".git", "config")
        assert os.path.isfile(git_config), ".git/config file missing"
    
    def test_git_has_initial_commit(self):
        """Verify repository has at least one commit"""
        result = subprocess.run(
            ["git", "-C", PROJECT_ROOT, "log", "--oneline"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, "Git log command failed"
        assert len(result.stdout.strip()) > 0, "No commits found in repository"


class TestDocumentationFiles:
    """Test suite for documentation files"""
    
    def test_readme_exists(self):
        """Verify README.md exists"""
        readme_path = os.path.join(PROJECT_ROOT, "README.md")
        assert os.path.isfile(readme_path), "README.md missing"
    
    def test_readme_has_content(self):
        """Verify README.md has substantial content"""
        readme_path = os.path.join(PROJECT_ROOT, "README.md")
        with open(readme_path, 'r') as f:
            content = f.read()
        assert len(content) > 1000, "README.md content too short"
        assert "# OpenClaw" in content, "README missing project title"
        assert "OpenClaw" in content, "README missing OpenClaw reference"
        assert "DevClaw" in content, "README missing DevClaw reference"
        assert "Symphony" in content, "README missing Symphony reference"
    
    def test_license_exists(self):
        """Verify LICENSE file exists"""
        license_path = os.path.join(PROJECT_ROOT, "LICENSE")
        assert os.path.isfile(license_path), "LICENSE file missing"
    
    def test_license_is_mit(self):
        """Verify LICENSE is MIT license"""
        license_path = os.path.join(PROJECT_ROOT, "LICENSE")
        with open(license_path, 'r') as f:
            content = f.read()
        assert "MIT License" in content, "LICENSE not MIT"
        assert "OpenClaw Project" in content, "LICENSE missing copyright"
    
    def test_gitignore_exists(self):
        """Verify .gitignore exists"""
        gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
        assert os.path.isfile(gitignore_path), ".gitignore missing"
    
    def test_gitignore_has_patterns(self):
        """Verify .gitignore has required patterns"""
        gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
        with open(gitignore_path, 'r') as f:
            content = f.read()
        assert "__pycache__" in content, ".gitignore missing Python patterns"
        assert "node_modules" in content, ".gitignore missing Node patterns"
        assert "target/" in content, ".gitignore missing Rust patterns"
        assert ".env" in content, ".gitignore missing env file patterns"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
