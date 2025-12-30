"""
Verify Fix Composite Module

Re-evaluates UI after fixes are applied:
1. Reload page (or restart server if needed)
2. Recapture screenshots
3. Re-run AI evaluation
4. Compare before/after scores
5. Determine if fix was successful
6. Track verification in lineage (VERIFY category)
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import CompositeModule, register_composite, UIVisibility
from ....engine.lineage import (
    RunTracker,
    StepCategory,
    ArtifactType,
)


logger = logging.getLogger(__name__)


@register_composite(
    module_id='composite.test.verify_fix',
    version='1.0.0',
    category='test',
    subcategory='verify',
    tags=['test', 'verify', 'fix', 'validation', 'qa', 'automation'],

    # Context requirements
    requires_context=['ui_review_results'],
    provides_context=['verification_results'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='Verify Fix',
    ui_label_key='composite.test.verify_fix.label',
    ui_description='Verify that applied fixes resolved UI issues',
    ui_description_key='composite.test.verify_fix.desc',
    ui_help='This composite re-evaluates the UI after fixes are applied. '
            'It captures new screenshots, runs AI evaluation, and compares '
            'before/after scores to determine if fixes were successful.',
    ui_help_key='composite.test.verify_fix.help',
    ui_group='Testing / Verification',
    ui_icon='CheckCircle2',
    ui_color='#10B981',

    # Connection types
    input_types=['object'],
    input_type_labels={
        'object': 'UI Review Results',
    },
    input_type_descriptions={
        'object': 'Results from previous ui_review including fixes applied',
    },

    output_types=['object'],
    output_type_labels={
        'object': 'Verification Report',
    },
    output_type_descriptions={
        'object': 'Verification results comparing before/after fix states',
    },

    # Connection suggestions
    suggested_predecessors=[
        'composite.test.ui_review',
        'llm.code_fix',
    ],
    suggested_successors=[
        'composite.test.quality_gate',
        'file.write',
        'communication.slack_send',
    ],

    # UI form generation
    ui_params_schema={
        'previous_results': {
            'type': 'object',
            'label': 'Previous Results',
            'label_key': 'composite.test.verify_fix.previous_results.label',
            'description': 'Results from ui_review or previous verification',
            'description_key': 'composite.test.verify_fix.previous_results.desc',
            'required': True,
            'ui_component': 'json',
        },
        'base_url': {
            'type': 'string',
            'label': 'Base URL',
            'label_key': 'composite.test.verify_fix.base_url.label',
            'description': 'Application URL to verify',
            'description_key': 'composite.test.verify_fix.base_url.desc',
            'required': True,
            'placeholder': 'http://localhost:3000',
        },
        'pages_to_verify': {
            'type': 'array',
            'label': 'Pages to Verify',
            'label_key': 'composite.test.verify_fix.pages.label',
            'description': 'Specific pages to re-verify (defaults to failed pages)',
            'description_key': 'composite.test.verify_fix.pages.desc',
            'required': False,
            'ui_component': 'json',
        },
        'evaluation_criteria': {
            'type': 'array',
            'label': 'Evaluation Criteria',
            'label_key': 'composite.test.verify_fix.criteria.label',
            'description': 'Criteria to evaluate',
            'description_key': 'composite.test.verify_fix.criteria.desc',
            'required': False,
            'default': ['visual_design', 'usability', 'accessibility', 'consistency'],
        },
        'improvement_threshold': {
            'type': 'number',
            'label': 'Improvement Threshold',
            'label_key': 'composite.test.verify_fix.threshold.label',
            'description': 'Minimum score improvement to consider fix successful (points)',
            'description_key': 'composite.test.verify_fix.threshold.desc',
            'default': 5,
            'required': False,
            'validation': {
                'min': 0,
                'max': 100,
            },
        },
        'min_score': {
            'type': 'number',
            'label': 'Minimum Pass Score',
            'label_key': 'composite.test.verify_fix.min_score.label',
            'description': 'Minimum score to pass verification',
            'description_key': 'composite.test.verify_fix.min_score.desc',
            'default': 70,
            'required': False,
        },
        'max_iterations': {
            'type': 'number',
            'label': 'Max Iterations',
            'label_key': 'composite.test.verify_fix.max_iterations.label',
            'description': 'Maximum fix-verify cycles before giving up',
            'description_key': 'composite.test.verify_fix.max_iterations.desc',
            'default': 3,
            'required': False,
        },
        'screenshot_dir': {
            'type': 'string',
            'label': 'Screenshot Directory',
            'label_key': 'composite.test.verify_fix.screenshot_dir.label',
            'description': 'Directory to save verification screenshots',
            'description_key': 'composite.test.verify_fix.screenshot_dir.desc',
            'default': './verify-screenshots',
            'required': False,
        },
        'headless': {
            'type': 'boolean',
            'label': 'Headless Mode',
            'label_key': 'composite.test.verify_fix.headless.label',
            'description': 'Run browser in headless mode',
            'description_key': 'composite.test.verify_fix.headless.desc',
            'default': True,
            'required': False,
        },
        'api_key': {
            'type': 'string',
            'label': 'OpenAI API Key',
            'label_key': 'composite.test.verify_fix.api_key.label',
            'description': 'OpenAI API key for vision analysis',
            'description_key': 'composite.test.verify_fix.api_key.desc',
            'required': False,
            'secret': True,
        },
        'append_to_lineage': {
            'type': 'object',
            'label': 'Append to Lineage',
            'label_key': 'composite.test.verify_fix.append_lineage.label',
            'description': 'Existing lineage data to append to',
            'description_key': 'composite.test.verify_fix.append_lineage.desc',
            'required': False,
        },
        'lineage_output': {
            'type': 'string',
            'label': 'Lineage Output Path',
            'label_key': 'composite.test.verify_fix.lineage_output.label',
            'description': 'Path to save lineage.json',
            'description_key': 'composite.test.verify_fix.lineage_output.desc',
            'default': './lineage.json',
            'required': False,
        },
    },

    # Steps definition
    steps=[
        {
            'id': 'launch_browser',
            'module': 'core.browser.launch',
            'params': {
                'headless': '${params.headless}'
            }
        },
        {
            'id': 'verify_pages',
            'module': 'flow.foreach',
            'params': {
                'items': '${get_pages_to_verify()}',
                'variable': 'page'
            },
            'steps': [
                {
                    'id': 'goto_page',
                    'module': 'core.browser.goto',
                    'params': {
                        'url': '${params.base_url}${page.path}'
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
                        'path': '${params.screenshot_dir}/verify_${page.name.replace(" ", "_")}.png',
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
            'id': 'cleanup_browser',
            'module': 'core.browser.close',
            'params': {},
            'on_error': 'continue'
        }
    ],

    # Output schema
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether verification passed (all pages improved)'
        },
        'verified': {
            'type': 'boolean',
            'description': 'Whether fixes were successfully verified'
        },
        'pages': {
            'type': 'array',
            'description': 'Individual page verification results'
        },
        'improvements': {
            'type': 'object',
            'description': 'Score improvements per page'
        },
        'regression': {
            'type': 'array',
            'description': 'Pages that got worse after fix'
        },
        'summary': {
            'type': 'string',
            'description': 'Verification summary'
        },
        'recommendation': {
            'type': 'string',
            'description': 'Next action recommendation'
        },
        'lineage': {
            'type': 'object',
            'description': 'Lineage data for visualization'
        },
        'lineage_path': {
            'type': 'string',
            'description': 'Path to saved lineage file'
        }
    },

    # Execution settings
    timeout=300,
    retryable=True,
    max_retries=2,

    # Documentation
    examples=[
        {
            'name': 'Basic Verification',
            'description': 'Verify fixes from ui_review',
            'params': {
                'previous_results': '${ui_review.output}',
                'base_url': 'http://localhost:3000',
                'min_score': 70
            }
        },
        {
            'name': 'Targeted Verification',
            'description': 'Verify specific pages',
            'params': {
                'previous_results': '${ui_review.output}',
                'base_url': 'http://localhost:3000',
                'pages_to_verify': [
                    {'path': '/login', 'name': 'Login Page'}
                ],
                'improvement_threshold': 10
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class VerifyFix(CompositeModule):
    """
    Verify Fix Composite Module

    Re-evaluates UI after fixes are applied to confirm improvements:

    1. **Page Selection**
       - By default, re-verifies only failed pages
       - Can specify explicit pages to verify
       - Skips already passing pages (unless explicitly included)

    2. **Screenshot Capture**
       - Captures fresh screenshots after fixes
       - Stores in separate verification directory
       - Timestamps for comparison

    3. **AI Re-evaluation**
       - Runs same evaluation criteria as original
       - Compares scores before/after
       - Identifies remaining issues

    4. **Improvement Analysis**
       - Calculates score delta per page
       - Identifies regressions (scores went down)
       - Determines if threshold met

    5. **Verdict**
       - PASS: All pages improved above threshold
       - PARTIAL: Some pages improved, some didn't
       - FAIL: No improvement or regression

    6. **Lineage Tracking**
       - All verification steps are VERIFY category
       - Links to original DECIDE steps
       - Creates verification decision nodes
    """

    def __init__(self, params: Dict[str, Any] = None):
        """Initialize with verification parameters"""
        super().__init__(params or {})
        self._tracker: Optional[RunTracker] = None
        self._previous_results: Dict[str, Any] = {}

    def _init_tracker(self, existing_lineage: Optional[Dict] = None) -> None:
        """Initialize RunTracker, optionally appending to existing lineage"""
        # If we have existing lineage, we could merge but for now start fresh
        # with a reference to the original run
        original_run_id = None
        if existing_lineage:
            original_run_id = existing_lineage.get('id')

        self._tracker = RunTracker(
            workflow_name="Verify Fix",
            metadata={
                'original_run_id': original_run_id,
                'verification_time': datetime.utcnow().isoformat(),
                'pages_count': len(self._get_pages_to_verify()),
            }
        )

    def _get_pages_to_verify(self) -> List[Dict[str, Any]]:
        """Get list of pages to verify"""
        # Explicit list takes priority
        explicit_pages = self.params.get('pages_to_verify')
        if explicit_pages:
            return explicit_pages

        # Otherwise, get failed pages from previous results
        previous = self.params.get('previous_results', {})
        pages = previous.get('pages', [])

        failed_pages = [
            {'path': p.get('path', '/'), 'name': p.get('name', 'Page')}
            for p in pages
            if not p.get('passed', True)
        ]

        return failed_pages or pages

    def _track_step(
        self,
        step_id: str,
        module_id: str,
        category: StepCategory,
        inputs: Dict[str, Any] = None,
        outputs: Dict[str, Any] = None,
        name: str = None,
    ) -> Optional[str]:
        """Track a step execution"""
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
        """Track an artifact"""
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
        """Record a verification decision"""
        if not self._tracker:
            return None

        return self._tracker.record_decision(
            step_id=step_id,
            decision=decision,
            reason=reason,
            confidence=confidence,
            evidence=evidence or [],
        )

    def _finalize_lineage(self, verified: bool) -> Dict[str, Any]:
        """Complete tracking and save lineage"""
        if not self._tracker:
            return {'lineage': None, 'lineage_path': None}

        self._tracker.complete(status="completed" if verified else "failed")

        lineage_path = self.params.get('lineage_output', './lineage.json')
        try:
            self._tracker.save(lineage_path)
        except Exception as e:
            logger.warning(f"Failed to save lineage: {e}")
            lineage_path = None

        return {
            'lineage': self._tracker.to_dict(),
            'lineage_path': str(lineage_path) if lineage_path else None,
        }

    def _build_output(self, metadata):
        """Build verification report from step results"""
        # Get previous results for comparison
        self._previous_results = self.params.get('previous_results', {})
        previous_pages = {
            p.get('name'): p
            for p in self._previous_results.get('pages', [])
        }

        # Initialize tracker
        existing_lineage = self.params.get('append_to_lineage')
        self._init_tracker(existing_lineage)

        # Track browser launch (ACT)
        browser_result = self.step_results.get('launch_browser', {})
        self._track_step(
            step_id='launch_browser',
            module_id='browser.launch',
            category=StepCategory.ACT,
            name='Launch Browser for Verification',
            inputs={'headless': self.params.get('headless', True)},
            outputs={'ok': browser_result.get('ok', False)},
        )

        verified_pages = []
        improvements = {}
        regressions = []
        all_artifact_ids = []
        total_improvement = 0
        improvement_threshold = self.params.get('improvement_threshold', 5)
        min_score = self.params.get('min_score', 70)

        # Process verification results
        verify_pages = self.step_results.get('verify_pages', {})
        if isinstance(verify_pages, dict):
            items = verify_pages.get('results', [])
            for idx, item in enumerate(items):
                page_info = item.get('page', {})
                evaluation = item.get('evaluate_ui', {})
                screenshot = item.get('capture_screenshot', {})
                page_name = page_info.get('name', f'Page_{idx}')

                new_score = evaluation.get('overall_score', 0)
                new_passed = evaluation.get('passed', False)
                new_issues = evaluation.get('issues', [])

                # Get previous score for comparison
                prev_page = previous_pages.get(page_name, {})
                prev_score = prev_page.get('score', 0)
                prev_issues = prev_page.get('issues', [])

                score_delta = new_score - prev_score
                issues_fixed = len(prev_issues) - len(new_issues)
                total_improvement += score_delta

                # Track screenshot capture (OBSERVE)
                screenshot_path = screenshot.get('path', '')
                screenshot_step_id = self._track_step(
                    step_id=f'verify_screenshot_{idx}',
                    module_id='browser.screenshot',
                    category=StepCategory.OBSERVE,
                    name=f'Verify Screenshot: {page_name}',
                    inputs={'url': page_info.get('path')},
                    outputs={'path': screenshot_path},
                )

                # Track screenshot artifact
                screenshot_artifact_id = None
                if screenshot_step_id and screenshot_path:
                    screenshot_artifact_id = self._track_artifact(
                        step_id=screenshot_step_id,
                        artifact_type=ArtifactType.SCREENSHOT,
                        name=f'{page_name} Verification Screenshot',
                        path=screenshot_path,
                    )
                    if screenshot_artifact_id:
                        all_artifact_ids.append(screenshot_artifact_id)

                # Track re-evaluation (EVALUATE)
                eval_step_id = self._track_step(
                    step_id=f'verify_evaluate_{idx}',
                    module_id='ui.evaluate',
                    category=StepCategory.EVALUATE,
                    name=f'Re-evaluate: {page_name}',
                    inputs={
                        'screenshot': screenshot_path,
                        'previous_score': prev_score,
                    },
                    outputs={
                        'score': new_score,
                        'delta': score_delta,
                        'passed': new_passed,
                        'issues_remaining': len(new_issues),
                    },
                )

                # Track evaluation report
                report_artifact_id = None
                if eval_step_id:
                    report_artifact_id = self._track_artifact(
                        step_id=eval_step_id,
                        artifact_type=ArtifactType.REPORT,
                        name=f'{page_name} Verification Report',
                        data={
                            'before': {'score': prev_score, 'issues': len(prev_issues)},
                            'after': {'score': new_score, 'issues': len(new_issues)},
                            'delta': score_delta,
                            'issues_fixed': issues_fixed,
                        },
                    )
                    if report_artifact_id:
                        all_artifact_ids.append(report_artifact_id)

                # Determine verification verdict
                if score_delta < 0:
                    verdict = 'regression'
                    regressions.append(page_name)
                elif score_delta >= improvement_threshold and new_passed:
                    verdict = 'verified'
                elif new_passed:
                    verdict = 'pass'
                elif score_delta > 0:
                    verdict = 'improved'
                else:
                    verdict = 'no_change'

                # Track verification decision (VERIFY)
                verify_step_id = self._track_step(
                    step_id=f'verify_decision_{idx}',
                    module_id='ai.verify',
                    category=StepCategory.VERIFY,
                    name=f'Verify Fix: {page_name}',
                    inputs={
                        'prev_score': prev_score,
                        'new_score': new_score,
                        'threshold': improvement_threshold,
                    },
                    outputs={'verdict': verdict},
                )

                if verify_step_id:
                    evidence = []
                    if screenshot_artifact_id:
                        evidence.append(screenshot_artifact_id)
                    if report_artifact_id:
                        evidence.append(report_artifact_id)

                    self._track_decision(
                        step_id=verify_step_id,
                        decision=verdict,
                        reason=f"Score changed from {prev_score} to {new_score} (delta: {score_delta:+d})",
                        confidence=0.9 if abs(score_delta) > 5 else 0.7,
                        evidence=evidence,
                    )

                verified_pages.append({
                    'name': page_name,
                    'path': page_info.get('path', '/'),
                    'previous_score': prev_score,
                    'new_score': new_score,
                    'delta': score_delta,
                    'passed': new_passed,
                    'verdict': verdict,
                    'issues_before': len(prev_issues),
                    'issues_after': len(new_issues),
                    'issues_fixed': issues_fixed,
                    'screenshot': screenshot_path,
                })

                improvements[page_name] = {
                    'score_delta': score_delta,
                    'issues_fixed': issues_fixed,
                    'verdict': verdict,
                }

        # Track cleanup
        self._track_step(
            step_id='cleanup_browser',
            module_id='browser.close',
            category=StepCategory.ACT,
            name='Close Browser',
            inputs={},
            outputs={'ok': True},
        )

        # Calculate overall result
        pages_verified = len([p for p in verified_pages if p['verdict'] == 'verified'])
        pages_improved = len([p for p in verified_pages if p['delta'] > 0])
        pages_regressed = len(regressions)
        total_pages = len(verified_pages)

        all_verified = pages_verified == total_pages and pages_regressed == 0
        avg_improvement = total_improvement / max(total_pages, 1)

        # Build summary
        summary = f"Verification: {pages_verified}/{total_pages} pages verified. "
        summary += f"Average improvement: {avg_improvement:+.1f} points. "
        if pages_regressed > 0:
            summary += f"WARNING: {pages_regressed} pages regressed. "
        if pages_improved > 0 and pages_improved != pages_verified:
            summary += f"{pages_improved} pages improved but not yet passing. "

        # Recommendation
        if all_verified:
            recommendation = "All fixes verified successfully. Ready to commit."
        elif pages_regressed > 0:
            recommendation = "Regressions detected. Review and rollback fixes for affected pages."
        elif pages_improved > 0:
            recommendation = "Some improvement seen. Consider additional fixes or lower threshold."
        else:
            recommendation = "No improvement detected. Fixes may not address the identified issues."

        # Final verification decision
        final_step_id = self._track_step(
            step_id='final_verification',
            module_id='ai.verify_final',
            category=StepCategory.VERIFY,
            name='Final Verification Decision',
            inputs={
                'total_pages': total_pages,
                'verified': pages_verified,
                'regressed': pages_regressed,
            },
            outputs={
                'verdict': 'pass' if all_verified else 'fail',
                'recommendation': recommendation,
            },
        )

        if final_step_id:
            self._track_decision(
                step_id=final_step_id,
                decision='pass' if all_verified else 'fail',
                reason=summary,
                confidence=0.95 if all_verified or pages_regressed > 0 else 0.75,
                evidence=all_artifact_ids[:5],  # Link to recent artifacts
            )

        # Finalize lineage
        lineage_data = self._finalize_lineage(all_verified)

        return {
            'ok': all_verified,
            'verified': all_verified,
            'pages': verified_pages,
            'improvements': improvements,
            'regression': regressions,
            'summary': summary,
            'recommendation': recommendation,
            'stats': {
                'total_pages': total_pages,
                'pages_verified': pages_verified,
                'pages_improved': pages_improved,
                'pages_regressed': pages_regressed,
                'avg_improvement': avg_improvement,
            },
            **lineage_data,
        }
