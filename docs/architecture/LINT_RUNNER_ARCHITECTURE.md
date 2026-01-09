# Lint Runner Architecture

**Version**: 1.0.0
**Date**: 2026-01-08
**Status**: Draft

---

## Overview

This document defines the architecture for the Flyto module validation (lint) system.

### Design Goals

1. **3-Stage Execution** - Fast metadata checks first, AST analysis second, deep security scan last
2. **Severity Policy** - PR Gate vs Release Gate vs Baseline exemption
3. **Unified Reports** - JSON (machine) + Markdown (human)
4. **Auto-fix** - Generate diffs for common issues

---

## 1. Rule Abstract Interface

### 1.1 Base Rule Class

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
import ast


class RuleStage(str, Enum):
    """Execution stage for rules."""
    METADATA = "metadata"      # Stage 1: Registry metadata only
    AST = "ast"                # Stage 2: AST parsing required
    SECURITY = "security"      # Stage 3: Deep security scan


class Severity(str, Enum):
    """Issue severity levels."""
    INFO = "info"              # Informational, never blocks
    WARN = "warn"              # Warning, blocks in strict mode
    ERROR = "error"            # Error, blocks PR
    BLOCKER = "blocker"        # Blocker, blocks release
    FATAL = "fatal"            # Fatal, stops validation


@dataclass
class ValidationIssue:
    """A single validation issue."""
    rule_id: str
    severity: Severity
    message: str
    module_id: str = ""
    file: str = ""
    line: int = 0
    col: int = 0
    suggestion: Optional[str] = None
    fixable: bool = False
    fix_diff: Optional[str] = None


class BaseRule(ABC):
    """Abstract base class for all validation rules."""

    # Rule identification
    rule_id: str = ""              # e.g., "CORE-ID-001"
    description: str = ""          # Human-readable description
    category: str = ""             # e.g., "identity", "schema"
    stage: RuleStage = RuleStage.METADATA

    # Severity configuration
    default_severity: Severity = Severity.ERROR
    stability_aware: bool = True   # Adjust severity by module stability

    # Fixability
    fixable: bool = False

    @classmethod
    @abstractmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        """Validate a module against this rule."""
        pass

    @classmethod
    def fix(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: str,
    ) -> Optional[str]:
        """
        Generate fixed source code.

        Returns:
            Fixed source code string, or None if cannot fix.
        """
        return None
```

### 1.2 MetadataRule

Stage 1 rules that only need registry metadata - no file I/O required.

```python
class MetadataRule(BaseRule):
    """Rules that only check metadata (no source code needed)."""

    stage = RuleStage.METADATA

    @classmethod
    @abstractmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        """Validate metadata only."""
        pass
```

**Examples**:
- CORE-ID-001: module_id format
- CORE-ID-002: version format
- CORE-EX-002: timeout_ms presence
- CORE-CAP-001: required_permissions format

### 1.3 ASTRule

Stage 2 rules that require AST parsing.

```python
class ASTRule(BaseRule):
    """Rules that require AST analysis."""

    stage = RuleStage.AST

    @classmethod
    @abstractmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        """Validate using AST analysis."""
        pass

    @classmethod
    def ensure_ast(cls, source_code: str, ast_tree: Optional[ast.AST]) -> ast.AST:
        """Ensure AST is available, parsing if needed."""
        if ast_tree is not None:
            return ast_tree
        return ast.parse(source_code)
```

**Examples**:
- CORE-AST-001: syntax validity
- CORE-AST-003: no print()
- CORE-AST-007: no eval/exec
- CORE-SCH-011: params_schema consistency

### 1.4 CodeScanRule (Security Deep)

Stage 3 rules for deep security analysis.

```python
class CodeScanRule(BaseRule):
    """Rules that perform deep security scanning."""

    stage = RuleStage.SECURITY

    # Security rules are always high priority
    default_severity = Severity.BLOCKER

    @classmethod
    @abstractmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        """Perform deep security scan."""
        pass

    @classmethod
    def scan_for_patterns(cls, source_code: str, patterns: List[str]) -> List[tuple]:
        """
        Scan source for dangerous patterns.

        Returns:
            List of (line_number, matched_pattern, line_content)
        """
        import re
        results = []
        for i, line in enumerate(source_code.splitlines(), 1):
            for pattern in patterns:
                if re.search(pattern, line):
                    results.append((i, pattern, line.strip()))
        return results
```

**Examples**:
- CORE-SEC-001: no hardcoded secrets
- CORE-SEC-002: no os.getenv() without config system
- CORE-SEC-003: SSRF protection check
- CORE-SEC-004: eval() usage review

---

## 2. SeverityPolicy

### 2.1 Gate Levels

```python
from enum import Enum
from dataclasses import dataclass
from typing import Set


class GateLevel(str, Enum):
    """Validation gate levels."""
    DEV = "dev"            # Local development (warnings only)
    CI = "ci"              # PR gate (errors fail)
    RELEASE = "release"    # Release gate (blockers fail)
    STRICT = "strict"      # Strictest (all issues fail)


@dataclass
class SeverityPolicy:
    """Policy for severity handling at each gate level."""

    gate: GateLevel

    # Which severities block at this gate
    blocking_severities: Set[Severity]

    # Upgrade these severities (WARN -> ERROR in strict mode)
    upgrade_severities: Dict[Severity, Severity] = None

    # Exempt rules (baseline)
    exempt_rules: Set[str] = None

    # Only apply strict rules to stable modules
    stable_only_strict: bool = False

    def should_block(self, issue: ValidationIssue, stability: str = "stable") -> bool:
        """Check if this issue should block at current gate."""
        # Check exemption
        if self.exempt_rules and issue.rule_id in self.exempt_rules:
            return False

        # Check stability-aware strictness
        if self.stable_only_strict and stability != "stable":
            # Non-stable modules get lenient treatment
            if issue.severity not in (Severity.BLOCKER, Severity.FATAL):
                return False

        # Apply severity upgrade
        effective_severity = issue.severity
        if self.upgrade_severities and issue.severity in self.upgrade_severities:
            effective_severity = self.upgrade_severities[issue.severity]

        return effective_severity in self.blocking_severities
```

### 2.2 Predefined Policies

```python
# Development: Only FATAL blocks
DEV_POLICY = SeverityPolicy(
    gate=GateLevel.DEV,
    blocking_severities={Severity.FATAL},
)

# CI/PR Gate: ERROR and above blocks
CI_POLICY = SeverityPolicy(
    gate=GateLevel.CI,
    blocking_severities={Severity.ERROR, Severity.BLOCKER, Severity.FATAL},
)

# Release Gate: BLOCKER and above blocks
RELEASE_POLICY = SeverityPolicy(
    gate=GateLevel.RELEASE,
    blocking_severities={Severity.BLOCKER, Severity.FATAL},
    upgrade_severities={
        Severity.WARN: Severity.ERROR,  # Upgrade warnings for stable modules
    },
    stable_only_strict=True,
)

# Strict: Everything blocks
STRICT_POLICY = SeverityPolicy(
    gate=GateLevel.STRICT,
    blocking_severities={Severity.WARN, Severity.ERROR, Severity.BLOCKER, Severity.FATAL},
    upgrade_severities={
        Severity.INFO: Severity.WARN,
        Severity.WARN: Severity.ERROR,
    },
)
```

### 2.3 Baseline Mechanism

```python
@dataclass
class Baseline:
    """Known issues that are temporarily exempted."""

    # Rule exemptions (global)
    exempt_rules: Set[str] = field(default_factory=set)

    # Module-specific exemptions
    module_exemptions: Dict[str, Set[str]] = field(default_factory=dict)

    # Expiration date for exemptions
    expires_at: Optional[datetime] = None

    def is_exempt(self, module_id: str, rule_id: str) -> bool:
        """Check if this module/rule combination is exempt."""
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False

        if rule_id in self.exempt_rules:
            return True

        module_rules = self.module_exemptions.get(module_id, set())
        return rule_id in module_rules

    @classmethod
    def from_file(cls, path: str) -> "Baseline":
        """Load baseline from JSON file."""
        import json
        with open(path) as f:
            data = json.load(f)
        return cls(
            exempt_rules=set(data.get("exempt_rules", [])),
            module_exemptions={
                m: set(rules) for m, rules in data.get("module_exemptions", {}).items()
            },
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
        )
```

**baseline.json example**:
```json
{
  "version": "1.0",
  "created_at": "2026-01-08T00:00:00Z",
  "expires_at": "2026-02-08T00:00:00Z",
  "exempt_rules": [],
  "module_exemptions": {
    "flow.breakpoint": ["CORE-SEC-004"],
    "browser.execute_script": ["CORE-SEC-004"]
  },
  "comment": "Temporary exemptions for eval usage in safe contexts"
}
```

---

## 3. Report Format

### 3.1 JSON Report (report.json)

```json
{
  "version": "1.0",
  "generated_at": "2026-01-08T12:00:00Z",
  "gate_level": "release",
  "passed": false,

  "summary": {
    "total_modules": 191,
    "passed_modules": 189,
    "failed_modules": 2,
    "total_issues": 15,
    "blocking_issues": 3,
    "fixable_issues": 8
  },

  "by_severity": {
    "FATAL": 0,
    "BLOCKER": 2,
    "ERROR": 1,
    "WARN": 8,
    "INFO": 4
  },

  "by_category": {
    "identity": 2,
    "schema": 5,
    "security": 3,
    "execution": 5
  },

  "by_stage": {
    "metadata": 7,
    "ast": 5,
    "security": 3
  },

  "top_offenders": [
    {"module_id": "api.http_post", "issue_count": 3},
    {"module_id": "browser.click", "issue_count": 2}
  ],

  "issues": [
    {
      "rule_id": "CORE-SCH-001",
      "severity": "ERROR",
      "message": "Missing params_schema",
      "module_id": "api.http_post",
      "file": "src/core/modules/atomic/api/http_post.py",
      "line": 45,
      "suggestion": "Add params_schema to @register_module",
      "fixable": true
    }
  ],

  "trend": {
    "previous_run": "2026-01-07T12:00:00Z",
    "issues_delta": -5,
    "new_issues": 1,
    "resolved_issues": 6
  }
}
```

### 3.2 Markdown Report (report.md)

```markdown
# Module Validation Report

**Generated**: 2026-01-08 12:00:00 UTC
**Gate Level**: release
**Result**: FAILED

---

## Summary

| Metric | Value |
|--------|-------|
| Total Modules | 191 |
| Passed | 189 (99.0%) |
| Failed | 2 |
| Total Issues | 15 |
| Blocking | 3 |
| Fixable | 8 |

---

## Issues by Severity

| Severity | Count | Status |
|----------|-------|--------|
| FATAL | 0 | - |
| BLOCKER | 2 | BLOCKING |
| ERROR | 1 | BLOCKING |
| WARN | 8 | - |
| INFO | 4 | - |

---

## Top Offenders

| Module | Issues | Priority |
|--------|--------|----------|
| api.http_post | 3 | HIGH |
| browser.click | 2 | MEDIUM |

---

## Actionable Items

### Blocking (Must Fix)

1. **[CORE-SCH-001]** `api.http_post` - Missing params_schema
   - File: `src/core/modules/atomic/api/http_post.py:45`
   - Suggestion: Add params_schema to @register_module
   - Fixable: `--fix`

2. **[CORE-SEC-004]** `browser.execute_script` - Uses eval()
   - File: `src/core/modules/atomic/browser/execute_script.py:78`
   - Suggestion: Add stability='beta' or security_reviewed tag

### Warnings (Should Fix)

1. **[CORE-DOC-001]** `string.concat` - Missing examples
   - File: `src/core/modules/atomic/string/concat.py`
   - Suggestion: Add examples array to metadata

---

## Trend

| Metric | Current | Previous | Delta |
|--------|---------|----------|-------|
| Total Issues | 15 | 20 | -5 |
| New Issues | 1 | - | - |
| Resolved | 6 | - | - |

---

## Run Command

```bash
# Reproduce this report
FLYTO_VALIDATION_MODE=dev python scripts/validate_all_modules.py --strict=release

# Auto-fix fixable issues
FLYTO_VALIDATION_MODE=dev python scripts/validate_all_modules.py --fix
```
```

### 3.3 Report Generator

```python
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import json


@dataclass
class ReportGenerator:
    """Generate validation reports in multiple formats."""

    issues: List[ValidationIssue]
    modules: Dict[str, Dict[str, Any]]
    policy: SeverityPolicy
    previous_report: Optional[Dict] = None

    def to_json(self) -> str:
        """Generate JSON report."""
        report = self._build_report_data()
        return json.dumps(report, indent=2, default=str)

    def to_markdown(self) -> str:
        """Generate Markdown report."""
        data = self._build_report_data()
        return self._format_markdown(data)

    def _build_report_data(self) -> Dict:
        """Build structured report data."""
        blocking = [i for i in self.issues if self._is_blocking(i)]
        fixable = [i for i in self.issues if i.fixable]

        # Calculate passed/failed
        failed_modules = set(i.module_id for i in blocking)
        passed = len(self.modules) - len(failed_modules)

        return {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat(),
            "gate_level": self.policy.gate.value,
            "passed": len(blocking) == 0,
            "summary": {
                "total_modules": len(self.modules),
                "passed_modules": passed,
                "failed_modules": len(failed_modules),
                "total_issues": len(self.issues),
                "blocking_issues": len(blocking),
                "fixable_issues": len(fixable),
            },
            "by_severity": self._count_by("severity"),
            "by_category": self._count_by_category(),
            "top_offenders": self._get_top_offenders(5),
            "issues": [self._issue_to_dict(i) for i in self.issues],
            "trend": self._calculate_trend(),
        }

    def _is_blocking(self, issue: ValidationIssue) -> bool:
        """Check if issue is blocking."""
        module_meta = self.modules.get(issue.module_id, {})
        stability = module_meta.get("stability", "stable")
        return self.policy.should_block(issue, stability)
```

---

## 4. --fix Mechanism

### 4.1 Fixable Rules

Priority order for auto-fix:
1. Schema description formatting
2. Canonical field renaming (e.g., `input_types` -> `input_data_types`)
3. Example format standardization
4. Missing default values

### 4.2 Fix Interface

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class FixResult:
    """Result of an auto-fix attempt."""

    rule_id: str
    module_id: str
    success: bool
    original: str
    fixed: str
    diff: str
    message: str


class FixableRule(BaseRule):
    """Base class for rules that can auto-fix issues."""

    fixable = True

    @classmethod
    @abstractmethod
    def fix(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: str,
    ) -> Optional[FixResult]:
        """
        Attempt to fix the issue.

        Returns:
            FixResult with diff, or None if cannot fix.
        """
        pass

    @classmethod
    def generate_diff(cls, original: str, fixed: str) -> str:
        """Generate unified diff."""
        import difflib
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            fixed.splitlines(keepends=True),
            fromfile="original",
            tofile="fixed",
        )
        return "".join(diff)
```

### 4.3 Example: Schema Description Fixer

```python
class SchemaDescriptionFixer(FixableRule):
    """Fix missing descriptions in params_schema and output_schema."""

    rule_id = "CORE-SCH-002"
    description = "Schema fields should have descriptions"
    fixable = True

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        for schema_name in ["params_schema", "output_schema"]:
            schema = metadata.get(schema_name, {})
            for key, spec in schema.items():
                if not spec.get("description"):
                    issues.append(cls.create_issue(
                        message=f"{schema_name}.{key} missing description",
                        module_id=module_id,
                        suggestion=f"Add description to {schema_name}.{key}",
                        fixable=True,
                    ))

        return issues

    @classmethod
    def fix(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: str,
    ) -> Optional[FixResult]:
        """Add default descriptions based on field names."""
        import re

        fixed = source_code
        changes_made = False

        for schema_name in ["params_schema", "output_schema"]:
            schema = metadata.get(schema_name, {})
            for key, spec in schema.items():
                if not spec.get("description"):
                    # Generate description from key name
                    desc = cls._generate_description(key, spec.get("type", "any"))

                    # Find and fix in source
                    pattern = rf"('{key}':\s*\{{\s*'type':\s*'[^']+')(\s*\}})"
                    replacement = rf"\1, 'description': '{desc}'\2"
                    new_fixed = re.sub(pattern, replacement, fixed)

                    if new_fixed != fixed:
                        fixed = new_fixed
                        changes_made = True

        if not changes_made:
            return None

        return FixResult(
            rule_id=cls.rule_id,
            module_id=module_id,
            success=True,
            original=source_code,
            fixed=fixed,
            diff=cls.generate_diff(source_code, fixed),
            message=f"Added missing descriptions to schema fields",
        )

    @classmethod
    def _generate_description(cls, key: str, type_hint: str) -> str:
        """Generate description from key name."""
        # Convert snake_case to readable format
        words = key.replace("_", " ").title()

        type_descriptions = {
            "string": "text value",
            "number": "numeric value",
            "boolean": "true/false flag",
            "object": "configuration object",
            "array": "list of items",
        }

        type_desc = type_descriptions.get(type_hint, "value")
        return f"The {words.lower()} {type_desc}"
```

### 4.4 Fix Runner

```python
class FixRunner:
    """Run auto-fixes on modules."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.results: List[FixResult] = []

    def run(
        self,
        modules: Dict[str, Dict[str, Any]],
        source_codes: Dict[str, str],
        file_paths: Dict[str, str],
    ) -> List[FixResult]:
        """Run all fixable rules on modules."""

        for module_id, metadata in modules.items():
            source = source_codes.get(module_id)
            if not source:
                continue

            for rule in get_fixable_rules():
                issues = rule.validate(module_id, metadata, source)

                for issue in issues:
                    if issue.fixable:
                        result = rule.fix(module_id, metadata, source)
                        if result:
                            self.results.append(result)

                            if not self.dry_run:
                                # Apply fix
                                file_path = file_paths.get(module_id)
                                if file_path:
                                    with open(file_path, "w") as f:
                                        f.write(result.fixed)
                                    # Update source for subsequent fixes
                                    source = result.fixed

        return self.results

    def generate_diff_report(self) -> str:
        """Generate unified diff report for all fixes."""
        lines = ["# Auto-Fix Diff Report\n"]

        for result in self.results:
            lines.append(f"## {result.module_id} ({result.rule_id})\n")
            lines.append("```diff")
            lines.append(result.diff)
            lines.append("```\n")

        return "\n".join(lines)
```

---

## 5. Runner Implementation

### 5.1 3-Stage Execution

```python
class LintRunner:
    """Main lint runner with 3-stage execution."""

    def __init__(
        self,
        policy: SeverityPolicy,
        baseline: Optional[Baseline] = None,
        enable_fix: bool = False,
    ):
        self.policy = policy
        self.baseline = baseline
        self.enable_fix = enable_fix
        self.issues: List[ValidationIssue] = []
        self.fixes: List[FixResult] = []

    def run(
        self,
        modules: Dict[str, Dict[str, Any]],
        source_codes: Optional[Dict[str, str]] = None,
        file_paths: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, List[ValidationIssue]]:
        """
        Run validation in 3 stages.

        Returns:
            (passed, issues)
        """
        source_codes = source_codes or {}
        file_paths = file_paths or {}

        # Stage 1: Metadata rules (fast, no I/O)
        print("Stage 1: Metadata validation...")
        metadata_rules = get_rules_by_stage(RuleStage.METADATA)
        self._run_rules(metadata_rules, modules, source_codes)

        # Early exit if fatal errors
        if self._has_fatal():
            return False, self.issues

        # Stage 2: AST rules (parse source)
        print("Stage 2: AST validation...")
        ast_rules = get_rules_by_stage(RuleStage.AST)
        ast_cache = self._parse_all(source_codes)
        self._run_rules(ast_rules, modules, source_codes, ast_cache)

        # Stage 3: Security deep scan
        print("Stage 3: Security scan...")
        security_rules = get_rules_by_stage(RuleStage.SECURITY)
        self._run_rules(security_rules, modules, source_codes, ast_cache)

        # Apply baseline exemptions
        if self.baseline:
            self.issues = self._apply_baseline(self.issues)

        # Run fixes if enabled
        if self.enable_fix:
            self._run_fixes(modules, source_codes, file_paths)

        # Calculate result
        blocking = [i for i in self.issues if self._is_blocking(i, modules)]
        passed = len(blocking) == 0

        return passed, self.issues

    def _run_rules(
        self,
        rules: List[Type[BaseRule]],
        modules: Dict[str, Dict[str, Any]],
        source_codes: Dict[str, str],
        ast_cache: Optional[Dict[str, ast.AST]] = None,
    ):
        """Run a set of rules on all modules."""
        for module_id, metadata in modules.items():
            source = source_codes.get(module_id)
            ast_tree = ast_cache.get(module_id) if ast_cache else None

            for rule in rules:
                try:
                    issues = rule.validate(module_id, metadata, source, ast_tree)
                    self.issues.extend(issues)
                except Exception as e:
                    self.issues.append(ValidationIssue(
                        rule_id=rule.rule_id,
                        severity=Severity.WARN,
                        message=f"Rule execution failed: {e}",
                        module_id=module_id,
                    ))

    def _parse_all(self, source_codes: Dict[str, str]) -> Dict[str, ast.AST]:
        """Parse all source codes to AST."""
        cache = {}
        for module_id, source in source_codes.items():
            try:
                cache[module_id] = ast.parse(source)
            except SyntaxError:
                pass  # AST rules will report this
        return cache
```

### 5.2 CLI Interface

```python
import argparse


def main():
    parser = argparse.ArgumentParser(description="Flyto Module Linter")

    parser.add_argument(
        "--strict",
        choices=["dev", "ci", "release", "strict"],
        default="ci",
        help="Gate level for validation",
    )

    parser.add_argument(
        "--baseline",
        type=str,
        help="Path to baseline.json for exemptions",
    )

    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix fixable issues (generates diff)",
    )

    parser.add_argument(
        "--fix-apply",
        action="store_true",
        help="Apply auto-fixes directly to files",
    )

    parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format",
    )

    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (default: stdout)",
    )

    args = parser.parse_args()

    # Select policy
    policy_map = {
        "dev": DEV_POLICY,
        "ci": CI_POLICY,
        "release": RELEASE_POLICY,
        "strict": STRICT_POLICY,
    }
    policy = policy_map[args.strict]

    # Load baseline if provided
    baseline = None
    if args.baseline:
        baseline = Baseline.from_file(args.baseline)

    # Discover modules
    modules = discover_modules()
    source_codes = load_source_codes(modules)
    file_paths = get_file_paths(modules)

    # Run linter
    runner = LintRunner(
        policy=policy,
        baseline=baseline,
        enable_fix=args.fix or args.fix_apply,
    )

    passed, issues = runner.run(modules, source_codes, file_paths)

    # Generate report
    generator = ReportGenerator(
        issues=issues,
        modules=modules,
        policy=policy,
    )

    if args.format == "json":
        output = generator.to_json()
    elif args.format == "markdown":
        output = generator.to_markdown()
    else:
        output = format_text_report(issues, passed)

    # Output
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
    else:
        print(output)

    # Exit code
    return 0 if passed else 1


if __name__ == "__main__":
    exit(main())
```

---

## 6. Usage Examples

### Basic Usage

```bash
# Development mode (only FATAL blocks)
python -m core.lint --strict=dev

# PR gate (ERROR blocks)
python -m core.lint --strict=ci

# Release gate (BLOCKER blocks, stable modules strict)
python -m core.lint --strict=release

# Strictest (all issues block)
python -m core.lint --strict=strict
```

### With Baseline

```bash
# Use baseline for known issues
python -m core.lint --strict=release --baseline=baseline.json
```

### Auto-fix

```bash
# Generate diff only
python -m core.lint --fix --format=markdown > fix-report.md

# Apply fixes
python -m core.lint --fix-apply
```

### Report Generation

```bash
# JSON report
python -m core.lint --format=json --output=report.json

# Markdown report
python -m core.lint --format=markdown --output=report.md
```

### CI Integration

```yaml
# .github/workflows/lint.yml
name: Module Lint

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Lint (PR gate)
        run: python -m core.lint --strict=ci --format=json --output=report.json

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: lint-report
          path: report.json

      - name: Comment on PR
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const report = require('./report.json');
            const blocking = report.issues.filter(i =>
              ['ERROR', 'BLOCKER', 'FATAL'].includes(i.severity)
            );

            let body = '## Lint Report\n\n';
            body += `**Status**: ${report.passed ? 'PASSED' : 'FAILED'}\n`;
            body += `**Blocking Issues**: ${blocking.length}\n\n`;

            if (blocking.length > 0) {
              body += '### Issues\n\n';
              for (const issue of blocking.slice(0, 10)) {
                body += `- **[${issue.rule_id}]** ${issue.module_id}: ${issue.message}\n`;
              }
            }

            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: body
            });
```

---

## 7. Migration Path

### Phase 1: Core Rules (Current)
- 28+ rules in flyto-core
- Basic severity handling
- CLI validation script

### Phase 2: Architecture Upgrade
- Implement 3-stage execution
- Add SeverityPolicy system
- Add baseline support
- Unified report format

### Phase 3: Auto-fix
- Implement fixable rules
- Diff generation
- Safe apply mechanism

### Phase 4: Pro Integration
- 50 additional rules from flyto-pro
- Rule inheritance (core + pro)
- Governance reports

---

## Appendix: Rule Categories

| Category | Prefix | Stage | Description |
|----------|--------|-------|-------------|
| Identity | CORE-ID | metadata | module_id, version format |
| Execution | CORE-EX | metadata | timeout, retry settings |
| Schema | CORE-SCH | metadata+ast | params/output schema |
| Capability | CORE-CAP | metadata | permissions, credentials |
| Security | CORE-SEC | security | secrets, eval, SSRF |
| Documentation | CORE-DOC | metadata | descriptions, examples |
| AST | CORE-AST | ast | syntax, forbidden calls |
