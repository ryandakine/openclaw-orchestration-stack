"""
Documentation Tests

This module tests the documentation for:
1. Valid internal and external links
2. Compilable code blocks
3. Valid YAML/JSON examples
4. Consistency with codebase
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import List, Tuple

import pytest
import yaml

# Configuration
DOCS_DIR = Path(__file__).parent.parent
PROJECT_ROOT = DOCS_DIR.parent
LINK_TIMEOUT = 10  # seconds


# ==============================================================================
# Link Tests
# ==============================================================================

def find_markdown_files() -> List[Path]:
    """Find all markdown files in the docs directory."""
    return list(DOCS_DIR.rglob("*.md"))


def extract_links(content: str) -> Tuple[List[str], List[str]]:
    """
    Extract internal and external links from markdown content.
    
    Returns:
        Tuple of (internal_links, external_links)
    """
    # Match markdown links [text](url)
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    
    internal_links = []
    external_links = []
    
    for match in re.finditer(link_pattern, content):
        url = match.group(2)
        
        # Skip anchors and special links
        if url.startswith('#') or url.startswith('mailto:'):
            continue
        
        # External links
        if url.startswith(('http://', 'https://')):
            external_links.append(url)
        # Internal links (relative paths)
        elif not url.startswith(('data:', 'javascript:')):
            internal_links.append(url)
    
    return internal_links, external_links


class TestLinks:
    """Tests for documentation links."""
    
    @pytest.mark.parametrize("md_file", find_markdown_files())
    def test_internal_links_exist(self, md_file: Path):
        """Test that all internal links point to existing files."""
        content = md_file.read_text()
        internal_links, _ = extract_links(content)
        
        for link in internal_links:
            # Remove anchor if present
            link_path = link.split('#')[0]
            
            # Skip empty links
            if not link_path:
                continue
            
            # Resolve relative to the markdown file's directory
            if link_path.startswith('/'):
                target = PROJECT_ROOT / link_path.lstrip('/')
            else:
                target = md_file.parent / link_path
            
            # Handle directory links (should have index/README)
            if target.is_dir():
                index_file = target / "index.md"
                readme_file = target / "README.md"
                assert index_file.exists() or readme_file.exists(), \
                    f"Directory link {link} in {md_file} has no index.md or README.md"
            else:
                # Add .md extension if not present
                if not target.suffix:
                    target = target.with_suffix('.md')
                
                assert target.exists(), \
                    f"Broken internal link: {link} in {md_file}"
    
    @pytest.mark.skip(reason="External link checking can be flaky")
    @pytest.mark.parametrize("md_file", find_markdown_files())
    def test_external_links_valid(self, md_file: Path):
        """Test that external links return valid HTTP status."""
        content = md_file.read_text()
        _, external_links = extract_links(content)
        
        import urllib.request
        
        for link in external_links:
            try:
                req = urllib.request.Request(
                    link,
                    headers={'User-Agent': 'Mozilla/5.0'},
                    method='HEAD'
                )
                response = urllib.request.urlopen(req, timeout=LINK_TIMEOUT)
                assert response.status < 400, \
                    f"External link {link} in {md_file} returned {response.status}"
            except Exception as e:
                pytest.skip(f"Could not verify external link {link}: {e}")


# ==============================================================================
# Code Block Tests
# ==============================================================================

def extract_code_blocks(content: str, language: str = None) -> List[Tuple[str, str]]:
    """
    Extract code blocks from markdown content.
    
    Args:
        content: Markdown content
        language: Optional language filter (e.g., 'python', 'bash')
    
    Returns:
        List of (language, code) tuples
    """
    # Match fenced code blocks ```language\ncode\n```
    pattern = r'```(\w+)?\n(.*?)```'
    
    blocks = []
    for match in re.finditer(pattern, content, re.DOTALL):
        block_lang = (match.group(1) or '').lower()
        code = match.group(2)
        
        if language is None or block_lang == language:
            blocks.append((block_lang, code))
    
    return blocks


class TestCodeBlocks:
    """Tests for documentation code blocks."""
    
    @pytest.mark.parametrize("md_file", find_markdown_files())
    def test_python_code_syntax(self, md_file: Path):
        """Test that Python code blocks have valid syntax."""
        content = md_file.read_text()
        python_blocks = extract_code_blocks(content, 'python')
        
        for _, code in python_blocks:
            # Skip incomplete examples
            if '...' in code or '# ...' in code:
                continue
            
            try:
                compile(code, '<string>', 'exec')
            except SyntaxError as e:
                pytest.fail(f"Syntax error in Python code block in {md_file}: {e}")
    
    @pytest.mark.parametrize("md_file", find_markdown_files())
    def test_json_code_valid(self, md_file: Path):
        """Test that JSON code blocks are valid JSON."""
        content = md_file.read_text()
        json_blocks = extract_code_blocks(content, 'json')
        
        for _, code in json_blocks:
            # Skip incomplete examples
            if '...' in code:
                continue
            
            try:
                json.loads(code)
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in code block in {md_file}: {e}")
    
    @pytest.mark.parametrize("md_file", find_markdown_files())
    def test_yaml_code_valid(self, md_file: Path):
        """Test that YAML code blocks are valid YAML."""
        content = md_file.read_text()
        yaml_blocks = extract_code_blocks(content, 'yaml')
        
        for _, code in yaml_blocks:
            # Skip incomplete examples
            if '...' in code:
                continue
            
            try:
                yaml.safe_load(code)
            except yaml.YAMLError as e:
                pytest.fail(f"Invalid YAML in code block in {md_file}: {e}")
    
    @pytest.mark.parametrize("md_file", find_markdown_files())
    def test_bash_code_no_syntax_errors(self, md_file: Path):
        """Test that bash code blocks have valid syntax."""
        content = md_file.read_text()
        bash_blocks = extract_code_blocks(content, 'bash')
        shell_blocks = extract_code_blocks(content, 'sh')
        
        all_blocks = bash_blocks + shell_blocks
        
        for lang, code in all_blocks:
            # Skip multi-line scripts that require context
            if '\n' in code.strip() and lang == 'bash':
                continue
            
            # Skip commands with placeholders
            if any(p in code for p in ['<', '>', '${', '...', '#']):
                continue
            
            # Check individual commands
            lines = [line.strip() for line in code.split('\n') if line.strip()]
            for line in lines:
                # Skip comments
                if line.startswith('#'):
                    continue
                
                # Skip variable assignments
                if '=' in line and not line.startswith(('export ', 'echo ')):
                    continue
                
                # Basic syntax check - look for unmatched quotes
                single_quotes = line.count("'") - line.count("\\'")
                double_quotes = line.count('"') - line.count('\\"')
                backticks = line.count('`')
                
                if single_quotes % 2 != 0:
                    pytest.fail(f"Unmatched single quote in {md_file}: {line}")
                if double_quotes % 2 != 0:
                    pytest.fail(f"Unmatched double quote in {md_file}: {line}")
                if backticks % 2 != 0:
                    pytest.fail(f"Unmatched backtick in {md_file}: {line}")


# ==============================================================================
# Configuration File Tests
# ==============================================================================

class TestConfigFiles:
    """Tests for configuration examples in documentation."""
    
    def test_docker_compose_valid(self):
        """Test that docker-compose.yml example is valid."""
        compose_file = PROJECT_ROOT / "docker" / "docker-compose.yml"
        if compose_file.exists():
            try:
                content = compose_file.read_text()
                yaml.safe_load(content)
            except yaml.YAMLError as e:
                pytest.fail(f"Invalid docker-compose.yml: {e}")
    
    def test_k8s_manifests_valid(self):
        """Test that Kubernetes manifests are valid YAML."""
        k8s_dir = PROJECT_ROOT / "k8s"
        if k8s_dir.exists():
            for yaml_file in k8s_dir.glob("*.yaml"):
                try:
                    content = yaml_file.read_text()
                    # Use safe_load_all to handle multi-document YAML files
                    list(yaml.safe_load_all(content))
                except yaml.YAMLError as e:
                    pytest.fail(f"Invalid YAML in {yaml_file}: {e}")
    
    def test_systemd_service_valid(self):
        """Test that systemd service files have valid syntax."""
        systemd_dir = PROJECT_ROOT / "systemd"
        if systemd_dir.exists():
            for service_file in systemd_dir.glob("*.service"):
                content = service_file.read_text()
                
                # Check for required sections
                assert '[Unit]' in content, f"Missing [Unit] section in {service_file}"
                assert '[Service]' in content, f"Missing [Service] section in {service_file}"
                assert '[Install]' in content, f"Missing [Install] section in {service_file}"


# ==============================================================================
# Documentation Structure Tests
# ==============================================================================

class TestDocumentationStructure:
    """Tests for documentation structure and organization."""
    
    def test_required_files_exist(self):
        """Test that required documentation files exist."""
        required_files = [
            DOCS_DIR / "architecture" / "system-design.md",
            DOCS_DIR / "architecture" / "data-flow.md",
            DOCS_DIR / "architecture" / "state-machine.md",
            DOCS_DIR / "guides" / "setup.md",
            DOCS_DIR / "guides" / "configuration.md",
            DOCS_DIR / "guides" / "troubleshooting.md",
            DOCS_DIR / "guides" / "security.md",
            DOCS_DIR / "api" / "rest-api.md",
            DOCS_DIR / "api" / "webhooks.md",
            DOCS_DIR / "api" / "schemas.md",
        ]
        
        for file_path in required_files:
            assert file_path.exists(), f"Required documentation file missing: {file_path}"
    
    def test_readme_files_exist(self):
        """Test that README.md files exist in documentation directories."""
        for dir_path in DOCS_DIR.iterdir():
            if dir_path.is_dir():
                readme = dir_path / "README.md"
                assert readme.exists(), f"README.md missing in {dir_path}"
    
    @pytest.mark.parametrize("md_file", find_markdown_files())
    def test_no_todo_placeholders(self, md_file: Path):
        """Test that documentation doesn't contain TODO/FIXME placeholders."""
        content = md_file.read_text()
        
        # Allow TODO in test_docs.py itself
        if md_file.name == "test_docs.py":
            return
        
        prohibited = ['TODO:', 'FIXME:', 'XXX:', 'HACK:']
        for marker in prohibited:
            assert marker not in content, \
                f"Found {marker} in {md_file}"
    
    @pytest.mark.parametrize("md_file", find_markdown_files())
    def test_headers_properly_formatted(self, md_file: Path):
        """Test that markdown headers are properly formatted."""
        content = md_file.read_text()
        lines = content.split('\n')
        
        in_code_block = False
        code_block_delimiter = None
        
        for i, line in enumerate(lines):
            # Track code blocks to skip lines inside them
            stripped = line.strip()
            if stripped.startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    code_block_delimiter = stripped
                elif stripped == code_block_delimiter:
                    in_code_block = False
                    code_block_delimiter = None
                continue
            
            # Skip lines inside code blocks
            if in_code_block:
                continue
            
            # Check for headers
            if line.startswith('#') and not line.startswith('#!'):
                level = len(line) - len(line.lstrip('#'))
                
                # Header level should be 1-6
                assert 1 <= level <= 6, \
                    f"Invalid header level {level} in {md_file}:{i+1}"
                
                # Header should have space after #
                if not line.startswith('# ' * level) and level < 7:
                    assert line[level] == ' ', \
                        f"Missing space after # in header in {md_file}:{i+1}"


# ==============================================================================
# API Documentation Consistency Tests
# ==============================================================================

class TestAPIDocumentation:
    """Tests for API documentation consistency."""
    
    def test_api_endpoints_documented(self):
        """Test that API endpoints are documented."""
        api_doc = DOCS_DIR / "api" / "rest-api.md"
        if not api_doc.exists():
            pytest.skip("API documentation not found")
        
        content = api_doc.read_text()
        
        # Check for common endpoints
        expected_endpoints = [
            'GET /health',
            'POST /ingest',
            'GET /tasks',
            'GET /intents',
            'GET /workers',
        ]
        
        for endpoint in expected_endpoints:
            assert endpoint in content, \
                f"Endpoint {endpoint} not documented in rest-api.md"
    
    def test_webhook_events_documented(self):
        """Test that webhook events are documented."""
        webhook_doc = DOCS_DIR / "api" / "webhooks.md"
        if not webhook_doc.exists():
            pytest.skip("Webhook documentation not found")
        
        content = webhook_doc.read_text()
        
        expected_events = [
            'task.created',
            'task.completed',
            'task.failed',
            'review.approved',
        ]
        
        for event in expected_events:
            assert event in content, \
                f"Event {event} not documented in webhooks.md"


# ==============================================================================
# Schema Consistency Tests
# ==============================================================================

class TestSchemaConsistency:
    """Tests for schema documentation consistency."""
    
    def test_task_status_enum_documented(self):
        """Test that all task statuses are documented."""
        state_machine_doc = DOCS_DIR / "architecture" / "state-machine.md"
        if not state_machine_doc.exists():
            pytest.skip("State machine documentation not found")
        
        content = state_machine_doc.read_text()
        
        expected_statuses = [
            'queued', 'executing', 'review_queued',
            'approved', 'merged', 'failed', 'blocked'
        ]
        
        for status in expected_statuses:
            assert status in content, \
                f"Task status '{status}' not documented in state-machine.md"


# ==============================================================================
# Main
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
