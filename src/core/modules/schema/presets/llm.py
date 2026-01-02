"""
LLM Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from .. import validators


def LLM_PROMPT(
    *,
    key: str = "prompt",
    required: bool = True,
    label: str = "Prompt",
    label_key: str = "schema.field.llm_prompt",
    placeholder: str = "Analyze this code and suggest improvements...",
) -> Dict[str, Dict[str, Any]]:
    """LLM prompt input field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="multiline",
    )


def SYSTEM_PROMPT(
    *,
    key: str = "system_prompt",
    required: bool = False,
    label: str = "System Prompt",
    label_key: str = "schema.field.system_prompt",
    placeholder: str = "You are an expert code reviewer...",
) -> Dict[str, Dict[str, Any]]:
    """System prompt to set LLM context and behavior."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="multiline",
    )


def LLM_CONTEXT(
    *,
    key: str = "context",
    label: str = "Context Data",
    label_key: str = "schema.field.llm_context",
) -> Dict[str, Dict[str, Any]]:
    """Additional context data to include in prompt."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Additional context data to include',
    )


def CONVERSATION_MESSAGES(
    *,
    key: str = "messages",
    label: str = "Conversation History",
    label_key: str = "schema.field.conversation_messages",
) -> Dict[str, Dict[str, Any]]:
    """Previous messages for multi-turn conversation."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        description='Previous messages for multi-turn conversation',
    )


def LLM_PROVIDER(
    *,
    key: str = "provider",
    default: str = "openai",
    label: str = "Provider",
    label_key: str = "schema.field.llm_provider",
) -> Dict[str, Dict[str, Any]]:
    """LLM provider selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["openai", "anthropic", "ollama"],
    )


def LLM_MODEL(
    *,
    key: str = "model",
    default: str = "gpt-4o",
    label: str = "Model",
    label_key: str = "schema.field.llm_model",
) -> Dict[str, Dict[str, Any]]:
    """LLM model selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Specific model to use',
        examples=[
            'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo',
            'claude-3-5-sonnet-20241022', 'claude-3-opus-20240229',
            'llama2', 'codellama', 'mistral'
        ],
    )


def TEMPERATURE(
    *,
    key: str = "temperature",
    default: float = 0.7,
    min_val: float = 0,
    max_val: float = 2,
    label: str = "Temperature",
    label_key: str = "schema.field.temperature",
) -> Dict[str, Dict[str, Any]]:
    """LLM creativity level (0=deterministic, 1=creative)."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        step=0.1,
        description='Creativity level (0=deterministic, 1=creative)',
    )


def MAX_TOKENS(
    *,
    key: str = "max_tokens",
    default: int = 2000,
    label: str = "Max Tokens",
    label_key: str = "schema.field.max_tokens",
) -> Dict[str, Dict[str, Any]]:
    """Maximum tokens in LLM response."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=1,
        max=128000,
        description='Maximum tokens in response',
    )


def LLM_RESPONSE_FORMAT(
    *,
    key: str = "response_format",
    default: str = "text",
    label: str = "Response Format",
    label_key: str = "schema.field.llm_response_format",
) -> Dict[str, Dict[str, Any]]:
    """Expected LLM response format."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["text", "json", "code", "markdown"],
    )


def LLM_API_KEY(
    *,
    key: str = "api_key",
    label: str = "API Key",
    label_key: str = "schema.field.llm_api_key",
) -> Dict[str, Dict[str, Any]]:
    """LLM API key (defaults to provider env var)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        format="password",
        description='API key (defaults to provider env var)',
        advanced=True,
    )


def LLM_BASE_URL(
    *,
    key: str = "base_url",
    label: str = "Base URL",
    label_key: str = "schema.field.llm_base_url",
    placeholder: str = "http://localhost:11434/v1",
) -> Dict[str, Dict[str, Any]]:
    """Custom API base URL (for Ollama or proxies)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=False,
        advanced=True,
        description='Custom API base URL (for Ollama or proxies)',
    )


def CODE_ISSUES(
    *,
    key: str = "issues",
    required: bool = True,
    label: str = "Issues",
    label_key: str = "schema.field.code_issues",
) -> Dict[str, Dict[str, Any]]:
    """List of issues to fix (from ui.evaluate, test results, etc.)."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='List of issues to fix (from ui.evaluate, test results, etc.)',
    )


def SOURCE_FILES(
    *,
    key: str = "source_files",
    required: bool = True,
    label: str = "Source Files",
    label_key: str = "schema.field.source_files",
) -> Dict[str, Dict[str, Any]]:
    """Files to analyze and potentially fix."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Files to analyze and potentially fix',
    )


def FIX_MODE(
    *,
    key: str = "fix_mode",
    default: str = "suggest",
    label: str = "Fix Mode",
    label_key: str = "schema.field.fix_mode",
) -> Dict[str, Dict[str, Any]]:
    """How to apply code fixes."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["suggest", "apply", "dry_run"],
        options=[
            {"value": "suggest", "label": "Suggest Only - Return fixes without applying"},
            {"value": "apply", "label": "Apply - Write fixes to files"},
            {"value": "dry_run", "label": "Dry Run - Show what would change"},
        ],
    )


def CREATE_BACKUP(
    *,
    key: str = "backup",
    default: bool = True,
    label: str = "Create Backup",
    label_key: str = "schema.field.create_backup",
) -> Dict[str, Dict[str, Any]]:
    """Create .bak backup before modifying files."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Create .bak backup before modifying files',
    )

