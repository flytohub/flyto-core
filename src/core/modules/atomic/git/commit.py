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
async def git_commit(context: Dict[str, Any]) -> Dict[str, Any]:
    """Create a git commit"""
    params = context['params']
    repo_path = params['repo_path']
    message = params['message']
    add_all = params.get('add_all', False)
    files = params.get('files', [])
    author_name = params.get('author_name')
    author_email = params.get('author_email')

    repo_path = os.path.abspath(os.path.expanduser(repo_path))

    if not os.path.isdir(os.path.join(repo_path, '.git')):
        return {
            'ok': False,
            'error': f'Not a git repository: {repo_path}',
            'error_code': 'NOT_A_REPO'
        }

    async def run_git(*args: str) -> tuple:
        proc = await asyncio.create_subprocess_exec(
            'git', '-C', repo_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode, out.decode('utf-8', errors='replace'), err.decode('utf-8', errors='replace')

    try:
        # Stage files
        if add_all:
            rc, _, err = await run_git('add', '-A')
            if rc != 0:
                return {
                    'ok': False,
                    'error': f'git add -A failed: {err.strip()}',
                    'error_code': 'STAGE_FAILED'
                }
        elif files:
            for f in files:
                rc, _, err = await run_git('add', f)
                if rc != 0:
                    return {
                        'ok': False,
                        'error': f'git add failed for {f}: {err.strip()}',
                        'error_code': 'STAGE_FAILED'
                    }

        # Build commit command
        commit_args: List[str] = ['commit', '-m', message]

        if author_name and author_email:
            commit_args.extend(['--author', f'{author_name} <{author_email}>'])

        rc, out, err = await run_git(*commit_args)

        if rc != 0:
            error_msg = err.strip() or out.strip()
            if 'nothing to commit' in error_msg or 'nothing to commit' in out:
                return {
                    'ok': False,
                    'error': 'Nothing to commit, working tree clean',
                    'error_code': 'NOTHING_TO_COMMIT'
                }
            return {
                'ok': False,
                'error': f'git commit failed: {error_msg}',
                'error_code': 'COMMIT_FAILED'
            }

        # Get the new commit hash
        rc, hash_out, _ = await run_git('rev-parse', 'HEAD')
        commit_hash = hash_out.strip() if rc == 0 else 'unknown'

        # Count files changed via diff --stat
        rc, stat_out, _ = await run_git('diff', '--stat', 'HEAD~1', 'HEAD')
        files_changed = 0
        if rc == 0 and stat_out.strip():
            lines = stat_out.strip().split('\n')
            # Last line is summary like " 3 files changed, 10 insertions(+), 2 deletions(-)"
            if lines:
                summary = lines[-1]
                for part in summary.split(','):
                    part = part.strip()
                    if 'file' in part:
                        try:
                            files_changed = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass

        logger.info(f"Git commit: {commit_hash[:8]} '{message[:50]}' ({files_changed} files)")

        return {
            'ok': True,
            'data': {
                'commit_hash': commit_hash,
                'message': message,
                'files_changed': files_changed,
            }
        }

    except FileNotFoundError:
        return {
            'ok': False,
            'error': 'git command not found. Ensure git is installed.',
            'error_code': 'GIT_NOT_FOUND'
        }

    except Exception as e:
        logger.error(f"Git commit error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'COMMIT_ERROR'
        }
