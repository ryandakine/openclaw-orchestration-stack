"""
Review Configuration Parser and Validator

Handles parsing and validation of .openclaw/review.yaml configuration files.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class Language(Enum):
    """Supported programming languages."""
    PYTHON = "python"
    RUST = "rust"
    NODE = "node"
    MIXED = "mixed"


class ProfileLevel(Enum):
    """Review profile strictness levels."""
    STANDARD = "STANDARD"
    STRICT = "STRICT"
    LENIENT = "LENIENT"


@dataclass
class RepoConfig:
    """Repository-level configuration."""
    language: Language = Language.MIXED
    profile_default: ProfileLevel = ProfileLevel.STANDARD


@dataclass
class CommandsConfig:
    """Command configurations for different phases."""
    test: list[str] = field(default_factory=list)
    lint: list[str] = field(default_factory=list)
    typecheck: list[str] = field(default_factory=list)
    format: list[str] = field(default_factory=list)
    build: list[str] = field(default_factory=list)


@dataclass
class SecurityConfig:
    """Security scan configurations."""
    dependency_scan: list[str] = field(default_factory=list)
    secret_scan: list[str] = field(default_factory=list)
    sast_scan: list[str] = field(default_factory=list)


@dataclass
class PolicyConfig:
    """Review policy configuration."""
    allow_warn_merge: bool = False
    fail_on_warn_over: int = 10
    require_approval: bool = True
    max_review_time_minutes: int = 30


@dataclass
class ReviewConfig:
    """Complete review configuration."""
    repo: RepoConfig = field(default_factory=RepoConfig)
    commands: CommandsConfig = field(default_factory=CommandsConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    
    # Raw config for extensibility
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def _parse_language(value: str) -> Language:
    """Parse language string to Language enum."""
    try:
        return Language(value.lower())
    except ValueError:
        valid = [l.value for l in Language]
        raise ConfigValidationError(
            f"Invalid language '{value}'. Valid options: {valid}"
        )


def _parse_profile(value: str) -> ProfileLevel:
    """Parse profile string to ProfileLevel enum."""
    try:
        return ProfileLevel(value.upper())
    except ValueError:
        valid = [p.value for p in ProfileLevel]
        raise ConfigValidationError(
            f"Invalid profile '{value}'. Valid options: {valid}"
        )


def parse_review_yaml(content: str) -> ReviewConfig:
    """
    Parse review.yaml content into a ReviewConfig object.
    
    Args:
        content: YAML content as string
        
    Returns:
        ReviewConfig object
        
    Raises:
        ConfigValidationError: If parsing or validation fails
        yaml.YAMLError: If YAML is malformed
    """
    try:
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError as e:
        raise ConfigValidationError(f"Invalid YAML: {e}")
    
    return _build_config(data)


def _build_config(data: dict[str, Any]) -> ReviewConfig:
    """Build ReviewConfig from parsed YAML data."""
    config = ReviewConfig()
    config.raw = data
    
    # Parse repo section
    if "repo" in data:
        repo_data = data["repo"]
        config.repo = RepoConfig(
            language=_parse_language(repo_data.get("language", "mixed")),
            profile_default=_parse_profile(repo_data.get("profile_default", "STANDARD")),
        )
    
    # Parse commands section
    if "commands" in data:
        cmd_data = data["commands"]
        config.commands = CommandsConfig(
            test=_ensure_list(cmd_data.get("test", [])),
            lint=_ensure_list(cmd_data.get("lint", [])),
            typecheck=_ensure_list(cmd_data.get("typecheck", [])),
            format=_ensure_list(cmd_data.get("format", [])),
            build=_ensure_list(cmd_data.get("build", [])),
        )
    
    # Parse security section
    if "security" in data:
        sec_data = data["security"]
        config.security = SecurityConfig(
            dependency_scan=_ensure_list(sec_data.get("dependency_scan", [])),
            secret_scan=_ensure_list(sec_data.get("secret_scan", [])),
            sast_scan=_ensure_list(sec_data.get("sast_scan", [])),
        )
    
    # Parse policy section
    if "policy" in data:
        policy_data = data["policy"]
        config.policy = PolicyConfig(
            allow_warn_merge=policy_data.get("allow_warn_merge", False),
            fail_on_warn_over=policy_data.get("fail_on_warn_over", 10),
            require_approval=policy_data.get("require_approval", True),
            max_review_time_minutes=policy_data.get("max_review_time_minutes", 30),
        )
    
    return config


def _ensure_list(value: Any) -> list[str]:
    """Ensure value is a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def validate_config(config: ReviewConfig) -> list[str]:
    """
    Validate a ReviewConfig object.
    
    Args:
        config: ReviewConfig to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Validate repo section
    if not isinstance(config.repo.language, Language):
        errors.append(f"repo.language must be a valid Language enum")
    
    if not isinstance(config.repo.profile_default, ProfileLevel):
        errors.append(f"repo.profile_default must be a valid ProfileLevel enum")
    
    # Validate commands section
    for field_name, commands in {
        "commands.test": config.commands.test,
        "commands.lint": config.commands.lint,
        "commands.typecheck": config.commands.typecheck,
        "commands.format": config.commands.format,
        "commands.build": config.commands.build,
    }.items():
        for i, cmd in enumerate(commands):
            if not cmd or not isinstance(cmd, str):
                errors.append(f"{field_name}[{i}] must be a non-empty string")
            elif cmd.strip() != cmd:
                errors.append(f"{field_name}[{i}] has leading/trailing whitespace")
    
    # Validate security section
    for field_name, commands in {
        "security.dependency_scan": config.security.dependency_scan,
        "security.secret_scan": config.security.secret_scan,
        "security.sast_scan": config.security.sast_scan,
    }.items():
        for i, cmd in enumerate(commands):
            if not cmd or not isinstance(cmd, str):
                errors.append(f"{field_name}[{i}] must be a non-empty string")
    
    # Validate policy section
    if config.policy.fail_on_warn_over < 0:
        errors.append("policy.fail_on_warn_over must be non-negative")
    
    if config.policy.max_review_time_minutes < 1:
        errors.append("policy.max_review_time_minutes must be at least 1")
    
    # Mixed language repos should have explicit commands
    if config.repo.language == Language.MIXED:
        total_commands = (
            len(config.commands.test) +
            len(config.commands.lint) +
            len(config.commands.typecheck) +
            len(config.commands.build)
        )
        if total_commands == 0:
            errors.append(
                "Mixed language repos should have explicit commands configured"
            )
    
    return errors


def load_review_yaml(path: Path | str) -> ReviewConfig:
    """
    Load and parse a review.yaml file.
    
    Args:
        path: Path to review.yaml file
        
    Returns:
        ReviewConfig object
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ConfigValidationError: If parsing or validation fails
    """
    path = Path(path)
    
    if not path.exists():
        raise FileNotFoundError(f"Review config not found: {path}")
    
    content = path.read_text()
    return parse_review_yaml(content)


def find_review_yaml(start_path: Path | str = Path.cwd()) -> Optional[Path]:
    """
    Find .openclaw/review.yaml by walking up directory tree.
    
    Args:
        start_path: Starting directory for search
        
    Returns:
        Path to review.yaml if found, None otherwise
    """
    current = Path(start_path).resolve()
    
    while current != current.parent:
        config_path = current / ".openclaw" / "review.yaml"
        if config_path.exists():
            return config_path
        current = current.parent
    
    return None
