# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Assert Status Module

Given a batch of HTTP probe results (source), compare probes against a baseline
and produce a verdict string. Used by pentest blueprints to decide whether a
series of auth-bypass attempts is `exploitable`, `sanitized`, or `unreachable`.
"""

from typing import Any, Dict, List

from ...base import BaseModule
from ...registry import register_module


def _get_status(entry: Any) -> Any:
    if isinstance(entry, dict):
        return entry.get("status")
    return None


def _get_error(entry: Any) -> Any:
    if isinstance(entry, dict):
        return entry.get("error")
    return None


@register_module(
    module_id='test.assert_status',
    version='1.0.0',
    category='testing',
    tags=['testing', 'assertion', 'pentest', 'auth', 'validation'],
    label='Assert Status',
    label_key='modules.test.assert_status.label',
    description='Compare probe statuses to a baseline to derive exploitable/sanitized verdict',
    description_key='modules.test.assert_status.description',
    icon='ShieldCheck',
    color='#10B981',

    input_types=['array', 'object'],
    output_types=['object'],
    can_receive_from=['*'],
    can_connect_to=['testing.*', 'test.*', 'flow.*', 'output.*'],

    params_schema={
        'source': {
            'type': ['array', 'object'],
            'required': True,
            'label': 'Source',
            'description': 'Batch result data (array of {status,...} from http.batch)',
        },
        'baseline_index': {
            'type': 'number',
            'required': False,
            'default': 0,
            'label': 'Baseline Index',
        },
        'probe_indices': {
            'type': 'array',
            'required': False,
            'label': 'Probe Indices',
            'description': 'Indices to compare against the baseline',
        },
        'expected_blocked': {
            'type': 'array',
            'required': False,
            'default': [401, 403],
            'label': 'Expected Blocked Statuses',
        },
        'on_bypass': {
            'type': 'string',
            'required': False,
            'default': 'exploitable',
            'label': 'On Bypass Verdict',
        },
        'on_blocked': {
            'type': 'string',
            'required': False,
            'default': 'sanitized',
            'label': 'On Blocked Verdict',
        },
        'on_error': {
            'type': 'string',
            'required': False,
            'default': 'unreachable',
            'label': 'On Error Verdict',
        },
    },
    output_schema={
        'passed': {'type': 'boolean', 'description': 'True when verdict != on_bypass'},
        'verdict': {'type': 'string', 'description': 'One of on_bypass/on_blocked/on_error values'},
        'baseline': {'type': 'object', 'description': 'Baseline probe summary'},
        'probes': {'type': 'array', 'description': 'Per-probe decision detail'},
    },
    timeout_ms=5000,
)
class AssertStatusModule(BaseModule):
    """Translate batched status codes into a security verdict."""

    module_name = "Assert Status"
    module_description = (
        "Compare probe statuses against a baseline to derive a pentest verdict."
    )

    def validate_params(self) -> None:
        if 'source' not in self.params:
            raise ValueError("Parameter 'source' is required")

    async def execute(self) -> Any:
        source = self.params.get('source')
        # http.batch's result shape is {'data': [...]}. Accept the wrapped
        # form as well as a raw list for convenience.
        if isinstance(source, dict) and 'data' in source:
            source = source['data']
        if not isinstance(source, list):
            raise ValueError("source must be a list of probe results or {data:[...]} wrapper")

        baseline_index = int(self.params.get('baseline_index', 0))
        probe_indices = self.params.get('probe_indices')
        expected_blocked = list(self.params.get('expected_blocked', [401, 403]))
        on_bypass = self.params.get('on_bypass', 'exploitable')
        on_blocked = self.params.get('on_blocked', 'sanitized')
        on_error = self.params.get('on_error', 'unreachable')

        if not source:
            return {
                'passed': False,
                'verdict': on_error,
                'baseline': None,
                'probes': [],
                'message': 'source is empty',
            }

        if baseline_index < 0 or baseline_index >= len(source):
            raise ValueError(f"baseline_index {baseline_index} out of range [0,{len(source)})")

        baseline = source[baseline_index]
        if probe_indices is None:
            probe_indices = [i for i in range(len(source)) if i != baseline_index]

        baseline_status = _get_status(baseline)
        baseline_err = _get_error(baseline)

        # Baseline itself failed → target is unreachable
        if baseline_err or baseline_status is None:
            return {
                'passed': False,
                'verdict': on_error,
                'baseline': {'index': baseline_index, 'status': baseline_status,
                             'error': baseline_err},
                'probes': [],
                'message': 'Baseline request failed — target unreachable',
            }

        probes_detail: List[Dict[str, Any]] = []
        any_bypass = False
        any_probe_evaluated = False

        # Two oracle modes based on baseline status:
        #   - baseline is 2xx ("authorized user"): bypass = probe also 2xx
        #     and not explicitly blocked (mirroring baseline).
        #   - baseline is blocked (401/403/4xx): bypass = probe flipped to
        #     2xx ("forged credential worked"). This is the NoSQLi / cred
        #     stuffing oracle where baseline sends bad creds and the probe
        #     sends the exploit.
        baseline_is_success = 200 <= baseline_status < 300
        baseline_is_blocked = baseline_status in expected_blocked

        for idx in probe_indices:
            if idx < 0 or idx >= len(source):
                probes_detail.append({
                    'index': idx, 'status': None, 'decision': 'skipped',
                    'reason': 'index out of range',
                })
                continue
            entry = source[idx]
            status = _get_status(entry)
            err = _get_error(entry)
            if err or status is None:
                probes_detail.append({
                    'index': idx, 'status': status, 'error': err,
                    'decision': 'unreachable',
                })
                continue

            any_probe_evaluated = True
            probe_is_blocked = status in expected_blocked
            probe_is_success = 200 <= status < 300

            if baseline_is_success:
                # Mode A — baseline authorized. Probe mirroring baseline = bypass.
                if probe_is_blocked:
                    decision = 'blocked'
                elif status == baseline_status:
                    decision = 'bypass'
                    any_bypass = True
                else:
                    decision = 'blocked'
            elif baseline_is_blocked or not baseline_is_success:
                # Mode B — baseline rejected. Probe flipping to 2xx = bypass.
                if probe_is_success:
                    decision = 'bypass'
                    any_bypass = True
                elif probe_is_blocked:
                    decision = 'blocked'
                else:
                    decision = 'blocked'
            else:
                decision = 'blocked'

            probes_detail.append({
                'index': idx, 'status': status, 'decision': decision,
            })

        if not any_probe_evaluated:
            verdict = on_error
        elif any_bypass:
            verdict = on_bypass
        else:
            verdict = on_blocked

        return {
            'passed': verdict != on_bypass,
            'verdict': verdict,
            'baseline': {'index': baseline_index, 'status': baseline_status},
            'probes': probes_detail,
            'expected_blocked': expected_blocked,
        }
