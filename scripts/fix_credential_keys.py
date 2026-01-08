#!/usr/bin/env python3
"""
Fix C003 warnings by adding credential_keys to modules with requires_credentials=True.
"""
import re
import os
from pathlib import Path

# Mapping of module patterns to their credential keys
CREDENTIAL_MAPPING = {
    # AI APIs
    'api.openai': ['OPENAI_API_KEY'],
    'api.anthropic': ['ANTHROPIC_API_KEY'],
    'api.google_gemini': ['GOOGLE_API_KEY'],

    # Agent modules (use LLM keys)
    'agent.': ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY'],

    # GitHub
    'api.github': ['GITHUB_TOKEN'],

    # Google services
    'api.google_sheets': ['GOOGLE_CREDENTIALS'],
    'core.api.google_search': ['GOOGLE_API_KEY', 'GOOGLE_CSE_ID'],
    'core.api.serpapi': ['SERPAPI_KEY'],

    # Notion
    'api.notion': ['NOTION_TOKEN'],

    # HTTP (generic)
    'api.http': ['API_KEY'],

    # Cloud storage
    'cloud.aws_s3': ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'],
    'cloud.azure': ['AZURE_STORAGE_CONNECTION_STRING'],
    'cloud.gcs': ['GOOGLE_CLOUD_CREDENTIALS'],

    # Communication
    'communication.twilio': ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN'],

    # Database
    'db.mongodb': ['MONGODB_URI'],
    'db.mysql': ['MYSQL_HOST', 'MYSQL_USER', 'MYSQL_PASSWORD'],
    'db.postgresql': ['POSTGRESQL_HOST', 'POSTGRESQL_USER', 'POSTGRESQL_PASSWORD'],
    'db.redis': ['REDIS_URL'],

    # Integrations
    'integration.jira': ['JIRA_TOKEN', 'JIRA_EMAIL'],
    'integration.salesforce': ['SALESFORCE_CLIENT_ID', 'SALESFORCE_CLIENT_SECRET'],
    'integration.slack': ['SLACK_TOKEN'],

    # Notifications
    'notification.discord': ['DISCORD_WEBHOOK_URL'],
    'notification.email': ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD'],
    'notification.slack': ['SLACK_TOKEN'],
    'notification.telegram': ['TELEGRAM_BOT_TOKEN'],

    # Payment
    'payment.stripe': ['STRIPE_API_KEY'],

    # Productivity
    'productivity.airtable': ['AIRTABLE_API_KEY'],
}


def get_credential_keys(module_id: str) -> list:
    """Get credential keys for a module based on its ID."""
    for pattern, keys in CREDENTIAL_MAPPING.items():
        if module_id.startswith(pattern):
            return keys
    return ['API_KEY']  # Default fallback


def add_credential_keys_to_file(file_path: str) -> int:
    """Add credential_keys to @register_module decorators in a file."""
    with open(file_path, 'r') as f:
        content = f.read()

    original = content
    changes = 0

    # Find all @register_module decorators with requires_credentials=True
    # Pattern: @register_module( ... requires_credentials=True ... )
    pattern = r'@register_module\((.*?)\)\s*(?:class|async def|def)'

    for match in re.finditer(pattern, content, re.DOTALL):
        decorator_content = match.group(1)

        # Check if it has requires_credentials=True
        if 'requires_credentials=True' not in decorator_content:
            continue

        # Check if it already has credential_keys
        if 'credential_keys=' in decorator_content:
            continue

        # Find module_id
        module_id_match = re.search(r"module_id=['\"]([^'\"]+)['\"]", decorator_content)
        if not module_id_match:
            continue

        module_id = module_id_match.group(1)
        credential_keys = get_credential_keys(module_id)

        # Add credential_keys after requires_credentials=True
        old_text = 'requires_credentials=True'
        new_text = f"requires_credentials=True,\n    credential_keys={credential_keys!r}"

        # Replace only in this decorator
        new_decorator = decorator_content.replace(old_text, new_text)
        content = content.replace(decorator_content, new_decorator)
        changes += 1
        print(f"  Fixed: {module_id} -> {credential_keys}")

    if content != original:
        with open(file_path, 'w') as f:
            f.write(content)

    return changes


def main():
    """Main entry point."""
    base_dir = Path(__file__).parent.parent / 'src' / 'core' / 'modules' / 'atomic'

    total_changes = 0

    for py_file in base_dir.rglob('*.py'):
        if '__pycache__' in str(py_file):
            continue

        changes = add_credential_keys_to_file(str(py_file))
        if changes > 0:
            total_changes += changes

    # Also check third_party modules
    third_party_dir = Path(__file__).parent.parent / 'src' / 'core' / 'modules' / 'third_party'
    if third_party_dir.exists():
        for py_file in third_party_dir.rglob('*.py'):
            if '__pycache__' in str(py_file):
                continue

            changes = add_credential_keys_to_file(str(py_file))
            if changes > 0:
                total_changes += changes

    print(f"\nTotal changes: {total_changes}")


if __name__ == '__main__':
    main()
