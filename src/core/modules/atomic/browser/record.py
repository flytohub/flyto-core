"""
Browser Record Module

Record user actions as workflow.
"""
from typing import Any, Dict, List, Optional
import asyncio
import json
import yaml
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


@register_module(
    module_id='core.browser.record',
    version='1.0.0',
    category='browser',
    tags=['browser', 'record', 'automation', 'workflow'],
    label='Record Actions',
    label_key='modules.browser.record.label',
    description='Record user actions as workflow',
    description_key='modules.browser.record.description',
    icon='Video',
    color='#DC3545',

    # Connection types
    input_types=['page'],
    output_types=['json', 'string'],

    params_schema=compose(
        field(
            'action',
            type='string',
            label='Action',
            label_key='modules.browser.record.params.action.label',
            description='Recording action (start, stop, get)',
            required=True,
            enum=['start', 'stop', 'get'],
        ),
        field(
            'output_format',
            type='string',
            label='Output Format',
            label_key='modules.browser.record.params.output_format.label',
            description='Format for recorded workflow (yaml or json)',
            default='yaml',
            enum=['yaml', 'json'],
        ),
        presets.OUTPUT_PATH(key='output_path', required=False),
    ),
    output_schema={
        'status': {'type': 'string'},
        'recording': {'type': 'array'},
        'workflow': {'type': 'string'}
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
    license='MIT'
)
class BrowserRecordModule(BaseModule):
    """Record Actions Module"""

    module_name = "Record Actions"
    module_description = "Record user actions as workflow"
    required_permission = "browser.interact"

    # Class-level storage for recordings
    _recordings: Dict[str, List[Dict[str, Any]]] = {}
    _handlers: Dict[str, Dict[str, Any]] = {}

    def validate_params(self):
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

            return {
                "status": "success",
                "message": "Recording started",
                "recording": []
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
            if self.output_path:
                from pathlib import Path
                output_path = Path(self.output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w') as f:
                    f.write(workflow)

            return {
                "status": "success",
                "message": "Recording stopped",
                "recording": recording,
                "workflow": workflow
            }

        elif self.action == 'get':
            recording = BrowserRecordModule._recordings.get(page_id, [])
            workflow = self._generate_workflow(recording)

            return {
                "status": "success",
                "recording": recording,
                "workflow": workflow
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
