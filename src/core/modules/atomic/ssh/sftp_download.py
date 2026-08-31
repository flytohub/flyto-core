# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
SFTP Download Module
Download files from remote servers via SFTP

HOW FAR THIS MODULE FOLLOWS REALITY

Unlike its upload sibling, this module already read something real back:
`os.path.getsize(local_path)` runs after `sftp.get` and stats the file that now
exists on this disk. That is a measurement of durable local state, and it is why
the success path here starts from a stronger position than `ssh.sftp_upload`'s
did.

It is not enough on its own, though, and the reason is the one `file.write`
gives about append mode. `sftp.get` overwrites, so a local file may already have
been at that path; a size read afterwards says how big the file is, not that our
transfer is why. What turns it into evidence is a number the module was ALREADY
fetching and throwing away -- `remote_attrs = await sftp.stat(remote_path)` was
assigned and never read again. The remote's own size for the source file is the
expectation the local size can be compared against, and it costs nothing because
the round trip was already being made.

    local size equals the remote size          OBSERVED
        Two measurements, one on each side, that agree. claim_by is INFERRED:
        the equality is this module's predicate, not a caller's.

    the sizes differ                           INDETERMINATE
        Not FAILED. There is a real race that makes this happen to a correct
        download -- the remote file can be rewritten between the stat and the
        get -- alongside the truncation it is more likely to mean. `file.write`
        splits the same way for the same reason: an inference of ours that may
        be wrong is indeterminate, a caller's broken contract is failed.

    the server reported no size for the source ACCEPTED
        A local size with nothing to compare it to is `file.write`'s append mode
        without a baseline, and gets the same answer: the transfer was accepted
        and nothing about it was confirmed. Rare -- SFTPAttrs almost always
        carries a size -- and it is here so that the OBSERVED case never has to
        cover for it.

    the remote file does not exist             FAILED
    no credentials / the local dir is unwritable  FAILED
    the transfer broke after it started        INDETERMINATE

`transfer_started` splits the last two, as in `ssh.sftp_upload`, and it matters
slightly more here: a broken download leaves a truncated file at `local_path`
that a later step will happily read.

VERIFIED is not reached and no `postcondition=` is declared. Equal sizes are not
equal bytes. `file.edit` compares content and earns VERIFIED for it; this
compares two integers.
"""

import logging
import os
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import enforce_outbound_host, validate_path_with_env_config
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


logger = logging.getLogger(__name__)


def _download_outcome(
    *,
    host: str,
    remote_path: str,
    local_path: str,
    local_size: int,
    remote_size: Optional[int],
) -> Dict[str, Any]:
    """The rung this download earned. Three answers; see the module docstring."""
    local_effect = {
        'kind': 'sftp_local_file_observed',
        'local_path': local_path,
        'bytes_on_disk': local_size,
        'measured_by': 'os.path.getsize(local_path), after the transfer returned',
        'detail': (
            'Size the local filesystem reports for the file that now exists. '
            'Real, but on its own it says how big the file is and not that this '
            'transfer is the reason -- get overwrites, so something may have '
            'been there already.'
        ),
    }

    if remote_size is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                local_effect,
                {
                    'kind': 'sftp_remote_size_unknown',
                    'host': host,
                    'remote_path': remote_path,
                    'measured_by': None,
                    'detail': (
                        'The server reported no size for the source file, so the '
                        'local size has nothing to be compared against. The '
                        'transfer was accepted and followed no further.'
                    ),
                },
            ],
        )

    remote_effect = {
        'kind': 'sftp_remote_size_observed',
        'host': host,
        'remote_path': remote_path,
        'bytes_on_remote': remote_size,
        'measured_by': 'sftp.stat(remote_path).size, before the transfer',
        'detail': (
            'The size the remote reported for the source. Read before the '
            'transfer, so a remote file rewritten mid-download would make this '
            'disagree with the local size through no fault of the transfer.'
        ),
    }

    if local_size == remote_size:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            postcondition='os.path.getsize(local_path) == sftp.stat(remote_path).size',
            effects=[remote_effect, local_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        postcondition='os.path.getsize(local_path) == sftp.stat(remote_path).size',
        effects=[
            remote_effect,
            local_effect,
            {
                'kind': 'sftp_sizes_disagree',
                'host': host,
                'remote_path': remote_path,
                'local_path': local_path,
                'predicate': 'os.path.getsize(local_path) == sftp.stat(remote_path).size',
                'expected_bytes': remote_size,
                'actual_bytes': local_size,
                'measured_by': 'the two sizes, compared',
                'detail': (
                    'The local file is not the size the remote reported. Most '
                    'likely a truncated transfer -- and there is a real race in '
                    'which a correct one lands here, because the remote file can '
                    'be rewritten between the stat and the get. We cannot say '
                    'which, so this is indeterminate rather than failed.'
                ),
            },
        ],
    )


def _refused(kind: str, detail: str, **fields: Any) -> Dict[str, Any]:
    """The envelope for a path where no bytes were transferred."""
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[dict(
            {'kind': kind, 'transfer_started': False, 'measured_by': None, 'detail': detail},
            **fields,
        )],
    )


def _broke_outcome(
    *,
    host: str,
    remote_path: str,
    local_path: str,
    kind: str,
    detail: str,
    transfer_started: bool,
    **fields: Any,
) -> Dict[str, Any]:
    """The rung for an exception, decided by whether bytes had started moving.

    INDETERMINATE after `get` began matters more here than on the upload side:
    what a broken download leaves behind is a truncated file on THIS disk, under
    a path a later step in the same workflow is likely to read as if it were
    whole.
    """
    return envelope(
        Outcome.INDETERMINATE if transfer_started else Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[dict(
            {
                'kind': kind,
                'host': host,
                'remote_path': remote_path,
                'local_path': local_path,
                'transfer_started': transfer_started,
                'measured_by': None,
                'detail': detail,
            },
            **fields,
        )],
    )


@register_module(
    module_id='ssh.sftp_download',
    version='1.0.0',
    category='atomic',
    subcategory='ssh',
    tags=['ssh', 'sftp', 'download', 'file', 'devops'],
    label='SFTP Download',
    label_key='modules.ssh.sftp_download.label',
    description='Download file from remote server via SFTP',
    description_key='modules.ssh.sftp_download.description',
    icon='Download',
    color='#10B981',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=120000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.connect', 'filesystem.write'],

    params_schema=compose(
        field('host', type='string', label='Host', label_key='modules.ssh.sftp_download.params.host.label',
              description='SSH server hostname or IP', required=True,
              placeholder='192.168.1.100', group=FieldGroup.CONNECTION),
        field('port', type='number', label='Port', label_key='modules.ssh.sftp_download.params.port.label',
              description='SSH port', default=22, min=1, max=65535,
              group=FieldGroup.CONNECTION),
        field('username', type='string', label='Username', label_key='modules.ssh.sftp_download.params.username.label',
              description='SSH username', required=True, placeholder='deploy',
              group=FieldGroup.CONNECTION),
        field('password', type='string', label='Password', label_key='modules.ssh.sftp_download.params.password.label',
              description='SSH password', format='password',
              group=FieldGroup.CONNECTION),
        field('private_key', type='string', label='Private Key', label_key='modules.ssh.sftp_download.params.private_key.label',
              description='PEM-format private key', format='multiline',
              group=FieldGroup.CONNECTION),
        field('remote_path', type='string', label='Remote Path', label_key='modules.ssh.sftp_download.params.remote_path.label',
              description='Path to file on remote server', required=True,
              placeholder='/var/log/app.log', group=FieldGroup.BASIC),
        field('local_path', type='string', label='Local Path', label_key='modules.ssh.sftp_download.params.local_path.label',
              description='Destination path on local machine', required=True,
              placeholder='/tmp/app.log', group=FieldGroup.BASIC),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether download succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'local_path': {'type': 'string', 'description': 'Local file path'},
                'size_bytes': {
                    'type': 'number',
                    'description': (
                        'Size the local filesystem reports for the downloaded file, '
                        'from os.path.getsize after the transfer'
                    ),
                },
                'remote_size_bytes': {
                    'type': 'number',
                    'description': (
                        'Size the remote reported for the source file before the '
                        'transfer. null when the server reported none -- which is '
                        'what leaves size_bytes with nothing to be checked against'
                    ),
                },
                'host': {'type': 'string', 'description': 'Source host'},
                'outcome': {
                    'type': 'object',
                    'description': (
                        'How far this download was followed: observed when the local '
                        'file matched the size the remote reported, accepted when '
                        'there was no remote size to compare, indeterminate when they '
                        'disagreed or the transfer broke after it began'
                    ),
                },
            }
        }
    },
    examples=[
        {
            'title': 'Download server log',
            'title_key': 'modules.ssh.sftp_download.examples.log.title',
            'params': {
                'host': '10.0.0.5',
                'username': 'deploy',
                'remote_path': '/var/log/nginx/access.log',
                'local_path': '/tmp/access.log'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def ssh_sftp_download(context: Dict[str, Any]) -> Dict[str, Any]:
    """Download file from remote server via SFTP"""
    # SECURITY: the path boundary is checked before the optional-dependency
    # import so it fails closed either way. Validating after the import would
    # make the guard conditional on asyncssh being installed.
    context['params']['local_path'] = validate_path_with_env_config(
        str(context['params']['local_path'])
    )

    # SECURITY: `host` is caller-controlled and this module opens an SSH
    # connection to it, so both the filesystem and the network side need a
    # boundary. Checked here, before the optional-dependency import, so it
    # fails closed whether or not asyncssh is installed.
    enforce_outbound_host(context['params']['host'], purpose='SFTP')

    try:
        import asyncssh
    except ImportError:
        raise ImportError(
            "asyncssh is required for ssh.sftp_download. "
            "Install with: pip install asyncssh"
        )

    params = context['params']
    host = params['host']
    port = params.get('port', 22)
    username = params['username']
    password = params.get('password')
    private_key = params.get('private_key')
    remote_path = params['remote_path']
    local_path = params['local_path']

    if not password and not private_key:
        return {
            'ok': False,
            'error': 'Either password or private_key must be provided',
            'error_code': 'MISSING_CREDENTIALS',
            'outcome': _refused(
                'sftp_credentials_missing',
                'No password and no private key, so no connection was attempted '
                'and nothing left this process.',
                host=host,
                remote_path=remote_path,
            ),
        }

    # local_path was confined at entry (see the top of this function). Remote
    # bytes land there, which is exactly the destination_path arbitrary file
    # write of GHSA-hmq9-xw4w-7ppc — that advisory named
    # cloud.{azure,gcs,aws_s3}.download and missed this SFTP sibling. Confining
    # it up front also means the makedirs below cannot create a tree outside
    # the sandbox. remote_path stays unvalidated on purpose: it addresses the
    # remote host, not this filesystem.
    local_dir = os.path.dirname(local_path)
    if not os.path.isdir(local_dir):
        try:
            os.makedirs(local_dir, exist_ok=True)
        except OSError as e:
            return {
                'ok': False,
                'error': f'Cannot create local directory: {e}',
                'error_code': 'DIRECTORY_ERROR',
                'outcome': _refused(
                    'sftp_local_directory_unwritable',
                    'The destination directory could not be created, so no '
                    'connection was attempted.',
                    host=host,
                    local_path=local_path,
                    error=f'{type(e).__name__}: {e}',
                ),
            }

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

    # Set immediately before `get`, read by every handler below. See the module
    # docstring: after it, a truncated file may be sitting at local_path for a
    # later step to read as if it were whole.
    transfer_started = False

    try:
        async with asyncssh.connect(**connect_opts) as conn:
            async with conn.start_sftp_client() as sftp:
                # Check if remote file exists
                try:
                    remote_attrs = await sftp.stat(remote_path)
                except asyncssh.SFTPNoSuchFile:
                    return {
                        'ok': False,
                        'error': f'Remote file not found: {remote_path}',
                        'error_code': 'FILE_NOT_FOUND',
                        'data': {
                            'host': host,
                            'outcome': _refused(
                                'sftp_remote_file_absent',
                                'The remote path holds no file, so nothing was '
                                'transferred and nothing was written locally.',
                                host=host,
                                remote_path=remote_path,
                                measured_by='sftp.stat(remote_path) before the transfer',
                            ),
                        },
                    }

                # This was assigned and never read. It is the expectation the
                # local size is compared against below -- the round trip was
                # already being made, and the number in it was being discarded.
                remote_size = getattr(remote_attrs, 'size', None)

                transfer_started = True
                await sftp.get(remote_path, local_path)

                file_size = os.path.getsize(local_path)

                logger.info(
                    f"SFTP download from {host}: {remote_path} -> {local_path} "
                    f"({file_size} bytes local, {remote_size} reported remote)"
                )

                return {
                    'ok': True,
                    'data': {
                        'local_path': local_path,
                        'size_bytes': file_size,
                        'remote_size_bytes': remote_size,
                        'host': host,
                        'outcome': _download_outcome(
                            host=host,
                            remote_path=remote_path,
                            local_path=local_path,
                            local_size=file_size,
                            remote_size=remote_size,
                        ),
                    }
                }

    except asyncssh.PermissionDenied as e:
        logger.error(f"SFTP permission denied on {host}: {e}")
        return {
            'ok': False,
            'error': f'SSH authentication failed: {e}',
            'error_code': 'AUTH_FAILED',
            'data': {
                'host': host,
                # FAILED unconditionally: authentication happens inside
                # `connect`, so no session existed for bytes to cross.
                'outcome': _refused(
                    'sftp_authentication_refused',
                    'The remote host refused the credentials, so no session '
                    'opened and no bytes were transferred.',
                    host=host,
                    remote_path=remote_path,
                ),
            },
        }

    except asyncssh.SFTPError as e:
        logger.error(f"SFTP error on {host}: {e}")
        return {
            'ok': False,
            'error': f'SFTP error: {e}',
            'error_code': 'SFTP_ERROR',
            'data': {
                'host': host,
                'outcome': _broke_outcome(
                    host=host,
                    remote_path=remote_path,
                    local_path=local_path,
                    kind='sftp_protocol_error',
                    detail=(
                        'The SFTP layer reported an error. Raised by the stat it '
                        'means nothing was written locally; raised by the get it '
                        'means local_path may hold a truncated file.'
                    ),
                    transfer_started=transfer_started,
                    error=f'{type(e).__name__}: {e}',
                ),
            },
        }

    except OSError as e:
        logger.error(f"SFTP connection failed to {host}: {e}")
        return {
            'ok': False,
            'error': f'Connection failed: {e}',
            'error_code': 'CONNECTION_ERROR',
            'data': {
                'host': host,
                # Note this handler also catches an OSError from the
                # os.path.getsize above, whose 'Connection failed' wording is
                # then wrong -- but the rung is not: getsize only runs with
                # transfer_started True, so this reports indeterminate, which is
                # the truth about a download whose result could not be measured.
                'outcome': _broke_outcome(
                    host=host,
                    remote_path=remote_path,
                    local_path=local_path,
                    kind='sftp_connection_error',
                    detail=(
                        'A socket- or filesystem-level error ended the exchange. '
                        'Before the transfer began nothing was written; after '
                        'it, local_path may hold a partial file.'
                    ),
                    transfer_started=transfer_started,
                    error=f'{type(e).__name__}: {e}',
                ),
            },
        }

    except Exception as e:
        logger.error(f"SFTP download error on {host}: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SFTP_ERROR',
            'data': {
                'host': host,
                'outcome': _broke_outcome(
                    host=host,
                    remote_path=remote_path,
                    local_path=local_path,
                    kind='sftp_download_raised',
                    detail=(
                        'An unclassified exception ended the exchange. The rung '
                        'is decided by whether the transfer had begun, because '
                        'nothing else here can say.'
                    ),
                    transfer_started=transfer_started,
                    error=f'{type(e).__name__}: {e}',
                ),
            },
        }
