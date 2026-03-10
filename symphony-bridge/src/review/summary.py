"""
Review Summary Generation for Symphony PR Bridge.

Provides methods for generating and formatting review summaries
from analysis findings for posting to GitHub.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class FindingSeverity(str, Enum):
    """Severity levels for review findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingCategory(str, Enum):
    """Categories for review findings."""
    SECURITY = "security"
    PERFORMANCE = "performance"
    BUG = "bug"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    ARCHITECTURE = "architecture"
    OTHER = "other"


@dataclass
class ReviewFinding:
    """Represents a single finding from code review."""
    message: str
    severity: FindingSeverity
    category: FindingCategory
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    suggestion: Optional[str] = None
    rule_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "suggestion": self.suggestion,
            "rule_id": self.rule_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ReviewFinding":
        """Create from dictionary."""
        return cls(
            message=data["message"],
            severity=FindingSeverity(data.get("severity", "info")),
            category=FindingCategory(data.get("category", "other")),
            file_path=data.get("file_path"),
            line_number=data.get("line_number"),
            suggestion=data.get("suggestion"),
            rule_id=data.get("rule_id"),
        )


@dataclass
class ReviewSummary:
    """Complete review summary with findings and metadata."""
    result: str  # "approve", "reject", "blocked"
    summary: str
    findings: List[ReviewFinding] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "result": self.result,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ReviewSummary":
        """Create from dictionary."""
        return cls(
            result=data["result"],
            summary=data["summary"],
            findings=[ReviewFinding.from_dict(f) for f in data.get("findings", [])],
            metadata=data.get("metadata", {}),
        )


def generate_summary(
    findings: List[ReviewFinding],
    result: str,
    custom_summary: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ReviewSummary:
    """
    Generate a review summary from findings.
    
    Args:
        findings: List of review findings
        result: Review result ("approve", "reject", "blocked")
        custom_summary: Optional custom summary text
        metadata: Additional metadata about the review
        
    Returns:
        ReviewSummary object
    """
    if custom_summary:
        summary = custom_summary
    else:
        summary = _generate_auto_summary(findings, result)
    
    return ReviewSummary(
        result=result,
        summary=summary,
        findings=findings,
        metadata=metadata or {},
    )


def _generate_auto_summary(findings: List[ReviewFinding], result: str) -> str:
    """Generate an automatic summary based on findings."""
    if not findings:
        if result == "approve":
            return "✅ **Approved** - No issues found in this PR."
        return "ℹ️ No findings to report."
    
    # Count by severity
    severity_counts: Dict[FindingSeverity, int] = {
        FindingSeverity.CRITICAL: 0,
        FindingSeverity.HIGH: 0,
        FindingSeverity.MEDIUM: 0,
        FindingSeverity.LOW: 0,
        FindingSeverity.INFO: 0,
    }
    
    for finding in findings:
        severity_counts[finding.severity] += 1
    
    # Build summary
    lines = []
    
    if result == "approve":
        lines.append("✅ **Approved** with minor suggestions.")
    elif result == "reject":
        lines.append("❌ **Changes Requested** - Please address the following issues.")
    elif result == "blocked":
        lines.append("🚫 **Blocked** - Critical issues must be resolved.")
    
    lines.append("")
    lines.append("### Summary")
    lines.append("")
    
    total = len(findings)
    lines.append(f"- **Total findings**: {total}")
    
    for severity in [FindingSeverity.CRITICAL, FindingSeverity.HIGH, 
                     FindingSeverity.MEDIUM, FindingSeverity.LOW, FindingSeverity.INFO]:
        count = severity_counts[severity]
        if count > 0:
            emoji = {
                FindingSeverity.CRITICAL: "🔴",
                FindingSeverity.HIGH: "🟠",
                FindingSeverity.MEDIUM: "🟡",
                FindingSeverity.LOW: "🔵",
                FindingSeverity.INFO: "⚪",
            }[severity]
            lines.append(f"- {emoji} **{severity.value.capitalize()}**: {count}")
    
    return "\n".join(lines)


def format_comment(
    summary: ReviewSummary,
    include_metadata: bool = True,
    include_findings_details: bool = True,
    max_findings: Optional[int] = None,
) -> str:
    """
    Format a review summary as a GitHub comment.
    
    Args:
        summary: ReviewSummary to format
        include_metadata: Whether to include metadata section
        include_findings_details: Whether to include detailed findings
        max_findings: Maximum number of findings to include (None for all)
        
    Returns:
        Formatted markdown string
    """
    lines = []
    
    # Header
    lines.append("## 🔍 Symphony Automated Review")
    lines.append("")
    
    # Summary
    lines.append(summary.summary)
    lines.append("")
    
    # Findings details
    if include_findings_details and summary.findings:
        lines.append("### Detailed Findings")
        lines.append("")
        
        findings_to_show = summary.findings
        if max_findings and len(findings_to_show) > max_findings:
            findings_to_show = findings_to_show[:max_findings]
        
        # Group by severity
        severity_order = [
            FindingSeverity.CRITICAL,
            FindingSeverity.HIGH,
            FindingSeverity.MEDIUM,
            FindingSeverity.LOW,
            FindingSeverity.INFO,
        ]
        
        for severity in severity_order:
            severity_findings = [f for f in findings_to_show if f.severity == severity]
            if severity_findings:
                emoji = {
                    FindingSeverity.CRITICAL: "🔴",
                    FindingSeverity.HIGH: "🟠",
                    FindingSeverity.MEDIUM: "🟡",
                    FindingSeverity.LOW: "🔵",
                    FindingSeverity.INFO: "⚪",
                }[severity]
                
                lines.append(f"#### {emoji} {severity.value.capitalize()}")
                lines.append("")
                
                for i, finding in enumerate(severity_findings, 1):
                    lines.append(_format_finding(finding, i))
                    lines.append("")
        
        # Show truncation notice
        if max_findings and len(summary.findings) > max_findings:
            remaining = len(summary.findings) - max_findings
            lines.append(f"*... and {remaining} more findings*")
            lines.append("")
    
    # Metadata
    if include_metadata and summary.metadata:
        lines.append("### Review Metadata")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>Click to expand</summary>")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(summary.metadata, indent=2))
        lines.append("```")
        lines.append("</details>")
        lines.append("")
    
    # Footer
    lines.append("---")
    lines.append("*This review was automatically generated by [Symphony](https://github.com/openclaw-orchestration-stack) 🎼*")
    
    return "\n".join(lines)


def _format_finding(finding: ReviewFinding, index: int) -> str:
    """Format a single finding for display."""
    lines = []
    
    # Header with file info
    if finding.file_path:
        location = f"`{finding.file_path}`"
        if finding.line_number:
            location += f":{finding.line_number}"
        lines.append(f"**{index}.** {location}")
    else:
        lines.append(f"**{index}.** General")
    
    # Category badge
    lines.append(f"*{finding.category.value.capitalize()}*")
    lines.append("")
    
    # Message
    lines.append(finding.message)
    
    # Suggestion
    if finding.suggestion:
        lines.append("")
        lines.append(f"**Suggestion:** {finding.suggestion}")
    
    # Rule ID
    if finding.rule_id:
        lines.append("")
        lines.append(f"<sub>Rule: `{finding.rule_id}`</sub>")
    
    return "\n".join(lines)


def format_review_body(
    summary: ReviewSummary,
    concise: bool = False,
) -> str:
    """
    Format review body for GitHub PR review API.
    
    Args:
        summary: ReviewSummary to format
        concise: If True, only include summary without detailed findings
        
    Returns:
        Formatted markdown string
    """
    if concise:
        return summary.summary
    
    return format_comment(
        summary,
        include_metadata=False,
        include_findings_details=True,
        max_findings=10,  # Limit findings in review body
    )


def create_review_comments_from_findings(
    findings: List[ReviewFinding],
    max_comments: int = 50,
) -> List[Dict[str, Any]]:
    """
    Convert findings to GitHub review comment format.
    
    Args:
        findings: List of review findings
        max_comments: Maximum number of comments to create
        
    Returns:
        List of comment dictionaries for API
    """
    comments = []
    
    for finding in findings:
        if not finding.file_path:
            continue
        
        if finding.line_number is None:
            continue
        
        body = finding.message
        if finding.suggestion:
            body += f"\n\n**Suggestion:** {finding.suggestion}"
        
        comment = {
            "path": finding.file_path,
            "line": finding.line_number,
            "body": body,
            "side": "RIGHT",
        }
        
        comments.append(comment)
        
        if len(comments) >= max_comments:
            break
    
    return comments


def parse_findings_from_json(json_data: str) -> List[ReviewFinding]:
    """
    Parse findings from JSON string.
    
    Args:
        json_data: JSON string containing findings
        
    Returns:
        List of ReviewFinding objects
    """
    try:
        data = json.loads(json_data)
        if isinstance(data, list):
            return [ReviewFinding.from_dict(f) for f in data]
        elif isinstance(data, dict) and "findings" in data:
            return [ReviewFinding.from_dict(f) for f in data["findings"]]
        else:
            return [ReviewFinding.from_dict(data)]
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Failed to parse findings from JSON: {e}")
        return []


def categorize_findings(findings: List[ReviewFinding]) -> Dict[FindingCategory, List[ReviewFinding]]:
    """
    Group findings by category.
    
    Args:
        findings: List of review findings
        
    Returns:
        Dictionary mapping categories to findings
    """
    categories: Dict[FindingCategory, List[ReviewFinding]] = {
        cat: [] for cat in FindingCategory
    }
    
    for finding in findings:
        categories[finding.category].append(finding)
    
    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def get_severity_emoji(severity: FindingSeverity) -> str:
    """Get emoji for severity level."""
    return {
        FindingSeverity.CRITICAL: "🔴",
        FindingSeverity.HIGH: "🟠",
        FindingSeverity.MEDIUM: "🟡",
        FindingSeverity.LOW: "🔵",
        FindingSeverity.INFO: "⚪",
    }.get(severity, "⚪")


def format_inline_comment(
    finding: ReviewFinding,
    include_category: bool = True,
) -> str:
    """
    Format a finding as an inline code review comment.
    
    Args:
        finding: ReviewFinding to format
        include_category: Whether to include category in comment
        
    Returns:
        Formatted comment string
    """
    lines = []
    
    if include_category:
        lines.append(f"**[{finding.category.value.capitalize()}]** ")
    
    lines.append(get_severity_emoji(finding.severity))
    lines.append(f" {finding.message}")
    
    if finding.suggestion:
        lines.append(f"\n\n💡 {finding.suggestion}")
    
    return "".join(lines)
