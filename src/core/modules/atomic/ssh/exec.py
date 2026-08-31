# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
SSH Execute Module
Execute commands on remote servers via SSH

HOW FAR THIS MODULE FOLLOWS REALITY

`shell.exec` settled the hard part of this already: a process exit code read
after the process ended is a real measurement, and `ceiling_for`'s own docstring
names it as the example of an honest OBSERVED. An exit status arriving over an
SSH channel is the same fact with a network in the middle -- it is not the peer
reporting on its own work the way a 2xx is, it is the remote sshd relaying the
status of the process the caller asked for. So the rungs follow `shell.exec`'s:

    exit status reported, and it is 0        OBSERVED
    exit status reported, and it is not 0    INDETERMINATE
        Because the command failing is not the same as nothing happening. A
        `systemctl restart nginx` that exits 1 may have stopped nginx and failed
        to start it; "it worked" and "nothing happened" are both unsupportable,
        which is what this rung is for. claim_by is INFERRED: no caller stated
        that exit 0 was required, and plenty of useful commands exit non-zero on
        purpose.
    no exit status reported at all           INDETERMINATE
    the command timed out                    INDETERMINATE
    the connection dropped after it was sent INDETERMINATE
    authentication failed                    FAILED
    the connection never came up             FAILED
    no credentials were supplied             FAILED

One thing is different here and worth naming, because it makes the rung carry
more weight than it does in `shell.exec`: this module returns `ok: True` for
every exit status. A remote command that exited 137 comes back as a success with
a number in it. The envelope is therefore the ONLY place the distinction between
"the command ran and reported success" and "the command ran and reported
failure" is stated at all.

A BUG THIS FOUND, not fixed here because the fix is not additive. The line
`exit_code = result.exit_status or 0` turns a `None` -- which is what asyncssh
gives when the channel closed without the remote sending an exit status -- into
a literal 0, and that 0 is returned beside `ok: True`. A severed connection is
rendered as a clean success, and no consumer can tell it from one. Changing the
field would change its type from int to None for existing callers, so what is
added is `exit_status_reported`, and the rung drops to INDETERMINATE whenever it
is False. The `or 0` should still go.

Everything above the run is a FAILED, and the flag that decides it is
`command_sent`. `asyncssh.connect` and `conn.run` raise overlapping exception
types -- an `OSError` is a dead host at connect time and a dropped TCP session
mid-command -- and one `except` clause cannot tell them apart after the fact.
The flag can, because it is set immediately before the run is awaited. This is
the same device `shell.exec` uses with `spawned`, and it is the difference
between "retry is safe" and "retry may run this twice".
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import enforce_outbound_host
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


logger = logging.getLogger(__name__)


def _run_outcome(
    *,
    host: str,
    command: str,
    exit_status: Optional[int],
    stdout_len: int,
    stderr_len: int,
) -> Dict[str, Any]:
    """The rung for a command that ran to a return. Three cases; see the docstring."""
    if exit_status is None:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'ssh_exit_status_missing',
                'host': host,
                'measured_by': None,
                'detail': (
                    'The channel closed without the remote sending an exit '
                    'status, so how the command ended -- or whether it finished '
                    'at all -- is not known. The exit_code of 0 beside this is a '
                    'default written by the module, not a status; '
                    'exit_status_reported is the field that says so.'
                ),
            }],
        )

    ran_effect = {
        'kind': 'ssh_command_completed',
        'host': host,
        'exit_status': exit_status,
        'stdout_bytes': stdout_len,
        'stderr_bytes': stderr_len,
        'measured_by': (
            'exit status the remote sshd sent on the channel when the process '
            'ended'
        ),
        'detail': (
            'The command ran on the remote host and terminated, and this is the '
            'status it terminated with. It is not an observation of what the '
            'command DID: nothing here looks at the remote system afterwards, '
            'and an exit 0 from a script that changed nothing reaches this line '
            'identically.'
        ),
    }

    if exit_status == 0:
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=[ran_effect])

    return envelope(
        Outcome.INDETERMINATE,
        # INFERRED: "exit 0 means it worked" is this module's reading, not a
        # contract any caller stated -- and `ok` stays True on this path, so
        # nobody's expectation was adjudicated either.
        claim_by=ClaimBy.INFERRED,
        effects=[
            ran_effect,
            {
                'kind': 'ssh_nonzero_exit',
                'host': host,
                'exit_status': exit_status,
                'measured_by': 'the reported exit status, compared against 0',
                'detail': (
                    'The command reported failure. That is not the same as '
                    'nothing having happened -- a restart that stops a service '
                    'and fails to start it exits non-zero having changed the '
                    'host -- so neither "it worked" nor "it did not" is '
                    'supportable. Note that ok is True regardless of this: the '
                    'rung is the only place the failure is stated.'
                ),
            },
        ],
    )


def _connection_outcome(
    *,
    host: str,
    kind: str,
    detail: str,
    command_sent: bool,
    **fields: Any,
) -> Dict[str, Any]:
    """The rung for an exception, decided by whether the command had left us.

    FAILED before the command was sent -- nothing reached the remote, and a
    retry cannot double anything. INDETERMINATE after: the command may have run
    to completion with the answer lost on the way back, which is precisely the
    case where a blind retry runs it twice.
    """
    return envelope(
        Outcome.INDETERMINATE if command_sent else Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[dict(
            {
                'kind': kind,
                'host': host,
                'command_sent': command_sent,
                'measured_by': None,
                'detail': detail,
            },
            **fields,
        )],
    )


@register_module(
    module_id='ssh.exec',
    version='1.0.0',
    category='atomic',
    subcategory='ssh',
    tags=['ssh', 'remote', 'command', 'devops'],
    label='SSH Execute',
    label_key='modules.ssh.exec.label',
    description='Execute command on remote server via SSH',
    description_key='modules.ssh.exec.description',
    icon='Terminal',
    color='#1E293B',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=60000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.connect'],

    params_schema=compose(
        field('host', type='string', label='Host', label_key='modules.ssh.exec.params.host.label',
              description='SSH server hostname or IP', required=True,
              placeholder='192.168.1.100', group=FieldGroup.CONNECTION),
        field('port', type='number', label='Port', label_key='modules.ssh.exec.params.port.label',
              description='SSH port', default=22, min=1, max=65535,
              group=FieldGroup.CONNECTION),
        field('username', type='string', label='Username', label_key='modules.ssh.exec.params.username.label',
              description='SSH username', required=True, placeholder='root',
              group=FieldGroup.CONNECTION),
        field('password', type='string', label='Password', label_key='modules.ssh.exec.params.password.label',
              description='SSH password', format='password',
              group=FieldGroup.CONNECTION),
        field('private_key', type='string', label='Private Key', label_key='modules.ssh.exec.params.private_key.label',
              description='PEM-format private key', format='multiline',
              group=FieldGroup.CONNECTION),
        field('command', type='string', label='Command', label_key='modules.ssh.exec.params.command.label',
              description='Command to execute on remote server', required=True,
              format='multiline', placeholder='ls -la /var/log',
              group=FieldGroup.BASIC),
        field('timeout', type='number', label='Timeout', label_key='modules.ssh.exec.params.timeout.label',
              description='Command timeout in seconds', default=30, min=1, max=3600,
              group=FieldGroup.ADVANCED),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether command succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'stdout': {'type': 'string', 'description': 'Standard output'},
                'stderr': {'type': 'string', 'description': 'Standard error'},
                'exit_code': {
                    'type': 'number',
                    'description': (
                        'Exit code, or 0 when the remote sent no exit status at all. '
                        'Check exit_status_reported before reading a 0 as success'
                    ),
                },
                'exit_status_reported': {
                    'type': 'boolean',
                    'description': (
                        'Whether the remote actually sent an exit status. False means '
                        'the channel closed without one and the exit_code beside it is '
                        'a default written by this module'
                    ),
                },
                'host': {'type': 'string', 'description': 'Target host'},
                'outcome': {
                    'type': 'object',
                    'description': (
                        'How far this command was followed: observed on a reported '
                        'exit 0, indeterminate on a non-zero or missing status and on '
                        'anything that broke after the command was sent, failed when '
                        'it never left'
                    ),
                },
            }
        }
    },
    examples=[
        {
            'title': 'List files on remote server',
            'title_key': 'modules.ssh.exec.examples.ls.title',
            'params': {
                'host': '192.168.1.100',
                'username': 'deploy',
                'command': 'ls -la /var/www'
            }
        },
        {
            'title': 'Restart service',
            'title_key': 'modules.ssh.exec.examples.restart.title',
            'params': {
                'host': '10.0.0.5',
                'username': 'root',
                'command': 'systemctl restart nginx'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def ssh_exec(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute command on remote server via SSH"""
    # SECURITY: `host` is caller-controlled and this module opens a raw
    # connection to it. Unguarded that reaches any internal service the runner
    # can route to, including the cloud metadata endpoint — the same
    # reachability the HTTP SSRF advisories are about, without a URL. Loopback
    # stays allowed so self-hosted deployments are unaffected.
    #
    # Checked before the optional-dependency import so it fails closed whether
    # or not asyncssh is installed.
    enforce_outbound_host(context['params']['host'], purpose='SSH')

    try:
        import asyncssh
    except ImportError:
        raise ImportError(
            "asyncssh is required for ssh.exec. "
            "Install with: pip install asyncssh"
        )

    params = context['params']
    host = params['host']
    port = params.get('port', 22)
    username = params['username']
    password = params.get('password')
    private_key = params.get('private_key')
    command = params['command']
    timeout = params.get('timeout', 30)

    if not password and not private_key:
        return {
            'ok': False,
            'error': 'Either password or private_key must be provided',
            'error_code': 'MISSING_CREDENTIALS',
            'outcome': envelope(
                Outcome.FAILED,
                claim_by=ClaimBy.NONE,
                effects=[{
                    'kind': 'ssh_credentials_missing',
                    'host': host,
                    'command_sent': False,
                    'measured_by': None,
                    'detail': (
                        'No password and no private key, so no connection was '
                        'attempted and nothing left this process.'
                    ),
                }],
            ),
        }

    # Set immediately before `conn.run` is awaited, and read by every except
    # clause below. See the module docstring: it is the only thing that can tell
    # a dead host at connect time from a session that dropped with the command
    # already running, and those two are not the same answer.
    command_sent = False

    connect_opts: Dict[str, Any] = {
        'host': host,
        'port': port,
        'username': username,
        'known_hosts': None,
    }

    if private_key:
        connect_opts['client_keys'] = [asyncssh.import_private_key(private_key)]
    if password:
        connect_opts['password'] = password

    try:
        async with asyncssh.connect(**connect_opts) as conn:
            command_sent = True
            result = await asyncio.wait_for(
                conn.run(command, check=False),
                timeout=timeout
            )

            stdout = result.stdout or ''
            stderr = result.stderr or ''
            exit_status = result.exit_status
            # BUG, left in place deliberately -- see the module docstring. `or 0`
            # launders a missing status into a clean success. The truth travels
            # in exit_status_reported and in the rung until the field itself can
            # be changed without breaking callers that type it as an int.
            exit_code = exit_status or 0

            logger.info(
                f"SSH exec on {host}: exit_code={exit_code}, "
                f"stdout_len={len(stdout)}, stderr_len={len(stderr)}"
            )

            return {
                'ok': True,
                'data': {
                    'stdout': stdout,
                    'stderr': stderr,
                    'exit_code': exit_code,
                    'exit_status_reported': exit_status is not None,
                    'host': host,
                    'outcome': _run_outcome(
                        host=host,
                        command=command,
                        exit_status=exit_status,
                        stdout_len=len(stdout),
                        stderr_len=len(stderr),
                    ),
                }
            }

    except asyncio.TimeoutError:
        logger.error(f"SSH command timed out on {host} after {timeout}s")
        return {
            'ok': False,
            'error': f'Command timed out after {timeout} seconds',
            'error_code': 'TIMEOUT',
            'data': {
                'host': host,
                # The textbook INDETERMINATE named in outcome.py. We stopped
                # waiting; the command is still running on a machine we no
                # longer have a channel to, and nothing here can say whether it
                # completed, half-completed, or never started.
                'outcome': _connection_outcome(
                    host=host,
                    kind='ssh_command_timed_out',
                    detail=(
                        f'The command did not return within {timeout}s and the '
                        'wait was abandoned. It was sent to the remote host and '
                        'may still be running there.'
                    ),
                    command_sent=command_sent,
                    timeout_seconds=timeout,
                ),
            },
        }

    except asyncssh.DisconnectError as e:
        logger.error(f"SSH disconnect error on {host}: {e}")
        return {
            'ok': False,
            'error': f'SSH connection disconnected: {e}',
            'error_code': 'DISCONNECT',
            'data': {
                'host': host,
                'outcome': _connection_outcome(
                    host=host,
                    kind='ssh_disconnected',
                    detail=(
                        'The SSH session ended before a result came back. '
                        'Whether the command had already run depends on when '
                        'the session dropped, which command_sent is the only '
                        'thing here that distinguishes.'
                    ),
                    command_sent=command_sent,
                ),
            },
        }

    except asyncssh.PermissionDenied as e:
        logger.error(f"SSH permission denied on {host}: {e}")
        return {
            'ok': False,
            'error': f'SSH authentication failed: {e}',
            'error_code': 'AUTH_FAILED',
            'data': {
                'host': host,
                # FAILED unconditionally, and the only handler here that does
                # not consult command_sent: authentication happens inside
                # `connect`, so the session never opened and no command could
                # have been sent.
                'outcome': envelope(
                    Outcome.FAILED,
                    claim_by=ClaimBy.NONE,
                    effects=[{
                        'kind': 'ssh_authentication_refused',
                        'host': host,
                        'command_sent': False,
                        'measured_by': None,
                        'detail': (
                            'The remote host refused the credentials, so no '
                            'session opened and the command was never sent.'
                        ),
                    }],
                ),
            },
        }

    except OSError as e:
        logger.error(f"SSH connection failed to {host}: {e}")
        return {
            'ok': False,
            'error': f'Connection failed: {e}',
            'error_code': 'CONNECTION_ERROR',
            'data': {
                'host': host,
                'outcome': _connection_outcome(
                    host=host,
                    kind='ssh_connection_error',
                    detail=(
                        'A socket-level error ended the exchange. Before the '
                        'command was sent this is an unreachable host and '
                        'nothing happened; after it, the TCP session died '
                        'under a command that may have completed.'
                    ),
                    command_sent=command_sent,
                    error=f'{type(e).__name__}: {e}',
                ),
            },
        }

    except Exception as e:
        logger.error(f"SSH exec error on {host}: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SSH_ERROR',
            'data': {
                'host': host,
                'outcome': _connection_outcome(
                    host=host,
                    kind='ssh_exec_raised',
                    detail=(
                        'An unclassified exception ended the exchange. The rung '
                        'is decided by whether the command had already been '
                        'sent, because nothing else here can say.'
                    ),
                    command_sent=command_sent,
                    error=f'{type(e).__name__}: {e}',
                ),
            },
        }
