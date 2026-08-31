# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
File Operation Modules
Basic file system operations

HOW FAR THIS MODULE FOLLOWS REALITY

`file.exists` changes nothing, so there is no effect to follow -- but it is the
one module in this group whose entire output IS a measurement of the world, and
that is what earns OBSERVED. `exists`, `is_file` and `is_directory` are read out
of a `stat` the kernel answered; not one of them is arithmetic on the caller's
own parameters.

`exists=False` is an observation too, and this is the part worth being careful
about. It is NOT the same shape as `database.query`'s empty result set, where
`len(rows) == 0` reads identically whether a statement matched nothing or was
discarded entirely. `ENOENT` is the filesystem's positive answer to the question
that was asked: this name does not resolve. A negative answer is still an
answer.

WHAT THE OLD CODE COULD NOT SAY, and why the stat replaced three `os.path` calls

`os.path.exists` returns False on ANY `OSError`, so it folded three unlike
worlds into one bit:

    the path is not there                        -> a real observation
    a parent directory denies us +x              -> we could not look
    a symlink loop, or a name too long           -> we could not look

Only the first is evidence. The other two are the textbook `indeterminate`: the
observation channel was closed, and reporting the same `False` for them is how a
permissions problem gets read downstream as "the file is gone". `os.stat` is
called once here and the errno is kept, so `FileNotFoundError` (and
`NotADirectoryError`, which is ENOENT's sibling for `a/b/c` where `b` is a file)
stay OBSERVED while everything else becomes INDETERMINATE.

The single call is also why `is_file` and `is_directory` can no longer disagree
with `exists`. Three separate `os.path` probes are three separate races: a path
replaced between them by a directory of the same name used to be able to report
`exists=True, is_file=False, is_directory=False`, a state no filesystem was ever
in. One stat, one mode word, three booleans out of it.

Symlinks follow, exactly as `os.path.exists` did: `os.stat` resolves them, so a
broken symlink is `exists=False` here and was `exists=False` before. That is a
statement about what the name resolves to, which is the question this module is
asked.
"""

from typing import Any, Dict, Optional, Tuple
from ....utils import validate_path_with_env_config
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
import os
import shutil
import stat as stat_module


# ---------------------------------------------------------------------------
# The only line in this module that measures anything. Everything below is a
# reading of the mode word it returns.
# ---------------------------------------------------------------------------
def _stat_once(path: str) -> Tuple[Optional[os.stat_result], Optional[str]]:
    """``(stat_result, None)`` when the kernel answered, ``(None, why)`` when not.

    "Not there" is an answer and comes back as ``(None, None)``: the caller
    distinguishes it from "could not look" by the reason being absent.
    """
    try:
        return os.stat(path), None
    except (FileNotFoundError, NotADirectoryError):
        # ENOENT, and the ENOENT-shaped case where a path component that must
        # be a directory is a file. Both mean the name does not resolve, which
        # is the question that was asked, answered.
        return None, None
    except OSError as error:
        # EACCES on a parent directory, ELOOP, ENAMETOOLONG, EIO. We did not
        # learn whether the path is there.
        return None, f"{type(error).__name__}: {error.strerror or error}"
    except ValueError as error:
        # An embedded null byte never reaches the kernel, so nothing was asked
        # and nothing was learned. `os.path.exists` swallowed this into the
        # same False as a missing file; kept as its own reason instead.
        return None, f"ValueError: {error}"


def _exists_outcome(
    *,
    path: str,
    found: bool,
    stat_error: Optional[str],
) -> Dict[str, Any]:
    """The rung this check earned.

    Two answers, and the split is on whether the kernel answered at all:

    * it answered, either way -> OBSERVED. A `stat` that returned, and a `stat`
      that returned ENOENT, are both measurements of the filesystem.
    * it could not be asked -> INDETERMINATE. `exists` is reported as False for
      backward compatibility, and the envelope is the only thing that says that
      False is a fallback rather than a finding.
    """
    if stat_error is not None:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'path_not_observable',
                'path': path,
                'measured_by': None,
                'reason': stat_error,
                'detail': (
                    'os.stat could not answer, so nothing was learned about this '
                    'path. The reported exists=False is a fallback and not an '
                    'observation: a parent directory we may not traverse, a '
                    'symlink loop and a name too long all land here, and none of '
                    'them means the path is absent.'
                ),
            }],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'path_stat_observed',
            'path': path,
            'exists': found,
            'measured_by': 'os.stat(path), once, symlinks resolved',
            'detail': (
                'The kernel answered. When exists is False that answer was '
                'ENOENT -- the name does not resolve -- which is a finding and '
                'not an absence of one. is_file and is_directory are read from '
                'the mode word of this same stat, so they cannot disagree with '
                'each other or with exists.'
            ),
        }],
    )


@register_module(
    module_id='file.exists',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'io', 'check', 'atomic', 'path_restricted'],
    label='Check File Exists',
    label_key='modules.file.exists.label',
    description='Check if a file or directory exists',
    description_key='modules.file.exists.description',
    icon='FileSearch',
    color='#6B7280',


    # Type definitions for connection validation
    input_types=['string'],
    output_types=['boolean'],

    can_receive_from=['*'],
    can_connect_to=['*'],    # Execution settings
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['filesystem.read'],

    # Schema-driven params
    params_schema=compose(
        presets.FILE_PATH(key='path', required=True, label='Path', placeholder='/path/to/file'),
    ),
    output_schema={
        'exists': {
            'type': 'boolean',
            'description': (
                'Whether path exists. False also when the path could not be '
                'inspected at all -- read outcome.rung to tell a finding from a '
                'fallback'
            )
        ,
                'description_key': 'modules.file.exists.output.exists.description'},
        'is_file': {
            'type': 'boolean',
            'description': 'Whether path is a file'
        ,
                'description_key': 'modules.file.exists.output.is_file.description'},
        'is_directory': {
            'type': 'boolean',
            'description': 'Whether path is a directory'
        ,
                'description_key': 'modules.file.exists.output.is_directory.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this check was followed into reality: observed when the '
                'stat answered (including ENOENT), indeterminate when it could '
                'not be asked'
            )
        ,
                'description_key': 'modules.file.exists.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Check file exists',
            'title_key': 'modules.file.exists.examples.check.title',
            'params': {
                'path': '/tmp/data.txt'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
)
async def file_exists(context):
    """Check if file exists"""
    params = context['params']
    # SECURITY: an unconfined path turns this into a host filesystem oracle —
    # probe for /etc/kubernetes, ~/.aws/credentials, container markers — which
    # is the reconnaissance step ahead of the read and write advisories.
    path = validate_path_with_env_config(str(params['path']))

    # One syscall, three booleans. See the module docstring for why this is not
    # three os.path calls any more.
    stat_result, stat_error = _stat_once(path)

    exists = stat_result is not None
    is_file = exists and stat_module.S_ISREG(stat_result.st_mode)
    is_directory = exists and stat_module.S_ISDIR(stat_result.st_mode)

    return {
        'ok': True,
        'data': {
            'exists': exists,
            'is_file': is_file,
            'is_directory': is_directory,
            'outcome': _exists_outcome(
                path=path,
                found=exists,
                stat_error=stat_error,
            ),
        }
    }
