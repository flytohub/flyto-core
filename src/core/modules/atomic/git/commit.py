# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Git Commit Module
Create a git commit in a local repository
"""

import asyncio
import logging
import os
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


logger = logging.getLogger(__name__)


@register_module(
    module_id='git.commit',
    version='1.0.0',
    category='atomic',
    subcategory='git',
    tags=['git', 'commit', 'version-control', 'devops'],
    label='Git Commit',
    label_key='modules.git.commit.label',
    description='Create a git commit',
    description_key='modules.git.commit.description',
    icon='GitCommit',
    color='#F05032',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=60000,
    retryable=False,
    concurrent_safe=False,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        field('repo_path', type='string', label='Repository Path', label_key='modules.git.commit.params.repo_path.label',
              description='Path to git repository', required=True,
              placeholder='/home/user/project', group=FieldGroup.BASIC),
        field('message', type='string', label='Commit Message', label_key='modules.git.commit.params.message.label',
              description='Commit message', required=True, format='multiline',
              placeholder='feat: add new feature', group=FieldGroup.BASIC),
        field('add_all', type='boolean', label='Add All', label_key='modules.git.commit.params.add_all.label',
              description='Stage all changes before committing (git add -A)', default=False,
              group=FieldGroup.OPTIONS),
        field('files', type='array', label='Files', label_key='modules.git.commit.params.files.label',
              description='Specific files to stage before committing',
              items={'type': 'string'},
              group=FieldGroup.OPTIONS),
        field('author_name', type='string', label='Author Name', label_key='modules.git.commit.params.author_name.label',
              description='Override commit author name', placeholder='John Doe',
              group=FieldGroup.ADVANCED),
        field('author_email', type='string', label='Author Email', label_key='modules.git.commit.params.author_email.label',
              description='Override commit author email', placeholder='john@example.com',
              group=FieldGroup.ADVANCED),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether commit succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'commit_hash': {'type': 'string', 'description': 'New commit hash'},
                'message': {'type': 'string', 'description': 'Commit message'},
                'files_changed': {'type': 'number', 'description': 'Number of files changed'},
            }
        }
    },
    examples=[
        {
            'title': 'Commit all changes',
            'title_key': 'modules.git.commit.examples.all.title',
            'params': {
                'repo_path': '/home/user/project',
                'message': 'feat: add user authentication',
                'add_all': True
            }
        },
        {
            'title': 'Commit specific files',
            'title_key': 'modules.git.commit.examples.files.title',
            'params': {
                'repo_path': '/home/user/project',
                'message': 'fix: correct typo in readme',
                'files': ['README.md']
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def _run_git(repo_path: str, *args: str) -> tuple:
    """Run a git command in the given repo and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        'git', '-C', repo_path, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode('utf-8', errors='replace'), err.decode('utf-8', errors='replace')


async def _stage_files(repo_path: str, add_all: bool, files: List[str]):
    """Stage files for commit. Returns error dict on failure, None on success."""
    if add_all:
        rc, _, err = await _run_git(repo_path, 'add', '-A')
        if rc != 0:
            return {'ok': False, 'error': f'git add -A failed: {err.strip()}', 'error_code': 'STAGE_FAILED'}
    elif files:
        for f in files:
            rc, _, err = await _run_git(repo_path, 'add', f)
            if rc != 0:
                return {'ok': False, 'error': f'git add failed for {f}: {err.strip()}', 'error_code': 'STAGE_FAILED'}
    return None


def _parse_files_changed(stat_out: str) -> int:
    """Parse files changed count from git diff --stat output."""
    if not stat_out.strip():
        return 0
    lines = stat_out.strip().split('\n')
    if not lines:
        return 0
    summary = lines[-1]
    for part in summary.split(','):
        part = part.strip()
        if 'file' in part:
            try:
                return int(part.split()[0])
            except (ValueError, IndexError):
                pass
    return 0


async def git_commit(context: Dict[str, Any]) -> Dict[str, Any]:
    """Create a git commit"""
    params = context['params']
    repo_path = os.path.abspath(os.path.expanduser(params['repo_path']))
    message = params['message']
    author_name = params.get('author_name')
    author_email = params.get('author_email')

    if not os.path.isdir(os.path.join(repo_path, '.git')):
        return {'ok': False, 'error': f'Not a git repository: {repo_path}', 'error_code': 'NOT_A_REPO'}

    try:
        stage_error = await _stage_files(repo_path, params.get('add_all', False), params.get('files', []))
        if stage_error:
            return stage_error

        commit_args: List[str] = ['commit', '-m', message]
        if author_name and author_email:
            commit_args.extend(['--author', f'{author_name} <{author_email}>'])

        rc, out, err = await _run_git(repo_path, *commit_args)
        if rc != 0:
            error_msg = err.strip() or out.strip()
            if 'nothing to commit' in error_msg or 'nothing to commit' in out:
                return {'ok': False, 'error': 'Nothing to commit, working tree clean', 'error_code': 'NOTHING_TO_COMMIT'}
            return {'ok': False, 'error': f'git commit failed: {error_msg}', 'error_code': 'COMMIT_FAILED'}

        rc, hash_out, _ = await _run_git(repo_path, 'rev-parse', 'HEAD')
        commit_hash = hash_out.strip() if rc == 0 else 'unknown'

        rc, stat_out, _ = await _run_git(repo_path, 'diff', '--stat', 'HEAD~1', 'HEAD')
        files_changed = _parse_files_changed(stat_out) if rc == 0 else 0

        logger.info(f"Git commit: {commit_hash[:8]} '{message[:50]}' ({files_changed} files)")
        return {'ok': True, 'data': {'commit_hash': commit_hash, 'message': message, 'files_changed': files_changed}}

    except FileNotFoundError:
        return {'ok': False, 'error': 'git command not found. Ensure git is installed.', 'error_code': 'GIT_NOT_FOUND'}
    except Exception as e:
        logger.error(f"Git commit error: {e}")
        return {'ok': False, 'error': str(e), 'error_code': 'COMMIT_ERROR'}
