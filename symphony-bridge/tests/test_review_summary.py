"""
Unit tests for review summary generation.
"""

import json
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from review.summary import (
    ReviewFinding,
    ReviewSummary,
    FindingSeverity,
    FindingCategory,
    generate_summary,
    format_comment,
    format_review_body,
    format_inline_comment,
    create_review_comments_from_findings,
    parse_findings_from_json,
    categorize_findings,
    get_severity_emoji,
)


class TestFindingSeverity:
    """Tests for FindingSeverity enum."""
    
    def test_severity_values(self):
        """Test severity values."""
        assert FindingSeverity.CRITICAL.value == "critical"
        assert FindingSeverity.HIGH.value == "high"
        assert FindingSeverity.MEDIUM.value == "medium"
        assert FindingSeverity.LOW.value == "low"
        assert FindingSeverity.INFO.value == "info"


class TestFindingCategory:
    """Tests for FindingCategory enum."""
    
    def test_category_values(self):
        """Test category values."""
        assert FindingCategory.SECURITY.value == "security"
        assert FindingCategory.PERFORMANCE.value == "performance"
        assert FindingCategory.BUG.value == "bug"
        assert FindingCategory.STYLE.value == "style"


class TestReviewFinding:
    """Tests for ReviewFinding dataclass."""
    
    def test_to_dict(self, sample_finding):
        """Test converting finding to dict."""
        data = sample_finding.to_dict()
        
        assert data["message"] == "Test finding message"
        assert data["severity"] == "medium"
        assert data["category"] == "bug"
        assert data["file_path"] == "src/test.py"
        assert data["line_number"] == 42
        assert data["suggestion"] == "Fix this issue"
        assert data["rule_id"] == "TEST-001"
    
    def test_from_dict(self):
        """Test creating finding from dict."""
        data = {
            "message": "Test message",
            "severity": "high",
            "category": "security",
            "file_path": "src/app.py",
            "line_number": 10,
        }
        
        finding = ReviewFinding.from_dict(data)
        
        assert finding.message == "Test message"
        assert finding.severity == FindingSeverity.HIGH
        assert finding.category == FindingCategory.SECURITY
    
    def test_from_dict_defaults(self):
        """Test creating finding from dict with defaults."""
        data = {"message": "Test"}
        
        finding = ReviewFinding.from_dict(data)
        
        assert finding.severity == FindingSeverity.INFO
        assert finding.category == FindingCategory.OTHER
        assert finding.file_path is None


class TestReviewSummary:
    """Tests for ReviewSummary dataclass."""
    
    def test_to_dict(self, sample_review_summary):
        """Test converting summary to dict."""
        data = sample_review_summary.to_dict()
        
        assert data["result"] == "reject"
        assert data["summary"] == "Test review summary"
        assert len(data["findings"]) == 1
        assert data["metadata"] == {"test": True}
    
    def test_from_dict(self):
        """Test creating summary from dict."""
        data = {
            "result": "approve",
            "summary": "Test summary",
            "findings": [
                {
                    "message": "Finding 1",
                    "severity": "low",
                    "category": "style",
                },
            ],
            "metadata": {"key": "value"},
        }
        
        summary = ReviewSummary.from_dict(data)
        
        assert summary.result == "approve"
        assert len(summary.findings) == 1
        assert summary.findings[0].message == "Finding 1"


class TestGenerateSummary:
    """Tests for generate_summary function."""
    
    def test_generate_approve_summary_no_findings(self):
        """Test generating approval summary with no findings."""
        summary = generate_summary(
            findings=[],
            result="approve",
        )
        
        assert summary.result == "approve"
        assert "Approved" in summary.summary
        assert len(summary.findings) == 0
    
    def test_generate_reject_summary_with_findings(self):
        """Test generating reject summary with findings."""
        findings = [
            ReviewFinding("Error 1", FindingSeverity.HIGH, FindingCategory.BUG),
            ReviewFinding("Error 2", FindingSeverity.MEDIUM, FindingCategory.BUG),
        ]
        
        summary = generate_summary(
            findings=findings,
            result="reject",
        )
        
        assert summary.result == "reject"
        assert "Changes Requested" in summary.summary
        assert len(summary.findings) == 2
        assert "2" in summary.summary  # Should mention count
    
    def test_generate_summary_with_custom_summary(self):
        """Test generating summary with custom text."""
        summary = generate_summary(
            findings=[],
            result="approve",
            custom_summary="Custom approval message",
        )
        
        assert summary.summary == "Custom approval message"
    
    def test_generate_summary_with_metadata(self):
        """Test generating summary with metadata."""
        metadata = {"reviewer": "symphony", "duration": 10.5}
        
        summary = generate_summary(
            findings=[],
            result="approve",
            metadata=metadata,
        )
        
        assert summary.metadata == metadata


class TestFormatComment:
    """Tests for format_comment function."""
    
    def test_format_basic_comment(self, sample_review_summary):
        """Test formatting a basic comment."""
        comment = format_comment(sample_review_summary)
        
        assert "Symphony Automated Review" in comment
        assert sample_review_summary.summary in comment
        assert "Detailed Findings" in comment
        assert sample_review_summary.findings[0].message in comment
    
    def test_format_without_findings_details(self, sample_review_summary):
        """Test formatting without findings details."""
        comment = format_comment(
            sample_review_summary,
            include_findings_details=False,
        )
        
        assert "Detailed Findings" not in comment
    
    def test_format_without_metadata(self, sample_review_summary):
        """Test formatting without metadata."""
        comment = format_comment(
            sample_review_summary,
            include_metadata=False,
        )
        
        assert "Review Metadata" not in comment
    
    def test_format_with_max_findings(self):
        """Test formatting with max findings limit."""
        findings = [
            ReviewFinding(f"Finding {i}", FindingSeverity.LOW, FindingCategory.STYLE)
            for i in range(10)
        ]
        
        summary = ReviewSummary("reject", "Test", findings)
        comment = format_comment(summary, max_findings=5)
        
        assert "and 5 more findings" in comment
    
    def test_format_groups_by_severity(self):
        """Test that findings are grouped by severity."""
        findings = [
            ReviewFinding("Critical", FindingSeverity.CRITICAL, FindingCategory.BUG),
            ReviewFinding("High", FindingSeverity.HIGH, FindingCategory.BUG),
            ReviewFinding("Medium", FindingSeverity.MEDIUM, FindingCategory.BUG),
        ]
        
        summary = ReviewSummary("reject", "Test", findings)
        comment = format_comment(summary)
        
        assert "Critical" in comment
        assert "High" in comment
        assert "Medium" in comment


class TestFormatReviewBody:
    """Tests for format_review_body function."""
    
    def test_format_concise(self, sample_review_summary):
        """Test concise format."""
        body = format_review_body(sample_review_summary, concise=True)
        
        assert body == sample_review_summary.summary
    
    def test_format_full(self, sample_review_summary):
        """Test full format."""
        body = format_review_body(sample_review_summary, concise=False)
        
        assert "Symphony Automated Review" in body
        assert sample_review_summary.summary in body


class TestFormatInlineComment:
    """Tests for format_inline_comment function."""
    
    def test_format_inline(self, sample_finding):
        """Test formatting inline comment."""
        comment = format_inline_comment(sample_finding)
        
        assert sample_finding.message in comment
        assert sample_finding.suggestion in comment
    
    def test_format_inline_without_category(self, sample_finding):
        """Test formatting without category."""
        comment = format_inline_comment(sample_finding, include_category=False)
        
        assert "[Bug]" not in comment
        assert sample_finding.message in comment


class TestCreateReviewComments:
    """Tests for create_review_comments_from_findings function."""
    
    def test_create_comments(self):
        """Test creating review comments from findings."""
        findings = [
            ReviewFinding(
                "Issue 1",
                FindingSeverity.HIGH,
                FindingCategory.BUG,
                file_path="src/file1.py",
                line_number=10,
                suggestion="Fix 1",
            ),
            ReviewFinding(
                "Issue 2",
                FindingSeverity.MEDIUM,
                FindingCategory.STYLE,
                file_path="src/file2.py",
                line_number=20,
            ),
            ReviewFinding(
                "No file path",
                FindingSeverity.LOW,
                FindingCategory.OTHER,
            ),
            ReviewFinding(
                "No line number",
                FindingSeverity.LOW,
                FindingCategory.OTHER,
                file_path="src/file3.py",
            ),
        ]
        
        comments = create_review_comments_from_findings(findings)
        
        # Only findings with both file_path and line_number become comments
        assert len(comments) == 2
        assert comments[0]["path"] == "src/file1.py"
        assert comments[0]["line"] == 10
        assert "Fix 1" in comments[0]["body"]
    
    def test_max_comments_limit(self):
        """Test max comments limit."""
        findings = [
            ReviewFinding(
                f"Issue {i}",
                FindingSeverity.LOW,
                FindingCategory.STYLE,
                file_path=f"src/file{i}.py",
                line_number=i,
            )
            for i in range(10)
        ]
        
        comments = create_review_comments_from_findings(findings, max_comments=5)
        
        assert len(comments) == 5


class TestParseFindingsFromJson:
    """Tests for parse_findings_from_json function."""
    
    def test_parse_list(self):
        """Test parsing list of findings."""
        data = [
            {"message": "Finding 1", "severity": "high", "category": "bug"},
            {"message": "Finding 2", "severity": "low", "category": "style"},
        ]
        
        findings = parse_findings_from_json(json.dumps(data))
        
        assert len(findings) == 2
        assert findings[0].message == "Finding 1"
    
    def test_parse_object_with_findings_key(self):
        """Test parsing object with findings key."""
        data = {
            "findings": [
                {"message": "Finding 1", "severity": "high", "category": "bug"},
            ],
            "other": "data",
        }
        
        findings = parse_findings_from_json(json.dumps(data))
        
        assert len(findings) == 1
    
    def test_parse_single_finding(self):
        """Test parsing single finding."""
        data = {"message": "Single finding", "severity": "medium", "category": "bug"}
        
        findings = parse_findings_from_json(json.dumps(data))
        
        assert len(findings) == 1
        assert findings[0].message == "Single finding"
    
    def test_parse_invalid_json(self):
        """Test parsing invalid JSON."""
        findings = parse_findings_from_json("invalid json")
        
        assert len(findings) == 0


class TestCategorizeFindings:
    """Tests for categorize_findings function."""
    
    def test_categorize(self):
        """Test categorizing findings."""
        findings = [
            ReviewFinding("Bug 1", FindingSeverity.HIGH, FindingCategory.BUG),
            ReviewFinding("Bug 2", FindingSeverity.MEDIUM, FindingCategory.BUG),
            ReviewFinding("Style 1", FindingSeverity.LOW, FindingCategory.STYLE),
            ReviewFinding("Security 1", FindingSeverity.CRITICAL, FindingCategory.SECURITY),
        ]
        
        categorized = categorize_findings(findings)
        
        assert len(categorized[FindingCategory.BUG]) == 2
        assert len(categorized[FindingCategory.STYLE]) == 1
        assert len(categorized[FindingCategory.SECURITY]) == 1
        assert FindingCategory.PERFORMANCE not in categorized  # Empty categories removed


class TestGetSeverityEmoji:
    """Tests for get_severity_emoji function."""
    
    def test_emojis(self):
        """Test emoji for each severity."""
        assert get_severity_emoji(FindingSeverity.CRITICAL) == "🔴"
        assert get_severity_emoji(FindingSeverity.HIGH) == "🟠"
        assert get_severity_emoji(FindingSeverity.MEDIUM) == "🟡"
        assert get_severity_emoji(FindingSeverity.LOW) == "🔵"
        assert get_severity_emoji(FindingSeverity.INFO) == "⚪"
    
    def test_invalid_severity(self):
        """Test emoji for invalid severity."""
        assert get_severity_emoji("invalid") == "⚪"
