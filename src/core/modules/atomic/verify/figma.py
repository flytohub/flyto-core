"""
Verify Figma Module - Fetch design tokens from Figma API

Runs locally with user's own Figma token.
Token never leaves the user's machine.
"""
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

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

        headers = {'X-Figma-Token': self.token}

        async with httpx.AsyncClient() as client:
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
                            'error': f"Node not found: {self.node_name}"
                        }

        # Store in context for chaining
        self.context['figma_style'] = node.style
        self.context['figma_node'] = node

        return {
            'ok': True,
            'data': {
                'node': node.to_dict(),
                'style': node.style.to_dict(),
            }
        }
