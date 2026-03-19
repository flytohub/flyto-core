# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Data Validate Records Module — Validate and filter extracted records

Single responsibility: check each record against field rules, split into valid/invalid.

Workflow position:
  pagination → dedup → validate_records → database.insert
"""
import logging
import re
from typing import Any, Dict, List

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)


# Built-in validators
_VALIDATORS = {
    'required': lambda v, _: v is not None and v != '',
    'not_empty': lambda v, _: bool(v) if isinstance(v, (str, list, dict)) else v is not None,
    'is_number': lambda v, _: isinstance(v, (int, float)) or (isinstance(v, str) and v.replace('.', '', 1).replace('-', '', 1).isdigit()),
    'is_url': lambda v, _: isinstance(v, str) and v.startswith(('http://', 'https://')),
    'is_email': lambda v, _: isinstance(v, str) and '@' in v and '.' in v.split('@')[-1],
    'min_length': lambda v, n: isinstance(v, str) and len(v) >= int(n),
    'max_length': lambda v, n: isinstance(v, str) and len(v) <= int(n),
    'matches': lambda v, p: isinstance(v, str) and bool(re.search(p, v)),
    'min_value': lambda v, n: isinstance(v, (int, float)) and v >= float(n),
    'max_value': lambda v, n: isinstance(v, (int, float)) and v <= float(n),
}


@register_module(
    module_id='data.validate_records',
    version='1.0.0',
    category='data',
    tags=['data', 'validate', 'filter', 'quality', 'clean'],
    label='Validate Records',
    label_key='modules.data.validate_records.label',
    description='Validate extracted records against field rules. Splits output into valid and invalid arrays.',
    description_key='modules.data.validate_records.description',
    icon='CheckCircle',
    color='#10B981',

    input_types=['array'],
    output_types=['array'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=30000,
    concurrent_safe=True,

    params_schema=compose(
        field('items', type='array', label='Items',
              description='Array of records to validate.',
              required=True,
              group=FieldGroup.BASIC),
        field('rules', type='object', label='Validation Rules',
              description='Field rules: {"field_name": ["required", "is_url"], "price": ["required", "is_number"]}. Available: required, not_empty, is_number, is_url, is_email, min_length:N, max_length:N, matches:REGEX, min_value:N, max_value:N',
              required=True,
              group=FieldGroup.BASIC),
        field('mode', type='select', label='Mode',
              description='What to do with invalid records',
              default='filter',
              options=[
                  {'value': 'filter', 'label': 'Filter (return only valid)'},
                  {'value': 'flag', 'label': 'Flag (add _valid and _errors fields)'},
                  {'value': 'strict', 'label': 'Strict (fail if any invalid)'},
              ],
              group=FieldGroup.OPTIONS),
        field('drop_fields', type='array', label='Drop Fields',
              description='Fields to remove from output (e.g., ["__index", "html"])',
              required=False, default=[],
              items={'type': 'string'},
              group=FieldGroup.OPTIONS),
    ),
    output_schema={
        'items':      {'type': 'array',   'description': 'Valid records (filter/flag mode) or all records (flag mode)'},
        'invalid':    {'type': 'array',   'description': 'Invalid records with error details (filter mode only)'},
        'total_in':   {'type': 'integer', 'description': 'Input record count'},
        'valid_count': {'type': 'integer', 'description': 'Number of valid records'},
        'invalid_count': {'type': 'integer', 'description': 'Number of invalid records'},
    },
    examples=[
        {
            'name': 'Require URL and title',
            'params': {
                'items': [],
                'rules': {'url': ['required', 'is_url'], 'title': ['required', 'min_length:3']},
            }
        },
        {
            'name': 'Flag mode with cleanup',
            'params': {
                'items': [],
                'rules': {'price': ['required', 'is_number']},
                'mode': 'flag',
                'drop_fields': ['__index', 'html'],
            }
        },
    ],
    author='Flyto Team', license='MIT',
    required_permissions=[],
)
class DataValidateRecordsModule(BaseModule):
    """Validate and filter extracted records."""

    module_name = "Validate Records"
    module_description = "Validate records against field rules"

    def validate_params(self) -> None:
        self.items = self.params.get('items', [])
        self.rules = self.params.get('rules', {})
        self.mode = self.params.get('mode', 'filter')
        self.drop_fields = self.params.get('drop_fields', [])

        if not isinstance(self.items, list):
            raise ValueError("items must be an array")
        if not isinstance(self.rules, dict):
            raise ValueError("rules must be an object")

    async def execute(self) -> Dict[str, Any]:
        valid_items = []
        invalid_items = []

        for record in self.items:
            if not isinstance(record, dict):
                invalid_items.append({'_record': record, '_errors': ['not a dict']})
                continue

            errors = self._validate_record(record)

            # Drop unwanted fields
            if self.drop_fields:
                record = {k: v for k, v in record.items() if k not in self.drop_fields}

            if errors:
                if self.mode == 'flag':
                    record['_valid'] = False
                    record['_errors'] = errors
                    valid_items.append(record)
                else:
                    invalid_items.append({**record, '_errors': errors})
            else:
                if self.mode == 'flag':
                    record['_valid'] = True
                valid_items.append(record)

        if self.mode == 'strict' and invalid_items:
            raise ValueError(
                f"{len(invalid_items)} invalid records found. "
                f"First error: {invalid_items[0].get('_errors', [])}"
            )

        total_in = len(self.items)
        logger.info(
            f"Validate: {total_in} records → {len(valid_items)} valid, "
            f"{len(invalid_items)} invalid"
        )

        return {
            'status': 'success',
            'items': valid_items,
            'invalid': invalid_items,
            'total_in': total_in,
            'valid_count': len(valid_items),
            'invalid_count': len(invalid_items),
        }

    def _validate_record(self, record: dict) -> List[str]:
        """Validate a single record against all rules. Returns list of error strings."""
        errors = []
        for field_name, rule_list in self.rules.items():
            value = record.get(field_name)
            if isinstance(rule_list, str):
                rule_list = [rule_list]

            for rule in rule_list:
                # Parse rule:arg format (e.g., "min_length:3")
                rule_name = rule
                rule_arg = None
                if ':' in rule:
                    rule_name, rule_arg = rule.split(':', 1)

                validator = _VALIDATORS.get(rule_name)
                if not validator:
                    errors.append(f"{field_name}: unknown rule '{rule_name}'")
                    continue

                if not validator(value, rule_arg):
                    errors.append(f"{field_name}: failed '{rule}'")
        return errors
