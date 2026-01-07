"""
Scheduled Report Composite Module

Generates and sends scheduled reports to notification channels.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.notification.scheduled_report',
    label='Scheduled Report',
    icon='FileText',
    color='#3B82F6',

    steps=[
        {
            'id': 'get_timestamp',
            'module': 'utility.datetime.now',
            'params': {'format': 'YYYY-MM-DD HH:mm:ss'}
        },
        {
            'id': 'format_report',
            'module': 'data.text.template',
            'params': {
                'template': '*${params.report_title}*\n\nGenerated: ${steps.get_timestamp.result}\n\n${params.report_content}'
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
                'body': '${steps.format_report.result}'
            },
            'on_error': 'continue'
        }
    ],

    params_schema={
        'report_title': {
            'type': 'string',
            'label': 'Report Title',
            'required': True,
            'placeholder': 'Daily Sales Report'
        },
        'report_content': {
            'type': 'string',
            'label': 'Report Content',
            'required': True,
            'placeholder': 'Total sales: $10,000'
        },
        'slack_webhook': {
            'type': 'string',
            'label': 'Slack Webhook URL',
            'placeholder': '${env.SLACK_WEBHOOK_URL}'
        },
        'smtp_server': {
            'type': 'string',
            'label': 'SMTP Server',
            'placeholder': 'smtp.gmail.com'
        },
        'smtp_port': {
            'type': 'number',
            'label': 'SMTP Port',
            'default': 587
        },
        'smtp_username': {
            'type': 'string',
            'label': 'SMTP Username',
            'placeholder': '${env.SMTP_USERNAME}'
        },
        'smtp_password': {
            'type': 'string',
            'label': 'SMTP Password',
            'sensitive': True,
            'placeholder': '${env.SMTP_PASSWORD}'
        },
        'from_email': {
            'type': 'string',
            'label': 'From Email',
            'placeholder': 'reports@company.com'
        },
        'to_email': {
            'type': 'string',
            'label': 'To Email',
            'placeholder': 'manager@company.com'
        }
    },

    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'report_title': {'type': 'string', 'description': 'The report title'},
        'timestamp': {'type': 'string', 'description': 'Unix timestamp'},
        'channels': {'type': 'object', 'description': 'The channels'}
    },

    timeout=60,
    retryable=True,
    max_retries=2,
)
class ScheduledReport(CompositeModule):
    """Scheduled Report - generate and send reports via Slack and email"""

    def _build_output(self, metadata):
        timestamp_result = self.step_results.get('get_timestamp', {})
        slack_result = self.step_results.get('send_slack', {})
        email_result = self.step_results.get('send_email', {})

        return {
            'status': 'success',
            'report_title': self.params.get('report_title', ''),
            'timestamp': timestamp_result.get('result', ''),
            'channels': {
                'slack': slack_result.get('sent', False),
                'email': email_result.get('sent', False)
            }
        }
