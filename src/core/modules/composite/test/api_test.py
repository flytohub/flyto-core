"""
API Test Suite Composite Module

Complete API testing workflow:
1. Optionally start API server
2. Run test cases with HTTP requests
3. Assert responses
4. Generate test report
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.test.api_test',
    version='1.0.0',
    category='test',
    subcategory='api',
    tags=['test', 'api', 'http', 'rest', 'automation', 'qa'],

    # Context requirements
    requires_context=None,
    provides_context=['test_results'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='API Test Suite',
    ui_label_key='composite.test.api_test.label',
    ui_description='Run comprehensive API tests with assertions',
    ui_description_key='composite.test.api_test.desc',
    ui_help='This composite module runs a suite of API tests. '
            'Define test cases with HTTP requests and expected responses. '
            'Supports all HTTP methods, authentication, request bodies, '
            'and comprehensive response assertions including status codes, '
            'headers, and JSON path validation.',
    ui_help_key='composite.test.api_test.help',
    ui_group='Testing / API',
    ui_icon='Zap',
    ui_color='#3B82F6',

    # Connection types with labels and descriptions
    input_types=['object', 'array'],
    input_type_labels={
        'object': 'Test Configuration',
        'array': 'Test Cases',
    },
    input_type_descriptions={
        'object': 'Complete test suite configuration',
        'array': 'Array of test case definitions',
    },

    output_types=['object', 'array'],
    output_type_labels={
        'object': 'Test Report',
        'array': 'Test Results',
    },
    output_type_descriptions={
        'object': 'Comprehensive test report with all results',
        'array': 'Array of individual test case results',
    },

    # Connection suggestions
    suggested_predecessors=[
        'file.read',
        'data.json_parse',
        'process.start',
    ],
    suggested_successors=[
        'file.write',
        'webhook.trigger',
        'communication.slack_send',
        'communication.email_send',
    ],

    # Connection error messages
    connection_error_messages={
        'type_mismatch': 'This module expects test configuration or test cases array',
        'missing_tests': 'Please provide at least one test case',
    },

    # UI form generation with enhanced fields
    ui_params_schema={
        'base_url': {
            'type': 'string',
            'label': 'Base URL',
            'label_key': 'composite.test.api_test.base_url.label',
            'description': 'Base URL for all API requests',
            'description_key': 'composite.test.api_test.base_url.desc',
            'help': 'All test case URLs will be appended to this base URL. '
                    'Include the protocol (http/https) and any base path.',
            'help_key': 'composite.test.api_test.base_url.help',
            'placeholder': 'http://localhost:3000/api',
            'examples': [
                'http://localhost:3000/api',
                'https://api.example.com/v1',
                'http://localhost:8080',
            ],
            'required': True,
            'ui_component': 'input',
            'validation': {
                'pattern': r'^https?://.+',
                'pattern_error': 'URL must start with http:// or https://',
            },
            'error_messages': {
                'required': 'Please enter the base URL for API tests',
                'pattern': 'Invalid URL format',
            },
        },
        'tests': {
            'type': 'array',
            'label': 'Test Cases',
            'label_key': 'composite.test.api_test.tests.label',
            'description': 'Array of API test cases',
            'description_key': 'composite.test.api_test.tests.desc',
            'help': 'Define test cases as an array of objects. Each test case '
                    'should specify the HTTP method, endpoint, and expected response.',
            'help_key': 'composite.test.api_test.tests.help',
            'hint': 'Each test case will be run sequentially',
            'required': True,
            'ui_component': 'json',
            'examples': [
                {
                    'name': 'Get Users List',
                    'method': 'GET',
                    'endpoint': '/users',
                    'expect': {
                        'status': 200,
                        'json_path': {'data': []}
                    }
                },
                {
                    'name': 'Create User',
                    'method': 'POST',
                    'endpoint': '/users',
                    'body': {'name': 'Test User', 'email': 'test@example.com'},
                    'expect': {
                        'status': 201,
                        'json_path_exists': ['data.id']
                    }
                }
            ],
        },
        'auth': {
            'type': 'object',
            'label': 'Authentication',
            'label_key': 'composite.test.api_test.auth.label',
            'description': 'Global authentication configuration',
            'description_key': 'composite.test.api_test.auth.desc',
            'help': 'Authentication will be applied to all requests unless overridden. '
                    'Supports bearer tokens, basic auth, and API keys.',
            'help_key': 'composite.test.api_test.auth.help',
            'required': False,
            'ui_component': 'json',
            'examples': [
                {'type': 'bearer', 'token': '${env.API_TOKEN}'},
                {'type': 'basic', 'username': 'admin', 'password': '${env.PASSWORD}'},
                {'type': 'api_key', 'header_name': 'X-API-Key', 'api_key': '${env.API_KEY}'},
            ],
        },
        'headers': {
            'type': 'object',
            'label': 'Default Headers',
            'label_key': 'composite.test.api_test.headers.label',
            'description': 'Headers to include in all requests',
            'description_key': 'composite.test.api_test.headers.desc',
            'help': 'These headers will be merged with test-specific headers.',
            'required': False,
            'ui_component': 'json',
            'default': {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
        },
        'start_server': {
            'type': 'boolean',
            'label': 'Start Server',
            'label_key': 'composite.test.api_test.start_server.label',
            'description': 'Start a server before running tests',
            'description_key': 'composite.test.api_test.start_server.desc',
            'default': False,
            'required': False,
            'ui_component': 'switch',
        },
        'server_command': {
            'type': 'string',
            'label': 'Server Command',
            'label_key': 'composite.test.api_test.server_command.label',
            'description': 'Command to start the API server',
            'description_key': 'composite.test.api_test.server_command.desc',
            'placeholder': 'npm run start:api',
            'required': False,
            'ui_component': 'input',
            'visible_when': {
                'field': 'start_server',
                'value': True
            },
        },
        'server_cwd': {
            'type': 'string',
            'label': 'Server Working Directory',
            'label_key': 'composite.test.api_test.server_cwd.label',
            'description': 'Directory to run server command in',
            'description_key': 'composite.test.api_test.server_cwd.desc',
            'placeholder': './backend',
            'required': False,
            'ui_component': 'input',
            'visible_when': {
                'field': 'start_server',
                'value': True
            },
        },
        'server_port': {
            'type': 'number',
            'label': 'Server Port',
            'label_key': 'composite.test.api_test.server_port.label',
            'description': 'Port to wait for before running tests',
            'description_key': 'composite.test.api_test.server_port.desc',
            'placeholder': '3000',
            'default': 3000,
            'required': False,
            'ui_component': 'number',
            'visible_when': {
                'field': 'start_server',
                'value': True
            },
        },
        'timeout': {
            'type': 'number',
            'label': 'Request Timeout (seconds)',
            'label_key': 'composite.test.api_test.timeout.label',
            'description': 'Timeout for each HTTP request',
            'description_key': 'composite.test.api_test.timeout.desc',
            'placeholder': '30',
            'default': 30,
            'required': False,
            'ui_component': 'number',
        },
        'stop_on_failure': {
            'type': 'boolean',
            'label': 'Stop on Failure',
            'label_key': 'composite.test.api_test.stop_on_failure.label',
            'description': 'Stop test suite on first failure',
            'description_key': 'composite.test.api_test.stop_on_failure.desc',
            'default': False,
            'required': False,
            'ui_component': 'switch',
        },
        'parallel': {
            'type': 'boolean',
            'label': 'Run in Parallel',
            'label_key': 'composite.test.api_test.parallel.label',
            'description': 'Run independent tests in parallel',
            'description_key': 'composite.test.api_test.parallel.desc',
            'help': 'Enable to run tests concurrently for faster execution. '
                    'Disable if tests have dependencies on each other.',
            'default': False,
            'required': False,
            'ui_component': 'switch',
        },
        'retry_failed': {
            'type': 'number',
            'label': 'Retry Failed Tests',
            'label_key': 'composite.test.api_test.retry_failed.label',
            'description': 'Number of times to retry failed tests',
            'description_key': 'composite.test.api_test.retry_failed.desc',
            'default': 0,
            'required': False,
            'ui_component': 'number',
            'validation': {
                'min': 0,
                'max': 5,
            },
        },
        'variables': {
            'type': 'object',
            'label': 'Test Variables',
            'label_key': 'composite.test.api_test.variables.label',
            'description': 'Variables to use in test cases (${var_name})',
            'description_key': 'composite.test.api_test.variables.desc',
            'help': 'Define variables that can be referenced in test cases '
                    'using ${variable_name} syntax.',
            'required': False,
            'ui_component': 'json',
            'examples': [
                {
                    'user_id': '12345',
                    'api_version': 'v2',
                    'test_email': 'test@example.com'
                }
            ],
        },
        'setup': {
            'type': 'array',
            'label': 'Setup Requests',
            'label_key': 'composite.test.api_test.setup.label',
            'description': 'Requests to run before tests (e.g., login)',
            'description_key': 'composite.test.api_test.setup.desc',
            'help': 'These requests run before the test suite starts. '
                    'Use for authentication or data seeding.',
            'required': False,
            'ui_component': 'json',
        },
        'teardown': {
            'type': 'array',
            'label': 'Teardown Requests',
            'label_key': 'composite.test.api_test.teardown.label',
            'description': 'Requests to run after tests (e.g., cleanup)',
            'description_key': 'composite.test.api_test.teardown.desc',
            'help': 'These requests run after all tests complete. '
                    'Use for cleanup operations.',
            'required': False,
            'ui_component': 'json',
        }
    },

    # Steps definition
    steps=[
        {
            'id': 'start_api_server',
            'module': 'process.start',
            'params': {
                'command': '${params.server_command}',
                'cwd': '${params.server_cwd}',
                'name': 'api-test-server',
            },
            'skip_if': '!${params.start_server}'
        },
        {
            'id': 'wait_server_port',
            'module': 'port.wait',
            'params': {
                'port': '${params.server_port}',
                'timeout': 60
            },
            'skip_if': '!${params.start_server}'
        },
        {
            'id': 'run_setup',
            'module': 'flow.foreach',
            'params': {
                'items': '${params.setup}',
                'variable': 'setup_request'
            },
            'skip_if': '!${params.setup}'
        },
        {
            'id': 'run_tests',
            'module': 'flow.foreach',
            'params': {
                'items': '${params.tests}',
                'variable': 'test_case'
            },
            'steps': [
                {
                    'id': 'make_request',
                    'module': 'http.request',
                    'params': {
                        'url': '${params.base_url}${test_case.endpoint}',
                        'method': '${test_case.method}',
                        'headers': '${merge(params.headers, test_case.headers)}',
                        'body': '${test_case.body}',
                        'auth': '${params.auth}',
                        'timeout': '${params.timeout}'
                    }
                },
                {
                    'id': 'assert_response',
                    'module': 'http.response_assert',
                    'params': {
                        'response': '${make_request}',
                        'status': '${test_case.expect.status}',
                        'json_path': '${test_case.expect.json_path}',
                        'json_path_exists': '${test_case.expect.json_path_exists}',
                        'body_contains': '${test_case.expect.body_contains}',
                        'content_type': '${test_case.expect.content_type}',
                        'max_duration_ms': '${test_case.expect.max_duration_ms}'
                    }
                }
            ]
        },
        {
            'id': 'run_teardown',
            'module': 'flow.foreach',
            'params': {
                'items': '${params.teardown}',
                'variable': 'teardown_request'
            },
            'skip_if': '!${params.teardown}',
            'on_error': 'continue'
        },
        {
            'id': 'stop_api_server',
            'module': 'process.stop',
            'params': {
                'name': 'api-test-server'
            },
            'skip_if': '!${params.start_server}',
            'on_error': 'continue'
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
                'total': {'type': 'number', 'description': 'Total test cases'},
                'passed': {'type': 'number', 'description': 'Passed tests'},
                'failed': {'type': 'number', 'description': 'Failed tests'},
                'skipped': {'type': 'number', 'description': 'Skipped tests'},
                'duration_ms': {'type': 'number', 'description': 'Total duration'},
                'avg_response_ms': {'type': 'number', 'description': 'Average response time'},
            }
        },
        'tests': {
            'type': 'array',
            'description': 'Individual test results',
            'items': {
                'name': {'type': 'string'},
                'endpoint': {'type': 'string'},
                'method': {'type': 'string'},
                'status': {'type': 'string', 'enum': ['passed', 'failed', 'skipped']},
                'response': {
                    'type': 'object',
                    'properties': {
                        'status': {'type': 'number'},
                        'duration_ms': {'type': 'number'},
                    }
                },
                'assertions': {'type': 'array'},
                'error': {'type': 'string'},
            }
        },
        'coverage': {
            'type': 'object',
            'description': 'API coverage statistics',
            'properties': {
                'endpoints_tested': {'type': 'array'},
                'methods_used': {'type': 'array'},
                'status_codes_seen': {'type': 'array'},
            }
        }
    },

    # Execution settings
    timeout=300,  # 5 minutes for full test suite
    retryable=False,
    max_retries=1,

    # Documentation
    examples=[
        {
            'name': 'Basic REST API Test',
            'description': 'Test CRUD operations on a REST API',
            'params': {
                'base_url': 'http://localhost:3000/api',
                'tests': [
                    {
                        'name': 'Get all users',
                        'method': 'GET',
                        'endpoint': '/users',
                        'expect': {
                            'status': 200,
                            'content_type': 'application/json',
                            'json_path_exists': ['data']
                        }
                    },
                    {
                        'name': 'Create user',
                        'method': 'POST',
                        'endpoint': '/users',
                        'body': {
                            'name': 'Test User',
                            'email': 'test@example.com'
                        },
                        'expect': {
                            'status': 201,
                            'json_path': {
                                'data.name': 'Test User'
                            }
                        }
                    },
                    {
                        'name': 'Get single user',
                        'method': 'GET',
                        'endpoint': '/users/1',
                        'expect': {
                            'status': 200,
                            'json_path_exists': ['data.id', 'data.name']
                        }
                    },
                    {
                        'name': 'Delete user',
                        'method': 'DELETE',
                        'endpoint': '/users/1',
                        'expect': {
                            'status': [200, 204]
                        }
                    }
                ]
            }
        },
        {
            'name': 'Authenticated API Test',
            'description': 'Test API with bearer token authentication',
            'params': {
                'base_url': 'https://api.example.com/v1',
                'auth': {
                    'type': 'bearer',
                    'token': '${env.API_TOKEN}'
                },
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Request-ID': '${uuid()}'
                },
                'setup': [
                    {
                        'name': 'Login',
                        'method': 'POST',
                        'endpoint': '/auth/login',
                        'body': {
                            'email': '${env.TEST_EMAIL}',
                            'password': '${env.TEST_PASSWORD}'
                        },
                        'save_response': {
                            'token': 'data.access_token'
                        }
                    }
                ],
                'tests': [
                    {
                        'name': 'Get profile',
                        'method': 'GET',
                        'endpoint': '/profile',
                        'expect': {
                            'status': 200,
                            'json_path_exists': ['data.email']
                        }
                    }
                ]
            }
        },
        {
            'name': 'API with Server Start',
            'description': 'Start server, run tests, then cleanup',
            'params': {
                'base_url': 'http://localhost:4000/api',
                'start_server': True,
                'server_command': 'npm run start:test',
                'server_cwd': './backend',
                'server_port': 4000,
                'tests': [
                    {
                        'name': 'Health check',
                        'method': 'GET',
                        'endpoint': '/health',
                        'expect': {
                            'status': 200,
                            'json_path': {'status': 'ok'}
                        }
                    }
                ]
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class APITestSuite(CompositeModule):
    """
    API Test Suite Composite Module

    This composite module provides comprehensive API testing:

    1. **Server Management** (optional)
       - Start API server before tests
       - Wait for server readiness
       - Cleanup after tests

    2. **Setup & Teardown**
       - Run setup requests (e.g., login, seed data)
       - Run teardown requests (e.g., cleanup)

    3. **Test Execution**
       - Support for all HTTP methods
       - Request body and headers
       - Authentication (bearer, basic, API key)
       - Response assertions

    4. **Assertions**
       - Status code validation
       - JSON path assertions
       - Body content matching
       - Response time limits

    5. **Reporting**
       - Comprehensive test report
       - Pass/fail statistics
       - Response time metrics
       - API coverage analysis
    """

    def _build_output(self, metadata):
        """Build test report from step results"""
        test_results = []
        total_passed = 0
        total_failed = 0
        total_duration = 0
        endpoints_tested = set()
        methods_used = set()
        status_codes_seen = set()

        # Process test results
        run_tests = self.step_results.get('run_tests', {})
        if isinstance(run_tests, dict):
            items = run_tests.get('results', [])
            for item in items:
                test_case = item.get('test_case', {})
                request_result = item.get('make_request', {})
                assert_result = item.get('assert_response', {})

                # Determine status
                request_ok = request_result.get('ok', False)
                assert_ok = assert_result.get('ok', False)
                status = 'passed' if (request_ok and assert_ok) else 'failed'

                if status == 'passed':
                    total_passed += 1
                else:
                    total_failed += 1

                # Track metrics
                duration = request_result.get('duration_ms', 0)
                total_duration += duration

                endpoint = test_case.get('endpoint', '')
                method = test_case.get('method', 'GET')
                response_status = request_result.get('status', 0)

                endpoints_tested.add(endpoint)
                methods_used.add(method)
                if response_status:
                    status_codes_seen.add(response_status)

                test_results.append({
                    'name': test_case.get('name', f'{method} {endpoint}'),
                    'endpoint': endpoint,
                    'method': method,
                    'status': status,
                    'response': {
                        'status': response_status,
                        'duration_ms': duration,
                    },
                    'assertions': assert_result.get('assertions', []),
                    'error': assert_result.get('errors', []) if not assert_ok else None,
                })

        total_tests = len(test_results)
        avg_duration = total_duration // max(total_tests, 1)

        return {
            'ok': total_failed == 0,
            'summary': {
                'total': total_tests,
                'passed': total_passed,
                'failed': total_failed,
                'skipped': 0,
                'duration_ms': metadata.get('duration_ms', total_duration),
                'avg_response_ms': avg_duration,
            },
            'tests': test_results,
            'coverage': {
                'endpoints_tested': list(endpoints_tested),
                'methods_used': list(methods_used),
                'status_codes_seen': sorted(list(status_codes_seen)),
            }
        }
