"""
Email Notification Module
Send emails via SMTP.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from ....base import BaseModule
from ....registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='notification.email.send',
    version='1.0.0',
    category='notification',
    tags=['notification', 'email', 'smtp', 'mail'],
    label='Send Email',
    label_key='modules.notification.email.send.label',
    description='Send email via SMTP',
    description_key='modules.notification.email.send.description',
    icon='Mail',
    color='#EA4335',

    # Connection types
    input_types=['text', 'json', 'any'],
    output_types=['api_response'],
    can_receive_from=['data.*', 'api.*', 'string.*', 'utility.*', 'flow.*', 'notification.*'],
    can_connect_to=['*'],  # Notifications can connect to any module

    # Phase 2: Execution settings
    timeout=30,  # SMTP operations should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=2,
    concurrent_safe=True,  # Multiple emails can be sent in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs SMTP credentials
    handles_sensitive_data=True,  # Email content may be sensitive
    required_permissions=['network.access'],

    params_schema={
        'smtp_server': {
            'type': 'string',
            'label': 'SMTP Server',
            'description': 'SMTP server hostname (e.g., smtp.gmail.com)',
            'placeholder': '${env.SMTP_SERVER}',
            'required': True
        },
        'smtp_port': {
            'type': 'number',
            'label': 'SMTP Port',
            'description': 'SMTP port (587 for TLS, 465 for SSL)',
            'default': 587,
            'required': False
        },
        'username': {
            'type': 'string',
            'label': 'Username',
            'description': 'SMTP username',
            'placeholder': '${env.SMTP_USERNAME}',
            'required': True
        },
        'password': {
            'type': 'string',
            'label': 'Password',
            'description': 'SMTP password (use env variable!)',
            'placeholder': '${env.SMTP_PASSWORD}',
            'required': True,
            'sensitive': True
        },
        'from_email': {
            'type': 'string',
            'label': 'From Email',
            'description': 'Sender email address',
            'placeholder': 'bot@example.com',
            'required': True
        },
        'to_email': {
            'type': 'string',
            'label': 'To Email',
            'description': 'Recipient email address',
            'placeholder': 'user@example.com',
            'required': True
        },
        'subject': {
            'type': 'string',
            'label': 'Subject',
            'description': 'Email subject',
            'placeholder': 'Workflow Alert',
            'required': True
        },
        'body': {
            'type': 'text',
            'label': 'Body',
            'description': 'Email body (HTML supported)',
            'placeholder': 'Your workflow has completed.',
            'required': True
        },
        'html': {
            'type': 'boolean',
            'label': 'HTML Body',
            'description': 'Send body as HTML',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'sent': {'type': 'boolean'},
        'message': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Simple plain text email',
            'params': {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'from_email': 'bot@example.com',
                'to_email': 'user@example.com',
                'subject': 'Workflow Complete',
                'body': 'Your automation workflow has finished successfully.'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class EmailSendModule(BaseModule):
    """Send email via SMTP"""

    module_name = "Send Email"
    module_description = "Send email message via SMTP server"

    def validate_params(self):
        required = ['smtp_server', 'username', 'password', 'from_email', 'to_email', 'subject', 'body']
        for param in required:
            if param not in self.params or not self.params[param]:
                raise ValueError(f"Missing required parameter: {param}")

        self.smtp_server = self.params['smtp_server']
        self.smtp_port = self.params.get('smtp_port', 587)
        self.username = self.params['username']
        self.password = self.params['password']
        self.from_email = self.params['from_email']
        self.to_email = self.params['to_email']
        self.subject = self.params['subject']
        self.body = self.params['body']
        self.html = self.params.get('html', False)

    async def execute(self) -> Any:
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = self.to_email
            msg['Subject'] = self.subject

            # Attach body
            if self.html:
                msg.attach(MIMEText(self.body, 'html'))
            else:
                msg.attach(MIMEText(self.body, 'plain'))

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            return {
                'status': 'success',
                'sent': True,
                'message': f'Email sent successfully to {self.to_email}'
            }

        except Exception as e:
            return {
                'status': 'error',
                'sent': False,
                'message': f'Failed to send email: {str(e)}'
            }
