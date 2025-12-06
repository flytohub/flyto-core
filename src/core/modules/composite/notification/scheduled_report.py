"""
Scheduled Report Composite Module

Generates and sends scheduled reports to notification channels.
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.notification.scheduled_report',
    version='1.0.0',
    category='notification',
    subcategory='report',
    tags=['notification', 'report', 'scheduled', 'email', 'slack'],

    # Context requirements
    requires_context=None,
    provides_context=['api_response'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='Scheduled Report',
    ui_label_key='composite.scheduled_report.label',
    ui_description='Generate a report from data and send it via email or Slack',
    ui_description_key='composite.scheduled_report.desc',
    ui_group='Notification / Report',
    ui_icon='FileText',
    ui_color='#3B82F6',

    # UI form generation
    ui_params_schema={
        'report_title': {
            'type': 'string',
            'label': 'Report Title',
            'label_key': 'composite.scheduled_report.report_title.label',
            'description': 'Title of the report',
            'description_key': 'composite.scheduled_report.report_title.desc',
            'placeholder': 'Daily Sales Report',
            'required': True,
            'ui_component': 'input',
        },
        'report_content': {
            'type': 'string',
            'label': 'Report Content',
            'label_key': 'composite.scheduled_report.report_content.label',
            'description': 'The report content (plain text or markdown)',
            'description_key': 'composite.scheduled_report.report_content.desc',
            'placeholder': 'Total sales: $10,000\nNew customers: 15',
            'required': True,
            'ui_component': 'textarea',
        },
        'slack_webhook': {
            'type': 'string',
            'label': 'Slack Webhook URL',
            'label_key': 'composite.scheduled_report.slack_webhook.label',
            'description': 'Slack webhook (leave empty to skip)',
            'description_key': 'composite.scheduled_report.slack_webhook.desc',
            'placeholder': '${env.SLACK_WEBHOOK_URL}',
            'required': False,
            'ui_component': 'input',
        },
        'smtp_server': {
            'type': 'string',
            'label': 'SMTP Server',
            'label_key': 'composite.scheduled_report.smtp_server.label',
            'description': 'Email SMTP server (leave empty to skip email)',
            'description_key': 'composite.scheduled_report.smtp_server.desc',
            'placeholder': 'smtp.gmail.com',
            'required': False,
            'ui_component': 'input',
        },
        'smtp_port': {
            'type': 'number',
            'label': 'SMTP Port',
            'label_key': 'composite.scheduled_report.smtp_port.label',
            'description': 'SMTP port',
            'description_key': 'composite.scheduled_report.smtp_port.desc',
            'default': 587,
            'required': False,
            'ui_component': 'number',
        },
        'smtp_username': {
            'type': 'string',
            'label': 'SMTP Username',
            'label_key': 'composite.scheduled_report.smtp_username.label',
            'description': 'SMTP login username',
            'description_key': 'composite.scheduled_report.smtp_username.desc',
            'placeholder': '${env.SMTP_USERNAME}',
            'required': False,
            'ui_component': 'input',
        },
        'smtp_password': {
            'type': 'string',
            'label': 'SMTP Password',
            'label_key': 'composite.scheduled_report.smtp_password.label',
            'description': 'SMTP login password',
            'description_key': 'composite.scheduled_report.smtp_password.desc',
            'placeholder': '${env.SMTP_PASSWORD}',
            'required': False,
            'sensitive': True,
            'ui_component': 'password',
        },
        'from_email': {
            'type': 'string',
            'label': 'From Email',
            'label_key': 'composite.scheduled_report.from_email.label',
            'description': 'Sender email address',
            'description_key': 'composite.scheduled_report.from_email.desc',
            'placeholder': 'reports@company.com',
            'required': False,
            'ui_component': 'input',
        },
        'to_email': {
            'type': 'string',
            'label': 'To Email',
            'label_key': 'composite.scheduled_report.to_email.label',
            'description': 'Recipient email address',
            'description_key': 'composite.scheduled_report.to_email.desc',
            'placeholder': 'manager@company.com',
            'required': False,
            'ui_component': 'input',
        }
    },

    # Connection types
    input_types=['json', 'text'],
    output_types=['api_response'],

    # Steps definition
    steps=[
        {
            'id': 'get_timestamp',
            'module': 'utility.datetime.now',
            'params': {
                'format': 'YYYY-MM-DD HH:mm:ss'
            }
        },
        {
            'id': 'format_report',
            'module': 'data.text.template',
            'params': {
                'template': '*${params.report_title}*\n\nGenerated: ${steps.get_timestamp.result}\n\n${params.report_content}\n\n---\nReport generated by Flyto Core'
            }
        },
        {
            'id': 'send_slack',
            'module': 'notification.slack.send_message',
            'params': {
                'webhook_url': '${params.slack_webhook}',
                'text': '${steps.format_report.result}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'send_email',
            'module': 'notification.email.send',
            'params': {
                'smtp_server': '${params.smtp_server}',
                'smtp_port': '${params.smtp_port}',
                'username': '${params.smtp_username}',
                'password': '${params.smtp_password}',
                'from_email': '${params.from_email}',
                'to_email': '${params.to_email}',
                'subject': '${params.report_title}',
                'body': '${steps.format_report.result}',
                'html': False
            },
            'on_error': 'continue'
        }
    ],

    # Output schema
    output_schema={
        'status': {'type': 'string'},
        'report_title': {'type': 'string'},
        'timestamp': {'type': 'string'},
        'channels': {
            'type': 'object',
            'properties': {
                'slack': {'type': 'boolean'},
                'email': {'type': 'boolean'}
            }
        }
    },

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=2,

    # Documentation
    examples=[
        {
            'name': 'Daily sales report to Slack',
            'description': 'Send daily sales report to Slack channel',
            'params': {
                'report_title': 'Daily Sales Report',
                'report_content': 'Total sales: $15,000\nOrders: 42\nTop product: Widget Pro',
                'slack_webhook': '${env.SLACK_WEBHOOK_URL}'
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class ScheduledReport(CompositeModule):
    """
    Scheduled Report Composite Module

    This composite module:
    1. Gets current timestamp
    2. Formats the report with title and timestamp
    3. Sends to Slack (if configured)
    4. Sends via email (if configured)
    """

    def _build_output(self, metadata):
        """Build output with delivery status"""
        timestamp_result = self.step_results.get('get_timestamp', {})
        slack_result = self.step_results.get('send_slack', {})
        email_result = self.step_results.get('send_email', {})

        channels = {
            'slack': slack_result.get('sent', False),
            'email': email_result.get('sent', False)
        }

        return {
            'status': 'success',
            'report_title': self.params.get('report_title', ''),
            'timestamp': timestamp_result.get('result', ''),
            'channels': channels
        }
