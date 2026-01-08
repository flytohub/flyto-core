"""
Validation Constants

Permission whitelist, capability mappings, and other constants.
"""
from typing import Dict, Set

# Valid permissions that can be declared in required_permissions
VALID_PERMISSIONS: Set[str] = {
    # Network
    "network.access",
    "network.private",

    # Database
    "database.read",
    "database.write",
    "database.query",

    # Cloud Storage
    "cloud.storage",
    "cloud.storage.read",
    "cloud.storage.write",

    # AI APIs
    "ai.api",
    "ai.openai",
    "ai.anthropic",
    "ai.google",

    # Communication
    "sms.send",
    "voice.call",
    "email.send",

    # Payment
    "payment.process",
    "payment.read",

    # Browser
    "browser.read",
    "browser.write",
    "browser.automation",

    # File System
    "filesystem.read",
    "filesystem.write",

    # Shell
    "shell.execute",

    # Desktop
    "desktop.automation",

    # App
    "app.automation",
}


# Import to capability mapping (for AST detection)
IMPORT_CAPABILITY_MAP: Dict[str, str] = {
    # Network libraries
    "httpx": "network.access",
    "aiohttp": "network.access",
    "requests": "network.access",
    "urllib": "network.access",
    "urllib3": "network.access",
    "http.client": "network.access",

    # Subprocess/shell
    "subprocess": "shell.execute",
    "os.system": "shell.execute",
    "shlex": "shell.execute",

    # Docker
    "docker": "shell.execute",

    # AI providers
    "openai": "ai.openai",
    "anthropic": "ai.anthropic",
    "google.generativeai": "ai.google",

    # Database
    "sqlite3": "database.query",
    "psycopg2": "database.query",
    "pymysql": "database.query",
    "asyncpg": "database.query",
    "motor": "database.query",
    "pymongo": "database.query",

    # File system
    "pathlib": "filesystem.read",  # Conservative - read by default
    "shutil": "filesystem.write",

    # Email
    "smtplib": "email.send",
    "email": "email.send",

    # Browser automation
    "playwright": "browser.automation",
    "selenium": "browser.automation",
    "pyppeteer": "browser.automation",
}


# Function call to capability mapping
CALL_CAPABILITY_MAP: Dict[str, str] = {
    # File operations
    "open": "filesystem.read",  # Could be write depending on mode
    "Path.write_text": "filesystem.write",
    "Path.write_bytes": "filesystem.write",
    "Path.mkdir": "filesystem.write",
    "Path.rmdir": "filesystem.write",
    "Path.unlink": "filesystem.write",
    "shutil.copy": "filesystem.write",
    "shutil.move": "filesystem.write",
    "shutil.rmtree": "filesystem.write",

    # Subprocess
    "subprocess.run": "shell.execute",
    "subprocess.call": "shell.execute",
    "subprocess.Popen": "shell.execute",
    "os.system": "shell.execute",
    "os.popen": "shell.execute",

    # Environment (forbidden)
    "os.getenv": "FORBIDDEN",
    "os.environ": "FORBIDDEN",
}


# Capabilities that imply side effects (require permissions)
SIDE_EFFECT_CAPABILITIES: Set[str] = {
    "network.access",
    "network.private",
    "database.write",
    "filesystem.write",
    "shell.execute",
    "email.send",
    "sms.send",
    "voice.call",
    "payment.process",
    "browser.automation",
    "desktop.automation",
    "app.automation",
}


# Secret patterns for detection
SECRET_PATTERNS = [
    (r'["\']sk-[a-zA-Z0-9]{32,}["\']', "OpenAI API key"),
    (r'["\']ghp_[a-zA-Z0-9]{36}["\']', "GitHub token"),
    (r'["\']gho_[a-zA-Z0-9]{36}["\']', "GitHub OAuth token"),
    (r'["\']github_pat_[a-zA-Z0-9_]{36,}["\']', "GitHub PAT"),
    (r'["\']xoxb-[a-zA-Z0-9-]+["\']', "Slack bot token"),
    (r'["\']xoxp-[a-zA-Z0-9-]+["\']', "Slack user token"),
    (r'["\']AKIA[A-Z0-9]{16}["\']', "AWS access key"),
    (r'Bearer\s+[a-zA-Z0-9._-]{20,}', "Bearer token"),
    (r'["\'][a-f0-9]{32}["\']', "Potential API key (32 hex)"),
]


# Sensitive parameter names
SENSITIVE_PARAM_PATTERNS = [
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "private_key",
    "credential",
    "auth",
    "bearer",
]


# Stability levels
STABILITY_LEVELS = {"stable", "beta", "alpha", "experimental", "deprecated"}


# Default severity by stability
SEVERITY_BY_STABILITY = {
    "stable": "ERROR",
    "beta": "WARN",
    "alpha": "INFO",
    "experimental": "INFO",
    "deprecated": "WARN",
}
