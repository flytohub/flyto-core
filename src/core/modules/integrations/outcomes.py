# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""How far an `integration.*` call was followed, in the terms `APIResponse` allows.

Every module under `integrations/` reaches the network through one method --
`base/client.py::BaseIntegration._request` -- and receives back one
`APIResponse`. So the evidence available to all seven of them is the same three
fields, and the rung each can claim follows from those and nothing else:

    response.status   the status line of the reply to THIS request, or a
                      literal 0 written in `_request` when no reply ever
                      arrived. The 0 is the important one: it is not a status,
                      it is the absence of one, and it is the difference
                      between "the peer refused" and "nobody said".
    response.ok       `status < 400`, except for Slack, which answers HTTP 200
                      with `{"ok": false}` in the body and overrides
                      `_response_is_ok` to read it.
    response.data     the parsed body, which is the peer describing its own
                      work.

THE CEILING ON EVERY SUCCESSFUL PATH IS ACCEPTED, for the reason
`third_party/developer/github.py` gives for GitHub and `http.request` settled
for every 2xx in this product: one request goes out, the reply to that same
request comes back, and nothing reads anything a second time. A 201 naming an
issue Jira says it just created is Jira reporting on its own work. Reaching
OBSERVED would take a second request -- a GET of the thing just written -- and
none of these modules makes one.

ACCEPTED is still worth attaching, because the alternative is not OBSERVED, it
is DISPATCHED: what the engine stamps on a module that says nothing, and what
all seven said before this change. "The instruction left us and nobody
confirmed anything" is untrue of a call that came back 201 with a
server-assigned key in it.

WHERE THE GROUP SPLITS IS THE ERROR PATH, and the split is exactly the retry
question:

    read, any non-2xx or no reply            FAILED
        A GET that was refused returned no data and altered nothing on either
        side. Nothing is left in doubt about the world -- only about data we do
        not have. Same shape, same answer as `github._read_refused`.

    mutation, the peer named a refusal       FAILED
        4xx, or Slack's HTTP 200 carrying `{"ok": false, "error": ...}`. The
        peer read the request, rejected it by name, and changed nothing.

    mutation, 5xx or no reply at all         INDETERMINATE
        The peer took the request off the wire and did not say what it did
        with it. The issue, record or message may exist. Calling this FAILED
        would be the more comfortable answer and the wrong one: it tells a
        person nothing happened when something may have, which is the failure
        mode a workflow author cannot recover from.

A NOTE ON `status == 0`, because it hides a multiplier. `_request` retries up
to `config.max_retries` times on `aiohttp.ClientError`, and re-sends on every
HTTP 429, before giving up and returning `status=0`. Each of those attempts is
a POST that may have reached the server. So a status of 0 on a mutation is not
one uncertain write, it is up to three of them, and any module the engine also
retries (`retryable=True`) multiplies that again.

These envelopes are attached to `ok: False` returns as well, even though
`wrap_legacy_result` turns those into an ERROR result and discards `data` on
the way out of the step. `atomic/dns/lookup.py` states the reason: the fact is
true whether or not a consumer exists yet, and adding it only once a consumer
exists means the consumer is built against results that carry nothing.
"""

from typing import Any, Dict, Optional

from ...engine.outcome import ClaimBy, Outcome, envelope


def peer_answered(service: str, status: int) -> Dict[str, Any]:
    """The one thing every successful path in this family measures.

    A server received the request, processed it far enough to choose a reply,
    and sent one. That is the whole distance between DISPATCHED and ACCEPTED,
    and -- since nothing here reads anything back -- the whole distance any of
    these modules travels.

    `status == 0` gets the OPPOSITE effect, and the branch is not a nicety. A
    0 is the literal `_request` writes after every attempt failed; saying "a
    server chose a reply" beside it would be this file committing the exact
    error it exists to catch -- a sentence about the world that is false, in
    the field a reader goes to when the rung is not enough.
    """
    if not status:
        return {
            'kind': f'{service}_no_reply',
            'service': service,
            'status': 0,
            'measured_by': (
                'APIResponse.status -- a literal 0, written by '
                'BaseIntegration._request when every attempt failed'
            ),
            'detail': (
                'No reply was read. The 0 beside this is not a status line, it is '
                'the absence of one: the client exhausted its attempts without '
                f'{service} answering any of them.'
            ),
        }
    return {
        'kind': f'{service}_reply_read',
        'service': service,
        'status': status,
        'measured_by': 'APIResponse.status -- the status line of the reply to this request',
        'detail': (
            'A server received this request and chose a reply. That is what '
            f'separates accepted from dispatched, and it is all it separates: no {service} '
            'state is read back anywhere in this module.'
        ),
    }


def read_refused(
    *,
    service: str,
    status: int,
    resource: str,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """FAILED -- a read that did not come back returned nothing and changed nothing.

    FAILED rather than INDETERMINATE, and the second axis in
    `engine/outcome.py` is what decides it: INDETERMINATE is for when we cannot
    say. Here we can. A read alters nothing on either side, so no effect is
    left in doubt -- there is only data we do not have. That holds for
    `status == 0` too: no reply arrived, so no data did.
    """
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[
            peer_answered(service, status),
            {
                'kind': f'{service}_read_refused',
                'resource': resource,
                'status': status,
                'error': error,
                'measured_by': 'APIResponse.status and APIResponse.ok',
                'detail': (
                    f'No {resource} was returned. '
                    + (
                        'No reply arrived at all -- the client exhausted its '
                        'attempts and wrote a literal 0 where a status would be.'
                        if status == 0 else
                        f'{service} answered and refused the read.'
                    )
                    + ' A read changes nothing, so nothing is left uncertain: this '
                    'did not happen. What is missing is data, not certainty.'
                ),
            },
        ],
    )


def mutation_unconfirmed(
    *,
    service: str,
    status: int,
    operation: str,
    error: Optional[str] = None,
    retry_note: Optional[str] = None,
) -> Dict[str, Any]:
    """The off-ladder answer for a write that did not come back confirmed.

    The split `http.request` makes between a refused request and one that
    vanished, moved onto `APIResponse`:

        4xx, or a 2xx whose body named an error (Slack)
            The peer read the request, rejected it by name, and changed
            nothing. Definite, so FAILED.
        5xx
            The peer broke while handling a write it had already taken off the
            wire. The thing may exist. INDETERMINATE.
        status == 0
            No reply at all, after up to `max_retries` attempts each of which
            may have reached the server. INDETERMINATE, and the one most
            likely to have happened more than once.
    """
    definite = 0 < status < 500
    detail = (
        f'{service} rejected this request by name and performed no {operation}.'
        if definite else
        (
            f'{service} took this request off the wire and did not confirm what it '
            f'did with it, so the {operation} may or may not have happened.'
            if status else
            f'No reply arrived for this {operation}. The client exhausted its '
            'attempts and wrote a literal 0 where a status would be; each of '
            'those attempts was a request that may have reached the server.'
        )
    )
    if retry_note and not definite:
        detail = f'{detail} {retry_note}'

    return envelope(
        Outcome.FAILED if definite else Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[
            peer_answered(service, status),
            {
                'kind': (
                    f'{service}_{operation}_rejected' if definite
                    else f'{service}_{operation}_unconfirmed'
                ),
                'operation': operation,
                'status': status,
                'error': error,
                'measured_by': 'APIResponse.status and APIResponse.ok',
                'detail': detail,
            },
        ],
    )
