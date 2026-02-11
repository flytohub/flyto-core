"""
Webhook Presets / Email Presets / Slack Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def WEBHOOK_URL(
    *,
    key: str = "url",
    required: bool = True,
    placeholder: str = "https://example.com/webhook",
    label: str = "Webhook URL",
    label_key: str = "schema.field.webhook_url",
) -> Dict[str, Dict[str, Any]]:
    """Webhook URL."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Target webhook URL',
        group=FieldGroup.BASIC,
    )


def WEBHOOK_PAYLOAD(
    *,
    key: str = "payload",
    required: bool = False,
    label: str = "Payload",
    label_key: str = "schema.field.webhook_payload",
) -> Dict[str, Dict[str, Any]]:
    """Webhook payload."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        description='JSON payload to send',
        group=FieldGroup.OPTIONS,
    )


def WEBHOOK_AUTH_TOKEN(
    *,
    key: str = "auth_token",
    required: bool = False,
    label: str = "Auth Token",
    label_key: str = "schema.field.webhook_auth_token",
) -> Dict[str, Dict[str, Any]]:
    """Webhook bearer auth token."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        secret=True,
        description='Bearer token for authorization',
        group=FieldGroup.CONNECTION,
    
        placeholder='Bearer your-token',
)

def EMAIL_TO(
    *,
    key: str = "to",
    required: bool = True,
    placeholder: str = "recipient@example.com",
    label: str = "To",
    label_key: str = "schema.field.email_to",
) -> Dict[str, Dict[str, Any]]:
    """Email recipient."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Recipient email address(es), comma-separated for multiple',
        group=FieldGroup.BASIC,
    )


def EMAIL_SUBJECT(
    *,
    key: str = "subject",
    required: bool = True,
    label: str = "Subject",
    label_key: str = "schema.field.email_subject",
) -> Dict[str, Dict[str, Any]]:
    """Email subject."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Email subject line',
        group=FieldGroup.BASIC,
    
        placeholder='Email Subject',
)


def EMAIL_BODY(
    *,
    key: str = "body",
    required: bool = True,
    label: str = "Body",
    label_key: str = "schema.field.email_body",
) -> Dict[str, Dict[str, Any]]:
    """Email body content."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        multiline=True,
        description='Email body content',
        group=FieldGroup.BASIC,
    
        placeholder='Email body content...',
)


def EMAIL_HTML(
    *,
    key: str = "html",
    default: bool = False,
    label: str = "HTML Format",
    label_key: str = "schema.field.email_html",
) -> Dict[str, Dict[str, Any]]:
    """Send as HTML email."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Send as HTML email',
        group=FieldGroup.OPTIONS,
    )


def EMAIL_FROM(
    *,
    key: str = "from_email",
    required: bool = False,
    label: str = "From",
    label_key: str = "schema.field.email_from",
) -> Dict[str, Dict[str, Any]]:
    """Sender email address."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Sender email (uses SMTP_FROM_EMAIL env if not provided)',
        group=FieldGroup.OPTIONS,
    
        placeholder='sender@example.com',
)


def EMAIL_CC(
    *,
    key: str = "cc",
    required: bool = False,
    label: str = "CC",
    label_key: str = "schema.field.email_cc",
) -> Dict[str, Dict[str, Any]]:
    """Email CC recipients."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='CC recipients, comma-separated',
        group=FieldGroup.OPTIONS,
    
        placeholder='cc@example.com',
)


def EMAIL_BCC(
    *,
    key: str = "bcc",
    required: bool = False,
    label: str = "BCC",
    label_key: str = "schema.field.email_bcc",
) -> Dict[str, Dict[str, Any]]:
    """Email BCC recipients."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='BCC recipients, comma-separated',
        group=FieldGroup.OPTIONS,
    
        placeholder='bcc@example.com',
)


def EMAIL_ATTACHMENTS(
    *,
    key: str = "attachments",
    required: bool = False,
    label: str = "Attachments",
    label_key: str = "schema.field.email_attachments",
) -> Dict[str, Dict[str, Any]]:
    """Email file attachments."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        default=[],
        required=required,
        description='List of file paths to attach',
        group=FieldGroup.OPTIONS,
    )


def SMTP_HOST(
    *,
    key: str = "smtp_host",
    required: bool = False,
    placeholder: str = "${env.SMTP_HOST}",
    label: str = "SMTP Host",
    label_key: str = "schema.field.smtp_host",
) -> Dict[str, Dict[str, Any]]:
    """SMTP server host."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='SMTP server host (uses SMTP_HOST env if not provided)',
        group=FieldGroup.CONNECTION,
    )


def SMTP_PORT(
    *,
    key: str = "smtp_port",
    default: int = 587,
    label: str = "SMTP Port",
    label_key: str = "schema.field.smtp_port",
) -> Dict[str, Dict[str, Any]]:
    """SMTP server port."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='SMTP server port (uses SMTP_PORT env if not provided)',
        group=FieldGroup.CONNECTION,
    )


def SMTP_USER(
    *,
    key: str = "smtp_user",
    required: bool = False,
    label: str = "SMTP User",
    label_key: str = "schema.field.smtp_user",
) -> Dict[str, Dict[str, Any]]:
    """SMTP username."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='SMTP username (uses SMTP_USER env if not provided)',
        group=FieldGroup.CONNECTION,
    
        placeholder='user@example.com',
)


def SMTP_PASSWORD(
    *,
    key: str = "smtp_password",
    required: bool = False,
    label: str = "SMTP Password",
    label_key: str = "schema.field.smtp_password",
) -> Dict[str, Dict[str, Any]]:
    """SMTP password."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        secret=True,
        description='SMTP password (uses SMTP_PASSWORD env if not provided)',
        group=FieldGroup.CONNECTION,
    
        placeholder='********',
)


def USE_TLS(
    *,
    key: str = "use_tls",
    default: bool = True,
    label: str = "Use TLS",
    label_key: str = "schema.field.use_tls",
) -> Dict[str, Dict[str, Any]]:
    """Use TLS encryption."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Use TLS encryption',
        group=FieldGroup.OPTIONS,
    )


def IMAP_HOST(
    *,
    key: str = "imap_host",
    required: bool = False,
    placeholder: str = "${env.IMAP_HOST}",
    label: str = "IMAP Host",
    label_key: str = "schema.field.imap_host",
) -> Dict[str, Dict[str, Any]]:
    """IMAP server host."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='IMAP server host',
        group=FieldGroup.CONNECTION,
    )


def IMAP_PORT(
    *,
    key: str = "imap_port",
    default: int = 993,
    label: str = "IMAP Port",
    label_key: str = "schema.field.imap_port",
) -> Dict[str, Dict[str, Any]]:
    """IMAP server port."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='IMAP server port',
        group=FieldGroup.CONNECTION,
    )


def IMAP_USER(
    *,
    key: str = "imap_user",
    required: bool = False,
    label: str = "IMAP User",
    label_key: str = "schema.field.imap_user",
) -> Dict[str, Dict[str, Any]]:
    """IMAP username."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='IMAP username',
        group=FieldGroup.CONNECTION,
    
        placeholder='user@example.com',
)


def IMAP_PASSWORD(
    *,
    key: str = "imap_password",
    required: bool = False,
    label: str = "IMAP Password",
    label_key: str = "schema.field.imap_password",
) -> Dict[str, Dict[str, Any]]:
    """IMAP password."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        secret=True,
        description='IMAP password',
        group=FieldGroup.CONNECTION,
    
        placeholder='********',
)


def EMAIL_FOLDER(
    *,
    key: str = "folder",
    default: str = "INBOX",
    label: str = "Folder",
    label_key: str = "schema.field.email_folder",
) -> Dict[str, Dict[str, Any]]:
    """Email folder/mailbox."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Mailbox folder to read from',
        group=FieldGroup.OPTIONS,
    
        placeholder='INBOX',
)


def EMAIL_LIMIT(
    *,
    key: str = "limit",
    default: int = 10,
    label: str = "Limit",
    label_key: str = "schema.field.email_limit",
) -> Dict[str, Dict[str, Any]]:
    """Email fetch limit."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Maximum number of emails to fetch',
        group=FieldGroup.OPTIONS,
    )


def EMAIL_UNREAD_ONLY(
    *,
    key: str = "unread_only",
    default: bool = False,
    label: str = "Unread Only",
    label_key: str = "schema.field.email_unread_only",
) -> Dict[str, Dict[str, Any]]:
    """Only fetch unread emails."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Only fetch unread emails',
        group=FieldGroup.OPTIONS,
    )


def EMAIL_SINCE_DATE(
    *,
    key: str = "since_date",
    required: bool = False,
    label: str = "Since Date",
    label_key: str = "schema.field.email_since_date",
) -> Dict[str, Dict[str, Any]]:
    """Fetch emails since date."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Fetch emails since this date (YYYY-MM-DD)',
        group=FieldGroup.OPTIONS,
    
        placeholder='2024-01-01',
)


def EMAIL_FROM_FILTER(
    *,
    key: str = "from_filter",
    required: bool = False,
    label: str = "From Filter",
    label_key: str = "schema.field.email_from_filter",
) -> Dict[str, Dict[str, Any]]:
    """Filter by sender email."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Filter by sender email address',
        group=FieldGroup.OPTIONS,
    
        placeholder='sender@example.com',
)


def EMAIL_SUBJECT_FILTER(
    *,
    key: str = "subject_filter",
    required: bool = False,
    label: str = "Subject Filter",
    label_key: str = "schema.field.email_subject_filter",
) -> Dict[str, Dict[str, Any]]:
    """Filter by subject."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Filter by subject (contains)',
        group=FieldGroup.OPTIONS,
    
        placeholder='keyword',
)

def SLACK_MESSAGE(
    *,
    key: str = "message",
    required: bool = True,
    label: str = "Message",
    label_key: str = "schema.field.slack_message",
) -> Dict[str, Dict[str, Any]]:
    """Slack message text."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Message text to send',
        group=FieldGroup.BASIC,
    
        placeholder='Your message here',
)


def SLACK_WEBHOOK_URL(
    *,
    key: str = "webhook_url",
    required: bool = False,
    placeholder: str = "${env.SLACK_WEBHOOK_URL}",
    label: str = "Webhook URL",
    label_key: str = "schema.field.slack_webhook_url",
) -> Dict[str, Dict[str, Any]]:
    """Slack webhook URL."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        secret=True,
        description='Slack incoming webhook URL',
        group=FieldGroup.CONNECTION,
    )


def SLACK_CHANNEL(
    *,
    key: str = "channel",
    required: bool = False,
    label: str = "Channel",
    label_key: str = "schema.field.slack_channel",
) -> Dict[str, Dict[str, Any]]:
    """Slack channel override."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Override channel (optional)',
        group=FieldGroup.OPTIONS,
    
        placeholder='#general',
)


def SLACK_USERNAME(
    *,
    key: str = "username",
    required: bool = False,
    label: str = "Username",
    label_key: str = "schema.field.slack_username",
) -> Dict[str, Dict[str, Any]]:
    """Slack bot username override."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Override bot username',
        group=FieldGroup.OPTIONS,
    
        placeholder='Bot',
)


def SLACK_ICON_EMOJI(
    *,
    key: str = "icon_emoji",
    required: bool = False,
    placeholder: str = ":robot_face:",
    label: str = "Icon Emoji",
    label_key: str = "schema.field.slack_icon_emoji",
) -> Dict[str, Dict[str, Any]]:
    """Slack bot icon emoji."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Emoji to use as icon (e.g., :robot_face:)',
        group=FieldGroup.OPTIONS,
    )


def SLACK_BLOCKS(
    *,
    key: str = "blocks",
    required: bool = False,
    label: str = "Blocks",
    label_key: str = "schema.field.slack_blocks",
) -> Dict[str, Dict[str, Any]]:
    """Slack Block Kit blocks."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Slack Block Kit blocks for rich formatting',
        group=FieldGroup.OPTIONS,
    )


def SLACK_ATTACHMENTS(
    *,
    key: str = "attachments",
    required: bool = False,
    label: str = "Attachments",
    label_key: str = "schema.field.slack_attachments",
) -> Dict[str, Dict[str, Any]]:
    """Slack message attachments."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Message attachments',
        group=FieldGroup.OPTIONS,
    )


# ============== Notification Presets ==============

def NOTIFY_URL(
    *,
    key: str = "url",
    required: bool = True,
    placeholder: str = "https://api.telegram.org/bot<TOKEN>/sendMessage",
    label: str = "Webhook URL",
    label_key: str = "schema.field.notify_url",
) -> Dict[str, Dict[str, Any]]:
    """Notification webhook URL (auto-detects platform)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        secret=True,
        description='Webhook URL for Telegram, Discord, Slack, LINE, or custom',
        group=FieldGroup.BASIC,
    )


def NOTIFY_MESSAGE(
    *,
    key: str = "message",
    required: bool = True,
    placeholder: str = "Hello from Flyto!",
    label: str = "Message",
    label_key: str = "schema.field.notify_message",
) -> Dict[str, Dict[str, Any]]:
    """Notification message content."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        multiline=True,
        description='Notification message content',
        group=FieldGroup.BASIC,
    )


def NOTIFY_TITLE(
    *,
    key: str = "title",
    required: bool = False,
    placeholder: str = "Alert",
    label: str = "Title",
    label_key: str = "schema.field.notify_title",
) -> Dict[str, Dict[str, Any]]:
    """Optional notification title."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Optional title (for Discord, Slack, Teams)',
        group=FieldGroup.OPTIONS,
    )


def TELEGRAM_CHAT_ID(
    *,
    key: str = "chat_id",
    required: bool = False,
    placeholder: str = "123456789",
    label: str = "Chat ID",
    label_key: str = "schema.field.telegram_chat_id",
) -> Dict[str, Dict[str, Any]]:
    """Telegram chat ID."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Telegram chat ID (required for Telegram)',
        group=FieldGroup.OPTIONS,
    )
