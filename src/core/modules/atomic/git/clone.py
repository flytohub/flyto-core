# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Git Clone Module
Clone a git repository to a local path
"""

import asyncio
import logging
import os
from typing import Any, Dict
from urllib.parse import urlparse, urlunparse

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


logger = logging.getLogger(__name__)


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
    cmd.extend([clone_url, destination])
    return cmd


async def _get_repo_info(destination: str) -> tuple:
    """Get current branch and HEAD commit hash from cloned repo."""
    branch_proc = await asyncio.create_subprocess_exec(
        'git', '-C', destination, 'rev-parse', '--abbrev-ref', 'HEAD',
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    branch_out, _ = await branch_proc.communicate()
    current_branch = branch_out.decode('utf-8').strip() if branch_proc.returncode == 0 else 'unknown'

    commit_proc = await asyncio.create_subprocess_exec(
        'git', '-C', destination, 'rev-parse', 'HEAD',
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    commit_out, _ = await commit_proc.communicate()
    commit_hash = commit_out.decode('utf-8').strip() if commit_proc.returncode == 0 else 'unknown'

    return current_branch, commit_hash


def _sanitize_error(error_msg: str, token: str = None) -> str:
    """Remove token from error messages."""
    if token:
        error_msg = error_msg.replace(token, '***')
    return error_msg


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
    required_permissions=['filesystem.write', 'network.connect'],

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
                'commit': {'type': 'string', 'description': 'HEAD commit hash'},
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
    author='Flyto Team',
    license='MIT'
)
async def git_clone(context: Dict[str, Any]) -> Dict[str, Any]:
    """Clone a git repository"""
    params = context['params']
    url = params['url']
    destination = os.path.abspath(os.path.expanduser(params['destination']))
    branch = params.get('branch')
    depth = params.get('depth')
    token = params.get('token')

    clone_url = _inject_token_into_url(url, token) if token and url.startswith('https://') else url
    cmd = _build_clone_cmd(clone_url, destination, branch, depth)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = _sanitize_error(stderr.decode('utf-8', errors='replace').strip(), token)
            logger.error(f"Git clone failed: {error_msg}")
            return {'ok': False, 'error': f'Git clone failed: {error_msg}', 'error_code': 'CLONE_FAILED'}

        current_branch, commit_hash = await _get_repo_info(destination)
        logger.info(f"Git clone: {url} -> {destination} (branch={current_branch}, commit={commit_hash[:8]})")
        return {'ok': True, 'data': {'path': destination, 'branch': current_branch, 'commit': commit_hash}}

    except FileNotFoundError:
        return {'ok': False, 'error': 'git command not found. Ensure git is installed.', 'error_code': 'GIT_NOT_FOUND'}
    except Exception as e:
        error_msg = _sanitize_error(str(e), token)
        logger.error(f"Git clone error: {error_msg}")
        return {'ok': False, 'error': error_msg, 'error_code': 'CLONE_ERROR'}
