# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Email Send Module
Send emails via SMTP

HOW FAR THIS MODULE FOLLOWS REALITY: accepted, and there is a measurement
behind it that this module used to throw away.

`smtplib.SMTP.sendmail` returns normally only after the server has answered the
final `.` of DATA with a 250, and what it RETURNS is the map of recipients the
server refused at `RCPT TO` -- empty when every one was taken. That map is the
peer reporting on receipt, per addressee, in the peer's own words. It is the
whole distance between `dispatched` and `accepted`, and this module discarded
it: `sendmail(...)` was called for its side effect and the result dropped on the
floor, while the payload reported `sent: True` and `recipients: all_recipients`
-- the caller's own input list, which reads identically whether the server took
every address, some of them, or (short of the all-refused exception) whether the
mail is being bounced back as this runs. `recipients` is still returned for
compatibility and is still not evidence; `accepted_recipients` and
`refused_recipients` beside it are.

A PARTIAL REFUSAL IS THE CASE WORTH KNOWING ABOUT. If ALL recipients are
refused, smtplib raises `SMTPRecipientsRefused` and this module re-raises, so
the payload never exists. If SOME are refused, `sendmail` returns normally and
this module -- before and after this change -- reports success. The rung stays
ACCEPTED, because the message genuinely was accepted for the others and calling
that a failure would be false, but the refusal is now named in the envelope AND
in `refused_recipients`, so a consumer that cares can see the people who will
never get it.

IT IS NOT OBSERVED, and the gap is the ordinary one for anything that reaches a
person: nothing here reads a mailbox. A 250 at DATA is the relay saying it has
taken custody. Greylisting, a downstream bounce, a spam filter, a full quota --
all of them happen after this call returns and none of them is visible from
here.

WHAT THIS MODULE CANNOT SAY, and a reader should know it: anything about a
failed send. Every error path re-raises, and a raised exception becomes a
`StepExecutionError` with the payload discarded -- so a timeout mid-DATA, which
is the textbook INDETERMINATE and matters here because `retryable=True,
max_retries=3` means a timed-out send is retried and a mail that did go out can
go out again, carries no envelope at all. Changing that is a change to error and
retry semantics, which is not a declaration's business.
"""
import logging
import os
import smtplib
from contextlib import suppress
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Iterable, List

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import enforce_outbound_host, validate_path_with_env_config
from ...registry import register_module
from ...schema import compose, presets

logger = logging.getLogger(__name__)


def _refusal_detail(refused: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The refusal map from `sendmail`, flattened into effect-sized records.

    smtplib hands back ``{address: (code, message_bytes)}``. The bytes are the
    server's own sentence about why, and they are the most useful thing on this
    path, so they are decoded rather than dropped.
    """
    records = []
    for address, response in refused.items():
        code, message = (response if isinstance(response, tuple) else (None, response))
        if isinstance(message, bytes):
            message = message.decode('utf-8', errors='replace')
        records.append({'recipient': address, 'code': code, 'response': message})
    return records


def _send_outcome(
    *,
    attempted: Iterable[str],
    accepted: List[str],
    refused: Dict[str, Any],
) -> Dict[str, Any]:
    """The rung this send earned, and the one line that earned it.

    ACCEPTED either way, and never higher. The measurement is the refusal map
    `sendmail` returned, which exists only because the server answered: it
    reports which addresses the relay took custody of, and taking a relay's word
    for its own work is the definition of the rung.

    Two shapes, one rung:

    * nothing refused -> the relay took every address this module handed it.
    * something refused -> it took the rest, and the addresses it would not take
      are named. Not FAILED: the message was accepted for everyone else, and
      marking the whole step failed would be as wrong in the other direction as
      the `sent: True` this path used to return on its own.

    What is deliberately absent is any claim about delivery. See the module
    docstring: a 250 at DATA is custody, not arrival.
    """
    effects: List[Dict[str, Any]] = [{
        'kind': 'smtp_recipients_accepted',
        'recipients': accepted,
        'count': len(accepted),
        'measured_by': (
            'the refusal map returned by smtplib.SMTP.sendmail -- these are the '
            'addresses it did NOT name, after the server answered 250 to DATA'
        ),
        'detail': (
            'The relay acknowledged taking the message for these addresses. That '
            'is the relay reporting on its own work; no mailbox is read here.'
        ),
    }]

    if refused:
        effects.append({
            'kind': 'smtp_recipients_refused',
            'refused': _refusal_detail(refused),
            'count': len(refused),
            'measured_by': 'smtplib.SMTP.sendmail return value, per recipient',
            'detail': (
                'The server refused these addresses at RCPT TO and took the '
                'message for the others. This step still reports success, '
                'because for the accepted addresses it is one; these people '
                'will not receive it.'
            ),
        })

    effects.append({
        'kind': 'delivery_not_observed',
        'attempted': list(attempted),
        'measured_by': None,
        'detail': (
            'Nothing here observes delivery. Acceptance by a relay is not '
            'arrival: a later bounce, a spam filter, a full quota and '
            'greylisting all happen after this call returns and none of them '
            'is visible from here.'
        ),
    })

    return envelope(Outcome.ACCEPTED, claim_by=ClaimBy.NONE, effects=effects)


@register_module(
    module_id='email.send',
    stability="beta",
    version='1.0.0',
    category='communication',
    subcategory='email',
    tags=[
        'email', 'smtp', 'send', 'notification', 'communication',
        'ssrf_protected', 'path_restricted',
    ],
    label='Send Email',
    label_key='modules.email.send.label',
    description='Send email via SMTP server',
    description_key='modules.email.send.description',
    icon='Mail',
    color='#EA4335',

    # Connection types
    input_types=['text', 'object'],
    output_types=['object'],
    can_connect_to=['notify.*', 'flow.*', 'data.*', 'string.*', 'object.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=60000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        presets.EMAIL_TO(),
        presets.EMAIL_SUBJECT(),
        presets.EMAIL_BODY(),
        presets.EMAIL_HTML(),
        presets.EMAIL_FROM(),
        presets.EMAIL_CC(),
        presets.EMAIL_BCC(),
        presets.EMAIL_ATTACHMENTS(),
        presets.SMTP_HOST(),
        presets.SMTP_PORT(),
        presets.SMTP_USER(),
        presets.SMTP_PASSWORD(),
        presets.USE_TLS(),
    ),
    output_schema={
        'sent': {
            'type': 'boolean',
            'description': 'Whether email was sent successfully'
        ,
                'description_key': 'modules.email.send.output.sent.description'},
        'message_id': {
            'type': 'string',
            'description': 'Email message ID'
        ,
                'description_key': 'modules.email.send.output.message_id.description'},
        'recipients': {
            'type': 'array',
            'description': (
                'Every address this module handed to the server: to + cc + bcc. '
                'The list that was ATTEMPTED, built from the caller\'s own '
                'parameters -- not a measurement of what the server took. See '
                'accepted_recipients'
            )
        ,
                'description_key': 'modules.email.send.output.recipients.description'},
        'accepted_recipients': {
            'type': 'array',
            'description': (
                'Addresses the server took custody of: the attempted list minus '
                'the ones smtplib.sendmail reported as refused'
            )
        ,
                'description_key': 'modules.email.send.output.accepted_recipients.description'},
        'refused_recipients': {
            'type': 'array',
            'description': (
                'Addresses the server refused at RCPT TO, each with the code and '
                'sentence it gave. Empty on an ordinary send; a non-empty list '
                'alongside sent=true means these people will not receive it'
            )
        ,
                'description_key': 'modules.email.send.output.refused_recipients.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this send was followed into reality. Always "accepted": '
                'the relay acknowledged taking the message, per recipient. '
                'Delivery is not observed'
            )
        ,
                'description_key': 'modules.email.send.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Send simple email',
            'title_key': 'modules.email.send.examples.basic.title',
            'params': {
                'to': 'team@flyto2.com',
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
    smtp_host = enforce_outbound_host(smtp_host, purpose='SMTP')

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
        safe_path = validate_path_with_env_config(file_path)
        if os.path.exists(safe_path):
            with open(safe_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = os.path.basename(safe_path)
                part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                msg.attach(part)

    # All recipients
    all_recipients = to_emails + cc_emails + bcc_emails

    # Send email
    # RELIABILITY: Use try/finally to ensure SMTP connection is always closed
    server = None
    try:
        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)

        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)

        # The return value is the point, not the side effect. smtplib gives back
        # the map of addresses the server refused at RCPT TO -- empty when it
        # took them all -- and returns at all only after a 250 for DATA. It used
        # to be discarded, which left this module with nothing but its own input
        # list to report.
        refused = server.sendmail(from_email, all_recipients, msg.as_string()) or {}
        accepted = [address for address in all_recipients if address not in refused]
        message_id = msg.get('Message-ID', '')

        if refused:
            logger.warning(
                f"Email accepted for {len(accepted)} of {len(all_recipients)} "
                f"recipients; server refused {sorted(refused)}"
            )
        else:
            logger.info(f"Email sent to {len(all_recipients)} recipients")

        return {
            'ok': True,
            'sent': True,
            'message_id': message_id,
            'recipients': all_recipients,
            'accepted_recipients': accepted,
            'refused_recipients': _refusal_detail(refused),
            'outcome': _send_outcome(
                attempted=all_recipients,
                accepted=accepted,
                refused=refused,
            ),
        }

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise
    finally:
        if server:
            with suppress(Exception):
                server.quit()
