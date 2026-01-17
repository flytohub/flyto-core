"""
Notify Send Module
Simple notification sender with auto platform detection.
Supports: Telegram, Discord, Slack, LINE, Generic Webhook
"""
import logging
import re
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_url_with_env_config, SSRFError


logger = logging.getLogger(__name__)


# Platform detection patterns
PLATFORM_PATTERNS = {
    'telegram': r'api\.telegram\.org/bot',
    'discord': r'discord\.com/api/webhooks|discordapp\.com/api/webhooks',
    'slack': r'hooks\.slack\.com',
    'line': r'api\.line\.me',
    'teams': r'webhook\.office\.com',
}


def detect_platform(url: str) -> str:
    """Detect notification platform from URL"""
    url_lower = url.lower()
    for platform, pattern in PLATFORM_PATTERNS.items():
        if re.search(pattern, url_lower):
            return platform
    return 'generic'


def build_payload(platform: str, message: str, title: str = None, extra: Dict = None) -> Dict:
    """Build platform-specific payload"""
    extra = extra or {}

    if platform == 'telegram':
        # Telegram Bot API format
        # URL should include chat_id as query param or in extra
        payload = {
            'text': message,
            'parse_mode': extra.get('parse_mode', 'HTML'),
        }
        if 'chat_id' in extra:
            payload['chat_id'] = extra['chat_id']
        return payload

    elif platform == 'discord':
        # Discord Webhook format
        payload = {'content': message}
        if title:
            payload['embeds'] = [{
                'title': title,
                'description': message,
                'color': extra.get('color', 7506394)  # Purple
            }]
            payload['content'] = None
        return payload

    elif platform == 'slack':
        # Slack Webhook format
        payload = {'text': message}
        if title:
            payload['blocks'] = [
                {
                    'type': 'header',
                    'text': {'type': 'plain_text', 'text': title}
                },
                {
                    'type': 'section',
                    'text': {'type': 'mrkdwn', 'text': message}
                }
            ]
        return payload

    elif platform == 'line':
        # LINE Notify format
        return {'message': f"{title}\n{message}" if title else message}

    elif platform == 'teams':
        # Microsoft Teams format
        return {
            '@type': 'MessageCard',
            'summary': title or 'Notification',
            'themeColor': extra.get('color', '8B5CF6'),
            'title': title,
            'text': message
        }

    else:
        # Generic webhook - just send message in body
        payload = {'message': message}
        if title:
            payload['title'] = title
        payload.update(extra)
        return payload


@register_module(
    module_id='notify.send',
    stability='stable',
    version='1.0.0',
    category='notification',
    subcategory='send',
    tags=['notification', 'webhook', 'telegram', 'discord', 'slack', 'alert', 'ssrf_protected'],
    label='Send Notification',
    label_key='modules.notify.send.label',
    description='Send notification to Telegram, Discord, Slack, LINE, or any webhook URL',
    description_key='modules.notify.send.description',
    icon='Bell',
    color='#8B5CF6',

    input_types=['text', 'object'],
    output_types=['object'],
    can_connect_to=['flow.*', 'data.*'],
    can_receive_from=['*'],

    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'url': {
            'type': 'string',
            'label': 'Webhook URL',
            'label_key': 'modules.notify.send.params.url.label',
            'description': 'Webhook URL (Telegram, Discord, Slack, or custom)',
            'description_key': 'modules.notify.send.params.url.description',
            'required': True,
            'placeholder': 'https://api.telegram.org/bot<TOKEN>/sendMessage',
            'secret': True
        },
        'message': {
            'type': 'string',
            'label': 'Message',
            'label_key': 'modules.notify.send.params.message.label',
            'description': 'Notification message content',
            'description_key': 'modules.notify.send.params.message.description',
            'required': True,
            'multiline': True,
            'placeholder': 'Hello from Flyto!'
        },
        'title': {
            'type': 'string',
            'label': 'Title',
            'label_key': 'modules.notify.send.params.title.label',
            'description': 'Optional title (for Discord, Slack, Teams)',
            'description_key': 'modules.notify.send.params.title.description',
            'required': False,
            'placeholder': 'Alert'
        },
        'chat_id': {
            'type': 'string',
            'label': 'Chat ID',
            'label_key': 'modules.notify.send.params.chat_id.label',
            'description': 'Telegram chat ID (required for Telegram)',
            'description_key': 'modules.notify.send.params.chat_id.description',
            'required': False,
            'placeholder': '123456789',
            'show_if': {'url': {'contains': 'telegram'}}
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether notification was sent successfully',
            'description_key': 'modules.notify.send.output.ok.description'
        },
        'platform': {
            'type': 'string',
            'description': 'Detected platform (telegram, discord, slack, etc.)',
            'description_key': 'modules.notify.send.output.platform.description'
        },
        'status_code': {
            'type': 'number',
            'description': 'HTTP response status code',
            'description_key': 'modules.notify.send.output.status_code.description'
        },
        'response': {
            'type': 'object',
            'description': 'Response from the webhook',
            'description_key': 'modules.notify.send.output.response.description'
        }
    },
    examples=[
        {
            'title': 'Send Telegram notification',
            'title_key': 'modules.notify.send.examples.telegram.title',
            'params': {
                'url': 'https://api.telegram.org/bot<TOKEN>/sendMessage',
                'message': 'BTC: $42,350 (+1.7%)',
                'chat_id': '123456789'
            }
        },
        {
            'title': 'Send Discord notification',
            'title_key': 'modules.notify.send.examples.discord.title',
            'params': {
                'url': 'https://discord.com/api/webhooks/xxx/yyy',
                'message': 'Price alert triggered!',
                'title': 'Crypto Alert'
            }
        },
        {
            'title': 'Send Slack notification',
            'title_key': 'modules.notify.send.examples.slack.title',
            'params': {
                'url': 'https://hooks.slack.com/services/xxx/yyy/zzz',
                'message': 'Deployment completed successfully'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def notify_send(context: Dict[str, Any]) -> Dict[str, Any]:
    """Send notification to webhook URL with auto platform detection"""
    try:
        import aiohttp
    except ImportError:
        raise ImportError("aiohttp is required for notify.send. Install with: pip install aiohttp")

    params = context['params']
    url = params['url']
    message = params['message']
    title = params.get('title')
    chat_id = params.get('chat_id')

    # Validate URL against SSRF attacks
    try:
        validate_url_with_env_config(url)
    except SSRFError as e:
        logger.warning(f"SSRF protection blocked notification to: {url}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SSRF_BLOCKED',
            'platform': 'unknown',
            'status_code': 0
        }

    # Detect platform
    platform = detect_platform(url)
    logger.info(f"Detected notification platform: {platform}")

    # Build payload
    extra = {}
    if chat_id:
        extra['chat_id'] = chat_id

    payload = build_payload(platform, message, title, extra)

    # Send request
    headers = {'Content-Type': 'application/json'}
    timeout = aiohttp.ClientTimeout(total=30)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                status_code = response.status

                try:
                    response_body = await response.json()
                except Exception:
                    response_body = await response.text()

                ok = status_code < 400

                if ok:
                    logger.info(f"Notification sent via {platform}: {status_code}")
                else:
                    logger.warning(f"Notification failed via {platform}: {status_code} - {response_body}")

                return {
                    'ok': ok,
                    'platform': platform,
                    'status_code': status_code,
                    'response': response_body
                }

    except aiohttp.ClientError as e:
        logger.error(f"Notification request failed: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'REQUEST_FAILED',
            'platform': platform,
            'status_code': 0
        }
    except Exception as e:
        logger.error(f"Unexpected error sending notification: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'UNKNOWN_ERROR',
            'platform': platform,
            'status_code': 0
        }
