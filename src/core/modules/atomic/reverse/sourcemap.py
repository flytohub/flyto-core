# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Sourcemap Module

Resolve a (generated line, generated column) location in a minified/bundled
JS file back to its original (pre-build) source file/line/column/name, using
a Source Map v3 payload. CDP has no native "resolve to original source"
capability (Chrome's own DevTools decodes the VLQ mappings client-side), so
this implements the decode itself — a hand-rolled VLQ decoder rather than a
pip dependency, since the one plausible package (`sourcemap` on PyPI) has
had no release since 2017 despite the Source Map v3 spec being small and
stable. See DECISIONS.md.

Session-independent like reverse.code: takes the source map JSON (or a
`data:` URI) as a plain text parameter — typically discovered via
`reverse.scripts` (action=list)'s existing `sourceMapURL` field per script,
then fetched with `http.get` (already SSRF-guarded) if it's an external
`.map` URL rather than an inline `data:` URI. This module never fetches
anything itself, never touches a browser/CDP session, and requires no
permission.
"""
import base64
import bisect
import json
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ...types import StabilityLevel

_B64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_B64_VALUES = {c: i for i, c in enumerate(_B64_CHARS)}


def _decode_vlq_value(s: str, pos: int):
    """Decode one base64-VLQ value starting at `pos`. Returns (value, next_pos)."""
    result = 0
    shift = 0
    while True:
        digit = _B64_VALUES[s[pos]]
        pos += 1
        continuation = digit & 0x20
        result += (digit & 0x1F) << shift
        if not continuation:
            break
        shift += 5
    if result & 1:
        return -(result >> 1), pos
    return result >> 1, pos


def _decode_segment(segment_str: str) -> List[int]:
    values = []
    pos = 0
    while pos < len(segment_str):
        value, pos = _decode_vlq_value(segment_str, pos)
        values.append(value)
    return values


def _parse_mappings(mappings: str) -> List[dict]:
    """Decode a Source Map v3 `mappings` string into a list of segments.

    generatedColumn resets to 0 at the start of each generated line (each
    ';'), but sourceIndex/sourceLine/sourceColumn/nameIndex deltas accumulate
    across the entire mappings string, not per line.
    """
    segments = []
    generated_line = 0
    source_index = 0
    source_line = 0
    source_column = 0
    name_index = 0

    for line_str in mappings.split(';'):
        generated_column = 0
        if line_str:
            for segment_str in line_str.split(','):
                if not segment_str:
                    continue
                values = _decode_segment(segment_str)
                generated_column += values[0]
                has_source = len(values) >= 4
                has_name = len(values) == 5
                if has_source:
                    source_index += values[1]
                    source_line += values[2]
                    source_column += values[3]
                if has_name:
                    name_index += values[4]
                segments.append({
                    'generatedLine': generated_line,
                    'generatedColumn': generated_column,
                    'sourceIndex': source_index if has_source else None,
                    'sourceLine': source_line if has_source else None,
                    'sourceColumn': source_column if has_source else None,
                    'nameIndex': name_index if has_name else None,
                })
        generated_line += 1
    return segments


def _resolve_sources(source_map: dict) -> List[str]:
    sources = source_map.get('sources') or []
    source_root = source_map.get('sourceRoot') or ''
    if source_root and not source_root.endswith('/'):
        source_root += '/'
    return [f"{source_root}{s}" for s in sources] if source_root else list(sources)


def _parse_source_map_text(text: str) -> dict:
    """Accept either raw Source Map v3 JSON, or a `data:` URI containing it."""
    text = text.strip()
    if text.startswith('data:'):
        _, _, payload = text.partition(',')
        if ';base64' in text.split(',', 1)[0]:
            payload = base64.b64decode(payload).decode('utf-8', errors='replace')
        text = payload
    return json.loads(text)


class _SourceMapIndex:
    """Parsed Source Map v3 payload, ready for generated->original lookups."""

    def __init__(self, source_map: dict):
        self.sources = source_map.get('sources') or []
        self.resolved_sources = _resolve_sources(source_map)
        self.sources_content = source_map.get('sourcesContent') or []
        self.names = source_map.get('names') or []
        self.segments = _parse_mappings(source_map.get('mappings', ''))
        self._keys = [(s['generatedLine'], s['generatedColumn']) for s in self.segments]

    def lookup(self, line: int, column: int) -> Optional[dict]:
        idx = bisect.bisect_right(self._keys, (line, column)) - 1
        if idx < 0:
            return None
        segment = self.segments[idx]
        if segment['sourceIndex'] is None:
            return None

        source_index = segment['sourceIndex']
        source = self.resolved_sources[source_index] if source_index < len(self.resolved_sources) else None
        content = self.sources_content[source_index] if source_index < len(self.sources_content) else None
        name_index = segment['nameIndex']
        name = self.names[name_index] if name_index is not None and name_index < len(self.names) else None

        return {
            'source': source,
            'sourceContent': content,
            'originalLine': segment['sourceLine'],
            'originalColumn': segment['sourceColumn'],
            'name': name,
        }


@register_module(
    module_id='reverse.sourcemap',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'sourcemap', 'vlq', 'javascript', 'deobfuscation'],
    label='Source Map Resolver',
    label_key='modules.reverse.sourcemap.label',
    description='Resolve a generated code location to its original source file/line/column',
    description_key='modules.reverse.sourcemap.description',
    icon='MapPin',
    color='#DC2626',

    input_types=['string'],
    output_types=['object'],

    can_receive_from=['reverse.*', 'http.*', 'flow.*'],
    can_connect_to=['reverse.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],

    params_schema=compose(
        field(
            'action',
            type='select',
            label='Action',
            label_key='modules.reverse.sourcemap.params.action.label',
            description='Source map operation to perform',
            required=True,
            options=[
                {'value': 'resolve', 'label': 'Resolve generated location'},
                {'value': 'list_sources', 'label': 'List source files'},
                {'value': 'get_original_source', 'label': 'Get embedded original source'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'source_map',
            type='string',
            label='Source Map',
            label_key='modules.reverse.sourcemap.params.source_map.label',
            description='Source Map v3 JSON text, or a data: URI containing it (e.g. from reverse.scripts sourceMapURL, or fetched via http.get)',
            placeholder='{"version":3,"sources":["app.js"],"mappings":"..."}',
            required=True,
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'generated_line',
            type='number',
            label='Generated Line',
            label_key='modules.reverse.sourcemap.params.generated_line.label',
            description='Zero-based line number in the generated (minified/bundled) file — required for resolve',
            required=False,
            min=0,
            showIf={"action": {"$in": ["resolve"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'generated_column',
            type='number',
            label='Generated Column',
            label_key='modules.reverse.sourcemap.params.generated_column.label',
            description='Zero-based column number in the generated file',
            default=0,
            required=False,
            min=0,
            showIf={"action": {"$in": ["resolve"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'source',
            type='string',
            label='Source',
            label_key='modules.reverse.sourcemap.params.source.label',
            description='A source path from list_sources, or its zero-based index — required for get_original_source',
            placeholder='app.js',
            required=False,
            showIf={"action": {"$in": ["get_original_source"]}},
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.sourcemap.output.status.description'},
        'source': {'type': 'string', 'description': 'Original source file path, or null if unmapped (resolve action)',
                'description_key': 'modules.reverse.sourcemap.output.source.description'},
        'originalLine': {'type': 'number', 'description': 'Zero-based original line number (resolve action)',
                'description_key': 'modules.reverse.sourcemap.output.originalLine.description'},
        'originalColumn': {'type': 'number', 'description': 'Zero-based original column number (resolve action)',
                'description_key': 'modules.reverse.sourcemap.output.originalColumn.description'},
        'name': {'type': 'string', 'description': 'Original identifier name, if recorded (resolve action)',
                'description_key': 'modules.reverse.sourcemap.output.name.description'},
        'sources': {'type': 'array', 'description': 'Source file paths (list_sources action)',
                'description_key': 'modules.reverse.sourcemap.output.sources.description'},
        'content': {'type': 'string', 'description': 'Embedded original source text (get_original_source action)',
                'description_key': 'modules.reverse.sourcemap.output.content.description'},
    },
    examples=[
        {'name': 'Resolve a minified location', 'params': {'action': 'resolve', 'source_map': '{"version":3,"sources":["app.js"],"mappings":"AAAA"}', 'generated_line': 0, 'generated_column': 0}},
        {'name': 'List source files', 'params': {'action': 'list_sources', 'source_map': '{"version":3,"sources":["app.js"],"mappings":""}'}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    # No permission gate, like reverse.code: pure text-in/structured-out,
    # no browser/CDP access, and never fetches anything itself (external
    # .map URLs are fetched by the caller via the already SSRF-guarded
    # http.get, not by this module). See DECISIONS.md.
    required_permissions=[],
)
class ReverseSourcemapModule(BaseModule):
    """Resolve a generated code location to its original source file/line/column."""

    module_name = "Source Map Resolver"
    module_description = "Resolve a generated code location to its original source"
    required_permission = ""

    def validate_params(self) -> None:
        self.action = self.params.get('action')
        if self.action not in ('resolve', 'list_sources', 'get_original_source'):
            raise ValueError(
                f"Invalid action: {self.action}. Must be resolve, list_sources, or get_original_source"
            )

        self.source_map_text = self.params.get('source_map')
        if not self.source_map_text:
            raise ValueError("Missing required parameter: source_map")

        self.generated_line = self.params.get('generated_line')
        if self.action == 'resolve' and self.generated_line is None:
            raise ValueError("resolve requires generated_line")
        self.generated_column = self.params.get('generated_column', 0)

        self.source = self.params.get('source')
        if self.action == 'get_original_source' and not self.source:
            raise ValueError("get_original_source requires source")

    async def execute(self) -> Dict[str, Any]:
        try:
            source_map = _parse_source_map_text(self.source_map_text)
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid source map: {exc}") from exc

        if self.action == 'resolve':
            index = _SourceMapIndex(source_map)
            match = index.lookup(int(self.generated_line), int(self.generated_column))
            if match is None:
                return {'status': 'success', 'source': None, 'originalLine': None, 'originalColumn': None, 'name': None}
            return {'status': 'success', **{k: v for k, v in match.items() if k != 'sourceContent'}}

        if self.action == 'list_sources':
            resolved_sources = _resolve_sources(source_map)
            sources_content = source_map.get('sourcesContent') or []
            sources = [
                {'source': src, 'hasContent': i < len(sources_content) and sources_content[i] is not None}
                for i, src in enumerate(resolved_sources)
            ]
            return {'status': 'success', 'sources': sources}

        return self._get_original_source(source_map)

    def _get_original_source(self, source_map: dict) -> Dict[str, Any]:
        raw_sources = source_map.get('sources') or []
        resolved_sources = _resolve_sources(source_map)
        sources_content = source_map.get('sourcesContent') or []

        index = None
        if self.source.isdigit():
            candidate = int(self.source)
            if 0 <= candidate < len(resolved_sources):
                index = candidate
        if index is None:
            for candidates in (resolved_sources, raw_sources):
                if self.source in candidates:
                    index = candidates.index(self.source)
                    break

        if index is None:
            return {'status': 'success', 'content': None, 'error': f"Unknown source: {self.source}"}

        content = sources_content[index] if index < len(sources_content) else None
        if content is None:
            return {'status': 'success', 'content': None, 'error': 'Source content is not embedded in this source map'}
        return {'status': 'success', 'content': content}
