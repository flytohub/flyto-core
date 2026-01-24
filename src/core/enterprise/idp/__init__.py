"""
IDP - Intelligent Document Processing

AI-powered document processing pipeline:
- Document classification
- Field extraction (AI + rules)
- Table detection and extraction
- Human-in-the-loop validation
- Multi-format support (PDF, images, scanned docs)

Reference: ITEM_PIPELINE_SPEC.md Section 14
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class DocumentType(Enum):
    """Supported document types."""
    # Financial documents
    INVOICE = "invoice"
    RECEIPT = "receipt"
    PURCHASE_ORDER = "purchase_order"
    BANK_STATEMENT = "bank_statement"

    # Identity documents
    ID_CARD = "id_card"
    PASSPORT = "passport"
    DRIVERS_LICENSE = "drivers_license"

    # Contract documents
    CONTRACT = "contract"
    NDA = "nda"
    AGREEMENT = "agreement"

    # Forms
    FORM = "form"
    APPLICATION = "application"
    SURVEY = "survey"

    # Other
    EMAIL = "email"
    LETTER = "letter"
    REPORT = "report"
    CUSTOM = "custom"


class FieldType(Enum):
    """Extraction field types."""
    STRING = "string"
    NUMBER = "number"
    DATE = "date"
    CURRENCY = "currency"
    ADDRESS = "address"
    PHONE = "phone"
    EMAIL = "email"
    CHECKBOX = "checkbox"
    SIGNATURE = "signature"


class ExtractionConfidence(Enum):
    """Confidence levels for extraction."""
    HIGH = "high"      # > 0.9
    MEDIUM = "medium"  # 0.7 - 0.9
    LOW = "low"        # < 0.7


@dataclass
class ExtractionField:
    """Field definition for document extraction."""
    name: str
    label: str
    field_type: FieldType = FieldType.STRING
    required: bool = False

    # Field aliases (for AI to recognize)
    aliases: List[str] = field(default_factory=list)

    # Extraction hints for AI
    extraction_hints: List[str] = field(default_factory=list)

    # Validation rules
    validation: Optional[Dict[str, Any]] = None

    # Region hint (optional, for faster extraction)
    region_hint: Optional[str] = None  # "top", "bottom", "left", "right"


@dataclass
class TableColumn:
    """Table column definition."""
    name: str
    label: str
    field_type: FieldType = FieldType.STRING
    required: bool = False


@dataclass
class TableSchema:
    """Table extraction schema."""
    name: str
    columns: List[TableColumn] = field(default_factory=list)
    required: bool = False
    min_rows: int = 0
    max_rows: Optional[int] = None


@dataclass
class ValidationRule:
    """Validation rule for extracted data."""
    rule: str  # Expression like "total == sum(line_items.amount)"
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class ExtractionSchema:
    """Complete extraction schema for a document type."""
    document_type: DocumentType
    name: str
    version: str = "1.0"

    # Field definitions
    fields: List[ExtractionField] = field(default_factory=list)

    # Table definitions
    tables: List[TableSchema] = field(default_factory=list)

    # Cross-field validation rules
    validation_rules: List[ValidationRule] = field(default_factory=list)

    # Preprocessing options
    deskew: bool = True
    denoise: bool = True
    enhance_contrast: bool = False


@dataclass
class ExtractedField:
    """Single extracted field result."""
    name: str
    value: Any
    confidence: float
    confidence_level: ExtractionConfidence

    # Location in document
    bounding_box: Optional[Tuple[int, int, int, int]] = None  # x, y, w, h
    page_number: int = 1

    # Source text (for debugging)
    source_text: Optional[str] = None

    # Validation status
    valid: bool = True
    validation_errors: List[str] = field(default_factory=list)


@dataclass
class ExtractedTable:
    """Extracted table result."""
    name: str
    rows: List[Dict[str, Any]]
    confidence: float

    # Table location
    bounding_box: Optional[Tuple[int, int, int, int]] = None
    page_number: int = 1

    # Per-cell confidence
    cell_confidences: Optional[List[Dict[str, float]]] = None


@dataclass
class ExtractionResult:
    """Complete extraction result for a document."""
    document_id: str
    document_type: DocumentType
    schema_version: str

    # Classification confidence
    classification_confidence: float

    # Extracted data
    fields: Dict[str, ExtractedField] = field(default_factory=dict)
    tables: Dict[str, ExtractedTable] = field(default_factory=dict)

    # Overall metrics
    overall_confidence: float = 0.0
    fields_requiring_review: List[str] = field(default_factory=list)

    # Processing info
    processed_at: Optional[datetime] = None
    processing_time_ms: int = 0
    page_count: int = 1

    # Raw data (for debugging)
    raw_ocr_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "document_id": self.document_id,
            "document_type": self.document_type.value,
            "classification_confidence": self.classification_confidence,
            "fields": {
                k: {
                    "value": v.value,
                    "confidence": v.confidence,
                    "valid": v.valid,
                }
                for k, v in self.fields.items()
            },
            "tables": {
                k: {
                    "rows": v.rows,
                    "confidence": v.confidence,
                }
                for k, v in self.tables.items()
            },
            "overall_confidence": self.overall_confidence,
            "fields_requiring_review": self.fields_requiring_review,
        }


class TaskStatus(Enum):
    """Validation task status."""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


@dataclass
class ValidationTask:
    """Human-in-the-loop validation task."""
    task_id: str
    document_id: str
    extraction_result: ExtractionResult

    # Fields to review
    fields_to_review: List[str] = field(default_factory=list)

    # Confidence scores
    confidence_scores: Dict[str, float] = field(default_factory=dict)

    # Status
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5  # 1-10, 10 = highest

    # Assignment
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None

    # Review info
    reviewed_at: Optional[datetime] = None
    reviewer: Optional[str] = None
    reviewer_corrections: Optional[Dict[str, Any]] = None
    review_notes: Optional[str] = None

    # SLA
    deadline: Optional[datetime] = None


class DocumentProcessor:
    """
    Document processing interface.

    This is the abstract interface - actual implementation
    should be provided by the runtime environment.
    """

    async def classify(
        self,
        document: bytes,
        filename: str = None,
        hint_type: DocumentType = None,
    ) -> Tuple[DocumentType, float]:
        """
        Classify document type.

        Args:
            document: Document content (PDF, image, etc.)
            filename: Optional filename for hint
            hint_type: Optional expected type

        Returns:
            Tuple of (DocumentType, confidence)
        """
        raise NotImplementedError("Implementation required")

    async def extract(
        self,
        document: bytes,
        schema: ExtractionSchema,
        filename: str = None,
    ) -> ExtractionResult:
        """
        Extract fields from document.

        Args:
            document: Document content
            schema: Extraction schema
            filename: Optional filename

        Returns:
            ExtractionResult with extracted fields
        """
        raise NotImplementedError("Implementation required")

    async def validate(
        self,
        result: ExtractionResult,
        schema: ExtractionSchema,
    ) -> ExtractionResult:
        """
        Validate extracted data against schema rules.

        Args:
            result: Extraction result to validate
            schema: Schema with validation rules

        Returns:
            Updated ExtractionResult with validation status
        """
        raise NotImplementedError("Implementation required")


class ValidationQueue:
    """
    Human validation queue interface.

    Manages human-in-the-loop validation workflow.
    """

    async def submit_for_review(
        self,
        extraction_result: ExtractionResult,
        confidence_threshold: float = 0.8,
        deadline: datetime = None,
    ) -> ValidationTask:
        """
        Submit extraction result for human review.

        Args:
            extraction_result: Result to review
            confidence_threshold: Fields below this threshold need review
            deadline: Optional deadline for review

        Returns:
            Created ValidationTask
        """
        raise NotImplementedError("Implementation required")

    async def get_pending_tasks(
        self,
        assignee: str = None,
        document_type: DocumentType = None,
        limit: int = 100,
    ) -> List[ValidationTask]:
        """
        Get pending validation tasks.

        Args:
            assignee: Filter by assignee
            document_type: Filter by document type
            limit: Maximum tasks to return

        Returns:
            List of pending tasks
        """
        raise NotImplementedError("Implementation required")

    async def assign_task(
        self,
        task_id: str,
        assignee: str,
    ) -> ValidationTask:
        """
        Assign task to reviewer.

        Args:
            task_id: Task to assign
            assignee: Reviewer ID

        Returns:
            Updated task
        """
        raise NotImplementedError("Implementation required")

    async def approve(
        self,
        task_id: str,
        corrections: Dict[str, Any] = None,
        notes: str = None,
    ) -> ValidationTask:
        """
        Approve task (optionally with corrections).

        Args:
            task_id: Task to approve
            corrections: Optional field corrections
            notes: Optional review notes

        Returns:
            Approved task
        """
        raise NotImplementedError("Implementation required")

    async def reject(
        self,
        task_id: str,
        reason: str,
    ) -> ValidationTask:
        """
        Reject task.

        Args:
            task_id: Task to reject
            reason: Rejection reason

        Returns:
            Rejected task
        """
        raise NotImplementedError("Implementation required")


# Pre-defined extraction schemas for common document types
INVOICE_SCHEMA = ExtractionSchema(
    document_type=DocumentType.INVOICE,
    name="Standard Invoice",
    fields=[
        ExtractionField(
            name="invoice_number",
            label="Invoice Number",
            field_type=FieldType.STRING,
            required=True,
            aliases=["inv no", "invoice #", "bill no", "invoice id"]
        ),
        ExtractionField(
            name="invoice_date",
            label="Invoice Date",
            field_type=FieldType.DATE,
            required=True,
            aliases=["date", "inv date", "bill date"]
        ),
        ExtractionField(
            name="due_date",
            label="Due Date",
            field_type=FieldType.DATE,
            aliases=["payment due", "due by"]
        ),
        ExtractionField(
            name="vendor_name",
            label="Vendor Name",
            field_type=FieldType.STRING,
            required=True,
            aliases=["from", "seller", "supplier", "company"]
        ),
        ExtractionField(
            name="vendor_address",
            label="Vendor Address",
            field_type=FieldType.ADDRESS,
        ),
        ExtractionField(
            name="customer_name",
            label="Customer Name",
            field_type=FieldType.STRING,
            aliases=["to", "bill to", "buyer", "client"]
        ),
        ExtractionField(
            name="subtotal",
            label="Subtotal",
            field_type=FieldType.CURRENCY,
        ),
        ExtractionField(
            name="tax_amount",
            label="Tax Amount",
            field_type=FieldType.CURRENCY,
            aliases=["tax", "vat", "gst"]
        ),
        ExtractionField(
            name="total_amount",
            label="Total Amount",
            field_type=FieldType.CURRENCY,
            required=True,
            aliases=["total", "amount due", "grand total", "total due"]
        ),
    ],
    tables=[
        TableSchema(
            name="line_items",
            columns=[
                TableColumn(name="description", label="Description"),
                TableColumn(name="quantity", label="Quantity", field_type=FieldType.NUMBER),
                TableColumn(name="unit_price", label="Unit Price", field_type=FieldType.CURRENCY),
                TableColumn(name="amount", label="Amount", field_type=FieldType.CURRENCY),
            ],
        ),
    ],
    validation_rules=[
        ValidationRule(
            rule="total_amount >= subtotal",
            message="Total should be greater than or equal to subtotal"
        ),
    ],
)


__all__ = [
    # Enums
    'DocumentType',
    'FieldType',
    'ExtractionConfidence',
    'TaskStatus',
    # Field definitions
    'ExtractionField',
    'TableColumn',
    'TableSchema',
    'ValidationRule',
    'ExtractionSchema',
    # Results
    'ExtractedField',
    'ExtractedTable',
    'ExtractionResult',
    # Validation
    'ValidationTask',
    # Interfaces
    'DocumentProcessor',
    'ValidationQueue',
    # Pre-defined schemas
    'INVOICE_SCHEMA',
]
