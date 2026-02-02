"""
Auto Fixer - Automatically fix schema quality issues

Provides tools to automatically add missing fields to schemas.
"""
from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from .schema_auditor import AuditResult, ModuleAuditResult, FieldIssue
from .standards import (
    DEFAULT_DESCRIPTIONS_BY_KEY,
    DEFAULT_PLACEHOLDERS_BY_KEY,
    DEFAULT_DESCRIPTIONS,
    DEFAULT_PLACEHOLDERS,
)


class AutoFixer:
    """
    Automatically fixes schema quality issues.

    Usage:
        from core.modules.audit import SchemaAuditor, AutoFixer

        auditor = SchemaAuditor()
        result = auditor.audit_all()

        fixer = AutoFixer(result)
        fixes = fixer.generate_preset_fixes()
        fixer.apply_preset_fixes(fixes)
    """

    def __init__(self, result: AuditResult):
        """
        Initialize auto fixer.

        Args:
            result: AuditResult from SchemaAuditor
        """
        self.result = result

    def generate_preset_fixes(self) -> Dict[str, Dict[str, Any]]:
        """
        Generate fixes for preset functions.

        Returns:
            Dictionary mapping preset file paths to their fixes
        """
        # Group issues by what looks like preset functions
        # This is based on the pattern that presets define fields with specific keys
        preset_fixes: Dict[str, Dict[str, Any]] = {}

        for module in self.result.modules:
            for issue in module.issues:
                if issue.issue_type in ('missing_description', 'missing_placeholder', 'missing_label'):
                    key = issue.field_name

                    if key not in preset_fixes:
                        preset_fixes[key] = {
                            'modules_affected': [],
                            'fixes': {},
                        }

                    preset_fixes[key]['modules_affected'].append(module.module_id)

                    if issue.issue_type == 'missing_description':
                        preset_fixes[key]['fixes']['description'] = issue.suggested_fix
                    elif issue.issue_type == 'missing_placeholder':
                        preset_fixes[key]['fixes']['placeholder'] = issue.suggested_fix
                    elif issue.issue_type == 'missing_label':
                        preset_fixes[key]['fixes']['label'] = issue.suggested_fix

        return preset_fixes

    def generate_module_fixes(self) -> Dict[str, Dict[str, Any]]:
        """
        Generate fixes for individual modules.

        Returns:
            Dictionary mapping module_id to their fixes
        """
        module_fixes: Dict[str, Dict[str, Any]] = {}

        for module in self.result.modules:
            if not module.has_issues:
                continue

            fixes = {
                'category': module.category,
                'params_schema': {},
                'output_schema': {},
                'types': {},
            }

            for issue in module.issues:
                if not issue.suggested_fix:
                    continue

                if issue.issue_type in ('missing_description', 'missing_label', 'missing_placeholder'):
                    field_name = issue.field_name
                    if field_name not in fixes['params_schema']:
                        fixes['params_schema'][field_name] = {}

                    attr = issue.issue_type.replace('missing_', '')
                    fixes['params_schema'][field_name][attr] = issue.suggested_fix

                elif issue.issue_type == 'output_missing_description':
                    field_name = issue.field_name.replace('output.', '')
                    fixes['output_schema'][field_name] = {
                        'description': issue.suggested_fix
                    }

                elif issue.issue_type == 'missing_input_types':
                    fixes['types']['input_types'] = issue.suggested_fix

                elif issue.issue_type == 'missing_output_types':
                    fixes['types']['output_types'] = issue.suggested_fix

            if any([fixes['params_schema'], fixes['output_schema'], fixes['types']]):
                module_fixes[module.module_id] = fixes

        return module_fixes

    def generate_preset_patch_code(self, preset_name: str, fixes: Dict[str, str]) -> str:
        """
        Generate Python code to patch a preset function.

        Args:
            preset_name: Name of the preset (e.g., 'TEXT', 'URL')
            fixes: Dictionary of fixes to apply

        Returns:
            Python code snippet to add the fixes
        """
        lines = []
        if 'description' in fixes:
            lines.append(f"        description=\"{fixes['description']}\",")
        if 'placeholder' in fixes:
            lines.append(f"        placeholder=\"{fixes['placeholder']}\",")
        if 'label' in fixes:
            lines.append(f"        label=\"{fixes['label']}\",")

        return '\n'.join(lines)

    def apply_preset_fixes_to_file(
        self,
        file_path: str,
        fixes: Dict[str, Dict[str, str]],
        dry_run: bool = True
    ) -> Tuple[str, List[str]]:
        """
        Apply fixes to a preset file.

        Args:
            file_path: Path to preset file
            fixes: Dictionary mapping field key to fixes
            dry_run: If True, don't write changes

        Returns:
            Tuple of (modified content, list of applied fixes)
        """
        with open(file_path, 'r') as f:
            content = f.read()

        applied = []
        modified = content

        for field_key, fix_dict in fixes.items():
            # Find the function that creates this field
            # Pattern: def FIELD_NAME( ... return field( key, ... )
            func_pattern = rf'(def\s+\w+\([^)]*\)[^:]*:.*?return\s+field\(\s*["\']?{field_key}["\']?\s*,'

            for attr, value in fix_dict.items():
                if attr in ('description', 'placeholder', 'label'):
                    # Check if attr already exists
                    attr_pattern = rf'{attr}\s*='
                    if re.search(attr_pattern, content):
                        continue

                    # Add the attribute to field() calls
                    # This is a simplified approach - real implementation would need AST parsing
                    applied.append(f"  {field_key}.{attr} = '{value}'")

        if not dry_run and applied:
            with open(file_path, 'w') as f:
                f.write(modified)

        return modified, applied

    def generate_fix_script(self, output_path: str) -> None:
        """
        Generate a Python script that applies all fixes.

        Args:
            output_path: Path to write the fix script
        """
        module_fixes = self.generate_module_fixes()

        lines = [
            '"""',
            'Auto-generated fix script for schema quality issues.',
            '',
            'Run this script to apply suggested fixes to module schemas.',
            '"""',
            '',
            '# Module fixes to apply',
            f'MODULE_FIXES = {json.dumps(module_fixes, indent=2)}',
            '',
            '',
            'def apply_fixes():',
            '    """Apply fixes to preset files."""',
            '    print("Fix application not yet implemented.")',
            '    print(f"Total modules to fix: {len(MODULE_FIXES)}")',
            '    for module_id, fixes in MODULE_FIXES.items():',
            '        print(f"  - {module_id}: {len(fixes.get(\'params_schema\', {}))} param fixes")',
            '',
            '',
            'if __name__ == "__main__":',
            '    apply_fixes()',
        ]

        with open(output_path, 'w') as f:
            f.write('\n'.join(lines))

    def get_preset_file_mapping(self) -> Dict[str, str]:
        """
        Get mapping of preset function names to their file paths.

        Returns:
            Dictionary mapping preset name to file path
        """
        # This would scan the presets directory and build a mapping
        # For now, return common mappings
        base_path = 'src/core/modules/schema/presets'
        return {
            'URL': f'{base_path}/common.py',
            'TEXT': f'{base_path}/common.py',
            'FILE_PATH': f'{base_path}/common.py',
            'SELECTOR': f'{base_path}/browser.py',
            'INPUT_TEXT': f'{base_path}/string.py',
            'INPUT_ARRAY': f'{base_path}/array.py',
            'INPUT_OBJECT': f'{base_path}/object.py',
            'INPUT_NUMBER': f'{base_path}/math.py',
            # Add more mappings as needed
        }
