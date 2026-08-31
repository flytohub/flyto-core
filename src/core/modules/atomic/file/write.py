# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
File Operation Modules
Basic file system operations
"""

from typing import Any, Dict, Optional, Tuple
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_path_with_env_config, PathTraversalError
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...errors import ModuleError
import os
import shutil


# ---------------------------------------------------------------------------
# STAGE 2 -- the only lines in this module that measure the world.
#
# Everything else here is arithmetic on the caller's own string. `os.stat` after
# the file handle has closed reads the file that now exists, which is what makes
# a claim of OBSERVED something other than a restatement of the input. The
# measurement is kept in its own function so the two stages stay separable: when
# it cannot answer, the module falls back to exactly the ACCEPTED claim it made
# before an observation existed here at all.
#
# What it does NOT establish: durability. There is no fsync, so st_size is the
# size the kernel reports for a file whose bytes may still be in the page cache.
# "The write reached the disk platter" is not observed and is not claimed.
# ---------------------------------------------------------------------------
def _observe_size_on_disk(path: str) -> Tuple[Optional[int], Optional[str]]:
    """``(st_size, None)`` when the file could be read back, ``(None, why)`` when not.

    A failure here is not a failure of the write. `open`/`write`/`close` already
    returned without raising; all that is lost is our ability to look. The rung
    is lowered to match, and the reason travels in the effect so the gap is
    visible rather than absent.
    """
    try:
        return os.stat(path).st_size, None
    except OSError as error:
        return None, f"{type(error).__name__}: {error.strerror or error}"


def _size_before_write(path: str, is_append: bool) -> Optional[int]:
    """The byte count this write starts from, or ``None`` when it cannot be read.

    ``'w'`` truncates the file at open, so its baseline is zero by the guarantee
    of the mode itself and costs no syscall. ``'a'`` keeps whatever was there, so
    the only way to read a *change* out of ``st_size`` afterwards is to have
    measured before -- a bare post-write size in append mode says how big the
    file is, not that our bytes are the reason.
    """
    if not is_append:
        return 0
    try:
        return os.stat(path).st_size
    except FileNotFoundError:
        # Absent is itself an observation, and an absent file contributes no
        # bytes. This is a real baseline, not a guess.
        return 0
    except OSError:
        return None


def _write_outcome(
    *,
    offered_bytes: int,
    baseline: Optional[int],
    observed_size: Optional[int],
    observation_error: Optional[str],
    encoding: str,
) -> Dict[str, Any]:
    """The rung this write earned, and the measurements that earned it.

    Three answers, one per outcome of the measurement:

    * measured, and the file grew by exactly the bytes offered -> OBSERVED.
    * measured, and it did not -> INDETERMINATE, not FAILED. Nobody declared a
      size contract: the equality is this module's own inference, and there are
      ordinary correct writes it is false for (``newline=None`` translates
      ``'\\n'`` to ``os.linesep`` on Windows, so content with newlines lands
      longer than ``len(content.encode(...))`` with nothing wrong). `outcome.py`
      splits exactly this case on who made the claim -- a caller's broken
      contract is FAILED, an inference of ours that may simply be wrong is
      INDETERMINATE -- and this is the second one. Calling it FAILED would put
      a red mark on correct writes on one platform.
    * not measured at all -> ACCEPTED. The OS acknowledged taking the bytes and
      nothing followed them further.

    ACCEPTED is also the honest floor: `open`/`write`/`close` returning without
    raising is an acknowledgement of receipt, not evidence the bytes landed.
    """
    offered_effect = {
        'kind': 'file_bytes_offered',
        'bytes': offered_bytes,
        'measured_by': 'len(content.encode(encoding))',
        'detail': (
            f'Length of the content handed to this module, encoded as {encoding!r}. '
            'This is the size of the content OFFERED, not of the file on disk: no '
            'syscall contributes to it, and it reads identically whether the file '
            'received every byte, some of them, or none.'
        ),
    }

    if observed_size is None or baseline is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                offered_effect,
                {
                    'kind': 'file_size_not_observed',
                    'measured_by': None,
                    'reason': observation_error or (
                        'no pre-write baseline for append mode, so no change '
                        'could be read out of the size afterwards'
                    ),
                    'detail': (
                        'The file was not read back. The write was accepted by the '
                        'OS and followed no further.'
                    ),
                },
            ],
        )

    observed_effect = {
        'kind': 'file_size_observed',
        'bytes_on_disk': observed_size,
        'bytes_added': observed_size - baseline,
        'measured_by': 'os.stat(path).st_size, after the file handle closed',
        'detail': (
            'Size the kernel reports for the file that now exists. Not fsync-ed: '
            'durability across power loss is not observed and is not claimed.'
        ),
    }

    if observed_size - baseline == offered_bytes:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED, not NONE: a predicate was evaluated and it was ours. No
            # caller asked for a byte count; recording who did keeps the
            # matching and the mismatching case attributable to the same author.
            claim_by=ClaimBy.INFERRED,
            effects=[offered_effect, observed_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            offered_effect,
            observed_effect,
            {
                'kind': 'file_size_disagrees',
                'predicate': (
                    'os.stat(path).st_size - size_before == len(content.encode(encoding))'
                ),
                'expected_bytes_added': offered_bytes,
                'actual_bytes_added': observed_size - baseline,
                'detail': (
                    'The file did not grow by the number of bytes offered. This may '
                    'be a short or truncated write, or it may be this module\'s '
                    'inference being wrong -- newline translation and BOM handling '
                    'both make a correct write land at a different length. We cannot '
                    'say which, so this is indeterminate rather than failed.'
                ),
            },
        ],
    )


@register_module(
    module_id='file.write',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'io', 'write', 'atomic', 'path_restricted'],
    label='Write File',
    label_key='modules.file.write.label',
    description='Write content to a file',
    description_key='modules.file.write.description',
    icon='FileText',
    color='#6B7280',


    # Type definitions for connection validation
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['*'],    # Execution settings
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.write'],

    # Schema-driven params
    params_schema=compose(
        presets.FILE_PATH(key='path', required=True, placeholder='/path/to/file.txt'),
        presets.FILE_CONTENT(required=True),
        presets.ENCODING(default='utf-8'),
        presets.WRITE_MODE(default='overwrite'),
    ),
    output_schema={
        'path': {
            'type': 'string',
            'description': 'File path'
        ,
                'description_key': 'modules.file.write.output.path.description'},
        'bytes_written': {
            'type': 'number',
            'description': (
                'Number of bytes offered to the writer: the encoded length of the '
                'content parameter. Not a measurement of the file on disk -- see '
                'bytes_on_disk'
            )
        ,
                'description_key': 'modules.file.write.output.bytes_written.description'},
        'bytes_on_disk': {
            'type': 'number',
            'description': (
                'Size the filesystem reports for the file after the write, from '
                'os.stat. null when the file could not be read back'
            )
        ,
                'description_key': 'modules.file.write.output.bytes_on_disk.description'},
        'bytes_added': {
            'type': 'number',
            'description': (
                'How much the file grew, measured as st_size minus the size before '
                'the write. null when either end could not be measured'
            )
        ,
                'description_key': 'modules.file.write.output.bytes_added.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this write was followed into reality: observed when the '
                'file grew by the bytes offered, accepted when nothing was read '
                'back, indeterminate when the size disagreed'
            )
        ,
                'description_key': 'modules.file.write.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Write text file',
            'title_key': 'modules.file.write.examples.text.title',
            'params': {
                'path': '/tmp/output.txt',
                'content': 'Hello World',
                'mode': 'overwrite'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def file_write(context):
    """Write file content"""
    params = context['params']
    path = params['path']
    content = params['content']
    encoding = params.get('encoding', 'utf-8')
    is_append = params.get('mode', 'overwrite') != 'overwrite'
    mode = 'a' if is_append else 'w'

    # SECURITY: Validate path to prevent path traversal attacks
    try:
        safe_path = validate_path_with_env_config(path)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    # Create parent directory if it doesn't exist
    parent_dir = os.path.dirname(safe_path)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    baseline = _size_before_write(safe_path, is_append)

    with open(safe_path, mode, encoding=encoding) as f:
        f.write(content)

    # Outside the `with`: the handle is closed, so the buffered bytes have been
    # handed to the kernel and st_size is a size and not a race.
    observed_size, observation_error = _observe_size_on_disk(safe_path)

    # Encoded after the write, exactly as before, so that a content the encoding
    # cannot represent still fails at f.write() and not one step earlier.
    offered_bytes = len(content.encode(encoding))

    return {
        'ok': True,
        'data': {
            'path': safe_path,
            'bytes_written': offered_bytes,
            'bytes_on_disk': observed_size,
            'bytes_added': (
                None if observed_size is None or baseline is None
                else observed_size - baseline
            ),
            'outcome': _write_outcome(
                offered_bytes=offered_bytes,
                baseline=baseline,
                observed_size=observed_size,
                observation_error=observation_error,
                encoding=encoding,
            ),
        }
    }
