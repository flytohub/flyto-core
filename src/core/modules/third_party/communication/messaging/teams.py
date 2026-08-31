# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Microsoft Teams Notification Module
Send notifications to Microsoft Teams via incoming webhook.

HOW FAR THIS MODULE FOLLOWS REALITY, and why 200 is not enough on this one API.

A Teams incoming webhook is the one connector in this group where the status
line alone is not an acknowledgement. The Office 365 connector answers ``200``
with a body of exactly ``1`` when it has taken the card -- and it also answers
``200`` with a body that is an English sentence describing a FAILURE, the
common one being ``Webhook message delivery failed with error: Microsoft Teams
endpoint returned HTTP error 413`` for a card over the size limit. Same status
line, opposite fact.

This module used to test ``response.status == 200`` and return ``status:
'sent'``, which made every one of those failures a green step. The status test
is left exactly as it was -- changing which replies count as an error is a
change to this module's contract with its callers -- but the RUNG now rests on
the body, which is the only thing that distinguishes the two:

    200, body ``1``            ACCEPTED. The connector acknowledged the card.
                               Its report of its own work; no channel is read
                               back, and nobody has seen anything.
    200, body anything else    INDETERMINATE. Teams answers 200 both for
                               acceptance and for a delivery failure it
                               describes in prose, and this module cannot tell
                               which it is looking at. "We cannot say" is the
                               honest answer, and it is `data.status` reading
                               'sent' beside it that makes saying so necessary.
    4xx                        FAILED. Refused by name; nothing was posted.
    anything else              INDETERMINATE. A 5xx broke with the card already
                               in its hands -- and `retryable=True,
                               max_retries=3` means a retry can post it twice.
                               A 202 is the newer Power Automate workflow URL
                               acknowledging, which this module treats as an
                               error; that is a defect, not a fact about the
                               world, and INDETERMINATE is what it is until the
                               status test is fixed.

VERIFIED is unreachable: no postcondition is declared and none is evaluated.

WHERE THE ENVELOPE GOES ON THE ERROR PATHS: inside ``data``, next to ``status``,
even though ``ok: False`` makes `wrap_legacy_result` build an ERROR result and
drop ``data`` on the way out of the step. Attached anyway, for the reason
`dns.lookup` gives for the same shape: the fact is true whether or not a
consumer exists yet, and adding it once one does means the consumer was built
against results that carried nothing.
"""
import logging
from typing import Any, Dict

import aiohttp

from .....engine.outcome import ClaimBy, Outcome, envelope
from .....utils import (
    SSRFError,
    enforce_outbound_url,
    guarded_aiohttp_request,
    guarded_client_session,
)
from ....base import BaseModule
from ....registry import register_module

logger = logging.getLogger(__name__)

#: What an Office 365 connector writes in the body when it accepts a card.
#: The whole body, not a prefix -- a failure body is a sentence, never this.
TEAMS_ACK_BODY = '1'


def _card_accepted(status: int, body: str) -> Dict[str, Any]:
    """ACCEPTED -- the connector wrote its acknowledgement and nothing else."""
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            {
                'kind': 'card_accepted_by_teams',
                'status': status,
                'response': body,
                'measured_by': (
                    f"response.status, and the body being exactly "
                    f"{TEAMS_ACK_BODY!r} -- the connector's acknowledgement"
                ),
                'detail': (
                    'The connector answered with the one body it writes when it '
                    'has taken the card. That is its report of its own work: no '
                    'channel is read back anywhere in this module.'
                ),
            },
            {
                'kind': 'nobody_has_read_it',
                'measured_by': None,
                'detail': (
                    'A posted card is not a read one. Nothing here observes a '
                    'person seeing it, and this rung does not imply one did.'
                ),
            },
        ],
    )


def _answer_inconclusive(status: int, body: str) -> Dict[str, Any]:
    """INDETERMINATE -- a 200 whose body is not the acknowledgement.

    The case this exists for is real and common: a card over the Teams size
    limit comes back ``200`` with ``Webhook message delivery failed with error:
    ... HTTP error 413`` in the body. This module reports that as a successful
    step, because its success test is the status line. The rung is the one
    field that declines to agree -- and it says INDETERMINATE rather than
    FAILED because the same shape also covers a proxy or a newer endpoint
    answering 200 with something else entirely, which may well have worked.
    """
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'teams_answer_not_an_acknowledgement',
            'status': status,
            'response': body[:500],
            'measured_by': f'the response body, against the connector ack {TEAMS_ACK_BODY!r}',
            'detail': (
                'Teams answered 200 without writing its acknowledgement. It '
                'answers 200 both when it takes a card and when it refuses one '
                'in prose -- a card over the size limit is the usual reason -- '
                'so whether anything reached the channel cannot be told from '
                'here. The step still reports success; this rung does not.'
            ),
        }],
    )


def _post_refused(status: int, body: str) -> Dict[str, Any]:
    """The off-ladder answer for a reply that was not a 200 at all.

    FAILED for a 4xx: Teams read the request, rejected it by name and posted
    nothing, which is definite. INDETERMINATE for everything else -- a 5xx
    broke with the card already taken off the wire, and a 202 is the newer
    Power Automate workflow endpoint acknowledging a card this module then
    reports as an error.
    """
    definite = 400 <= status < 500
    return envelope(
        Outcome.FAILED if definite else Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'webhook_refused_by_teams' if definite else 'webhook_answer_inconclusive',
            'status': status,
            'response': body[:500],
            'measured_by': 'response.status, against the 200 this module accepts',
            'detail': (
                'Teams answered and named a reason; nothing was posted.'
                if definite else
                'Teams did not answer 200, and the request was already in its '
                'hands. A 5xx may still have posted the card; a 202 is the '
                'newer workflow endpoint accepting one. Neither is knowable '
                'from the status line alone.'
            ),
        }],
    )


def _blocked(reason: str, *, before_request: bool) -> Dict[str, Any]:
    """The SSRF guard tripping -- two different facts under one exception type.

    Before the request nothing left this process: FAILED. From inside
    `guarded_aiohttp_request` the POST already went out and a server answered
    with a redirect the guard would not follow, so what that server did with the
    body first is unknown: INDETERMINATE.
    """
    return envelope(
        Outcome.FAILED if before_request else Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'blocked_by_ssrf_guard',
            'reason': reason,
            'measured_by': (
                'enforce_outbound_url, before any socket was opened'
                if before_request else
                'the SSRF guard re-run on a redirect hop, inside guarded_aiohttp_request'
            ),
            'detail': (
                'The request was refused before it left this process. Nothing '
                'was sent anywhere.'
                if before_request else
                'The POST left and a server answered it with a redirect into '
                'blocked space. What that server did with the body before '
                'redirecting is not knowable here.'
            ),
        }],
    )


@register_module(
    module_id='notification.teams.send_message',
    version='1.0.0',
    category='notification',
    tags=['notification', 'teams', 'microsoft', 'messaging', 'webhook'],
    label='Send Teams Message',
    label_key='modules.notification.teams.send_message.label',
    description='Send message to Microsoft Teams via incoming webhook',
    description_key='modules.notification.teams.send_message.description',
    icon='MessageSquare',
    color='#6264A7',

    # Connection types
    input_types=['text', 'json', 'any'],
    output_types=['api_response'],
    can_receive_from=['data.*', 'http.*', 'string.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'flow.*', 'notify.*', 'end'],

    # Phase 2: Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['TEAMS_WEBHOOK_URL'],
    handles_sensitive_data=True,
    required_permissions=['network.access'],

    params_schema={
        'webhook_url': {
            'type': 'string',
            'label': 'Webhook URL',
            'description': 'Microsoft Teams incoming webhook URL',
            'description_key': 'modules.notification.teams.send_message.params.webhook_url.description',
            'placeholder': 'https://outlook.office.com/webhook/...',
            'required': True
        },
        'message': {
            'type': 'text',
            'label': 'Message',
            'description': 'The message text to send',
            'description_key': 'modules.notification.teams.send_message.params.message.description',
            'placeholder': 'Hello from Flyto2!',
            'required': True
        },
        'title': {
            'type': 'string',
            'label': 'Title',
            'description': 'Message card title (optional)',
            'description_key': 'modules.notification.teams.send_message.params.title.description',
            'placeholder': 'Notification',
            'required': False
        },
        'color': {
            'type': 'string',
            'label': 'Theme Color',
            'description': 'Theme color hex code (optional)',
            'description_key': 'modules.notification.teams.send_message.params.color.description',
            'placeholder': '#6264A7',
            'required': False
        },
        'sections': {
            'type': 'array',
            'label': 'Sections',
            'description': 'Additional MessageCard sections (optional)',
            'description_key': 'modules.notification.teams.send_message.params.sections.description',
            'required': False
        }
    },
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether the operation succeeded'},
        'data': {
            'type': 'object',
            'description': (
                'Response data with status, webhook_url, and outcome. `status` '
                'is decided by the status line alone; `outcome` is decided by '
                'the body, which is the only thing that separates a Teams 200 '
                'that took the card from a Teams 200 that refused it in prose'
            )
        }
    },
    examples=[
        {
            'name': 'Simple notification',
            'params': {
                'webhook_url': 'https://outlook.office.com/webhook/...',
                'message': 'Deployment completed successfully!',
                'title': 'Deploy Status',
                'color': '#00FF00'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class TeamsSendMessageModule(BaseModule):
    """Send message to Microsoft Teams via incoming webhook"""

    module_name = "Send Teams Message"
    module_description = "Send message to Microsoft Teams channel via incoming webhook URL"

    def validate_params(self) -> None:
        if 'webhook_url' not in self.params or not self.params['webhook_url']:
            raise ValueError(
                "Missing required parameter: webhook_url. "
                "Get webhook URL from Teams channel -> Connectors -> Incoming Webhook"
            )

        if 'message' not in self.params or not self.params['message']:
            raise ValueError("Missing required parameter: message")

        self.webhook_url = self.params['webhook_url']
        self.message = self.params['message']
        self.title = self.params.get('title')
        self.color = self.params.get('color')
        self.sections = self.params.get('sections')

    async def execute(self) -> Any:
        # SECURITY: gate the client-controlled webhook URL through the SSRF guard
        # (GHSA-pgwh-4jj4-qm8v) — prevents posting to internal/metadata endpoints.
        try:
            enforce_outbound_url(self.webhook_url)
        except SSRFError as e:
            return {
                'ok': False,
                'data': {
                    'status': 'error',
                    'message': f'SSRF protection blocked request: {e}',
                    'outcome': _blocked(str(e), before_request=True),
                },
                'error_code': 'SSRF_BLOCKED',
            }

        # Build Teams MessageCard payload
        payload = {
            '@type': 'MessageCard',
            '@context': 'http://schema.org/extensions',
            'summary': self.title or self.message[:50],
            'text': self.message
        }

        if self.title:
            payload['title'] = self.title

        if self.color:
            # Strip '#' if present for themeColor
            payload['themeColor'] = self.color.lstrip('#')

        if self.sections:
            payload['sections'] = self.sections

        # Send to Teams webhook
        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        try:
            async with guarded_client_session(timeout=timeout) as session:
                response = await guarded_aiohttp_request(
                    session,
                    'POST',
                    self.webhook_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                )
                try:
                    if response.status == 200:
                        # The body, not the status line, is what says whether
                        # Teams took the card -- see the module docstring. Read
                        # on this path so the rung has something to rest on;
                        # `status` stays 'sent' either way, because changing
                        # which replies are errors is a contract change.
                        body = (await response.text() or '').strip()
                        accepted = body == TEAMS_ACK_BODY
                        if not accepted:
                            logger.warning(
                                "Teams answered 200 without its acknowledgement "
                                "body; the card may not have been posted: %r",
                                body[:200],
                            )
                        return {
                            'ok': True,
                            'data': {
                                'status': 'sent',
                                'webhook_url': self.webhook_url,
                                'outcome': (
                                    _card_accepted(response.status, body)
                                    if accepted
                                    else _answer_inconclusive(response.status, body)
                                ),
                            }
                        }
                    error_text = await response.text()
                    return {
                        'ok': False,
                        'data': {
                            'status': 'error',
                            'message': f'Failed to send message: HTTP {response.status} - {error_text}',
                            'outcome': _post_refused(response.status, error_text),
                        }
                    }
                finally:
                    response.release()
        except SSRFError as e:
            # Reachable only from inside `guarded_aiohttp_request`: the initial
            # URL already passed `enforce_outbound_url` above, so the guard that
            # trips here is the one re-run on a redirect hop -- the POST left.
            return {
                'ok': False,
                'data': {
                    'status': 'error',
                    'message': f'SSRF protection blocked request: {e}',
                    'outcome': _blocked(str(e), before_request=False),
                },
                'error_code': 'SSRF_BLOCKED',
            }
