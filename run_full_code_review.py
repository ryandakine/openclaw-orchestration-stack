#!/usr/bin/env python3
"""
Symphony Full Code Review - Reviews all OpenClaw components
"""
import sys
import ast
import json
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

@dataclass
class ReviewFinding:
    file: str
    line: int
    severity: str  # critical, high, medium, low
    category: str  # security, bug, style, performance, correctness
    message: str
    suggestion: str

@dataclass
class FileReview:
    file: str
    lines: int
    findings: List[ReviewFinding]
    score: int  # 0-100

class SymphonyReviewer:
    """Static analysis reviewer for Python code."""
    
    CRITICAL_PATTERNS = [
        (r'eval\s*\(', 'eval() usage - dangerous code execution'),
        (r'exec\s*\(', 'exec() usage - dangerous code execution'),
        (r'subprocess\.call.*shell\s*=\s*True', 'subprocess with shell=True - injection risk'),
        (r'os\.system\s*\(', 'os.system() - command injection risk'),
        (r'input\s*\(', 'input() in Python 2 - security risk'),
        (r'__import__\s*\(', 'Dynamic __import__() - code injection risk'),
        (r'pickle\.loads?', 'pickle usage - arbitrary code execution'),
        (r'yaml\.load\s*\([^)]*\)', 'yaml.load() without Loader - code execution'),
    ]
    
    BUG_PATTERNS = [
        (r'except\s*:', 'Bare except clause - catches SystemExit'),
        (r'==\s*(True|False|None)', 'Comparison with singleton using == (use is)'),
        (r'\.has_key\s*\(', 'Python 2 has_key() - deprecated'),
        (r'print\s+[^(]', 'Python 2 print statement'),
        (r'\blist\s*\[\s*\]\s*\*\s*\d+', 'List multiplication creates references'),
        (r'mutable\s*=', 'Mutable default argument risk'),
    ]
    
    STYLE_PATTERNS = [
        (r'^\s{3}[^\s]', 'Indentation not multiple of 4'),
        (r';$', 'Trailing semicolon'),
        (r'print\s*\([^)]*\)$', 'Debug print statement'),
        (r'TODO|FIXME|XXX', 'TODO/FIXME/XXX found'),
        (r'\bpass\b', 'Empty pass statement'),
    ]
    
    def __init__(self):
        self.all_findings: List[ReviewFinding] = []
        self.files_reviewed = 0
        
    def review_file(self, filepath: Path) -> FileReview:
        """Review a single Python file."""
        self.files_reviewed += 1
        findings = []
        
        try:
            content = filepath.read_text()
            lines = content.split('\n')
        except Exception as e:
            return FileReview(
                file=str(filepath),
                lines=0,
                findings=[ReviewFinding(
                    file=str(filepath),
                    line=0,
                    severity='high',
                    category='bug',
                    message=f'Cannot read file: {e}',
                    suggestion='Check file permissions and encoding'
                )],
                score=0
            )
        
        # Pattern-based checks
        for line_num, line in enumerate(lines, 1):
            # Critical security patterns
            for pattern, message in self.CRITICAL_PATTERNS:
                if re.search(pattern, line):
                    findings.append(ReviewFinding(
                        file=str(filepath),
                        line=line_num,
                        severity='critical',
                        category='security',
                        message=message,
                        suggestion='Use safer alternatives or validate inputs'
                    ))
            
            # Bug patterns
            for pattern, message in self.BUG_PATTERNS:
                if re.search(pattern, line):
                    findings.append(ReviewFinding(
                        file=str(filepath),
                        line=line_num,
                        severity='high',
                        category='bug',
                        message=message,
                        suggestion='Fix the identified issue'
                    ))
            
            # Style patterns
            for pattern, message in self.STYLE_PATTERNS:
                if re.search(pattern, line):
                    findings.append(ReviewFinding(
                        file=str(filepath),
                        line=line_num,
                        severity='low',
                        category='style',
                        message=message,
                        suggestion='Clean up code style'
                    ))
        
        # AST-based checks
        try:
            tree = ast.parse(content)
            findings.extend(self._ast_checks(filepath, tree, lines))
        except SyntaxError as e:
            findings.append(ReviewFinding(
                file=str(filepath),
                line=e.lineno or 0,
                severity='critical',
                category='bug',
                message=f'Syntax error: {e.msg}',
                suggestion='Fix syntax error'
            ))
        
        # Calculate score
        score = self._calculate_score(findings, len(lines))
        
        return FileReview(
            file=str(filepath),
            lines=len(lines),
            findings=findings,
            score=score
        )
    
    def _ast_checks(self, filepath: Path, tree: ast.AST, lines: List[str]) -> List[ReviewFinding]:
        """AST-based code analysis."""
        findings = []
        
        for node in ast.walk(tree):
            # Check for mutable default arguments
            if isinstance(node, ast.FunctionDef):
                for default in node.args.defaults + node.args.kw_defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        findings.append(ReviewFinding(
                            file=str(filepath),
                            line=node.lineno,
                            severity='high',
                            category='bug',
                            message='Mutable default argument',
                            suggestion='Use None as default and initialize inside function'
                        ))
            
            # Check for bare except
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    findings.append(ReviewFinding(
                        file=str(filepath),
                        line=node.lineno,
                        severity='medium',
                        category='bug',
                        message='Bare except clause',
                        suggestion='Use specific exception types'
                    ))
            
            # Check for unused imports (simple check)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    # Simple heuristic - not comprehensive
                    if name.split('.')[0] not in str(tree):
                        pass  # Skip for now - would need more analysis
        
        return findings
    
    def _calculate_score(self, findings: List[ReviewFinding], total_lines: int) -> int:
        """Calculate review score (0-100)."""
        if not findings:
            return 100
        
        deductions = {
            'critical': 25,
            'high': 10,
            'medium': 5,
            'low': 1
        }
        
        total_deduction = sum(deductions.get(f.severity, 0) for f in findings)
        return max(0, 100 - total_deduction)
    
    def review_all(self, base_path: Path, pattern: str = "*.py") -> Dict[str, Any]:
        """Review all files matching pattern."""
        results = []
        
        for filepath in base_path.rglob(pattern):
            # Skip tests, venv, cache
            if any(skip in str(filepath) for skip in ['__pycache__', '.venv', 'venv', 'test_', '_test.py']):
                continue
            
            review = self.review_file(filepath)
            results.append(review)
            self.all_findings.extend(review.findings)
        
        return self._generate_report(results)
    
    def _generate_report(self, results: List[FileReview]) -> Dict[str, Any]:
        """Generate final review report."""
        total_findings = len(self.all_findings)
        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        category_counts = {}
        
        for f in self.all_findings:
            severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1
            category_counts[f.category] = category_counts.get(f.category, 0) + 1
        
        avg_score = sum(r.score for r in results) / len(results) if results else 0
        
        return {
            'timestamp': datetime.now().isoformat(),
            'files_reviewed': self.files_reviewed,
            'total_findings': total_findings,
            'severity_breakdown': severity_counts,
            'category_breakdown': category_counts,
            'average_score': round(avg_score, 2),
            'findings': [asdict(f) for f in self.all_findings[:50]],  # Top 50
            'file_reviews': [asdict(r) for r in results]
        }

def main():
    print("=" * 60)
    print("SYMPHONY FULL CODE REVIEW")
    print("=" * 60)
    print()
    
    reviewer = SymphonyReviewer()
    
    # Review each component
    components = [
        ("OpenClaw", Path("openclaw/src")),
        ("DevClaw Runner", Path("devclaw-runner/src")),
        ("Symphony Bridge", Path("symphony-bridge/src")),
        ("Shared Utils", Path("shared")),
    ]
    
    all_reports = {}
    
    for name, path in components:
        print(f"Reviewing {name}...")
        if path.exists():
            report = reviewer.review_all(path)
            all_reports[name] = report
            print(f"  Files: {report['files_reviewed']}, Findings: {report['total_findings']}, Score: {report['average_score']}")
        else:
            print(f"  Path not found: {path}")
        print()
    
    # Generate summary report
    summary = {
        'review_timestamp': datetime.now().isoformat(),
        'total_files': sum(r['files_reviewed'] for r in all_reports.values()),
        'total_findings': sum(r['total_findings'] for r in all_reports.values()),
        'overall_score': round(sum(r['average_score'] for r in all_reports.values()) / len(all_reports), 2),
        'component_reports': all_reports
    }
    
    # Save report
    report_path = Path('review_report.json')
    report_path.write_text(json.dumps(summary, indent=2))
    
    # Print summary
    print("=" * 60)
    print("REVIEW SUMMARY")
    print("=" * 60)
    print(f"Total Files Reviewed: {summary['total_files']}")
    print(f"Total Findings: {summary['total_findings']}")
    print(f"Overall Code Quality Score: {summary['overall_score']}/100")
    print()
    
    for name, report in all_reports.items():
        sev = report['severity_breakdown']
        print(f"{name}:")
        print(f"  Score: {report['average_score']}/100")
        print(f"  Critical: {sev.get('critical', 0)}, High: {sev.get('high', 0)}, Medium: {sev.get('medium', 0)}, Low: {sev.get('low', 0)}")
    
    print()
    print(f"Full report saved to: {report_path}")
    
    return summary

if __name__ == '__main__':
    main()
