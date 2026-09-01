# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Record Module

Record user actions as workflow.

`"message": "Recording started"` IS NOT A RECORDING THAT STARTED

Each of the three actions returned a string it had just written and a list it
already held. ``start`` returned ``"recording": []`` -- the empty list assigned
one line above. ``stop`` returned the generated YAML and, when a path was given,
wrote a file it then never looked at. None of the three ever asked the browser
or the filesystem anything.

The injected script leaves a flag behind, and the flag is readable:

    page.evaluate('() => { ... window._flytoRecording = true; }')
    page.evaluate('() => window._flytoRecording === true')   ->  True

That second read is a fact about the page's JS world. It is ``undefined`` on a
page the injection did not reach, on a page that navigated since, and in a frame
the module attached to the wrong target -- so it is not the same value with and
without the effect, which is the whole test.

    start   the page reports the flag set            OBSERVED
            it does not, or could not be asked       INDETERMINATE / ACCEPTED
    stop    a path was given and the file is there   OBSERVED (bytes_on_disk)
            a path was given and it is not           INDETERMINATE
            no path, and events were recorded        OBSERVED (event count)
            no path, and none were                   ACCEPTED
    get     events were recorded                     OBSERVED
            none were                                ACCEPTED

The empty-recording case is ACCEPTED for `database.query`'s reason and it is the
one worth stating plainly, because it is this module's most likely outcome: an
empty list reads identically whether the user did nothing, the injected
listeners never ran, the page navigated and wiped them, or the console handler
was attached to a different page object than the one being driven. Reporting
``status: success`` with an empty workflow was the module claiming all four at
once.

A recorded event, by contrast, is an observation: every entry arrives through a
``console`` message the browser delivered from the page.
"""
import os
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import json
import yaml

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field
from ....utils import validate_path_with_env_config


_READ_RECORDING_FLAG = '() => window._flytoRecording === true'


async def _read_recording_flag(page) -> Tuple[Optional[bool], Optional[str]]:
    """``(flag, None)`` when the page could be asked, ``(None, why)`` when not."""
    try:
        return bool(await page.evaluate(_READ_RECORDING_FLAG)), None
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"


def _start_outcome(*, flag: Optional[bool], read_error: Optional[str]) -> Dict[str, Any]:
    """The rung a `start` earned, from the flag the injected script leaves behind."""
    if flag is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'recording_flag_not_observed',
                'measured_by': None,
                'reason': read_error or 'the page could not be evaluated',
                'detail': (
                    'The injection returned without raising and the page could '
                    'not be asked whether the flag is set, so nothing followed '
                    'the script into the document.'
                ),
            }],
        )
    if flag:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            effects=[{
                'kind': 'recording_flag_observed',
                'measured_by': 'page.evaluate of window._flytoRecording, read after the injection',
                'detail': (
                    'The page reports the flag the injected script sets. It is '
                    'undefined on a document the injection did not reach and on '
                    'one that navigated since, so it is evidence the listeners '
                    'are installed in the document being driven. That the '
                    'listeners will FIRE is not claimed: nothing has happened '
                    'in the page yet.'
                ),
            }],
        )
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            'kind': 'recording_flag_unset',
            'predicate': 'window._flytoRecording === true',
            'measured_by': 'page.evaluate of window._flytoRecording, read after the injection',
            'detail': (
                'page.evaluate returned without raising and the flag is not '
                'set. A navigation between the injection and this read does '
                'this, and so does an evaluation that landed in a different '
                'document, so this is indeterminate rather than failed.'
            ),
        }],
    )


def _recorded_events_effect(count: int) -> Dict[str, Any]:
    """The count of events, and what it is a count OF."""
    return {
        'kind': 'events_recorded' if count else 'no_events_recorded',
        'count': count,
        'measured_by': (
            'len() over entries appended from console messages the browser '
            'delivered from the page'
        ) if count else None,
        'detail': (
            'Each entry arrived as a console message from the recorded page.'
        ) if count else (
            'No events. That reads the same whether the user did nothing, the '
            'injected listeners never ran, the page navigated and wiped them, '
            'or the console handler was attached to a different page object -- '
            'so it is not an observation of anything.'
        ),
    }


def _stop_or_get_outcome(
    *,
    action: str,
    event_count: int,
    path: Optional[str] = None,
    bytes_on_disk: Optional[int] = None,
    stat_error: Optional[str] = None,
) -> Dict[str, Any]:
    """The rung a `stop` or `get` earned.

    When a path was asked for, the FILE is the effect and the read-back decides;
    the event count rides along as context. With no path, the recorded events
    are all there is.
    """
    events = _recorded_events_effect(event_count)

    if path is not None:
        if bytes_on_disk is None:
            return envelope(
                Outcome.INDETERMINATE,
                claim_by=ClaimBy.INFERRED,
                effects=[events, {
                    'kind': 'workflow_file_missing',
                    'path': path,
                    'predicate': 'a workflow file exists at the output path',
                    'measured_by': 'os.stat() on the output path after the write',
                    'reason': stat_error or 'nothing is at the output path',
                    'detail': (
                        'The write returned without raising and there is no '
                        'file to measure. Indeterminate rather than failed: no '
                        'postcondition was declared about the path.'
                    ),
                }],
            )
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[events, {
                'kind': 'workflow_file_written',
                'path': path,
                'bytes_on_disk': bytes_on_disk,
                'measured_by': 'os.stat().st_size on the output path after the write',
                'detail': (
                    'Size the filesystem reports. A workflow with no steps in '
                    'it is still a real file, so this says the file is there '
                    'and not that anything was recorded -- the event count '
                    'beside it is the part that says that.'
                ),
            }],
        )

    if event_count:
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=[events])
    return envelope(Outcome.ACCEPTED, claim_by=ClaimBy.NONE, effects=[events])


def _stat_size(path: str) -> Tuple[Optional[int], Optional[str]]:
    """``(st_size, None)`` when the file is there, ``(None, why)`` when it is not."""
    try:
        return os.stat(path).st_size, None
    except OSError as error:
        return None, f"{type(error).__name__}: {error.strerror or error}"


@register_module(
    module_id='browser.record',
    version='1.0.0',
    category='browser',
    tags=['browser', 'record', 'automation', 'workflow', 'ssrf_protected', 'path_restricted', 'filesystem_write'],
    label='Record Actions',
    label_key='modules.browser.record.label',
    description='Record user actions as workflow',
    description_key='modules.browser.record.description',
    icon='Video',
    color='#DC3545',

    # Connection types
    input_types=['page'],
    output_types=['json', 'string'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        field(
            'action',
            type='string',
            label='Action',
            label_key='modules.browser.record.params.action.label',
            description='Recording action to perform',
            required=True,
            options=[
                {'value': 'start', 'label': 'Start Recording'},
                {'value': 'stop', 'label': 'Stop Recording'},
                {'value': 'get', 'label': 'Get Current Recording'},
            ],
        ),
        field(
            'output_format',
            type='string',
            label='Output Format',
            label_key='modules.browser.record.params.output_format.label',
            description='Format for recorded workflow',
            default='yaml',
            options=[
                {'value': 'yaml', 'label': 'YAML (human-readable)'},
                {'value': 'json', 'label': 'JSON (machine-friendly)'},
            ],
        ),
        presets.OUTPUT_PATH(key='output_path', required=False),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.record.output.status.description'},
        'recording': {'type': 'array', 'description': 'Recording data or path',
                'description_key': 'modules.browser.record.output.recording.description'},
        'workflow': {'type': 'string', 'description': 'The workflow',
                'description_key': 'modules.browser.record.output.workflow.description'},
        'event_count': {'type': 'number', 'description': 'Actions recorded from the page'},
        'recording_flag': {'type': 'boolean', 'description': 'Whether the page reports the recording flag set (start only)'},
        'bytes_on_disk': {'type': 'number', 'description': 'Size of the written workflow file, when a path was given'},
        'outcome': {'type': 'object', 'description': (
            'How far the effect was followed. Decided per action: start reads '
            'the injected flag back out of the page; stop measures the written '
            'file when a path was given; an empty recording is only "accepted".'
        )}
    },
    examples=[
        {
            'name': 'Start recording',
            'params': {'action': 'start'}
        },
        {
            'name': 'Stop and get workflow as YAML',
            'params': {'action': 'stop', 'output_format': 'yaml'}
        },
        {
            'name': 'Get current recording',
            'params': {'action': 'get'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserRecordModule(BaseModule):
    """Record Actions Module"""

    module_name = "Record Actions"
    module_description = "Record user actions as workflow"
    required_permission = "browser.automation"

    # Class-level storage for recordings
    _recordings: Dict[str, List[Dict[str, Any]]] = {}
    _handlers: Dict[str, Dict[str, Any]] = {}

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['start', 'stop', 'get']:
            raise ValueError(f"Invalid action: {self.action}")

        self.output_format = self.params.get('output_format', 'yaml')
        self.output_path = self.params.get('output_path')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        page_id = str(id(page))

        if self.action == 'start':
            # Initialize recording for this page
            BrowserRecordModule._recordings[page_id] = []

            async def on_click(element):
                selector = await self._get_selector(element)
                BrowserRecordModule._recordings[page_id].append({
                    'module': 'core.browser.click',
                    'params': {'selector': selector}
                })

            async def on_input(element, value):
                selector = await self._get_selector(element)
                BrowserRecordModule._recordings[page_id].append({
                    'module': 'core.browser.type',
                    'params': {'selector': selector, 'text': value}
                })

            # Use Playwright's page events for basic tracking
            def handle_console(msg):
                # Record navigation events from console
                if msg.text.startswith('FLYTO_RECORD:'):
                    data = json.loads(msg.text.replace('FLYTO_RECORD:', ''))
                    BrowserRecordModule._recordings[page_id].append(data)

            page.on('console', handle_console)

            # Inject recording script
            await page.evaluate('''
                () => {
                    // Track clicks
                    document.addEventListener('click', (e) => {
                        const target = e.target;
                        let selector = '';
                        if (target.id) {
                            selector = '#' + target.id;
                        } else if (target.className) {
                            selector = '.' + target.className.split(' ').join('.');
                        } else {
                            selector = target.tagName.toLowerCase();
                        }
                        console.log('FLYTO_RECORD:' + JSON.stringify({
                            module: 'core.browser.click',
                            params: { selector: selector }
                        }));
                    }, true);

                    // Track input
                    document.addEventListener('input', (e) => {
                        const target = e.target;
                        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                            let selector = '';
                            if (target.id) {
                                selector = '#' + target.id;
                            } else if (target.name) {
                                selector = `[name="${target.name}"]`;
                            } else if (target.className) {
                                selector = '.' + target.className.split(' ').join('.');
                            }
                            // Debounced - will capture final value
                            clearTimeout(target._flytoTimeout);
                            target._flytoTimeout = setTimeout(() => {
                                console.log('FLYTO_RECORD:' + JSON.stringify({
                                    module: 'core.browser.type',
                                    params: { selector: selector, text: target.value }
                                }));
                            }, 500);
                        }
                    }, true);

                    window._flytoRecording = true;
                }
            ''')

            BrowserRecordModule._handlers[page_id] = {'console': handle_console}

            # The injected script leaves this flag behind. Reading it back is
            # the only thing here that came from the page rather than from us.
            flag, flag_error = await _read_recording_flag(page)

            return {
                "status": "success",
                "message": "Recording started",
                "recording": [],
                "recording_flag": flag,
                "outcome": _start_outcome(flag=flag, read_error=flag_error),
            }

        elif self.action == 'stop':
            recording = BrowserRecordModule._recordings.get(page_id, [])

            # Remove handlers
            if page_id in BrowserRecordModule._handlers:
                handlers = BrowserRecordModule._handlers[page_id]
                if 'console' in handlers:
                    page.remove_listener('console', handlers['console'])
                del BrowserRecordModule._handlers[page_id]

            # Stop recording script
            await page.evaluate('() => { window._flytoRecording = false; }')

            # Generate workflow
            workflow = self._generate_workflow(recording)

            # Clear recording
            if page_id in BrowserRecordModule._recordings:
                del BrowserRecordModule._recordings[page_id]

            # Save to file if path provided
            written_path: Optional[str] = None
            bytes_on_disk: Optional[int] = None
            stat_error: Optional[str] = None
            if self.output_path:
                from pathlib import Path
                # GHSA-p34x: confine the recording output to FLYTO_SANDBOX_DIR.
                output_path = Path(validate_path_with_env_config(self.output_path))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w') as f:
                    f.write(workflow)
                written_path = str(output_path)
                bytes_on_disk, stat_error = _stat_size(written_path)

            return {
                "status": "success",
                "message": "Recording stopped",
                "recording": recording,
                "workflow": workflow,
                "event_count": len(recording),
                "bytes_on_disk": bytes_on_disk,
                "outcome": _stop_or_get_outcome(
                    action='stop',
                    event_count=len(recording),
                    path=written_path,
                    bytes_on_disk=bytes_on_disk,
                    stat_error=stat_error,
                ),
            }

        elif self.action == 'get':
            recording = BrowserRecordModule._recordings.get(page_id, [])
            workflow = self._generate_workflow(recording)

            return {
                "status": "success",
                "recording": recording,
                "workflow": workflow,
                "event_count": len(recording),
                "outcome": _stop_or_get_outcome(action='get', event_count=len(recording)),
            }

    def _generate_workflow(self, recording: List[Dict[str, Any]]) -> str:
        """Generate workflow from recorded actions"""
        workflow_data = {
            'name': 'Recorded Workflow',
            'description': 'Auto-generated from browser recording',
            'steps': []
        }

        for i, action in enumerate(recording):
            step = {
                'id': f'step_{i+1}',
                'module': action.get('module', 'unknown'),
                'params': action.get('params', {})
            }
            workflow_data['steps'].append(step)

        if self.output_format == 'yaml':
            return yaml.dump(workflow_data, default_flow_style=False, allow_unicode=True)
        else:
            return json.dumps(workflow_data, indent=2)

    async def _get_selector(self, element) -> str:
        """Get unique selector for element"""
        return await element.evaluate('''
            (el) => {
                if (el.id) return '#' + el.id;
                if (el.className) return '.' + el.className.split(' ').join('.');
                return el.tagName.toLowerCase();
            }
        ''')
