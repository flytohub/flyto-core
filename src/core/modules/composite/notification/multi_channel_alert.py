"""
Multi-Channel Alert Composite Module

Sends alerts to multiple notification channels simultaneously.
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.notification.multi_channel_alert',
    version='1.0.0',
    category='notification',
    subcategory='alert',
    tags=['notification', 'alert', 'multi-channel', 'slack', 'discord', 'telegram'],

    # Context requirements
    requires_context=None,
    provides_context=['api_response'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='Multi-Channel Alert',
    ui_label_key='modules.composite.notification.multi_channel_alert.label',
    ui_description='Send alert notifications to multiple channels (Slack, Discord, Telegram) simultaneously',
    ui_description_key='modules.composite.notification.multi_channel_alert.description',
    ui_group='Notification / Alert',
    ui_icon='Bell',
    ui_color='#EF4444',

    # UI form generation
    ui_params_schema={
        'title': {
            'type': 'string',
            'label': 'Alert Title',
            'description': 'Title of the alert',
            'placeholder': 'Production Alert',
            'required': True,
            'ui_component': 'input',
        },
        'message': {
            'type': 'string',
            'label': 'Alert Message',
            'description': 'The alert message content',
            'placeholder': 'Server CPU usage exceeded 90%',
            'required': True,
            'ui_component': 'textarea',
        },
        'severity': {
            'type': 'string',
            'label': 'Severity',
            'description': 'Alert severity level',
            'default': 'warning',
            'required': False,
            'ui_component': 'select',
            'options': [
                {'value': 'critical', 'label': 'Critical'},
                {'value': 'warning', 'label': 'Warning'},
                {'value': 'info', 'label': 'Info'}
            ]
        },
        'slack_webhook': {
            'type': 'string',
            'label': 'Slack Webhook URL',
            'description': 'Slack webhook (leave empty to skip)',
            'placeholder': '${env.SLACK_WEBHOOK_URL}',
            'required': False,
            'ui_component': 'input',
        },
        'discord_webhook': {
            'type': 'string',
            'label': 'Discord Webhook URL',
            'description': 'Discord webhook (leave empty to skip)',
            'placeholder': '${env.DISCORD_WEBHOOK_URL}',
            'required': False,
            'ui_component': 'input',
        },
        'telegram_token': {
            'type': 'string',
            'label': 'Telegram Bot Token',
            'description': 'Telegram bot token (leave empty to skip)',
            'placeholder': '${env.TELEGRAM_BOT_TOKEN}',
            'required': False,
            'sensitive': True,
            'ui_component': 'password',
        },
        'telegram_chat_id': {
            'type': 'string',
            'label': 'Telegram Chat ID',
            'description': 'Telegram chat ID or channel username',
            'placeholder': '@alerts',
            'required': False,
            'ui_component': 'input',
        }
    },

    # Connection types
    input_types=['text', 'json'],
    output_types=['api_response'],

    # Steps definition
    steps=[
        {
            'id': 'slack',
            'module': 'notification.slack.send_message',
            'params': {
                'webhook_url': '${params.slack_webhook}',
                'text': 'ALERT: *${params.title}*\n\n${params.message}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'discord',
            'module': 'notification.discord.send_message',
            'params': {
                'webhook_url': '${params.discord_webhook}',
                'content': 'ALERT: **${params.title}**\n\n${params.message}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'telegram',
            'module': 'notification.telegram.send_message',
            'params': {
                'bot_token': '${params.telegram_token}',
                'chat_id': '${params.telegram_chat_id}',
                'text': 'ALERT: *${params.title}*\n\n${params.message}',
                'parse_mode': 'Markdown'
            },
            'on_error': 'continue'
        }
    ],

    # Output schema
    output_schema={
        'status': {'type': 'string'},
        'channels': {
            'type': 'object',
            'properties': {
                'slack': {'type': 'boolean'},
                'discord': {'type': 'boolean'},
                'telegram': {'type': 'boolean'}
            }
        },
        'success_count': {'type': 'number'}
    },

    # Execution settings
    timeout=60,
    retryable=False,
    max_retries=1,

    # Documentation
    examples=[
        {
            'name': 'Critical production alert',
            'description': 'Send critical alert to all channels',
            'params': {
                'title': 'Production Down',
                'message': 'API server is not responding. Immediate action required.',
                'severity': 'critical',
                'slack_webhook': '${env.SLACK_WEBHOOK_URL}',
                'discord_webhook': '${env.DISCORD_WEBHOOK_URL}'
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class MultiChannelAlert(CompositeModule):
    """
    Multi-Channel Alert Composite Module

    This composite module:
    1. Sends alert to Slack (if configured)
    2. Sends alert to Discord (if configured)
    3. Sends alert to Telegram (if configured)
    4. Returns status for each channel
    """

    def _build_output(self, metadata):
        """Build output with channel status"""
        slack_result = self.step_results.get('slack', {})
        discord_result = self.step_results.get('discord', {})
        telegram_result = self.step_results.get('telegram', {})

        channels = {
            'slack': slack_result.get('sent', False),
            'discord': discord_result.get('sent', False),
            'telegram': telegram_result.get('sent', False)
        }

        success_count = sum(1 for sent in channels.values() if sent)

        return {
            'status': 'success' if success_count > 0 else 'failed',
            'channels': channels,
            'success_count': success_count
        }
