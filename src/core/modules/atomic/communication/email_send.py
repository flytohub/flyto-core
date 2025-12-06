"""
Email Send Module
Send emails via SMTP
"""
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Any, Dict, List, Optional

from ...registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='email.send',
    version='1.0.0',
    category='communication',
    subcategory='email',
    tags=['email', 'smtp', 'send', 'notification', 'communication'],
    label='Send Email',
    label_key='modules.email.send.label',
    description='Send email via SMTP server',
    description_key='modules.email.send.description',
    icon='Mail',
    color='#EA4335',

    # Connection types
    input_types=['text', 'object'],
    output_types=['object'],
    can_connect_to=['notification.*'],

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.smtp'],

    params_schema={
        'to': {
            'type': 'string',
            'label': 'To',
            'label_key': 'modules.email.send.params.to.label',
            'description': 'Recipient email address(es), comma-separated for multiple',
            'description_key': 'modules.email.send.params.to.description',
            'required': True,
            'placeholder': 'recipient@example.com'
        },
        'subject': {
            'type': 'string',
            'label': 'Subject',
            'label_key': 'modules.email.send.params.subject.label',
            'description': 'Email subject line',
            'description_key': 'modules.email.send.params.subject.description',
            'required': True
        },
        'body': {
            'type': 'string',
            'label': 'Body',
            'label_key': 'modules.email.send.params.body.label',
            'description': 'Email body content',
            'description_key': 'modules.email.send.params.body.description',
            'required': True
        },
        'html': {
            'type': 'boolean',
            'label': 'HTML Format',
            'label_key': 'modules.email.send.params.html.label',
            'description': 'Send as HTML email',
            'description_key': 'modules.email.send.params.html.description',
            'required': False,
            'default': False
        },
        'from_email': {
            'type': 'string',
            'label': 'From',
            'label_key': 'modules.email.send.params.from_email.label',
            'description': 'Sender email (uses SMTP_FROM_EMAIL env if not provided)',
            'description_key': 'modules.email.send.params.from_email.description',
            'required': False
        },
        'cc': {
            'type': 'string',
            'label': 'CC',
            'label_key': 'modules.email.send.params.cc.label',
            'description': 'CC recipients, comma-separated',
            'description_key': 'modules.email.send.params.cc.description',
            'required': False
        },
        'bcc': {
            'type': 'string',
            'label': 'BCC',
            'label_key': 'modules.email.send.params.bcc.label',
            'description': 'BCC recipients, comma-separated',
            'description_key': 'modules.email.send.params.bcc.description',
            'required': False
        },
        'attachments': {
            'type': 'array',
            'label': 'Attachments',
            'label_key': 'modules.email.send.params.attachments.label',
            'description': 'List of file paths to attach',
            'description_key': 'modules.email.send.params.attachments.description',
            'required': False,
            'default': []
        },
        'smtp_host': {
            'type': 'string',
            'label': 'SMTP Host',
            'label_key': 'modules.email.send.params.smtp_host.label',
            'description': 'SMTP server host (uses SMTP_HOST env if not provided)',
            'description_key': 'modules.email.send.params.smtp_host.description',
            'required': False
        },
        'smtp_port': {
            'type': 'number',
            'label': 'SMTP Port',
            'label_key': 'modules.email.send.params.smtp_port.label',
            'description': 'SMTP server port (uses SMTP_PORT env if not provided)',
            'description_key': 'modules.email.send.params.smtp_port.description',
            'required': False,
            'default': 587
        },
        'smtp_user': {
            'type': 'string',
            'label': 'SMTP User',
            'label_key': 'modules.email.send.params.smtp_user.label',
            'description': 'SMTP username (uses SMTP_USER env if not provided)',
            'description_key': 'modules.email.send.params.smtp_user.description',
            'required': False
        },
        'smtp_password': {
            'type': 'string',
            'label': 'SMTP Password',
            'label_key': 'modules.email.send.params.smtp_password.label',
            'description': 'SMTP password (uses SMTP_PASSWORD env if not provided)',
            'description_key': 'modules.email.send.params.smtp_password.description',
            'required': False,
            'secret': True
        },
        'use_tls': {
            'type': 'boolean',
            'label': 'Use TLS',
            'label_key': 'modules.email.send.params.use_tls.label',
            'description': 'Use TLS encryption',
            'description_key': 'modules.email.send.params.use_tls.description',
            'required': False,
            'default': True
        }
    },
    output_schema={
        'sent': {
            'type': 'boolean',
            'description': 'Whether email was sent successfully'
        },
        'message_id': {
            'type': 'string',
            'description': 'Email message ID'
        },
        'recipients': {
            'type': 'array',
            'description': 'List of recipients'
        }
    },
    examples=[
        {
            'title': 'Send simple email',
            'title_key': 'modules.email.send.examples.basic.title',
            'params': {
                'to': 'user@example.com',
                'subject': 'Hello',
                'body': 'This is a test email.'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def email_send(context: Dict[str, Any]) -> Dict[str, Any]:
    """Send email via SMTP"""
    params = context['params']

    # Get SMTP configuration
    smtp_host = params.get('smtp_host') or os.getenv('SMTP_HOST')
    smtp_port = params.get('smtp_port') or int(os.getenv('SMTP_PORT', '587'))
    smtp_user = params.get('smtp_user') or os.getenv('SMTP_USER')
    smtp_password = params.get('smtp_password') or os.getenv('SMTP_PASSWORD')
    use_tls = params.get('use_tls', True)

    # Validate SMTP config
    if not smtp_host:
        raise ValueError("SMTP host not configured. Set SMTP_HOST env or provide smtp_host param")

    # Get email parameters
    from_email = params.get('from_email') or os.getenv('SMTP_FROM_EMAIL', smtp_user)
    to_emails = [e.strip() for e in params['to'].split(',')]
    cc_emails = [e.strip() for e in params.get('cc', '').split(',')] if params.get('cc') else []
    bcc_emails = [e.strip() for e in params.get('bcc', '').split(',')] if params.get('bcc') else []
    subject = params['subject']
    body = params['body']
    is_html = params.get('html', False)
    attachments = params.get('attachments', [])

    # Build message
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = ', '.join(to_emails)
    msg['Subject'] = subject

    if cc_emails:
        msg['Cc'] = ', '.join(cc_emails)

    # Attach body
    content_type = 'html' if is_html else 'plain'
    msg.attach(MIMEText(body, content_type))

    # Attach files
    for file_path in attachments:
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = os.path.basename(file_path)
                part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                msg.attach(part)

    # All recipients
    all_recipients = to_emails + cc_emails + bcc_emails

    # Send email
    try:
        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)

        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)

        server.sendmail(from_email, all_recipients, msg.as_string())
        message_id = msg.get('Message-ID', '')
        server.quit()

        logger.info(f"Email sent to {len(all_recipients)} recipients")

        return {
            'ok': True,
            'sent': True,
            'message_id': message_id,
            'recipients': all_recipients
        }

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise
