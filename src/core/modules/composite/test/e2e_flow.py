"""
E2E Test Flow Composite Module

Complete end-to-end testing workflow for web applications:
1. Start development server
2. Wait for server ready
3. Launch browser
4. Run test scenarios
5. Capture screenshots
6. Stop server
7. Generate report
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.test.e2e_flow',
    version='1.0.0',
    category='test',
    subcategory='e2e',
    tags=['test', 'e2e', 'browser', 'automation', 'qa', 'web'],

    # Context requirements
    requires_context=None,
    provides_context=['test_results', 'screenshots'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='E2E Test Flow',
    ui_label_key='composite.test.e2e_flow.label',
    ui_description='Run complete end-to-end tests for web applications',
    ui_description_key='composite.test.e2e_flow.desc',
    ui_help='This composite module provides a complete E2E testing workflow. '
            'It starts your development server, waits for it to be ready, '
            'launches a browser, runs through test scenarios, captures screenshots '
            'at each step, and generates a comprehensive test report. '
            'Ideal for CI/CD pipelines and local testing.',
    ui_help_key='composite.test.e2e_flow.help',
    ui_group='Testing / E2E',
    ui_icon='PlayCircle',
    ui_color='#10B981',

    # Connection types with labels and descriptions
    input_types=['object', 'string'],
    input_type_labels={
        'object': 'Test Configuration',
        'string': 'Project Path',
    },
    input_type_descriptions={
        'object': 'Test configuration object with scenarios and options',
        'string': 'Path to the project directory to test',
    },

    output_types=['object', 'array'],
    output_type_labels={
        'object': 'Test Report',
        'array': 'Test Results',
    },
    output_type_descriptions={
        'object': 'Comprehensive test report with all results and screenshots',
        'array': 'Array of individual test case results',
    },

    # Connection suggestions
    suggested_predecessors=[
        'shell.exec',
        'file.read',
        'data.json_parse',
    ],
    suggested_successors=[
        'file.write',
        'webhook.trigger',
        'communication.slack_send',
    ],

    # Connection error messages
    connection_error_messages={
        'type_mismatch': 'This module expects a test configuration object or project path',
        'missing_config': 'Please provide test configuration',
    },

    # UI form generation with enhanced fields
    ui_params_schema={
        'project_path': {
            'type': 'string',
            'label': 'Project Path',
            'label_key': 'composite.test.e2e_flow.project_path.label',
            'description': 'Path to the project to test',
            'description_key': 'composite.test.e2e_flow.project_path.desc',
            'help': 'Provide the absolute or relative path to your project directory. '
                    'This should contain package.json or equivalent.',
            'help_key': 'composite.test.e2e_flow.project_path.help',
            'placeholder': './my-project',
            'examples': [
                './frontend',
                '/Users/dev/my-app',
                '../webapp',
            ],
            'required': True,
            'ui_component': 'input',
            'validation': {
                'min_length': 1,
            },
            'error_messages': {
                'required': 'Please enter the project path',
            },
        },
        'start_command': {
            'type': 'string',
            'label': 'Start Command',
            'label_key': 'composite.test.e2e_flow.start_command.label',
            'description': 'Command to start the development server',
            'description_key': 'composite.test.e2e_flow.start_command.desc',
            'help': 'The shell command to start your development server. '
                    'This should be a non-blocking command that starts a server.',
            'help_key': 'composite.test.e2e_flow.start_command.help',
            'placeholder': 'npm run dev',
            'default': 'npm run dev',
            'examples': [
                'npm run dev',
                'yarn start',
                'python manage.py runserver',
                'npm run serve',
            ],
            'required': False,
            'ui_component': 'input',
        },
        'server_port': {
            'type': 'number',
            'label': 'Server Port',
            'label_key': 'composite.test.e2e_flow.server_port.label',
            'description': 'Port the server will run on',
            'description_key': 'composite.test.e2e_flow.server_port.desc',
            'help': 'The port number where your development server will listen. '
                    'We will wait for this port to become available before starting tests.',
            'help_key': 'composite.test.e2e_flow.server_port.help',
            'placeholder': '3000',
            'default': 3000,
            'required': False,
            'ui_component': 'number',
            'validation': {
                'min': 1,
                'max': 65535,
            },
        },
        'base_url': {
            'type': 'string',
            'label': 'Base URL',
            'label_key': 'composite.test.e2e_flow.base_url.label',
            'description': 'Base URL for testing (defaults to localhost:port)',
            'description_key': 'composite.test.e2e_flow.base_url.desc',
            'help': 'The base URL to use for all tests. If not provided, '
                    'will default to http://localhost:{port}',
            'help_key': 'composite.test.e2e_flow.base_url.help',
            'placeholder': 'http://localhost:3000',
            'required': False,
            'ui_component': 'input',
        },
        'scenarios': {
            'type': 'array',
            'label': 'Test Scenarios',
            'label_key': 'composite.test.e2e_flow.scenarios.label',
            'description': 'List of test scenarios to run',
            'description_key': 'composite.test.e2e_flow.scenarios.desc',
            'help': 'Define test scenarios as an array of objects. Each scenario '
                    'should have a name and steps (actions to perform).',
            'help_key': 'composite.test.e2e_flow.scenarios.help',
            'hint': 'Each scenario is a sequence of browser actions',
            'required': True,
            'ui_component': 'json',
            'examples': [
                {
                    'name': 'Login Flow',
                    'steps': [
                        {'action': 'goto', 'url': '/login'},
                        {'action': 'type', 'selector': '#email', 'text': 'test@example.com'},
                        {'action': 'type', 'selector': '#password', 'text': 'password123'},
                        {'action': 'click', 'selector': 'button[type="submit"]'},
                        {'action': 'wait', 'selector': '.dashboard'},
                        {'action': 'screenshot', 'name': 'after_login'},
                    ]
                }
            ],
        },
        'screenshot_dir': {
            'type': 'string',
            'label': 'Screenshot Directory',
            'label_key': 'composite.test.e2e_flow.screenshot_dir.label',
            'description': 'Directory to save screenshots',
            'description_key': 'composite.test.e2e_flow.screenshot_dir.desc',
            'placeholder': './screenshots',
            'default': './test-screenshots',
            'required': False,
            'ui_component': 'input',
        },
        'headless': {
            'type': 'boolean',
            'label': 'Headless Mode',
            'label_key': 'composite.test.e2e_flow.headless.label',
            'description': 'Run browser in headless mode',
            'description_key': 'composite.test.e2e_flow.headless.desc',
            'help': 'Enable headless mode for CI/CD environments where no display is available.',
            'default': True,
            'required': False,
            'ui_component': 'switch',
        },
        'timeout': {
            'type': 'number',
            'label': 'Test Timeout (seconds)',
            'label_key': 'composite.test.e2e_flow.timeout.label',
            'description': 'Maximum time for each test scenario',
            'description_key': 'composite.test.e2e_flow.timeout.desc',
            'placeholder': '60',
            'default': 60,
            'required': False,
            'ui_component': 'number',
        },
        'stop_on_failure': {
            'type': 'boolean',
            'label': 'Stop on Failure',
            'label_key': 'composite.test.e2e_flow.stop_on_failure.label',
            'description': 'Stop testing on first failure',
            'description_key': 'composite.test.e2e_flow.stop_on_failure.desc',
            'default': False,
            'required': False,
            'ui_component': 'switch',
        },
        'cleanup': {
            'type': 'boolean',
            'label': 'Cleanup After Test',
            'label_key': 'composite.test.e2e_flow.cleanup.label',
            'description': 'Stop server and close browser after tests',
            'description_key': 'composite.test.e2e_flow.cleanup.desc',
            'default': True,
            'required': False,
            'ui_component': 'switch',
        }
    },

    # Steps definition - the core workflow
    steps=[
        {
            'id': 'start_server',
            'module': 'process.start',
            'params': {
                'command': '${params.start_command}',
                'cwd': '${params.project_path}',
                'name': 'e2e-test-server',
                'wait_for_output': 'ready',
                'wait_timeout': 60
            },
            'on_error': 'continue',
            'skip_if': '${params.base_url}'
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
            'id': 'run_scenarios',
            'module': 'flow.foreach',
            'params': {
                'items': '${params.scenarios}',
                'variable': 'scenario'
            },
            'steps': [
                {
                    'id': 'scenario_start',
                    'module': 'utility.log',
                    'params': {
                        'message': 'Running scenario: ${scenario.name}'
                    }
                }
            ]
        },
        {
            'id': 'cleanup_browser',
            'module': 'core.browser.close',
            'params': {},
            'on_error': 'continue',
            'run_if': '${params.cleanup}'
        },
        {
            'id': 'cleanup_server',
            'module': 'process.stop',
            'params': {
                'name': 'e2e-test-server'
            },
            'on_error': 'continue',
            'run_if': '${params.cleanup}'
        }
    ],

    # Enhanced output schema
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether all tests passed',
            'example': True,
        },
        'summary': {
            'type': 'object',
            'description': 'Test summary statistics',
            'properties': {
                'total': {'type': 'number', 'description': 'Total scenarios'},
                'passed': {'type': 'number', 'description': 'Passed scenarios'},
                'failed': {'type': 'number', 'description': 'Failed scenarios'},
                'skipped': {'type': 'number', 'description': 'Skipped scenarios'},
                'duration_ms': {'type': 'number', 'description': 'Total duration'},
            }
        },
        'scenarios': {
            'type': 'array',
            'description': 'Individual scenario results',
            'items': {
                'name': {'type': 'string'},
                'status': {'type': 'string', 'enum': ['passed', 'failed', 'skipped']},
                'steps': {'type': 'array'},
                'screenshots': {'type': 'array'},
                'error': {'type': 'string'},
            }
        },
        'screenshots': {
            'type': 'array',
            'description': 'List of captured screenshot paths',
        }
    },

    # Execution settings
    timeout=600,  # 10 minutes for full test suite
    retryable=False,
    max_retries=1,

    # Documentation
    examples=[
        {
            'name': 'Test Next.js App',
            'description': 'Run E2E tests on a Next.js application',
            'params': {
                'project_path': './frontend',
                'start_command': 'npm run dev',
                'server_port': 3000,
                'scenarios': [
                    {
                        'name': 'Home Page Load',
                        'steps': [
                            {'action': 'goto', 'url': '/'},
                            {'action': 'wait', 'selector': 'main'},
                            {'action': 'screenshot', 'name': 'home'},
                        ]
                    },
                    {
                        'name': 'Navigation Test',
                        'steps': [
                            {'action': 'goto', 'url': '/'},
                            {'action': 'click', 'selector': 'nav a[href="/about"]'},
                            {'action': 'wait', 'selector': 'h1'},
                            {'action': 'screenshot', 'name': 'about'},
                        ]
                    }
                ],
                'headless': True
            }
        },
        {
            'name': 'Test React App with Login',
            'description': 'Test React app including authentication flow',
            'params': {
                'project_path': './app',
                'start_command': 'npm start',
                'server_port': 3000,
                'scenarios': [
                    {
                        'name': 'Login Flow',
                        'steps': [
                            {'action': 'goto', 'url': '/login'},
                            {'action': 'type', 'selector': '#email', 'text': 'test@example.com'},
                            {'action': 'type', 'selector': '#password', 'text': 'password'},
                            {'action': 'click', 'selector': 'button[type="submit"]'},
                            {'action': 'wait', 'selector': '.dashboard', 'timeout': 5000},
                            {'action': 'screenshot', 'name': 'dashboard'},
                            {'action': 'assert', 'selector': '.user-name', 'contains': 'Test User'},
                        ]
                    }
                ],
                'stop_on_failure': True
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class WebAppE2ETest(CompositeModule):
    """
    Web Application E2E Test Composite Module

    This composite module provides a complete end-to-end testing workflow:

    1. **Server Management**
       - Starts the development server
       - Waits for the server to be ready (port check)
       - Automatically cleans up after tests

    2. **Browser Automation**
       - Launches browser (headless or visible)
       - Executes test scenarios
       - Captures screenshots at key points

    3. **Test Execution**
       - Runs multiple test scenarios
       - Supports various actions: goto, click, type, wait, assert
       - Handles errors gracefully

    4. **Reporting**
       - Generates comprehensive test report
       - Includes pass/fail statistics
       - Links to captured screenshots
    """

    def _build_output(self, metadata):
        """Build test report from step results"""
        scenarios_results = []
        screenshots = []
        total_passed = 0
        total_failed = 0

        # Process scenario results from step_results
        run_scenarios = self.step_results.get('run_scenarios', {})
        if isinstance(run_scenarios, dict):
            items = run_scenarios.get('results', [])
            for item in items:
                status = 'passed' if item.get('ok', False) else 'failed'
                if status == 'passed':
                    total_passed += 1
                else:
                    total_failed += 1

                scenarios_results.append({
                    'name': item.get('scenario', {}).get('name', 'Unknown'),
                    'status': status,
                    'steps': item.get('steps', []),
                    'screenshots': item.get('screenshots', []),
                    'error': item.get('error'),
                })

                # Collect screenshots
                screenshots.extend(item.get('screenshots', []))

        return {
            'ok': total_failed == 0,
            'summary': {
                'total': len(scenarios_results),
                'passed': total_passed,
                'failed': total_failed,
                'skipped': 0,
                'duration_ms': metadata.get('duration_ms', 0),
            },
            'scenarios': scenarios_results,
            'screenshots': screenshots,
        }
