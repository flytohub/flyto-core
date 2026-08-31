# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Git Commit Module
Create a git commit in a local repository

HOW FAR THIS MODULE FOLLOWS REALITY

Five return paths, and only one of them can say anything above ACCEPTED.

What made this module worth opening is that it already returned a commit sha,
and a sha *looks* like the strongest evidence in this whole group: 40 hex
characters naming a real object in a real object store. It is not, on its own.
``git rev-parse HEAD`` after a commit answers "what is HEAD now", and HEAD
resolves to something in any repository with any history at all. Apply the test
this contract runs on every number -- would this value be the same if the effect
had not happened? -- and a bare post-commit sha fails it: with no commit created,
`rev-parse HEAD` still returns a sha, just the previous one. It is the same
shape as ``file.write``'s append mode, where a bare ``st_size`` says how big the
file is and not that our bytes are the reason.

So the sha is read TWICE, once before the commit and once after, and what earns
OBSERVED is the pair:

    head moved, before -> after                     OBSERVED
        Two reads of the repository's own ref, and they differ. A new commit
        object is at HEAD and was not there a moment ago. `claim_by` is
        INFERRED: "HEAD moved" is this module's predicate, not one any caller
        stated.

    HEAD did not resolve before and resolves now     OBSERVED
        The first commit in a fresh repository. `rev-parse --verify HEAD` fails
        on an unborn HEAD, so there is no baseline sha -- but "no commit was
        reachable from HEAD, and now one is" is itself a measured change, not a
        missing measurement.

    HEAD could not be read after the commit          ACCEPTED
        `git commit` exited 0 and nothing was read back. That is the OS and git
        acknowledging the instruction, and no more.

    git exited 0 and HEAD did not move               INDETERMINATE
        Should not happen. It is reported as "we cannot say" rather than FAILED
        because the predicate is ours: an inference of this module's that may
        simply be wrong is exactly the case `outcome.py` splits on claimant.

`files_changed` is deliberately NOT what any rung rests on, and it is worth
saying why in the file rather than in a review comment. It comes from
``git diff --stat HEAD~1 HEAD``, which has no `HEAD~1` on a root commit; that
call exits non-zero and `files_changed` becomes a literal 0 written below. A
commit that created twelve files reports 0 there. Hanging OBSERVED on it would
have reproduced the `database.query` defect precisely -- a count that reads
identically whether the effect was enormous or absent. It travels as an effect
with `diffstat_available` beside it so the 0 stays readable as "not measured".

Nothing here reaches VERIFIED, and no `postcondition=` is declared. HEAD moving
is not the caller's goal; "the requested message and the staged files are in the
new commit" would be, and this module never looks. Declaring the predicate
without evaluating it would move the overclaim one level up, which is the one
thing worse than not claiming.
"""

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import validate_path_with_env_config
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


logger = logging.getLogger(__name__)

#: git object names, in both hash algorithms git can be configured with. Used
#: only to decide whether a `rev-parse` answer is a measurement or the module's
#: own 'unknown' sentinel travelling under a name that looks like data.
_OBJECT_NAME = re.compile(r'^[0-9a-f]{40}$|^[0-9a-f]{64}$')


async def _run_git(repo_path: str, *args: str) -> tuple:
    """Run a git command in the given repo and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        'git', '-C', repo_path, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode('utf-8', errors='replace'), err.decode('utf-8', errors='replace')


async def _head_sha(repo_path: str) -> Optional[str]:
    """The object name HEAD resolves to, or ``None`` when it resolves to nothing.

    ``--verify`` is what makes the ``None`` meaningful. Plain ``rev-parse HEAD``
    on an unborn HEAD prints the literal string ``HEAD`` on stdout alongside its
    error; ``--verify`` refuses to print anything that is not an object name, so
    a caller of this function can trust that a returned value is a sha and that
    ``None`` means "nothing is reachable from HEAD" rather than "a word came
    back that I did not check".
    """
    rc, out, _ = await _run_git(repo_path, 'rev-parse', '--verify', 'HEAD')
    candidate = out.strip()
    if rc == 0 and _OBJECT_NAME.match(candidate):
        return candidate
    return None


async def _stage_files(repo_path: str, add_all: bool, files: List[str]):
    """Stage files for commit. Returns error dict on failure, None on success."""
    if add_all:
        rc, _, err = await _run_git(repo_path, 'add', '-A')
        if rc != 0:
            return {
                'ok': False,
                'error': f'git add -A failed: {err.strip()}',
                'error_code': 'STAGE_FAILED',
                'outcome': _refused(
                    'git_stage_failed',
                    'git add -A exited non-zero, so no commit was attempted.',
                    repo_path=repo_path,
                ),
            }
    elif files:
        for f in files:
            rc, _, err = await _run_git(repo_path, 'add', f)
            if rc != 0:
                return {
                    'ok': False,
                    'error': f'git add failed for {f}: {err.strip()}',
                    'error_code': 'STAGE_FAILED',
                    'outcome': _refused(
                        'git_stage_failed',
                        f'git add exited non-zero for {f!r}, so no commit was attempted.',
                        repo_path=repo_path,
                    ),
                }
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


def _refused(kind: str, detail: str, **fields: Any) -> Dict[str, Any]:
    """The envelope for a path where no commit object was created.

    FAILED and not INDETERMINATE on every one of them, and the reason is that
    git is unusually good at this: `git commit` is atomic with respect to the
    ref it moves, and each of these paths is a definite report from a process
    that ran to completion and refused. Nothing is left in an unknown state for
    a consumer to wonder about, so "we cannot say" would be a weaker statement
    than the truth.
    """
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[dict({'kind': kind, 'measured_by': None, 'detail': detail}, **fields)],
    )


def _commit_outcome(
    *,
    repo_path: str,
    head_before: Optional[str],
    head_after: Optional[str],
    files_changed: int,
    diffstat_available: bool,
) -> Dict[str, Any]:
    """The rung this commit earned. See the module docstring for the four cases."""
    diffstat_effect = {
        'kind': 'git_commit_diffstat',
        'files_changed': files_changed,
        'diffstat_available': diffstat_available,
        'measured_by': (
            'git diff --stat HEAD~1 HEAD' if diffstat_available else None
        ),
        'detail': (
            'File count parsed from the diff between this commit and its parent.'
            if diffstat_available else
            'No diffstat was read -- a root commit has no HEAD~1, so the '
            'files_changed of 0 beside this is a literal written by the module '
            'and not a count of anything. It is carried so a consumer can tell '
            'the two kinds of zero apart; no rung rests on it.'
        ),
    }

    if head_after is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                {
                    'kind': 'git_head_not_read_back',
                    'repo_path': repo_path,
                    'head_before': head_before,
                    'measured_by': None,
                    'detail': (
                        'git commit exited 0 and HEAD could not be resolved '
                        'afterwards, so nothing was read back. The commit was '
                        'accepted by git and followed no further.'
                    ),
                },
                diffstat_effect,
            ],
        )

    moved_effect = {
        'kind': 'git_head_moved',
        'repo_path': repo_path,
        'head_before': head_before,
        'head_after': head_after,
        'measured_by': (
            'git rev-parse --verify HEAD, read once before the commit and once '
            'after'
        ),
        'detail': (
            'The repository ref moved to a commit object that was not at HEAD '
            'before. Not a claim about the commit\'s contents: nothing here '
            'reads the message, the tree, or the staged paths back.'
            if head_before is not None else
            'HEAD resolved to nothing before this commit and resolves to a '
            'commit object now. That transition is the measurement, and the '
            'absence of a baseline sha is part of it rather than a gap in it. '
            'The ordinary cause is a root commit in a fresh repository; a '
            'rev-parse that failed for some other reason would land here too, '
            'though a repository broken enough for that would not have let the '
            'commit itself exit 0.'
        ),
    }

    if head_before == head_after:
        return envelope(
            Outcome.INDETERMINATE,
            # INFERRED: "a successful commit moves HEAD" is this module's own
            # predicate. A caller's broken contract would be FAILED; an
            # inference of ours that may be wrong is this.
            claim_by=ClaimBy.INFERRED,
            postcondition='git rev-parse --verify HEAD differs before and after the commit',
            effects=[
                dict(
                    moved_effect,
                    kind='git_head_did_not_move',
                    detail=(
                        'git commit exited 0 and HEAD resolves to the same '
                        'object it did before. Either no commit was created '
                        'despite the exit status, or this module\'s assumption '
                        'that a commit moves HEAD does not hold here. We cannot '
                        'say which, so this is indeterminate rather than failed.'
                    ),
                ),
                diffstat_effect,
            ],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.INFERRED,
        postcondition='git rev-parse --verify HEAD differs before and after the commit',
        effects=[moved_effect, diffstat_effect],
    )


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
              description='Override commit author email', placeholder='dev@flyto2.com',
              group=FieldGroup.ADVANCED),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether commit succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'commit_hash': {'type': 'string', 'description': 'New commit hash'},
                'head_before': {
                    'type': 'string',
                    'description': (
                        'Object HEAD resolved to before the commit, or null on an '
                        'unborn HEAD. Present so commit_hash can be read as a change '
                        'rather than as a restatement of where HEAD happens to be'
                    ),
                },
                'message': {'type': 'string', 'description': 'Commit message'},
                'files_changed': {
                    'type': 'number',
                    'description': (
                        'Files in the diff between this commit and its parent. 0 for a '
                        'root commit, which has no parent to diff against -- see '
                        'outcome.effects[].diffstat_available before reading a 0 as '
                        '"changed nothing"'
                    ),
                },
                'outcome': {
                    'type': 'object',
                    'description': (
                        'How far this commit was followed into reality: observed when '
                        'HEAD moved, accepted when HEAD could not be read back, '
                        'indeterminate when git exited 0 and HEAD did not move'
                    ),
                },
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
    author='Flyto2 Team',
    license='MIT'
)
async def git_commit(context: Dict[str, Any]) -> Dict[str, Any]:
    """Create a git commit"""
    params = context['params']
    # SECURITY: `git -C repo_path add/commit` writes into whatever tree this
    # names, under the same filesystem.write permission the arbitrary file
    # write advisories covered. The `files` param stays unvalidated: git
    # resolves a pathspec relative to repo_path, which is now confined.
    repo_path = validate_path_with_env_config(str(params['repo_path']))
    message = params['message']
    author_name = params.get('author_name')
    author_email = params.get('author_email')

    if not os.path.isdir(os.path.join(repo_path, '.git')):
        return {
            'ok': False,
            'error': f'Not a git repository: {repo_path}',
            'error_code': 'NOT_A_REPO',
            'outcome': _refused(
                'git_repo_absent',
                'No .git directory at this path, so no git process was started.',
                repo_path=repo_path,
            ),
        }

    try:
        stage_error = await _stage_files(repo_path, params.get('add_all', False), params.get('files', []))
        if stage_error:
            return stage_error

        # STAGE 1 of the measurement -- see the module docstring. Read before
        # the commit so the sha read afterwards is a change and not a reading.
        head_before = await _head_sha(repo_path)

        commit_args: List[str] = ['commit', '-m', message]
        if author_name and author_email:
            commit_args.extend(['--author', f'{author_name} <{author_email}>'])

        rc, out, err = await _run_git(repo_path, *commit_args)
        if rc != 0:
            error_msg = err.strip() or out.strip()
            if 'nothing to commit' in error_msg or 'nothing to commit' in out:
                return {
                    'ok': False,
                    'error': 'Nothing to commit, working tree clean',
                    'error_code': 'NOTHING_TO_COMMIT',
                    'outcome': _refused(
                        'git_nothing_to_commit',
                        'git found no staged difference and created no commit.',
                        repo_path=repo_path,
                        head=head_before,
                    ),
                }
            return {
                'ok': False,
                'error': f'git commit failed: {error_msg}',
                'error_code': 'COMMIT_FAILED',
                'outcome': _refused(
                    'git_commit_rejected',
                    'git commit exited non-zero; no commit object was created.',
                    repo_path=repo_path,
                    head=head_before,
                    exit_code=rc,
                ),
            }

        # STAGE 2 -- the only other line in this module that measures the
        # repository rather than restating an input.
        head_after = await _head_sha(repo_path)
        commit_hash = head_after if head_after is not None else 'unknown'

        rc, stat_out, _ = await _run_git(repo_path, 'diff', '--stat', 'HEAD~1', 'HEAD')
        diffstat_available = rc == 0
        files_changed = _parse_files_changed(stat_out) if diffstat_available else 0

        logger.info(f"Git commit: {commit_hash[:8]} '{message[:50]}' ({files_changed} files)")
        return {
            'ok': True,
            'data': {
                'commit_hash': commit_hash,
                'head_before': head_before,
                'message': message,
                'files_changed': files_changed,
                'outcome': _commit_outcome(
                    repo_path=repo_path,
                    head_before=head_before,
                    head_after=head_after,
                    files_changed=files_changed,
                    diffstat_available=diffstat_available,
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
                repo_path=repo_path,
            ),
        }
    except Exception as e:
        logger.error(f"Git commit error: {e}")
        # INDETERMINATE, unlike every other error path here. The others are git
        # reporting a refusal; this is our own process raising somewhere inside a
        # sequence that spawns subprocesses, and it can land after `git commit`
        # has already moved the ref. Whether a commit exists is exactly what is
        # not known, which is what this rung is for.
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'COMMIT_ERROR',
            'outcome': envelope(
                Outcome.INDETERMINATE,
                claim_by=ClaimBy.NONE,
                effects=[{
                    'kind': 'git_commit_raised',
                    'repo_path': repo_path,
                    'error': f'{type(e).__name__}: {e}',
                    'measured_by': None,
                    'detail': (
                        'An exception was raised while driving git. HEAD was not '
                        'read afterwards, so whether a commit object was created '
                        'is not known.'
                    ),
                }],
            ),
        }
