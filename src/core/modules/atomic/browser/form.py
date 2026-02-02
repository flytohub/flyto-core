"""
Browser Form Module - Smart form filling

Automatically fills form fields based on a data object.
Supports various input types and can auto-detect field types.

Features:
- Auto-detect input types (text, email, password, select, checkbox, radio)
- Support field mapping with selectors
- Clear fields before filling option
- Submit form option
"""
from typing import Any, Dict, List, Optional

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field


@register_module(
    module_id='browser.form',
    version='1.0.0',
    category='browser',
    tags=['browser', 'form', 'input', 'automation', 'ssrf_protected'],
    label='Fill Form',
    label_key='modules.browser.form.label',
    description='Smart form filling with automatic field detection',
    description_key='modules.browser.form.description',
    icon='FormInput',
    color='#8B5CF6',

    input_types=['page'],
    output_types=['page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'flow.*'],

    params_schema=compose(
        field(
            'form_selector',
            type='string',
            label='Form Selector',
            label_key='modules.browser.form.params.form_selector.label',
            description='CSS selector for the form element (optional)',
            placeholder='form, #login-form',
            required=False,
        ),
        field(
            'data',
            type='object',
            label='Form Data',
            label_key='modules.browser.form.params.data.label',
            description='Key-value pairs to fill (key = field name/id, value = content)',
            required=True,
        ),
        field(
            'field_mapping',
            type='object',
            label='Field Mapping',
            label_key='modules.browser.form.params.field_mapping.label',
            description='Custom selector mapping {fieldName: selector}',
            required=False,
        ),
        field(
            'clear_before_fill',
            type='boolean',
            label='Clear Before Fill',
            label_key='modules.browser.form.params.clear_before_fill.label',
            description='Clear existing field values before filling',
            default=True,
        ),
        field(
            'submit',
            type='boolean',
            label='Submit Form',
            label_key='modules.browser.form.params.submit.label',
            description='Submit form after filling',
            default=False,
        ),
        field(
            'submit_selector',
            type='string',
            label='Submit Button Selector',
            label_key='modules.browser.form.params.submit_selector.label',
            description='CSS selector for submit button',
            placeholder='button[type="submit"], input[type="submit"]',
            required=False,
        ),
        field(
            'delay_between_fields_ms',
            type='integer',
            label='Delay Between Fields (ms)',
            label_key='modules.browser.form.params.delay_between_fields_ms.label',
            description='Delay between filling each field (for more human-like behavior)',
            default=100,
            min=0,
            max=5000,
        ),
    ),
    output_schema={
        'filled_fields': {
            'type': 'array',
            'description': 'List of fields that were filled',
            'description_key': 'modules.browser.form.output.filled_fields.description'
        },
        'failed_fields': {
            'type': 'array',
            'description': 'List of fields that failed to fill',
            'description_key': 'modules.browser.form.output.failed_fields.description'
        },
        'submitted': {
            'type': 'boolean',
            'description': 'Whether form was submitted',
            'description_key': 'modules.browser.form.output.submitted.description'
        }
    },
    examples=[
        {
            'name': 'Fill login form',
            'params': {
                'data': {
                    'email': 'user@example.com',
                    'password': 'secret123'
                },
                'submit': True
            }
        },
        {
            'name': 'Fill with custom selectors',
            'params': {
                'data': {
                    'username': 'john_doe',
                    'bio': 'Hello world'
                },
                'field_mapping': {
                    'username': '#user-name-input',
                    'bio': 'textarea.bio-field'
                }
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=60000,
    required_permissions=['browser.automation'],
)
class BrowserFormModule(BaseModule):
    """
    Smart form filling module.

    Fills form fields based on a data object with automatic
    field type detection and optional custom selector mapping.
    """

    module_name = "Fill Form"
    module_description = "Smart form filling with automatic field detection"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.form_selector = self.params.get('form_selector')
        self.data = self.params.get('data', {})
        self.field_mapping = self.params.get('field_mapping', {})
        self.clear_before_fill = self.params.get('clear_before_fill', True)
        self.submit = self.params.get('submit', False)
        self.submit_selector = self.params.get('submit_selector')
        self.delay_between_fields_ms = self.params.get('delay_between_fields_ms', 100)

        if not isinstance(self.data, dict):
            raise ValueError("data must be an object")

        if not self.data:
            raise ValueError("data cannot be empty")

    async def execute(self) -> Dict[str, Any]:
        import asyncio

        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        filled_fields = []
        failed_fields = []

        for field_name, value in self.data.items():
            try:
                # Get selector for this field
                selector = self._get_field_selector(field_name)

                # Clear field if requested
                if self.clear_before_fill:
                    await browser.evaluate(f'''
                        const el = document.querySelector("{selector}");
                        if (el) {{
                            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {{
                                el.value = '';
                            }}
                        }}
                    ''')

                # Fill the field based on type
                await self._fill_field(browser, selector, value)
                filled_fields.append({
                    'name': field_name,
                    'selector': selector,
                    'value': value if not self._is_sensitive(field_name) else '***'
                })

                # Delay between fields
                if self.delay_between_fields_ms > 0:
                    await asyncio.sleep(self.delay_between_fields_ms / 1000)

            except Exception as e:
                failed_fields.append({
                    'name': field_name,
                    'error': str(e)
                })

        # Submit form if requested
        submitted = False
        if self.submit and len(filled_fields) > 0:
            try:
                submit_sel = self.submit_selector or 'button[type="submit"], input[type="submit"]'
                await browser.click(submit_sel)
                submitted = True
            except Exception as e:
                failed_fields.append({
                    'name': '__submit__',
                    'error': str(e)
                })

        return {
            'ok': True,
            'data': {
                'filled_fields': filled_fields,
                'failed_fields': failed_fields,
                'submitted': submitted,
                'total_fields': len(self.data),
                'success_count': len(filled_fields),
                'fail_count': len(failed_fields)
            }
        }

    def _get_field_selector(self, field_name: str) -> str:
        """Get CSS selector for a field."""
        # Check custom mapping first
        if field_name in self.field_mapping:
            return self.field_mapping[field_name]

        # Build form prefix if form_selector is specified
        prefix = f'{self.form_selector} ' if self.form_selector else ''

        # Try common patterns
        selectors = [
            f'{prefix}[name="{field_name}"]',
            f'{prefix}#{field_name}',
            f'{prefix}[id="{field_name}"]',
            f'{prefix}[data-field="{field_name}"]',
        ]

        return selectors[0]  # Use first pattern by default

    async def _fill_field(self, browser, selector: str, value: Any) -> None:
        """Fill a field based on its type."""
        # Get element info to determine type
        element_info = await browser.evaluate(f'''
            (() => {{
                const el = document.querySelector("{selector}");
                if (!el) return null;
                return {{
                    tagName: el.tagName,
                    type: el.type || '',
                    isSelect: el.tagName === 'SELECT',
                    isCheckbox: el.type === 'checkbox',
                    isRadio: el.type === 'radio'
                }};
            }})()
        ''')

        if not element_info:
            # Try to find by name attribute
            await browser.type(selector, str(value))
            return

        if element_info.get('isSelect'):
            # Handle select dropdown
            await browser.evaluate(f'''
                document.querySelector("{selector}").value = "{value}";
                document.querySelector("{selector}").dispatchEvent(new Event('change', {{ bubbles: true }}));
            ''')
        elif element_info.get('isCheckbox'):
            # Handle checkbox
            should_check = bool(value)
            await browser.evaluate(f'''
                const cb = document.querySelector("{selector}");
                if (cb.checked !== {str(should_check).lower()}) {{
                    cb.click();
                }}
            ''')
        elif element_info.get('isRadio'):
            # Handle radio button
            await browser.evaluate(f'''
                const radio = document.querySelector("{selector}[value='{value}']") ||
                             document.querySelector("{selector}");
                if (radio) radio.click();
            ''')
        else:
            # Regular text input
            await browser.type(selector, str(value))

    def _is_sensitive(self, field_name: str) -> bool:
        """Check if field contains sensitive data."""
        sensitive_keywords = ['password', 'secret', 'token', 'key', 'credit', 'card', 'cvv', 'ssn']
        return any(kw in field_name.lower() for kw in sensitive_keywords)
