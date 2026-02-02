"""
Report Generator - Generate audit reports in various formats

Produces markdown and JSON reports from audit results.
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict

from .schema_auditor import AuditResult, ModuleAuditResult, FieldIssue
from .standards import QualityLevel


class ReportGenerator:
    """
    Generates audit reports in various formats.

    Usage:
        from core.modules.audit import SchemaAuditor, ReportGenerator

        auditor = SchemaAuditor()
        result = auditor.audit_all()

        generator = ReportGenerator(result)
        generator.generate_all('/path/to/output')
    """

    def __init__(self, result: AuditResult):
        """
        Initialize report generator.

        Args:
            result: AuditResult from SchemaAuditor
        """
        self.result = result

    def generate_all(self, output_dir: str) -> None:
        """
        Generate all reports to output directory.

        Args:
            output_dir: Directory to write reports
        """
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'by_category'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'issues'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'fixes'), exist_ok=True)

        # Generate summary
        self._write_summary(os.path.join(output_dir, 'summary.md'))

        # Generate category reports
        for category, modules in self.result.by_category.items():
            self._write_category_report(
                os.path.join(output_dir, 'by_category', f'{category}.md'),
                category,
                modules
            )

        # Generate issue type reports (JSON)
        self._write_issue_reports(os.path.join(output_dir, 'issues'))

        # Generate suggested fixes
        self._write_suggested_fixes(os.path.join(output_dir, 'fixes', 'suggested_fixes.json'))

    def _write_summary(self, path: str) -> None:
        """Write summary report."""
        r = self.result

        lines = [
            "# Schema Audit Report",
            "",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Modules | {r.total_modules} |",
            f"| Modules with Issues | {r.modules_with_issues} ({r.modules_with_issues/r.total_modules*100:.1f}%) |",
            f"| Total Issues | {r.total_issues} |",
            f"| Critical Issues | {r.critical_issues} |",
            f"| Warning Issues | {r.warning_issues} |",
            f"| Info Issues | {r.info_issues} |",
            "",
            "## Issues by Type",
            "",
            "| Issue Type | Count |",
            "|------------|-------|",
        ]

        for issue_type, issues in sorted(r.by_issue_type.items(), key=lambda x: -len(x[1])):
            lines.append(f"| {issue_type} | {len(issues)} |")

        lines.extend([
            "",
            "## Issues by Category",
            "",
            "| Category | Modules | Issues | Critical |",
            "|----------|---------|--------|----------|",
        ])

        for category in sorted(r.by_category.keys()):
            modules = r.by_category[category]
            total_issues = sum(len(m.issues) for m in modules)
            critical = sum(m.critical_count for m in modules)
            lines.append(f"| {category} | {len(modules)} | {total_issues} | {critical} |")

        lines.extend([
            "",
            "## Top 10 Modules by Issues",
            "",
            "| Module | Category | Issues | Critical |",
            "|--------|----------|--------|----------|",
        ])

        sorted_modules = sorted(r.modules, key=lambda m: -len(m.issues))[:10]
        for m in sorted_modules:
            if m.has_issues:
                lines.append(f"| {m.module_id} | {m.category} | {len(m.issues)} | {m.critical_count} |")

        with open(path, 'w') as f:
            f.write('\n'.join(lines))

    def _write_category_report(self, path: str, category: str, modules: List[ModuleAuditResult]) -> None:
        """Write category-specific report."""
        lines = [
            f"# Category: {category}",
            "",
            f"Total Modules: {len(modules)}",
            f"Modules with Issues: {sum(1 for m in modules if m.has_issues)}",
            "",
            "## Modules",
            "",
        ]

        for module in sorted(modules, key=lambda m: m.module_id):
            if not module.has_issues:
                continue

            lines.extend([
                f"### {module.module_id}",
                "",
                f"Issues: {len(module.issues)} (Critical: {module.critical_count}, Warning: {module.warning_count}, Info: {module.info_count})",
                "",
                "| Field | Issue | Level | Suggestion |",
                "|-------|-------|-------|------------|",
            ])

            for issue in module.issues:
                suggestion = issue.suggested_fix or '-'
                if len(suggestion) > 40:
                    suggestion = suggestion[:37] + '...'
                lines.append(f"| {issue.field_name} | {issue.issue_type} | {issue.level.value} | {suggestion} |")

            lines.append("")

        with open(path, 'w') as f:
            f.write('\n'.join(lines))

    def _write_issue_reports(self, output_dir: str) -> None:
        """Write JSON reports for each issue type."""
        for issue_type, issues in self.result.by_issue_type.items():
            data = {
                'issue_type': issue_type,
                'total_count': len(issues),
                'issues': [
                    {
                        'module_id': i.module_id,
                        'field_name': i.field_name,
                        'level': i.level.value,
                        'message': i.message,
                        'suggested_fix': i.suggested_fix,
                    }
                    for i in issues
                ]
            }

            path = os.path.join(output_dir, f'{issue_type}.json')
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)

    def _write_suggested_fixes(self, path: str) -> None:
        """Write all suggested fixes to a JSON file."""
        fixes: Dict[str, Dict[str, Any]] = {}

        for module in self.result.modules:
            if not module.has_issues:
                continue

            module_fixes: Dict[str, Any] = {
                'category': module.category,
                'params_schema_fixes': {},
                'output_schema_fixes': {},
                'type_fixes': {},
            }

            for issue in module.issues:
                if not issue.suggested_fix:
                    continue

                if issue.issue_type in ('missing_description', 'missing_label', 'missing_placeholder'):
                    field_name = issue.field_name
                    if field_name not in module_fixes['params_schema_fixes']:
                        module_fixes['params_schema_fixes'][field_name] = {}

                    if issue.issue_type == 'missing_description':
                        module_fixes['params_schema_fixes'][field_name]['description'] = issue.suggested_fix
                    elif issue.issue_type == 'missing_label':
                        module_fixes['params_schema_fixes'][field_name]['label'] = issue.suggested_fix
                    elif issue.issue_type == 'missing_placeholder':
                        module_fixes['params_schema_fixes'][field_name]['placeholder'] = issue.suggested_fix

                elif issue.issue_type == 'output_missing_description':
                    field_name = issue.field_name.replace('output.', '')
                    module_fixes['output_schema_fixes'][field_name] = {
                        'description': issue.suggested_fix
                    }

                elif issue.issue_type in ('missing_input_types', 'missing_output_types'):
                    module_fixes['type_fixes'][issue.issue_type] = issue.suggested_fix

            if any(module_fixes['params_schema_fixes'] or
                   module_fixes['output_schema_fixes'] or
                   module_fixes['type_fixes']):
                fixes[module.module_id] = module_fixes

        with open(path, 'w') as f:
            json.dump(fixes, f, indent=2)

    def get_summary_dict(self) -> Dict[str, Any]:
        """Get summary as a dictionary."""
        r = self.result
        return {
            'total_modules': r.total_modules,
            'modules_with_issues': r.modules_with_issues,
            'total_issues': r.total_issues,
            'critical_issues': r.critical_issues,
            'warning_issues': r.warning_issues,
            'info_issues': r.info_issues,
            'issues_by_type': {k: len(v) for k, v in r.by_issue_type.items()},
            'issues_by_category': {
                k: sum(len(m.issues) for m in v)
                for k, v in r.by_category.items()
            },
        }

    def print_summary(self) -> None:
        """Print summary to console."""
        r = self.result
        print(f"\n{'='*60}")
        print("SCHEMA AUDIT SUMMARY")
        print(f"{'='*60}")
        print(f"Total Modules:        {r.total_modules}")
        print(f"Modules with Issues:  {r.modules_with_issues} ({r.modules_with_issues/r.total_modules*100:.1f}%)")
        print(f"Total Issues:         {r.total_issues}")
        print(f"  - Critical:         {r.critical_issues}")
        print(f"  - Warning:          {r.warning_issues}")
        print(f"  - Info:             {r.info_issues}")
        print(f"\nTop Issue Types:")
        for issue_type, issues in sorted(r.by_issue_type.items(), key=lambda x: -len(x[1]))[:5]:
            print(f"  - {issue_type}: {len(issues)}")
        print(f"{'='*60}\n")
