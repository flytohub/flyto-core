# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Assert Timing Module

Given a batch of HTTP probe results (source), compare a probe's duration_ms to
a baseline's duration_ms and produce a verdict. Designed for time-based blind
SQL injection, NoSQL injection, and similar delay-based oracle detection.
"""

from typing import Any

from ...base import BaseModule
from ...registry import register_module


def _get_duration(entry: Any) -> int:
    if isinstance(entry, dict):
        try:
            return int(entry.get("duration_ms") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _get_error(entry: Any) -> Any:
    if isinstance(entry, dict):
        return entry.get("error")
    return None


@register_module(
    module_id='test.assert_timing',
    version='1.0.0',
    category='testing',
    tags=['testing', 'assertion', 'pentest', 'timing', 'validation'],
    label='Assert Timing',
    label_key='modules.test.assert_timing.label',
    description='Compare probe duration to a baseline to detect time-based oracles',
    description_key='modules.test.assert_timing.description',
    icon='Clock',
    color='#F59E0B',

    input_types=['array', 'object'],
    output_types=['object'],
    can_receive_from=['*'],
    can_connect_to=['testing.*', 'test.*', 'flow.*', 'output.*'],

    params_schema={
        'source': {
            'type': ['array', 'object'],
            'required': True,
            'label': 'Source',
            'description': 'Batch result data (array of {duration_ms,...} from http.batch)',
        },
        'baseline_index': {
            'type': 'number',
            'required': False,
            'default': 0,
            'label': 'Baseline Index',
        },
        'probe_index': {
            'type': 'number',
            'required': True,
            'label': 'Probe Index',
        },
        'threshold_ms': {
            'type': 'number',
            'required': False,
            'default': 3000,
            'label': 'Threshold (ms)',
            'description': 'Minimum probe-vs-baseline delta to flag as exploitable',
        },
        'on_slow': {
            'type': 'string',
            'required': False,
            'default': 'exploitable',
            'label': 'On Slow Verdict',
        },
        'on_normal': {
            'type': 'string',
            'required': False,
            'default': 'inconclusive',
            'label': 'On Normal Verdict',
        },
        'on_error': {
            'type': 'string',
            'required': False,
            'default': 'unreachable',
            'label': 'On Error Verdict',
        },
    },
    output_schema={
        'passed': {'type': 'boolean', 'description': 'True when verdict != on_slow'},
        'verdict': {'type': 'string', 'description': 'on_slow/on_normal/on_error value'},
        'baseline_ms': {'type': 'number', 'description': 'Baseline duration in ms'},
        'probe_ms': {'type': 'number', 'description': 'Probe duration in ms'},
        'delta_ms': {'type': 'number', 'description': 'probe_ms - baseline_ms'},
        'threshold_ms': {'type': 'number', 'description': 'Threshold used'},
    },
    timeout_ms=5000,
)
class AssertTimingModule(BaseModule):
    """Detect time-based oracles by comparing probe duration to a baseline."""

    module_name = "Assert Timing"
    module_description = (
        "Compare probe duration to a baseline; flag delta above threshold."
    )

    def validate_params(self) -> None:
        if 'source' not in self.params:
            raise ValueError("Parameter 'source' is required")
        if 'probe_index' not in self.params:
            raise ValueError("Parameter 'probe_index' is required")

    async def execute(self) -> Any:
        source = self.params.get('source')
        if isinstance(source, dict) and 'data' in source:
            source = source['data']
        if not isinstance(source, list):
            raise ValueError(
                f"source must be a list of probe results or {{data:[...]}} wrapper; "
                f"got {type(source).__name__}: {str(source)[:200]}"
            )

        baseline_index = int(self.params.get('baseline_index', 0))
        probe_index = int(self.params.get('probe_index'))
        threshold_ms = int(self.params.get('threshold_ms', 3000))
        on_slow = self.params.get('on_slow', 'exploitable')
        on_normal = self.params.get('on_normal', 'inconclusive')
        on_error = self.params.get('on_error', 'unreachable')

        if not source:
            return {
                'passed': False,
                'verdict': on_error,
                'baseline_ms': 0,
                'probe_ms': 0,
                'delta_ms': 0,
                'threshold_ms': threshold_ms,
                'message': 'source is empty',
            }

        if not (0 <= baseline_index < len(source)):
            raise ValueError(f"baseline_index {baseline_index} out of range")
        if not (0 <= probe_index < len(source)):
            raise ValueError(f"probe_index {probe_index} out of range")

        baseline = source[baseline_index]
        probe = source[probe_index]

        # Either request errored → we can't make a timing judgment
        if _get_error(baseline) or _get_error(probe):
            return {
                'passed': False,
                'verdict': on_error,
                'baseline_ms': _get_duration(baseline),
                'probe_ms': _get_duration(probe),
                'delta_ms': 0,
                'threshold_ms': threshold_ms,
                'message': 'Baseline or probe request errored',
            }

        baseline_ms = _get_duration(baseline)
        probe_ms = _get_duration(probe)
        delta_ms = probe_ms - baseline_ms

        verdict = on_slow if delta_ms >= threshold_ms else on_normal

        return {
            'passed': verdict != on_slow,
            'verdict': verdict,
            'baseline_ms': baseline_ms,
            'probe_ms': probe_ms,
            'delta_ms': delta_ms,
            'threshold_ms': threshold_ms,
        }
