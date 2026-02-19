# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Schema Audit Module - Quality assurance for module schemas

This module provides tools to audit, report, and fix schema quality issues
across all registered modules.

Usage:
    from core.modules.audit import SchemaAuditor, run_audit

    # Run full audit
    auditor = SchemaAuditor()
    report = auditor.audit_all()

    # Generate reports
    auditor.generate_report('/path/to/report')
"""
from .standards import (
    REQUIRED_PARAM_FIELDS,
    RECOMMENDED_PARAM_FIELDS,
    REQUIRED_OUTPUT_FIELDS,
    DEFAULT_PLACEHOLDERS,
    DEFAULT_DESCRIPTIONS,
    QualityLevel,
)
from .schema_auditor import SchemaAuditor, AuditResult, FieldIssue
from .report_generator import ReportGenerator

__all__ = [
    'SchemaAuditor',
    'AuditResult',
    'FieldIssue',
    'ReportGenerator',
    'REQUIRED_PARAM_FIELDS',
    'RECOMMENDED_PARAM_FIELDS',
    'REQUIRED_OUTPUT_FIELDS',
    'DEFAULT_PLACEHOLDERS',
    'DEFAULT_DESCRIPTIONS',
    'QualityLevel',
]
