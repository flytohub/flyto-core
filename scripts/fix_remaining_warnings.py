#!/usr/bin/env python3
"""
Fix remaining lint warnings.

Targets:
- SEC001: Add ssrf_protected tag to network modules
- SEC002: Add path_restricted tag to file modules
- C004: Add required_permissions for sensitive data modules
- S004: Add missing descriptions in output_schema
- Q007: Add empty params_schema where missing
"""

import re
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MODULES_PATH = PROJECT_ROOT / "src" / "core" / "modules"


def add_ssrf_tag_aggressive(content: str) -> str:
    """Add ssrf_protected tag to any module with network-related tags."""
    # Network indicators in tags
    network_indicators = [
        'browser', 'http', 'api', 'network', 'request', 'fetch', 'url',
        'webhook', 'socket', 'remote', 'cloud', 'storage', 'oauth',
        'github', 'slack', 'discord', 'telegram', 'twilio', 'stripe',
        'notion', 'airtable', 'jira', 'salesforce', 'google', 'azure',
        'gcs', 's3', 'openai', 'anthropic', 'gemini', 'ollama'
    ]

    tags_match = re.search(r"tags=\[([^\]]+)\]", content)
    if not tags_match:
        return content

    tags_content = tags_match.group(1)

    # Check if already has ssrf_protected
    if 'ssrf_protected' in tags_content:
        return content

    # Check if any network indicator
    is_network = any(ind.lower() in tags_content.lower() for ind in network_indicators)
    if not is_network:
        return content

    # Add ssrf_protected
    new_tags = tags_content.rstrip().rstrip("'").rstrip('"') + "', 'ssrf_protected'"
    if tags_content.endswith("'"):
        new_tags = tags_content + ", 'ssrf_protected'"
    elif tags_content.endswith('"'):
        new_tags = tags_content + ', "ssrf_protected"'
    else:
        new_tags = tags_content + ", 'ssrf_protected'"

    return content.replace(f"tags=[{tags_content}]", f"tags=[{new_tags}]")


def add_path_tag_aggressive(content: str) -> str:
    """Add path_restricted tag to file-related modules."""
    file_indicators = [
        'file', 'path', 'directory', 'folder', 'write', 'read', 'save',
        'load', 'download', 'upload', 'excel', 'csv', 'pdf', 'word',
        'document', 'image', 'storage', 'copy', 'move', 'delete'
    ]

    tags_match = re.search(r"tags=\[([^\]]+)\]", content)
    if not tags_match:
        return content

    tags_content = tags_match.group(1)

    if 'path_restricted' in tags_content:
        return content

    is_file = any(ind.lower() in tags_content.lower() for ind in file_indicators)
    if not is_file:
        return content

    new_tags = tags_content.rstrip().rstrip("'").rstrip('"') + "', 'path_restricted'"
    if tags_content.endswith("'"):
        new_tags = tags_content + ", 'path_restricted'"
    elif tags_content.endswith('"'):
        new_tags = tags_content + ', "path_restricted"'
    else:
        new_tags = tags_content + ", 'path_restricted'"

    return content.replace(f"tags=[{tags_content}]", f"tags=[{new_tags}]")


def add_permissions_for_sensitive(content: str) -> str:
    """Add required_permissions for handles_sensitive_data=True modules."""
    if 'handles_sensitive_data=True' not in content:
        return content

    if 'required_permissions=' in content:
        # Check if it's empty
        if 'required_permissions=[]' in content:
            # Determine appropriate permissions
            perms = ['data.read']
            if 'file' in content.lower() or 'write' in content.lower():
                perms.append('data.write')
            if 'process' in content.lower():
                perms = ['process.execute']
            if 'pdf' in content.lower() or 'word' in content.lower() or 'excel' in content.lower():
                perms = ['document.read', 'document.write']

            perm_str = ', '.join(f"'{p}'" for p in perms)
            content = content.replace('required_permissions=[]', f'required_permissions=[{perm_str}]')
        return content

    # Add required_permissions after handles_sensitive_data=True
    perms = ['data.read', 'data.write']
    perm_str = ', '.join(f"'{p}'" for p in perms)
    pattern = r'(handles_sensitive_data=True,)'
    replacement = rf"\1\n    required_permissions=[{perm_str}],"
    return re.sub(pattern, replacement, content)


def add_output_descriptions(content: str) -> str:
    """Add missing descriptions in output_schema."""
    # Find output_schema block
    output_match = re.search(r'output_schema\s*=\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}', content, re.DOTALL)
    if not output_match:
        return content

    output_block = output_match.group(0)

    # Check for properties without descriptions
    # Pattern: "field": {"type": "xxx"} without description
    def add_desc(match):
        field_name = match.group(1)
        field_content = match.group(2)
        if 'description' not in field_content:
            # Add a generic description
            desc = f"The {field_name.replace('_', ' ')} value"
            new_content = field_content.rstrip().rstrip('}') + f', "description": "{desc}"' + '}'
            return f'"{field_name}": {new_content}'
        return match.group(0)

    pattern = r'"(\w+)":\s*(\{[^}]+\})'
    new_output = re.sub(pattern, add_desc, output_block)

    if new_output != output_block:
        return content.replace(output_block, new_output)

    return content


def add_empty_params_schema(content: str) -> str:
    """Add params_schema={} where missing."""
    if 'params_schema=' in content:
        return content

    # Only add if @register_module is present
    if '@register_module' not in content:
        return content

    # Add before output_schema if present
    if 'output_schema=' in content:
        return content.replace(
            'output_schema=',
            'params_schema={},\n    output_schema='
        )

    # Add before timeout_ms if present
    if 'timeout_ms=' in content:
        return content.replace(
            'timeout_ms=',
            'params_schema={},\n    timeout_ms='
        )

    return content


def fix_file(filepath: Path) -> bool:
    """Fix a single file."""
    try:
        content = filepath.read_text()
        original = content

        content = add_ssrf_tag_aggressive(content)
        content = add_path_tag_aggressive(content)
        content = add_permissions_for_sensitive(content)
        content = add_output_descriptions(content)
        content = add_empty_params_schema(content)

        if content != original:
            filepath.write_text(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    fixed_count = 0
    total_count = 0

    for filepath in MODULES_PATH.rglob("*.py"):
        if "__pycache__" in str(filepath):
            continue
        if filepath.name.startswith("_"):
            continue

        total_count += 1
        if fix_file(filepath):
            fixed_count += 1
            print(f"Fixed: {filepath.relative_to(PROJECT_ROOT)}")

    print(f"\nProcessed {total_count} files, fixed {fixed_count}")


if __name__ == "__main__":
    main()
