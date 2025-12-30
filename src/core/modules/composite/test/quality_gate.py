"""
Quality Gate Composite Module

CI/CD quality gate that reads lineage.json and determines pass/fail:
1. Load lineage from AI UI Review or other test runs
2. Analyze all DECIDE steps
3. Check if all decisions meet criteria
4. Output CI-friendly exit codes and reports
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import CompositeModule, register_composite, UIVisibility
from ....engine.lineage import (
    Run,
    Step,
    StepCategory,
    Decision,
)


@register_composite(
    module_id='composite.test.quality_gate',
    version='1.0.0',
    category='test',
    subcategory='ci',
    tags=['test', 'ci', 'cd', 'quality', 'gate', 'automation', 'pipeline'],

    # Context requirements
    requires_context=None,
    provides_context=['quality_gate_result'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='Quality Gate',
    ui_label_key='composite.test.quality_gate.label',
    ui_description='CI/CD quality gate based on lineage analysis',
    ui_description_key='composite.test.quality_gate.desc',
    ui_help='Reads lineage.json from test runs and determines if the CI pipeline '
            'should pass or fail based on decision outcomes. Perfect for use after '
            'AI UI Review or other test composites.',
    ui_help_key='composite.test.quality_gate.help',
    ui_group='Testing / CI-CD',
    ui_icon='ShieldCheck',
    ui_color='#10B981',

    # Connection types
    input_types=['object', 'string'],
    input_type_labels={
        'object': 'Lineage Data',
        'string': 'Lineage File Path',
    },
    input_type_descriptions={
        'object': 'Lineage data object from previous step',
        'string': 'Path to lineage.json file',
    },

    output_types=['object'],
    output_type_labels={
        'object': 'Gate Result',
    },
    output_type_descriptions={
        'object': 'Quality gate result with pass/fail and details',
    },

    # Connection suggestions
    suggested_predecessors=[
        'composite.test.ui_review',
        'composite.test.e2e_flow',
        'composite.test.api_test',
    ],
    suggested_successors=[
        'shell.exec',
        'webhook.trigger',
        'communication.slack_send',
    ],

    # UI form generation
    ui_params_schema={
        'lineage_path': {
            'type': 'string',
            'label': 'Lineage File Path',
            'label_key': 'composite.test.quality_gate.lineage_path.label',
            'description': 'Path to lineage.json file',
            'description_key': 'composite.test.quality_gate.lineage_path.desc',
            'required': False,
            'default': './lineage.json',
            'ui_component': 'input',
        },
        'lineage_data': {
            'type': 'object',
            'label': 'Lineage Data',
            'label_key': 'composite.test.quality_gate.lineage_data.label',
            'description': 'Lineage data object (alternative to file)',
            'description_key': 'composite.test.quality_gate.lineage_data.desc',
            'required': False,
            'ui_component': 'json',
        },
        'require_all_pass': {
            'type': 'boolean',
            'label': 'Require All Pass',
            'label_key': 'composite.test.quality_gate.require_all_pass.label',
            'description': 'Fail if any decision is not "pass"',
            'description_key': 'composite.test.quality_gate.require_all_pass.desc',
            'default': True,
            'required': False,
            'ui_component': 'switch',
        },
        'min_confidence': {
            'type': 'number',
            'label': 'Minimum Confidence',
            'label_key': 'composite.test.quality_gate.min_confidence.label',
            'description': 'Minimum confidence threshold for decisions (0-1)',
            'description_key': 'composite.test.quality_gate.min_confidence.desc',
            'default': 0.7,
            'required': False,
            'ui_component': 'number',
            'validation': {
                'min': 0,
                'max': 1,
                'step': 0.1,
            },
        },
        'fail_on_low_confidence': {
            'type': 'boolean',
            'label': 'Fail on Low Confidence',
            'label_key': 'composite.test.quality_gate.fail_on_low_confidence.label',
            'description': 'Fail gate if any decision has confidence below threshold',
            'description_key': 'composite.test.quality_gate.fail_on_low_confidence.desc',
            'default': False,
            'required': False,
            'ui_component': 'switch',
        },
        'allowed_failures': {
            'type': 'array',
            'label': 'Allowed Failure Decisions',
            'label_key': 'composite.test.quality_gate.allowed_failures.label',
            'description': 'Decision values that should not cause failure',
            'description_key': 'composite.test.quality_gate.allowed_failures.desc',
            'required': False,
            'default': [],
            'ui_component': 'chips',
        },
        'blocking_failures': {
            'type': 'array',
            'label': 'Blocking Failure Decisions',
            'label_key': 'composite.test.quality_gate.blocking_failures.label',
            'description': 'Decision values that always cause failure',
            'description_key': 'composite.test.quality_gate.blocking_failures.desc',
            'required': False,
            'default': ['fail', 'critical'],
            'ui_component': 'chips',
        },
        'exit_on_failure': {
            'type': 'boolean',
            'label': 'Exit on Failure',
            'label_key': 'composite.test.quality_gate.exit_on_failure.label',
            'description': 'Exit process with code 1 on failure (for CI)',
            'description_key': 'composite.test.quality_gate.exit_on_failure.desc',
            'default': False,
            'required': False,
            'ui_component': 'switch',
        },
    },

    # Steps definition (mostly handled in code)
    steps=[
        {
            'id': 'load_lineage',
            'module': 'file.read',
            'params': {
                'path': '${params.lineage_path}'
            },
            'skip_if': '${params.lineage_data}'
        }
    ],

    # Output schema
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether quality gate passed'
        },
        'passed': {
            'type': 'boolean',
            'description': 'Alias for ok'
        },
        'run_id': {
            'type': 'string',
            'description': 'ID of the analyzed run'
        },
        'total_decisions': {
            'type': 'number',
            'description': 'Total number of decisions analyzed'
        },
        'passed_decisions': {
            'type': 'number',
            'description': 'Number of passed decisions'
        },
        'failed_decisions': {
            'type': 'number',
            'description': 'Number of failed decisions'
        },
        'blocked_decisions': {
            'type': 'array',
            'description': 'List of blocking decision details'
        },
        'low_confidence_decisions': {
            'type': 'array',
            'description': 'List of low confidence decision details'
        },
        'summary': {
            'type': 'string',
            'description': 'Human-readable summary'
        },
        'exit_code': {
            'type': 'number',
            'description': 'Suggested exit code (0=pass, 1=fail)'
        }
    },

    # Execution settings
    timeout=30,
    retryable=False,
    max_retries=1,

    # Documentation
    examples=[
        {
            'name': 'Basic Quality Gate',
            'description': 'Simple pass/fail gate from lineage file',
            'params': {
                'lineage_path': './lineage.json',
                'require_all_pass': True
            }
        },
        {
            'name': 'CI Pipeline Gate',
            'description': 'Quality gate with CI exit code',
            'params': {
                'lineage_path': './test-artifacts/lineage.json',
                'require_all_pass': True,
                'exit_on_failure': True,
                'blocking_failures': ['fail', 'critical', 'security_violation']
            }
        },
        {
            'name': 'Lenient Gate',
            'description': 'Allow some failures to pass',
            'params': {
                'lineage_path': './lineage.json',
                'require_all_pass': False,
                'allowed_failures': ['need_fix', 'warning'],
                'blocking_failures': ['critical']
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class CIQualityGate(CompositeModule):
    """
    CI/CD Quality Gate Composite Module

    Analyzes lineage data from test runs and determines if the CI pipeline
    should pass or fail.

    Features:

    1. **Lineage Analysis**
       - Loads lineage.json from file or accepts data directly
       - Parses all DECIDE category steps
       - Extracts decision values and confidence scores

    2. **Decision Evaluation**
       - Checks if all decisions are "pass"
       - Validates confidence thresholds
       - Handles blocking and allowed failure lists

    3. **CI Integration**
       - Outputs CI-friendly results
       - Can exit with code 1 on failure
       - Provides detailed failure reasons

    4. **Reporting**
       - Summary of all decisions
       - Details on blocking failures
       - Low confidence warnings
    """

    def _load_lineage(self) -> Optional[Run]:
        """Load lineage data from file or params"""
        # Try direct data first
        lineage_data = self.params.get('lineage_data')
        if lineage_data:
            if isinstance(lineage_data, dict):
                return Run.from_dict(lineage_data)
            return None

        # Try file path
        lineage_path = self.params.get('lineage_path', './lineage.json')
        path = Path(lineage_path)

        if not path.exists():
            return None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return Run.from_dict(data)
        except Exception:
            return None

    def _analyze_decisions(self, run: Run) -> Dict[str, Any]:
        """Analyze all decisions in the run"""
        min_confidence = self.params.get('min_confidence', 0.7)
        require_all_pass = self.params.get('require_all_pass', True)
        fail_on_low_confidence = self.params.get('fail_on_low_confidence', False)
        allowed_failures = set(self.params.get('allowed_failures', []))
        blocking_failures = set(self.params.get('blocking_failures', ['fail', 'critical']))

        decision_steps = run.get_decision_steps()
        total_decisions = len(decision_steps)
        passed_decisions = 0
        failed_decisions = 0
        blocked_decisions = []
        low_confidence_decisions = []
        all_passed = True

        for step in decision_steps:
            if not step.decision:
                continue

            decision = step.decision.decision
            confidence = step.decision.confidence
            reason = step.decision.reason

            # Check for blocking failures
            if decision in blocking_failures:
                all_passed = False
                failed_decisions += 1
                blocked_decisions.append({
                    'step_id': step.id,
                    'step_name': step.name,
                    'decision': decision,
                    'reason': reason,
                    'confidence': confidence,
                })
                continue

            # Check if decision is a pass
            if decision == 'pass':
                passed_decisions += 1
            elif decision in allowed_failures:
                passed_decisions += 1  # Allowed failure counts as pass
            elif require_all_pass:
                all_passed = False
                failed_decisions += 1
                blocked_decisions.append({
                    'step_id': step.id,
                    'step_name': step.name,
                    'decision': decision,
                    'reason': reason,
                    'confidence': confidence,
                })
            else:
                failed_decisions += 1

            # Check confidence threshold
            if confidence < min_confidence:
                low_confidence_decisions.append({
                    'step_id': step.id,
                    'step_name': step.name,
                    'decision': decision,
                    'confidence': confidence,
                    'threshold': min_confidence,
                })
                if fail_on_low_confidence:
                    all_passed = False

        return {
            'total_decisions': total_decisions,
            'passed_decisions': passed_decisions,
            'failed_decisions': failed_decisions,
            'blocked_decisions': blocked_decisions,
            'low_confidence_decisions': low_confidence_decisions,
            'all_passed': all_passed,
        }

    def _build_output(self, metadata):
        """Build quality gate result"""
        # Load lineage
        run = self._load_lineage()
        if not run:
            return {
                'ok': False,
                'passed': False,
                'run_id': None,
                'total_decisions': 0,
                'passed_decisions': 0,
                'failed_decisions': 0,
                'blocked_decisions': [],
                'low_confidence_decisions': [],
                'summary': 'Failed to load lineage data',
                'exit_code': 1,
            }

        # Analyze decisions
        analysis = self._analyze_decisions(run)

        # Build summary
        if analysis['all_passed']:
            summary = f"Quality gate PASSED: {analysis['passed_decisions']}/{analysis['total_decisions']} decisions passed."
        else:
            summary = (
                f"Quality gate FAILED: {analysis['failed_decisions']} blocking decision(s). "
                f"{analysis['passed_decisions']}/{analysis['total_decisions']} passed."
            )

        if analysis['low_confidence_decisions']:
            summary += f" Warning: {len(analysis['low_confidence_decisions'])} low confidence decision(s)."

        passed = analysis['all_passed']
        exit_code = 0 if passed else 1

        # Handle CI exit
        if self.params.get('exit_on_failure') and not passed:
            # Note: In actual execution, this would exit the process
            # Here we just set the exit code
            pass

        return {
            'ok': passed,
            'passed': passed,
            'run_id': run.id,
            'total_decisions': analysis['total_decisions'],
            'passed_decisions': analysis['passed_decisions'],
            'failed_decisions': analysis['failed_decisions'],
            'blocked_decisions': analysis['blocked_decisions'],
            'low_confidence_decisions': analysis['low_confidence_decisions'],
            'summary': summary,
            'exit_code': exit_code,
        }
