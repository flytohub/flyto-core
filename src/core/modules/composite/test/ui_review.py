"""
UI Review Composite Module

Complete AI-powered UI review workflow:
1. Start application server
2. Launch browser and navigate
3. Capture screenshots
4. AI analysis with vision
5. Generate improvement recommendations
6. Optionally auto-fix issues
7. Generate comprehensive report

Enhanced with Data Lineage Tracking:
- Each step categorized (observe/evaluate/decide/act/verify)
- Screenshots and reports stored as Artifacts
- AI decisions recorded with confidence and evidence
- Outputs lineage.json for visualization
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..base import CompositeModule, register_composite, UIVisibility
from ....engine.lineage import (
    RunTracker,
    StepCategory,
    ArtifactType,
)


@register_composite(
    module_id='composite.test.ui_review',
    version='1.0.0',
    category='test',
    subcategory='ui',
    tags=['test', 'ui', 'review', 'ai', 'vision', 'automation', 'quality'],

    # Context requirements
    requires_context=None,
    provides_context=['ui_review_results', 'screenshots', 'fixes'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='AI UI Review',
    ui_label_key='composite.test.ui_review.label',
    ui_description='Complete AI-powered UI review with optional auto-fix',
    ui_description_key='composite.test.ui_review.desc',
    ui_help='This composite module performs comprehensive UI review using AI vision. '
            'It captures screenshots, analyzes them with GPT-4 Vision, identifies issues, '
            'scores UI quality across multiple dimensions, and can optionally generate '
            'and apply code fixes automatically. Perfect for CI/CD quality gates.',
    ui_help_key='composite.test.ui_review.help',
    ui_group='Testing / UI Quality',
    ui_icon='Sparkles',
    ui_color='#8B5CF6',

    # Connection types
    input_types=['object', 'string'],
    input_type_labels={
        'object': 'Review Configuration',
        'string': 'Project Path',
    },
    input_type_descriptions={
        'object': 'Complete review configuration with pages and criteria',
        'string': 'Path to the project to review',
    },

    output_types=['object'],
    output_type_labels={
        'object': 'Review Report',
    },
    output_type_descriptions={
        'object': 'Comprehensive UI review report with scores, issues, and fixes',
    },

    # Connection suggestions
    suggested_predecessors=[
        'shell.exec',
        'file.read',
    ],
    suggested_successors=[
        'file.write',
        'webhook.trigger',
        'communication.slack_send',
    ],

    # UI form generation
    ui_params_schema={
        'project_path': {
            'type': 'string',
            'label': 'Project Path',
            'label_key': 'composite.test.ui_review.project_path.label',
            'description': 'Path to the project',
            'description_key': 'composite.test.ui_review.project_path.desc',
            'required': True,
            'placeholder': './my-app',
            'ui_component': 'input',
        },
        'start_command': {
            'type': 'string',
            'label': 'Start Command',
            'label_key': 'composite.test.ui_review.start_command.label',
            'description': 'Command to start the application',
            'description_key': 'composite.test.ui_review.start_command.desc',
            'placeholder': 'npm run dev',
            'default': 'npm run dev',
            'required': False,
            'ui_component': 'input',
        },
        'base_url': {
            'type': 'string',
            'label': 'Base URL',
            'label_key': 'composite.test.ui_review.base_url.label',
            'description': 'Application URL (if already running)',
            'description_key': 'composite.test.ui_review.base_url.desc',
            'placeholder': 'http://localhost:3000',
            'required': False,
            'ui_component': 'input',
        },
        'server_port': {
            'type': 'number',
            'label': 'Server Port',
            'label_key': 'composite.test.ui_review.server_port.label',
            'description': 'Port the server runs on',
            'description_key': 'composite.test.ui_review.server_port.desc',
            'default': 3000,
            'required': False,
            'ui_component': 'number',
        },
        'pages': {
            'type': 'array',
            'label': 'Pages to Review',
            'label_key': 'composite.test.ui_review.pages.label',
            'description': 'List of pages/routes to review',
            'description_key': 'composite.test.ui_review.pages.desc',
            'required': True,
            'ui_component': 'json',
            'examples': [
                {'path': '/', 'name': 'Home Page'},
                {'path': '/login', 'name': 'Login Page'},
                {'path': '/dashboard', 'name': 'Dashboard', 'auth_required': True}
            ],
        },
        'viewports': {
            'type': 'array',
            'label': 'Viewports',
            'label_key': 'composite.test.ui_review.viewports.label',
            'description': 'Screen sizes to test',
            'description_key': 'composite.test.ui_review.viewports.desc',
            'required': False,
            'default': [
                {'name': 'desktop', 'width': 1920, 'height': 1080},
                {'name': 'tablet', 'width': 768, 'height': 1024},
                {'name': 'mobile', 'width': 375, 'height': 812}
            ],
            'ui_component': 'json',
        },
        'evaluation_criteria': {
            'type': 'array',
            'label': 'Evaluation Criteria',
            'label_key': 'composite.test.ui_review.evaluation_criteria.label',
            'description': 'What to evaluate',
            'description_key': 'composite.test.ui_review.evaluation_criteria.desc',
            'required': False,
            'default': ['visual_design', 'usability', 'accessibility', 'consistency'],
            'ui_component': 'multiselect',
            'options': [
                {'value': 'visual_design', 'label': 'Visual Design'},
                {'value': 'usability', 'label': 'Usability'},
                {'value': 'accessibility', 'label': 'Accessibility'},
                {'value': 'consistency', 'label': 'Consistency'},
                {'value': 'typography', 'label': 'Typography'},
                {'value': 'color_scheme', 'label': 'Color Scheme'},
                {'value': 'responsiveness', 'label': 'Responsiveness'},
            ],
        },
        'min_score': {
            'type': 'number',
            'label': 'Minimum Pass Score',
            'label_key': 'composite.test.ui_review.min_score.label',
            'description': 'Minimum score to pass review (0-100)',
            'description_key': 'composite.test.ui_review.min_score.desc',
            'default': 70,
            'required': False,
            'ui_component': 'number',
            'validation': {
                'min': 0,
                'max': 100,
            },
        },
        'auto_fix': {
            'type': 'boolean',
            'label': 'Auto-Fix Issues',
            'label_key': 'composite.test.ui_review.auto_fix.label',
            'description': 'Automatically generate and suggest code fixes',
            'description_key': 'composite.test.ui_review.auto_fix.desc',
            'default': False,
            'required': False,
            'ui_component': 'switch',
        },
        'fix_mode': {
            'type': 'string',
            'label': 'Fix Mode',
            'label_key': 'composite.test.ui_review.fix_mode.label',
            'description': 'How to apply fixes',
            'description_key': 'composite.test.ui_review.fix_mode.desc',
            'default': 'suggest',
            'required': False,
            'enum': ['suggest', 'apply', 'dry_run'],
            'visible_when': {
                'field': 'auto_fix',
                'value': True
            },
        },
        'source_files': {
            'type': 'array',
            'label': 'Source Files',
            'label_key': 'composite.test.ui_review.source_files.label',
            'description': 'Files to analyze for fixes',
            'description_key': 'composite.test.ui_review.source_files.desc',
            'required': False,
            'placeholder': ['./src/components/*.tsx', './src/styles/*.css'],
            'visible_when': {
                'field': 'auto_fix',
                'value': True
            },
        },
        'screenshot_dir': {
            'type': 'string',
            'label': 'Screenshot Directory',
            'label_key': 'composite.test.ui_review.screenshot_dir.label',
            'description': 'Directory to save screenshots',
            'description_key': 'composite.test.ui_review.screenshot_dir.desc',
            'default': './ui-review-screenshots',
            'required': False,
            'ui_component': 'input',
        },
        'headless': {
            'type': 'boolean',
            'label': 'Headless Mode',
            'label_key': 'composite.test.ui_review.headless.label',
            'description': 'Run browser in headless mode',
            'description_key': 'composite.test.ui_review.headless.desc',
            'default': True,
            'required': False,
            'ui_component': 'switch',
        },
        'api_key': {
            'type': 'string',
            'label': 'OpenAI API Key',
            'label_key': 'composite.test.ui_review.api_key.label',
            'description': 'OpenAI API key for vision analysis',
            'description_key': 'composite.test.ui_review.api_key.desc',
            'required': False,
            'secret': True,
        },
        'lineage_output': {
            'type': 'string',
            'label': 'Lineage Output Path',
            'label_key': 'composite.test.ui_review.lineage_output.label',
            'description': 'Path to save lineage.json for visualization',
            'description_key': 'composite.test.ui_review.lineage_output.desc',
            'required': False,
            'default': './lineage.json',
            'ui_component': 'input',
        },
        'enable_lineage': {
            'type': 'boolean',
            'label': 'Enable Lineage Tracking',
            'label_key': 'composite.test.ui_review.enable_lineage.label',
            'description': 'Track execution lineage for visualization',
            'description_key': 'composite.test.ui_review.enable_lineage.desc',
            'default': True,
            'required': False,
            'ui_component': 'switch',
        },
    },

    # Steps definition
    steps=[
        {
            'id': 'start_server',
            'module': 'process.start',
            'params': {
                'command': '${params.start_command}',
                'cwd': '${params.project_path}',
                'name': 'ui-review-server',
                'wait_for_output': 'ready',
                'wait_timeout': 60
            },
            'skip_if': '${params.base_url}',
            'on_error': 'continue'
        },
        {
            'id': 'wait_port',
            'module': 'port.wait',
            'params': {
                'port': '${params.server_port}',
                'timeout': 60
            },
            'skip_if': '${params.base_url}'
        },
        {
            'id': 'launch_browser',
            'module': 'core.browser.launch',
            'params': {
                'headless': '${params.headless}'
            }
        },
        {
            'id': 'review_pages',
            'module': 'flow.foreach',
            'params': {
                'items': '${params.pages}',
                'variable': 'page'
            },
            'steps': [
                {
                    'id': 'goto_page',
                    'module': 'core.browser.goto',
                    'params': {
                        'url': '${params.base_url || "http://localhost:" + params.server_port}${page.path}'
                    }
                },
                {
                    'id': 'wait_load',
                    'module': 'core.browser.wait',
                    'params': {
                        'selector': 'body',
                        'timeout': 10000
                    }
                },
                {
                    'id': 'capture_screenshot',
                    'module': 'core.browser.screenshot',
                    'params': {
                        'path': '${params.screenshot_dir}/${page.name.replace(" ", "_")}.png',
                        'fullPage': True
                    }
                },
                {
                    'id': 'evaluate_ui',
                    'module': 'ui.evaluate',
                    'params': {
                        'screenshot': '${capture_screenshot.path}',
                        'page_type': '${page.name}',
                        'evaluation_criteria': '${params.evaluation_criteria}',
                        'min_score': '${params.min_score}',
                        'api_key': '${params.api_key}'
                    }
                }
            ]
        },
        {
            'id': 'generate_fixes',
            'module': 'llm.code_fix',
            'params': {
                'issues': '${collect_issues(review_pages)}',
                'source_files': '${params.source_files}',
                'fix_mode': '${params.fix_mode}',
                'api_key': '${params.api_key}'
            },
            'skip_if': '!${params.auto_fix}'
        },
        {
            'id': 'cleanup_browser',
            'module': 'core.browser.close',
            'params': {},
            'on_error': 'continue'
        },
        {
            'id': 'cleanup_server',
            'module': 'process.stop',
            'params': {
                'name': 'ui-review-server'
            },
            'skip_if': '${params.base_url}',
            'on_error': 'continue'
        }
    ],

    # Output schema
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether review passed minimum score'
        },
        'overall_score': {
            'type': 'number',
            'description': 'Average score across all pages'
        },
        'passed': {
            'type': 'boolean',
            'description': 'Whether all pages passed'
        },
        'pages': {
            'type': 'array',
            'description': 'Individual page review results'
        },
        'issues': {
            'type': 'array',
            'description': 'All issues found across pages'
        },
        'fixes': {
            'type': 'array',
            'description': 'Generated code fixes (if auto_fix enabled)'
        },
        'screenshots': {
            'type': 'array',
            'description': 'Paths to captured screenshots'
        },
        'summary': {
            'type': 'string',
            'description': 'Executive summary'
        },
        'lineage': {
            'type': 'object',
            'description': 'Execution lineage data for visualization'
        },
        'lineage_path': {
            'type': 'string',
            'description': 'Path to saved lineage.json file'
        }
    },

    # Execution settings
    timeout=600,  # 10 minutes
    retryable=False,
    max_retries=1,

    # Documentation
    examples=[
        {
            'name': 'Basic UI Review',
            'description': 'Review a React app with default settings',
            'params': {
                'project_path': './my-app',
                'start_command': 'npm run dev',
                'server_port': 3000,
                'pages': [
                    {'path': '/', 'name': 'Home'},
                    {'path': '/about', 'name': 'About'},
                ],
                'min_score': 70
            }
        },
        {
            'name': 'Full Review with Auto-Fix',
            'description': 'Complete review with automatic issue fixing',
            'params': {
                'project_path': './frontend',
                'start_command': 'npm start',
                'server_port': 3000,
                'pages': [
                    {'path': '/', 'name': 'Landing Page'},
                    {'path': '/login', 'name': 'Login'},
                    {'path': '/dashboard', 'name': 'Dashboard'},
                ],
                'viewports': [
                    {'name': 'desktop', 'width': 1920, 'height': 1080},
                    {'name': 'mobile', 'width': 375, 'height': 812}
                ],
                'evaluation_criteria': ['visual_design', 'usability', 'accessibility'],
                'min_score': 75,
                'auto_fix': True,
                'fix_mode': 'suggest',
                'source_files': [
                    './src/components/**/*.tsx',
                    './src/styles/**/*.css'
                ]
            }
        },
        {
            'name': 'CI/CD Quality Gate',
            'description': 'Use as a quality gate in CI/CD',
            'params': {
                'base_url': 'http://localhost:3000',
                'pages': [
                    {'path': '/', 'name': 'Home'},
                ],
                'min_score': 80,
                'headless': True,
                'screenshot_dir': './test-artifacts/ui-review'
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class AIUIReview(CompositeModule):
    """
    AI-Powered UI Review Composite Module

    This module provides comprehensive, automated UI quality review:

    1. **Application Management**
       - Starts development server if needed
       - Waits for server readiness
       - Handles cleanup after review

    2. **Multi-Page Review**
       - Navigates to each specified page
       - Captures full-page screenshots
       - Tests multiple viewports (desktop, tablet, mobile)

    3. **AI Vision Analysis**
       - Uses GPT-4 Vision to analyze screenshots
       - Evaluates visual design, usability, accessibility
       - Scores each dimension from 0-100

    4. **Issue Detection**
       - Identifies specific UI issues
       - Categorizes by severity (Critical, Major, Minor)
       - Pinpoints exact locations

    5. **Auto-Fix Generation** (optional)
       - Analyzes source code
       - Generates targeted fixes
       - Can apply fixes automatically

    6. **Reporting**
       - Comprehensive review report
       - Individual page scores
       - Actionable recommendations

    7. **Lineage Tracking** (new)
       - Each step categorized (observe/evaluate/decide/act/verify)
       - Screenshots and reports as Artifacts
       - AI decisions with confidence and evidence
       - Outputs lineage.json for swimlane visualization
    """

    def __init__(self, params: Dict[str, Any] = None):
        """Initialize with optional lineage tracking"""
        super().__init__(params or {})
        self._tracker: Optional[RunTracker] = None

    def _init_tracker(self) -> None:
        """Initialize the RunTracker if lineage is enabled"""
        if self.params.get('enable_lineage', True):
            self._tracker = RunTracker(
                workflow_name="AI UI Review",
                metadata={
                    'project_path': self.params.get('project_path'),
                    'pages': len(self.params.get('pages', [])),
                    'min_score': self.params.get('min_score', 70),
                    'auto_fix': self.params.get('auto_fix', False),
                }
            )

    def _track_step(
        self,
        step_id: str,
        module_id: str,
        category: StepCategory,
        inputs: Dict[str, Any] = None,
        outputs: Dict[str, Any] = None,
        name: str = None,
    ) -> Optional[str]:
        """Track a step execution if lineage is enabled"""
        if not self._tracker:
            return None

        tracked_id = self._tracker.start_step(
            module_id=module_id,
            category=category,
            name=name or step_id,
            inputs=inputs or {},
        )
        if outputs is not None:
            self._tracker.end_step(tracked_id, outputs=outputs)
        return tracked_id

    def _track_artifact(
        self,
        step_id: str,
        artifact_type: ArtifactType,
        name: str,
        path: str = None,
        data: Dict[str, Any] = None,
    ) -> Optional[str]:
        """Track an artifact if lineage is enabled"""
        if not self._tracker:
            return None

        return self._tracker.add_artifact(
            step_id=step_id,
            artifact_type=artifact_type,
            name=name,
            path=path,
            data=data,
        )

    def _track_decision(
        self,
        step_id: str,
        decision: str,
        reason: str,
        confidence: float,
        evidence: list = None,
    ) -> Optional[str]:
        """Record an AI decision if lineage is enabled"""
        if not self._tracker:
            return None

        return self._tracker.record_decision(
            step_id=step_id,
            decision=decision,
            reason=reason,
            confidence=confidence,
            evidence=evidence or [],
        )

    def _finalize_lineage(self, passed: bool) -> Dict[str, Any]:
        """Complete tracking and save lineage"""
        if not self._tracker:
            return {'lineage': None, 'lineage_path': None}

        self._tracker.complete(status="completed" if passed else "failed")

        # Save lineage file
        lineage_path = self.params.get('lineage_output', './lineage.json')
        try:
            self._tracker.save(lineage_path)
        except Exception as e:
            lineage_path = None

        return {
            'lineage': self._tracker.to_dict(),
            'lineage_path': str(lineage_path) if lineage_path else None,
        }

    def _build_output(self, metadata):
        """Build review report from step results with lineage tracking"""
        # Initialize tracker at the start
        self._init_tracker()

        pages_results = []
        all_issues = []
        all_screenshots = []
        all_artifact_ids = []
        total_score = 0
        page_count = 0
        all_passed = True

        # Track server start step (ACT)
        if not self.params.get('base_url'):
            server_result = self.step_results.get('start_server', {})
            step_id = self._track_step(
                step_id='start_server',
                module_id='process.start',
                category=StepCategory.ACT,
                name='Start Application Server',
                inputs={'command': self.params.get('start_command')},
                outputs={'ok': server_result.get('ok', False)},
            )

            # Track port wait (OBSERVE)
            port_result = self.step_results.get('wait_port', {})
            self._track_step(
                step_id='wait_port',
                module_id='port.wait',
                category=StepCategory.OBSERVE,
                name='Wait for Server Port',
                inputs={'port': self.params.get('server_port')},
                outputs={'available': port_result.get('available', False)},
            )

        # Track browser launch (ACT)
        browser_result = self.step_results.get('launch_browser', {})
        self._track_step(
            step_id='launch_browser',
            module_id='browser.launch',
            category=StepCategory.ACT,
            name='Launch Browser',
            inputs={'headless': self.params.get('headless', True)},
            outputs={'ok': browser_result.get('ok', False)},
        )

        # Process page reviews
        review_pages = self.step_results.get('review_pages', {})
        if isinstance(review_pages, dict):
            items = review_pages.get('results', [])
            for idx, item in enumerate(items):
                page_info = item.get('page', {})
                evaluation = item.get('evaluate_ui', {})
                screenshot = item.get('capture_screenshot', {})
                page_name = page_info.get('name', f'Page_{idx}')

                score = evaluation.get('overall_score', 0)
                passed = evaluation.get('passed', False)
                issues = evaluation.get('issues', [])

                total_score += score
                page_count += 1
                if not passed:
                    all_passed = False

                # Track screenshot capture (OBSERVE)
                screenshot_path = screenshot.get('path', '')
                screenshot_step_id = self._track_step(
                    step_id=f'screenshot_{idx}',
                    module_id='browser.screenshot',
                    category=StepCategory.OBSERVE,
                    name=f'Capture Screenshot: {page_name}',
                    inputs={'url': page_info.get('path')},
                    outputs={'path': screenshot_path},
                )

                # Track screenshot artifact
                screenshot_artifact_id = None
                if screenshot_step_id and screenshot_path:
                    screenshot_artifact_id = self._track_artifact(
                        step_id=screenshot_step_id,
                        artifact_type=ArtifactType.SCREENSHOT,
                        name=f'{page_name} Screenshot',
                        path=screenshot_path,
                    )
                    if screenshot_artifact_id:
                        all_artifact_ids.append(screenshot_artifact_id)

                # Track UI evaluation (EVALUATE)
                eval_step_id = self._track_step(
                    step_id=f'evaluate_{idx}',
                    module_id='ui.evaluate',
                    category=StepCategory.EVALUATE,
                    name=f'Evaluate UI: {page_name}',
                    inputs={'screenshot': screenshot_path},
                    outputs={
                        'score': score,
                        'passed': passed,
                        'issues_count': len(issues),
                    },
                )

                # Track evaluation report artifact
                report_artifact_id = None
                if eval_step_id:
                    report_artifact_id = self._track_artifact(
                        step_id=eval_step_id,
                        artifact_type=ArtifactType.REPORT,
                        name=f'{page_name} Evaluation Report',
                        data={
                            'scores': evaluation.get('scores', {}),
                            'issues': issues,
                            'recommendations': evaluation.get('recommendations', []),
                        },
                    )
                    if report_artifact_id:
                        all_artifact_ids.append(report_artifact_id)

                # Track decision (DECIDE)
                min_score = self.params.get('min_score', 70)
                decision_step_id = self._track_step(
                    step_id=f'decide_{idx}',
                    module_id='ai.decision',
                    category=StepCategory.DECIDE,
                    name=f'Quality Decision: {page_name}',
                    inputs={'score': score, 'threshold': min_score},
                    outputs={'decision': 'pass' if passed else 'need_fix'},
                )

                if decision_step_id:
                    evidence = []
                    if screenshot_artifact_id:
                        evidence.append(screenshot_artifact_id)
                    if report_artifact_id:
                        evidence.append(report_artifact_id)

                    self._track_decision(
                        step_id=decision_step_id,
                        decision='pass' if passed else 'need_fix',
                        reason=f"Score {score}/100 {'meets' if passed else 'below'} threshold {min_score}",
                        confidence=0.95 if abs(score - min_score) > 10 else 0.75,
                        evidence=evidence,
                    )

                pages_results.append({
                    'name': page_name,
                    'path': page_info.get('path', '/'),
                    'score': score,
                    'passed': passed,
                    'scores': evaluation.get('scores', {}),
                    'issues': issues,
                    'strengths': evaluation.get('strengths', []),
                    'recommendations': evaluation.get('recommendations', []),
                    'screenshot': screenshot_path
                })

                all_issues.extend([
                    {**issue, 'page': page_name}
                    for issue in issues
                ])

                if screenshot_path:
                    all_screenshots.append(screenshot_path)

        # Get fixes if generated
        fixes = []
        fix_result = self.step_results.get('generate_fixes', {})
        if fix_result:
            fixes = fix_result.get('fixes', [])

            # Track fix generation (ACT)
            if self.params.get('auto_fix'):
                fix_step_id = self._track_step(
                    step_id='generate_fixes',
                    module_id='llm.code_fix',
                    category=StepCategory.ACT,
                    name='Generate Code Fixes',
                    inputs={'issues_count': len(all_issues)},
                    outputs={'fixes_count': len(fixes)},
                )

                # Track each fix as a patch artifact
                for fix_idx, fix in enumerate(fixes):
                    if fix_step_id:
                        self._track_artifact(
                            step_id=fix_step_id,
                            artifact_type=ArtifactType.PATCH,
                            name=f"Fix: {fix.get('file', f'patch_{fix_idx}')}",
                            data=fix,
                        )

        overall_score = total_score // max(page_count, 1)
        min_score = self.params.get('min_score', 70)

        # Build summary
        critical_issues = len([i for i in all_issues if i.get('severity') == 'Critical'])
        major_issues = len([i for i in all_issues if i.get('severity') == 'Major'])

        summary = f"UI Review: {overall_score}/100 overall score across {page_count} pages. "
        if all_passed:
            summary += "All pages passed minimum threshold. "
        else:
            summary += f"Some pages below {min_score} threshold. "
        summary += f"Found {len(all_issues)} issues ({critical_issues} critical, {major_issues} major)."
        if fixes:
            summary += f" Generated {len(fixes)} code fixes."

        # Track cleanup steps (ACT)
        self._track_step(
            step_id='cleanup_browser',
            module_id='browser.close',
            category=StepCategory.ACT,
            name='Close Browser',
            inputs={},
            outputs={'ok': True},
        )

        if not self.params.get('base_url'):
            self._track_step(
                step_id='cleanup_server',
                module_id='process.stop',
                category=StepCategory.ACT,
                name='Stop Server',
                inputs={'name': 'ui-review-server'},
                outputs={'ok': True},
            )

        # Finalize lineage tracking
        final_passed = all_passed and critical_issues == 0
        lineage_data = self._finalize_lineage(final_passed)

        return {
            'ok': final_passed,
            'overall_score': overall_score,
            'passed': all_passed,
            'pages': pages_results,
            'issues': all_issues,
            'fixes': fixes,
            'screenshots': all_screenshots,
            'summary': summary,
            **lineage_data,
        }
