# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Advanced File Operations Modules

Provides extended file manipulation capabilities.

HOW FAR THIS MODULE FOLLOWS REALITY

`moved: True` is a literal written after `shutil.move` returns. A move is the
one operation in this group with two halves that can be checked independently,
and checking both is what earns OBSERVED:

    the destination is there   -- os.path.lexists on where it actually landed
    the source is not          -- os.path.lexists on where it came from

Only the pair is evidence. Either half alone is satisfied by a state that is not
a move: an overwrite of a destination that already existed satisfies the first,
and a plain delete satisfies the second.

WHERE IT ACTUALLY LANDED, which is not always where the caller asked

`shutil.move(src, dst)` where `dst` is an EXISTING DIRECTORY does not create
`dst`. It puts the source inside it, at `dst/basename(src)`, and returns that
path. This module reports the caller's `destination` unchanged, so for that case
the `destination` field names a directory and not the file -- a pre-existing
reporting defect that is left alone here rather than changed under consumers who
may already work around it.

The observation must not inherit it. Checking `lexists(destination)` in the
directory case would be checking that a directory which existed before the move
still exists: a reading that is True no matter what happened, which is precisely
the "would this be the same if the effect had NOT happened" failure. So
`shutil.move`'s RETURN VALUE is what gets stat-ed, and it travels in the effect
as `landed_at` so the discrepancy is visible in the payload.

LEXISTS, NOT EXISTS

`os.path.exists` resolves symlinks, and a move operates on the link rather than
its target. Moving a broken symlink would leave `exists(landed_at)` False --
correctly, the target is still missing -- and this module would report an
INDETERMINATE for a move that worked perfectly. `lexists` asks about the name,
which is the thing that moved.

SIZES ARE CORROBORATION, NOT THE VERDICT

A byte count is taken for a regular-file source and compared afterwards, but the
existence pair is what the rung turns on. A directory source has no meaningful
`st_size` -- it is the size of the directory entry, not of the tree -- so gating
on size would make every directory move unobservable. When both sizes are known
and disagree, that is enough on its own to drop to INDETERMINATE.
"""
import os
import shutil
import stat as stat_module
from typing import Any, Dict, Optional, Tuple
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_path_with_env_config
from ....engine.outcome import ClaimBy, Outcome, envelope


def _regular_file_size(path: str) -> Optional[int]:
    """``st_size`` when `path` is a regular file, ``None`` for anything else.

    None for a directory on purpose, not as an error path: `st_size` on a
    directory is the size of its entry and comparing two of them says nothing
    about whether a tree moved. Never raises -- a size that cannot be read
    costs corroboration, not the operation.
    """
    try:
        result = os.stat(path)
    except (OSError, ValueError):
        return None
    return result.st_size if stat_module.S_ISREG(result.st_mode) else None


def _move_outcome(
    *,
    source: str,
    requested_destination: str,
    landed_at: str,
    destination_present: bool,
    source_gone: bool,
    size_before: Optional[int],
    size_after: Optional[int],
) -> Dict[str, Any]:
    """The rung this move earned, from the pair of lexists and the sizes.

    OBSERVED needs every check that could be made to have passed. A move is a
    conjunction -- arrived AND departed -- so one half failing is one half of a
    move, and there is no rung for that.

    A failing check is INDETERMINATE rather than FAILED because the predicate is
    this module's own and no caller declared it. There are correct moves it
    reads wrong: another process may legitimately recreate the source path after
    `shutil.move` released it, and this module cannot tell that from a move that
    did not happen.
    """
    sizes_disagree = (
        size_before is not None
        and size_after is not None
        and size_before != size_after
    )

    observation = {
        'kind': 'move_endpoints_observed',
        'source': source,
        'requested_destination': requested_destination,
        'landed_at': landed_at,
        'destination_present': destination_present,
        'source_gone': source_gone,
        'bytes_before': size_before,
        'bytes_after': size_after,
        'measured_by': (
            'os.path.lexists on the path shutil.move returned and on the source, '
            'after the move'
        ),
        'detail': (
            'landed_at is shutil.move\'s return value, not the requested '
            'destination: moving into an existing directory places the source '
            'inside it, and checking the requested path there would be checking '
            'that a directory which already existed still does. Byte counts are '
            'present only when both ends were regular files. Not fsync-ed: '
            'durability across power loss is not observed and is not claimed.'
        ),
    }

    if destination_present and source_gone and not sizes_disagree:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: the predicate is this module's, not a caller's.
            claim_by=ClaimBy.INFERRED,
            effects=[observation],
        )

    if sizes_disagree:
        reason = (
            'The destination is not the size the source was. A short move, or a '
            'source that was still being written when shutil.move read it.'
        )
    elif not destination_present and not source_gone:
        reason = (
            'Neither end moved: the source is still where it was and nothing is '
            'at the destination.'
        )
    elif not destination_present:
        reason = (
            'The source is gone but nothing is at the destination. Half a move '
            'is not a move, and this is the half that loses data.'
        )
    else:
        reason = (
            'Something is at the destination but the source is still there. The '
            'destination may be what the move put there, or what was there '
            'before it.'
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            observation,
            {
                'kind': 'move_endpoints_disagree',
                'predicate': (
                    'os.path.lexists(landed_at) and not os.path.lexists(source) '
                    'and, when both are regular files, the byte counts match'
                ),
                'reason': reason,
                'detail': (
                    'Indeterminate rather than failed: no caller declared this '
                    'predicate, and a process recreating the source path after '
                    'shutil.move released it reads identically here to a move '
                    'that never happened.'
                ),
            },
        ],
    )


@register_module(
    module_id='file.move',
    version='1.0.0',
    category='file',
    subcategory='operations',
    tags=['file', 'move', 'rename', 'path_restricted'],
    label='Move File',
    label_key='modules.file.move.label',
    description='Move or rename a file',
    description_key='modules.file.move.description',
    icon='Move',
    color='#8B5CF6',

    # Connection types
    input_types=['file_path', 'text'],
    output_types=['file_path', 'text'],


    can_receive_from=['*'],
    can_connect_to=['file.*', 'data.*', 'pdf.*', 'image.*', 'ai.*', 'notify.*', 'flow.*'],    # Execution settings
    timeout_ms=10000,
    retryable=False,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['filesystem.write'],

    # Schema-driven params
    params_schema=compose(
        presets.SOURCE_PATH(required=True),
        presets.DESTINATION_PATH(required=True),
    ),
    output_schema={
        'moved': {
            'type': 'boolean',
            'description': (
                'Literal True written after shutil.move returned. Not a '
                'measurement of either endpoint -- read outcome.rung for that'
            ),
            'description_key': 'modules.file.move.output.moved.description'},
        'source': {'type': 'string', 'description': 'The source',
                'description_key': 'modules.file.move.output.source.description'},
        'destination': {
            'type': 'string',
            'description': (
                'The destination as requested. When it names an existing '
                'directory the file lands INSIDE it -- see outcome.effects '
                'landed_at for where it actually went'
            ),
            'description_key': 'modules.file.move.output.destination.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this move was followed into reality: observed when the '
                'destination is present and the source is gone, indeterminate '
                'when only one of those holds'
            ),
            'description_key': 'modules.file.move.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Move file to archive',
            'params': {
                'source': 'data/input.csv',
                'destination': 'archive/input_2024.csv'
            }
        },
        {
            'title': 'Rename file',
            'params': {
                'source': 'report.txt',
                'destination': 'report_final.txt'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class FileMoveModule(BaseModule):
    """Move File Module"""

    def validate_params(self) -> None:
        self.source = self.params.get('source')
        self.destination = self.params.get('destination')

        if not self.source or not self.destination:
            raise ValueError("source and destination are required")

    async def execute(self) -> Any:
        try:
            # GHSA-p34x: confine both operands to FLYTO_SANDBOX_DIR — move had
            # NO path guard, so a client-controlled absolute source/destination
            # was an arbitrary move/delete + write primitive.
            self.source = validate_path_with_env_config(self.source)
            self.destination = validate_path_with_env_config(self.destination)
            if not os.path.exists(self.source):
                raise FileNotFoundError(f"Source file not found: {self.source}")

            # Create destination directory if needed
            dest_dir = os.path.dirname(self.destination)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)

            size_before = _regular_file_size(self.source)

            # The return value, not the parameter. See the module docstring: for
            # a destination that is an existing directory these are different
            # paths, and only the returned one is where the bytes are.
            landed_at = shutil.move(self.source, self.destination) or self.destination

            destination_present = os.path.lexists(landed_at)
            source_gone = not os.path.lexists(self.source)
            size_after = _regular_file_size(landed_at)
        except Exception as e:
            raise RuntimeError(f"Failed to move file: {str(e)}")

        return {
            "moved": True,
            "source": self.source,
            "destination": self.destination,
            "outcome": _move_outcome(
                source=self.source,
                requested_destination=self.destination,
                landed_at=landed_at,
                destination_present=destination_present,
                source_gone=source_gone,
                size_before=size_before,
                size_after=size_after,
            ),
        }
