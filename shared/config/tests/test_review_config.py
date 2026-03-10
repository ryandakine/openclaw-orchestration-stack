"""
Tests for review_config.py - Config parser and validator
"""

import pytest
from pathlib import Path
import tempfile
import yaml

from shared.config.review_config import (
    ReviewConfig,
    RepoConfig,
    CommandsConfig,
    SecurityConfig,
    PolicyConfig,
    Language,
    ProfileLevel,
    parse_review_yaml,
    validate_config,
    load_review_yaml,
    find_review_yaml,
    ConfigValidationError,
)


class TestParseReviewYaml:
    """Tests for parse_review_yaml function."""
    
    def test_parse_minimal_config(self):
        """Test parsing a minimal valid config."""
        content = """
repo:
  language: python
  profile_default: STANDARD
"""
        config = parse_review_yaml(content)
        
        assert config.repo.language == Language.PYTHON
        assert config.repo.profile_default == ProfileLevel.STANDARD
    
    def test_parse_full_config(self):
        """Test parsing a complete config with all sections."""
        content = """
repo:
  language: mixed
  profile_default: STRICT

commands:
  test:
    - "pytest -q"
    - "cargo test"
  lint:
    - "ruff check ."
    - "cargo clippy"
  typecheck:
    - "mypy ."
  format:
    - "black --check ."
  build:
    - "cargo build --release"

security:
  dependency_scan:
    - "cargo audit"
    - "pip-audit"
  secret_scan:
    - "gitleaks detect"
  sast_scan:
    - "bandit -r ."

policy:
  allow_warn_merge: false
  fail_on_warn_over: 5
  require_approval: true
  max_review_time_minutes: 45
"""
        config = parse_review_yaml(content)
        
        # Check repo section
        assert config.repo.language == Language.MIXED
        assert config.repo.profile_default == ProfileLevel.STRICT
        
        # Check commands section
        assert len(config.commands.test) == 2
        assert "pytest -q" in config.commands.test
        assert "cargo test" in config.commands.test
        assert len(config.commands.lint) == 2
        assert len(config.commands.typecheck) == 1
        assert len(config.commands.format) == 1
        assert len(config.commands.build) == 1
        
        # Check security section
        assert len(config.security.dependency_scan) == 2
        assert len(config.security.secret_scan) == 1
        assert len(config.security.sast_scan) == 1
        
        # Check policy section
        assert config.policy.allow_warn_merge is False
        assert config.policy.fail_on_warn_over == 5
        assert config.policy.require_approval is True
        assert config.policy.max_review_time_minutes == 45
    
    def test_parse_empty_config(self):
        """Test parsing an empty config."""
        config = parse_review_yaml("")
        
        assert config.repo.language == Language.MIXED
        assert config.repo.profile_default == ProfileLevel.STANDARD
        assert config.commands.test == []
        assert config.commands.lint == []
        assert config.security.dependency_scan == []
    
    def test_parse_invalid_yaml(self):
        """Test parsing invalid YAML raises error."""
        content = """
repo:
  language: python
  profile_default: STANDARD
  invalid: [unclosed
"""
        with pytest.raises(ConfigValidationError) as exc_info:
            parse_review_yaml(content)
        
        assert "Invalid YAML" in str(exc_info.value)
    
    def test_parse_invalid_language(self):
        """Test parsing with invalid language raises error."""
        content = """
repo:
  language: invalidlang
"""
        with pytest.raises(ConfigValidationError) as exc_info:
            parse_review_yaml(content)
        
        assert "Invalid language" in str(exc_info.value)
    
    def test_parse_invalid_profile(self):
        """Test parsing with invalid profile raises error."""
        content = """
repo:
  profile_default: INVALID
"""
        with pytest.raises(ConfigValidationError) as exc_info:
            parse_review_yaml(content)
        
        assert "Invalid profile" in str(exc_info.value)
    
    def test_parse_single_command_as_string(self):
        """Test that single commands are converted to list."""
        content = """
commands:
  test: "pytest"
  lint: "ruff check ."
"""
        config = parse_review_yaml(content)
        
        assert config.commands.test == ["pytest"]
        assert config.commands.lint == ["ruff check ."]
    
    def test_case_insensitive_language(self):
        """Test that language values are case-insensitive."""
        for lang in ["PYTHON", "Python", "python", "PyThOn"]:
            content = f"""
repo:
  language: {lang}
"""
            config = parse_review_yaml(content)
            assert config.repo.language == Language.PYTHON
    
    def test_case_insensitive_profile(self):
        """Test that profile values are case-insensitive."""
        for profile in ["standard", "STANDARD", "Standard"]:
            content = f"""
repo:
  profile_default: {profile}
"""
            config = parse_review_yaml(content)
            assert config.repo.profile_default == ProfileLevel.STANDARD


class TestValidateConfig:
    """Tests for validate_config function."""
    
    def test_valid_config(self):
        """Test validation of a valid config."""
        config = ReviewConfig()
        config.commands.test = ["pytest"]
        
        errors = validate_config(config)
        assert errors == []
    
    def test_invalid_empty_command(self):
        """Test validation catches empty commands."""
        config = ReviewConfig()
        config.commands.test = [""]
        
        errors = validate_config(config)
        assert any("must be a non-empty string" in e for e in errors)
    
    def test_invalid_whitespace_command(self):
        """Test validation catches commands with whitespace."""
        config = ReviewConfig()
        config.commands.test = ["  pytest  "]
        
        errors = validate_config(config)
        assert any("leading/trailing whitespace" in e for e in errors)
    
    def test_invalid_negative_fail_threshold(self):
        """Test validation catches negative fail_on_warn_over."""
        config = ReviewConfig()
        config.policy.fail_on_warn_over = -1
        
        errors = validate_config(config)
        assert any("non-negative" in e for e in errors)
    
    def test_invalid_zero_review_time(self):
        """Test validation catches zero review time."""
        config = ReviewConfig()
        config.policy.max_review_time_minutes = 0
        
        errors = validate_config(config)
        assert any("at least 1" in e for e in errors)
    
    def test_mixed_language_without_commands(self):
        """Test validation warns about mixed language without commands."""
        config = ReviewConfig()
        config.repo.language = Language.MIXED
        config.commands.test = []
        config.commands.lint = []
        config.commands.typecheck = []
        config.commands.build = []
        
        errors = validate_config(config)
        assert any("Mixed language repos should have explicit commands" in e for e in errors)
    
    def test_mixed_language_with_commands_valid(self):
        """Test mixed language with commands is valid."""
        config = ReviewConfig()
        config.repo.language = Language.MIXED
        config.commands.test = ["pytest"]
        
        errors = validate_config(config)
        assert not any("Mixed language" in e for e in errors)


class TestLoadReviewYaml:
    """Tests for load_review_yaml function."""
    
    def test_load_existing_file(self, tmp_path):
        """Test loading an existing review.yaml file."""
        config_file = tmp_path / "review.yaml"
        config_file.write_text("""
repo:
  language: python
""")
        
        config = load_review_yaml(config_file)
        assert config.repo.language == Language.PYTHON
    
    def test_load_nonexistent_file(self, tmp_path):
        """Test loading a non-existent file raises error."""
        config_file = tmp_path / "nonexistent.yaml"
        
        with pytest.raises(FileNotFoundError):
            load_review_yaml(config_file)
    
    def test_load_as_string_path(self, tmp_path):
        """Test loading with string path."""
        config_file = tmp_path / "review.yaml"
        config_file.write_text("""
repo:
  language: rust
""")
        
        config = load_review_yaml(str(config_file))
        assert config.repo.language == Language.RUST


class TestFindReviewYaml:
    """Tests for find_review_yaml function."""
    
    def test_find_in_current_directory(self, tmp_path):
        """Test finding review.yaml in current directory."""
        openclaw_dir = tmp_path / ".openclaw"
        openclaw_dir.mkdir()
        config_file = openclaw_dir / "review.yaml"
        config_file.write_text("repo:\n  language: python\n")
        
        found = find_review_yaml(tmp_path)
        assert found == config_file
    
    def test_find_in_parent_directory(self, tmp_path):
        """Test finding review.yaml in parent directory."""
        openclaw_dir = tmp_path / ".openclaw"
        openclaw_dir.mkdir()
        config_file = openclaw_dir / "review.yaml"
        config_file.write_text("repo:\n  language: python\n")
        
        subdir = tmp_path / "subdir" / "nested"
        subdir.mkdir(parents=True)
        
        found = find_review_yaml(subdir)
        assert found == config_file
    
    def test_not_found(self, tmp_path):
        """Test returns None when no review.yaml exists."""
        found = find_review_yaml(tmp_path)
        assert found is None
    
    def test_not_found_at_root(self, tmp_path):
        """Test stops searching at filesystem root."""
        # Use a deeply nested path without .openclaw
        subdir = tmp_path / "a" / "b" / "c"
        subdir.mkdir(parents=True)
        
        found = find_review_yaml(subdir)
        assert found is None


class TestDataclasses:
    """Tests for dataclass structures."""
    
    def test_review_config_defaults(self):
        """Test ReviewConfig has proper defaults."""
        config = ReviewConfig()
        
        assert isinstance(config.repo, RepoConfig)
        assert isinstance(config.commands, CommandsConfig)
        assert isinstance(config.security, SecurityConfig)
        assert isinstance(config.policy, PolicyConfig)
    
    def test_repo_config_defaults(self):
        """Test RepoConfig defaults."""
        repo = RepoConfig()
        assert repo.language == Language.MIXED
        assert repo.profile_default == ProfileLevel.STANDARD
    
    def test_commands_config_defaults(self):
        """Test CommandsConfig defaults."""
        cmds = CommandsConfig()
        assert cmds.test == []
        assert cmds.lint == []
        assert cmds.typecheck == []
        assert cmds.format == []
        assert cmds.build == []
    
    def test_security_config_defaults(self):
        """Test SecurityConfig defaults."""
        sec = SecurityConfig()
        assert sec.dependency_scan == []
        assert sec.secret_scan == []
        assert sec.sast_scan == []
    
    def test_policy_config_defaults(self):
        """Test PolicyConfig defaults."""
        policy = PolicyConfig()
        assert policy.allow_warn_merge is False
        assert policy.fail_on_warn_over == 10
        assert policy.require_approval is True
        assert policy.max_review_time_minutes == 30


class TestLanguageEnum:
    """Tests for Language enum."""
    
    def test_language_values(self):
        """Test language enum has correct values."""
        assert Language.PYTHON.value == "python"
        assert Language.RUST.value == "rust"
        assert Language.NODE.value == "node"
        assert Language.MIXED.value == "mixed"


class TestProfileLevelEnum:
    """Tests for ProfileLevel enum."""
    
    def test_profile_values(self):
        """Test profile enum has correct values."""
        assert ProfileLevel.STANDARD.value == "STANDARD"
        assert ProfileLevel.STRICT.value == "STRICT"
        assert ProfileLevel.LENIENT.value == "LENIENT"
