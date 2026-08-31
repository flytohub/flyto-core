# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
File Operation Modules
Basic file system operations

HOW FAR THIS MODULE FOLLOWS REALITY

A read changes nothing, so there is no effect to follow -- and OBSERVED is still
the honest rung, for the same reason `database.query` earns it on a SELECT that
returned rows: `content` is bytes the filesystem handed us, decoded. No branch
invents it. That is a measurement of the world and not of the caller's own
parameters, which is the whole test.

THE EMPTY FILE, which is where this could have gone wrong

`len(content) == 0` on its own is exactly the shape this contract exists to
distrust -- `database.query` had to be dropped to ACCEPTED for an empty result
set because `len(rows) == 0` reads identically whether a statement matched
nothing or was discarded entirely. It does not read the same way here, and the
difference is `open()`. A file that opens is a file that exists; the zero came
back from a successful `stat` of it, not from the absence of an answer. So an
empty file is OBSERVED, and the effect says the size is zero rather than saying
nothing.

WHAT IS REPORTED, and the disagreement that used to be silent

`size` is `st_size` -- bytes on disk. `content` is text, decoded through
`encoding`. For anything but pure ASCII these are different numbers, and the old
output offered `size` beside `content` with nothing saying which was which; a
consumer checking `len(content) == size` was reading a bug into UTF-8. Both
counts are now in the envelope, named for what they count.

The stat is also taken from the open handle (`os.fstat`) rather than from the
path a second time. The path form was a second lookup of a name that may no
longer be the file we just read -- a rotated log is replaced between the read
and the stat, and the old code would pair one file's bytes with another file's
size. `fstat` measures the object the bytes actually came from.
"""

from typing import Any, Dict, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_path_with_env_config, PathTraversalError
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...errors import ValidationError, FileNotFoundError, ModuleError
import os
import shutil


def _read_outcome(
    *,
    path: str,
    size: Optional[int],
    characters: int,
    encoding: str,
    stat_error: Optional[str],
) -> Dict[str, Any]:
    """The rung this read earned.

    OBSERVED on both paths that got the bytes, because the bytes are the
    observation and the size is corroboration rather than the evidence itself.
    When `fstat` could not answer, the content still came from the filesystem,
    so the rung does not move -- only the effect loses a field.
    """
    effects = [{
        'kind': 'file_content_read',
        'path': path,
        'characters_returned': characters,
        'encoding': encoding,
        'measured_by': "open(path).read(), decoded through encoding",
        'detail': (
            'Text the filesystem handed us. characters_returned counts DECODED '
            'characters and is not a byte count: for anything outside ASCII it '
            'is smaller than bytes_on_disk, and neither number is wrong.'
        ),
    }]

    if size is None:
        effects.append({
            'kind': 'file_size_not_observed',
            'measured_by': None,
            'reason': stat_error,
            'detail': (
                'os.fstat on the open handle could not answer. The content was '
                'still read from the filesystem, so the rung is unchanged; only '
                'the corroborating byte count is missing.'
            ),
        })
    else:
        effects.append({
            'kind': 'file_size_observed',
            'bytes_on_disk': size,
            'measured_by': 'os.fstat(handle).st_size, on the handle the bytes came from',
            'detail': (
                'Size of the object that was actually read, not of whatever the '
                'path resolves to now. A size of 0 is a measurement of an empty '
                'file, not a missing answer -- the file opened.'
            ),
        })

    return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=effects)


@register_module(
    module_id='file.read',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'io', 'read', 'atomic', 'path_restricted'],
    label='Read File',
    label_key='modules.file.read.label',
    description='Read content from a file',
    description_key='modules.file.read.description',
    icon='FileText',
    color='#6B7280',

    # Connection types
    input_types=['string'],
    output_types=['string', 'binary'],


    can_receive_from=['*'],
    can_connect_to=['*'],    # Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read'],

    # Schema-driven params
    params_schema=compose(
        presets.FILE_PATH(key='path', required=True, placeholder='/path/to/file.txt'),
        presets.ENCODING(default='utf-8'),
    ),
    output_schema={
        'content': {
            'type': 'string',
            'description': 'File content'
        ,
                'description_key': 'modules.file.read.output.content.description'},
        'size': {
            'type': 'number',
            'description': (
                'File size in bytes, from os.fstat on the handle the content was '
                'read from. Not the length of content, which counts decoded '
                'characters. null when the stat could not answer'
            )
        ,
                'description_key': 'modules.file.read.output.size.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this read was followed into reality: observed, because '
                'the content is bytes the filesystem returned. An empty file is '
                'observed too -- it opened'
            )
        ,
                'description_key': 'modules.file.read.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Read text file',
            'title_key': 'modules.file.read.examples.text.title',
            'params': {
                'path': '/tmp/data.txt',
                'encoding': 'utf-8'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def file_read(context):
    """Read file content"""
    params = context['params']
    path = params['path']
    encoding = params.get('encoding', 'utf-8')

    # SECURITY: Validate path to prevent path traversal attacks
    try:
        safe_path = validate_path_with_env_config(path)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    if not os.path.exists(safe_path):
        raise FileNotFoundError(f"File not found: {path}", path=path)

    # The stat comes off the open handle, inside the `with`, so the size and the
    # bytes describe the same object. See the module docstring.
    stat_error = None
    size = None
    with open(safe_path, 'r', encoding=encoding) as f:
        content = f.read()
        try:
            size = os.fstat(f.fileno()).st_size
        except OSError as error:
            # Losing the size does not lose the read. The rung is unchanged and
            # the reason travels in the effect rather than vanishing.
            stat_error = f"{type(error).__name__}: {error.strerror or error}"

    return {
        'ok': True,
        'data': {
            'content': content,
            'size': size,
            'outcome': _read_outcome(
                path=safe_path,
                size=size,
                characters=len(content),
                encoding=encoding,
                stat_error=stat_error,
            ),
        }
    }


