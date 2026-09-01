# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
SFTP Upload Module
Upload files to remote servers via SFTP

HOW FAR THIS MODULE FOLLOWS REALITY

This is `file.write`'s defect with a network added, and it was here in exactly
the form the brief describes. The module returned:

    'size_bytes': file_size          # os.path.getsize(LOCAL_path)

as its evidence that a file had been uploaded. That number is measured before
the transfer starts, off the local disk, from the file being sent. It is
byte-identical if the remote disk is full and the write truncates, if the remote
filesystem is read-only, or if the server accepted the handle and wrote nothing.
`await sftp.put(...)` returns `None` and nothing was ever read back. Apply the
test -- would this value be the same if the effect had not happened? -- and it
plainly would.

So a read-back was added, the same way it was added to `file.write`, and the
rung now follows the measurement rather than the intention:

    stat after the put, size matches the local file    OBSERVED
        `sftp.stat(remote_path).size` is a number the remote server produced
        about a file on its own disk, after the transfer closed. claim_by is
        INFERRED because the equality is this module's predicate, not one a
        caller stated.

    stat after the put, size differs                   INDETERMINATE
        Not FAILED, for `file.write`'s reason: nobody declared a size contract,
        so a mismatch is this module's inference possibly being wrong. There are
        ordinary correct uploads it is false for -- an SFTP server that appends
        rather than truncating, a concurrent writer, a filesystem that reports
        allocated rather than logical size. A caller's broken contract is
        FAILED; an inference of ours that may simply be wrong is this.

    stat failed, or the server reported no size        ACCEPTED
        The honest floor, and the rung this module had before a read-back
        existed. `put` returned without raising, which is the server
        acknowledging the transfer, and nothing followed it further. A stat that
        raises is NOT a failed upload -- some servers deny stat while permitting
        write -- so it must not fail the module, only lower what it may claim.

    remote file exists and overwrite=False             FAILED, claim_by=CALLER
        The one predicate here a caller actually wrote. `overwrite=False` says
        "do not replace it"; the stat found one; the module evaluated that and
        stopped. Attributing it to the caller is what tells a reader this is a
        contract, not a malfunction.

    no credentials / local file missing / auth refused FAILED
    the transfer broke after it started                INDETERMINATE

The last two are split by `transfer_started`, set immediately before `put`.
Before it, nothing reached the remote and a retry is free. After it, a partial
file may be sitting on the remote host under the destination name -- which is
the case a blind retry has to know about, and the case a single `error_code`
cannot express.

VERIFIED is not reached and no `postcondition=` is declared. A size match is
evidence the transfer completed, not that the right bytes arrived; `file.edit`
earns VERIFIED because it compares content, and nothing here does. Declaring the
stronger predicate while measuring the weaker one would move the overclaim up a
level instead of removing it.
"""

import logging
import os
from typing import Any, Dict, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import enforce_outbound_host, validate_path_with_env_config
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The only lines in this module that measure the remote side. Everything else
# is arithmetic on a local file we already had. Kept in its own function so the
# two stages stay separable: when it cannot answer, the module falls back to
# exactly the ACCEPTED claim it made before a read-back existed here at all.
# ---------------------------------------------------------------------------
async def _observe_remote_size(sftp: Any, remote_path: str) -> Tuple[Optional[int], Optional[str]]:
    """``(size, None)`` when the remote file could be stat-ed, ``(None, why)`` when not.

    Every exception is swallowed on purpose, and the bare ``Exception`` is not
    laziness: this runs after ``put`` has already returned, so a failure here is
    a failure to LOOK and never a failure of the upload. Letting it propagate
    would turn a successful transfer into an error return over an observation
    the module was not required to make. Servers that permit write and deny stat
    exist, and on those this path is the normal one.
    """
    try:
        attrs = await sftp.stat(remote_path)
    except Exception as error:  # noqa: BLE001 - see docstring
        return None, f'{type(error).__name__}: {error}'
    size = getattr(attrs, 'size', None)
    if size is None:
        return None, 'the server returned attributes with no size field'
    return size, None


def _upload_outcome(
    *,
    host: str,
    remote_path: str,
    offered_bytes: int,
    observed_size: Optional[int],
    observation_error: Optional[str],
) -> Dict[str, Any]:
    """The rung this upload earned. Three answers; see the module docstring."""
    offered_effect = {
        'kind': 'sftp_bytes_offered',
        'host': host,
        'remote_path': remote_path,
        'bytes': offered_bytes,
        'measured_by': 'os.path.getsize(local_path), before the transfer',
        'detail': (
            'The size of the LOCAL file that was sent. No part of this number '
            'comes from the remote host: it reads identically whether the '
            'remote received every byte, some of them, or none.'
        ),
    }

    if observed_size is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                offered_effect,
                {
                    'kind': 'sftp_remote_not_read_back',
                    'host': host,
                    'remote_path': remote_path,
                    'measured_by': None,
                    'reason': observation_error,
                    'detail': (
                        'The remote file was not read back. The transfer was '
                        'accepted by the server and followed no further. Not a '
                        'failed upload -- a failure to look at one.'
                    ),
                },
            ],
        )

    observed_effect = {
        'kind': 'sftp_remote_size_observed',
        'host': host,
        'remote_path': remote_path,
        'bytes_on_remote': observed_size,
        'measured_by': 'sftp.stat(remote_path).size, after the transfer closed',
        'detail': (
            'Size the remote server reports for the file that now exists there. '
            'A size, not a comparison of contents: equal length is not equal '
            'bytes, and nothing here checksums anything.'
        ),
    }

    if observed_size == offered_bytes:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            postcondition='sftp.stat(remote_path).size == os.path.getsize(local_path)',
            effects=[offered_effect, observed_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        postcondition='sftp.stat(remote_path).size == os.path.getsize(local_path)',
        effects=[
            offered_effect,
            observed_effect,
            {
                'kind': 'sftp_remote_size_disagrees',
                'host': host,
                'remote_path': remote_path,
                'predicate': 'sftp.stat(remote_path).size == os.path.getsize(local_path)',
                'expected_bytes': offered_bytes,
                'actual_bytes': observed_size,
                'measured_by': 'the two sizes, compared',
                'detail': (
                    'The remote file is not the size of the file that was sent. '
                    'This may be a short or truncated transfer, or it may be '
                    "this module's inference being wrong -- a server that "
                    'appends rather than truncates, another writer, or a '
                    'filesystem reporting allocated size all make a correct '
                    'upload land at a different length. We cannot say which, so '
                    'this is indeterminate rather than failed.'
                ),
            },
        ],
    )


def _refused(kind: str, detail: str, *, claim_by: Any = ClaimBy.NONE, **fields: Any) -> Dict[str, Any]:
    """The envelope for a path where no bytes were sent."""
    return envelope(
        Outcome.FAILED,
        claim_by=claim_by,
        effects=[dict(
            {'kind': kind, 'transfer_started': False, 'measured_by': None, 'detail': detail},
            **fields,
        )],
    )


def _broke_outcome(
    *,
    host: str,
    remote_path: str,
    kind: str,
    detail: str,
    transfer_started: bool,
    **fields: Any,
) -> Dict[str, Any]:
    """The rung for an exception, decided by whether bytes had started moving.

    FAILED before `put` -- nothing reached the remote, and a retry is free.
    INDETERMINATE after: a partial file may be sitting on the remote host under
    the destination name, and a caller that retries blindly needs to know the
    difference.
    """
    return envelope(
        Outcome.INDETERMINATE if transfer_started else Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[dict(
            {
                'kind': kind,
                'host': host,
                'remote_path': remote_path,
                'transfer_started': transfer_started,
                'measured_by': None,
                'detail': detail,
            },
            **fields,
        )],
    )


@register_module(
    module_id='ssh.sftp_upload',
    version='1.0.0',
    category='atomic',
    subcategory='ssh',
    tags=['ssh', 'sftp', 'upload', 'file', 'devops'],
    label='SFTP Upload',
    label_key='modules.ssh.sftp_upload.label',
    description='Upload file to remote server via SFTP',
    description_key='modules.ssh.sftp_upload.description',
    icon='Upload',
    color='#3B82F6',

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
    required_permissions=['network.connect', 'filesystem.read'],

    params_schema=compose(
        field('host', type='string', label='Host', label_key='modules.ssh.sftp_upload.params.host.label',
              description='SSH server hostname or IP', required=True,
              placeholder='192.168.1.100', group=FieldGroup.CONNECTION),
        field('port', type='number', label='Port', label_key='modules.ssh.sftp_upload.params.port.label',
              description='SSH port', default=22, min=1, max=65535,
              group=FieldGroup.CONNECTION),
        field('username', type='string', label='Username', label_key='modules.ssh.sftp_upload.params.username.label',
              description='SSH username', required=True, placeholder='deploy',
              group=FieldGroup.CONNECTION),
        field('password', type='string', label='Password', label_key='modules.ssh.sftp_upload.params.password.label',
              description='SSH password', format='password',
              group=FieldGroup.CONNECTION),
        field('private_key', type='string', label='Private Key', label_key='modules.ssh.sftp_upload.params.private_key.label',
              description='PEM-format private key', format='multiline',
              group=FieldGroup.CONNECTION),
        field('local_path', type='string', label='Local Path', label_key='modules.ssh.sftp_upload.params.local_path.label',
              description='Path to local file to upload', required=True,
              placeholder='/tmp/deploy.tar.gz', group=FieldGroup.BASIC),
        field('remote_path', type='string', label='Remote Path', label_key='modules.ssh.sftp_upload.params.remote_path.label',
              description='Destination path on remote server', required=True,
              placeholder='/var/www/deploy.tar.gz', group=FieldGroup.BASIC),
        field('overwrite', type='boolean', label='Overwrite', label_key='modules.ssh.sftp_upload.params.overwrite.label',
              description='Overwrite existing remote file', default=True,
              group=FieldGroup.OPTIONS),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether upload succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'remote_path': {'type': 'string', 'description': 'Remote file path'},
                'size_bytes': {
                    'type': 'number',
                    'description': (
                        'Size of the LOCAL file that was offered to the transfer. Not '
                        'a measurement of the remote file -- see remote_size_bytes'
                    ),
                },
                'remote_size_bytes': {
                    'type': 'number',
                    'description': (
                        'Size the remote server reports for the file after the '
                        'transfer, from sftp.stat. null when it could not be read back'
                    ),
                },
                'host': {'type': 'string', 'description': 'Target host'},
                'outcome': {
                    'type': 'object',
                    'description': (
                        'How far this upload was followed: observed when the remote '
                        'file measured the size offered, accepted when nothing was '
                        'read back, indeterminate when the size disagreed or the '
                        'transfer broke after it began'
                    ),
                },
            }
        }
    },
    examples=[
        {
            'title': 'Upload deployment archive',
            'title_key': 'modules.ssh.sftp_upload.examples.deploy.title',
            'params': {
                'host': '10.0.0.5',
                'username': 'deploy',
                'local_path': '/tmp/app.tar.gz',
                'remote_path': '/opt/releases/app.tar.gz'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def ssh_sftp_upload(context: Dict[str, Any]) -> Dict[str, Any]:
    """Upload file to remote server via SFTP"""
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
            "asyncssh is required for ssh.sftp_upload. "
            "Install with: pip install asyncssh"
        )

    params = context['params']
    host = params['host']
    port = params.get('port', 22)
    username = params['username']
    password = params.get('password')
    private_key = params.get('private_key')
    local_path = params['local_path']
    remote_path = params['remote_path']
    overwrite = params.get('overwrite', True)

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
            ),
        }

    # local_path was confined at entry (see the top of this function): it is
    # read and shipped to a caller-chosen SSH host, so an unconfined path is
    # credential exfiltration with its own egress channel. remote_path is
    # deliberately NOT validated — it names a location on the remote host.
    if not os.path.isfile(local_path):
        return {
            'ok': False,
            'error': f'Local file not found: {local_path}',
            'error_code': 'FILE_NOT_FOUND',
            'outcome': _refused(
                'sftp_local_file_absent',
                'There is nothing at the local path to send, so no connection '
                'was attempted.',
                host=host,
                local_path=local_path,
            ),
        }

    file_size = os.path.getsize(local_path)
    # Set immediately before `put`, read by every handler below. See the module
    # docstring: it is the difference between "nothing reached the remote" and
    # "a partial file may be sitting there under the destination name".
    transfer_started = False

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
            async with conn.start_sftp_client() as sftp:
                # Check if remote file exists when overwrite is disabled
                if not overwrite:
                    try:
                        await sftp.stat(remote_path)
                        return {
                            'ok': False,
                            'error': f'Remote file already exists: {remote_path}',
                            'error_code': 'FILE_EXISTS',
                            # claim_by=CALLER: `overwrite=False` is a predicate
                            # the caller wrote, this module evaluated it against
                            # a real stat of the remote, and it did not hold.
                            # That is a broken contract and not a malfunction.
                            'outcome': _refused(
                                'sftp_remote_file_exists',
                                'The caller asked not to overwrite and a file is '
                                'already at the remote path. Nothing was sent.',
                                claim_by=ClaimBy.CALLER,
                                host=host,
                                remote_path=remote_path,
                                predicate='no file exists at remote_path',
                                measured_by='sftp.stat(remote_path) before the transfer',
                            ),
                        }
                    except asyncssh.SFTPNoSuchFile:
                        pass  # File doesn't exist, safe to upload

                transfer_started = True
                await sftp.put(local_path, remote_path)

                # STAGE 2 -- the only measurement of the remote side. Outside
                # nothing: `put` has returned, so the server has taken and closed
                # the file and a stat is a size rather than a race.
                observed_size, observation_error = await _observe_remote_size(sftp, remote_path)

                logger.info(
                    f"SFTP upload to {host}: {local_path} -> {remote_path} "
                    f"({file_size} bytes offered, {observed_size} observed)"
                )

                return {
                    'ok': True,
                    'data': {
                        'remote_path': remote_path,
                        'size_bytes': file_size,
                        'remote_size_bytes': observed_size,
                        'host': host,
                        'outcome': _upload_outcome(
                            host=host,
                            remote_path=remote_path,
                            offered_bytes=file_size,
                            observed_size=observed_size,
                            observation_error=observation_error,
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
                # FAILED unconditionally, and the only handler that does not
                # consult transfer_started: authentication happens inside
                # `connect`, so no session existed to send bytes over.
                'outcome': _refused(
                    'sftp_authentication_refused',
                    'The remote host refused the credentials, so no session '
                    'opened and no bytes were sent.',
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
                    kind='sftp_protocol_error',
                    detail=(
                        'The SFTP layer reported an error. Raised by the '
                        'pre-transfer stat it means nothing was written; raised '
                        'by the put it means the remote path may hold a partial '
                        'file. transfer_started is what separates them.'
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
                'outcome': _broke_outcome(
                    host=host,
                    remote_path=remote_path,
                    kind='sftp_connection_error',
                    detail=(
                        'A socket-level error ended the exchange. Before the '
                        'transfer began nothing reached the remote; after it, '
                        'the session died mid-write.'
                    ),
                    transfer_started=transfer_started,
                    error=f'{type(e).__name__}: {e}',
                ),
            },
        }

    except Exception as e:
        logger.error(f"SFTP upload error on {host}: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SFTP_ERROR',
            'data': {
                'host': host,
                'outcome': _broke_outcome(
                    host=host,
                    remote_path=remote_path,
                    kind='sftp_upload_raised',
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
