# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Git Clone Module
Clone a git repository to a local path

HOW FAR THIS MODULE FOLLOWS REALITY

`git.clone` is the one module in this group that earns OBSERVED without needing
a baseline, and the reason is a property of git rather than a cleverness here:
`git clone` refuses a destination that already exists and is not empty. So when
it exits 0, whatever is at the destination was put there by this clone, and
reading a commit object out of it is a reading of durable state that could not
have been there before.

    a commit object resolves at the destination     OBSERVED
        `git -C destination rev-parse HEAD` walks a real object store on the
        local disk and prints an object name. If no clone had happened there
        would be no repository to ask, and the answer would be the module's
        'unknown' sentinel. That is the test this contract runs on every value,
        and this one passes it.

    git exited 0 and no commit resolves             ACCEPTED
        Cloning an EMPTY repository is a success with an unborn HEAD, and
        `rev-parse` fails. The clone was accepted and nothing was read back.
        Reported honestly rather than smoothed into the OBSERVED case, which
        would have made "the remote had no commits" indistinguishable from "we
        confirmed the history landed".

    the URL or the target was refused               FAILED
    git exited non-zero, or is not installed        FAILED
        Definite refusals. No repository was created.

    an exception escaped mid-clone                  INDETERMINATE
        The `try` below spans the subprocess AND the read-back. An exception can
        land after `git clone` has already written a tree, so whether anything
        exists at the destination is exactly what is not known. This is the one
        place in this module where a retry is not obviously safe, and collapsing
        it into the FAILED paths would hide that.

VERIFIED is not reachable and none is declared. What a caller wants verified is
"the destination holds the history of that URL at that branch"; this module
reads a sha and a branch name out of the clone without ever comparing them to
the remote, so there is no predicate here that has been evaluated.
"""

import asyncio
import logging
import re
from typing import Any, Dict
from urllib.parse import urlparse, urlunparse

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import (
    SSRFError,
    enforce_outbound_host,
    enforce_outbound_url,
    validate_path_with_env_config,
)
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)

# git remote-helper transports (ext::, fd::, transport::cmd) execute an arbitrary
# command — `git clone 'ext::sh -c "id"'` is RCE. Detect the `scheme::` form.
_GIT_TRANSPORT_HELPER = re.compile(r'^[A-Za-z][A-Za-z0-9+.\-]*::')
_ALLOWED_CLONE_SCHEMES = {'http', 'https', 'ssh', 'git', 'ftp', 'ftps', 'rsync'}

# Protocols git itself is permitted to use, injected via GIT_ALLOW_PROTOCOL so
# the dangerous remote-helper transports (ext, fd, …) are refused by git even if
# a validation gap ever let one through. Defense in depth alongside
# _validate_clone_url.
_GIT_ALLOWED_PROTOCOLS = "http:https:ssh:git:ftp:ftps:rsync:file"


class UnsafeCloneURL(ValueError):
    """Raised when a clone URL could trigger command execution or local access."""


def _validate_clone_url(url: str) -> None:
    """Reject clone URLs that can run commands (ext::), read local files (file://),
    inject git options (leading '-'), or hit arbitrary local paths."""
    if not url or not url.strip():
        raise UnsafeCloneURL("empty clone url")
    u = url.strip()
    if u.startswith('-'):
        raise UnsafeCloneURL("clone url must not start with '-' (option injection)")
    if _GIT_TRANSPORT_HELPER.match(u):
        raise UnsafeCloneURL("git remote-helper transport (e.g. ext::) is not allowed")
    parsed = urlparse(u)
    if parsed.scheme and parsed.scheme.lower() not in _ALLOWED_CLONE_SCHEMES:
        # Explicit non-allowed scheme (file://, ext:: already caught above).
        raise UnsafeCloneURL(f"clone scheme '{parsed.scheme}' is not allowed")
    # Scheme-less values (scp-style user@host:path or a local repo path) are a
    # legitimate git feature and not command execution; the dangerous vectors
    # (ext::/fd:: transports, file://, option-injecting leading '-') are already
    # rejected above.


def _guard_clone_target(url: str) -> None:
    """SSRF guard for the clone target.

    Kept separate from ``_validate_clone_url``, which bounds *how* git connects
    (transport, option injection). This bounds *where*: without it,
    `git clone https://169.254.169.254/x` or an internal git host is a plain
    SSRF, with the response surfacing in git's error output. http(s) targets
    reuse the guard the HTTP modules use; scp-style `user@host:path` has no URL
    to parse, so its host is checked directly. Scheme-less local paths have no
    network component and are left to the path guard.
    """
    u = (url or '').strip()
    parsed = urlparse(u)
    scheme = (parsed.scheme or '').lower()
    if scheme in ('http', 'https'):
        enforce_outbound_url(u)
    elif not scheme and '@' in u and ':' in u:
        scp_host = u.split('@', 1)[1].split(':', 1)[0]
        if scp_host:
            enforce_outbound_host(scp_host, purpose='git remote')


def _build_clone_env() -> Dict[str, str]:
    """Scrubbed environment for the git subprocess.

    git inherits PATH/HOME/SSL certs but NOT host secrets, and GIT_ALLOW_PROTOCOL
    restricts git to safe transports (no ext/fd remote-helpers) regardless of the
    URL — defense in depth on top of _validate_clone_url. Set
    FLYTO_SANDBOX_INHERIT_ENV=1 to restore full inheritance.
    """
    from core.safe_env import build_sandbox_env
    return build_sandbox_env({
        "GIT_ALLOW_PROTOCOL": _GIT_ALLOWED_PROTOCOLS,
        "GIT_TERMINAL_PROMPT": "0",  # never block on an interactive cred prompt
    })


def _inject_token_into_url(url: str, token: str) -> str:
    """Inject access token into HTTPS URL for private repos."""
    parsed = urlparse(url)
    port_suffix = f':{parsed.port}' if parsed.port else ''
    authed = parsed._replace(
        netloc=f'x-access-token:{token}@{parsed.hostname}{port_suffix}'
    )
    return urlunparse(authed)


def _build_clone_cmd(clone_url: str, destination: str, branch: str = None, depth: int = None) -> list:
    """Build git clone command list."""
    cmd = ['git', 'clone']
    if branch:
        cmd.extend(['--branch', branch])
    if depth:
        cmd.extend(['--depth', str(depth)])
    # '--' terminates option parsing so neither url nor destination can be read
    # as a git flag (defense in depth alongside _validate_clone_url).
    cmd.extend(['--', clone_url, destination])
    return cmd


async def _get_repo_info(destination: str) -> tuple:
    """Get current branch and HEAD commit hash from cloned repo."""
    env = _build_clone_env()
    branch_proc = await asyncio.create_subprocess_exec(
        'git', '-C', destination, 'rev-parse', '--abbrev-ref', 'HEAD',
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
    )
    branch_out, _ = await branch_proc.communicate()
    current_branch = branch_out.decode('utf-8').strip() if branch_proc.returncode == 0 else 'unknown'

    commit_proc = await asyncio.create_subprocess_exec(
        'git', '-C', destination, 'rev-parse', 'HEAD',
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
    )
    commit_out, _ = await commit_proc.communicate()
    commit_hash = commit_out.decode('utf-8').strip() if commit_proc.returncode == 0 else 'unknown'

    return current_branch, commit_hash


def _sanitize_error(error_msg: str, token: str = None) -> str:
    """Remove token from error messages."""
    if token:
        error_msg = error_msg.replace(token, '***')
    return error_msg


#: git object names in both hash algorithms git can be configured with. Used to
#: tell a measurement apart from `_get_repo_info`'s 'unknown' sentinel, which is
#: a string like any other and would otherwise be read as evidence.
_OBJECT_NAME = re.compile(r'^[0-9a-f]{40}$|^[0-9a-f]{64}$')


def _refused(kind: str, detail: str, **fields: Any) -> Dict[str, Any]:
    """The envelope for a path where no repository was created.

    FAILED on all of them. Two are refusals by this module before anything was
    spawned, two are git itself exiting non-zero, and in every case the
    destination is known not to hold a clone. "We cannot say" would be a weaker
    statement than the one the code can actually make.
    """
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[dict({'kind': kind, 'measured_by': None, 'detail': detail}, **fields)],
    )


def _clone_outcome(
    *,
    destination: str,
    commit_hash: str,
    branch: str,
) -> Dict[str, Any]:
    """The rung this clone earned; two cases, decided by the read-back.

    The decision is whether `commit_hash` is an object name or the 'unknown'
    string `_get_repo_info` substitutes when `rev-parse` fails. Those are not
    the same kind of value and the pattern test is what keeps them apart -- a
    sentinel that travels in a field typed 'string' is exactly how a
    non-measurement gets read as a measurement.
    """
    if _OBJECT_NAME.match(commit_hash or ''):
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'git_repository_cloned',
                'path': destination,
                'commit': commit_hash,
                'branch': branch,
                'measured_by': (
                    'git -C <destination> rev-parse HEAD, against the object '
                    'store the clone wrote'
                ),
                'detail': (
                    'A commit object resolves inside the destination, which git '
                    'clone would have refused to write into had it already '
                    'existed non-empty. Not a claim about completeness: nothing '
                    'here compares the local history against the remote, and a '
                    'shallow clone resolves a sha exactly like a full one.'
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'git_clone_not_read_back',
            'path': destination,
            'branch': branch,
            'measured_by': None,
            'detail': (
                'git clone exited 0 and no commit object could be resolved at '
                'the destination. The ordinary cause is a remote with no '
                'commits, which clones successfully onto an unborn HEAD. The '
                'clone was accepted; nothing about its contents was observed.'
            ),
        }],
    )


@register_module(
    module_id='git.clone',
    version='1.0.0',
    category='atomic',
    subcategory='git',
    tags=['git', 'clone', 'repository', 'devops'],
    label='Git Clone',
    label_key='modules.git.clone.label',
    description='Clone a git repository',
    description_key='modules.git.clone.description',
    icon='GitBranch',
    color='#F05032',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=300000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=True,
    # git.clone spawns the host `git` binary, whose ext:: transport is a host RCE
    # primitive. Declare subprocess.execute so the capability gate
    # (core.module_policy) treats it as a dangerous host-exec module: it must be
    # explicitly granted (FLYTO_GRANTED_PERMISSIONS) AND is denied by the default
    # denylist (git.*) — it cannot run silently with a safe-looking permission set.
    required_permissions=['filesystem.write', 'network.connect', 'subprocess.execute'],

    params_schema=compose(
        field('url', type='string', label='Repository URL', label_key='modules.git.clone.params.url.label',
              description='Git repository URL (HTTPS or SSH)', required=True,
              placeholder='https://github.com/user/repo.git', group=FieldGroup.BASIC),
        field('destination', type='string', label='Destination', label_key='modules.git.clone.params.destination.label',
              description='Local path to clone into', required=True,
              placeholder='/tmp/my-repo', group=FieldGroup.BASIC),
        field('branch', type='string', label='Branch', label_key='modules.git.clone.params.branch.label',
              description='Branch to checkout after clone', placeholder='main',
              group=FieldGroup.OPTIONS),
        field('depth', type='number', label='Depth', label_key='modules.git.clone.params.depth.label',
              description='Shallow clone depth (omit for full clone)', min=1,
              group=FieldGroup.OPTIONS),
        field('token', type='string', label='Access Token', label_key='modules.git.clone.params.token.label',
              description='Personal access token for private repos', format='password',
              placeholder='ghp_xxxxxxxxxxxx', group=FieldGroup.CONNECTION),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether clone succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Local repository path'},
                'branch': {'type': 'string', 'description': 'Current branch'},
                'commit': {
                    'type': 'string',
                    'description': (
                        'HEAD commit hash, or the literal "unknown" when HEAD could '
                        'not be resolved in the clone (an empty remote). Check it '
                        'against an object-name pattern before reading it as a sha'
                    ),
                },
                'outcome': {
                    'type': 'object',
                    'description': (
                        'How far this clone was followed into reality: observed when a '
                        'commit object resolved at the destination, accepted when none '
                        'did, indeterminate when an exception escaped mid-clone'
                    ),
                },
            }
        }
    },
    examples=[
        {
            'title': 'Clone public repository',
            'title_key': 'modules.git.clone.examples.public.title',
            'params': {
                'url': 'https://github.com/user/repo.git',
                'destination': '/tmp/repo'
            }
        },
        {
            'title': 'Shallow clone specific branch',
            'title_key': 'modules.git.clone.examples.shallow.title',
            'params': {
                'url': 'https://github.com/user/repo.git',
                'destination': '/tmp/repo',
                'branch': 'develop',
                'depth': 1
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def git_clone(context: Dict[str, Any]) -> Dict[str, Any]:
    """Clone a git repository"""
    params = context['params']
    url = params['url']
    # SECURITY: git writes a whole tree at destination, with file names and
    # contents taken from the remote repository. Unconfined, a clone can drop
    # attacker-authored files anywhere the process can write — an arbitrary
    # file write with a nicer interface. The URL side already has its own
    # guard (tests/core/test_git_clone_url.py); this is the path side.
    destination = validate_path_with_env_config(str(params['destination']))
    branch = params.get('branch')
    depth = params.get('depth')
    token = params.get('token')

    # SECURITY: reject ext::/file://, option-injecting, and disallowed-scheme URLs
    # before they reach `git clone` (ext:: transport = arbitrary command execution).
    try:
        _validate_clone_url(url)
    except UnsafeCloneURL as e:
        logger.error(f"Git clone refused unsafe url: {e}")
        return {
            'ok': False,
            'error': f'Unsafe clone url: {e}',
            'error_code': 'UNSAFE_URL',
            'outcome': _refused(
                'git_clone_url_refused',
                'The clone URL was refused before git was spawned; nothing left this process.',
                destination=destination,
            ),
        }

    # SECURITY: and where it points. _validate_clone_url bounds the transport;
    # this bounds the destination, so an internal git host or the metadata
    # endpoint cannot be reached through a module that looked "already guarded".
    try:
        _guard_clone_target(url)
    except SSRFError as e:
        logger.warning("Git clone blocked by SSRF guard")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SSRF_BLOCKED',
            'outcome': _refused(
                'git_clone_target_refused',
                'The clone target was refused by the outbound guard before git was '
                'spawned; nothing left this process.',
                destination=destination,
            ),
        }

    clone_url = _inject_token_into_url(url, token) if token and url.startswith('https://') else url
    cmd = _build_clone_cmd(clone_url, destination, branch, depth)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=_build_clone_env(),
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = _sanitize_error(stderr.decode('utf-8', errors='replace').strip(), token)
            logger.error(f"Git clone failed: {error_msg}")
            return {
                'ok': False,
                'error': f'Git clone failed: {error_msg}',
                'error_code': 'CLONE_FAILED',
                'outcome': _refused(
                    'git_clone_rejected',
                    'git clone exited non-zero. git removes a destination it created '
                    'and failed to populate, so no repository was left behind.',
                    destination=destination,
                    exit_code=process.returncode,
                ),
            }

        current_branch, commit_hash = await _get_repo_info(destination)
        logger.info(f"Git clone: {url} -> {destination} (branch={current_branch}, commit={commit_hash[:8]})")
        return {
            'ok': True,
            'data': {
                'path': destination,
                'branch': current_branch,
                'commit': commit_hash,
                'outcome': _clone_outcome(
                    destination=destination,
                    commit_hash=commit_hash,
                    branch=current_branch,
                ),
            },
        }

    except FileNotFoundError:
        return {
            'ok': False,
            'error': 'git command not found. Ensure git is installed.',
            'error_code': 'GIT_NOT_FOUND',
            'outcome': _refused(
                'git_binary_absent',
                'The git executable could not be spawned, so nothing left this process.',
                destination=destination,
            ),
        }
    except Exception as e:
        error_msg = _sanitize_error(str(e), token)
        logger.error(f"Git clone error: {error_msg}")
        # INDETERMINATE, and the only path in this module that is. The `try`
        # spans `communicate()` AND the read-back, so an exception here can land
        # either side of a clone that already wrote a tree. Whether anything
        # exists at the destination is what is not known -- which also makes
        # this the one error a caller must not blindly retry into.
        return {
            'ok': False,
            'error': error_msg,
            'error_code': 'CLONE_ERROR',
            'outcome': envelope(
                Outcome.INDETERMINATE,
                claim_by=ClaimBy.NONE,
                effects=[{
                    'kind': 'git_clone_raised',
                    'destination': destination,
                    'error': f'{type(e).__name__}: {_sanitize_error(str(e), token)}',
                    'measured_by': None,
                    'detail': (
                        'An exception was raised while driving git clone. The '
                        'destination was not inspected afterwards, so whether a '
                        'partial or complete repository exists there is not known.'
                    ),
                }],
            ),
        }
