"""
Image Processing Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def IMAGE_INPUT_PATH(
    *,
    key: str = "input_path",
    required: bool = True,
    label: str = "Input Path",
    label_key: str = "schema.field.image_input_path",
    placeholder: str = "/path/to/image.png",
) -> Dict[str, Dict[str, Any]]:
    """Input image file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Path to the input image file',
        format="path",
        group=FieldGroup.BASIC,
    )


def IMAGE_OUTPUT_PATH(
    *,
    key: str = "output_path",
    required: bool = False,
    label: str = "Output Path",
    label_key: str = "schema.field.image_output_path",
    placeholder: str = "/path/to/output.png",
) -> Dict[str, Dict[str, Any]]:
    """Output image file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Path where the processed image will be saved',
        format="path",
        group=FieldGroup.BASIC,
    )


def IMAGE_WIDTH(
    *,
    key: str = "width",
    required: bool = False,
    label: str = "Width",
    label_key: str = "schema.field.image_width",
    min_val: int = 1,
    max_val: int = 10000,
) -> Dict[str, Dict[str, Any]]:
    """Image width in pixels."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=min_val,
        max=max_val,
        description='Target width in pixels',
        group=FieldGroup.OPTIONS,
    )


def IMAGE_HEIGHT(
    *,
    key: str = "height",
    required: bool = False,
    label: str = "Height",
    label_key: str = "schema.field.image_height",
    min_val: int = 1,
    max_val: int = 10000,
) -> Dict[str, Dict[str, Any]]:
    """Image height in pixels."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=min_val,
        max=max_val,
        description='Target height in pixels',
        group=FieldGroup.OPTIONS,
    )


def IMAGE_SCALE(
    *,
    key: str = "scale",
    required: bool = False,
    label: str = "Scale Factor",
    label_key: str = "schema.field.image_scale",
    min_val: float = 0.01,
    max_val: float = 10.0,
) -> Dict[str, Dict[str, Any]]:
    """Image scale factor."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=min_val,
        max=max_val,
        step=0.1,
        description='Scale factor (e.g., 0.5 for half, 2.0 for double)',
        group=FieldGroup.OPTIONS,
    )


def IMAGE_QUALITY(
    *,
    key: str = "quality",
    default: int = 85,
    min_val: int = 1,
    max_val: int = 100,
    label: str = "Quality",
    label_key: str = "schema.field.image_quality",
) -> Dict[str, Dict[str, Any]]:
    """Image quality (1-100)."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Quality level (1-100, higher is better)',
        group=FieldGroup.OPTIONS,
    )


def IMAGE_FORMAT(
    *,
    key: str = "format",
    required: bool = False,
    default: str = "png",
    label: str = "Output Format",
    label_key: str = "schema.field.image_format",
) -> Dict[str, Dict[str, Any]]:
    """Image output format."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        default=default,
        options=[
            {"value": "png", "label": "PNG (lossless, transparent)"},
            {"value": "jpeg", "label": "JPEG (lossy, small size)"},
            {"value": "webp", "label": "WebP (modern, best compression)"},
            {"value": "gif", "label": "GIF (animation, 256 colors)"},
            {"value": "bmp", "label": "BMP (uncompressed)"},
            {"value": "tiff", "label": "TIFF (print quality)"},
        ],
        description='Output image format',
        group=FieldGroup.OPTIONS,
    )


def IMAGE_RESIZE_ALGORITHM(
    *,
    key: str = "algorithm",
    default: str = "lanczos",
    label: str = "Algorithm",
    label_key: str = "schema.field.image_resize_algorithm",
) -> Dict[str, Dict[str, Any]]:
    """Image resize algorithm."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {"value": "lanczos", "label": "Lanczos (best quality, slower)"},
            {"value": "bicubic", "label": "Bicubic (high quality)"},
            {"value": "bilinear", "label": "Bilinear (good balance)"},
            {"value": "nearest", "label": "Nearest (fastest, pixelated)"},
        ],
        description='Resampling algorithm for resize',
        group=FieldGroup.OPTIONS,
    )


def IMAGE_MAINTAIN_ASPECT(
    *,
    key: str = "maintain_aspect",
    default: bool = True,
    label: str = "Maintain Aspect Ratio",
    label_key: str = "schema.field.image_maintain_aspect",
) -> Dict[str, Dict[str, Any]]:
    """Maintain aspect ratio when resizing."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Maintain original aspect ratio',
        group=FieldGroup.OPTIONS,
    )


def IMAGE_OPTIMIZE(
    *,
    key: str = "optimize",
    default: bool = True,
    label: str = "Optimize",
    label_key: str = "schema.field.image_optimize",
) -> Dict[str, Dict[str, Any]]:
    """Apply additional image optimization."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Apply additional optimization',
        group=FieldGroup.OPTIONS,
    )


def IMAGE_MAX_SIZE_KB(
    *,
    key: str = "max_size_kb",
    required: bool = False,
    label: str = "Max Size (KB)",
    label_key: str = "schema.field.image_max_size_kb",
) -> Dict[str, Dict[str, Any]]:
    """Target maximum file size in KB."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=1,
        description='Target maximum file size in KB',
        group=FieldGroup.OPTIONS,
    )


def IMAGE_RESIZE_OPTIONS(
    *,
    key: str = "resize",
    required: bool = False,
    label: str = "Resize",
    label_key: str = "schema.field.image_resize_options",
) -> Dict[str, Dict[str, Any]]:
    """Resize options object."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        description='Resize options: {width, height, keep_aspect}',
        group=FieldGroup.OPTIONS,
    )


def IMAGE_URL(
    *,
    key: str = "url",
    required: bool = True,
    label: str = "Image URL",
    label_key: str = "schema.field.image_url",
    placeholder: str = "https://example.com/image.jpg",
) -> Dict[str, Dict[str, Any]]:
    """Image URL to download."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='URL of the image to download',
        validation=validators.URL_HTTP,
        group=FieldGroup.BASIC,
    )


def OUTPUT_DIRECTORY(
    *,
    key: str = "output_dir",
    required: bool = False,
    default: str = "/tmp",
    label: str = "Output Directory",
    label_key: str = "schema.field.output_directory",
) -> Dict[str, Dict[str, Any]]:
    """Output directory path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        default=default,
        description='Directory where output files will be saved',
        format="path",
        group=FieldGroup.BASIC,
    
        placeholder='/path/to/output',
)


# QR Code Presets
def QRCODE_DATA(
    *,
    key: str = "data",
    required: bool = True,
    label: str = "Data",
    label_key: str = "schema.field.qrcode_data",
    placeholder: str = "https://example.com",
) -> Dict[str, Dict[str, Any]]:
    """Data to encode in QR code."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Text, URL, or data to encode',
        group=FieldGroup.BASIC,
    )


def QRCODE_SIZE(
    *,
    key: str = "size",
    default: int = 300,
    min_val: int = 100,
    max_val: int = 2000,
    label: str = "Size",
    label_key: str = "schema.field.qrcode_size",
) -> Dict[str, Dict[str, Any]]:
    """QR code size in pixels."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Size in pixels',
        group=FieldGroup.OPTIONS,
    )


def QRCODE_COLOR(
    *,
    key: str = "color",
    default: str = "#000000",
    label: str = "Foreground Color",
    label_key: str = "schema.field.qrcode_color",
) -> Dict[str, Dict[str, Any]]:
    """QR code foreground color."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Color of the QR code (hex or name)',
        group=FieldGroup.OPTIONS,
    
        placeholder='#000000',
)


def QRCODE_BACKGROUND(
    *,
    key: str = "background",
    default: str = "#FFFFFF",
    label: str = "Background Color",
    label_key: str = "schema.field.qrcode_background",
) -> Dict[str, Dict[str, Any]]:
    """QR code background color."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Background color (hex or name)',
        group=FieldGroup.OPTIONS,
    
        placeholder='#FFFFFF',
)


def QRCODE_ERROR_CORRECTION(
    *,
    key: str = "error_correction",
    default: str = "M",
    label: str = "Error Correction",
    label_key: str = "schema.field.qrcode_error_correction",
) -> Dict[str, Dict[str, Any]]:
    """QR code error correction level."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {'value': 'L', 'label': 'Low (7%)'},
            {'value': 'M', 'label': 'Medium (15%)'},
            {'value': 'Q', 'label': 'Quartile (25%)'},
            {'value': 'H', 'label': 'High (30%)'},
        ],
        description='Error correction level',
        group=FieldGroup.OPTIONS,
    )


def QRCODE_LOGO_PATH(
    *,
    key: str = "logo_path",
    required: bool = False,
    label: str = "Logo Path",
    label_key: str = "schema.field.qrcode_logo_path",
) -> Dict[str, Dict[str, Any]]:
    """Path to logo image to embed in QR code."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        format="path",
        description='Path to logo image to embed in center',
        group=FieldGroup.OPTIONS,
    
        placeholder='/path/to/logo.png',
)
