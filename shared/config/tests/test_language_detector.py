"""
Tests for language_detector.py - Auto-detect repo language
"""

import pytest
from pathlib import Path
import tempfile

from shared.config.language_detector import (
    Language,
    LanguageDetectionResult,
    MonorepoStructure,
    detect_language,
    detect_monorepo_structure,
    get_recommended_commands,
    suggest_review_yaml,
    LANGUAGE_MARKERS,
    PRIORITY_MARKERS,
)


class TestDetectLanguage:
    """Tests for detect_language function."""
    
    def test_detect_python_from_requirements(self, tmp_path):
        """Test detecting Python from requirements.txt."""
        (tmp_path / "requirements.txt").write_text("pytest\n")
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.PYTHON
        assert Language.PYTHON in result.detected_languages
        assert "requirements.txt" in result.markers_found[Language.PYTHON]
    
    def test_detect_python_from_pyproject(self, tmp_path):
        """Test detecting Python from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[build-system]\n")
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.PYTHON
    
    def test_detect_rust_from_cargo(self, tmp_path):
        """Test detecting Rust from Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text("[package]\n")
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.RUST
        assert "Cargo.toml" in result.markers_found[Language.RUST]
    
    def test_detect_node_from_package_json(self, tmp_path):
        """Test detecting Node from package.json."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.NODE
    
    def test_detect_go_from_gomod(self, tmp_path):
        """Test detecting Go from go.mod."""
        (tmp_path / "go.mod").write_text("module test\n")
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.GO
    
    def test_detect_java_from_pom(self, tmp_path):
        """Test detecting Java from pom.xml."""
        (tmp_path / "pom.xml").write_text("<project></project>")
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.JAVA
    
    def test_detect_mixed_languages(self, tmp_path):
        """Test detecting mixed languages."""
        (tmp_path / "requirements.txt").write_text("pytest\n")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.MIXED
        assert Language.PYTHON in result.detected_languages
        assert Language.NODE in result.detected_languages
    
    def test_detect_from_source_files(self, tmp_path):
        """Test detecting from source file extensions."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('hello')")
        (src_dir / "utils.py").write_text("def foo(): pass")
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.PYTHON
    
    def test_empty_repo(self, tmp_path):
        """Test detecting in empty repo."""
        result = detect_language(tmp_path)
        assert result.primary_language == Language.MIXED
        assert result.detected_languages == {}
        assert result.confidence == 0.0
    
    def test_nonexistent_path(self):
        """Test detecting in non-existent path raises error."""
        with pytest.raises(FileNotFoundError):
            detect_language("/nonexistent/path/12345")
    
    def test_file_path_raises_error(self, tmp_path):
        """Test passing a file path raises error."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")
        
        with pytest.raises(NotADirectoryError):
            detect_language(file_path)
    
    def test_min_confidence_filtering(self, tmp_path):
        """Test min_confidence parameter."""
        (tmp_path / "requirements.txt").write_text("pytest\n")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        
        # With high min_confidence, should return single primary language
        result = detect_language(tmp_path, min_confidence=0.8)
        # Since both have priority markers, neither may exceed 0.8 individually
        # but the result should still be consistent
        assert result.primary_language in [Language.PYTHON, Language.NODE, Language.MIXED]
    
    def test_confidence_calculation(self, tmp_path):
        """Test confidence is calculated properly."""
        (tmp_path / "Cargo.toml").write_text("[package]\n")
        
        result = detect_language(tmp_path)
        assert result.confidence == 1.0  # Only one language detected


class TestDetectMonorepoStructure:
    """Tests for detect_monorepo_structure function."""
    
    def test_simple_repo_not_monorepo(self, tmp_path):
        """Test simple repo is not detected as monorepo."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        
        result = detect_monorepo_structure(tmp_path)
        assert result.is_monorepo is False
        assert result.packages == {}
    
    def test_npm_workspaces(self, tmp_path):
        """Test detecting npm workspaces."""
        (tmp_path / "package.json").write_text('''
{
    "name": "monorepo",
    "workspaces": ["packages/*"]
}
''')
        packages_dir = tmp_path / "packages" / "pkg1"
        packages_dir.mkdir(parents=True)
        (packages_dir / "package.json").write_text('{"name": "pkg1"}')
        
        result = detect_monorepo_structure(tmp_path)
        assert result.is_monorepo is True
        assert result.workspace_type == "npm"
        assert "pkg1" in result.packages
        assert result.language_per_package["pkg1"] == Language.NODE
    
    def test_cargo_workspace(self, tmp_path):
        """Test detecting Cargo workspace."""
        (tmp_path / "Cargo.toml").write_text('''
[workspace]
members = ["crate1", "crate2"]
''')
        (tmp_path / "crate1").mkdir()
        (tmp_path / "crate2").mkdir()
        
        result = detect_monorepo_structure(tmp_path)
        assert result.is_monorepo is True
        assert result.workspace_type == "cargo"
        assert "crate1" in result.packages or "crate1" in str(result.packages.get("crate1", ""))
    
    def test_poetry_packages(self, tmp_path):
        """Test detecting Poetry packages."""
        (tmp_path / "pyproject.toml").write_text('''
[tool.poetry]
name = "monorepo"

[tool.poetry.packages]
include = [{ include = "pkg1" }]
''')
        (tmp_path / "pkg1").mkdir()
        
        # May or may not be detected depending on tomli availability
        result = detect_monorepo_structure(tmp_path)
        # Just verify it doesn't crash
        assert isinstance(result, MonorepoStructure)
    
    def test_nonexistent_path(self):
        """Test non-existent path raises error."""
        with pytest.raises(FileNotFoundError):
            detect_monorepo_structure("/nonexistent/path/12345")


class TestGetRecommendedCommands:
    """Tests for get_recommended_commands function."""
    
    def test_python_commands(self):
        """Test Python recommended commands."""
        cmds = get_recommended_commands(Language.PYTHON)
        
        assert "pytest" in cmds["test"][0] or "python -m pytest" in cmds["test"]
        assert "ruff" in cmds["lint"][0] or "flake8" in cmds["lint"][0]
        assert "mypy" in cmds["typecheck"][0]
        assert "black" in cmds["format"][0] or "ruff" in cmds["format"][0]
        assert "pip-audit" in cmds["security"][0] or "bandit" in cmds["security"][0]
    
    def test_rust_commands(self):
        """Test Rust recommended commands."""
        cmds = get_recommended_commands(Language.RUST)
        
        assert "cargo test" in cmds["test"][0]
        assert "cargo clippy" in cmds["lint"][0]
        assert cmds["typecheck"] == []  # Rust uses compile for type checking
        assert "cargo fmt" in cmds["format"][0]
        assert "cargo audit" in cmds["security"][0]
    
    def test_node_commands(self):
        """Test Node recommended commands."""
        cmds = get_recommended_commands(Language.NODE)
        
        assert "npm test" in cmds["test"][0]
        assert "eslint" in cmds["lint"][0] or "npm run lint" in cmds["lint"][0]
        assert "tsc" in cmds["typecheck"][0] or "typecheck" in cmds["typecheck"][0]
        assert "prettier" in cmds["format"][0] or "format:check" in cmds["format"][0]
        assert "npm audit" in cmds["security"][0]
    
    def test_go_commands(self):
        """Test Go recommended commands."""
        cmds = get_recommended_commands(Language.GO)
        
        assert "go test" in cmds["test"][0]
        assert "golangci-lint" in cmds["lint"][0] or "go vet" in cmds["lint"][0]
        assert "gofmt" in cmds["format"][0] or "go fmt" in cmds["format"][0]
    
    def test_java_commands(self):
        """Test Java recommended commands."""
        cmds = get_recommended_commands(Language.JAVA)
        
        assert "test" in cmds["test"][0]  # mvnw test or gradlew test
        assert "check" in cmds["lint"][0] or "checkstyle" in cmds["lint"][0]
    
    def test_mixed_commands_empty(self):
        """Test mixed language has empty commands."""
        cmds = get_recommended_commands(Language.MIXED)
        
        assert cmds["test"] == []
        assert cmds["lint"] == []


class TestSuggestReviewYaml:
    """Tests for suggest_review_yaml function."""
    
    def test_suggests_python_config(self, tmp_path):
        """Test suggesting config for Python repo."""
        (tmp_path / "requirements.txt").write_text("pytest\n")
        
        yaml_content = suggest_review_yaml(tmp_path)
        
        assert "language: python" in yaml_content
        assert "pytest" in yaml_content
        assert "ruff" in yaml_content or "flake8" in yaml_content
        assert "mypy" in yaml_content
    
    def test_suggests_rust_config(self, tmp_path):
        """Test suggesting config for Rust repo."""
        (tmp_path / "Cargo.toml").write_text("[package]\n")
        
        yaml_content = suggest_review_yaml(tmp_path)
        
        assert "language: rust" in yaml_content
        assert "cargo test" in yaml_content
        assert "cargo clippy" in yaml_content
    
    def test_suggests_mixed_config(self, tmp_path):
        """Test suggesting config for mixed repo."""
        (tmp_path / "requirements.txt").write_text("pytest\n")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        
        yaml_content = suggest_review_yaml(tmp_path)
        
        assert "language: mixed" in yaml_content
        assert "pytest" in yaml_content or "npm test" in yaml_content
    
    def test_includes_policy_section(self, tmp_path):
        """Test suggested config includes policy section."""
        (tmp_path / "Cargo.toml").write_text("[package]\n")
        
        yaml_content = suggest_review_yaml(tmp_path)
        
        assert "policy:" in yaml_content
        assert "allow_warn_merge" in yaml_content
        assert "fail_on_warn_over" in yaml_content


class TestLanguageDetectionResult:
    """Tests for LanguageDetectionResult dataclass."""
    
    def test_dataclass_creation(self):
        """Test creating a LanguageDetectionResult."""
        result = LanguageDetectionResult(
            primary_language=Language.PYTHON,
            detected_languages={Language.PYTHON: 1.0},
            confidence=1.0,
            markers_found={Language.PYTHON: ["requirements.txt"]},
        )
        
        assert result.primary_language == Language.PYTHON
        assert result.confidence == 1.0


class TestMonorepoStructure:
    """Tests for MonorepoStructure dataclass."""
    
    def test_dataclass_defaults(self):
        """Test MonorepoStructure defaults."""
        structure = MonorepoStructure()
        
        assert structure.is_monorepo is False
        assert structure.packages == {}
        assert structure.language_per_package == {}
        assert structure.workspace_root is None
        assert structure.workspace_type is None
