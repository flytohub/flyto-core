# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Verify Figma Module - Fetch design tokens from Figma API

Runs locally with user's own Figma token.
Token never leaves the user's machine.

HOW FAR THIS MODULE FOLLOWS REALITY

Despite the category, this module verifies nothing. It issues one GET and
parses the reply to that same GET. So the ceiling is ACCEPTED, for the reason
`http.request` settled for every 2xx in this product: a body Figma composed
about its own file is Figma's word for it. Reaching OBSERVED would take a
second, independent look, and there is not one.

What is worth the branch is the OTHER axis. This module takes a target from the
caller -- a `node_id`, or a `node_name` -- and there are three outcomes to
asking for one, not two:

  the reply carried a node                    ACCEPTED, claim_by=caller
  the reply carried no node for that target   FAILED, claim_by=caller

FAILED and not INDETERMINATE because `engine/outcome.py` splits exactly this on
who made the claim: the caller named the node, so a reply without it is a
broken contract rather than a guess of ours that may be wrong.

THE BUG THIS FOUND, and it is the reason the second branch exists at all. Only
one of those two cases used to be visible. `node_name` not found already
returned `ok: False`. But `node_id` not found did not:

    nodes.get(self.node_id, {}).get('document', {})

returns `{}` for an id Figma did not send back, `parse_node({})` turns that into
`FigmaNode(id='', name='', type='')` with an empty style, and the module
returned `ok: True` with it. A caller asking for the padding of one component
got `{'style': {}}` and a success -- indistinguishable from a component with no
style overrides. `{}` is the textbook value that reads the same whether the
effect happened or not, and the rung is now decided by `bool(node.id)`: a node
id is a value only Figma can have put there.

The same shape sits on the whole-file path: `data.get('document', {})` is `{}`
for any 200 whose body is not the shape this module expects, and that also now
lands on FAILED rather than on an empty success.

WHAT IS NOT CLAIMED, and specifically not claimed by the module named `verify`:
`find_by_name` walking the tree and finding a node is a selector over data we
were handed, not a check that anything we did took effect. Declaring it as a
`postcondition=` would raise this module's ceiling to VERIFIED on every path,
so an ACCEPTED file fetch would start carrying a predicate string it never
evaluated. A read cannot be dressed up as a proof by declaring one.

WHAT NEVER REACHES A CONSUMER: `response.raise_for_status()` and the httpx
timeout raise out of `execute()`, so a 401, a 404 on the file, or a stalled
connection produce an exception and no payload -- and therefore no
INDETERMINATE envelope. Converting those raises into returns would change what
the retry machinery sees for three separate failure kinds, which is a larger
change than this one and is written down instead of made.
"""
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field as schema_field

FIGMA_API_BASE = "https://api.figma.com/v1"


@dataclass
class FigmaStyle:
    """Extracted style from a Figma node."""
    # Typography
    font_family: Optional[str] = None
    font_size: Optional[float] = None
    font_weight: Optional[int] = None
    line_height: Optional[float] = None
    letter_spacing: Optional[float] = None
    text_align: Optional[str] = None

    # Colors
    fill_color: Optional[str] = None
    stroke_color: Optional[str] = None
    background_color: Optional[str] = None

    # Spacing / Layout
    padding_top: Optional[float] = None
    padding_right: Optional[float] = None
    padding_bottom: Optional[float] = None
    padding_left: Optional[float] = None
    gap: Optional[float] = None

    # Size
    width: Optional[float] = None
    height: Optional[float] = None

    # Border
    border_radius: Optional[float] = None
    border_width: Optional[float] = None

    # Effects
    opacity: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class FigmaNode:
    """A node from Figma file."""
    id: str
    name: str
    type: str
    style: FigmaStyle = field(default_factory=FigmaStyle)
    children: List["FigmaNode"] = field(default_factory=list)

    def find_by_name(self, name: str) -> Optional["FigmaNode"]:
        """Find child node by name (recursive)."""
        if self.name == name:
            return self
        for child in self.children:
            found = child.find_by_name(name)
            if found:
                return found
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'style': self.style.to_dict(),
        }


def rgba_to_hex(color: Dict[str, float]) -> str:
    """Convert Figma RGBA to hex."""
    r = int(color.get('r', 0) * 255)
    g = int(color.get('g', 0) * 255)
    b = int(color.get('b', 0) * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def extract_style(data: Dict[str, Any]) -> FigmaStyle:
    """Extract style properties from Figma node data."""
    style = FigmaStyle()

    # Typography
    type_style = data.get('style', {})
    if type_style:
        style.font_family = type_style.get('fontFamily')
        style.font_size = type_style.get('fontSize')
        style.font_weight = type_style.get('fontWeight')
        lh = type_style.get('lineHeightPx')
        if lh:
            style.line_height = lh
        style.letter_spacing = type_style.get('letterSpacing')
        style.text_align = type_style.get('textAlignHorizontal', '').lower() or None

    # Colors (fills)
    fills = data.get('fills', [])
    if fills and fills[0].get('type') == 'SOLID':
        color = fills[0].get('color', {})
        style.fill_color = rgba_to_hex(color)

    # Background
    bg = data.get('backgroundColor')
    if bg:
        style.background_color = rgba_to_hex(bg)

    # Strokes
    strokes = data.get('strokes', [])
    if strokes and strokes[0].get('type') == 'SOLID':
        color = strokes[0].get('color', {})
        style.stroke_color = rgba_to_hex(color)
        style.border_width = data.get('strokeWeight')

    # Size
    box = data.get('absoluteBoundingBox', {})
    style.width = box.get('width')
    style.height = box.get('height')

    # Padding (auto-layout)
    style.padding_top = data.get('paddingTop')
    style.padding_right = data.get('paddingRight')
    style.padding_bottom = data.get('paddingBottom')
    style.padding_left = data.get('paddingLeft')
    style.gap = data.get('itemSpacing')

    # Border
    style.border_radius = data.get('cornerRadius')
    style.opacity = data.get('opacity')

    return style


def parse_node(data: Dict[str, Any]) -> FigmaNode:
    """Parse raw Figma node data into FigmaNode."""
    node = FigmaNode(
        id=data.get('id', ''),
        name=data.get('name', ''),
        type=data.get('type', ''),
    )
    node.style = extract_style(data)

    for child_data in data.get('children', []):
        node.children.append(parse_node(child_data))

    return node


def _figma_node_read(*, target_kind: str, target: Optional[str], node: "FigmaNode") -> Dict[str, Any]:
    """ACCEPTED -- Figma answered and its answer carried a node.

    `style_fields` is recorded and does not decide anything: a real node can
    legitimately extract to few fields. What decides the rung is `node.id`,
    because an id is a value only the far end can have supplied.
    """
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.CALLER if target else ClaimBy.NONE,
        effects=[{
            'kind': 'figma_node_read',
            'target_kind': target_kind,
            'target': target,
            'node_id': node.id,
            'node_type': node.type,
            'style_fields': len(node.style.to_dict()),
            'measured_by': 'a non-empty node id parsed out of the Figma reply',
            'detail': (
                'Figma returned a node for this request. Nothing was read back '
                'and no design was compared against anything, so this is the '
                'whole distance travelled.'
            ),
        }],
    )


def _figma_node_missing(*, target_kind: str, target: Optional[str], detail: str) -> Dict[str, Any]:
    """FAILED -- the reply arrived and did not contain what the caller named."""
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.CALLER,
        effects=[{
            'kind': 'figma_node_missing',
            'target_kind': target_kind,
            'target': target,
            'measured_by': 'the requested node was absent from the parsed reply',
            'detail': detail,
        }],
    )


@register_module(
    module_id='verify.figma',
    version='1.0.0',
    category='verify',
    tags=['verify', 'figma', 'design', 'api'],
    label='Fetch Figma Style',
    label_key='modules.verify.figma.label',
    description='Fetch design tokens from Figma API (token stays local)',
    description_key='modules.verify.figma.description',
    icon='Figma',
    color='#F24E1E',

    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['verify.compare', 'verify.*', 'data.*'],

    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['figma.read'],

    params_schema=compose(
        schema_field('file_id', type='string', required=True, description='Figma file key (from URL)',
                     placeholder='unique-id'),
        schema_field('node_id', type='string', required=False, description='Specific node ID to fetch',
                     placeholder='unique-id'),
        schema_field('node_name', type='string', required=False, description='Find node by name',
                     placeholder='my-name'),
        schema_field('token', type='string', required=False, description='Figma token (or use FIGMA_TOKEN env var)',
                     placeholder='your-token'),
    ),
    output_schema={
        'node': {'type': 'object', 'description': 'Figma node data'},
        'style': {'type': 'object', 'description': 'Extracted style'},
        'outcome': {'type': 'object', 'description': (
            'How far the fetch was followed: "accepted" when Figma returned a node, '
            '"failed" when its reply carried nothing for the node or file the caller '
            'named -- including the ok=true case where node and style come back '
            'empty. Never higher: one GET, and its own reply is all that was read'
        )},
    },
)
class VerifyFigmaModule(BaseModule):
    """Fetch design tokens from Figma API."""

    module_name = "Fetch Figma Style"
    module_description = "Get design tokens from Figma (local execution)"

    def validate_params(self) -> None:
        self.file_id = self.params.get('file_id')
        self.node_id = self.params.get('node_id')
        self.node_name = self.params.get('node_name')
        self.token = self.params.get('token') or os.environ.get('FIGMA_TOKEN')

        if not self.file_id:
            raise ValueError("file_id is required")
        if not self.token:
            raise ValueError("Figma token required. Set FIGMA_TOKEN env var or pass token parameter.")

    async def execute(self) -> Dict[str, Any]:
        import httpx
        from ....utils import guarded_httpx_client

        headers = {'X-Figma-Token': self.token}

        # What the caller named, carried through to the envelope. `node_id` wins
        # because the branch below ignores `node_name` when both are given.
        if self.node_id:
            target_kind, target = 'node_id', self.node_id
        elif self.node_name:
            target_kind, target = 'node_name', self.node_name
        else:
            target_kind, target = 'file', None

        async with guarded_httpx_client() as client:
            if self.node_id:
                # Fetch specific node
                response = await client.get(
                    f"{FIGMA_API_BASE}/files/{self.file_id}/nodes",
                    params={'ids': self.node_id},
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                nodes = data.get('nodes', {})
                node_data = nodes.get(self.node_id, {}).get('document', {})
                node = parse_node(node_data)

            else:
                # Fetch entire file
                response = await client.get(
                    f"{FIGMA_API_BASE}/files/{self.file_id}",
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                node = parse_node(data.get('document', {}))

                # Find by name if specified
                if self.node_name:
                    found = node.find_by_name(self.node_name)
                    if found:
                        node = found
                    else:
                        return {
                            'ok': False,
                            'error': f"Node not found: {self.node_name}",
                            # No 'data' dict on this return, so the envelope goes
                            # where `_apply_outcome_contract` looks when there is
                            # none -- the top level. `wrap_legacy_result` turns an
                            # ok=False into an ERROR and discards it, and it is
                            # attached anyway for the reason `atomic/dns/lookup.py`
                            # gives: the fact is true whether or not a consumer
                            # exists yet, and waiting for one means building the
                            # consumer against results that carry nothing.
                            'outcome': _figma_node_missing(
                                target_kind='node_name',
                                target=self.node_name,
                                detail=(
                                    'The file was fetched and parsed, and no node in it '
                                    'is named as the caller asked.'
                                ),
                            ),
                        }

        # Store in context for chaining
        self.context['figma_style'] = node.style
        self.context['figma_node'] = node

        if not node.id:
            # ok stays True. A missing node is not a transport failure and this
            # module is not the place to decide a workflow should stop -- the
            # engine reads the rung, marks the step PARTIAL and keeps going
            # (`executor.py::_record_unconfirmed_outcome`). What changes is that
            # `{'style': {}}` no longer reaches a consumer indistinguishable
            # from a component that genuinely has no style overrides.
            missing_detail = (
                f'Figma answered, and its reply carried no node under {self.node_id!r}. '
                'Either no such node exists in this file, or the id it came back '
                'under is not the id it was asked for; this module cannot tell '
                'which, and returns an empty node either way.'
            ) if self.node_id else (
                'Figma answered, and its reply carried no document for this file.'
            )
            return {
                'ok': True,
                'data': {
                    'node': node.to_dict(),
                    'style': node.style.to_dict(),
                    'outcome': _figma_node_missing(
                        target_kind=target_kind,
                        target=target or self.file_id,
                        detail=missing_detail,
                    ),
                },
            }

        return {
            'ok': True,
            'data': {
                'node': node.to_dict(),
                'style': node.style.to_dict(),
                'outcome': _figma_node_read(
                    target_kind=target_kind, target=target, node=node,
                ),
            }
        }
