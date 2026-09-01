# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Advanced File Operations Modules

Provides extended file manipulation capabilities.

HOW FAR THIS MODULE FOLLOWS REALITY

`copied: True` is a literal written in this file on the line after
`shutil.copy2` returns. It is the `file.write` defect exactly: it would read the
same if the destination filesystem were full and the copy landed short, because
nothing about it comes from the destination.

What earns OBSERVED is two stats of two different objects and a comparison
between them:

    the source, sized before the copy   -- what we set out to move
    the destination, sized after it     -- what is actually there now

Equal -> OBSERVED. This is the only reading in this module that would be
different if the copy had not happened: before it, `os.stat(destination)` either
raises ENOENT or reports the size of whatever the caller agreed to overwrite.

WHAT THE COMPARISON DOES NOT ESTABLISH, stated because a size is a weak witness

Equal sizes are not equal bytes. Nothing here reads the content back, so a copy
that produced the right NUMBER of wrong bytes is OBSERVED here and would be
caught only by a checksum this module does not compute. The effect says
`bytes`, never `contents`, so the gap is in the payload rather than in a
comment nobody reads.

It is also not durability: no fsync, so `st_size` is what the kernel reports for
a file whose bytes may still be in the page cache. Same limit as `file.write`,
same refusal to claim past it.

A MISMATCH IS INDETERMINATE, NOT FAILED

The equality is this module's own inference and no caller declared it, which is
the split `outcome.py` draws on `claim_by`. There is an ordinary correct copy it
is false for: a source being appended to by another process while `copy2` reads
it lands a destination legitimately larger than the size sampled beforehand.
Calling that FAILED would put a red mark on a copy that worked.
"""
import os
import shutil
from typing import Any, Dict, Optional, Tuple
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_path_with_env_config
from ....engine.outcome import ClaimBy, Outcome, envelope


def _size_of(path: str) -> Tuple[Optional[int], Optional[str]]:
    """``(st_size, None)`` when the path could be sized, ``(None, why)`` when not.

    Never raises. A failure to measure is not a failure of the copy -- by the
    time the destination is sized `shutil.copy2` has already returned without
    raising -- so it must not be able to turn a successful copy into a
    "Failed to copy file" the caller has to debug. It lowers the rung instead.
    """
    try:
        return os.stat(path).st_size, None
    except (OSError, ValueError) as error:
        strerror = getattr(error, 'strerror', None)
        return None, f"{type(error).__name__}: {strerror or error}"


def _copy_outcome(
    *,
    source: str,
    destination: str,
    source_size: Optional[int],
    destination_size: Optional[int],
    observation_error: Optional[str],
) -> Dict[str, Any]:
    """The rung this copy earned, and the two stats that earned it.

    Three answers, one per outcome of the measurement:

    * both ends sized and equal -> OBSERVED.
    * both ends sized and unequal -> INDETERMINATE. See the module docstring:
      the predicate is ours, and there are correct copies it is false for.
    * an end could not be sized -> ACCEPTED. `shutil.copy2` returned without
      raising, which is an acknowledgement that the bytes were taken, and
      nothing followed them further.
    """
    if destination_size is None or source_size is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'copy_not_observed',
                'source': source,
                'destination': destination,
                'measured_by': None,
                'reason': observation_error or 'an end of the copy could not be sized',
                'detail': (
                    'shutil.copy2 returned without raising and nothing was read '
                    'back. The copy was accepted by the OS and followed no '
                    'further.'
                ),
            }],
        )

    sized_effect = {
        'kind': 'copy_sizes_observed',
        'source': source,
        'destination': destination,
        'source_bytes': source_size,
        'destination_bytes': destination_size,
        'measured_by': (
            'os.stat(source).st_size before the copy, os.stat(destination).st_size '
            'after it'
        ),
        'detail': (
            'Byte counts of two different objects on the filesystem. Not a '
            'comparison of contents: no checksum is computed, so equal sizes do '
            'not establish equal bytes. Not fsync-ed, so durability across power '
            'loss is not observed and is not claimed.'
        ),
    }

    if destination_size == source_size:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: a predicate was evaluated and it was this module's own.
            # No caller asked for a size match; recording who did keeps the
            # matching and the mismatching case attributable to one author.
            claim_by=ClaimBy.INFERRED,
            effects=[sized_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            sized_effect,
            {
                'kind': 'copy_sizes_disagree',
                'predicate': 'os.stat(destination).st_size == os.stat(source).st_size',
                'expected_bytes': source_size,
                'actual_bytes': destination_size,
                'detail': (
                    'The destination is not the size the source was. This may be '
                    'a short or truncated copy, or it may be this module\'s '
                    'inference being wrong -- a source still being written to '
                    'while copy2 reads it lands a destination that legitimately '
                    'differs from the size sampled beforehand. We cannot say '
                    'which, so this is indeterminate rather than failed.'
                ),
            },
        ],
    )


@register_module(
    module_id='file.copy',
    version='1.0.0',
    category='file',
    subcategory='operations',
    tags=['file', 'copy', 'duplicate', 'path_restricted'],
    label='Copy File',
    label_key='modules.file.copy.label',
    description='Copy a file to another location',
    description_key='modules.file.copy.description',
    icon='Copy',
    color='#10B981',

    # Connection types
    input_types=['file_path', 'text'],
    output_types=['file_path', 'text'],


    can_receive_from=['*'],
    can_connect_to=['file.*', 'data.*', 'pdf.*', 'image.*', 'ai.*', 'notify.*', 'flow.*'],    # Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['filesystem.write'],

    # Schema-driven params
    params_schema=compose(
        presets.SOURCE_PATH(required=True),
        presets.DESTINATION_PATH(required=True),
        presets.OVERWRITE(default=False),
    ),
    output_schema={
        'copied': {
            'type': 'boolean',
            'description': (
                'Literal True written after shutil.copy2 returned. Not a '
                'measurement of the destination -- read outcome.rung for that'
            ),
            'description_key': 'modules.file.copy.output.copied.description'},
        'source': {'type': 'string', 'description': 'The source',
                'description_key': 'modules.file.copy.output.source.description'},
        'destination': {'type': 'string', 'description': 'The destination',
                'description_key': 'modules.file.copy.output.destination.description'},
        'size': {
            'type': 'number',
            'description': (
                'Size the filesystem reports for the destination after the copy, '
                'from os.stat. null when it could not be read back'
            ),
            'description_key': 'modules.file.copy.output.size.description'},
        'source_size': {
            'type': 'number',
            'description': (
                'Size the filesystem reported for the source before the copy. '
                'null when it could not be read'
            ),
            'description_key': 'modules.file.copy.output.source_size.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this copy was followed into reality: observed when the '
                'destination is the size the source was, accepted when neither '
                'end could be sized, indeterminate when the sizes disagreed'
            ),
            'description_key': 'modules.file.copy.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Backup file',
            'params': {
                'source': 'data/important.csv',
                'destination': 'backup/important.csv',
                'overwrite': True
            }
        },
        {
            'title': 'Duplicate configuration',
            'params': {
                'source': 'config.yaml',
                'destination': 'config.backup.yaml'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class FileCopyModule(BaseModule):
    """Copy File Module"""

    def validate_params(self) -> None:
        self.source = self.params.get('source')
        self.destination = self.params.get('destination')
        self.overwrite = self.params.get('overwrite', False)

        if not self.source or not self.destination:
            raise ValueError("source and destination are required")

    async def execute(self) -> Any:
        try:
            # GHSA-p34x: confine both operands to FLYTO_SANDBOX_DIR — copy had
            # NO path guard, so a client-controlled absolute source/destination
            # was an arbitrary read/write primitive.
            self.source = validate_path_with_env_config(self.source)
            self.destination = validate_path_with_env_config(self.destination)
            if not os.path.exists(self.source):
                raise FileNotFoundError(f"Source file not found: {self.source}")

            if os.path.exists(self.destination) and not self.overwrite:
                raise FileExistsError(f"Destination already exists: {self.destination}")

            # Create destination directory if needed
            dest_dir = os.path.dirname(self.destination)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)

            # Sampled BEFORE the copy: this is the size we set out to copy, and
            # it is the only baseline against which the destination's size can
            # say anything. Taken after the copy it would still be a real
            # measurement, but of a source that copy2 has already read.
            source_size, source_error = _size_of(self.source)

            shutil.copy2(self.source, self.destination)

            # After copy2 returns, so the destination is the file that now
            # exists rather than the one that may have been there before.
            file_size, dest_error = _size_of(self.destination)
        except Exception as e:
            raise RuntimeError(f"Failed to copy file: {str(e)}")

        return {
            "copied": True,
            "source": self.source,
            "destination": self.destination,
            "size": file_size,
            "source_size": source_size,
            "outcome": _copy_outcome(
                source=self.source,
                destination=self.destination,
                source_size=source_size,
                destination_size=file_size,
                observation_error=dest_error or source_error,
            ),
        }
