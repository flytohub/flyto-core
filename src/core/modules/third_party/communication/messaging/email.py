# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Email Notification Module
Send emails via SMTP.

HOW FAR THIS MODULE FOLLOWS REALITY

Two questions, and this module used to answer neither. It catches every
exception and returns ``{'status': 'error', 'sent': False, ...}`` with no ``ok``
key, which ``_execute_single_mode`` passes straight through -- so a rejected
login and a delivered message were both recorded as steps that SUCCEEDED, and
the only thing separating them was a boolean nobody downstream is obliged to
read.

THE HAPPY PATH IS ACCEPTED, and there is a measurement behind it that this
module also used to throw away. `smtplib.SMTP.send_message` returns normally
only after the server has answered the final ``.`` of DATA with a 250, and what
it RETURNS is the map of addresses the server refused at ``RCPT TO`` -- empty
when it took them all. That map is the relay reporting on receipt, in its own
words. Custody, not arrival: a later bounce, a spam filter, a full quota and
greylisting all happen after this call returns, and none of them is visible from
here. So ACCEPTED, never OBSERVED, and never VERIFIED -- no postcondition is
declared and none is evaluated.

THE ERROR PATH SPLITS ON ONE QUESTION: had the message been handed over yet?

    before send_message      Nothing left this process. A DNS failure, a refused
                             connection, a rejected login, a bad MIME part --
                             the mail does not exist anywhere. FAILED.
    a named SMTP refusal     The server rejected the envelope or the data by
                             name: every recipient refused, the sender refused,
                             DATA rejected. Definite, so FAILED.
    anything else, after     A disconnect or a timeout with the message already
                             on the wire. It may have been delivered.
                             INDETERMINATE -- and this is the one that matters,
                             because `retryable=True, max_retries=2` means a
                             timed-out send is retried and a mail that did go
                             out goes out again.

Calling that last case FAILED would be the comfortable answer and the wrong one:
it tells a person nothing was sent when something may have been, which is the
failure mode a workflow author cannot recover from.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List

from ....base import BaseModule
from .....utils import enforce_outbound_host
from ....registry import register_module
from .....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)

#: SMTP errors that name what the server refused, and refuse the whole message.
#: Each one means the server read something and said no to it, so nothing was
#: delivered and nothing is left in doubt. `SMTPRecipientsRefused` is raised only
#: when EVERY recipient was refused; a partial refusal returns normally and is
#: handled on the accepted path.
_DEFINITE_REFUSALS = (
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
    smtplib.SMTPDataError,
    smtplib.SMTPHeloError,
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPConnectError,
    smtplib.SMTPNotSupportedError,
)


def _refusal_detail(refused: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The refusal map from `send_message`, flattened into effect-sized records."""
    records = []
    for address, response in refused.items():
        code, message = (response if isinstance(response, tuple) else (None, response))
        if isinstance(message, bytes):
            message = message.decode('utf-8', errors='replace')
        records.append({'recipient': address, 'code': code, 'response': message})
    return records


def _accepted(to_email: str, refused: Dict[str, Any]) -> Dict[str, Any]:
    """ACCEPTED -- the relay took custody, per recipient.

    The measurement is the refusal map `send_message` returned, which exists
    only because the server answered. A non-empty map beside a ``status:
    'success'`` is a real state: the message was taken for the other addresses
    and these ones will never receive it.
    """
    effects: List[Dict[str, Any]] = [{
        'kind': 'smtp_message_accepted',
        'to': to_email,
        'measured_by': (
            'smtplib.SMTP.send_message returned after the server answered 250 '
            'to DATA, naming no refusal for this address'
            if not refused else
            'smtplib.SMTP.send_message returned; its refusal map is not empty'
        ),
        'detail': (
            'The relay acknowledged taking the message. That is the relay '
            'reporting on its own work; no mailbox is read here.'
        ),
    }]

    if refused:
        effects.append({
            'kind': 'smtp_recipients_refused',
            'refused': _refusal_detail(refused),
            'count': len(refused),
            'measured_by': 'smtplib.SMTP.send_message return value, per recipient',
            'detail': (
                'The server refused these addresses at RCPT TO and took the '
                'message for any others. This step reports success; these '
                'people will not receive it.'
            ),
        })

    effects.append({
        'kind': 'delivery_not_observed',
        'to': to_email,
        'measured_by': None,
        'detail': (
            'Acceptance by a relay is not arrival. A later bounce, a spam '
            'filter, a full quota and greylisting all happen after this call '
            'returns and none of them is visible from here.'
        ),
    })

    return envelope(Outcome.ACCEPTED, claim_by=ClaimBy.NONE, effects=effects)


def _send_failed(error: BaseException, *, handed_over: bool) -> Dict[str, Any]:
    """The off-ladder answer, decided by how far the message had got.

    Not FAILED for everything, which is what a bare ``except Exception`` invites.
    The question the ladder asks here is the retry question, and the answer is
    the difference between a mail that never existed and a mail that may already
    be in somebody's inbox.
    """
    definite = (not handed_over) or isinstance(error, _DEFINITE_REFUSALS)
    return envelope(
        Outcome.FAILED if definite else Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'smtp_send_refused' if definite else 'smtp_send_inconclusive',
            'error_type': type(error).__name__,
            'error': str(error),
            'handed_over': handed_over,
            'measured_by': (
                'the exception raised before smtplib.SMTP.send_message was called'
                if not handed_over else
                'the exception type raised by smtplib, against the refusals that name a stage'
            ),
            'detail': (
                'The message was never handed to a server, or the server '
                'refused it by name. It does not exist anywhere.'
                if definite else
                'The message was already on the wire when this failed. It may '
                'have been delivered; a retry may deliver it a second time.'
            ),
        }],
    )


@register_module(
    module_id='notification.email.send',
    version='1.0.0',
    category='notification',
    tags=['ssrf_protected', 'notification', 'email', 'smtp', 'mail'],
    label='Send Email',
    label_key='modules.notification.email.send.label',
    description='Send email via SMTP',
    description_key='modules.notification.email.send.description',
    icon='Mail',
    color='#EA4335',

    # Connection types
    input_types=['text', 'json', 'any'],
    output_types=['api_response'],
    can_receive_from=['data.*', 'http.*', 'string.*', 'utility.*', 'flow.*', 'notify.*'],
    can_connect_to=['*'],  # Notifications can connect to any module

    # Phase 2: Execution settings
    timeout_ms=30000,  # SMTP operations should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=2,
    concurrent_safe=True,  # Multiple emails can be sent in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD'],
    handles_sensitive_data=True,  # Email content may be sensitive
    required_permissions=['email.send'],

    params_schema={
        'smtp_server': {
            'type': 'string',
            'label': 'SMTP Server',
            'description': 'SMTP server hostname (e.g., smtp.gmail.com)',
                'description_key': 'modules.notification.email.send.params.smtp_server.description',
            'placeholder': '${env.SMTP_SERVER}',
            'required': True
        },
        'smtp_port': {
            'type': 'number',
            'label': 'SMTP Port',
            'description': 'SMTP port (587 for TLS, 465 for SSL)',
                'description_key': 'modules.notification.email.send.params.smtp_port.description',
            'default': 587,
            'required': False
        },
        'username': {
            'type': 'string',
            'label': 'Username',
            'description': 'SMTP username',
                'description_key': 'modules.notification.email.send.params.username.description',
            'placeholder': '${env.SMTP_USERNAME}',
            'required': True
        },
        'password': {
            'type': 'string',
            'label': 'Password',
            'description': 'SMTP password (use env variable!)',
                'description_key': 'modules.notification.email.send.params.password.description',
            'placeholder': '${env.SMTP_PASSWORD}',
            'required': True,
            'sensitive': True
        },
        'from_email': {
            'type': 'string',
            'label': 'From Email',
            'description': 'Sender email address',
                'description_key': 'modules.notification.email.send.params.from_email.description',
            'placeholder': 'alerts@flyto2.com',
            'required': True
        },
        'to_email': {
            'type': 'string',
            'label': 'To Email',
            'description': 'Recipient email address',
                'description_key': 'modules.notification.email.send.params.to_email.description',
            'placeholder': 'team@flyto2.com',
            'required': True
        },
        'subject': {
            'type': 'string',
            'label': 'Subject',
            'description': 'Email subject',
                'description_key': 'modules.notification.email.send.params.subject.description',
            'placeholder': 'Workflow Alert',
            'required': True
        },
        'body': {
            'type': 'text',
            'label': 'Body',
            'description': 'Email body (HTML supported)',
                'description_key': 'modules.notification.email.send.params.body.description',
            'placeholder': 'Your workflow has completed.',
            'required': True
        },
        'html': {
            'type': 'boolean',
            'label': 'HTML Body',
            'description': 'Send body as HTML',
                'description_key': 'modules.notification.email.send.params.html.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.notification.email.send.output.status.description'},
        'sent': {'type': 'boolean', 'description': 'Whether notification was sent',
                'description_key': 'modules.notification.email.send.output.sent.description'},
        'message': {'type': 'string', 'description': 'Result message describing the outcome',
                'description_key': 'modules.notification.email.send.output.message.description'},
        'refused_recipients': {
            'type': 'array',
            'description': (
                'Addresses the server refused at RCPT TO, each with the code and '
                'sentence it gave. Empty on an ordinary send; a non-empty list '
                'alongside sent=true means these people will not receive it'
            ),
            'description_key': 'modules.notification.email.send.output.refused_recipients.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this send was followed: "accepted" when the relay took '
                'custody, "failed" when the message was never handed over or was '
                'refused by name, "indeterminate" when it broke with the message '
                'already on the wire'
            ),
            'description_key': 'modules.notification.email.send.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Simple plain text email',
            'params': {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'from_email': 'alerts@flyto2.com',
                'to_email': 'team@flyto2.com',
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

    def validate_params(self) -> None:
        required = ['smtp_server', 'username', 'password', 'from_email', 'to_email', 'subject', 'body']
        for param in required:
            if param not in self.params or not self.params[param]:
                raise ValueError(f"Missing required parameter: {param}")

        # SECURITY: smtp_server is caller-controlled and smtplib will connect to
        # it, carrying self.username/self.password with it — so an unguarded
        # value both probes internal hosts and hands them SMTP credentials.
        self.smtp_server = enforce_outbound_host(
            self.params['smtp_server'], purpose='SMTP'
        )
        self.smtp_port = self.params.get('smtp_port', 587)
        self.username = self.params['username']
        self.password = self.params['password']
        self.from_email = self.params['from_email']
        self.to_email = self.params['to_email']
        self.subject = self.params['subject']
        self.body = self.params['body']
        self.html = self.params.get('html', False)

    async def execute(self) -> Any:
        # The one bit of state the error path needs: everything before this
        # becomes True is a failure of a message that never existed, and
        # everything after it may be a message already delivered. Without it a
        # bare `except Exception` has no way to tell the two apart, which is
        # what made every failure here look equally final.
        handed_over = False
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
                handed_over = True
                # The return value is the point, not the side effect: smtplib
                # gives back the addresses the server refused at RCPT TO, and
                # returns at all only after a 250 for DATA.
                refused = server.send_message(msg) or {}

            if refused:
                logger.warning(
                    "SMTP server refused %s while accepting the message: %s",
                    sorted(refused), self.to_email,
                )

            return {
                'status': 'success',
                'sent': True,
                'message': f'Email sent successfully to {self.to_email}',
                'refused_recipients': _refusal_detail(refused),
                'outcome': _accepted(self.to_email, refused),
            }

        except Exception as e:
            return {
                'status': 'error',
                'sent': False,
                'message': f'Failed to send email: {str(e)}',
                'refused_recipients': [],
                'outcome': _send_failed(e, handed_over=handed_over),
            }
