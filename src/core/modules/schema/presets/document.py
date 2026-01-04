"""
Document Common Presets / Excel Presets / PDF Presets / Word Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def DOC_INPUT_PATH(
    *,
    key: str = "input_path",
    required: bool = True,
    label: str = "Input Path",
    label_key: str = "schema.field.doc_input_path",
    placeholder: str = "/path/to/document",
) -> Dict[str, Dict[str, Any]]:
    """Input document file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='Path to the input document',
        group=FieldGroup.BASIC,
    )


def DOC_OUTPUT_PATH(
    *,
    key: str = "output_path",
    required: bool = False,
    label: str = "Output Path",
    label_key: str = "schema.field.doc_output_path",
    placeholder: str = "/path/to/output",
) -> Dict[str, Dict[str, Any]]:
    """Output document file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='Path for the output document',
        group=FieldGroup.BASIC,
    )


def DOC_PAGES(
    *,
    key: str = "pages",
    default: str = "all",
    label: str = "Pages",
    label_key: str = "schema.field.doc_pages",
) -> Dict[str, Dict[str, Any]]:
    """Page range to process."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Page range (e.g., "1-5", "1,3,5", or "all")',
        group=FieldGroup.OPTIONS,
    )


def DOC_EXTRACT_TABLES(
    *,
    key: str = "extract_tables",
    default: bool = False,
    label: str = "Extract Tables",
    label_key: str = "schema.field.doc_extract_tables",
) -> Dict[str, Dict[str, Any]]:
    """Extract tables from document."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Extract tables as structured data',
        group=FieldGroup.OPTIONS,
    )


def DOC_EXTRACT_IMAGES(
    *,
    key: str = "extract_images",
    default: bool = False,
    label: str = "Extract Images",
    label_key: str = "schema.field.doc_extract_images",
) -> Dict[str, Dict[str, Any]]:
    """Extract embedded images."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Extract embedded images',
        group=FieldGroup.OPTIONS,
    )


def DOC_PRESERVE_FORMATTING(
    *,
    key: str = "preserve_formatting",
    default: bool = True,
    label: str = "Preserve Formatting",
    label_key: str = "schema.field.doc_preserve_formatting",
) -> Dict[str, Dict[str, Any]]:
    """Preserve document formatting."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Preserve basic formatting',
        group=FieldGroup.OPTIONS,
    )


def DOC_IMAGES_OUTPUT_DIR(
    *,
    key: str = "images_output_dir",
    label: str = "Images Output Directory",
    label_key: str = "schema.field.doc_images_output_dir",
) -> Dict[str, Dict[str, Any]]:
    """Directory to save extracted images."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Directory to save extracted images',
        group=FieldGroup.OPTIONS,
    )

def EXCEL_PATH(
    *,
    key: str = "path",
    required: bool = True,
    label: str = "Excel Path",
    label_key: str = "schema.field.excel_path",
    placeholder: str = "/path/to/file.xlsx",
) -> Dict[str, Dict[str, Any]]:
    """Excel file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='Path to the Excel file',
        group=FieldGroup.BASIC,
    )


def EXCEL_SHEET(
    *,
    key: str = "sheet",
    label: str = "Sheet Name",
    label_key: str = "schema.field.excel_sheet",
) -> Dict[str, Dict[str, Any]]:
    """Excel sheet name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Sheet name (default: first sheet)',
        group=FieldGroup.OPTIONS,
    )


def EXCEL_HEADER_ROW(
    *,
    key: str = "header_row",
    default: int = 1,
    label: str = "Header Row",
    label_key: str = "schema.field.excel_header_row",
) -> Dict[str, Dict[str, Any]]:
    """Header row number (1-based)."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Row number for headers (1-based, 0 for no headers)',
        group=FieldGroup.OPTIONS,
    )


def EXCEL_RANGE(
    *,
    key: str = "range",
    label: str = "Cell Range",
    label_key: str = "schema.field.excel_range",
) -> Dict[str, Dict[str, Any]]:
    """Excel cell range."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Cell range to read (e.g., "A1:D10")',
        group=FieldGroup.OPTIONS,
    )


def EXCEL_AS_DICT(
    *,
    key: str = "as_dict",
    default: bool = True,
    label: str = "Return as Dict",
    label_key: str = "schema.field.excel_as_dict",
) -> Dict[str, Dict[str, Any]]:
    """Return rows as dictionaries."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Return rows as dictionaries (using headers as keys)',
        group=FieldGroup.OPTIONS,
    )


def EXCEL_DATA(
    *,
    key: str = "data",
    required: bool = True,
    label: str = "Data",
    label_key: str = "schema.field.excel_data",
) -> Dict[str, Dict[str, Any]]:
    """Data array for Excel."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Data to write (array of arrays or array of objects)',
        group=FieldGroup.BASIC,
    )


def EXCEL_HEADERS(
    *,
    key: str = "headers",
    label: str = "Headers",
    label_key: str = "schema.field.excel_headers",
) -> Dict[str, Dict[str, Any]]:
    """Column headers."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        description='Column headers (auto-detected from objects if not provided)',
        group=FieldGroup.OPTIONS,
    )


def EXCEL_SHEET_NAME(
    *,
    key: str = "sheet_name",
    default: str = "Sheet1",
    label: str = "Sheet Name",
    label_key: str = "schema.field.excel_sheet_name",
) -> Dict[str, Dict[str, Any]]:
    """Excel sheet name for writing."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Name of the worksheet',
        group=FieldGroup.OPTIONS,
    )


def EXCEL_AUTO_WIDTH(
    *,
    key: str = "auto_width",
    default: bool = True,
    label: str = "Auto Width",
    label_key: str = "schema.field.excel_auto_width",
) -> Dict[str, Dict[str, Any]]:
    """Auto-adjust column widths."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Automatically adjust column widths',
        group=FieldGroup.OPTIONS,
    )

def PDF_PATH(
    *,
    key: str = "path",
    required: bool = True,
    label: str = "PDF Path",
    label_key: str = "schema.field.pdf_path",
    placeholder: str = "/path/to/document.pdf",
) -> Dict[str, Dict[str, Any]]:
    """PDF file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='Path to the PDF file',
        group=FieldGroup.BASIC,
    )


def PDF_CONTENT(
    *,
    key: str = "content",
    required: bool = True,
    label: str = "Content",
    label_key: str = "schema.field.pdf_content",
) -> Dict[str, Dict[str, Any]]:
    """HTML or text content for PDF."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='HTML or text content to convert to PDF',
        group=FieldGroup.BASIC,
    )


def PDF_TITLE(
    *,
    key: str = "title",
    label: str = "Title",
    label_key: str = "schema.field.pdf_title",
) -> Dict[str, Dict[str, Any]]:
    """Document title metadata."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Document title (metadata)',
        group=FieldGroup.OPTIONS,
    )


def PDF_AUTHOR(
    *,
    key: str = "author",
    label: str = "Author",
    label_key: str = "schema.field.pdf_author",
) -> Dict[str, Dict[str, Any]]:
    """Document author metadata."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Document author (metadata)',
        group=FieldGroup.OPTIONS,
    )


def PDF_PAGE_SIZE(
    *,
    key: str = "page_size",
    default: str = "A4",
    label: str = "Page Size",
    label_key: str = "schema.field.pdf_page_size",
) -> Dict[str, Dict[str, Any]]:
    """Page size format."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["A4", "Letter", "Legal", "A3", "A5"],
        description='Page size format',
        group=FieldGroup.OPTIONS,
    )


def PDF_ORIENTATION(
    *,
    key: str = "orientation",
    default: str = "portrait",
    label: str = "Orientation",
    label_key: str = "schema.field.pdf_orientation",
) -> Dict[str, Dict[str, Any]]:
    """Page orientation."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["portrait", "landscape"],
        description='Page orientation',
        group=FieldGroup.OPTIONS,
    )


def PDF_MARGIN(
    *,
    key: str = "margin",
    default: int = 20,
    label: str = "Margin (mm)",
    label_key: str = "schema.field.pdf_margin",
) -> Dict[str, Dict[str, Any]]:
    """Page margin in millimeters."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Page margin in millimeters',
        group=FieldGroup.OPTIONS,
    )


def PDF_HEADER(
    *,
    key: str = "header",
    label: str = "Header",
    label_key: str = "schema.field.pdf_header",
) -> Dict[str, Dict[str, Any]]:
    """Header text for each page."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Header text for each page',
        group=FieldGroup.OPTIONS,
    )


def PDF_FOOTER(
    *,
    key: str = "footer",
    label: str = "Footer",
    label_key: str = "schema.field.pdf_footer",
) -> Dict[str, Dict[str, Any]]:
    """Footer text for each page."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Footer text for each page',
        group=FieldGroup.OPTIONS,
    )


def PDF_TEMPLATE(
    *,
    key: str = "template",
    required: bool = True,
    label: str = "Template PDF",
    label_key: str = "schema.field.pdf_template",
) -> Dict[str, Dict[str, Any]]:
    """PDF template file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Path to the PDF template file',
        group=FieldGroup.OPTIONS,
    )


def PDF_FORM_FIELDS(
    *,
    key: str = "fields",
    label: str = "Form Fields",
    label_key: str = "schema.field.pdf_form_fields",
) -> Dict[str, Dict[str, Any]]:
    """Form field key-value pairs."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        default={},
        description='Key-value pairs of form field names and values',
        group=FieldGroup.OPTIONS,
    )


def PDF_IMAGES(
    *,
    key: str = "images",
    label: str = "Images",
    label_key: str = "schema.field.pdf_images",
) -> Dict[str, Dict[str, Any]]:
    """Images to insert into PDF."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        default=[],
        description='List of images to insert with position info',
        group=FieldGroup.OPTIONS,
    )


def PDF_FLATTEN(
    *,
    key: str = "flatten",
    default: bool = True,
    label: str = "Flatten Form",
    label_key: str = "schema.field.pdf_flatten",
) -> Dict[str, Dict[str, Any]]:
    """Flatten form fields."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Flatten form fields (make them non-editable)',
        group=FieldGroup.OPTIONS,
    )

def WORD_FILE_PATH(
    *,
    key: str = "file_path",
    required: bool = True,
    label: str = "File Path",
    label_key: str = "schema.field.word_file_path",
) -> Dict[str, Dict[str, Any]]:
    """Word document file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Path to the Word document (.docx)',
        group=FieldGroup.BASIC,
    )


def DOC_CONVERSION_METHOD(
    *,
    key: str = "method",
    default: str = "auto",
    label: str = "Conversion Method",
    label_key: str = "schema.field.doc_conversion_method",
) -> Dict[str, Dict[str, Any]]:
    """Document conversion method."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        options=[
            {"value": "auto", "label": "Auto (best available)"},
            {"value": "libreoffice", "label": "LibreOffice"},
            {"value": "docx2pdf", "label": "docx2pdf (Windows/Mac)"},
        ],
        description='Method to use for conversion',
        group=FieldGroup.OPTIONS,
    )
