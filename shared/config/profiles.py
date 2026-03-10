"""
Review Profiles

Predefined review strictness profiles for different use cases.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProfileLevel(Enum):
    """Review profile strictness levels."""
    STANDARD = "STANDARD"
    STRICT = "STRICT"
    LENIENT = "LENIENT"
    MINIMAL = "MINIMAL"
    SECURITY_FOCUSED = "SECURITY_FOCUSED"


@dataclass
class ProfileSettings:
    """Settings for a review profile."""
    # Command execution
    require_all_tests: bool = True
    require_all_lint: bool = True
    require_typecheck: bool = True
    require_format_check: bool = True
    
    # Security
    require_dependency_scan: bool = True
    require_secret_scan: bool = True
    require_sast_scan: bool = False
    
    # Policy
    allow_warn_merge: bool = False
    fail_on_warn_over: int = 10
    max_review_time_minutes: int = 30
    require_approval: bool = True
    
    # Review depth
    review_line_threshold: int = 500  # Lines per review chunk
    require_docstrings: bool = False
    require_tests_for_new_code: bool = False
    check_test_coverage: bool = False
    min_coverage_percent: int = 0
    
    # Automation
    auto_fix_formatting: bool = False
    auto_fix_lint: bool = False
    block_on_security_findings: bool = True
    
    # Extensibility
    custom_rules: list[str] = field(default_factory=list)
    disabled_checks: list[str] = field(default_factory=list)


@dataclass
class ReviewProfile:
    """A review profile with name, description, and settings."""
    name: str
    level: ProfileLevel
    description: str
    settings: ProfileSettings
    
    def applies_to_language(self, language: str) -> bool:
        """Check if this profile applies to a given language."""
        # All profiles apply to all languages by default
        return True


# Predefined profiles

STANDARD_PROFILE = ReviewProfile(
    name="Standard",
    level=ProfileLevel.STANDARD,
    description="Default review strictness with essential checks",
    settings=ProfileSettings(
        require_all_tests=True,
        require_all_lint=True,
        require_typecheck=True,
        require_format_check=True,
        require_dependency_scan=True,
        require_secret_scan=True,
        require_sast_scan=False,
        allow_warn_merge=False,
        fail_on_warn_over=10,
        max_review_time_minutes=30,
        require_approval=True,
        review_line_threshold=500,
        require_docstrings=False,
        require_tests_for_new_code=False,
        check_test_coverage=False,
        min_coverage_percent=0,
        auto_fix_formatting=False,
        auto_fix_lint=False,
        block_on_security_findings=True,
    ),
)

STRICT_PROFILE = ReviewProfile(
    name="Strict",
    level=ProfileLevel.STRICT,
    description="Maximum checks for critical codebases",
    settings=ProfileSettings(
        require_all_tests=True,
        require_all_lint=True,
        require_typecheck=True,
        require_format_check=True,
        require_dependency_scan=True,
        require_secret_scan=True,
        require_sast_scan=True,
        allow_warn_merge=False,
        fail_on_warn_over=0,  # Fail on any warning
        max_review_time_minutes=60,
        require_approval=True,
        review_line_threshold=300,
        require_docstrings=True,
        require_tests_for_new_code=True,
        check_test_coverage=True,
        min_coverage_percent=80,
        auto_fix_formatting=False,  # Manual review required
        auto_fix_lint=False,
        block_on_security_findings=True,
    ),
)

LENIENT_PROFILE = ReviewProfile(
    name="Lenient",
    level=ProfileLevel.LENIENT,
    description="Minimal checks for rapid prototyping",
    settings=ProfileSettings(
        require_all_tests=False,  # Tests recommended but not required
        require_all_lint=True,
        require_typecheck=False,
        require_format_check=False,
        require_dependency_scan=True,
        require_secret_scan=True,
        require_sast_scan=False,
        allow_warn_merge=True,
        fail_on_warn_over=50,
        max_review_time_minutes=15,
        require_approval=False,  # Auto-approve if basic checks pass
        review_line_threshold=1000,
        require_docstrings=False,
        require_tests_for_new_code=False,
        check_test_coverage=False,
        min_coverage_percent=0,
        auto_fix_formatting=True,
        auto_fix_lint=True,
        block_on_security_findings=True,
    ),
)

MINIMAL_PROFILE = ReviewProfile(
    name="Minimal",
    level=ProfileLevel.MINIMAL,
    description="Security scans only - fastest option",
    settings=ProfileSettings(
        require_all_tests=False,
        require_all_lint=False,
        require_typecheck=False,
        require_format_check=False,
        require_dependency_scan=True,
        require_secret_scan=True,
        require_sast_scan=False,
        allow_warn_merge=True,
        fail_on_warn_over=1000,  # Essentially unlimited
        max_review_time_minutes=10,
        require_approval=False,
        review_line_threshold=2000,
        require_docstrings=False,
        require_tests_for_new_code=False,
        check_test_coverage=False,
        min_coverage_percent=0,
        auto_fix_formatting=False,
        auto_fix_lint=False,
        block_on_security_findings=True,
    ),
)

SECURITY_FOCUSED_PROFILE = ReviewProfile(
    name="Security Focused",
    level=ProfileLevel.SECURITY_FOCUSED,
    description="Security-first with moderate code quality checks",
    settings=ProfileSettings(
        require_all_tests=True,
        require_all_lint=True,
        require_typecheck=True,
        require_format_check=False,
        require_dependency_scan=True,
        require_secret_scan=True,
        require_sast_scan=True,
        allow_warn_merge=False,
        fail_on_warn_over=5,
        max_review_time_minutes=45,
        require_approval=True,
        review_line_threshold=400,
        require_docstrings=False,
        require_tests_for_new_code=False,
        check_test_coverage=False,
        min_coverage_percent=0,
        auto_fix_formatting=False,
        auto_fix_lint=False,
        block_on_security_findings=True,
        custom_rules=["check-for-secrets-in-tests", "verify-dependency-pinning"],
    ),
)

# Profile registry
PROFILES: dict[ProfileLevel, ReviewProfile] = {
    ProfileLevel.STANDARD: STANDARD_PROFILE,
    ProfileLevel.STRICT: STRICT_PROFILE,
    ProfileLevel.LENIENT: LENIENT_PROFILE,
    ProfileLevel.MINIMAL: MINIMAL_PROFILE,
    ProfileLevel.SECURITY_FOCUSED: SECURITY_FOCUSED_PROFILE,
}


def get_profile(level: ProfileLevel | str) -> ReviewProfile:
    """
    Get a review profile by level.
    
    Args:
        level: ProfileLevel enum or string name
        
    Returns:
        ReviewProfile for the given level
        
    Raises:
        ValueError: If profile level is not recognized
    """
    if isinstance(level, str):
        try:
            level = ProfileLevel(level.upper())
        except ValueError:
            valid = [p.value for p in ProfileLevel]
            raise ValueError(
                f"Invalid profile level '{level}'. Valid options: {valid}"
            )
    
    if level not in PROFILES:
        raise ValueError(f"Profile not found: {level}")
    
    return PROFILES[level]


def get_profile_by_name(name: str) -> Optional[ReviewProfile]:
    """
    Get a profile by its display name (case-insensitive).
    
    Args:
        name: Profile display name
        
    Returns:
        ReviewProfile if found, None otherwise
    """
    name_lower = name.lower()
    for profile in PROFILES.values():
        if profile.name.lower() == name_lower:
            return profile
    return None


def list_profiles() -> list[ReviewProfile]:
    """Get list of all available profiles."""
    return list(PROFILES.values())


def create_custom_profile(
    name: str,
    base_profile: ProfileLevel | ReviewProfile,
    overrides: dict,
) -> ReviewProfile:
    """
    Create a custom profile based on an existing one.
    
    Args:
        name: Name for the new profile
        base_profile: Base profile to extend
        overrides: Dictionary of setting overrides
        
    Returns:
        New ReviewProfile with custom settings
    """
    if isinstance(base_profile, ProfileLevel):
        base = get_profile(base_profile)
    else:
        base = base_profile
    
    # Start with base settings
    settings_dict = {
        "require_all_tests": base.settings.require_all_tests,
        "require_all_lint": base.settings.require_all_lint,
        "require_typecheck": base.settings.require_typecheck,
        "require_format_check": base.settings.require_format_check,
        "require_dependency_scan": base.settings.require_dependency_scan,
        "require_secret_scan": base.settings.require_secret_scan,
        "require_sast_scan": base.settings.require_sast_scan,
        "allow_warn_merge": base.settings.allow_warn_merge,
        "fail_on_warn_over": base.settings.fail_on_warn_over,
        "max_review_time_minutes": base.settings.max_review_time_minutes,
        "require_approval": base.settings.require_approval,
        "review_line_threshold": base.settings.review_line_threshold,
        "require_docstrings": base.settings.require_docstrings,
        "require_tests_for_new_code": base.settings.require_tests_for_new_code,
        "check_test_coverage": base.settings.check_test_coverage,
        "min_coverage_percent": base.settings.min_coverage_percent,
        "auto_fix_formatting": base.settings.auto_fix_formatting,
        "auto_fix_lint": base.settings.auto_fix_lint,
        "block_on_security_findings": base.settings.block_on_security_findings,
        "custom_rules": list(base.settings.custom_rules),
        "disabled_checks": list(base.settings.disabled_checks),
    }
    
    # Apply overrides
    settings_dict.update(overrides)
    
    new_settings = ProfileSettings(**settings_dict)
    
    return ReviewProfile(
        name=name,
        level=ProfileLevel.STANDARD,  # Custom profiles use STANDARD level
        description=f"Custom profile based on {base.name}",
        settings=new_settings,
    )


def profile_to_yaml(profile: ReviewProfile) -> str:
    """
    Convert a profile to YAML format for .openclaw/review.yaml.
    
    Args:
        profile: ReviewProfile to convert
        
    Returns:
        YAML string representation
    """
    s = profile.settings
    lines = [
        "# Profile Configuration",
        f"# Profile: {profile.name}",
        f"# Description: {profile.description}",
        "",
        "repo:",
        f"  profile_default: {profile.level.value}",
        "",
        "policy:",
        f"  allow_warn_merge: {str(s.allow_warn_merge).lower()}",
        f"  fail_on_warn_over: {s.fail_on_warn_over}",
        f"  require_approval: {str(s.require_approval).lower()}",
        f"  max_review_time_minutes: {s.max_review_time_minutes}",
        "",
        "# Profile Settings (for reference)",
        f"# require_all_tests: {str(s.require_all_tests).lower()}",
        f"# require_all_lint: {str(s.require_all_lint).lower()}",
        f"# require_typecheck: {str(s.require_typecheck).lower()}",
        f"# require_format_check: {str(s.require_format_check).lower()}",
        f"# require_dependency_scan: {str(s.require_dependency_scan).lower()}",
        f"# require_secret_scan: {str(s.require_secret_scan).lower()}",
        f"# require_sast_scan: {str(s.require_sast_scan).lower()}",
    ]
    
    if s.custom_rules:
        lines.append("# custom_rules:")
        for rule in s.custom_rules:
            lines.append(f"#   - {rule}")
    
    if s.disabled_checks:
        lines.append("# disabled_checks:")
        for check in s.disabled_checks:
            lines.append(f"#   - {check}")
    
    return "\n".join(lines)


def should_run_check(profile: ReviewProfile, check_type: str) -> bool:
    """
    Check if a specific check should run based on profile settings.
    
    Args:
        profile: ReviewProfile to check
        check_type: Type of check (test, lint, typecheck, format, security_dep, security_sec, security_sast)
        
    Returns:
        True if the check should run
    """
    s = profile.settings
    
    check_map = {
        "test": s.require_all_tests,
        "lint": s.require_all_lint,
        "typecheck": s.require_typecheck,
        "format": s.require_format_check,
        "security_dep": s.require_dependency_scan,
        "security_sec": s.require_secret_scan,
        "security_sast": s.require_sast_scan,
    }
    
    return check_map.get(check_type, True)
