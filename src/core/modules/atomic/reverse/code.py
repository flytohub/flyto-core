# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Code Module

Beautify minified/obfuscated JavaScript and search its AST for function
declarations, string literals, and call sites — Phase 3 of the
reverse-engineering toolkit. Pure Python (tree-sitter + jsbeautifier), no
Node.js involved. Operates on any JS source string — typically the output
of a prior reverse.scripts get_source step — and does not touch a browser,
CDP session, or execute the code, so it carries none of the elevated risk
the rest of reverse.* has and requires no special permission. Real semantic
deobfuscation (control-flow-flattening reversal, string-array decoding) is
out of scope here; see DECISIONS.md and ROADMAP.md 0.5 (Phase 4).
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...errors import ModuleError
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ...types import StabilityLevel

_MISSING_DEPS_MESSAGE = (
    "tree-sitter, tree-sitter-javascript, and jsbeautifier are required for "
    "reverse.code. Install with: pip install 'flyto-core[jsast]'"
)


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


@register_module(
    module_id='reverse.code',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'ast', 'beautify', 'javascript', 'deobfuscation'],
    label='Code Analysis',
    label_key='modules.reverse.code.label',
    description='Beautify minified JavaScript and search its AST for functions, strings, and call sites',
    description_key='modules.reverse.code.description',
    icon='FileCode2',
    color='#DC2626',

    input_types=['string'],
    output_types=['object'],

    can_receive_from=['reverse.*', 'flow.*'],
    can_connect_to=['reverse.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],

    params_schema=compose(
        field(
            'action',
            type='select',
            label='Action',
            label_key='modules.reverse.code.params.action.label',
            description='Code analysis operation to perform',
            required=True,
            options=[
                {'value': 'beautify', 'label': 'Beautify source'},
                {'value': 'list_functions', 'label': 'List function declarations'},
                {'value': 'list_strings', 'label': 'List string literals'},
                {'value': 'find_calls', 'label': 'Find call sites'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'source',
            type='string',
            label='JavaScript Source',
            label_key='modules.reverse.code.params.source.label',
            description='JavaScript source text to analyze, e.g. from reverse.scripts get_source',
            placeholder='function a(x){return x*2}',
            required=True,
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'function_name',
            type='string',
            label='Function Name',
            label_key='modules.reverse.code.params.function_name.label',
            description='Function name to search for (e.g. "fetch" or "obj.method") — required for find_calls',
            placeholder='fetch',
            required=False,
            showIf={"action": {"$in": ["find_calls"]}},
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.code.output.status.description'},
        'formatted': {'type': 'string', 'description': 'Beautified source (beautify action)',
                'description_key': 'modules.reverse.code.output.formatted.description'},
        'functions': {'type': 'array', 'description': 'Function declarations found (list_functions action)',
                'description_key': 'modules.reverse.code.output.functions.description'},
        'strings': {'type': 'array', 'description': 'String literals found (list_strings action)',
                'description_key': 'modules.reverse.code.output.strings.description'},
        'calls': {'type': 'array', 'description': 'Call sites found (find_calls action)',
                'description_key': 'modules.reverse.code.output.calls.description'},
    },
    examples=[
        {'name': 'Beautify minified source', 'params': {'action': 'beautify', 'source': 'function a(x){return x*2}'}},
        {'name': 'List function declarations', 'params': {'action': 'list_functions', 'source': 'function login(u,p){}'}},
        {'name': 'Find fetch call sites', 'params': {'action': 'find_calls', 'source': 'fetch("/api")', 'function_name': 'fetch'}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    # No permission gate, unlike every other reverse.* module: this operates
    # on a plain JS source string, never touches a browser/CDP session, and
    # never executes the code (tree-sitter only parses; jsbeautifier only
    # reformats). See DECISIONS.md.
    required_permissions=[],
)
class ReverseCodeModule(BaseModule):
    """Beautify JavaScript and search its AST for functions, strings, and call sites."""

    module_name = "Code Analysis"
    module_description = "Beautify minified JS and search its AST"
    required_permission = ""

    def validate_params(self) -> None:
        self.action = self.params.get('action')
        if self.action not in ('beautify', 'list_functions', 'list_strings', 'find_calls'):
            raise ValueError(
                f"Invalid action: {self.action}. Must be beautify, list_functions, list_strings, or find_calls"
            )

        self.source = self.params.get('source')
        if not self.source:
            raise ValueError("Missing required parameter: source")

        self.function_name = self.params.get('function_name')
        if self.action == 'find_calls' and not self.function_name:
            raise ValueError("find_calls requires function_name")

    async def execute(self) -> Dict[str, Any]:
        if self.action == 'beautify':
            return {'status': 'success', 'formatted': self._beautify()}

        tree, source_bytes = self._parse()

        if self.action == 'list_functions':
            functions = self._list_functions(tree, source_bytes)
            return {'status': 'success', 'functions': functions, 'count': len(functions)}

        if self.action == 'list_strings':
            strings = self._list_strings(tree, source_bytes)
            return {'status': 'success', 'strings': strings, 'count': len(strings)}

        calls = self._find_calls(tree, source_bytes, self.function_name)
        return {'status': 'success', 'calls': calls, 'count': len(calls)}

    def _beautify(self) -> str:
        try:
            import jsbeautifier
        except ImportError as exc:
            raise ModuleError(_MISSING_DEPS_MESSAGE) from exc

        return jsbeautifier.beautify(self.source)

    def _parse(self):
        try:
            from tree_sitter import Language, Parser
            import tree_sitter_javascript as tsjs
        except ImportError as exc:
            raise ModuleError(_MISSING_DEPS_MESSAGE) from exc

        language = Language(tsjs.language())
        parser = Parser(language)
        source_bytes = self.source.encode('utf-8')
        return parser.parse(source_bytes), source_bytes

    def _list_functions(self, tree, source_bytes: bytes) -> List[dict]:
        functions = []
        for node in _walk(tree.root_node):
            if node.type == 'function_declaration':
                name_node = node.child_by_field_name('name')
                functions.append({
                    'name': self._text(name_node, source_bytes) if name_node else None,
                    'startLine': node.start_point[0],
                    'endLine': node.end_point[0],
                })
            elif node.type == 'method_definition':
                name_node = node.child_by_field_name('name')
                functions.append({
                    'name': self._text(name_node, source_bytes) if name_node else None,
                    'startLine': node.start_point[0],
                    'endLine': node.end_point[0],
                })
            elif node.type == 'variable_declarator':
                value = node.child_by_field_name('value')
                if value is not None and value.type in ('function_expression', 'arrow_function'):
                    name_node = node.child_by_field_name('name')
                    functions.append({
                        'name': self._text(name_node, source_bytes) if name_node else None,
                        'startLine': value.start_point[0],
                        'endLine': value.end_point[0],
                    })
        return functions

    def _list_strings(self, tree, source_bytes: bytes) -> List[dict]:
        strings = []
        for node in _walk(tree.root_node):
            if node.type in ('string', 'template_string'):
                strings.append({
                    'value': self._text(node, source_bytes),
                    'startLine': node.start_point[0],
                })
        return strings

    def _find_calls(self, tree, source_bytes: bytes, function_name: str) -> List[dict]:
        calls = []
        target = function_name.rsplit('.', 1)[-1]
        for node in _walk(tree.root_node):
            if node.type != 'call_expression':
                continue
            fn = node.child_by_field_name('function')
            if fn is None:
                continue

            matched = False
            if fn.type == 'identifier' and self._text(fn, source_bytes) == function_name:
                matched = True
            elif fn.type == 'member_expression':
                prop = fn.child_by_field_name('property')
                if prop is not None and self._text(prop, source_bytes) == target:
                    matched = True

            if matched:
                arguments = node.child_by_field_name('arguments')
                calls.append({
                    'startLine': node.start_point[0],
                    'startColumn': node.start_point[1],
                    'argsText': self._text(arguments, source_bytes) if arguments else '',
                })
        return calls

    @staticmethod
    def _text(node, source_bytes: bytes) -> str:
        return source_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace')
