"""
Core Constants - Centralized configuration values

This module contains all constants and default values used throughout the flyto-core system.
All magic numbers, default URLs, and configuration values should be defined here.
"""
from typing import Dict, Any


# =============================================================================
# Execution Defaults
# =============================================================================

DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_DELAY_MS: int = 1000
DEFAULT_TIMEOUT_SECONDS: int = 30
DEFAULT_TIMEOUT_MS: int = 30000
EXPONENTIAL_BACKOFF_BASE: int = 2
MAX_LOG_RESULT_LENGTH: int = 200
DEFAULT_MAX_TREE_DEPTH: int = 5


# =============================================================================
# Browser Defaults
# =============================================================================

DEFAULT_BROWSER_TIMEOUT: int = 10
DEFAULT_BROWSER_TIMEOUT_MS: int = 30000
DEFAULT_NAVIGATION_TIMEOUT_MS: int = 30000
DEFAULT_BROWSER_MAX_RETRIES: int = 2
DEFAULT_HEADLESS: bool = True
DEFAULT_VIEWPORT_WIDTH: int = 1920
DEFAULT_VIEWPORT_HEIGHT: int = 1080
DEFAULT_USER_AGENT: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# =============================================================================
# LLM Defaults
# =============================================================================

DEFAULT_LLM_MAX_TOKENS: int = 2000
DEFAULT_LLM_NUM_PREDICT: int = 2000
OLLAMA_DEFAULT_URL: str = "http://localhost:11434"
OLLAMA_EMBEDDINGS_ENDPOINT: str = f"{OLLAMA_DEFAULT_URL}/api/embeddings"
OLLAMA_GENERATE_ENDPOINT: str = f"{OLLAMA_DEFAULT_URL}/api/generate"


# =============================================================================
# Validation Constants
# =============================================================================

MIN_DESCRIPTION_LENGTH: int = 10
MAX_DESCRIPTION_LENGTH: int = 200
MIN_LABEL_WORDS: int = 2
MAX_LABEL_WORDS: int = 5
MIN_TAGS_COUNT: int = 2
MAX_TAGS_COUNT: int = 5
MAX_TIMEOUT_LIMIT: int = 3600
MAX_RETRIES_LIMIT: int = 10


# =============================================================================
# API Configuration
# =============================================================================

class APIEndpoints:
    """Centralized API endpoint configuration"""

    # Stripe
    STRIPE_BASE_URL: str = "https://api.stripe.com/v1"
    STRIPE_PAYMENT_INTENTS: str = f"{STRIPE_BASE_URL}/payment_intents"
    STRIPE_CUSTOMERS: str = f"{STRIPE_BASE_URL}/customers"
    STRIPE_CHARGES: str = f"{STRIPE_BASE_URL}/charges"

    # GitHub
    GITHUB_BASE_URL: str = "https://api.github.com"
    GITHUB_API_ACCEPT_HEADER: str = "application/vnd.github.v3+json"

    @classmethod
    def github_repo(cls, owner: str, repo: str) -> str:
        return f"{cls.GITHUB_BASE_URL}/repos/{owner}/{repo}"

    @classmethod
    def github_issues(cls, owner: str, repo: str) -> str:
        return f"{cls.github_repo(owner, repo)}/issues"

    # Google APIs
    GOOGLE_SEARCH_URL: str = "https://www.googleapis.com/customsearch/v1"
    GOOGLE_GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1"

    @classmethod
    def google_gemini_generate(cls, model: str, api_key: str) -> str:
        return f"{cls.GOOGLE_GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"

    # SerpAPI
    SERPAPI_BASE_URL: str = "https://serpapi.com/search"

    # Airtable
    AIRTABLE_BASE_URL: str = "https://api.airtable.com/v0"

    @classmethod
    def airtable_table(cls, base_id: str, table_name: str) -> str:
        import urllib.parse
        return f"{cls.AIRTABLE_BASE_URL}/{base_id}/{urllib.parse.quote(table_name)}"

    # Notion
    NOTION_BASE_URL: str = "https://api.notion.com/v1"
    NOTION_API_VERSION: str = "2022-06-28"

    @classmethod
    def notion_pages(cls) -> str:
        return f"{cls.NOTION_BASE_URL}/pages"

    @classmethod
    def notion_database_query(cls, database_id: str) -> str:
        return f"{cls.NOTION_BASE_URL}/databases/{database_id}/query"

    # Anthropic
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"
    ANTHROPIC_MESSAGES_URL: str = f"{ANTHROPIC_BASE_URL}/messages"
    ANTHROPIC_API_VERSION: str = "2023-06-01"
    DEFAULT_ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"

    # Google Gemini
    DEFAULT_GEMINI_MODEL: str = "gemini-1.5-pro"

    # Twilio
    TWILIO_BASE_URL: str = "https://api.twilio.com/2010-04-01"

    @classmethod
    def twilio_messages(cls, account_sid: str) -> str:
        return f"{cls.TWILIO_BASE_URL}/Accounts/{account_sid}/Messages.json"

    @classmethod
    def twilio_calls(cls, account_sid: str) -> str:
        return f"{cls.TWILIO_BASE_URL}/Accounts/{account_sid}/Calls.json"

    # OpenAI
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_CHAT_COMPLETIONS: str = f"{OPENAI_BASE_URL}/chat/completions"
    OPENAI_EMBEDDINGS: str = f"{OPENAI_BASE_URL}/embeddings"
    DEFAULT_OPENAI_MODEL: str = "gpt-4-turbo-preview"

    # Database Defaults
    MYSQL_DEFAULT_PORT: int = 3306
    POSTGRESQL_DEFAULT_PORT: int = 5432
    MONGODB_DEFAULT_PORT: int = 27017
    REDIS_DEFAULT_PORT: int = 6379


# =============================================================================
# API Limits
# =============================================================================

GOOGLE_API_MAX_RESULTS: int = 10
GOOGLE_API_MIN_RESULTS: int = 1
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100


# =============================================================================
# Environment Variable Names
# =============================================================================

class EnvVars:
    """Environment variable names"""

    # API Keys
    GITHUB_TOKEN: str = "GITHUB_TOKEN"
    GOOGLE_API_KEY: str = "GOOGLE_API_KEY"
    GOOGLE_AI_API_KEY: str = "GOOGLE_AI_API_KEY"
    GOOGLE_SEARCH_ENGINE_ID: str = "GOOGLE_SEARCH_ENGINE_ID"
    SERPAPI_KEY: str = "SERPAPI_KEY"
    STRIPE_API_KEY: str = "STRIPE_API_KEY"
    AIRTABLE_API_KEY: str = "AIRTABLE_API_KEY"
    OPENAI_API_KEY: str = "OPENAI_API_KEY"
    ANTHROPIC_API_KEY: str = "ANTHROPIC_API_KEY"
    NOTION_API_KEY: str = "NOTION_API_KEY"
    OLLAMA_API_URL: str = "OLLAMA_API_URL"

    # Twilio
    TWILIO_ACCOUNT_SID: str = "TWILIO_ACCOUNT_SID"
    TWILIO_AUTH_TOKEN: str = "TWILIO_AUTH_TOKEN"

    # Database
    DATABASE_URL: str = "DATABASE_URL"
    REDIS_URL: str = "REDIS_URL"
    MONGODB_URI: str = "MONGODB_URI"

    # Messaging / Webhooks
    SLACK_WEBHOOK_URL: str = "SLACK_WEBHOOK_URL"
    DISCORD_WEBHOOK_URL: str = "DISCORD_WEBHOOK_URL"
    TELEGRAM_BOT_TOKEN: str = "TELEGRAM_BOT_TOKEN"

    # SMTP
    SMTP_HOST: str = "SMTP_HOST"
    SMTP_PORT: str = "SMTP_PORT"
    SMTP_USER: str = "SMTP_USER"
    SMTP_PASSWORD: str = "SMTP_PASSWORD"

    # Cloud Storage
    AWS_ACCESS_KEY_ID: str = "AWS_ACCESS_KEY_ID"
    AWS_SECRET_ACCESS_KEY: str = "AWS_SECRET_ACCESS_KEY"
    AWS_REGION: str = "AWS_REGION"
    GCS_CREDENTIALS: str = "GCS_CREDENTIALS"
    AZURE_STORAGE_CONNECTION_STRING: str = "AZURE_STORAGE_CONNECTION_STRING"


# =============================================================================
# CLI Constants
# =============================================================================

CLI_SEPARATOR: str = "=" * 70
CLI_VERSION: str = "1.0.0"


# =============================================================================
# Module Categories
# =============================================================================

MODULE_CATEGORIES: Dict[str, str] = {
    "browser": "Browser Automation",
    "element": "Element Operations",
    "string": "String Processing",
    "array": "Array Operations",
    "object": "Object Operations",
    "file": "File Operations",
    "data": "Data Processing",
    "datetime": "Date & Time",
    "math": "Math Operations",
    "utility": "Utilities",
    "api": "API Integration",
    "ai": "AI Services",
    "database": "Database",
    "cloud": "Cloud Storage",
    "communication": "Communication",
    "payment": "Payment Processing",
}


# =============================================================================
# Workflow Status
# =============================================================================

class WorkflowStatus:
    """Workflow execution status values"""

    PENDING: str = "pending"
    RUNNING: str = "running"
    SUCCESS: str = "success"
    COMPLETED: str = "completed"
    FAILURE: str = "failure"
    CANCELLED: str = "cancelled"


# =============================================================================
# Error Messages
# =============================================================================

class ErrorMessages:
    """Centralized error messages"""

    MODULE_NOT_FOUND: str = "Module not found: {module_id}"
    MISSING_REQUIRED_PARAM: str = "Missing required parameter: {param_name}"
    INVALID_PARAM_TYPE: str = "Invalid parameter type for {param_name}: expected {expected}, got {actual}"
    API_KEY_MISSING: str = "API key not found. Please set {env_var} environment variable."
    TIMEOUT_ERROR: str = "Module {module_id} timed out after {timeout}s"
    RETRY_EXHAUSTED: str = "Module {module_id} failed after {attempts} attempts"

    @classmethod
    def format(cls, message: str, **kwargs) -> str:
        """Format error message with parameters"""
        return message.format(**kwargs)
