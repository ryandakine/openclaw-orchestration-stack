"""
Tests for Node.js/TypeScript support in language_detector and command_runner.
"""

import json
import pytest
from pathlib import Path

from shared.config.language_detector import (
    Language,
    detect_language,
    detect_monorepo_structure,
    detect_typescript,
    detect_node_package_manager,
    get_recommended_commands,
)
from shared.config.command_runner import (
    NodeOutputParser,
    ParsedNodeOutput,
)


class TestNodeDetection:
    """Tests for Node.js language detection."""
    
    def test_detect_node_from_package_json(self, tmp_path):
        """Test detecting Node from package.json."""
        (tmp_path / "package.json").write_text('{"name": "test-project"}')
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.NODE
        assert "package.json" in result.markers_found[Language.NODE]
    
    def test_detect_node_from_tsconfig(self, tmp_path):
        """Test detecting Node from tsconfig.json."""
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.NODE
        assert "tsconfig.json" in result.markers_found[Language.NODE]
    
    def test_detect_node_from_js_files(self, tmp_path):
        """Test detecting Node from .js files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "index.js").write_text("console.log('hello');")
        (src_dir / "utils.js").write_text("module.exports = {};")
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.NODE
    
    def test_detect_node_from_ts_files(self, tmp_path):
        """Test detecting Node from .ts files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "index.ts").write_text("const x: number = 1;")
        (src_dir / "utils.ts").write_text("export function foo() {}")
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.NODE
    
    def test_detect_node_with_lockfiles(self, tmp_path):
        """Test detecting Node with various lockfiles."""
        # Test package-lock.json
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "package-lock.json").write_text('{"lockfileVersion": 2}')
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.NODE
    
    def test_detect_node_from_jsx_tsx(self, tmp_path):
        """Test detecting Node from JSX/TSX files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "App.jsx").write_text("const App = () => <div />;")
        (src_dir / "Component.tsx").write_text("const Component = () => <div />;")
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.NODE


class TestPackageJsonParsing:
    """Tests for package.json parsing."""
    
    def test_basic_package_json(self, tmp_path):
        """Test basic package.json parsing."""
        package_content = {
            "name": "test-project",
            "version": "1.0.0",
            "scripts": {
                "test": "jest",
                "lint": "eslint .",
                "build": "tsc"
            },
            "dependencies": {
                "express": "^4.18.0"
            },
            "devDependencies": {
                "typescript": "^5.0.0"
            }
        }
        
        (tmp_path / "package.json").write_text(json.dumps(package_content))
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.NODE
    
    def test_package_json_with_engines(self, tmp_path):
        """Test package.json with engines field."""
        package_content = {
            "name": "test-project",
            "engines": {
                "node": ">=18.0.0",
                "npm": ">=9.0.0"
            }
        }
        
        (tmp_path / "package.json").write_text(json.dumps(package_content))
        
        result = detect_language(tmp_path)
        assert result.primary_language == Language.NODE
    
    def test_package_json_with_workspaces(self, tmp_path):
        """Test package.json with workspaces."""
        package_content = {
            "name": "monorepo-root",
            "workspaces": ["packages/*"]
        }
        
        (tmp_path / "package.json").write_text(json.dumps(package_content))
        
        # Create a workspace package
        pkg_dir = tmp_path / "packages" / "pkg1"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text('{"name": "pkg1"}')
        
        result = detect_monorepo_structure(tmp_path)
        assert result.is_monorepo is True
        assert result.workspace_type in ["npm", "yarn"]
        assert "pkg1" in result.packages


class TestWorkspaceDetection:
    """Tests for npm/yarn/pnpm workspace detection."""
    
    def test_npm_workspaces_array(self, tmp_path):
        """Test npm workspaces with array format."""
        (tmp_path / "package.json").write_text(json.dumps({
            "name": "monorepo",
            "workspaces": ["packages/*"]
        }))
        
        pkg_dir = tmp_path / "packages" / "api"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text('{"name": "api"}')
        
        result = detect_monorepo_structure(tmp_path)
        assert result.is_monorepo is True
        assert result.workspace_type == "npm"
        assert "api" in result.packages
    
    def test_npm_workspaces_object(self, tmp_path):
        """Test npm workspaces with object format."""
        (tmp_path / "package.json").write_text(json.dumps({
            "name": "monorepo",
            "workspaces": {
                "packages": ["packages/*"]
            }
        }))
        
        pkg_dir = tmp_path / "packages" / "web"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text('{"name": "web"}')
        
        result = detect_monorepo_structure(tmp_path)
        assert result.is_monorepo is True
        assert "web" in result.packages
    
    def test_yarn_workspaces(self, tmp_path):
        """Test yarn workspaces detection."""
        (tmp_path / "package.json").write_text(json.dumps({
            "name": "monorepo",
            "workspaces": ["packages/*"]
        }))
        (tmp_path / "yarn.lock").write_text("")  # Empty yarn.lock
        
        pkg_dir = tmp_path / "packages" / "app"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text('{"name": "app"}')
        
        result = detect_monorepo_structure(tmp_path)
        assert result.is_monorepo is True
        assert result.workspace_type == "yarn"
    
    def test_pnpm_workspace_yaml(self, tmp_path):
        """Test pnpm workspace detection from pnpm-workspace.yaml."""
        (tmp_path / "package.json").write_text('{"name": "monorepo"}')
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n")
        
        pkg_dir = tmp_path / "packages" / "lib"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text('{"name": "lib"}')
        
        result = detect_monorepo_structure(tmp_path)
        assert result.is_monorepo is True
        assert result.workspace_type == "pnpm"
        assert "lib" in result.packages


class TestTypeScriptDetection:
    """Tests for TypeScript detection."""
    
    def test_detect_typescript_from_tsconfig(self, tmp_path):
        """Test detecting TypeScript from tsconfig.json."""
        tsconfig = {
            "compilerOptions": {
                "target": "ES2020",
                "strict": True,
                "module": "commonjs"
            }
        }
        (tmp_path / "tsconfig.json").write_text(json.dumps(tsconfig))
        
        result = detect_typescript(tmp_path)
        assert result["has_typescript"] is True
        assert result["is_strict"] is True
        assert result["tsconfig_path"] is not None
    
    def test_detect_typescript_from_files(self, tmp_path):
        """Test detecting TypeScript from .ts files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "index.ts").write_text("const x: string = 'hello';")
        
        result = detect_typescript(tmp_path)
        assert result["has_typescript"] is True
        assert result["ts_file_count"] == 1
    
    def test_typescript_not_detected(self, tmp_path):
        """Test that pure JS projects don't detect TypeScript."""
        (tmp_path / "index.js").write_text("const x = 'hello';")
        
        result = detect_typescript(tmp_path)
        assert result["has_typescript"] is False


class TestPackageManagerDetection:
    """Tests for package manager detection."""
    
    def test_detect_npm(self, tmp_path):
        """Test npm detection from package-lock.json."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "package-lock.json").write_text('{}')
        
        pm = detect_node_package_manager(tmp_path)
        assert pm == "npm"
    
    def test_detect_yarn(self, tmp_path):
        """Test yarn detection from yarn.lock."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "yarn.lock").write_text('')
        
        pm = detect_node_package_manager(tmp_path)
        assert pm == "yarn"
    
    def test_detect_pnpm(self, tmp_path):
        """Test pnpm detection from pnpm-lock.yaml."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "pnpm-lock.yaml").write_text('')
        
        pm = detect_node_package_manager(tmp_path)
        assert pm == "pnpm"
    
    def test_detect_pnpm_workspace(self, tmp_path):
        """Test pnpm detection from pnpm-workspace.yaml."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "pnpm-workspace.yaml").write_text('packages: []')
        
        pm = detect_node_package_manager(tmp_path)
        assert pm == "pnpm"
    
    def test_detect_from_package_manager_field(self, tmp_path):
        """Test detection from packageManager field in package.json."""
        (tmp_path / "package.json").write_text(json.dumps({
            "name": "test",
            "packageManager": "pnpm@8.0.0"
        }))
        
        pm = detect_node_package_manager(tmp_path)
        assert pm == "pnpm"


class TestNodeRecommendedCommands:
    """Tests for Node.js recommended commands."""
    
    def test_node_commands_structure(self):
        """Test that Node commands have expected structure."""
        cmds = get_recommended_commands(Language.NODE)
        
        assert "test" in cmds
        assert "lint" in cmds
        assert "typecheck" in cmds
        assert "format" in cmds
        assert "security" in cmds
    
    def test_node_test_commands(self):
        """Test Node test commands include npm/yarn/pnpm."""
        cmds = get_recommended_commands(Language.NODE)
        
        assert any("npm test" in cmd for cmd in cmds["test"])
        assert any("yarn test" in cmd for cmd in cmds["test"])
        assert any("pnpm test" in cmd for cmd in cmds["test"])
    
    def test_node_lint_commands(self):
        """Test Node lint commands include eslint."""
        cmds = get_recommended_commands(Language.NODE)
        
        assert any("eslint" in cmd for cmd in cmds["lint"])
    
    def test_node_typecheck_commands(self):
        """Test Node typecheck commands include tsc."""
        cmds = get_recommended_commands(Language.NODE)
        
        assert any("tsc" in cmd for cmd in cmds["typecheck"])
    
    def test_node_security_commands(self):
        """Test Node security commands include npm audit."""
        cmds = get_recommended_commands(Language.NODE)
        
        assert any("npm audit" in cmd for cmd in cmds["security"])


class TestNpmTestOutputParser:
    """Tests for npm test output parsing."""
    
    def test_parse_jest_success(self):
        """Test parsing successful Jest output."""
        output = """
Test Suites: 3 passed, 3 total
Tests:       10 passed, 10 total
Snapshots:   0 total
Time:        1.234s
"""
        result = NodeOutputParser.parse_npm_test(output)
        assert result.success is True
        assert "10 passed" in result.summary
    
    def test_parse_jest_failure(self):
        """Test parsing Jest failure output."""
        output = """
Test Suites: 1 failed, 2 passed, 3 total
Tests:       2 failed, 8 passed, 10 total
"""
        result = NodeOutputParser.parse_npm_test(output)
        assert result.success is False
        assert result.error_count == 2
    
    def test_parse_mocha_output(self):
        """Test parsing Mocha test output."""
        output = """
  Array
    #indexOf()
      ✓ should return -1 when not present
      ✓ should return the index when present

  2 passing (10ms)
"""
        result = NodeOutputParser.parse_npm_test(output)
        assert result.success is True
        assert "2 passing" in result.summary
    
    def test_parse_mocha_failure(self):
        """Test parsing Mocha failure output."""
        output = """
  1 passing (10ms)
  2 failing
"""
        result = NodeOutputParser.parse_npm_test(output)
        assert result.success is False
        assert result.error_count == 2
    
    def test_parse_coverage_summary(self):
        """Test parsing test output with coverage."""
        output = """
Test Suites: 1 passed, 1 total
Tests:       5 passed, 5 total
----------|---------|----------|---------|---------|-------------------
File      | % Stmts | % Branch | % Funcs | % Lines | Uncovered Line #s 
----------|---------|----------|---------|---------|-------------------
All files |   85.71|    75.00 |   80.00 |   85.71 |                   
----------|---------|----------|---------|---------|-------------------
"""
        result = NodeOutputParser.parse_npm_test(output)
        assert result.success is True


class TestEslintOutputParser:
    """Tests for ESLint output parsing."""
    
    def test_parse_eslint_no_issues(self):
        """Test parsing ESLint output with no issues."""
        output = """
✨  Done in 1.23s.
"""
        result = NodeOutputParser.parse_eslint(output)
        assert result.success is True
        assert result.error_count == 0
    
    def test_parse_eslint_errors(self):
        """Test parsing ESLint output with errors."""
        output = """
/home/user/project/src/index.js
  10:5   error  'foo' is not defined     no-undef
  15:10  error  Missing semicolon        semi

✖ 2 errors (1 fixable, 1 not fixable)
"""
        result = NodeOutputParser.parse_eslint(output)
        assert result.success is False
        assert result.error_count == 2
    
    def test_parse_eslint_with_warnings(self):
        """Test parsing ESLint output with warnings."""
        output = """
/home/user/project/src/utils.js
  5:1  warning  Unexpected console statement  no-console

✖ 0 errors, 1 warning
"""
        result = NodeOutputParser.parse_eslint(output)
        assert result.success is True  # Warnings don't fail
        assert result.warning_count == 1


class TestNpmAuditParser:
    """Tests for npm audit output parsing."""
    
    def test_parse_npm_audit_json_no_vulns(self):
        """Test parsing npm audit JSON with no vulnerabilities."""
        output = json.dumps({
            "metadata": {
                "vulnerabilities": {
                    "info": 0,
                    "low": 0,
                    "moderate": 0,
                    "high": 0,
                    "critical": 0,
                    "total": 0
                }
            },
            "advisories": {}
        })
        result = NodeOutputParser.parse_npm_audit(output, json_format=True)
        assert result.success is True
        assert result.error_count == 0
    
    def test_parse_npm_audit_json_with_vulns(self):
        """Test parsing npm audit JSON with vulnerabilities."""
        output = json.dumps({
            "metadata": {
                "vulnerabilities": {
                    "info": 0,
                    "low": 2,
                    "moderate": 3,
                    "high": 1,
                    "critical": 1,
                    "total": 7
                }
            },
            "advisories": {
                "1234": {
                    "severity": "critical",
                    "title": "Prototype Pollution",
                    "module_name": "lodash"
                },
                "5678": {
                    "severity": "high",
                    "title": "Regular Expression DoS",
                    "module_name": "minimatch"
                }
            }
        })
        result = NodeOutputParser.parse_npm_audit(output, json_format=True)
        assert result.success is False
        assert result.error_count == 2  # critical + high
        assert result.warning_count == 5  # moderate + low
    
    def test_parse_npm_audit_text_output(self):
        """Test parsing npm audit text output."""
        output = """
# npm audit report

lodash  <=4.17.20
Severity: high
Regular Expression Denial of Service

minimatch  <3.0.5
Severity: high
minimatch ReDoS vulnerability

2 high severity vulnerabilities

To address all issues, run:
  npm audit fix
"""
        result = NodeOutputParser.parse_npm_audit(output, json_format=False)
        assert result.success is False
        assert result.error_count >= 2  # At least 2 high severity
    
    def test_parse_npm_audit_no_issues(self):
        """Test parsing npm audit with no issues."""
        output = """
found 0 vulnerabilities
"""
        result = NodeOutputParser.parse_npm_audit(output, json_format=False)
        assert result.success is True


class TestTypeScriptErrorParser:
    """Tests for TypeScript error parsing."""
    
    def test_parse_typescript_no_errors(self):
        """Test parsing TypeScript output with no errors."""
        output = """
$ tsc --noEmit
Done in 2.34s.
"""
        result = NodeOutputParser.parse_typescript_errors(output)
        assert result.success is True
        assert result.error_count == 0
    
    def test_parse_typescript_errors(self):
        """Test parsing TypeScript output with errors."""
        output = """
src/index.ts(10,5): error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'.
src/utils.ts(20,15): error TS2322: Type 'number' is not assignable to type 'string'.
src/utils.ts(25,3): error TS7006: Parameter 'x' implicitly has an 'any' type.
"""
        result = NodeOutputParser.parse_typescript_errors(output)
        assert result.success is False
        assert result.error_count == 3
        assert len(result.details) == 3
        
        # Check first error detail
        first_error = result.details[0]
        assert first_error["file"] == "src/index.ts"
        assert first_error["line"] == 10
        assert first_error["column"] == 5
        assert first_error["code"] == "TS2345"
    
    def test_parse_typescript_with_context(self):
        """Test parsing TypeScript output with additional context."""
        output = """
src/components/Button.tsx(45,12): error TS2322: Type '{ onClick: () => void; }' is not assignable to type 'ButtonProps'.
  Property 'children' is missing in type '{ onClick: () => void; }' but required in type 'ButtonProps'.
"""
        result = NodeOutputParser.parse_typescript_errors(output)
        assert result.success is False
        assert result.error_count == 1


class TestNodeOutputParserAutoDetect:
    """Tests for auto-detection in NodeOutputParser."""
    
    def test_auto_detect_npm_test(self):
        """Test auto-detection of npm test command."""
        output = "Test Suites: 5 passed, 5 total"
        result = NodeOutputParser.parse_command_output("npm test", output)
        assert "passed" in result.summary or result.success is True
    
    def test_auto_detect_eslint(self):
        """Test auto-detection of eslint command."""
        output = "✖ 3 errors, 2 warnings"
        result = NodeOutputParser.parse_command_output("npx eslint .", output)
        assert result.error_count == 3
        assert result.warning_count == 2
    
    def test_auto_detect_tsc(self):
        """Test auto-detection of tsc command."""
        output = "src/index.ts(10,5): error TS2345: ..."
        result = NodeOutputParser.parse_command_output("npx tsc --noEmit", output)
        assert result.error_count >= 1
    
    def test_auto_detect_npm_audit(self):
        """Test auto-detection of npm audit command."""
        output = json.dumps({
            "metadata": {
                "vulnerabilities": {
                    "critical": 1,
                    "high": 0,
                    "moderate": 0,
                    "low": 0,
                    "total": 1
                }
            }
        })
        result = NodeOutputParser.parse_command_output("npm audit --json", output)
        assert result.error_count == 1
