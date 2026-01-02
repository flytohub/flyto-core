"""
Multi-Channel Alert Composite Module

Sends alerts to multiple notification channels simultaneously.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.notification.multi_channel_alert',
    label='Multi-Channel Alert',
    icon='Bell',
    color='#EF4444',

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

    params_schema={
        'title': {
            'type': 'string',
            'label': 'Alert Title',
            'required': True,
            'placeholder': 'Production Alert'
        },
        'message': {
            'type': 'string',
            'label': 'Alert Message',
            'required': True,
            'placeholder': 'Server CPU usage exceeded 90%'
        },
        'severity': {
            'type': 'string',
            'label': 'Severity',
            'default': 'warning',
            'options': ['critical', 'warning', 'info']
        },
        'slack_webhook': {
            'type': 'string',
            'label': 'Slack Webhook URL',
            'placeholder': '${env.SLACK_WEBHOOK_URL}'
        },
        'discord_webhook': {
            'type': 'string',
            'label': 'Discord Webhook URL',
            'placeholder': '${env.DISCORD_WEBHOOK_URL}'
        },
        'telegram_token': {
            'type': 'string',
            'label': 'Telegram Bot Token',
            'sensitive': True,
            'placeholder': '${env.TELEGRAM_BOT_TOKEN}'
        },
        'telegram_chat_id': {
            'type': 'string',
            'label': 'Telegram Chat ID',
            'placeholder': '@alerts'
        }
    },

    output_schema={
        'status': {'type': 'string'},
        'channels': {'type': 'object'},
        'success_count': {'type': 'number'}
    },

    timeout=60,
    retryable=False,
    max_retries=1,
)
class MultiChannelAlert(CompositeModule):
    """Multi-Channel Alert - send to Slack, Discord, Telegram simultaneously"""

    def _build_output(self, metadata):
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
