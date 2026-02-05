"""
Verify Report Module - Generate verification reports

Outputs HTML, JSON, or Markdown reports with screenshots.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field as schema_field


@register_module(
    module_id='verify.report',
    version='1.0.0',
    category='verify',
    tags=['verify', 'report', 'html', 'json', 'markdown'],
    label='Generate Report',
    label_key='modules.verify.report.label',
    description='Generate verification report in HTML/JSON/Markdown',
    description_key='modules.verify.report.description',
    icon='FileText',
    color='#8B5CF6',

    input_types=['object'],
    output_types=['string', 'file'],

    can_receive_from=['verify.compare', 'verify.*'],
    can_connect_to=['file.*', 'notification.*', 'flow.*'],

    timeout_ms=10000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.write'],

    params_schema=compose(
        schema_field('results', type='array', required=True, description='Comparison results from verify.compare'),
        schema_field('name', type='string', required=False, default='verify-report', description='Report name'),
        schema_field('url', type='string', required=False, description='URL that was verified'),
        schema_field('format', type='string', required=False, default='html', description='Output format (html, json, markdown, all)'),
        schema_field('output_dir', type='string', required=False, default='./verify-reports', description='Output directory'),
        schema_field('screenshots', type='array', required=False, description='Screenshot paths to include'),
    ),
    output_schema={
        'report_path': {'type': 'string', 'description': 'Path to generated report'},
        'summary': {'type': 'object', 'description': 'Summary statistics'},
    },
)
class VerifyReportModule(BaseModule):
    """Generate verification report."""

    module_name = "Generate Report"
    module_description = "Create HTML/JSON/Markdown verification report"

    def validate_params(self) -> None:
        self.results = self.params.get('results', [])
        self.name = self.params.get('name', 'verify-report')
        self.url = self.params.get('url', '')
        self.format = self.params.get('format', 'html')
        self.output_dir = Path(self.params.get('output_dir', './verify-reports'))
        self.screenshots = self.params.get('screenshots', [])

        # Use compare_result from context if not provided
        if not self.results and 'compare_result' in self.context:
            result = self.context['compare_result']
            self.results = [result.to_dict() if hasattr(result, 'to_dict') else result]

    async def execute(self) -> Dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Calculate summary
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get('passed', False))
        failed = total - passed
        total_violations = sum(len(r.get('violations', [])) for r in self.results)
        errors = sum(r.get('error_count', 0) for r in self.results)
        warnings = sum(r.get('warning_count', 0) for r in self.results)

        summary = {
            'overall_passed': errors == 0,
            'pass_rate': round((passed / total * 100) if total > 0 else 100, 1),
            'total_rules': total,
            'passed_rules': passed,
            'failed_rules': failed,
            'total_violations': total_violations,
            'error_count': errors,
            'warning_count': warnings,
        }

        report_data = {
            'name': self.name,
            'url': self.url,
            'created_at': datetime.now().isoformat(),
            'summary': summary,
            'results': self.results,
            'screenshots': self.screenshots,
        }

        report_paths = {}

        if self.format in ('html', 'all'):
            path = self.output_dir / f'{self.name}.html'
            path.write_text(self._generate_html(report_data), encoding='utf-8')
            report_paths['html'] = str(path)

        if self.format in ('json', 'all'):
            path = self.output_dir / f'{self.name}.json'
            path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding='utf-8')
            report_paths['json'] = str(path)

        if self.format in ('markdown', 'all'):
            path = self.output_dir / f'{self.name}.md'
            path.write_text(self._generate_markdown(report_data), encoding='utf-8')
            report_paths['markdown'] = str(path)

        return {
            'ok': True,
            'data': {
                'report_paths': report_paths,
                'summary': summary,
            }
        }

    def _generate_html(self, data: Dict) -> str:
        summary = data['summary']
        status_class = 'pass' if summary['overall_passed'] else 'fail'
        status_text = 'PASSED' if summary['overall_passed'] else 'FAILED'

        results_html = ''
        for result in data['results']:
            result_class = 'pass' if result.get('passed') else 'fail'
            violations_html = ''
            for v in result.get('violations', []):
                severity = v.get('severity', 'warning')
                violations_html += f'''
                <div class="violation {severity}">
                    <span class="severity">{severity.upper()}</span>
                    <span class="property">{v.get('property')}</span>:
                    expected <code>{v.get('expected')}</code>,
                    got <code>{v.get('actual')}</code>
                    {f"(diff: {v.get('difference')})" if v.get('difference') else ''}
                </div>
                '''

            results_html += f'''
            <div class="result {result_class}">
                <h3>{"✓" if result.get('passed') else "✗"} {result.get('selector', 'unknown')}</h3>
                {violations_html if violations_html else '<p class="no-violations">No violations</p>'}
            </div>
            '''

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify Report - {data['name']}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 2rem; background: #f5f5f5; }}
        .header {{ background: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 1rem; }}
        .summary-card {{ background: white; padding: 1rem; border-radius: 8px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .summary-card .value {{ font-size: 2rem; font-weight: bold; }}
        .summary-card.pass .value {{ color: #22c55e; }}
        .summary-card.fail .value {{ color: #ef4444; }}
        .result {{ background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .result.pass {{ border-left: 4px solid #22c55e; }}
        .result.fail {{ border-left: 4px solid #ef4444; }}
        .result h3 {{ margin: 0 0 0.5rem 0; font-size: 1rem; }}
        .violation {{ padding: 0.5rem; margin: 0.25rem 0; border-radius: 4px; font-size: 0.9rem; }}
        .violation.error {{ background: #fef2f2; color: #991b1b; }}
        .violation.warning {{ background: #fffbeb; color: #92400e; }}
        .violation.info {{ background: #eff6ff; color: #1e40af; }}
        .severity {{ font-weight: bold; margin-right: 0.5rem; }}
        code {{ background: #e5e7eb; padding: 0.125rem 0.25rem; border-radius: 3px; }}
        .no-violations {{ color: #22c55e; margin: 0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{data['name']}</h1>
        <div>{data.get('url', '')}</div>
    </div>
    <div class="summary">
        <div class="summary-card {status_class}"><div class="value">{status_text}</div><div>Status</div></div>
        <div class="summary-card"><div class="value">{summary['pass_rate']}%</div><div>Pass Rate</div></div>
        <div class="summary-card"><div class="value">{summary['passed_rules']}/{summary['total_rules']}</div><div>Rules</div></div>
        <div class="summary-card fail"><div class="value">{summary['error_count']}</div><div>Errors</div></div>
    </div>
    <h2>Results</h2>
    {results_html}
    <div style="color:#999;font-size:0.8rem;text-align:center;margin-top:2rem;">Generated at {data['created_at']}</div>
</body>
</html>'''

    def _generate_markdown(self, data: Dict) -> str:
        summary = data['summary']
        status = ":white_check_mark: PASSED" if summary['overall_passed'] else ":x: FAILED"

        lines = [
            f"# Verify Report: {data['name']}",
            "",
            f"**URL:** {data.get('url', 'N/A')}",
            f"**Status:** {status}",
            f"**Pass Rate:** {summary['pass_rate']}%",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Rules | {summary['total_rules']} |",
            f"| Passed | {summary['passed_rules']} |",
            f"| Failed | {summary['failed_rules']} |",
            f"| Errors | {summary['error_count']} |",
            f"| Warnings | {summary['warning_count']} |",
            "",
            "## Results",
            "",
        ]

        for result in data['results']:
            icon = ":white_check_mark:" if result.get('passed') else ":x:"
            lines.append(f"### {icon} `{result.get('selector', 'unknown')}`")
            lines.append("")

            violations = result.get('violations', [])
            if violations:
                lines.append("| Severity | Property | Expected | Actual | Diff |")
                lines.append("|----------|----------|----------|--------|------|")
                for v in violations:
                    diff = v.get('difference', '-')
                    lines.append(f"| {v.get('severity')} | {v.get('property')} | {v.get('expected')} | {v.get('actual')} | {diff} |")
                lines.append("")
            else:
                lines.append("*No violations*")
                lines.append("")

        lines.append(f"---")
        lines.append(f"*Generated at {data['created_at']}*")

        return "\n".join(lines)
