# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Advanced File Operations Modules

Provides extended file manipulation capabilities.

HOW FAR THIS MODULE FOLLOWS REALITY

`deleted: True` was a literal written on the line after `os.remove` returned.
Deletion is the easiest effect in this group to actually check, because absence
is observable: one `lexists` after the unlink is a measurement of the world and
not of anything this module was handed.

    unlinked, and the name is gone      -> OBSERVED
    unlinked, and the name is still     -> INDETERMINATE
    nothing to unlink, name is absent   -> OBSERVED, and see below
    nothing to unlink, name is present  -> INDETERMINATE (a race; see below)

THE NO-OP PATH, which is where a rung is easy to get wrong

With `ignore_missing`, a run that unlinks nothing returns `deleted: False`. There
is no effect to have followed, so the temptation is to claim nothing. What is
claimed instead is the state, measured the same way and named so it cannot be
misread: `lexists` answered False, so the caller's desired end state -- this name
is not there -- holds. `unlink_issued: False` rides in the effect, so a consumer
reading OBSERVED here cannot mistake it for "we deleted something".

The fourth line is reachable only as a race: something creates the path between
the `exists` precondition and the `lexists` that follows it. It is reported
rather than smoothed over, because a module that says "nothing to delete" while
something is sitting at that path is a result somebody should look at.

WHAT `lexists` DOES AND DOES NOT BUY HERE

`lexists` is the syscall that matches what `unlink` acts on -- a name, not what
the name points at -- so it is the right question to ask after an unlink.

It is NOT, as it first appears, a way to catch a dangling symlink taking the
no-op path. `validate_path_with_env_config` returns `os.path.realpath`, which
resolves the WHOLE path including its last component, so by the time `execute`
runs there is no symlink left at the end of `self.file_path` and `lexists` and
`exists` cannot disagree about it. Measured, not assumed: a test that creates a
dangling symlink and deletes through it reports `observed`, because the module
was handed the resolved target.

That resolution has a consequence worth stating plainly, since nothing else in
this file does: passing a symlink to this module deletes the symlink's TARGET
and leaves the link behind. It follows from the sandbox check needing a
canonical path -- resolving is what stops a link from pointing out of
FLYTO_SANDBOX_DIR -- and it is left exactly as it is here. Changing which file
this module deletes is not a change to make while adding an outcome.

WHY A SURVIVING NAME IS INDETERMINATE AND NOT FAILED

No caller declared the predicate; it is this module's own, which is the split
`outcome.py` draws on `claim_by`. A process recreating the path in the moment
between the unlink and the check reads identically to an unlink that did
nothing, and there is nothing here that can tell them apart.

WHAT IS NOT CLAIMED

Not that the bytes are unrecoverable, and not that the file's data is freed: an
open handle elsewhere, or another hard link to the same inode, keeps the content
alive after the name is gone. `unlink` removes a NAME, and `lexists` observes
exactly that much. The effect says `name_removed` rather than `file_destroyed`
for that reason.
"""
import os
import shutil
from typing import Any, Dict
from ....utils import validate_path_with_env_config
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


def _delete_outcome(*, path: str, unlink_issued: bool, still_present: bool) -> Dict[str, Any]:
    """The rung this delete earned, from one `lexists` after the fact.

    The same measurement decides all four cases; `unlink_issued` only changes
    what the effect is called, never how hard the evidence is looked at.
    """
    if not still_present:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            effects=[{
                'kind': 'name_removed' if unlink_issued else 'name_already_absent',
                'path': path,
                'unlink_issued': unlink_issued,
                'measured_by': 'os.path.lexists(path), after the unlink, symlinks not resolved',
                'detail': (
                    'The name does not resolve. This is an observation of the '
                    'filesystem and not of any parameter. It is a statement '
                    'about the NAME only: an open handle or another hard link '
                    'keeps the content alive, and neither is observed here.'
                    + (
                        ''
                        if unlink_issued else
                        ' No unlink was issued on this path -- nothing changed, '
                        'and what is observed is that the caller\'s desired end '
                        'state already held.'
                    )
                ),
            }],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            'kind': 'name_still_present',
            'path': path,
            'unlink_issued': unlink_issued,
            'predicate': 'not os.path.lexists(path)',
            'measured_by': 'os.path.lexists(path), after the unlink, symlinks not resolved',
            'detail': (
                (
                    'os.remove returned without raising and the name is still '
                    'there. Something recreated it, or the unlink did not take.'
                    if unlink_issued else
                    'Nothing was unlinked because the path read as absent, and '
                    'a name IS there now. Something created it in between.'
                )
                + ' Indeterminate rather than failed: no caller declared this '
                'predicate, and a process recreating the path reads the same '
                'here as an unlink that did nothing.'
            ),
        }],
    )


@register_module(
    module_id='file.delete',
    version='1.0.0',
    category='file',
    subcategory='operations',
    tags=['file', 'delete', 'remove', 'path_restricted'],
    label='Delete File',
    label_key='modules.file.delete.label',
    description='Delete a file from the filesystem',
    description_key='modules.file.delete.description',
    icon='Trash2',
    color='#EF4444',

    # Connection types
    input_types=['file_path', 'text'],
    output_types=['boolean'],


    can_receive_from=['*'],
    can_connect_to=['file.*', 'data.*', 'pdf.*', 'image.*', 'ai.*', 'notify.*', 'flow.*'],    # Execution settings
    timeout_ms=5000,
    retryable=False,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['filesystem.write'],

    # Schema-driven params
    params_schema=compose(
        presets.FILE_PATH(required=True),
        presets.IGNORE_MISSING(default=False),
    ),
    output_schema={
        'deleted': {
            'type': 'boolean',
            'description': (
                'Whether an unlink was issued. Not a measurement that the name '
                'is gone -- read outcome.rung for that'
            ),
            'description_key': 'modules.file.delete.output.deleted.description'},
        'file_path': {'type': 'string', 'description': 'The file path',
                'description_key': 'modules.file.delete.output.file_path.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this delete was followed into reality: observed when '
                'the name is gone afterwards, indeterminate when it is still '
                'there'
            ),
            'description_key': 'modules.file.delete.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Delete temporary file',
            'params': {
                'file_path': '/tmp/temp.txt',
                'ignore_missing': True
            }
        },
        {
            'title': 'Delete log file',
            'params': {
                'file_path': 'logs/app.log'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class FileDeleteModule(BaseModule):
    """Delete File Module"""

    def validate_params(self) -> None:
        raw_file_path = self.params.get('file_path')
        self.ignore_missing = self.params.get('ignore_missing', False)

        if not raw_file_path:
            raise ValueError("file_path is required")

        # SECURITY: os.remove() on an unconfined path is arbitrary file
        # deletion — the destructive counterpart of the arbitrary file write
        # advisories (GHSA-p64w-hgfm-824v, GHSA-hmq9-xw4w-7ppc). Confine it to
        # FLYTO_SANDBOX_DIR before anything can reach the unlink.
        self.file_path = validate_path_with_env_config(str(raw_file_path))

    async def execute(self) -> Any:
        try:
            if os.path.exists(self.file_path):
                os.remove(self.file_path)
                unlink_issued = True
            elif self.ignore_missing:
                unlink_issued = False
            else:
                raise FileNotFoundError(f"File not found: {self.file_path}")

            # The one line that measures anything. lexists and not exists: the
            # unlink acts on the name, so the check has to ask about the name.
            still_present = os.path.lexists(self.file_path)
        except Exception as e:
            raise RuntimeError(f"Failed to delete file: {str(e)}")

        return {
            "deleted": unlink_issued,
            "file_path": self.file_path,
            "outcome": _delete_outcome(
                path=self.file_path,
                unlink_issued=unlink_issued,
                still_present=still_present,
            ),
        }
