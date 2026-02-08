"""
Verify Annotate Module - Draw labeled bounding boxes on screenshots

Draws annotation markers (A, B, C...) with colored bounding boxes,
coordinate labels, and descriptions on screenshot images.
Used by verify.visual_diff to visualize differences.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field as schema_field

logger = logging.getLogger(__name__)

# Default color palette for annotation labels
LABEL_COLORS = [
    (255, 68, 68),    # Red
    (255, 165, 0),    # Orange
    (68, 68, 255),    # Blue
    (0, 180, 0),      # Green
    (180, 0, 180),    # Purple
    (0, 180, 180),    # Cyan
    (255, 215, 0),    # Gold
    (255, 105, 180),  # Pink
]


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color string to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))


def draw_annotations(image_path: str, annotations: List[Dict], output_path: str) -> Dict[str, Any]:
    """
    Draw bounding boxes and labels on an image.

    Each annotation: {label, x, y, width, height, color?, description?}
    Returns: {output_path, annotation_count}
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ImportError("Pillow is required for verify.annotate. Install with: pip install Pillow")

    img = Image.open(image_path).convert('RGBA')
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Try to load a reasonable font
    font = _get_font(16)
    font_small = _get_font(12)

    for i, ann in enumerate(annotations):
        label = ann.get('label', chr(65 + i))  # A, B, C...
        x = int(ann.get('x', 0))
        y = int(ann.get('y', 0))
        w = int(ann.get('width', 50))
        h = int(ann.get('height', 50))
        description = ann.get('description', '')

        # Color from annotation or palette
        if ann.get('color'):
            color_rgb = hex_to_rgb(ann['color']) if isinstance(ann['color'], str) else tuple(ann['color'][:3])
        else:
            color_rgb = LABEL_COLORS[i % len(LABEL_COLORS)]

        # Draw semi-transparent filled rectangle
        fill_color = color_rgb + (40,)
        draw.rectangle([x, y, x + w, y + h], fill=fill_color, outline=color_rgb + (220,), width=2)

        # Draw label badge (top-left corner)
        badge_w, badge_h = 24, 22
        badge_x, badge_y = x - 1, y - badge_h
        if badge_y < 0:
            badge_y = y  # Put inside if no room above
        draw.rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], fill=color_rgb + (230,))
        draw.text((badge_x + 6, badge_y + 2), label, fill=(255, 255, 255, 255), font=font)

        # Draw coordinate text (bottom-right)
        coord_text = f"({x},{y}) {w}x{h}"
        draw.text((x + 2, y + h + 2), coord_text, fill=color_rgb + (200,), font=font_small)

        # Draw description below coordinates if provided
        if description:
            desc_y = y + h + 16
            draw.text((x + 2, desc_y), description[:60], fill=color_rgb + (200,), font=font_small)

    # Composite overlay onto original
    result = Image.alpha_composite(img, overlay).convert('RGB')

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.save(str(out), quality=95)

    return {
        'output_path': str(out),
        'annotation_count': len(annotations),
    }


def _get_font(size: int):
    """Try to load a font, fall back to default."""
    try:
        from PIL import ImageFont
    except ImportError:
        return None

    # Try common system fonts
    font_paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        '/System/Library/Fonts/SFNSText.ttf',
        'C:/Windows/Fonts/arial.ttf',
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue

    try:
        return ImageFont.load_default()
    except Exception:
        return None


@register_module(
    module_id='verify.annotate',
    version='1.0.0',
    category='verify',
    tags=['verify', 'annotate', 'screenshot', 'visual', 'diff', 'bounding-box'],
    label='Annotate Screenshot',
    label_key='modules.verify.annotate.label',
    description='Draw labeled bounding boxes on screenshots to mark differences',
    description_key='modules.verify.annotate.description',
    icon='PenTool',
    color='#8B5CF6',

    input_types=['object'],
    output_types=['image', 'file'],

    can_receive_from=['verify.*', 'vision.*', 'browser.*'],
    can_connect_to=['verify.*', 'file.*', 'notification.*'],

    timeout_ms=15000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.write'],

    params_schema=compose(
        schema_field('image_path', type='string', required=True, description='Path to the screenshot image'),
        schema_field('annotations', type='array', required=True, description='Array of annotations: [{label, x, y, width, height, color?, description?}]'),
        schema_field('output_path', type='string', required=False, description='Output path for annotated image (default: adds _annotated suffix)'),
    ),
    output_schema={
        'output_path': {'type': 'string', 'description': 'Path to annotated image'},
        'annotation_count': {'type': 'integer', 'description': 'Number of annotations drawn'},
    },
)
class VerifyAnnotateModule(BaseModule):
    """Draw labeled bounding boxes on screenshots."""

    module_name = "Annotate Screenshot"
    module_description = "Mark difference regions on screenshots with labels"

    def validate_params(self) -> None:
        self.image_path = self.params.get('image_path')
        self.annotations = self.params.get('annotations', [])
        self.output_path = self.params.get('output_path')

        if not self.image_path:
            raise ValueError("image_path is required")
        if not self.annotations:
            raise ValueError("annotations array is required and must not be empty")

        # Default output path
        if not self.output_path:
            p = Path(self.image_path)
            self.output_path = str(p.parent / f"{p.stem}_annotated{p.suffix}")

    async def execute(self) -> Dict[str, Any]:
        if not Path(self.image_path).exists():
            return {'ok': False, 'error': f'Image not found: {self.image_path}'}

        result = draw_annotations(self.image_path, self.annotations, self.output_path)

        return {
            'ok': True,
            'data': result,
        }
