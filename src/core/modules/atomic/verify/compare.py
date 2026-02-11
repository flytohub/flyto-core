"""
Verify Compare Module - Compare captured styles with expected values

Detects differences with configurable tolerance.
"""
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field as schema_field


class Severity(Enum):
    """Violation severity levels."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Violation:
    """A single style violation."""
    property: str
    expected: Any
    actual: Any
    difference: Optional[float] = None
    severity: Severity = Severity.WARNING
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property": self.property,
            "expected": self.expected,
            "actual": self.actual,
            "difference": self.difference,
            "severity": self.severity.value,
            "message": self.message or f"{self.property}: expected {self.expected}, got {self.actual}",
        }


@dataclass
class CompareResult:
    """Result of comparing one element."""
    selector: str
    passed: bool
    violations: List[Violation] = field(default_factory=list)
    expected_style: Optional[Dict[str, Any]] = None
    actual_style: Optional[Dict[str, Any]] = None

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.WARNING)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selector": self.selector,
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "violations": [v.to_dict() for v in self.violations],
        }


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


def colors_match(color1: str, color2: str, tolerance: int = 5) -> bool:
    """Check if two colors match within tolerance."""
    try:
        r1, g1, b1 = hex_to_rgb(color1)
        r2, g2, b2 = hex_to_rgb(color2)
        return abs(r1 - r2) <= tolerance and abs(g1 - g2) <= tolerance and abs(b1 - b2) <= tolerance
    except ValueError:
        return color1.lower() == color2.lower()


@register_module(
    module_id='verify.compare',
    version='1.0.0',
    category='verify',
    tags=['verify', 'compare', 'style', 'design', 'figma'],
    label='Compare Styles',
    label_key='modules.verify.compare.label',
    description='Compare captured styles with expected values',
    description_key='modules.verify.compare.description',
    icon='GitCompare',
    color='#8B5CF6',

    input_types=['object'],
    output_types=['object'],

    can_receive_from=['verify.capture', 'verify.*'],
    can_connect_to=['verify.*', 'data.*', 'flow.*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        schema_field('actual', type='object', required=True, description='Captured element styles (from verify.capture)'),
        schema_field('expected', type='object', required=True, description='Expected styles to compare against'),
        schema_field('selector', type='string', required=False, description='Selector for reporting',
                     placeholder='#element or .class'),
        schema_field('size_tolerance', type='number', required=False, default=2.0, description='Tolerance for size (px)'),
        schema_field('spacing_tolerance', type='number', required=False, default=2.0, description='Tolerance for spacing (px)'),
        schema_field('font_size_tolerance', type='number', required=False, default=1.0, description='Tolerance for font size (px)'),
        schema_field('color_tolerance', type='integer', required=False, default=5, description='Tolerance for color (0-255)'),
        schema_field('check_typography', type='boolean', required=False, default=True, description='Check typography'),
        schema_field('check_colors', type='boolean', required=False, default=True, description='Check colors'),
        schema_field('check_spacing', type='boolean', required=False, default=True, description='Check spacing'),
        schema_field('check_sizing', type='boolean', required=False, default=False, description='Check sizing'),
    ),
    output_schema={
        'passed': {'type': 'boolean', 'description': 'Whether comparison passed'},
        'violations': {'type': 'array', 'description': 'List of violations found'},
        'error_count': {'type': 'integer', 'description': 'Number of errors'},
        'warning_count': {'type': 'integer', 'description': 'Number of warnings'},
    },
)
class VerifyCompareModule(BaseModule):
    """Compare captured styles with expected values."""

    module_name = "Compare Styles"
    module_description = "Detect style differences with tolerance"

    def validate_params(self) -> None:
        self.actual = self.params.get('actual', {})
        self.expected = self.params.get('expected', {})
        self.selector = self.params.get('selector', '')

        self.size_tolerance = self.params.get('size_tolerance', 2.0)
        self.spacing_tolerance = self.params.get('spacing_tolerance', 2.0)
        self.font_size_tolerance = self.params.get('font_size_tolerance', 1.0)
        self.color_tolerance = self.params.get('color_tolerance', 5)

        self.check_typography = self.params.get('check_typography', True)
        self.check_colors = self.params.get('check_colors', True)
        self.check_spacing = self.params.get('check_spacing', True)
        self.check_sizing = self.params.get('check_sizing', False)

    async def execute(self) -> Dict[str, Any]:
        violations = []

        # Use captured element from context if not provided
        if not self.actual and 'captured_element' in self.context:
            captured = self.context['captured_element']
            self.actual = captured.to_dict() if hasattr(captured, 'to_dict') else captured

        if self.check_typography:
            violations.extend(self._compare_typography())

        if self.check_colors:
            violations.extend(self._compare_colors())

        if self.check_spacing:
            violations.extend(self._compare_spacing())

        if self.check_sizing:
            violations.extend(self._compare_sizing())

        has_errors = any(v.severity == Severity.ERROR for v in violations)
        result = CompareResult(
            selector=self.selector,
            passed=not has_errors,
            violations=violations,
            expected_style=self.expected,
            actual_style=self.actual,
        )

        # Store in context
        self.context['compare_result'] = result

        return {
            'ok': True,
            'data': result.to_dict()
        }

    def _compare_typography(self) -> List[Violation]:
        violations = []

        # Font size
        exp_fs = self.expected.get('font_size') or self.expected.get('fontSize')
        act_fs = self.actual.get('font_size') or self.actual.get('fontSize')
        if exp_fs is not None and act_fs is not None:
            diff = abs(float(exp_fs) - float(act_fs))
            if diff > self.font_size_tolerance:
                violations.append(Violation(
                    property="font_size",
                    expected=exp_fs,
                    actual=act_fs,
                    difference=diff,
                    severity=Severity.ERROR if diff > 4 else Severity.WARNING,
                ))

        # Font weight
        exp_fw = self.expected.get('font_weight') or self.expected.get('fontWeight')
        act_fw = self.actual.get('font_weight') or self.actual.get('fontWeight')
        if exp_fw is not None and act_fw is not None:
            diff = abs(int(exp_fw) - int(act_fw))
            if diff > 0:
                violations.append(Violation(
                    property="font_weight",
                    expected=exp_fw,
                    actual=act_fw,
                    difference=diff,
                    severity=Severity.WARNING if diff <= 100 else Severity.ERROR,
                ))

        return violations

    def _compare_colors(self) -> List[Violation]:
        violations = []

        # Text color
        exp_color = self.expected.get('color') or self.expected.get('fill_color')
        act_color = self.actual.get('color')
        if exp_color and act_color:
            if not colors_match(exp_color, act_color, self.color_tolerance):
                violations.append(Violation(
                    property="color",
                    expected=exp_color,
                    actual=act_color,
                    severity=Severity.WARNING,
                ))

        # Background color
        exp_bg = self.expected.get('background_color') or self.expected.get('backgroundColor')
        act_bg = self.actual.get('background_color') or self.actual.get('backgroundColor')
        if exp_bg and act_bg:
            if not colors_match(exp_bg, act_bg, self.color_tolerance):
                violations.append(Violation(
                    property="background_color",
                    expected=exp_bg,
                    actual=act_bg,
                    severity=Severity.WARNING,
                ))

        return violations

    def _compare_spacing(self) -> List[Violation]:
        violations = []
        tol = self.spacing_tolerance

        padding_props = [
            ('padding_top', 'paddingTop'),
            ('padding_right', 'paddingRight'),
            ('padding_bottom', 'paddingBottom'),
            ('padding_left', 'paddingLeft'),
        ]

        for snake, camel in padding_props:
            exp = self.expected.get(snake) or self.expected.get(camel)
            act = self.actual.get(snake) or self.actual.get(camel)
            if exp is not None and act is not None:
                diff = abs(float(exp) - float(act))
                if diff > tol:
                    violations.append(Violation(
                        property=snake,
                        expected=exp,
                        actual=act,
                        difference=diff,
                        severity=Severity.WARNING if diff <= 8 else Severity.ERROR,
                    ))

        return violations

    def _compare_sizing(self) -> List[Violation]:
        violations = []
        tol = self.size_tolerance

        for prop in ['width', 'height']:
            exp = self.expected.get(prop)
            act = self.actual.get(prop)
            if exp is not None and act is not None:
                diff = abs(float(exp) - float(act))
                if diff > tol:
                    violations.append(Violation(
                        property=prop,
                        expected=exp,
                        actual=act,
                        difference=diff,
                        severity=Severity.INFO if diff <= 10 else Severity.WARNING,
                    ))

        return violations
