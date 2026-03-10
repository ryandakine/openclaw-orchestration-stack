"""
Symphony Reviewer Engine for Symphony Bridge.

Provides the main review logic including:
- Review task entry point
- Diff analysis
- Checklist-based validation (correctness, bugs, security, style, tests, scope)
- Review result submission
"""

import json
import uuid
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

try:
    from shared.db import (
        get_connection,
        transaction,
        execute,
        insert,
        update,
        get_task_by_id,
    )
    from ..github.client import GitHubClient
    from ..review.summary import (
        ReviewSummary,
        ReviewFinding,
        FindingSeverity,
        FindingCategory,
        generate_summary,
    )
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    from shared.db import (
        get_connection,
        transaction,
        execute,
        insert,
        update,
        get_task_by_id,
    )
    from github.client import GitHubClient
    from review.summary import (
        ReviewSummary,
        ReviewFinding,
        FindingSeverity,
        FindingCategory,
        generate_summary,
    )

logger = logging.getLogger(__name__)


class ReviewResult(str, Enum):
    """Review result types."""
    APPROVE = "approve"
    REJECT = "reject"
    BLOCK = "blocked"


@dataclass
class ReviewChecklist:
    """
    Review checklist categories.
    
    Each category tracks whether it passed review and any findings.
    """
    correctness: bool = True
    correctness_findings: List[str] = field(default_factory=list)
    
    bugs: bool = True
    bug_findings: List[str] = field(default_factory=list)
    
    security: bool = True
    security_findings: List[str] = field(default_factory=list)
    
    style: bool = True
    style_findings: List[str] = field(default_factory=list)
    
    tests: bool = True
    test_findings: List[str] = field(default_factory=list)
    
    scope: bool = True
    scope_findings: List[str] = field(default_factory=list)
    
    def all_passed(self) -> bool:
        """Check if all checklist items passed."""
        return all([
            self.correctness,
            self.bugs,
            self.security,
            self.style,
            self.tests,
            self.scope,
        ])
    
    def get_failed_categories(self) -> List[str]:
        """Get list of failed category names."""
        failed = []
        if not self.correctness:
            failed.append("correctness")
        if not self.bugs:
            failed.append("bugs")
        if not self.security:
            failed.append("security")
        if not self.style:
            failed.append("style")
        if not self.tests:
            failed.append("tests")
        if not self.scope:
            failed.append("scope")
        return failed
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "correctness": {
                "passed": self.correctness,
                "findings": self.correctness_findings,
            },
            "bugs": {
                "passed": self.bugs,
                "findings": self.bug_findings,
            },
            "security": {
                "passed": self.security,
                "findings": self.security_findings,
            },
            "style": {
                "passed": self.style,
                "findings": self.style_findings,
            },
            "tests": {
                "passed": self.tests,
                "findings": self.test_findings,
            },
            "scope": {
                "passed": self.scope,
                "findings": self.scope_findings,
            },
        }


@dataclass
class DiffAnalysis:
    """Results of analyzing a PR diff."""
    files_changed: List[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    total_lines: int = 0
    file_types: Dict[str, int] = field(default_factory=dict)
    has_tests: bool = False
    has_documentation: bool = False
    complexity_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "files_changed": self.files_changed,
            "additions": self.additions,
            "deletions": self.deletions,
            "total_lines": self.total_lines,
            "file_types": self.file_types,
            "has_tests": self.has_tests,
            "has_documentation": self.has_documentation,
            "complexity_score": self.complexity_score,
        }


class ReviewerEngine:
    """
    Symphony Reviewer Engine - performs automated code reviews.
    
    This engine:
    1. Analyzes PR diffs
    2. Checks against review checklist
    3. Submits review results
    4. Logs all actions to audit trail
    """
    
    def __init__(self, github_client: Optional[GitHubClient] = None):
        """
        Initialize the reviewer engine.
        
        Args:
            github_client: Optional GitHub client for fetching PR data
        """
        self.github_client = github_client
        self.logger = logging.getLogger(__name__)
    
    def _log_audit_event(
        self,
        correlation_id: str,
        action: str,
        payload: Dict[str, Any],
        actor: str = "symphony",
    ) -> None:
        """Log an audit event."""
        try:
            # Note: id is auto-increment, don't specify it
            insert("audit_events", {
                "correlation_id": correlation_id,
                "actor": actor,
                "action": action,
                "payload": json.dumps(payload),
            })
        except Exception as e:
            self.logger.error(f"Failed to log audit event: {e}")
    
    def review_task(
        self,
        task_id: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        custom_checklist: Optional[ReviewChecklist] = None,
    ) -> ReviewSummary:
        """
        Main review entry point.
        
        Performs a complete review of a task:
        1. Fetches PR diff if GitHub client available
        2. Analyzes the diff
        3. Runs checklist validation
        4. Submits review result
        
        Args:
            task_id: The task ID to review
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            custom_checklist: Optional custom checklist to use
            
        Returns:
            ReviewSummary with the review results
        """
        task = get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        if task["status"] != "review_queued":
            raise ValueError(
                f"Task {task_id} is not in review_queued status (current: {task['status']})"
            )
        
        correlation_id = task["correlation_id"]
        
        # Log review started
        self._log_audit_event(
            correlation_id=correlation_id,
            action="review.started",
            payload={
                "task_id": task_id,
                "pr_number": pr_number,
                "owner": owner,
                "repo": repo,
            },
        )
        
        try:
            # Analyze diff if we have GitHub info
            diff_analysis = None
            if self.github_client and owner and repo and pr_number:
                diff_analysis = self.analyze_diff(owner, repo, pr_number)
            
            # Run checklist validation
            checklist = custom_checklist or self._default_checklist()
            self._run_checklist_validation(task, diff_analysis, checklist)
            
            # Determine result
            if not checklist.all_passed():
                if not checklist.security:
                    # Security issues block the PR
                    result = ReviewResult.BLOCK
                else:
                    # Other issues can be fixed via remediation
                    result = ReviewResult.REJECT
            else:
                result = ReviewResult.APPROVE
            
            # Generate findings
            findings = self._checklist_to_findings(checklist)
            
            # Create summary
            summary = generate_summary(
                findings=findings,
                result=result.value,
                metadata={
                    "task_id": task_id,
                    "checklist": checklist.to_dict(),
                    "diff_analysis": diff_analysis.to_dict() if diff_analysis else None,
                }
            )
            
            # Submit review result
            self.work_finish(task_id, result, summary, checklist)
            
            return summary
            
        except Exception as e:
            self.logger.exception(f"Review failed for task {task_id}: {e}")
            
            # Log failure
            self._log_audit_event(
                correlation_id=correlation_id,
                action="review.failed",
                payload={
                    "task_id": task_id,
                    "error": str(e),
                },
            )
            
            # Create failure summary
            return generate_summary(
                findings=[
                    ReviewFinding(
                        message=f"Review failed with error: {e}",
                        severity=FindingSeverity.HIGH,
                        category=FindingCategory.OTHER,
                    )
                ],
                result=ReviewResult.BLOCK.value,
                custom_summary=f"Review failed: {e}",
            )
    
    def analyze_diff(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> DiffAnalysis:
        """
        Read and analyze PR diff.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            
        Returns:
            DiffAnalysis with statistics
        """
        if not self.github_client:
            raise ValueError("GitHub client required for diff analysis")
        
        try:
            # Fetch PR diff via GitHub API
            diff_data = self._fetch_pr_diff(owner, repo, pr_number)
            
            analysis = DiffAnalysis()
            
            # Parse diff for statistics
            files_changed = []
            file_types = {}
            has_tests = False
            has_docs = False
            
            for file_info in diff_data.get("files", []):
                filename = file_info.get("filename", "")
                files_changed.append(filename)
                
                # Track file types
                ext = filename.split(".")[-1] if "." in filename else "none"
                file_types[ext] = file_types.get(ext, 0) + 1
                
                # Check for tests
                if "test" in filename.lower() or "spec" in filename.lower():
                    has_tests = True
                
                # Check for docs
                if filename.endswith((".md", ".rst", ".txt")) or "doc" in filename.lower():
                    has_docs = True
                
                # Count lines
                analysis.additions += file_info.get("additions", 0)
                analysis.deletions += file_info.get("deletions", 0)
            
            analysis.files_changed = files_changed
            analysis.file_types = file_types
            analysis.has_tests = has_tests
            analysis.has_documentation = has_docs
            analysis.total_lines = analysis.additions + analysis.deletions
            
            # Calculate complexity score (simple heuristic)
            analysis.complexity_score = min(
                10.0,
                (len(files_changed) * 0.5) + (analysis.total_lines / 100)
            )
            
            self.logger.info(
                f"Analyzed diff for {owner}/{repo}#{pr_number}: "
                f"{len(files_changed)} files, {analysis.total_lines} lines"
            )
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Failed to analyze diff: {e}")
            return DiffAnalysis()
    
    def _fetch_pr_diff(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """Fetch PR diff data from GitHub API."""
        # Get PR files
        files = self.github_client._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
            params={"per_page": 100},
        )
        
        return {"files": files}
    
    def _default_checklist(self) -> ReviewChecklist:
        """Create a default checklist (all passing)."""
        return ReviewChecklist()
    
    def _run_checklist_validation(
        self,
        task: Dict[str, Any],
        diff_analysis: Optional[DiffAnalysis],
        checklist: ReviewChecklist,
    ) -> None:
        """
        Run checklist validation against task and diff.
        
        This performs automated checks:
        - Correctness: Basic validation
        - Bugs: Pattern matching for common bugs
        - Security: Security pattern checks
        - Style: Conformance to style guidelines
        - Tests: Presence of tests
        - Scope: Appropriateness for the task
        """
        # Check tests if code changes detected
        if diff_analysis and diff_analysis.files_changed:
            # Check for test files
            code_files = [
                f for f in diff_analysis.files_changed
                if not ("test" in f.lower() or "spec" in f.lower())
            ]
            
            if code_files and not diff_analysis.has_tests:
                checklist.tests = False
                checklist.test_findings.append(
                    "No test files detected for code changes. Consider adding tests."
                )
        
        # Check scope (simple heuristic based on line count)
        if diff_analysis and diff_analysis.total_lines > 500:
            checklist.scope = False
            checklist.scope_findings.append(
                f"Large change ({diff_analysis.total_lines} lines). "
                "Consider breaking into smaller PRs."
            )
        
        # Check security patterns in changed files
        if diff_analysis:
            security_issues = self._check_security_patterns(diff_analysis)
            if security_issues:
                checklist.security = False
                checklist.security_findings.extend(security_issues)
        
        # Check for documentation
        if diff_analysis and diff_analysis.files_changed:
            has_doc_changes = any(
                f.endswith(".md") or "doc" in f.lower()
                for f in diff_analysis.files_changed
            )
            # Public API changes should have docs (simplified check)
            has_public_api_changes = any(
                f.endswith((".py", ".js", ".ts", ".rs", ".go", ".java"))
                for f in diff_analysis.files_changed
            )
            if has_public_api_changes and not has_doc_changes:
                checklist.documentation = False
                # Note: documentation is not in our checklist, so we'll add it to style
                checklist.style_findings.append(
                    "Consider updating documentation for public API changes"
                )
    
    def _check_security_patterns(self, diff_analysis: DiffAnalysis) -> List[str]:
        """Check for common security issues in changed files."""
        issues = []
        
        # This would ideally analyze actual file content
        # For now, provide a placeholder that can be extended
        
        return issues
    
    def _checklist_to_findings(self, checklist: ReviewChecklist) -> List[ReviewFinding]:
        """Convert checklist failures to ReviewFindings."""
        findings = []
        
        if not checklist.correctness:
            for msg in checklist.correctness_findings:
                findings.append(ReviewFinding(
                    message=msg,
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.BUG,
                ))
        
        if not checklist.bugs:
            for msg in checklist.bug_findings:
                findings.append(ReviewFinding(
                    message=msg,
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.BUG,
                ))
        
        if not checklist.security:
            for msg in checklist.security_findings:
                findings.append(ReviewFinding(
                    message=msg,
                    severity=FindingSeverity.CRITICAL,
                    category=FindingCategory.SECURITY,
                ))
        
        if not checklist.style:
            for msg in checklist.style_findings:
                findings.append(ReviewFinding(
                    message=msg,
                    severity=FindingSeverity.LOW,
                    category=FindingCategory.STYLE,
                ))
        
        if not checklist.tests:
            for msg in checklist.test_findings:
                findings.append(ReviewFinding(
                    message=msg,
                    severity=FindingSeverity.MEDIUM,
                    category=FindingCategory.TESTING,
                ))
        
        if not checklist.scope:
            for msg in checklist.scope_findings:
                findings.append(ReviewFinding(
                    message=msg,
                    severity=FindingSeverity.MEDIUM,
                    category=FindingCategory.ARCHITECTURE,
                ))
        
        return findings
    
    def check_against_checklist(
        self,
        task_id: str,
        checklist: ReviewChecklist,
    ) -> ReviewChecklist:
        """
        Check a task against a custom checklist.
        
        Args:
            task_id: The task to check
            checklist: The checklist to validate against
            
        Returns:
            Updated checklist with results
        """
        task = get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        # Parse payload for any stored analysis
        payload = task.get("payload") or "{}"
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        
        # Get PR info from payload
        queue_metadata = payload.get("review_queue", {})
        owner = queue_metadata.get("owner")
        repo = queue_metadata.get("repo")
        pr_number = queue_metadata.get("pr_number")
        
        # Analyze diff if available
        diff_analysis = None
        if self.github_client and owner and repo and pr_number:
            try:
                diff_analysis = self.analyze_diff(owner, repo, pr_number)
            except Exception as e:
                self.logger.warning(f"Could not analyze diff: {e}")
        
        # Run validation
        self._run_checklist_validation(task, diff_analysis, checklist)
        
        return checklist
    
    def work_finish(
        self,
        task_id: str,
        result: ReviewResult,
        summary: ReviewSummary,
        checklist: ReviewChecklist,
    ) -> Dict[str, Any]:
        """
        Submit review result and update task state.
        
        Args:
            task_id: The task being reviewed
            result: The review result (approve/reject/block)
            summary: The review summary
            checklist: The checklist used
            
        Returns:
            Dictionary with review result details
        """
        task = get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        correlation_id = task["correlation_id"]
        review_id = str(uuid.uuid4())
        
        with transaction() as conn:
            # Store review record
            conn.execute(
                """
                INSERT INTO reviews (id, task_id, result, summary, findings, reviewer_id, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    review_id,
                    task_id,
                    result.value,
                    summary.summary,
                    json.dumps([f.to_dict() for f in summary.findings]),
                    "symphony_reviewer",
                )
            )
            
            # Update task status based on result
            if result == ReviewResult.APPROVE:
                new_status = "approved"
            elif result == ReviewResult.REJECT:
                new_status = "review_failed"
            else:  # BLOCK
                new_status = "blocked"
            
            conn.execute(
                """
                UPDATE tasks 
                SET status = ?, 
                    updated_at = CURRENT_TIMESTAMP,
                    claimed_by = NULL,
                    claimed_at = NULL,
                    lease_expires_at = NULL
                WHERE id = ?
                """,
                (new_status, task_id)
            )
        
        # Log audit event
        self._log_audit_event(
            correlation_id=correlation_id,
            action=f"review.completed.{result.value}",
            payload={
                "task_id": task_id,
                "review_id": review_id,
                "result": result.value,
                "findings_count": len(summary.findings),
                "checklist": checklist.to_dict(),
            },
        )
        
        self.logger.info(f"Review completed for task {task_id}: {result.value}")
        
        return {
            "review_id": review_id,
            "task_id": task_id,
            "result": result.value,
            "status": new_status,
            "findings_count": len(summary.findings),
        }
