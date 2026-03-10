"""
Tests for profiles.py - Review profiles
"""

import pytest

from shared.config.profiles import (
    ProfileLevel,
    ProfileSettings,
    ReviewProfile,
    STANDARD_PROFILE,
    STRICT_PROFILE,
    LENIENT_PROFILE,
    MINIMAL_PROFILE,
    SECURITY_FOCUSED_PROFILE,
    PROFILES,
    get_profile,
    get_profile_by_name,
    list_profiles,
    create_custom_profile,
    profile_to_yaml,
    should_run_check,
)


class TestProfileSettings:
    """Tests for ProfileSettings dataclass."""
    
    def test_default_settings(self):
        """Test ProfileSettings defaults."""
        settings = ProfileSettings()
        
        assert settings.require_all_tests is True
        assert settings.require_all_lint is True
        assert settings.require_typecheck is True
        assert settings.require_format_check is True
        assert settings.allow_warn_merge is False
        assert settings.fail_on_warn_over == 10
        assert settings.max_review_time_minutes == 30
    
    def test_custom_settings(self):
        """Test creating custom settings."""
        settings = ProfileSettings(
            require_all_tests=False,
            fail_on_warn_over=0,
        )
        
        assert settings.require_all_tests is False
        assert settings.fail_on_warn_over == 0
        assert settings.require_all_lint is True  # Default value


class TestPredefinedProfiles:
    """Tests for predefined profiles."""
    
    def test_standard_profile(self):
        """Test STANDARD profile has expected settings."""
        profile = STANDARD_PROFILE
        
        assert profile.name == "Standard"
        assert profile.level == ProfileLevel.STANDARD
        assert profile.settings.require_all_tests is True
        assert profile.settings.require_secret_scan is True
        assert profile.settings.require_sast_scan is False
        assert profile.settings.fail_on_warn_over == 10
    
    def test_strict_profile(self):
        """Test STRICT profile has expected settings."""
        profile = STRICT_PROFILE
        
        assert profile.name == "Strict"
        assert profile.level == ProfileLevel.STRICT
        assert profile.settings.fail_on_warn_over == 0  # Fail on any warning
        assert profile.settings.require_sast_scan is True
        assert profile.settings.require_docstrings is True
        assert profile.settings.min_coverage_percent == 80
    
    def test_lenient_profile(self):
        """Test LENIENT profile has expected settings."""
        profile = LENIENT_PROFILE
        
        assert profile.name == "Lenient"
        assert profile.level == ProfileLevel.LENIENT
        assert profile.settings.allow_warn_merge is True
        assert profile.settings.require_approval is False  # Auto-approve
        assert profile.settings.auto_fix_formatting is True
    
    def test_minimal_profile(self):
        """Test MINIMAL profile has expected settings."""
        profile = MINIMAL_PROFILE
        
        assert profile.name == "Minimal"
        assert profile.level == ProfileLevel.MINIMAL
        assert profile.settings.require_all_tests is False
        assert profile.settings.require_all_lint is False
        assert profile.settings.require_secret_scan is True  # Still check secrets
    
    def test_security_focused_profile(self):
        """Test SECURITY_FOCUSED profile has expected settings."""
        profile = SECURITY_FOCUSED_PROFILE
        
        assert profile.name == "Security Focused"
        assert profile.level == ProfileLevel.SECURITY_FOCUSED
        assert profile.settings.require_sast_scan is True
        assert profile.settings.require_format_check is False
        assert len(profile.settings.custom_rules) > 0
    
    def test_profiles_registry(self):
        """Test PROFILES registry contains all profiles."""
        assert ProfileLevel.STANDARD in PROFILES
        assert ProfileLevel.STRICT in PROFILES
        assert ProfileLevel.LENIENT in PROFILES
        assert ProfileLevel.MINIMAL in PROFILES
        assert ProfileLevel.SECURITY_FOCUSED in PROFILES


class TestGetProfile:
    """Tests for get_profile function."""
    
    def test_get_by_enum(self):
        """Test getting profile by enum."""
        profile = get_profile(ProfileLevel.STANDARD)
        assert profile == STANDARD_PROFILE
    
    def test_get_by_string(self):
        """Test getting profile by string name."""
        profile = get_profile("STANDARD")
        assert profile == STANDARD_PROFILE
    
    def test_get_by_lowercase_string(self):
        """Test getting profile by lowercase string."""
        profile = get_profile("strict")
        assert profile == STRICT_PROFILE
    
    def test_get_invalid_profile(self):
        """Test getting invalid profile raises error."""
        with pytest.raises(ValueError) as exc_info:
            get_profile("INVALID")
        
        assert "Invalid profile level" in str(exc_info.value)


class TestGetProfileByName:
    """Tests for get_profile_by_name function."""
    
    def test_get_by_display_name(self):
        """Test getting profile by display name."""
        profile = get_profile_by_name("Standard")
        assert profile == STANDARD_PROFILE
    
    def test_get_by_lowercase_name(self):
        """Test getting profile by lowercase name."""
        profile = get_profile_by_name("strict")
        assert profile == STRICT_PROFILE
    
    def test_get_nonexistent_name(self):
        """Test getting non-existent profile returns None."""
        profile = get_profile_by_name("NonExistent")
        assert profile is None


class TestListProfiles:
    """Tests for list_profiles function."""
    
    def test_list_all_profiles(self):
        """Test listing all profiles."""
        profiles = list_profiles()
        
        assert len(profiles) == 5
        assert STANDARD_PROFILE in profiles
        assert STRICT_PROFILE in profiles
        assert LENIENT_PROFILE in profiles
        assert MINIMAL_PROFILE in profiles
        assert SECURITY_FOCUSED_PROFILE in profiles


class TestCreateCustomProfile:
    """Tests for create_custom_profile function."""
    
    def test_create_from_enum(self):
        """Test creating custom profile from enum."""
        custom = create_custom_profile(
            "My Custom",
            ProfileLevel.STANDARD,
            {"fail_on_warn_over": 5, "require_sast_scan": True},
        )
        
        assert custom.name == "My Custom"
        assert custom.settings.fail_on_warn_over == 5
        assert custom.settings.require_sast_scan is True
        assert custom.settings.require_all_tests is True  # From base
    
    def test_create_from_profile(self):
        """Test creating custom profile from another profile."""
        custom = create_custom_profile(
            "Strict Light",
            STRICT_PROFILE,
            {"fail_on_warn_over": 5},  # Less strict than STRICT
        )
        
        assert custom.name == "Strict Light"
        assert custom.settings.fail_on_warn_over == 5
        assert custom.settings.require_docstrings is True  # From STRICT
    
    def test_create_preserves_lists(self):
        """Test creating custom profile copies lists properly."""
        custom = create_custom_profile(
            "Custom",
            SECURITY_FOCUSED_PROFILE,
            {"custom_rules": ["new-rule"]},
        )
        
        # Should have new rules, not shared reference
        assert "new-rule" in custom.settings.custom_rules
        assert custom.settings.custom_rules is not SECURITY_FOCUSED_PROFILE.settings.custom_rules


class TestProfileToYaml:
    """Tests for profile_to_yaml function."""
    
    def test_standard_to_yaml(self):
        """Test converting STANDARD profile to YAML."""
        yaml = profile_to_yaml(STANDARD_PROFILE)
        
        assert "Profile: Standard" in yaml
        assert "STANDARD" in yaml
        assert "policy:" in yaml
        assert "allow_warn_merge: false" in yaml
    
    def test_lenient_to_yaml(self):
        """Test converting LENIENT profile to YAML."""
        yaml = profile_to_yaml(LENIENT_PROFILE)
        
        assert "allow_warn_merge: true" in yaml
    
    def test_custom_rules_in_yaml(self):
        """Test custom rules appear in YAML."""
        yaml = profile_to_yaml(SECURITY_FOCUSED_PROFILE)
        
        assert "custom_rules:" in yaml
        assert "check-for-secrets-in-tests" in yaml


class TestShouldRunCheck:
    """Tests for should_run_check function."""
    
    def test_should_run_test(self):
        """Test checking if test should run."""
        assert should_run_check(STANDARD_PROFILE, "test") is True
        assert should_run_check(LENIENT_PROFILE, "test") is False
    
    def test_should_run_lint(self):
        """Test checking if lint should run."""
        assert should_run_check(STANDARD_PROFILE, "lint") is True
        assert should_run_check(MINIMAL_PROFILE, "lint") is False
    
    def test_should_run_typecheck(self):
        """Test checking if typecheck should run."""
        assert should_run_check(STANDARD_PROFILE, "typecheck") is True
        assert should_run_check(LENIENT_PROFILE, "typecheck") is False
    
    def test_should_run_format(self):
        """Test checking if format should run."""
        assert should_run_check(STANDARD_PROFILE, "format") is True
        assert should_run_check(LENIENT_PROFILE, "format") is False
    
    def test_should_run_security_dep(self):
        """Test checking if security dep scan should run."""
        assert should_run_check(MINIMAL_PROFILE, "security_dep") is True
    
    def test_should_run_security_sec(self):
        """Test checking if security secret scan should run."""
        assert should_run_check(MINIMAL_PROFILE, "security_sec") is True
    
    def test_should_run_security_sast(self):
        """Test checking if SAST should run."""
        assert should_run_check(STANDARD_PROFILE, "security_sast") is False
        assert should_run_check(STRICT_PROFILE, "security_sast") is True
    
    def test_unknown_check_defaults_true(self):
        """Test unknown check types default to True."""
        assert should_run_check(STANDARD_PROFILE, "unknown_check") is True


class TestReviewProfile:
    """Tests for ReviewProfile dataclass."""
    
    def test_applies_to_language(self):
        """Test applies_to_language method."""
        profile = STANDARD_PROFILE
        
        # All profiles apply to all languages by default
        assert profile.applies_to_language("python") is True
        assert profile.applies_to_language("rust") is True
        assert profile.applies_to_language("node") is True
    
    def test_profile_creation(self):
        """Test creating a ReviewProfile."""
        profile = ReviewProfile(
            name="Test",
            level=ProfileLevel.STANDARD,
            description="Test profile",
            settings=ProfileSettings(),
        )
        
        assert profile.name == "Test"
        assert profile.description == "Test profile"


class TestProfileLevel:
    """Tests for ProfileLevel enum."""
    
    def test_level_values(self):
        """Test profile level values."""
        assert ProfileLevel.STANDARD.value == "STANDARD"
        assert ProfileLevel.STRICT.value == "STRICT"
        assert ProfileLevel.LENIENT.value == "LENIENT"
        assert ProfileLevel.MINIMAL.value == "MINIMAL"
        assert ProfileLevel.SECURITY_FOCUSED.value == "SECURITY_FOCUSED"
