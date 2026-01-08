"""
CLI Internationalization Stub

This is a stub implementation. Actual translations are provided by flyto-i18n.
The CLI will display keys directly until flyto-i18n integration is complete.
"""


class I18n:
    """
    Stub i18n class - returns key as-is.

    In production, this should be replaced by flyto-i18n integration.
    """

    def __init__(self, lang: str = 'en'):
        self.lang = lang
        # Default English fallbacks for common CLI messages
        self._fallbacks = {
            'cli.welcome': 'Welcome to Flyto Workflow Engine',
            'cli.version': 'Version: 1.0.0',
            'cli.description': 'Automate your workflows with ease',
            'cli.loading_workflow': 'Loading workflow',
            'cli.goodbye': 'Goodbye!',
            'cli.no_workflows_found': 'No workflows found',
            'cli.available_workflows': 'Available workflows:',
            'cli.enter_custom_path': 'Enter custom path',
            'cli.invalid_workflow_choice': 'Invalid choice. Please enter 1-{max}',
            'cli.starting_workflow': 'Starting workflow...',
            'cli.step_progress': 'Step {current}/{total}',
            'cli.workflow_completed': 'Workflow completed successfully!',
            'cli.workflow_failed': 'Workflow failed',
            'cli.execution_time': 'Execution time',
            'cli.results_saved': 'Results saved to',
            'cli.error_occurred': 'Error',
            'cli.required_parameters': 'Required parameters:',
            'cli.parameter_required': 'This parameter is required',
            'cli.value_min': 'Value must be >= {min}',
            'cli.value_max': 'Value must be <= {max}',
            'cli.invalid_type': 'Invalid type, expected {type}',
            'cli.example': 'Example: {placeholder}',
            'params.required': 'required',
            'params.optional': 'optional',
            'params.default': 'default',
            'status.success': 'Success',
            'status.error': 'Error',
        }

    def t(self, key: str, **kwargs) -> str:
        """
        Get translated text.

        Returns fallback English text if available, otherwise returns the key.
        """
        text = self._fallbacks.get(key, key)

        # Replace placeholders
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                return text

        return text
