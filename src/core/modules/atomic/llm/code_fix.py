# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
LLM Code Fix Module
AI-powered automatic code fixes based on issues and feedback

HOW FAR THIS MODULE FOLLOWS REALITY

This is the only module in the ai/llm group that changes anything outside a
provider's billing record: with `fix_mode='apply'` it writes model-generated code
over the caller's source files. So the rung is about the WRITES, not about the
completion, and the two halves are deliberately not averaged:

  fix_mode='suggest' (the default) or 'dry_run'         ACCEPTED
      A completion came back and nothing was written. `fixes` is text the model
      produced; `applied` under dry_run is a list of fixes that WOULD apply,
      computed in memory. Nothing on disk changed and nothing claims it did.

  fix_mode='apply', every write read back and matched   OBSERVED
      Each file is read back after `write_text` closes and compared against the
      exact string that was written. That is a measurement of the file that now
      exists, not of the string we handed over -- the distinction `file.write`
      exists to make. `len(applied)` on its own is NOT that: it counts how many
      times `write_text` returned without raising, which is identical whether the
      bytes landed or the disk filled up mid-write.

  fix_mode='apply', a write could not be read back      INDETERMINATE
      or came back different. INDETERMINATE and not FAILED, for the reason
      `outcome.py` gives: nobody declared this equality, it is this module's own
      inference, and a concurrent writer or an editor with the file open makes it
      false without our write having gone wrong. `claim_by=INFERRED` records
      whose judgement it was.

  a guard refused before the model was called           FAILED
      A missing API key, or no source file inside the sandbox. Both return above
      the call, so nothing was requested and nothing was written.

  the LLM call itself failed                            passed through
      `llm_chat` builds its own envelope and knows things this module does not --
      whether the provider refused (FAILED) or never answered (INDETERMINATE).
      Its result is returned verbatim so that distinction survives.

WHY NOT VERIFIED, when a read-back is a postcondition that held. Because the
predicate that held is "the bytes we wrote are the bytes on disk", and the thing
the caller actually wanted is "the issue is fixed". Nothing here compiles, lints
or runs anything. Declaring `postcondition=` on the decorator would let this
module claim the rung that renders as done, for a file full of model output that
has never been executed. That is the largest available false green in this
module and the read-back does not earn it.

One path deliberately carries no envelope: `issues` empty returns before
anything is requested or written, and the engine's default stamp is the honest
answer for it. There is nothing more than the floor to say about a step that did
nothing, and inventing an effect to describe the absence of one would be noise.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import validate_path_with_env_config
from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The only lines in this module that measure the world.
#
# `write_text` returning is an acknowledgement from the OS that it took the
# string. Reading the file back afterwards is a different fact, and it is the
# one that separates ACCEPTED from OBSERVED here exactly as `os.stat` does in
# `file.write`.
#
# Content rather than size, on purpose. `write_text(..., encoding='utf-8')`
# translates '\n' to os.linesep on the way out and `read_text` translates it
# back on the way in, so the round trip is exact on every platform while a byte
# count is not -- on Windows the file is legitimately longer than
# `len(new_content.encode('utf-8'))`, which would make a correct write look like
# a short one.
#
# What it does NOT establish: durability (no fsync), and nothing whatsoever
# about whether the code now in the file is correct.
# ---------------------------------------------------------------------------
def _read_back(path: Path, expected: str) -> Tuple[Optional[bool], Optional[str]]:
    """``(matches, None)`` when the file could be read, ``(None, why)`` when not.

    A failure here is not a failure of the write: `write_text` already returned.
    All that is lost is our ability to look, and the rung drops to match.
    """
    try:
        return path.read_text(encoding='utf-8') == expected, None
    except (OSError, UnicodeError) as error:
        reason = getattr(error, 'strerror', None) or str(error)
        return None, f"{type(error).__name__}: {reason}"


def _refused_before_dispatch(reason: str) -> Dict[str, Any]:
    """FAILED: the guard returned above the model call and above every write."""
    return envelope(
        Outcome.FAILED,
        effects=[{
            'kind': 'nothing_requested_or_written',
            'reason': reason,
            'measured_by': 'a guard that returned before the LLM call',
            'detail': (
                'No completion was requested and no file was touched. Nothing '
                'happened, and we know that rather than infer it.'
            ),
        }],
    )


def _fix_outcome(
    *,
    fix_mode: str,
    fixes_generated: int,
    writes: List[Dict[str, Any]],
    backups_written: int,
) -> Dict[str, Any]:
    """The rung the WRITES earned. The completion only ever earns ACCEPTED.

    `writes` is one entry per file `write_text` was called on, each carrying
    either a read-back verdict or the error that stopped it. An empty list means
    no write was attempted -- the normal, correct state of 'suggest' and
    'dry_run', not a degraded one.
    """
    completion_effect = {
        'kind': 'fixes_generated',
        'count': fixes_generated,
        'measured_by': 'len() over the fixes parsed out of the model response',
        'detail': (
            'How many fixes the model proposed. A count of the answer, not of '
            'anything on disk: nothing here checks that a fix is correct, or '
            'even that it is valid code.'
        ),
    }

    if not writes:
        return envelope(
            Outcome.ACCEPTED,
            effects=[
                completion_effect,
                {
                    'kind': 'no_files_written',
                    'fix_mode': fix_mode,
                    'measured_by': None,
                    'detail': (
                        f"fix_mode={fix_mode!r} attempted no write. Under "
                        "'dry_run' the `applied` list is what WOULD be applied, "
                        "computed in memory; under 'suggest' the fixes are text "
                        "for a person to read. Under 'apply' it means no fix "
                        "named a file that had been read, so nothing reached "
                        "write_text at all."
                    ),
                },
            ],
        )

    matched = [entry for entry in writes if entry['matches'] is True]
    unconfirmed = [entry for entry in writes if entry['matches'] is not True]

    written_effect = {
        'kind': 'files_written',
        'writes_attempted': len(writes),
        'read_back_matching': len(matched),
        'backups_written': backups_written,
        'files': writes,
        'measured_by': (
            'path.read_text(encoding="utf-8") after write_text returned, '
            'compared with the exact string written'
        ),
        'detail': (
            'Each file that write_text returned for was read back and compared '
            'with what was written. That measures the file which now exists -- '
            'unlike len(applied), which counts calls that did not raise and is '
            'the same number whether the bytes landed or not. It does not '
            'measure durability (nothing fsyncs) and says nothing about whether '
            'the code is correct: nothing here compiles, lints or runs it.'
        ),
    }

    if unconfirmed:
        return envelope(
            Outcome.INDETERMINATE,
            # INFERRED, not CALLER: nobody asked for this equality. It is this
            # module's own predicate, and an editor or a concurrent writer makes
            # it false without our write having gone wrong -- which is the split
            # `outcome.py` draws between FAILED and INDETERMINATE.
            claim_by=ClaimBy.INFERRED,
            effects=[
                completion_effect,
                written_effect,
                {
                    'kind': 'write_not_confirmed',
                    'predicate': 'path.read_text() == the content written',
                    'count': len(unconfirmed),
                    'files': unconfirmed,
                    'detail': (
                        'At least one file could not be read back, came back '
                        'different from what was written, or raised on the way '
                        'out. The last of those is not "unchanged": write_text '
                        'truncates at open, so a write that raised part-way '
                        'leaves a damaged file behind. We cannot say which '
                        'happened, so this is indeterminate rather than failed.'
                    ),
                },
            ],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.INFERRED,
        effects=[completion_effect, written_effect],
    )


@register_module(
    module_id='llm.code_fix',
    stability="beta",
    version='1.0.0',
    category='atomic',
    subcategory='llm',
    tags=['llm', 'ai', 'code', 'fix', 'auto', 'repair', 'atomic'],
    label='AI Code Fix',
    label_key='modules.llm.code_fix.label',
    description='Automatically generate code fixes based on issues',
    description_key='modules.llm.code_fix.description',
    icon='Wrench',
    color='#EF4444',

    # Connection types
    input_types=['any'],
    output_types=['object', 'array'],
    can_connect_to=['*'],  # Can connect to any module (file, shell, llm, etc.)
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=180000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    # Schema-driven params
    params_schema=compose(
        presets.CODE_ISSUES(required=True),
        presets.SOURCE_FILES(required=True),
        presets.FIX_MODE(default='suggest'),
        presets.CREATE_BACKUP(default=True),
        presets.TEXT(key='context', label='Additional Context', multiline=True, placeholder='This is a React project using Tailwind CSS...'),
        presets.LLM_MODEL(default='gpt-4o'),
        presets.LLM_API_KEY(),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether operation succeeded'
        ,
                'description_key': 'modules.llm.code_fix.output.ok.description'},
        'fixes': {
            'type': 'array',
            'description': 'List of generated fixes'
        ,
                'description_key': 'modules.llm.code_fix.output.fixes.description'},
        'applied': {
            'type': 'array',
            'description': 'List of applied fixes (if fix_mode is apply)'
        ,
                'description_key': 'modules.llm.code_fix.output.applied.description'},
        'failed': {
            'type': 'array',
            'description': 'Fixes that could not be applied'
        ,
                'description_key': 'modules.llm.code_fix.output.failed.description'},
        'summary': {
            'type': 'string',
            'description': 'Summary of fixes'
        ,
                'description_key': 'modules.llm.code_fix.output.summary.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the WRITES were followed: observed when every applied '
                'file was read back and matched what was written, indeterminate '
                'when one could not be, accepted when nothing was written '
                '(suggest / dry_run). Never verified -- nothing here compiles, '
                'lints or runs the code it wrote'
            ),
            'description_key': 'modules.llm.code_fix.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Fix UI Issues',
            'title_key': 'modules.llm.code_fix.examples.ui.title',
            'params': {
                'issues': '${ui_evaluation.issues}',
                'source_files': ['./src/components/Footer.tsx', './src/styles/footer.css'],
                'fix_mode': 'suggest',
                'context': 'React + Tailwind CSS project'
            }
        },
        {
            'title': 'Auto-fix and Apply',
            'title_key': 'modules.llm.code_fix.examples.apply.title',
            'params': {
                'issues': '${test_results.failures}',
                'source_files': ['./src/App.tsx'],
                'fix_mode': 'apply',
                'backup': True
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def llm_code_fix(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate and optionally apply code fixes using AI"""
    params = context['params']
    issues = params['issues']
    source_files = params['source_files']
    fix_mode = params.get('fix_mode', 'suggest')
    backup = params.get('backup', True)
    additional_context = params.get('context', '')
    model = params.get('model', 'gpt-4o')
    api_key = params.get('api_key') or os.getenv('OPENAI_API_KEY')

    if not api_key:
        return {
            'ok': False,
            'error': 'OpenAI API key not provided',
            'error_code': 'MISSING_API_KEY',
            'outcome': _refused_before_dispatch('MISSING_API_KEY'),
        }

    if not issues:
        # No envelope on purpose. Nothing was requested and nothing was written,
        # and the engine's default stamp is the honest floor for that. See the
        # module docstring.
        return {
            'ok': True,
            'fixes': [],
            'applied': [],
            'failed': [],
            'summary': 'No issues to fix'
        }

    # Read source files
    # SECURITY: source_files is caller-controlled and each entry is both read
    # here and written back below with model-generated content. Confine every
    # entry to FLYTO_SANDBOX_DIR up front so one validated path is carried
    # through to the write — this module holds the same filesystem.read /
    # filesystem.write permissions as the modules named in GHSA-wc94-386q-5478
    # and GHSA-p64w-hgfm-824v, so it needs the same boundary.
    file_contents = {}
    validated_paths: Dict[str, Path] = {}
    for file_path in source_files:
        try:
            path = Path(validate_path_with_env_config(str(file_path)))
        except Exception as e:
            logger.warning(f"Rejected source file outside the sandbox: {e}")
            continue
        if path.exists():
            try:
                file_contents[file_path] = path.read_text(encoding='utf-8')
                validated_paths[file_path] = path
            except Exception as e:
                logger.warning(f"Could not read {file_path}: {e}")

    if not file_contents:
        return {
            'ok': False,
            'error': 'No source files could be read',
            'error_code': 'NO_FILES',
            'outcome': _refused_before_dispatch('NO_FILES'),
        }

    # Build prompt for LLM
    prompt = _build_fix_prompt(issues, file_contents, additional_context)

    # Call LLM
    #
    # BUG FIX, found by giving this module an outcome rung and then asking what
    # the rung was measuring. `@register_module` replaces a function-style
    # module with a `FunctionModuleWrapper` CLASS whose constructor is
    # `(params, context)`, so `llm.chat`'s exported name is a class and not the
    # coroutine. The previous call passed it a single `{'params': ...}` dict,
    # which raised `TypeError: __init__() missing 1 required positional
    # argument: 'context'` on every invocation -- caught two lines below and
    # returned as `LLM_ERROR`. This module could not generate a fix at all: with
    # issues to fix and files it could read, the only reachable answer was that
    # error. Instantiating the wrapper the way the engine does is what makes
    # every path past this point live, including the writes.
    try:
        from .chat import llm_chat
        llm_result = await llm_chat(
            {
                'prompt': prompt,
                'system_prompt': _get_system_prompt(),
                'model': model,
                'api_key': api_key,
                'max_tokens': 4000,
                'response_format': 'json',
                'temperature': 0.3  # Lower for more consistent code
            },
            {},
        ).execute()
    except Exception as e:
        # `llm_chat` catches its own transport failures, so anything arriving
        # here broke somewhere we cannot place. The request may or may not have
        # been sent; nothing was written either way.
        return {
            'ok': False,
            'error': f'LLM call failed: {e}',
            'error_code': 'LLM_ERROR',
            'outcome': envelope(
                Outcome.INDETERMINATE,
                effects=[{
                    'kind': 'llm_call_raised',
                    'error_type': type(e).__name__,
                    'error': str(e),
                    'measured_by': None,
                    'detail': (
                        'The call to llm.chat raised rather than returning. '
                        'Whether a completion was requested and billed cannot be '
                        'told from here. No file was written.'
                    ),
                }],
            ),
        }

    if not llm_result.get('ok'):
        # Returned verbatim, envelope included: llm.chat knows whether the
        # provider refused (FAILED) or never answered (INDETERMINATE), and
        # rebuilding a rung out here would flatten that into a guess.
        return llm_result

    # Parse fixes
    fixes = _parse_fixes(llm_result.get('response', ''), llm_result.get('parsed'))

    if not fixes:
        return {
            'ok': True,
            'fixes': [],
            'applied': [],
            'failed': [],
            'summary': 'No fixes could be generated',
            'outcome': _fix_outcome(
                fix_mode=fix_mode, fixes_generated=0, writes=[], backups_written=0,
            ),
        }

    applied = []
    failed = []
    # One entry per file `write_text` returned for, with the read-back verdict.
    writes: List[Dict[str, Any]] = []
    backups_written = 0

    # Apply fixes if requested
    if fix_mode in ['apply', 'dry_run']:
        for fix in fixes:
            file_path = fix.get('file')
            if not file_path or file_path not in file_contents:
                failed.append({**fix, 'error': 'File not found'})
                continue

            original_content = file_contents[file_path]
            new_content = _apply_fix(original_content, fix)

            if new_content == original_content:
                failed.append({**fix, 'error': 'Fix could not be applied'})
                continue

            fix['diff'] = _generate_diff(original_content, new_content)

            if fix_mode == 'apply':
                # Reuse the path already validated at read time. The substring
                # '..' check this replaces never blocked an absolute path, so
                # `source_files: ["/etc/cron.d/job"]` reached write_text intact.
                path = validated_paths[file_path]

                # Create backup
                if backup:
                    backup_path = path.with_suffix(path.suffix + '.bak')
                    backup_path.write_text(original_content, encoding='utf-8')
                    backups_written += 1

                # Write fix
                try:
                    path.write_text(new_content, encoding='utf-8')
                except Exception as e:
                    # A raised write is NOT a file left alone. `write_text`
                    # opens with 'w', which truncates before the first byte is
                    # written, so a failure part-way through leaves a truncated
                    # or half-written file behind. It goes in `writes` with
                    # `matches: None` for exactly that reason -- the rung has to
                    # come out indeterminate, not accepted.
                    failed.append({**fix, 'error': str(e)})
                    writes.append({
                        'file': file_path,
                        'matches': None,
                        'write_error': str(e),
                    })
                else:
                    # The handle is closed, so this reads the file that now
                    # exists rather than racing the one being written.
                    matches, read_error = _read_back(path, new_content)
                    writes.append({
                        'file': file_path,
                        'matches': matches,
                        'read_back_error': read_error,
                    })
                    fix['read_back_matches'] = matches
                    applied.append(fix)
                    logger.info("Applied fix to source file")
            else:
                # dry_run
                applied.append(fix)

    summary = f"Generated {len(fixes)} fixes. "
    if fix_mode == 'apply':
        summary += f"Applied {len(applied)}, failed {len(failed)}."
    elif fix_mode == 'dry_run':
        summary += f"Would apply {len(applied)} fixes."
    else:
        summary += "Review and apply manually."

    logger.info(summary)

    return {
        'ok': True,
        'fixes': fixes,
        'applied': applied,
        'failed': failed,
        'summary': summary,
        'outcome': _fix_outcome(
            fix_mode=fix_mode,
            fixes_generated=len(fixes),
            writes=writes,
            backups_written=backups_written,
        ),
    }


def _get_system_prompt() -> str:
    """Get system prompt for code fixing"""
    return """You are an expert software engineer fixing code issues.

For each issue, generate a precise fix. Return JSON:
{
  "fixes": [
    {
      "file": "path/to/file.tsx",
      "issue": "Description of issue being fixed",
      "fix_type": "replace|insert|delete",
      "search": "exact code to find (for replace)",
      "replace": "new code to use",
      "line_number": 42,
      "explanation": "Why this fix works"
    }
  ],
  "summary": "Brief summary of all fixes"
}

Rules:
1. Use EXACT code matches for "search" field
2. Preserve indentation and style
3. Make minimal changes needed
4. Don't break existing functionality
5. Consider accessibility and best practices"""


def _build_fix_prompt(issues: List[Dict], files: Dict[str, str], context: str) -> str:
    """Build the fix generation prompt"""
    prompt = "Generate fixes for these issues:\n\n"

    prompt += "## Issues\n"
    for i, issue in enumerate(issues, 1):
        if isinstance(issue, dict):
            prompt += f"{i}. [{issue.get('severity', 'Unknown')}] {issue.get('description', issue)}\n"
            if issue.get('location'):
                prompt += f"   Location: {issue['location']}\n"
        else:
            prompt += f"{i}. {issue}\n"

    prompt += "\n## Source Files\n"
    for file_path, content in files.items():
        prompt += f"\n### {file_path}\n```\n{content}\n```\n"

    if context:
        prompt += f"\n## Additional Context\n{context}\n"

    return prompt


def _parse_fixes(response: str, parsed: Optional[Dict]) -> List[Dict]:
    """Parse fixes from LLM response"""
    import json

    # Try parsed first
    if parsed and isinstance(parsed, dict) and 'fixes' in parsed:
        return parsed['fixes']

    # Try to find JSON
    json_match = re.search(r'\{[\s\S]*"fixes"[\s\S]*\}', response)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if 'fixes' in data:
                return data['fixes']
        except json.JSONDecodeError:
            pass

    return []


def _apply_fix(content: str, fix: Dict) -> str:
    """Apply a single fix to content"""
    fix_type = fix.get('fix_type', 'replace')
    search = fix.get('search', '')
    replace = fix.get('replace', '')
    line_number = fix.get('line_number')

    if fix_type == 'replace' and search:
        if search in content:
            return content.replace(search, replace, 1)

    if fix_type == 'insert' and line_number:
        lines = content.split('\n')
        if 0 < line_number <= len(lines) + 1:
            lines.insert(line_number - 1, replace)
            return '\n'.join(lines)

    if fix_type == 'delete' and search:
        return content.replace(search, '', 1)

    return content


def _generate_diff(original: str, new: str) -> str:
    """Generate a simple diff"""
    import difflib

    original_lines = original.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines, new_lines,
        fromfile='original', tofile='fixed',
        lineterm=''
    )

    return ''.join(diff)
