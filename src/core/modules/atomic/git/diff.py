# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Git Diff Module
Get git diff output with statistics
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


async def _run_git(repo_path: str, *args: str) -> tuple:
    """Run a git command in the given repo and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        'git', '-C', repo_path, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode('utf-8', errors='replace'), err.decode('utf-8', errors='replace')


def _build_diff_args(staged: bool, ref1: str, ref2: str = None, extra_flags: List[str] = None) -> List[str]:
    """Build git diff argument list."""
    args: List[str] = ['diff']
    if staged:
        args.append('--cached')
    elif ref2:
        args.extend([ref1, ref2])
    else:
        args.append(ref1)
    if extra_flags:
        args.extend(extra_flags)
    return args


def _parse_numstat(numstat_out: str) -> tuple:
    """Parse git diff --numstat output into (files_changed, insertions, deletions)."""
    files_changed = 0
    insertions = 0
    deletions = 0
    if not numstat_out.strip():
        return files_changed, insertions, deletions
    for line in numstat_out.strip().split('\n'):
        parts = line.split('\t')
        if len(parts) >= 3:
            files_changed += 1
            try:
                insertions += int(parts[0])
            except ValueError:
                pass
            try:
                deletions += int(parts[1])
            except ValueError:
                pass
    return files_changed, insertions, deletions


@register_module(
    module_id='git.diff',
    version='1.0.0',
    category='atomic',
    subcategory='git',
    tags=['git', 'diff', 'changes', 'devops'],
    label='Git Diff',
    label_key='modules.git.diff.label',
    description='Get git diff',
    description_key='modules.git.diff.description',
    icon='GitPullRequest',
    color='#F05032',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=60000,
    retryable=True,
    max_retries=1,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['filesystem.read'],

    params_schema=compose(
        field('repo_path', type='string', label='Repository Path', label_key='modules.git.diff.params.repo_path.label',
              description='Path to git repository', required=True,
              placeholder='/home/user/project', group=FieldGroup.BASIC),
        field('ref1', type='string', label='Reference 1', label_key='modules.git.diff.params.ref1.label',
              description='First reference (commit, branch, tag)', default='HEAD',
              placeholder='HEAD', group=FieldGroup.OPTIONS),
        field('ref2', type='string', label='Reference 2', label_key='modules.git.diff.params.ref2.label',
              description='Second reference to compare against',
              placeholder='main', group=FieldGroup.OPTIONS),
        field('staged', type='boolean', label='Staged Only', label_key='modules.git.diff.params.staged.label',
              description='Show only staged changes (--cached)', default=False,
              group=FieldGroup.OPTIONS),
        field('stat_only', type='boolean', label='Stats Only', label_key='modules.git.diff.params.stat_only.label',
              description='Show only file statistics (--stat)', default=False,
              group=FieldGroup.OPTIONS),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether diff succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'diff': {'type': 'string', 'description': 'Diff output'},
                'files_changed': {'type': 'number', 'description': 'Number of files changed'},
                'insertions': {'type': 'number', 'description': 'Number of line insertions'},
                'deletions': {'type': 'number', 'description': 'Number of line deletions'},
            }
        }
    },
    examples=[
        {
            'title': 'Show unstaged changes',
            'title_key': 'modules.git.diff.examples.unstaged.title',
            'params': {
                'repo_path': '/home/user/project'
            }
        },
        {
            'title': 'Compare branches',
            'title_key': 'modules.git.diff.examples.branches.title',
            'params': {
                'repo_path': '/home/user/project',
                'ref1': 'main',
                'ref2': 'feature/login'
            }
        },
        {
            'title': 'Show staged changes stats',
            'title_key': 'modules.git.diff.examples.staged.title',
            'params': {
                'repo_path': '/home/user/project',
                'staged': True,
                'stat_only': True
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def git_diff(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get git diff"""
    params = context['params']
    repo_path = os.path.abspath(os.path.expanduser(params['repo_path']))
    ref1 = params.get('ref1', 'HEAD')
    ref2 = params.get('ref2')
    staged = params.get('staged', False)
    stat_only = params.get('stat_only', False)

    if not os.path.isdir(os.path.join(repo_path, '.git')):
        return {'ok': False, 'error': f'Not a git repository: {repo_path}', 'error_code': 'NOT_A_REPO'}

    try:
        diff_args = _build_diff_args(staged, ref1, ref2, ['--stat'] if stat_only else None)
        rc, diff_out, err = await _run_git(repo_path, *diff_args)
        if rc != 0:
            return {'ok': False, 'error': f'git diff failed: {err.strip()}', 'error_code': 'DIFF_FAILED'}

        numstat_args = _build_diff_args(staged, ref1, ref2, ['--numstat'])
        rc, numstat_out, _ = await _run_git(repo_path, *numstat_args)
        files_changed, insertions, deletions = _parse_numstat(numstat_out) if rc == 0 else (0, 0, 0)

        logger.info(f"Git diff: {files_changed} files, +{insertions}/-{deletions}")
        return {'ok': True, 'data': {'diff': diff_out, 'files_changed': files_changed, 'insertions': insertions, 'deletions': deletions}}

    except FileNotFoundError:
        return {'ok': False, 'error': 'git command not found. Ensure git is installed.', 'error_code': 'GIT_NOT_FOUND'}
    except Exception as e:
        logger.error(f"Git diff error: {e}")
        return {'ok': False, 'error': str(e), 'error_code': 'DIFF_ERROR'}
