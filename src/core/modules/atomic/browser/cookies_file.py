# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Cookies File Module — Import/export cookies to/from JSON file

Enables session persistence beyond browser profile:
- Export current cookies to a JSON file
- Import cookies from a JSON file (restore session)
- Compatible with other tools' cookie formats (Puppeteer, curl, etc.)

`cookie_count` MEANT TWO DIFFERENT THINGS AND ONE OF THEM WAS THE INPUT

Both actions returned ``"cookie_count": len(...)`` and the two ``len``s counted
opposite ends of the operation:

  export  ``len(cookies)`` over the list ``context.cookies()`` returned. That is
          a real read, of the SOURCE. It says nothing about the file, which is
          the effect -- the count is identical if the write raised, truncated,
          or landed on a full disk.
  import  ``len(clean)`` over the list this module built FROM THE FILE. It is
          the input, in `file.write`'s ``bytes_written`` shape, and it is
          reported as the number of cookies imported.

This module is `browser.cookies`' sibling and it inherits that module's measured
failure: ``add_cookies`` returns normally for a cookie the jar refuses. On the
Chromium this repo drives,

    add_cookies([{name: 'good', ...}, {name: 'past', ..., expires: 1000000}])
    context.cookies()  ->  [('good', '1')]

No exception, nothing logged, one cookie gone. An expiry in the past is not a
corner case for THIS module: a cookies file on disk is exactly where stale
expiries come from, and restoring one is what the module is for. So a saved
session that has quietly expired reported ``cookie_count: 12`` and restored
nothing.

Each action is now measured at the end it changes:

  export  the FILE, re-read from disk and parsed. OBSERVED when it is there and
          holds the same number of entries; INDETERMINATE when it cannot be read
          back or holds a different count.
  import  the JAR, re-read after ``add_cookies``. OBSERVED when at least one
          offered cookie is in it -- with the dropped names carried in the
          effect; INDETERMINATE when none of them are; ACCEPTED when the file
          (or the domain filter) offered no cookies at all, because an empty
          jar read is `database.query`'s empty result set and reads the same
          whether nothing was offered or everything was refused.

Partial import is OBSERVED and not FAILED on purpose: the ladder's OBSERVED is
"we saw the world change. Not that the right thing changed", and a jar that took
eight of twelve cookies did change. Which four went is in the effect rather than
in the rung.

What OBSERVED does NOT say for export: a re-read of a path proves a file with
that content is there now, not that this call is what put it there. A previous
export of the same jar to the same path is indistinguishable. That is the same
bound `browser.pdf` and `browser.screenshot` carry on ``st_size``.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import validate_path_with_env_config
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)


def _read_back_file(path: Path) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """``(entry_count, bytes_on_disk, None)`` for a file we could parse, else the reason.

    Parsed rather than stat'ed. ``st_size`` alone would call a half-written or
    truncated JSON array a successful export -- and the failure this read exists
    to catch is precisely a write that did not finish.
    """
    try:
        raw = path.read_bytes()
    except OSError as error:
        return None, None, f"{type(error).__name__}: {error.strerror or error}"
    try:
        parsed = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, len(raw), f"{type(error).__name__}: {error}"
    if not isinstance(parsed, list):
        return None, len(raw), 'the file does not hold a JSON array'
    return len(parsed), len(raw), None


def _export_outcome(
    *,
    path: str,
    jar_count: int,
    entries_on_disk: Optional[int],
    bytes_on_disk: Optional[int],
    read_error: Optional[str],
) -> Dict[str, Any]:
    """The rung an export earned, decided by re-reading the file it wrote."""
    source_effect = {
        'kind': 'cookies_read_from_jar',
        'count': jar_count,
        'measured_by': 'BrowserContext.cookies(), read from the browser cookie store',
        'detail': (
            'The source of the export, and a real read -- but of the jar, not of '
            'the file. It is unchanged if the write never landed.'
        ),
    }

    if entries_on_disk is None or entries_on_disk != jar_count:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[
                source_effect,
                {
                    'kind': 'cookie_file_unconfirmed',
                    'path': path,
                    'predicate': 'the file parses as a JSON array of the exported cookies',
                    'entries_on_disk': entries_on_disk,
                    'bytes_on_disk': bytes_on_disk,
                    'expected_entries': jar_count,
                    'measured_by': 'json.loads of the output path, read back after the write',
                    'reason': read_error or (
                        f'the file holds {entries_on_disk} entries, {jar_count} were written'
                    ),
                    'detail': (
                        'write_text() returned without raising and the file is '
                        'not what was written to it. Indeterminate rather than '
                        'failed: no postcondition was declared about the path '
                        'and another process may have replaced the file between '
                        'the write and this read.'
                    ),
                },
            ],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.INFERRED,
        effects=[
            source_effect,
            {
                'kind': 'cookie_file_written',
                'path': path,
                'entries_on_disk': entries_on_disk,
                'bytes_on_disk': bytes_on_disk,
                'measured_by': 'json.loads of the output path, read back after the write',
                'detail': (
                    'The file parses and holds one entry per exported cookie. It '
                    'does not follow that this call is what put it there: an '
                    'identical earlier export to the same path reads the same.'
                ),
            },
        ],
    )


def _import_outcome(
    *,
    path: str,
    offered: int,
    stored: int,
    missing: List[str],
) -> Dict[str, Any]:
    """The rung an import earned, decided by re-reading the jar."""
    offered_effect = {
        'kind': 'cookies_offered',
        'path': path,
        'count': offered,
        'measured_by': 'len() of the list parsed out of the file',
        'detail': (
            'How many cookies the file offered. No browser call contributes to '
            'it: add_cookies() returns normally for every cookie the jar '
            'refuses, so this reads the same whether all of them landed or none '
            'did.'
        ),
    }

    if offered == 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                offered_effect,
                {
                    'kind': 'no_cookies_offered',
                    'measured_by': None,
                    'detail': (
                        'The file, after the domain filter, held no cookies. '
                        'add_cookies([]) was accepted and the jar was not asked '
                        'to change, so there is nothing to have observed.'
                    ),
                },
            ],
        )

    jar_effect = {
        'kind': 'cookie_jar_observed' if stored else 'cookie_jar_unconfirmed',
        'offered': offered,
        'stored': stored,
        'dropped_names': missing,
        'predicate': 'each imported cookie is in the jar afterwards, by name and value',
        'measured_by': 'BrowserContext.cookies(), read back after add_cookies()',
        'detail': (
            'Matched on name and value, which is what browser.cookies compares: '
            'the jar normalises the domain, so comparing that would report a '
            'stored cookie as missing.'
        ),
    }

    if stored:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            effects=[offered_effect, jar_effect] + ([{
                'kind': 'cookies_dropped',
                'count': len(missing),
                'names': missing,
                'detail': (
                    'These are not in the jar. add_cookies() does not raise for '
                    'a cookie it refuses -- an expiry in the past is the '
                    'measured case, and a saved session file is where those come '
                    'from. The jar did change, so the rung stays on the ladder; '
                    'which cookies made it is here rather than in the rung.'
                ),
            }] if missing else []),
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            offered_effect,
            jar_effect,
            {
                'kind': 'cookies_dropped',
                'count': len(missing),
                'names': missing,
                'detail': (
                    'Not one offered cookie is in the jar. Every expiry in the '
                    'file being in the past does this, and so does a page '
                    'clearing cookies between the write and this read, so this '
                    'is indeterminate rather than failed.'
                ),
            },
        ],
    )


@register_module(
    module_id='browser.cookies_file',
    version='1.0.0',
    category='browser',
    tags=['browser', 'cookies', 'session', 'export', 'import', 'persistence'],
    label='Cookies File',
    label_key='modules.browser.cookies_file.label',
    description='Import or export browser cookies to/from a JSON file for session persistence.',
    description_key='modules.browser.cookies_file.description',
    icon='FileJson',
    color='#F97316',
    input_types=['page'],
    output_types=['json'],
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],
    params_schema=compose(
        field('action', type='select', label='Action',
              description='Export cookies to file or import from file.',
              required=True, default='export',
              options=[
                  {'value': 'export', 'label': 'Export to file'},
                  {'value': 'import', 'label': 'Import from file'},
              ],
              group='basic'),
        field('file_path', type='string', label='File path',
              description='Path to the JSON cookies file.',
              required=True, placeholder='~/.flyto/cookies/site.json',
              format='path',
              group='basic'),
        field('domain_filter', type='string', label='Domain filter',
              description='Only export/import cookies for this domain (e.g., ".github.com"). Empty = all.',
              required=False, default='',
              group='advanced'),
    ),
    output_schema={
        'action':       {'type': 'string', 'description': 'Action performed (export/import)'},
        'cookie_count': {'type': 'number', 'description': 'Cookies exported, or cookies actually found in the jar after an import'},
        'offered_count': {'type': 'number', 'description': 'Cookies the file offered (import only) — may exceed cookie_count'},
        'dropped_names': {'type': 'array', 'description': 'Names the jar refused (import only)'},
        'entries_on_disk': {'type': 'number', 'description': 'Entries parsed back out of the written file (export only)'},
        'bytes_on_disk': {'type': 'number', 'description': 'Size of the written file (export only)'},
        'file_path':    {'type': 'string', 'description': 'Path to the cookies file'},
        'domains':      {'type': 'array',  'description': 'Unique domains in the cookies'},
        'outcome':      {'type': 'object', 'description': (
            'How far the effect was followed: export is observed when the file '
            'parses back with the same entry count, import when the jar holds '
            'the imported cookies afterwards'
        )},
    },
    examples=[
        {'name': 'Export all cookies', 'params': {'action': 'export', 'file_path': 'cookies.json'}},
        {'name': 'Import session', 'params': {'action': 'import', 'file_path': 'cookies.json'}},
        {'name': 'Export for specific domain', 'params': {'action': 'export', 'file_path': 'gh.json', 'domain_filter': '.github.com'}},
    ],
    author='Flyto2 Team', license='MIT', timeout_ms=10000,
    required_permissions=["browser.read", "browser.write"],
)
class BrowserCookiesFileModule(BaseModule):
    module_name = "Cookies File"
    required_permission = "browser.write"

    def validate_params(self) -> None:
        self.action = self.params.get('action', 'export')
        if self.action not in ('export', 'import'):
            raise ValueError(f"Invalid action: {self.action}")
        raw_path = self.params.get('file_path', '')
        if not raw_path:
            raise ValueError("file_path is required")
        self.file_path = Path(validate_path_with_env_config(raw_path))
        self.domain_filter = self.params.get('domain_filter', '')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        context = browser._context

        if self.action == 'export':
            return await self._export(context)
        else:
            return await self._import(context)

    async def _export(self, context) -> dict:
        file_path = Path(validate_path_with_env_config(str(self.file_path)))
        cookies = await context.cookies()

        if self.domain_filter:
            cookies = [c for c in cookies if self.domain_filter in c.get('domain', '')]

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(cookies, indent=2, default=str), encoding='utf-8')

        # The file is the effect; the jar was only the source. Re-read and parse
        # it rather than trusting write_text() to have finished.
        entries_on_disk, bytes_on_disk, read_error = _read_back_file(file_path)

        domains = sorted({c.get('domain', '') for c in cookies})
        logger.info("Exported %d cookies to %s", len(cookies), file_path)

        return {
            "status": "success",
            "action": "export",
            "cookie_count": len(cookies),
            "entries_on_disk": entries_on_disk,
            "bytes_on_disk": bytes_on_disk,
            "file_path": str(file_path),
            "domains": domains,
            "outcome": _export_outcome(
                path=str(file_path),
                jar_count=len(cookies),
                entries_on_disk=entries_on_disk,
                bytes_on_disk=bytes_on_disk,
                read_error=read_error,
            ),
        }

    async def _import(self, context) -> dict:
        file_path = Path(validate_path_with_env_config(str(self.file_path)))
        if not file_path.exists():
            raise FileNotFoundError(f"Cookie file not found: {file_path}")

        data = json.loads(file_path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise ValueError("Cookie file must contain a JSON array")

        cookies = data
        if self.domain_filter:
            cookies = [c for c in cookies if self.domain_filter in c.get('domain', '')]

        # Playwright expects specific fields; strip extras
        clean = []
        for c in cookies:
            entry = {
                'name': c['name'],
                'value': c['value'],
                'domain': c.get('domain', ''),
                'path': c.get('path', '/'),
            }
            if c.get('expires'):
                entry['expires'] = c['expires']
            if c.get('httpOnly') is not None:
                entry['httpOnly'] = c['httpOnly']
            if c.get('secure') is not None:
                entry['secure'] = c['secure']
            if c.get('sameSite'):
                entry['sameSite'] = c['sameSite']
            clean.append(entry)

        await context.add_cookies(clean)

        # add_cookies() returns normally for every cookie the jar refuses, so
        # this read is the only thing that separates imported from dropped.
        jar = {(c.get('name'), c.get('value')) for c in await context.cookies()}
        stored_names = [c['name'] for c in clean if (c['name'], c['value']) in jar]
        missing_names = [c['name'] for c in clean if (c['name'], c['value']) not in jar]

        domains = sorted({c.get('domain', '') for c in clean})
        logger.info(
            "Imported %d of %d cookies from %s", len(stored_names), len(clean), file_path
        )
        if missing_names:
            logger.warning(
                "%d cookies from %s are not in the jar: %s",
                len(missing_names), file_path, missing_names,
            )

        return {
            "status": "success",
            "action": "import",
            # Read back, not counted from the file: this used to be len(clean).
            "cookie_count": len(stored_names),
            "offered_count": len(clean),
            "dropped_names": missing_names,
            "file_path": str(file_path),
            "domains": domains,
            "outcome": _import_outcome(
                path=str(file_path),
                offered=len(clean),
                stored=len(stored_names),
                missing=missing_names,
            ),
        }
