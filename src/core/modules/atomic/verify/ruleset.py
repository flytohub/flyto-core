"""
Verify Ruleset Module - Load verification rules from YAML

Defines what to verify and tolerance settings.
For style verification (compare browser with Figma).
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field as schema_field


@dataclass
class Rule:
    """A single verification rule."""
    name: str
    selector: str
    figma_node: Optional[str] = None
    check_typography: bool = True
    check_colors: bool = True
    check_spacing: bool = True
    check_sizing: bool = False
    size_tolerance: Optional[float] = None
    spacing_tolerance: Optional[float] = None
    font_size_tolerance: Optional[float] = None
    color_tolerance: Optional[int] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rule":
        return cls(
            name=data.get('name', 'unnamed'),
            selector=data.get('selector', ''),
            figma_node=data.get('figma_node'),
            check_typography=data.get('check_typography', True),
            check_colors=data.get('check_colors', True),
            check_spacing=data.get('check_spacing', True),
            check_sizing=data.get('check_sizing', False),
            size_tolerance=data.get('size_tolerance'),
            spacing_tolerance=data.get('spacing_tolerance'),
            font_size_tolerance=data.get('font_size_tolerance'),
            color_tolerance=data.get('color_tolerance'),
            description=data.get('description'),
        )


@dataclass
class Ruleset:
    """Collection of verification rules."""
    name: str
    version: str = "1.0"
    description: Optional[str] = None
    figma_file_id: Optional[str] = None
    base_url: Optional[str] = None
    size_tolerance: float = 2.0
    spacing_tolerance: float = 2.0
    font_size_tolerance: float = 1.0
    color_tolerance: int = 5
    rules: List[Rule] = field(default_factory=list)
    viewport_width: int = 1280
    viewport_height: int = 800

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'figma_file_id': self.figma_file_id,
            'base_url': self.base_url,
            'tolerances': {
                'size': self.size_tolerance,
                'spacing': self.spacing_tolerance,
                'font_size': self.font_size_tolerance,
                'color': self.color_tolerance,
            },
            'viewport': {
                'width': self.viewport_width,
                'height': self.viewport_height,
            },
            'rules': [r.to_dict() for r in self.rules],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Ruleset":
        tolerances = data.get('tolerances', {})
        viewport = data.get('viewport', {})

        ruleset = cls(
            name=data.get('name', 'unnamed'),
            version=data.get('version', '1.0'),
            description=data.get('description'),
            figma_file_id=data.get('figma_file_id'),
            base_url=data.get('base_url'),
            size_tolerance=tolerances.get('size', 2.0),
            spacing_tolerance=tolerances.get('spacing', 2.0),
            font_size_tolerance=tolerances.get('font_size', 1.0),
            color_tolerance=tolerances.get('color', 5),
            viewport_width=viewport.get('width', 1280),
            viewport_height=viewport.get('height', 800),
        )

        for rule_data in data.get('rules', []):
            ruleset.rules.append(Rule.from_dict(rule_data))

        return ruleset

    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)


def load_ruleset(path: Union[str, Path]) -> Ruleset:
    """Load ruleset from YAML file."""
    import yaml

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Ruleset file not found: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    return Ruleset.from_dict(data)


def save_ruleset(ruleset: Ruleset, path: Union[str, Path]) -> None:
    """Save ruleset to YAML file."""
    import yaml

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(ruleset.to_dict(), f, default_flow_style=False, allow_unicode=True)


@register_module(
    module_id='verify.ruleset',
    version='1.0.0',
    category='verify',
    tags=['verify', 'ruleset', 'yaml', 'config'],
    label='Load Ruleset',
    label_key='modules.verify.ruleset.label',
    description='Load verification rules from YAML file',
    description_key='modules.verify.ruleset.description',
    icon='FileJson',
    color='#8B5CF6',

    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['verify.run', 'verify.*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.read'],

    params_schema=compose(
        schema_field('path', type='string', required=True, description='Path to YAML ruleset file'),
    ),
    output_schema={
        'ruleset': {'type': 'object', 'description': 'Parsed ruleset'},
        'rules_count': {'type': 'integer', 'description': 'Number of rules'},
    },
)
class VerifyRulesetModule(BaseModule):
    """Load verification rules from YAML file."""

    module_name = "Load Ruleset"
    module_description = "Parse YAML verification rules"

    def validate_params(self) -> None:
        self.path = self.params.get('path')
        if not self.path:
            raise ValueError("path is required")

    async def execute(self) -> Dict[str, Any]:
        ruleset = load_ruleset(self.path)

        # Store in context
        self.context['ruleset'] = ruleset

        return {
            'ok': True,
            'data': {
                'ruleset': ruleset.to_dict(),
                'rules_count': len(ruleset.rules),
            }
        }
