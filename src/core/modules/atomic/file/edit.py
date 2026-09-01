# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
File Edit Module
Targeted string replacement in files (not full overwrite).

HOW FAR THIS MODULE FOLLOWS REALITY

This is the one module in the file group that can reach VERIFIED, and it is
worth being precise about why, because VERIFIED is the only rung anything is
allowed to render as done and almost nothing earns it.

VERIFIED is defined as "a postcondition was evaluated and it held". Two things
are needed and both are here:

  * a postcondition declared on `@register_module`, so there is a predicate the
    claim is ABOUT rather than a rung asserted into the air; and
  * the module actually evaluating it -- the file is opened again after the
    write, read through the same encoding, and compared for equality against the
    exact string that was written.

WHY A READ-BACK AND NOT A SIZE, which is what `file.write` settled for

`file.write` compares `st_size` against `len(content.encode(...))` and stops at
OBSERVED, because a size is a weak witness: the right number of wrong bytes
passes it. It stops there for a good reason -- it is the module every bulk write
in the product goes through, and re-reading arbitrary payloads to check them
would double the I/O of the whole system.

`file.edit` is not that module. It has already read the entire file into memory
to perform the replacement, so the content it must match is in hand and the
comparison is exact rather than a proxy for exactness. The extra cost is one
re-read of a file that was just written and is therefore in the page cache.

WHAT VERIFIED HERE DOES NOT MEAN, and this is the load-bearing paragraph

  * Not durability. There is no `fsync`. The read-back can be served from the
    page cache, so what held is "the filesystem reports this content at this
    path", not "these bytes survive power loss". A module cannot verify past
    the layer it can see, and this one sees the kernel's view.
  * Not exclusivity. The predicate held at the instant it was evaluated.
    Nothing stops another writer from changing the file immediately afterwards,
    and no rung on this ladder ever claimed otherwise.
  * Not that the edit was the RIGHT edit. `new_string` is the caller's, and
    equality with it says the caller's instruction was carried out, not that the
    instruction was correct.

THE NEWLINE TRAP, which this comparison walked into once

A text round-trip looks symmetric and is not. `open(..., 'w')` leaves `newline`
at None, which translates `'\n'` to `os.linesep` on the way out; `open(..., 'r')`
at None applies UNIVERSAL NEWLINES on the way back, which collapses `'\r\n'` AND
a bare `'\r'` to `'\n'`. The two are not inverses. Measured: writing
`'a\r\nb\n'` and reading it back plainly returns `'a\nb\n'` -- so a `new_string`
carrying a CR would have been reported FAILED for a perfectly correct edit,
which is a false red on exactly the rung that is allowed to render as done.

So the read-back opens with `newline=''`, which disables translation and returns
the characters that are actually on disk, and it is compared against
`_expected_on_disk` -- the writer's own translation applied to the content that
was written. That is a model of what the writer did rather than a hope that it
did nothing, and it holds on both POSIX (`os.linesep == '\n'`, so the expected
string is the written one) and Windows (where `'a\nb'` is genuinely `'a\r\nb'` on
disk and the comparison expects that).

A MISMATCH IS FAILED, WHICH IS DIFFERENT FROM `file.write`

`file.write` calls a size disagreement INDETERMINATE, and correctly: its
predicate is an inference that is false for ordinary correct writes -- newline
translation lands content at a length its arithmetic does not predict, which is
the same translation described above, seen from the side that cannot correct for
it. This comparison can and does correct for it, and a BOM is written and
stripped by the same codec, so there is no ordinary correct edit left for which
it is false. If what comes back is not what the writer put there, the declared
postcondition genuinely does not hold at the moment it was evaluated, whoever
caused that. That is what FAILED means.

A read-back that could not be performed at all -- the file vanished, the codec
raised -- is neither. Nothing was evaluated, so nothing held or failed, and the
rung falls to ACCEPTED: the OS took the bytes and nothing followed them.

THE `old_string` MISS IS ALSO FAILED, AND FOR A DIFFERENT REASON

When `old_string` is not in the file, no write is attempted. That is FAILED with
`claim_by=caller`, which is the other half of `outcome.py`'s split: the caller
asserted that this string is in this file and it was not. A contract was broken,
and it was the caller's contract, not an inference of ours.
"""

from typing import Any, Dict, Optional, Tuple
from ...registry import register_module
from ...schema import compose, field, presets
from ....utils import validate_path_with_env_config, PathTraversalError
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...errors import ValidationError, FileNotFoundError, ModuleError
import os


#: The predicate this module evaluates, declared so `verified` has something to
#: be about. `ceiling_for` in `core/engine/outcome.py` caps any module without
#: one at `observed`, so this string is not documentation -- it is the thing
#: that makes the rung below reachable at all.
POSTCONDITION = (
    "the file re-read through the same encoding equals the content written"
)


def _generate_diff(original: str, modified: str, path: str) -> str:
    """Generate a unified diff between original and modified content."""
    import difflib
    diff_lines = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile="a/{}".format(os.path.basename(path)),
        tofile="b/{}".format(os.path.basename(path)),
        n=3,
    ))
    return ''.join(diff_lines)


# ---------------------------------------------------------------------------
# The only lines in this module that measure the world. Everything else is
# string manipulation on content the caller supplied.
# ---------------------------------------------------------------------------
def _expected_on_disk(written: str) -> str:
    """What the writer actually put in the file, given how it opened it.

    `open(..., 'w')` with `newline` at its default translates every `'\\n'` to
    `os.linesep`. On POSIX that is the identity; on Windows it is not, and a
    comparison that ignored it would fail every edit on that platform. See the
    module docstring for the measurement.
    """
    return written.replace('\n', os.linesep)


def _read_back(path: str, encoding: str) -> Tuple[Optional[str], Optional[str]]:
    """``(content, None)`` when the file could be re-read, ``(None, why)`` when not.

    ``newline=''`` is load-bearing, not tidiness: the default would apply
    universal newlines and collapse `'\\r\\n'` and a bare `'\\r'` to `'\\n'`,
    so a `new_string` containing a CR would come back different from what was
    written and be reported as a failure of a correct edit. Disabling
    translation here is what lets the comparison be against
    `_expected_on_disk` -- the characters that are really in the file.

    A failure here is not a failure of the edit. `open`/`write`/`close` already
    returned without raising; all that is lost is the ability to evaluate the
    postcondition, and the rung falls to the one that claims nothing about it.
    """
    try:
        with open(path, 'r', encoding=encoding, newline='') as handle:
            return handle.read(), None
    except (OSError, ValueError, UnicodeError) as error:
        strerror = getattr(error, 'strerror', None)
        return None, f"{type(error).__name__}: {strerror or error}"


def _edit_outcome(
    *,
    path: str,
    written: str,
    read_back: Optional[str],
    read_back_error: Optional[str],
    encoding: str,
    replacements: int,
) -> Dict[str, Any]:
    """The rung this edit earned. Three answers; see the module docstring.

    * read back and equal -> VERIFIED. The declared postcondition was evaluated
      and it held.
    * read back and unequal -> FAILED. It was evaluated and it did not hold.
    * not read back -> ACCEPTED. It was not evaluated, so it neither held nor
      failed, and the honest floor is that the OS acknowledged the bytes.
    """
    if read_back is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            postcondition=POSTCONDITION,
            effects=[{
                'kind': 'edit_not_read_back',
                'path': path,
                'replacements': replacements,
                'measured_by': None,
                'reason': read_back_error,
                'detail': (
                    'The write returned without raising and the file could not '
                    'be read again, so the postcondition was never evaluated. '
                    'Not a failure of the edit -- a failure to look at it.'
                ),
            }],
        )

    if read_back == written:
        return envelope(
            Outcome.VERIFIED,
            # INFERRED: the predicate is this module's own declaration, not
            # something a caller passed in. `file.write` uses the same value for
            # the same reason -- it keeps the holding and the failing case
            # attributable to one author.
            claim_by=ClaimBy.INFERRED,
            postcondition=POSTCONDITION,
            effects=[{
                'kind': 'edit_content_verified',
                'path': path,
                'replacements': replacements,
                'characters': len(read_back),
                'encoding': encoding,
                'measured_by': (
                    'the file re-opened after the write and compared for string '
                    'equality against the content written'
                ),
                'detail': (
                    'Exact equality, not a size or a checksum. Not fsync-ed: '
                    'this is the filesystem\'s view and not a claim about power '
                    'loss. Held at the instant it was evaluated; nothing here '
                    'prevents a later writer.'
                ),
            }],
        )

    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.INFERRED,
        postcondition=POSTCONDITION,
        effects=[{
            'kind': 'edit_content_differs',
            'path': path,
            'predicate': POSTCONDITION,
            'expected_characters': len(written),
            'actual_characters': len(read_back),
            'encoding': encoding,
            'measured_by': (
                'the file re-opened after the write and compared for string '
                'equality against the content written'
            ),
            'detail': (
                'What is at this path is not what was written to it. FAILED and '
                'not INDETERMINATE: a text round-trip through one encoding is '
                'symmetric -- newline translation and BOM handling both undo '
                'themselves on the way back -- so unlike file.write\'s byte '
                'arithmetic there is no ordinary correct edit this comparison '
                'is false for. A short write and a concurrent writer are both '
                'states in which the declared postcondition does not hold.'
            ),
        }],
    )


@register_module(
    module_id='file.edit',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'edit', 'replace', 'atomic', 'path_restricted'],
    label='Edit File',
    label_key='modules.file.edit.label',
    description='Replace a string in a file (targeted edit, not full overwrite)',
    description_key='modules.file.edit.description',
    icon='FileEdit',
    color='#3B82F6',

    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=False,

    # The predicate that makes `verified` reachable. Without this the engine
    # caps the claim at `observed`, because there would be nothing for a
    # "postcondition was evaluated and held" to be about.
    postcondition=POSTCONDITION,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.write'],

    params_schema=compose(
        presets.FILE_PATH(key='path', required=True, placeholder='/path/to/file.txt'),
        field('old_string', type='string', label='Old String', required=True, format='multiline',
              description='Text to find and replace',
              placeholder='Enter Old String...'),
        field('new_string', type='string', label='New String', required=True, format='multiline',
              description='Replacement text',
              placeholder='Enter New String...'),
        field('replace_all', type='boolean', label='Replace All', default=False,
              description='Whether to replace all occurrences'),
        presets.ENCODING(default='utf-8'),
    ),
    output_schema={
        'path': {
            'type': 'string',
            'description': 'File path that was edited',
            'description_key': 'modules.file.edit.output.path.description',
        },
        'replacements': {
            'type': 'number',
            'description': 'Number of replacements made',
            'description_key': 'modules.file.edit.output.replacements.description',
        },
        'diff': {
            'type': 'string',
            'description': 'Unified diff of changes',
            'description_key': 'modules.file.edit.output.diff.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this edit was followed into reality: verified when the '
                'file re-read equals what was written, failed when it does not, '
                'accepted when the file could not be read back'
            ),
            'description_key': 'modules.file.edit.output.outcome.description',
        },
    },
    examples=[
        {
            'title': 'Replace string in file',
            'title_key': 'modules.file.edit.examples.replace.title',
            'params': {
                'path': '/tmp/example.py',
                'old_string': 'def hello():',
                'new_string': 'def hello_world():',
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
)
async def file_edit(context):
    """Replace string in file (targeted edit, not full overwrite)."""
    params = context['params']
    path = params['path']
    old_string = params['old_string']
    new_string = params['new_string']
    replace_all = params.get('replace_all', False)
    encoding = params.get('encoding', 'utf-8')

    try:
        safe_path = validate_path_with_env_config(path)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    if not os.path.exists(safe_path):
        raise FileNotFoundError("File not found: {}".format(path), path=path)

    with open(safe_path, 'r', encoding=encoding) as f:
        original = f.read()

    if old_string not in original:
        # No write is attempted, so there is no effect to follow. FAILED with
        # claim_by=CALLER: the caller asserted this string is in this file, and
        # `outcome.py` reserves FAILED for exactly a broken caller contract.
        return {
            'ok': False,
            'error': 'old_string not found in {}'.format(path),
            'outcome': envelope(
                Outcome.FAILED,
                claim_by=ClaimBy.CALLER,
                postcondition=POSTCONDITION,
                effects=[{
                    'kind': 'old_string_absent',
                    'path': safe_path,
                    'measured_by': 'substring test against the file as read',
                    'detail': (
                        'The file was read and does not contain old_string. No '
                        'write was attempted, so nothing changed on disk.'
                    ),
                }],
            ),
        }

    if replace_all:
        modified = original.replace(old_string, new_string)
        count = original.count(old_string)
    else:
        modified = original.replace(old_string, new_string, 1)
        count = 1

    with open(safe_path, 'w', encoding=encoding) as f:
        f.write(modified)

    # Outside the `with`: the handle is closed, so the buffered characters have
    # reached the kernel and the read-back is a comparison and not a race with
    # our own buffer.
    read_back, read_back_error = _read_back(safe_path, encoding)

    return {
        'ok': True,
        'data': {
            'path': path,
            'replacements': count,
            'diff': _generate_diff(original, modified, path),
            'outcome': _edit_outcome(
                path=safe_path,
                # The writer's translation, modelled -- not `modified` itself.
                written=_expected_on_disk(modified),
                read_back=read_back,
                read_back_error=read_back_error,
                encoding=encoding,
                replacements=count,
            ),
        }
    }
