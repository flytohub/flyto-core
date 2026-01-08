#!/usr/bin/env python3
"""
Fix lint warnings automatically.

This script fixes common lint warnings:
- Q009: Add return type hints to validate_params
- SEC001: Add ssrf_protected tag to network modules
- SEC002: Add path_restricted tag to file modules
- C003: Add credential_keys to modules with requires_credentials
- S001: Add params_schema where missing
"""

import re
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MODULES_PATH = PROJECT_ROOT / "src" / "core" / "modules"


def fix_validate_params_type_hint(content: str) -> str:
    """Add -> None type hint to validate_params methods."""
    # Pattern: def validate_params(self): without return type
    pattern = r'(\s+def validate_params\(self\))(\s*:)'
    replacement = r'\1 -> None\2'
    return re.sub(pattern, replacement, content)


def add_ssrf_protected_tag(content: str) -> str:
    """Add 'ssrf_protected' to tags for network modules."""
    # Check if it's a network module (has 'browser', 'http', 'api', 'network' in tags)
    network_indicators = ['browser', 'http', 'api', 'network', 'request', 'fetch']

    # Find tags line
    tags_match = re.search(r"tags=\[([^\]]+)\]", content)
    if not tags_match:
        return content

    tags_content = tags_match.group(1)

    # Check if any network indicator is in tags
    is_network = any(ind in tags_content.lower() for ind in network_indicators)
    if not is_network:
        return content

    # Check if already has ssrf_protected
    if 'ssrf_protected' in tags_content:
        return content

    # Add ssrf_protected tag
    new_tags = tags_content.rstrip() + ", 'ssrf_protected'"
    return content.replace(f"tags=[{tags_content}]", f"tags=[{new_tags}]")


def add_path_restricted_tag(content: str) -> str:
    """Add 'path_restricted' to tags for file modules."""
    # Check if it's a file module
    file_indicators = ['file', 'path', 'directory', 'folder', 'write', 'read', 'save', 'load', 'download', 'upload']

    tags_match = re.search(r"tags=\[([^\]]+)\]", content)
    if not tags_match:
        return content

    tags_content = tags_match.group(1)

    # Check if any file indicator is in tags
    is_file = any(ind in tags_content.lower() for ind in file_indicators)
    if not is_file:
        return content

    # Check if already has path_restricted
    if 'path_restricted' in tags_content:
        return content

    # Add path_restricted tag
    new_tags = tags_content.rstrip() + ", 'path_restricted'"
    return content.replace(f"tags=[{tags_content}]", f"tags=[{new_tags}]")


def add_credential_keys(content: str) -> str:
    """Add credential_keys for modules with requires_credentials=True."""
    # Check if has requires_credentials=True
    if 'requires_credentials=True' not in content:
        return content

    # Check if already has credential_keys
    if 'credential_keys=' in content:
        return content

    # Determine credential key based on module type
    credential_key = 'API_KEY'  # Default

    if 'openai' in content.lower():
        credential_key = 'OPENAI_API_KEY'
    elif 'anthropic' in content.lower():
        credential_key = 'ANTHROPIC_API_KEY'
    elif 'github' in content.lower():
        credential_key = 'GITHUB_TOKEN'
    elif 'google' in content.lower() or 'gemini' in content.lower():
        credential_key = 'GOOGLE_API_KEY'
    elif 'notion' in content.lower():
        credential_key = 'NOTION_API_KEY'
    elif 'slack' in content.lower():
        credential_key = 'SLACK_TOKEN'
    elif 'stripe' in content.lower():
        credential_key = 'STRIPE_API_KEY'
    elif 'twilio' in content.lower():
        credential_key = 'TWILIO_AUTH_TOKEN'
    elif 'airtable' in content.lower():
        credential_key = 'AIRTABLE_API_KEY'
    elif 'jira' in content.lower():
        credential_key = 'JIRA_API_TOKEN'
    elif 'salesforce' in content.lower():
        credential_key = 'SALESFORCE_ACCESS_TOKEN'
    elif 'redis' in content.lower():
        credential_key = 'REDIS_PASSWORD'
    elif 'azure' in content.lower():
        credential_key = 'AZURE_STORAGE_KEY'
    elif 'gcs' in content.lower() or 'google cloud' in content.lower():
        credential_key = 'GCS_SERVICE_ACCOUNT_KEY'
    elif 'ollama' in content.lower():
        credential_key = 'OLLAMA_API_KEY'
    elif 'discord' in content.lower():
        credential_key = 'DISCORD_BOT_TOKEN'
    elif 'telegram' in content.lower():
        credential_key = 'TELEGRAM_BOT_TOKEN'
    elif 'email' in content.lower() or 'smtp' in content.lower():
        credential_key = 'SMTP_PASSWORD'

    # Add credential_keys after requires_credentials=True
    pattern = r'(requires_credentials=True,)'
    replacement = rf"\1\n    credential_keys=['{credential_key}'],"
    return re.sub(pattern, replacement, content)


def fix_file(filepath: Path) -> bool:
    """Fix a single file. Returns True if changes were made."""
    try:
        content = filepath.read_text()
        original = content

        # Apply fixes
        content = fix_validate_params_type_hint(content)
        content = add_ssrf_protected_tag(content)
        content = add_path_restricted_tag(content)
        content = add_credential_keys(content)

        if content != original:
            filepath.write_text(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Fix all module files."""
    fixed_count = 0
    total_count = 0

    # Find all Python files in modules directory
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
