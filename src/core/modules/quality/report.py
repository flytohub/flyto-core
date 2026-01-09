"""
Report Generator

Generates validation reports in JSON and Markdown formats.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .types import AggregateReport, Severity, ValidationIssue


@dataclass
class ReportMetadata:
    """Metadata for a validation report."""
    generated_at: str
    strict_level: str
    total_modules: int
    passed_modules: int
    failed_modules: int


class ReportGenerator:
    """Generates validation reports in multiple formats."""

    def __init__(self, report: AggregateReport):
        """
        Initialize report generator.

        Args:
            report: AggregateReport to generate from
        """
        self.report = report

    def to_json(self, indent: int = 2) -> str:
        """
        Generate JSON report.

        Args:
            indent: JSON indentation level

        Returns:
            JSON string
        """
        data = self._build_report_data()
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def to_dict(self) -> Dict[str, Any]:
        """Generate report as dictionary."""
        return self._build_report_data()

    def to_markdown(self) -> str:
        """
        Generate Markdown report.

        Returns:
            Markdown string
        """
        lines = []

        # Header
        lines.append("# Validation Report")
        lines.append("")
        lines.append(f"**Generated**: {datetime.now().isoformat()}")
        lines.append(f"**Strict Level**: {self.report.strict_level.value}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Modules | {self.report.total_modules} |")
        lines.append(f"| Passed | {self.report.passed_modules} |")
        lines.append(f"| Failed | {self.report.failed_modules} |")
        lines.append(f"| Total Errors | {self.report.total_errors} |")
        lines.append(f"| Total Warnings | {self.report.total_warnings} |")
        lines.append(f"| Total Blockers | {self.report.total_blockers} |")
        lines.append("")

        # Result
        status = "PASSED" if self.report.passed() else "FAILED"
        lines.append(f"**Result**: {status}")
        lines.append("")

        # Issues by Severity
        if self.report.all_issues:
            lines.append("## Issues by Severity")
            lines.append("")
            for sev, count in sorted(self.report.issues_by_severity.items()):
                emoji = self._severity_emoji(sev)
                lines.append(f"- {emoji} {sev}: {count}")
            lines.append("")

            # Issues by Category
            lines.append("## Issues by Category")
            lines.append("")
            for cat, count in sorted(self.report.issues_by_category.items()):
                lines.append(f"- {cat.upper()}: {count}")
            lines.append("")

            # Top Offenders (modules with most issues)
            lines.append("## Top Offenders")
            lines.append("")
            top_offenders = self._get_top_offenders(limit=10)
            if top_offenders:
                lines.append("| Module | Issues |")
                lines.append("|--------|--------|")
                for module_id, count in top_offenders:
                    lines.append(f"| {module_id} | {count} |")
            else:
                lines.append("No issues found.")
            lines.append("")

            # Detailed Issues
            lines.append("## Detailed Issues")
            lines.append("")
            for r in self.report.reports:
                if r.issues:
                    lines.append(f"### {r.module_id}")
                    lines.append("")
                    for issue in r.issues:
                        emoji = self._severity_emoji(issue.severity.value)
                        loc = f" ({issue.file}:{issue.line})" if issue.file and issue.line else ""
                        lines.append(f"- {emoji} **{issue.rule_id}** [{issue.severity.value}]{loc}")
                        lines.append(f"  - {issue.message}")
                        if issue.suggestion:
                            lines.append(f"  - Suggestion: {issue.suggestion}")
                    lines.append("")

        return "\n".join(lines)

    def _build_report_data(self) -> Dict[str, Any]:
        """Build the complete report data structure."""
        return {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "strict_level": self.report.strict_level.value,
            },
            "summary": {
                "total_modules": self.report.total_modules,
                "passed_modules": self.report.passed_modules,
                "failed_modules": self.report.failed_modules,
                "total_issues": self.report.total_issues,
                "total_errors": self.report.total_errors,
                "total_warnings": self.report.total_warnings,
                "total_blockers": self.report.total_blockers,
            },
            "passed": self.report.passed(),
            "by_severity": self.report.issues_by_severity,
            "by_category": self.report.issues_by_category,
            "top_offenders": [
                {"module_id": m, "issue_count": c}
                for m, c in self._get_top_offenders(limit=10)
            ],
            "issues": [
                {
                    "module_id": issue.module_id,
                    "rule_id": issue.rule_id,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "file": issue.file,
                    "line": issue.line,
                    "col": issue.col,
                    "suggestion": issue.suggestion,
                }
                for issue in self.report.all_issues
            ],
            "modules": [
                {
                    "module_id": r.module_id,
                    "passed": r.passed,
                    "error_count": r.error_count,
                    "warning_count": r.warning_count,
                    "blocker_count": r.blocker_count,
                }
                for r in self.report.reports
            ],
        }

    def _get_top_offenders(self, limit: int = 10) -> List[tuple]:
        """Get modules with most issues."""
        counts = {}
        for r in self.report.reports:
            if r.issues:
                counts[r.module_id] = len(r.issues)

        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_counts[:limit]

    def _severity_emoji(self, severity: str) -> str:
        """Get emoji for severity level."""
        emojis = {
            "INFO": "i",
            "WARN": "!",
            "ERROR": "X",
            "BLOCKER": "XX",
            "FATAL": "XXX",
        }
        return emojis.get(severity, "?")


def generate_report(
    report: AggregateReport,
    format: str = "json",
) -> str:
    """
    Generate a validation report in the specified format.

    Args:
        report: AggregateReport to generate from
        format: Output format (json, markdown, text)

    Returns:
        Report string
    """
    generator = ReportGenerator(report)

    if format == "json":
        return generator.to_json()
    elif format == "markdown" or format == "md":
        return generator.to_markdown()
    else:
        # Default to text summary
        return report.format_summary()
