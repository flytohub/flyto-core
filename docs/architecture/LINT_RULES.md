# Flyto-Core Lint Rules Reference

This document provides a comprehensive reference for all validation rules in the flyto-core quality system.

## Overview

- **Total Rules**: 28+ rules across 6 categories
- **Execution**: 3-stage validation (Metadata → AST → Security)
- **Stability-Aware**: Severity adjusts based on module stability

## Rule Categories

### Identity Rules (CORE-ID-*)

Rules that validate module identity and versioning.

| ID | Severity | Stage | Description | Fixable |
|----|----------|-------|-------------|---------|
| CORE-ID-001 | ERROR | metadata | module_id must match pattern `category.action` | No |
| CORE-ID-002 | ERROR | metadata | version must follow semver (X.Y.Z) | No |
| CORE-ID-003 | WARN | metadata | stability must be valid value | No |

### Execution Rules (CORE-EX-*)

Rules that validate execution parameters.

| ID | Severity | Stage | Description | Fixable |
|----|----------|-------|-------------|---------|
| CORE-EX-001 | ERROR | metadata | timeout_ms must be positive | No |
| CORE-EX-002 | WARN | metadata | timeout_ms should not exceed 10 minutes | No |
| CORE-EX-003 | ERROR | metadata | max_retries must be within bounds (1-10) | No |

### Schema Rules (CORE-SCH-*)

Rules that validate params_schema and output_schema.

| ID | Severity | Stage | Description | Fixable |
|----|----------|-------|-------------|---------|
| CORE-SCH-001 | ERROR | metadata | params_schema is required for stable modules | No |
| CORE-SCH-002 | ERROR | metadata | output_schema is required | No |
| CORE-SCH-003 | ERROR | metadata | Schema properties must have type | No |
| CORE-SCH-004 | WARN | metadata | Schema properties should have description | No |
| CORE-SCH-005 | ERROR | metadata | Required fields must not have default | No |
| CORE-SCH-011 | ERROR | ast | params usage must match params_schema | No |
| CORE-SCH-012 | WARN | ast | return structure must match output_schema | No |

### Capability Rules (CORE-CAP-*)

Rules that validate permissions and capabilities.

| ID | Severity | Stage | Description | Fixable |
|----|----------|-------|-------------|---------|
| CORE-CAP-001 | ERROR | metadata | capabilities must be from whitelist | No |
| CORE-CAP-002 | ERROR | metadata | capabilities required for side effects | No |
| CORE-CAP-003 | WARN | ast | declared capabilities must match observed | No |
| CORE-CAP-004 | ERROR | metadata | dangerous capabilities require security_reviewed | No |

### Security Rules (CORE-SEC-*)

Rules that check for security issues.

| ID | Severity | Stage | Description | Fixable |
|----|----------|-------|-------------|---------|
| CORE-SEC-001 | BLOCKER | ast | No API keys or secrets in defaults | No |
| CORE-SEC-002 | BLOCKER | ast | No secrets in example values | No |
| CORE-SEC-003 | WARN | metadata | credential_keys should be declared | No |
| CORE-SEC-004 | ERROR | security | sensitive params must be marked | No |

### AST Rules (CORE-AST-*)

Rules that analyze code structure via AST.

| ID | Severity | Stage | Description | Fixable |
|----|----------|-------|-------------|---------|
| CORE-AST-000 | FATAL | ast | Syntax must be valid Python | No |
| CORE-AST-001 | ERROR | ast | execute() method must be async | No |
| CORE-AST-002 | WARN | ast | No print statements in production code | Yes |
| CORE-AST-003 | ERROR | ast | No logging with sensitive data | No |
| CORE-AST-004 | WARN | ast | No commented-out code blocks | No |
| CORE-AST-005 | ERROR | ast | No hardcoded file paths | No |
| CORE-AST-006 | WARN | ast | No TODO/FIXME in stable modules | No |
| CORE-AST-007 | BLOCKER | ast | No dangerous functions (eval/exec/compile) | No |
| CORE-AST-008 | WARN | ast | Functions should have docstrings | No |
| CORE-AST-009 | ERROR | ast | No wildcard imports | No |

---

## Severity Levels

| Level | Symbol | CI Behavior | When to Use |
|-------|--------|-------------|-------------|
| INFO | i | Pass, just log | Informational |
| WARN | ! | Pass, but warn | Should fix soon |
| ERROR | X | Fail PR | Must fix before merge |
| BLOCKER | XX | Fail release | Critical security/stability |
| FATAL | XXX | Fail immediately | Syntax errors |

---

## Execution Stages

| Stage | When | Rules Run |
|-------|------|-----------|
| METADATA | Always | Checks registry metadata only |
| AST | If source provided | Requires source code parsing |
| SECURITY | If source provided | Deep security scans |

**Early Exit**: If a FATAL error occurs in Stage 1, Stages 2 and 3 are skipped.

---

## Gate Levels

| Gate | Blocking Severities | Use Case |
|------|---------------------|----------|
| DEV | FATAL only | Development |
| CI | ERROR, BLOCKER, FATAL | Pull Request |
| RELEASE | BLOCKER, FATAL | Release branch |
| STRICT | All (WARN→ERROR) | Release gate |

---

## CLI Usage

```bash
# Basic validation
python scripts/validate_all_modules.py

# Strict mode for release
python scripts/validate_all_modules.py --strict=release

# With mypy type checking
python scripts/validate_all_modules.py --strict=release --include-mypy

# JSON output
python scripts/validate_all_modules.py --format=json --output=report.json

# Markdown report
python scripts/validate_all_modules.py --format=markdown --output=report.md

# With baseline exemptions
python scripts/validate_all_modules.py --baseline=.baseline.json

# List all rules
python scripts/validate_all_modules.py --list-rules
```

---

## Baseline Exemptions

Create a `.baseline.json` file to exempt specific rules:

```json
{
  "exempt_rules": ["CORE-AST-006"],
  "module_exemptions": {
    "browser.click": ["CORE-SCH-004"]
  },
  "expires_at": "2026-06-01T00:00:00",
  "reason": "Legacy modules pending refactor"
}
```

---

## Stability-Aware Severity

Some rules adjust severity based on module stability:

| Stability | Default Behavior |
|-----------|-----------------|
| stable | Full enforcement |
| beta | WARN for some rules |
| alpha | INFO for most rules |
| experimental | INFO only |
| deprecated | WARN only |

---

## Adding New Rules

1. Create rule class in appropriate category file under `rules/`
2. Inherit from `MetadataRule`, `ASTRule`, or `SecurityRule`
3. Set `rule_id`, `description`, `category`, `default_severity`, `stage`
4. Implement `validate()` method
5. Register with `@register_rule` decorator

Example:
```python
from .base import MetadataRule
from ..types import Severity, RuleStage

@register_rule
class MyNewRule(MetadataRule):
    rule_id = "CORE-XX-001"
    description = "Rule description"
    category = "category"
    stage = RuleStage.METADATA
    default_severity = Severity.ERROR

    @classmethod
    def validate(cls, module_id, metadata, source_code=None, ast_tree=None):
        issues = []
        # Validation logic
        return issues
```

---

## Related Documentation

- [LINT_RUNNER_ARCHITECTURE.md](./LINT_RUNNER_ARCHITECTURE.md) - Full architecture design
- [MODULE_SPECIFICATION.md](../MODULE_SPECIFICATION.md) - Module metadata specification
