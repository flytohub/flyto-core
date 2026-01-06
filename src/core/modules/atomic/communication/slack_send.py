"""
Slack Send Module
Send messages to Slack channels via webhook
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='slack.send',
    stability="beta",
    version='1.0.0',
    category='communication',
    subcategory='slack',
    tags=['slack', 'message', 'send', 'notification', 'webhook'],
    label='Send Slack Message',
    label_key='modules.slack.send.label',
    description='Send messages to Slack channels via incoming webhook',
    description_key='modules.slack.send.description',
    icon='MessageSquare',
    color='#4A154B',

    input_types=['text', 'object'],
    output_types=['object'],
    can_connect_to=['notification.*'],
    can_receive_from=['*'],

    timeout=30,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    requires_credentials=True,
    handles_sensitive_data=False,
    required_permissions=['network.http'],

    params_schema=compose(
        presets.SLACK_MESSAGE(),
        presets.SLACK_WEBHOOK_URL(),
        presets.SLACK_CHANNEL(),
        presets.SLACK_USERNAME(),
        presets.SLACK_ICON_EMOJI(),
        presets.SLACK_BLOCKS(),
        presets.SLACK_ATTACHMENTS(),
    ),
    output_schema={
        'sent': {
            'type': 'boolean',
            'description': 'Whether message was sent successfully'
        }
    },
    examples=[
        {
            'title': 'Send simple message',
            'title_key': 'modules.slack.send.examples.simple.title',
            'params': {
                'message': 'Hello from Flyto!'
            }
        },
        {
            'title': 'Send with formatting',
            'title_key': 'modules.slack.send.examples.formatted.title',
            'params': {
                'message': 'Task completed successfully',
                'username': 'Flyto Bot',
                'icon_emoji': ':white_check_mark:'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def slack_send(context: Dict[str, Any]) -> Dict[str, Any]:
    """Send message to Slack via webhook"""
    try:
        import aiohttp
    except ImportError:
        raise ImportError("aiohttp is required for slack.send. Install with: pip install aiohttp")

    params = context['params']
    message = params['message']
    webhook_url = params.get('webhook_url') or os.getenv('SLACK_WEBHOOK_URL')
    channel = params.get('channel')
    username = params.get('username')
    icon_emoji = params.get('icon_emoji')
    blocks = params.get('blocks')
    attachments = params.get('attachments')

    if not webhook_url:
        raise ValueError("Slack webhook URL not configured. Set SLACK_WEBHOOK_URL env or provide webhook_url param")

    payload = {'text': message}

    if channel:
        payload['channel'] = channel
    if username:
        payload['username'] = username
    if icon_emoji:
        payload['icon_emoji'] = icon_emoji
    if blocks:
        payload['blocks'] = blocks
    if attachments:
        payload['attachments'] = attachments

    async with aiohttp.ClientSession() as session:
        async with session.post(webhook_url, json=payload) as response:
            if response.status == 200:
                logger.info("Slack message sent successfully")
                return {
                    'ok': True,
                    'sent': True
                }
            else:
                text = await response.text()
                logger.error(f"Failed to send Slack message: {response.status} - {text}")
                raise RuntimeError(f"Slack API error: {response.status} - {text}")
