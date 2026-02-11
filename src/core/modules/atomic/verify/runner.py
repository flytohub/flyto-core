"""
Verify Run Module - Main entry point for design verification

Orchestrates: ruleset → capture → figma → compare → report
Uses other verify modules instead of inline logic.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field as schema_field


@register_module(
    module_id='verify.run',
    version='1.0.0',
    category='verify',
    tags=['verify', 'design', 'browser', 'figma', 'e2e'],
    label='Run Verification',
    label_key='modules.verify.run.label',
    description='Run full design verification: capture → compare → report',
    description_key='modules.verify.run.description',
    icon='CheckCircle',
    color='#8B5CF6',

    input_types=['string'],
    output_types=['object', 'file'],

    can_receive_from=['*'],
    can_connect_to=['notification.*', 'flow.*', 'file.*'],

    timeout_ms=120000,
    retryable=True,
    max_retries=1,
    concurrent_safe=False,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read', 'file.write'],

    params_schema=compose(
        schema_field('url', type='string', required=True, description='URL to verify', placeholder='https://example.com'),
        schema_field('selectors', type='array', required=False, description='CSS selectors to verify'),
        schema_field('ruleset_path', type='string', required=False, description='Path to YAML ruleset file', placeholder='/path/to/ruleset.yaml'),
        schema_field('expected_styles', type='object', required=False, description='Expected styles per selector'),
        schema_field('figma_file_id', type='string', required=False, description='Figma file ID for comparison', placeholder='xxxxxxxxx'),
        schema_field('figma_token', type='string', required=False, description='Figma token (or FIGMA_TOKEN env)', placeholder='figd_...'),
        schema_field('figma_mapping', type='object', required=False, description='Selector to Figma node mapping'),
        schema_field('output_dir', type='string', required=False, default='./verify-reports', description='Output directory', placeholder='/path/to/output'),
        schema_field('report_format', type='string', required=False, default='html', description='Report format', placeholder='html'),
        schema_field('take_screenshot', type='boolean', required=False, default=True, description='Capture screenshot'),
        schema_field('viewport_width', type='integer', required=False, default=1280, description='Viewport width'),
        schema_field('viewport_height', type='integer', required=False, default=800, description='Viewport height'),
    ),
    output_schema={
        'passed': {'type': 'boolean', 'description': 'Overall verification passed'},
        'summary': {'type': 'object', 'description': 'Summary statistics'},
        'report_path': {'type': 'string', 'description': 'Path to generated report'},
    },
    examples=[
        {
            'name': 'Verify with selectors',
            'params': {
                'url': 'http://localhost:3000',
                'selectors': ['button[type="submit"]', 'input[type="email"]'],
            }
        },
        {
            'name': 'Compare with Figma',
            'params': {
                'url': 'http://localhost:3000',
                'selectors': ['button.primary'],
                'figma_file_id': 'abc123xyz',
                'figma_mapping': {'button.primary': 'Primary Button'},
            }
        },
        {
            'name': 'Use YAML ruleset',
            'params': {
                'url': 'http://localhost:3000',
                'ruleset_path': './design-rules.yaml',
            }
        },
    ],
)
class VerifyRunModule(BaseModule):
    """Run full design verification workflow using other verify modules."""

    module_name = "Run Verification"
    module_description = "Orchestrate capture → compare → report"

    def validate_params(self) -> None:
        self.url = self.params.get('url')
        self.selectors = self.params.get('selectors', [])
        self.ruleset_path = self.params.get('ruleset_path')
        self.expected_styles = self.params.get('expected_styles', {})
        self.figma_file_id = self.params.get('figma_file_id')
        self.figma_token = self.params.get('figma_token')
        self.figma_mapping = self.params.get('figma_mapping', {})
        self.output_dir = Path(self.params.get('output_dir', './verify-reports'))
        self.report_format = self.params.get('report_format', 'html')
        self.take_screenshot = self.params.get('take_screenshot', True)
        self.viewport_width = self.params.get('viewport_width', 1280)
        self.viewport_height = self.params.get('viewport_height', 800)

        if not self.url:
            raise ValueError("url is required")
        if not self.selectors and not self.ruleset_path:
            raise ValueError("Either selectors or ruleset_path is required")

    async def execute(self) -> Dict[str, Any]:
        from .capture import VerifyCaptureModule
        from .compare import VerifyCompareModule, Severity
        from .figma import VerifyFigmaModule
        from .report import VerifyReportModule
        from .ruleset import VerifyRulesetModule, Rule

        results = []
        screenshots = []
        rules = []

        # Step 1: Load ruleset if provided
        if self.ruleset_path:
            ruleset_module = VerifyRulesetModule()
            ruleset_module.params = {'path': self.ruleset_path}
            ruleset_module.context = {}
            ruleset_module.validate_params()
            ruleset_result = await ruleset_module.execute()

            if ruleset_result.get('ok'):
                ruleset_data = ruleset_result['data']['ruleset']
                for rule_data in ruleset_data.get('rules', []):
                    rules.append(Rule.from_dict(rule_data))
                # Use ruleset's figma_file_id if not explicitly provided
                if not self.figma_file_id and ruleset_data.get('figma_file_id'):
                    self.figma_file_id = ruleset_data['figma_file_id']
        else:
            # Convert selectors to rules
            for selector in self.selectors:
                rules.append(Rule(
                    name=selector,
                    selector=selector,
                    figma_node=self.figma_mapping.get(selector),
                ))

        # Step 2: Fetch Figma styles if configured
        figma_styles = {}
        if self.figma_file_id:
            for rule in rules:
                if rule.figma_node:
                    try:
                        figma_module = VerifyFigmaModule()
                        figma_module.params = {
                            'file_id': self.figma_file_id,
                            'node_name': rule.figma_node,
                            'token': self.figma_token,
                        }
                        figma_module.context = {}
                        figma_module.validate_params()
                        figma_result = await figma_module.execute()

                        if figma_result.get('ok'):
                            figma_styles[rule.selector] = figma_result['data']['style']
                    except Exception as e:
                        # Continue without Figma style if fetch fails
                        pass

        # Step 3: Capture and compare each rule
        for rule in rules:
            # Capture browser styles
            capture_module = VerifyCaptureModule()
            capture_module.params = {
                'url': self.url,
                'selector': rule.selector,
                'viewport_width': self.viewport_width,
                'viewport_height': self.viewport_height,
            }
            capture_module.context = {}
            capture_module.validate_params()
            capture_result = await capture_module.execute()

            if not capture_result.get('ok') or not capture_result['data'].get('found'):
                # Element not found
                results.append({
                    'selector': rule.selector,
                    'passed': False,
                    'error_count': 1,
                    'warning_count': 0,
                    'violations': [{
                        'property': 'element',
                        'expected': 'exists',
                        'actual': 'not found',
                        'severity': 'error',
                        'message': f'Element not found: {rule.selector}',
                    }],
                })
                continue

            captured_element = capture_result['data']['element']

            # Get expected style (priority: explicit > figma > none)
            expected = self.expected_styles.get(rule.selector, {})
            if not expected and rule.selector in figma_styles:
                expected = figma_styles[rule.selector]

            # Compare if we have expected styles
            if expected:
                compare_module = VerifyCompareModule()
                compare_module.params = {
                    'actual': captured_element,
                    'expected': expected,
                    'selector': rule.selector,
                    'check_typography': rule.check_typography,
                    'check_colors': rule.check_colors,
                    'check_spacing': rule.check_spacing,
                    'check_sizing': rule.check_sizing,
                }
                compare_module.context = {}
                compare_module.validate_params()
                compare_result = await compare_module.execute()

                if compare_result.get('ok'):
                    results.append(compare_result['data'])
                else:
                    results.append({
                        'selector': rule.selector,
                        'passed': False,
                        'error_count': 1,
                        'warning_count': 0,
                        'violations': [{'property': 'compare', 'expected': 'success', 'actual': 'failed', 'severity': 'error'}],
                    })
            else:
                # No expected style - capture only (passes)
                results.append({
                    'selector': rule.selector,
                    'passed': True,
                    'error_count': 0,
                    'warning_count': 0,
                    'violations': [],
                    'captured_style': captured_element,
                })

        # Step 4: Take screenshot
        if self.take_screenshot:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = self.output_dir / 'screenshot.png'

            from core.browser.driver import BrowserDriver
            driver = BrowserDriver(headless=True)
            await driver.launch()
            try:
                page = await driver.new_page()
                await page.set_viewport_size({'width': self.viewport_width, 'height': self.viewport_height})
                await page.goto(self.url, wait_until='networkidle')
                await page.screenshot(path=str(screenshot_path), full_page=True)
                screenshots.append(str(screenshot_path))
            finally:
                await driver.close()

        # Step 5: Generate report
        report_module = VerifyReportModule()
        report_module.params = {
            'results': results,
            'name': 'verify-report',
            'url': self.url,
            'format': self.report_format,
            'output_dir': str(self.output_dir),
            'screenshots': screenshots,
        }
        report_module.context = {}
        report_module.validate_params()
        report_result = await report_module.execute()

        # Calculate summary
        total = len(results)
        passed = sum(1 for r in results if r.get('passed', False))
        errors = sum(r.get('error_count', 0) for r in results)
        warnings = sum(r.get('warning_count', 0) for r in results)

        return {
            'ok': True,
            'data': {
                'passed': errors == 0,
                'summary': {
                    'total_rules': total,
                    'passed_rules': passed,
                    'failed_rules': total - passed,
                    'error_count': errors,
                    'warning_count': warnings,
                    'pass_rate': round((passed / total * 100) if total > 0 else 100, 1),
                },
                'report_paths': report_result.get('data', {}).get('report_paths', {}),
                'results': results,
                'screenshots': screenshots,
            }
        }


# High-level wrapper class for convenience
class VerifyRunner:
    """
    High-level API for design verification.

    Usage:
        runner = VerifyRunner(output_dir="./reports")
        result = await runner.run_quick(url, selectors)
        result = await runner.run(url, ruleset_path)
        result = await runner.run_with_figma(url, selectors, figma_file_id, figma_mapping)
    """

    def __init__(self, output_dir: str = "./verify-reports", figma_token: str = None):
        self.output_dir = output_dir
        self.figma_token = figma_token

    async def run_quick(
        self,
        url: str,
        selectors: List[str],
        expected_styles: Dict[str, Dict] = None,
    ) -> Dict[str, Any]:
        """Quick verification with selectors."""
        module = VerifyRunModule()
        module.params = {
            'url': url,
            'selectors': selectors,
            'expected_styles': expected_styles or {},
            'output_dir': self.output_dir,
        }
        module.context = {}
        module.validate_params()
        return await module.execute()

    async def run(
        self,
        url: str,
        ruleset_path: str,
        report_format: str = "html",
    ) -> Dict[str, Any]:
        """Full verification with YAML ruleset."""
        module = VerifyRunModule()
        module.params = {
            'url': url,
            'ruleset_path': ruleset_path,
            'output_dir': self.output_dir,
            'report_format': report_format,
        }
        module.context = {}
        module.validate_params()
        return await module.execute()

    async def run_with_figma(
        self,
        url: str,
        selectors: List[str],
        figma_file_id: str,
        figma_mapping: Dict[str, str],
        expected_styles: Dict[str, Dict] = None,
    ) -> Dict[str, Any]:
        """Verification with Figma design comparison."""
        module = VerifyRunModule()
        module.params = {
            'url': url,
            'selectors': selectors,
            'figma_file_id': figma_file_id,
            'figma_mapping': figma_mapping,
            'figma_token': self.figma_token,
            'expected_styles': expected_styles or {},
            'output_dir': self.output_dir,
        }
        module.context = {}
        module.validate_params()
        return await module.execute()
