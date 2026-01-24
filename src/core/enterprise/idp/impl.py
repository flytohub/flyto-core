"""
IDP - Intelligent Document Processing Implementation

Document classification, field extraction, and validation.
Supports text-based extraction with optional OCR.

For usage:
    from src.core.enterprise.idp.impl import get_processor, get_validation_queue
    processor = get_processor()
"""

import io
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from . import (
    DocumentProcessor,
    DocumentType,
    ExtractionConfidence,
    ExtractionField,
    ExtractionResult,
    ExtractionSchema,
    ExtractedField,
    ExtractedTable,
    FieldType,
    TableSchema,
    TaskStatus,
    ValidationQueue,
    ValidationTask,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Text Extraction Helpers
# =============================================================================

def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF using PyPDF2 if available."""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except ImportError:
        logger.warning("PyPDF2 not installed, falling back to placeholder")
        return "[PDF text extraction requires PyPDF2]"
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""


def extract_text_from_image(content: bytes) -> str:
    """Extract text from image using Tesseract OCR if available."""
    try:
        import pytesseract
        from PIL import Image
        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image)
        return text
    except ImportError:
        logger.warning("pytesseract/PIL not installed, using placeholder")
        return "[OCR requires pytesseract and PIL]"
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return ""


def extract_text(content: bytes, filename: str = None) -> str:
    """Extract text from document based on type."""
    if filename:
        ext = filename.lower().split(".")[-1]
        if ext == "pdf":
            return extract_text_from_pdf(content)
        elif ext in ("png", "jpg", "jpeg", "tiff", "bmp"):
            return extract_text_from_image(content)
        elif ext == "txt":
            return content.decode("utf-8", errors="replace")

    # Try to detect by content
    if content[:4] == b"%PDF":
        return extract_text_from_pdf(content)

    # Try as text
    try:
        return content.decode("utf-8")
    except Exception:
        return extract_text_from_image(content)


# =============================================================================
# Field Extraction Patterns
# =============================================================================

FIELD_PATTERNS = {
    FieldType.DATE: [
        r"\d{1,2}/\d{1,2}/\d{2,4}",
        r"\d{1,2}-\d{1,2}-\d{2,4}",
        r"\d{4}-\d{2}-\d{2}",
        r"[A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4}",
    ],
    FieldType.CURRENCY: [
        r"\$[\d,]+\.?\d*",
        r"USD\s*[\d,]+\.?\d*",
        r"€[\d,]+\.?\d*",
        r"£[\d,]+\.?\d*",
        r"[\d,]+\.\d{2}",
    ],
    FieldType.EMAIL: [
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    ],
    FieldType.PHONE: [
        r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}",
        r"\(\d{3}\)\s*\d{3}[-.\s]?\d{4}",
    ],
    FieldType.NUMBER: [
        r"\d+\.?\d*",
    ],
}


def get_confidence_level(confidence: float) -> ExtractionConfidence:
    """Convert confidence score to level."""
    if confidence >= 0.9:
        return ExtractionConfidence.HIGH
    elif confidence >= 0.7:
        return ExtractionConfidence.MEDIUM
    else:
        return ExtractionConfidence.LOW


# =============================================================================
# Document Processor Implementation
# =============================================================================

class DocumentProcessorImpl(DocumentProcessor):
    """
    Document processor implementation.

    Features:
    - Text-based document classification
    - Pattern-based field extraction
    - Table detection
    - Validation
    """

    def __init__(self):
        self._schemas: Dict[DocumentType, ExtractionSchema] = {}

    def register_schema(self, schema: ExtractionSchema) -> None:
        """Register an extraction schema."""
        self._schemas[schema.document_type] = schema

    async def classify(
        self,
        document: bytes,
        filename: str = None,
        hint_type: DocumentType = None,
    ) -> Tuple[DocumentType, float]:
        """Classify document type."""
        if hint_type:
            return hint_type, 0.95

        text = extract_text(document, filename)
        text_lower = text.lower()

        # Score each document type
        scores: Dict[DocumentType, float] = {}

        # Invoice indicators
        invoice_keywords = ["invoice", "bill to", "payment due", "amount due", "total"]
        invoice_score = sum(1 for kw in invoice_keywords if kw in text_lower)
        scores[DocumentType.INVOICE] = min(invoice_score / 3, 1.0)

        # Receipt indicators
        receipt_keywords = ["receipt", "thank you", "change", "cash", "card"]
        receipt_score = sum(1 for kw in receipt_keywords if kw in text_lower)
        scores[DocumentType.RECEIPT] = min(receipt_score / 3, 1.0)

        # Contract indicators
        contract_keywords = ["agreement", "party", "whereas", "terms", "signature"]
        contract_score = sum(1 for kw in contract_keywords if kw in text_lower)
        scores[DocumentType.CONTRACT] = min(contract_score / 3, 1.0)

        # ID document indicators
        id_keywords = ["passport", "license", "id card", "identification", "date of birth"]
        id_score = sum(1 for kw in id_keywords if kw in text_lower)
        if id_score > 0:
            if "passport" in text_lower:
                scores[DocumentType.PASSPORT] = min(id_score / 2, 1.0)
            elif "license" in text_lower:
                scores[DocumentType.DRIVERS_LICENSE] = min(id_score / 2, 1.0)
            else:
                scores[DocumentType.ID_CARD] = min(id_score / 2, 1.0)

        # Find best match
        if scores:
            best_type = max(scores, key=lambda k: scores[k])
            return best_type, scores[best_type]

        return DocumentType.CUSTOM, 0.5

    async def extract(
        self,
        document: bytes,
        schema: ExtractionSchema,
        filename: str = None,
    ) -> ExtractionResult:
        """Extract fields from document."""
        start_time = datetime.utcnow()

        text = extract_text(document, filename)
        text_lower = text.lower()

        # Initialize result
        result = ExtractionResult(
            document_id=f"doc_{uuid.uuid4().hex[:12]}",
            document_type=schema.document_type,
            schema_version=schema.version,
            classification_confidence=0.9,
            raw_ocr_text=text[:2000] if text else None,
        )

        # Extract fields
        for field_def in schema.fields:
            extracted = self._extract_field(text, text_lower, field_def)
            if extracted:
                result.fields[field_def.name] = extracted
                if extracted.confidence_level == ExtractionConfidence.LOW:
                    result.fields_requiring_review.append(field_def.name)

        # Extract tables
        for table_schema in schema.tables:
            extracted_table = self._extract_table(text, text_lower, table_schema)
            if extracted_table:
                result.tables[table_schema.name] = extracted_table

        # Calculate overall confidence
        if result.fields:
            confidences = [f.confidence for f in result.fields.values()]
            result.overall_confidence = sum(confidences) / len(confidences)
        else:
            result.overall_confidence = 0.5

        result.processed_at = datetime.utcnow()
        result.processing_time_ms = int(
            (result.processed_at - start_time).total_seconds() * 1000
        )

        return result

    def _extract_field(
        self,
        text: str,
        text_lower: str,
        field_def: ExtractionField,
    ) -> Optional[ExtractedField]:
        """Extract a single field from text."""
        # Search for field label and aliases
        search_terms = [field_def.label.lower(), field_def.name.lower()]
        search_terms.extend([a.lower() for a in field_def.aliases])

        value = None
        confidence = 0.0
        source_text = None

        for term in search_terms:
            if term in text_lower:
                # Find position of label
                pos = text_lower.find(term)
                # Look for value after label (within 100 chars)
                context = text[pos:pos + 150]

                # Extract based on field type
                patterns = FIELD_PATTERNS.get(field_def.field_type, [])
                for pattern in patterns:
                    match = re.search(pattern, context, re.IGNORECASE)
                    if match:
                        value = match.group()
                        source_text = context[:80]
                        confidence = 0.85
                        break

                # Fallback: extract next word/phrase
                if not value and ":" in context:
                    after_colon = context.split(":", 1)[1].strip()
                    value = after_colon.split("\n")[0].strip()[:100]
                    confidence = 0.6

                if value:
                    break

        if not value:
            # Try direct pattern matching without label
            patterns = FIELD_PATTERNS.get(field_def.field_type, [])
            for pattern in patterns:
                matches = re.findall(pattern, text)
                if matches:
                    value = matches[0]
                    confidence = 0.5
                    break

        if value:
            return ExtractedField(
                name=field_def.name,
                value=self._parse_value(value, field_def.field_type),
                confidence=confidence,
                confidence_level=get_confidence_level(confidence),
                source_text=source_text,
            )

        return None

    def _parse_value(self, value: str, field_type: FieldType) -> Any:
        """Parse extracted value to appropriate type."""
        if field_type == FieldType.NUMBER:
            try:
                clean = re.sub(r"[^\d.]", "", value)
                return float(clean)
            except ValueError:
                return value

        elif field_type == FieldType.CURRENCY:
            try:
                clean = re.sub(r"[^\d.]", "", value)
                return float(clean)
            except ValueError:
                return value

        elif field_type == FieldType.CHECKBOX:
            return value.lower() in ("yes", "true", "checked", "x", "✓")

        return value.strip()

    def _extract_table(
        self,
        text: str,
        text_lower: str,
        table_schema: TableSchema,
    ) -> Optional[ExtractedTable]:
        """Extract table from text."""
        # Simple line-based table detection
        lines = text.split("\n")
        rows = []

        # Look for table header
        header_found = False
        for i, line in enumerate(lines):
            line_lower = line.lower()

            # Check if line contains column headers
            header_matches = sum(
                1 for col in table_schema.columns
                if col.label.lower() in line_lower or col.name.lower() in line_lower
            )

            if header_matches >= 2:
                header_found = True
                # Extract subsequent rows
                for j in range(i + 1, min(i + 50, len(lines))):
                    row_line = lines[j].strip()
                    if not row_line or len(row_line) < 5:
                        continue

                    # Simple split by multiple spaces or tabs
                    parts = re.split(r"\s{2,}|\t", row_line)
                    if len(parts) >= 2:
                        row = {}
                        for k, col in enumerate(table_schema.columns):
                            if k < len(parts):
                                row[col.name] = self._parse_value(parts[k], col.field_type)
                        if row:
                            rows.append(row)

                break

        if rows:
            return ExtractedTable(
                name=table_schema.name,
                rows=rows,
                confidence=0.7 if header_found else 0.5,
            )

        return None

    async def validate(
        self,
        result: ExtractionResult,
        schema: ExtractionSchema,
    ) -> ExtractionResult:
        """Validate extracted data against schema rules."""
        # Check required fields
        for field_def in schema.fields:
            if field_def.required:
                if field_def.name not in result.fields:
                    result.fields_requiring_review.append(field_def.name)
                elif result.fields[field_def.name].value is None:
                    result.fields[field_def.name].valid = False
                    result.fields[field_def.name].validation_errors.append(
                        f"Required field '{field_def.label}' is empty"
                    )

        # Apply validation rules
        for rule in schema.validation_rules:
            try:
                # Build context for rule evaluation
                context = {
                    f.name: f.value
                    for f in result.fields.values()
                }
                # Simple rule evaluation (basic comparison)
                # In production, use a proper expression evaluator
                if not self._evaluate_rule(rule.rule, context):
                    # Mark related fields as requiring review
                    for field in result.fields.values():
                        if field.name in rule.rule:
                            field.validation_errors.append(rule.message)
            except Exception as e:
                logger.warning(f"Rule evaluation failed: {e}")

        return result

    def _evaluate_rule(self, rule: str, context: Dict[str, Any]) -> bool:
        """Evaluate a simple validation rule."""
        # Basic comparisons only for safety
        if ">=" in rule:
            parts = rule.split(">=")
            left = self._get_context_value(parts[0].strip(), context)
            right = self._get_context_value(parts[1].strip(), context)
            return left >= right if left and right else True
        elif "<=" in rule:
            parts = rule.split("<=")
            left = self._get_context_value(parts[0].strip(), context)
            right = self._get_context_value(parts[1].strip(), context)
            return left <= right if left and right else True
        elif "==" in rule:
            parts = rule.split("==")
            left = self._get_context_value(parts[0].strip(), context)
            right = self._get_context_value(parts[1].strip(), context)
            return left == right

        return True

    def _get_context_value(self, expr: str, context: Dict[str, Any]) -> Any:
        """Get value from context or parse literal."""
        if expr in context:
            return context[expr]
        try:
            return float(expr)
        except ValueError:
            return expr


# =============================================================================
# Validation Queue Implementation
# =============================================================================

class ValidationQueueImpl(ValidationQueue):
    """
    Human-in-the-loop validation queue implementation.

    Features:
    - Task assignment
    - SLA tracking
    - Correction workflow
    """

    def __init__(self):
        self._tasks: Dict[str, ValidationTask] = {}

    async def submit_for_review(
        self,
        extraction_result: ExtractionResult,
        confidence_threshold: float = 0.8,
        deadline: datetime = None,
    ) -> ValidationTask:
        """Submit extraction result for human review."""
        # Identify fields needing review
        fields_to_review = []
        confidence_scores = {}

        for name, field in extraction_result.fields.items():
            confidence_scores[name] = field.confidence
            if field.confidence < confidence_threshold:
                fields_to_review.append(name)
            if not field.valid:
                fields_to_review.append(name)

        # Add already flagged fields
        fields_to_review.extend(extraction_result.fields_requiring_review)
        fields_to_review = list(set(fields_to_review))

        # Calculate priority based on confidence
        avg_confidence = extraction_result.overall_confidence
        if avg_confidence < 0.5:
            priority = 9
        elif avg_confidence < 0.7:
            priority = 7
        else:
            priority = 5

        task = ValidationTask(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            document_id=extraction_result.document_id,
            extraction_result=extraction_result,
            fields_to_review=fields_to_review,
            confidence_scores=confidence_scores,
            status=TaskStatus.PENDING,
            priority=priority,
            deadline=deadline or datetime.utcnow() + timedelta(hours=24),
        )

        self._tasks[task.task_id] = task
        logger.info(f"Created validation task: {task.task_id} with {len(fields_to_review)} fields to review")

        return task

    async def get_pending_tasks(
        self,
        assignee: str = None,
        document_type: DocumentType = None,
        limit: int = 100,
    ) -> List[ValidationTask]:
        """Get pending validation tasks."""
        result = []

        for task in self._tasks.values():
            if task.status not in (TaskStatus.PENDING, TaskStatus.IN_REVIEW):
                continue
            if assignee and task.assigned_to != assignee:
                continue
            if document_type and task.extraction_result.document_type != document_type:
                continue
            result.append(task)

        # Sort by priority (high first) and deadline
        result.sort(key=lambda t: (-t.priority, t.deadline or datetime.max))

        return result[:limit]

    async def assign_task(
        self,
        task_id: str,
        assignee: str,
    ) -> ValidationTask:
        """Assign task to reviewer."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        task.assigned_to = assignee
        task.assigned_at = datetime.utcnow()
        task.status = TaskStatus.IN_REVIEW

        logger.info(f"Assigned task {task_id} to {assignee}")
        return task

    async def approve(
        self,
        task_id: str,
        corrections: Dict[str, Any] = None,
        notes: str = None,
    ) -> ValidationTask:
        """Approve task with optional corrections."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        task.status = TaskStatus.APPROVED
        task.reviewed_at = datetime.utcnow()
        task.reviewer = task.assigned_to
        task.reviewer_corrections = corrections
        task.review_notes = notes

        # Apply corrections to extraction result
        if corrections:
            for field_name, corrected_value in corrections.items():
                if field_name in task.extraction_result.fields:
                    task.extraction_result.fields[field_name].value = corrected_value
                    task.extraction_result.fields[field_name].confidence = 1.0
                    task.extraction_result.fields[field_name].confidence_level = ExtractionConfidence.HIGH

        logger.info(f"Approved task {task_id}")
        return task

    async def reject(
        self,
        task_id: str,
        reason: str,
    ) -> ValidationTask:
        """Reject task."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        task.status = TaskStatus.REJECTED
        task.reviewed_at = datetime.utcnow()
        task.reviewer = task.assigned_to
        task.review_notes = reason

        logger.info(f"Rejected task {task_id}: {reason}")
        return task

    async def get_task(self, task_id: str) -> Optional[ValidationTask]:
        """Get task by ID."""
        return self._tasks.get(task_id)

    async def get_task_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        total = len(self._tasks)
        pending = sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING)
        in_review = sum(1 for t in self._tasks.values() if t.status == TaskStatus.IN_REVIEW)
        approved = sum(1 for t in self._tasks.values() if t.status == TaskStatus.APPROVED)
        rejected = sum(1 for t in self._tasks.values() if t.status == TaskStatus.REJECTED)

        overdue = sum(
            1 for t in self._tasks.values()
            if t.deadline and t.deadline < datetime.utcnow()
            and t.status in (TaskStatus.PENDING, TaskStatus.IN_REVIEW)
        )

        return {
            "total": total,
            "pending": pending,
            "in_review": in_review,
            "approved": approved,
            "rejected": rejected,
            "overdue": overdue,
        }


# =============================================================================
# Singleton Instances
# =============================================================================

_processor: DocumentProcessorImpl = None
_validation_queue: ValidationQueueImpl = None


def get_processor() -> DocumentProcessorImpl:
    """Get document processor singleton."""
    global _processor
    if _processor is None:
        _processor = DocumentProcessorImpl()
    return _processor


def get_validation_queue() -> ValidationQueueImpl:
    """Get validation queue singleton."""
    global _validation_queue
    if _validation_queue is None:
        _validation_queue = ValidationQueueImpl()
    return _validation_queue


__all__ = [
    # Implementations
    "DocumentProcessorImpl",
    "ValidationQueueImpl",
    # Helpers
    "extract_text",
    "extract_text_from_pdf",
    "extract_text_from_image",
    # Factory functions
    "get_processor",
    "get_validation_queue",
]
