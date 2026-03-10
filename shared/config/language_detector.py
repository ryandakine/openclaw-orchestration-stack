"""
Language Detector

Auto-detect repository language and monorepo structure from file presence.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Any


class Language(Enum):
    """Supported programming languages."""
    PYTHON = "python"
    RUST = "rust"
    NODE = "node"
    GO = "go"
    JAVA = "java"
    MIXED = "mixed"


# Language detection markers
LANGUAGE_MARKERS = {
    Language.PYTHON: [
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Pipfile",
        "poetry.lock",
        "*.py",
    ],
    Language.RUST: [
        "Cargo.toml",
        "Cargo.lock",
        "*.rs",
    ],
    Language.NODE: [
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "tsconfig.json",
        "*.js",
        "*.ts",
        "*.jsx",
        "*.tsx",
    ],
    Language.GO: [
        "go.mod",
        "go.sum",
        "*.go",
    ],
    Language.JAVA: [
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "*.java",
    ],
}

# Priority markers (these strongly indicate the language)
PRIORITY_MARKERS = {
    Language.PYTHON: ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
    Language.RUST: ["Cargo.toml"],
    Language.NODE: ["package.json", "tsconfig.json"],
    Language.GO: ["go.mod"],
    Language.JAVA: ["pom.xml", "build.gradle", "build.gradle.kts"],
}


@dataclass
class LanguageDetectionResult:
    """Result of language detection."""
    primary_language: Language
    detected_languages: dict[Language, float] = field(default_factory=dict)
    confidence: float = 0.0
    markers_found: dict[Language, list[str]] = field(default_factory=dict)


@dataclass
class MonorepoStructure:
    """Detected monorepo structure."""
    is_monorepo: bool = False
    packages: dict[str, Path] = field(default_factory=dict)
    language_per_package: dict[str, Language] = field(default_factory=dict)
    workspace_root: Optional[Path] = None
    workspace_type: Optional[str] = None  # npm, cargo, poetry, etc.


def _has_marker(repo_path: Path, marker: str) -> bool:
    """Check if a marker exists in the repository."""
    if marker.startswith("*."):
        # Glob pattern for file extensions
        extension = marker[1:]  # e.g., ".py"
        for file_path in repo_path.rglob(f"*{extension}"):
            if file_path.is_file():
                return True
        return False
    else:
        # Specific file
        return (repo_path / marker).exists()


def _count_files_with_extension(repo_path: Path, extension: str) -> int:
    """Count files with given extension."""
    count = 0
    for file_path in repo_path.rglob(f"*{extension}"):
        if file_path.is_file():
            count += 1
    return count


def detect_language(repo_path: Path | str, min_confidence: float = 0.3) -> LanguageDetectionResult:
    """
    Auto-detect the primary language of a repository.
    
    Args:
        repo_path: Path to repository root
        min_confidence: Minimum confidence threshold for considering a language detected
        
    Returns:
        LanguageDetectionResult with primary language and confidence scores
    """
    repo_path = Path(repo_path).resolve()
    
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository path not found: {repo_path}")
    
    if not repo_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {repo_path}")
    
    detected = {}
    markers_found = {}
    
    # Check each language's markers
    for language, markers in LANGUAGE_MARKERS.items():
        found_markers = []
        score = 0.0
        
        for marker in markers:
            if _has_marker(repo_path, marker):
                found_markers.append(marker)
                
                # Priority markers get higher weight
                if marker in PRIORITY_MARKERS.get(language, []):
                    score += 2.0
                elif marker.startswith("*."):
                    # File extension markers - weight by file count (capped)
                    count = _count_files_with_extension(repo_path, marker[1:])
                    score += min(count * 0.1, 1.0)  # Cap at 1.0 for many files
                else:
                    score += 1.0
        
        if found_markers:
            detected[language] = score
            markers_found[language] = found_markers
    
    # Normalize scores to confidence values (0-1)
    total_score = sum(detected.values())
    if total_score > 0:
        detected = {lang: score / total_score for lang, score in detected.items()}
    
    # Determine primary language
    if not detected:
        return LanguageDetectionResult(
            primary_language=Language.MIXED,
            detected_languages={},
            confidence=0.0,
            markers_found={},
        )
    
    # Find language with highest confidence
    primary = max(detected.items(), key=lambda x: x[1])
    primary_language = primary[0]
    confidence = primary[1]
    
    # Check if it's truly mixed (multiple languages with significant presence)
    significant_languages = [
        lang for lang, conf in detected.items() if conf >= min_confidence
    ]
    
    if len(significant_languages) > 1:
        primary_language = Language.MIXED
    
    return LanguageDetectionResult(
        primary_language=primary_language,
        detected_languages=detected,
        confidence=confidence,
        markers_found=markers_found,
    )


def detect_monorepo_structure(repo_path: Path | str) -> MonorepoStructure:
    """
    Detect monorepo structure and find packages with different languages.
    
    Args:
        repo_path: Path to repository root
        
    Returns:
        MonorepoStructure describing the repository layout
    """
    repo_path = Path(repo_path).resolve()
    
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository path not found: {repo_path}")
    
    structure = MonorepoStructure(workspace_root=repo_path)
    packages = {}
    language_per_package = {}
    
    # Check for npm/yarn/pnpm workspaces
    package_json = repo_path / "package.json"
    if package_json.exists():
        import json
        try:
            content = json.loads(package_json.read_text())
            if "workspaces" in content:
                structure.is_monorepo = True
                # Detect package manager
                if (repo_path / "pnpm-workspace.yaml").exists() or (repo_path / "pnpm-lock.yaml").exists():
                    structure.workspace_type = "pnpm"
                elif (repo_path / "yarn.lock").exists():
                    structure.workspace_type = "yarn"
                else:
                    structure.workspace_type = "npm"
                
                # Parse workspace patterns
                workspace_patterns = content["workspaces"]
                if isinstance(workspace_patterns, dict):
                    workspace_patterns = workspace_patterns.get("packages", [])
                
                for pattern in workspace_patterns:
                    # Convert pattern like "packages/*" to glob
                    if "*" in pattern:
                        base_path = pattern.replace("/*", "").replace("*", "")
                        packages_dir = repo_path / base_path
                        if packages_dir.exists():
                            for pkg_dir in packages_dir.iterdir():
                                if pkg_dir.is_dir() and (pkg_dir / "package.json").exists():
                                    pkg_name = pkg_dir.name
                                    packages[pkg_name] = pkg_dir
                                    language_per_package[pkg_name] = Language.NODE
                    else:
                        pkg_dir = repo_path / pattern
                        if pkg_dir.exists():
                            pkg_name = pkg_dir.name
                            packages[pkg_name] = pkg_dir
                            language_per_package[pkg_name] = Language.NODE
        except (json.JSONDecodeError, IOError):
            pass
    
    # Check for pnpm workspace (pnpm-workspace.yaml)
    pnpm_workspace = repo_path / "pnpm-workspace.yaml"
    if pnpm_workspace.exists() and not structure.is_monorepo:
        try:
            import yaml
            content = yaml.safe_load(pnpm_workspace.read_text())
            if content and "packages" in content:
                structure.is_monorepo = True
                structure.workspace_type = "pnpm"
                
                for pattern in content["packages"]:
                    if "*" in pattern:
                        base_path = pattern.replace("/*", "").replace("*", "")
                        packages_dir = repo_path / base_path
                        if packages_dir.exists():
                            for pkg_dir in packages_dir.iterdir():
                                if pkg_dir.is_dir() and (pkg_dir / "package.json").exists():
                                    pkg_name = pkg_dir.name
                                    packages[pkg_name] = pkg_dir
                                    language_per_package[pkg_name] = Language.NODE
                    else:
                        pkg_dir = repo_path / pattern
                        if pkg_dir.exists():
                            pkg_name = pkg_dir.name
                            packages[pkg_name] = pkg_dir
                            language_per_package[pkg_name] = Language.NODE
        except (ImportError, IOError, yaml.YAMLError):
            pass
    
    # Check for Cargo workspaces
    cargo_toml = repo_path / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text()
            if "[workspace]" in content:
                structure.is_monorepo = True
                structure.workspace_type = "cargo"
                
                # Parse workspace members
                import re
                members_match = re.search(r'members\s*=\s*\[(.*?)\]', content, re.DOTALL)
                if members_match:
                    members_str = members_match.group(1)
                    # Extract quoted strings
                    members = re.findall(r'"([^"]+)"', members_str)
                    
                    for member in members:
                        pkg_dir = repo_path / member
                        if pkg_dir.exists():
                            pkg_name = member.replace("/", "_").replace("-", "_")
                            packages[pkg_name] = pkg_dir
                            language_per_package[pkg_name] = Language.RUST
        except IOError:
            pass
    
    # Check for Python monorepo patterns
    pyproject_toml = repo_path / "pyproject.toml"
    if pyproject_toml.exists():
        try:
            import tomli
            content = tomli.loads(pyproject_toml.read_text())
            
            # Poetry packages
            if "tool" in content and "poetry" in content["tool"]:
                poetry = content["tool"]["poetry"]
                if "packages" in poetry:
                    structure.is_monorepo = True
                    structure.workspace_type = "poetry"
                    
                    for pkg in poetry["packages"]:
                        include = pkg.get("include", "")
                        from_path = pkg.get("from", ".")
                        pkg_dir = repo_path / from_path / include
                        if pkg_dir.exists():
                            pkg_name = include
                            packages[pkg_name] = pkg_dir
                            language_per_package[pkg_name] = Language.PYTHON
            
            # PDM/Hatch monorepo
            if "tool" in content:
                if "pdm" in content["tool"] or "hatch" in content["tool"]:
                    # Look for packages directory
                    for pkg_dir in repo_path.iterdir():
                        if pkg_dir.is_dir():
                            if (pkg_dir / "pyproject.toml").exists():
                                structure.is_monorepo = True
                                if "pdm" in content["tool"]:
                                    structure.workspace_type = "pdm"
                                else:
                                    structure.workspace_type = "hatch"
                                
                                pkg_name = pkg_dir.name
                                packages[pkg_name] = pkg_dir
                                language_per_package[pkg_name] = Language.PYTHON
        except (ImportError, IOError, Exception):
            # Try basic pattern matching if tomli not available
            pass
    
    # Detect languages for each package
    for pkg_name, pkg_path in packages.items():
        if pkg_name not in language_per_package:
            result = detect_language(pkg_path)
            language_per_package[pkg_name] = result.primary_language
    
    structure.packages = packages
    structure.language_per_package = language_per_package
    
    return structure


def get_recommended_commands(language: Language) -> dict[str, list[str]]:
    """
    Get recommended commands for a language.
    
    Args:
        language: The programming language
        
    Returns:
        Dictionary of command categories and their commands
    """
    commands = {
        Language.PYTHON: {
            "test": ["pytest -q", "python -m pytest"],
            "lint": ["ruff check .", "flake8", "pylint src"],
            "typecheck": ["mypy .", "mypy src"],
            "format": ["black --check .", "ruff format --check ."],
            "security": ["pip-audit -r requirements.txt", "bandit -r src"],
        },
        Language.RUST: {
            "test": ["cargo test"],
            "lint": ["cargo clippy -- -D warnings", "cargo clippy"],
            "typecheck": [],  # Rust is compiled, no separate typecheck
            "format": ["cargo fmt --check"],
            "security": ["cargo audit", "cargo deny check"],
        },
        Language.NODE: {
            "test": ["npm test", "yarn test", "pnpm test"],
            "lint": ["npm run lint", "eslint .", "npx eslint ."],
            "typecheck": ["npx tsc --noEmit", "npm run typecheck"],
            "format": ["npm run format:check", "prettier --check ."],
            "security": ["npm audit", "npm audit --audit-level moderate"],
        },
        Language.GO: {
            "test": ["go test ./..."],
            "lint": ["golangci-lint run", "go vet ./..."],
            "typecheck": [],  # Go is compiled, no separate typecheck
            "format": ["gofmt -l .", "go fmt ./..."],
            "security": ["gosec ./...", "nancy sleuth"],
        },
        Language.JAVA: {
            "test": ["./mvnw test", "./gradlew test"],
            "lint": ["./mvnw checkstyle:check", "./gradlew check"],
            "typecheck": [],  # Java is compiled
            "format": ["./mvnw spotless:check"],
            "security": ["./mvnw dependency-check:check"],
        },
        Language.MIXED: {
            "test": [],
            "lint": [],
            "typecheck": [],
            "format": [],
            "security": [],
        },
    }
    
    return commands.get(language, commands[Language.MIXED])


def detect_typescript(repo_path: Path | str) -> dict[str, Any]:
    """
    Detect TypeScript configuration and settings.
    
    Args:
        repo_path: Path to repository root
        
    Returns:
        Dictionary with TypeScript detection results
    """
    repo_path = Path(repo_path).resolve()
    result = {
        "has_typescript": False,
        "tsconfig_path": None,
        "is_strict": False,
        "compiler_options": {},
    }
    
    tsconfig_path = repo_path / "tsconfig.json"
    if tsconfig_path.exists():
        result["has_typescript"] = True
        result["tsconfig_path"] = tsconfig_path
        
        try:
            import json
            content = json.loads(tsconfig_path.read_text())
            compiler_options = content.get("compilerOptions", {})
            result["compiler_options"] = compiler_options
            result["is_strict"] = compiler_options.get("strict", False)
        except (json.JSONDecodeError, IOError):
            pass
    
    # Also check for TypeScript files
    ts_files = list(repo_path.rglob("*.ts"))
    tsx_files = list(repo_path.rglob("*.tsx"))
    if ts_files or tsx_files:
        result["has_typescript"] = True
        result["ts_file_count"] = len(ts_files) + len(tsx_files)
    
    return result


def detect_node_package_manager(repo_path: Path | str) -> str:
    """
    Detect the package manager used in a Node.js project.
    
    Args:
        repo_path: Path to repository root
        
    Returns:
        Package manager name: 'npm', 'yarn', 'pnpm', or 'unknown'
    """
    repo_path = Path(repo_path).resolve()
    
    if (repo_path / "pnpm-lock.yaml").exists() or (repo_path / "pnpm-workspace.yaml").exists():
        return "pnpm"
    if (repo_path / "yarn.lock").exists():
        return "yarn"
    if (repo_path / "package-lock.json").exists():
        return "npm"
    
    # Check package.json for packageManager field (npm 7+)
    package_json = repo_path / "package.json"
    if package_json.exists():
        try:
            import json
            content = json.loads(package_json.read_text())
            package_manager = content.get("packageManager", "")
            if package_manager.startswith("pnpm"):
                return "pnpm"
            elif package_manager.startswith("yarn"):
                return "yarn"
            elif package_manager.startswith("npm"):
                return "npm"
        except (json.JSONDecodeError, IOError):
            pass
    
    # Default to npm if package.json exists
    if package_json.exists():
        return "npm"
    
    return "unknown"


# ============================================================================
# MONOREPO SUPPORT FUNCTIONS
# ============================================================================

def get_workspace_packages(repo_path: Path | str) -> dict[str, dict]:
    """
    Get workspace packages for npm, Cargo, and Poetry workspaces.
    
    Args:
        repo_path: Path to repository root
        
    Returns:
        Dictionary mapping package names to package info dicts with:
        - path: Path to package
        - language: Language enum
        - workspace_type: Type of workspace (npm, cargo, poetry)
        - commands: Recommended commands for this package
    """
    repo_path = Path(repo_path).resolve()
    packages = {}
    
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository path not found: {repo_path}")
    
    # Check for npm workspaces
    package_json = repo_path / "package.json"
    if package_json.exists():
        import json
        try:
            content = json.loads(package_json.read_text())
            if "workspaces" in content:
                workspace_patterns = content["workspaces"]
                if isinstance(workspace_patterns, dict):
                    workspace_patterns = workspace_patterns.get("packages", [])
                
                for pattern in workspace_patterns:
                    if "*" in pattern:
                        base_path = pattern.replace("/*", "").replace("*", "")
                        packages_dir = repo_path / base_path
                        if packages_dir.exists():
                            for pkg_dir in packages_dir.iterdir():
                                if pkg_dir.is_dir() and (pkg_dir / "package.json").exists():
                                    try:
                                        pkg_content = json.loads((pkg_dir / "package.json").read_text())
                                        pkg_name = pkg_content.get("name", pkg_dir.name)
                                        packages[pkg_name] = {
                                            "path": pkg_dir,
                                            "language": Language.NODE,
                                            "workspace_type": "npm",
                                            "commands": get_recommended_commands(Language.NODE),
                                        }
                                    except (json.JSONDecodeError, IOError):
                                        pkg_name = pkg_dir.name
                                        packages[pkg_name] = {
                                            "path": pkg_dir,
                                            "language": Language.NODE,
                                            "workspace_type": "npm",
                                            "commands": get_recommended_commands(Language.NODE),
                                        }
                    else:
                        pkg_dir = repo_path / pattern
                        if pkg_dir.exists() and (pkg_dir / "package.json").exists():
                            try:
                                pkg_content = json.loads((pkg_dir / "package.json").read_text())
                                pkg_name = pkg_content.get("name", pkg_dir.name)
                            except (json.JSONDecodeError, IOError):
                                pkg_name = pkg_dir.name
                            packages[pkg_name] = {
                                "path": pkg_dir,
                                "language": Language.NODE,
                                "workspace_type": "npm",
                                "commands": get_recommended_commands(Language.NODE),
                            }
        except (json.JSONDecodeError, IOError):
            pass
    
    # Check for Cargo workspaces
    cargo_toml = repo_path / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text()
            if "[workspace]" in content:
                import re
                members_match = re.search(r'members\s*=\s*\[(.*?)\]', content, re.DOTALL)
                if members_match:
                    members_str = members_match.group(1)
                    members = re.findall(r'"([^"]+)"', members_str)
                    
                    for member in members:
                        pkg_dir = repo_path / member
                        if pkg_dir.exists():
                            # Try to get package name from Cargo.toml
                            pkg_name = member.replace("/", "_").replace("-", "_")
                            member_cargo = pkg_dir / "Cargo.toml"
                            if member_cargo.exists():
                                try:
                                    member_content = member_cargo.read_text()
                                    name_match = re.search(r'^\s*name\s*=\s*"([^"]+)"', member_content, re.MULTILINE)
                                    if name_match:
                                        pkg_name = name_match.group(1)
                                except IOError:
                                    pass
                            
                            packages[pkg_name] = {
                                "path": pkg_dir,
                                "language": Language.RUST,
                                "workspace_type": "cargo",
                                "commands": get_recommended_commands(Language.RUST),
                            }
        except IOError:
            pass
    
    # Check for Poetry packages
    pyproject_toml = repo_path / "pyproject.toml"
    if pyproject_toml.exists():
        try:
            content = pyproject_toml.read_text()
            
            # Poetry packages
            if "[tool.poetry]" in content:
                import re
                # Look for packages definition
                packages_match = re.search(r'\[tool\.poetry\.packages\](.*?)(?=\[|$)', content, re.DOTALL)
                if packages_match:
                    pkg_section = packages_match.group(1)
                    includes = re.findall(r'include\s*=\s*"([^"]+)"', pkg_section)
                    for include in includes:
                        pkg_dir = repo_path / include
                        if pkg_dir.exists():
                            packages[include] = {
                                "path": pkg_dir,
                                "language": Language.PYTHON,
                                "workspace_type": "poetry",
                                "commands": get_recommended_commands(Language.PYTHON),
                            }
                
                # Also check for standard src or package directory structure
                for pkg_dir in repo_path.iterdir():
                    if pkg_dir.is_dir():
                        if (pkg_dir / "__init__.py").exists() or (pkg_dir / "pyproject.toml").exists():
                            pkg_name = pkg_dir.name
                            if pkg_name not in packages and not pkg_name.startswith("."):
                                packages[pkg_name] = {
                                    "path": pkg_dir,
                                    "language": Language.PYTHON,
                                    "workspace_type": "poetry",
                                    "commands": get_recommended_commands(Language.PYTHON),
                                }
        except IOError:
            pass
    
    return packages


def detect_languages_per_directory(repo_path: Path | str) -> dict[Path, Language]:
    """
    Map directories to their detected languages.
    
    This is useful for mixed monorepos where different directories
    contain different languages.
    
    Args:
        repo_path: Path to repository root
        
    Returns:
        Dictionary mapping directory paths to Language enums
    """
    repo_path = Path(repo_path).resolve()
    dir_languages = {}
    
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository path not found: {repo_path}")
    
    # First check if there's a workspace structure
    workspace_packages = get_workspace_packages(repo_path)
    for pkg_name, pkg_info in workspace_packages.items():
        dir_languages[pkg_info["path"]] = pkg_info["language"]
    
    # Also scan common monorepo directories
    common_dirs = ["apps", "libs", "packages", "services", "tools", "components"]
    for dir_name in common_dirs:
        dir_path = repo_path / dir_name
        if dir_path.exists() and dir_path.is_dir():
            for subdir in dir_path.iterdir():
                if subdir.is_dir() and subdir not in dir_languages:
                    result = detect_language(subdir)
                    if result.primary_language != Language.MIXED:
                        dir_languages[subdir] = result.primary_language
    
    return dir_languages


def suggest_review_yaml(repo_path: Path | str) -> str:
    """
    Suggest a review.yaml configuration based on detected languages.
    
    Args:
        repo_path: Path to repository root
        
    Returns:
        Suggested review.yaml content as string
    """
    repo_path = Path(repo_path)
    
    # Detect language and structure
    lang_result = detect_language(repo_path)
    mono_structure = detect_monorepo_structure(repo_path)
    workspace_packages = get_workspace_packages(repo_path)
    dir_languages = detect_languages_per_directory(repo_path)
    
    lines = [
        "# Auto-generated .openclaw/review.yaml",
        f"# Detected languages: {', '.join(l.value for l in lang_result.detected_languages.keys())}",
        "",
        "repo:",
    ]
    
    if mono_structure.is_monorepo or len(workspace_packages) > 1:
        lines.append(f"  language: mixed  # {mono_structure.workspace_type or 'mixed'} monorepo detected")
    else:
        lines.append(f"  language: {lang_result.primary_language.value}")
    
    lines.extend([
        "  profile_default: STANDARD",
    ])
    
    # Add workspaces section for monorepos
    if workspace_packages or dir_languages:
        lines.extend([
            "",
            "workspaces:",
        ])
        
        # Use workspace packages if available
        if workspace_packages:
            for pkg_name, pkg_info in workspace_packages.items():
                rel_path = pkg_info["path"].relative_to(repo_path) if pkg_info["path"].is_relative_to(repo_path) else pkg_info["path"]
                lines.extend([
                    f"  {pkg_name}:",
                    f'    path: "{rel_path}"',
                    f'    language: {pkg_info["language"].value}',
                    "    commands:",
                ])
                # Add recommended commands
                cmds = pkg_info.get("commands", {})
                if cmds.get("test"):
                    lines.append(f'      test: {cmds["test"][:1]}')  # First test command only
        
        # Add directory-based languages
        elif dir_languages:
            for dir_path, language in dir_languages.items():
                rel_path = dir_path.relative_to(repo_path) if dir_path.is_relative_to(repo_path) else dir_path
                pkg_name = dir_path.name
                lines.extend([
                    f"  {pkg_name}:",
                    f'    path: "{rel_path}"',
                    f'    language: {language.value}',
                    "    commands:",
                ])
                cmds = get_recommended_commands(language)
                if cmds.get("test"):
                    lines.append(f'      test: {cmds["test"][:1]}')
    
    lines.extend([
        "",
        "commands:",
    ])
    
    # Add commands based on detected languages
    all_commands = {
        "test": [],
        "lint": [],
        "typecheck": [],
        "format": [],
    }
    
    languages_to_check = [lang_result.primary_language]
    if lang_result.primary_language == Language.MIXED:
        # Include all detected languages
        languages_to_check = list(lang_result.detected_languages.keys())
    
    for lang in languages_to_check:
        if lang == Language.MIXED:
            continue
        recs = get_recommended_commands(lang)
        for category in all_commands:
            if recs.get(category):
                all_commands[category].extend(recs[category][:1])  # Take first recommendation
    
    for category, cmds in all_commands.items():
        if cmds:
            lines.append(f"  {category}:")
            for cmd in cmds:
                lines.append(f'    - "{cmd}"')
    
    # Add security section
    lines.extend([
        "",
        "security:",
        "  dependency_scan:",
    ])
    
    for lang in languages_to_check:
        if lang == Language.MIXED:
            continue
        recs = get_recommended_commands(lang)
        for cmd in recs.get("security", [])[:1]:
            lines.append(f'    - "{cmd}"')
    
    lines.extend([
        "  secret_scan:",
        '    - "gitleaks detect"',
        "",
        "policy:",
        "  allow_warn_merge: false",
        "  fail_on_warn_over: 10",
        "  require_approval: true",
        "  max_review_time_minutes: 30",
    ])
    
    return "\n".join(lines)
