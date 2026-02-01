"""
Multi-Language Runtime Support

Defines configurations for running plugins written in different programming languages.
Each language has its own executable, arguments, entry point pattern, and package manager.
"""

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import RuntimeError, PathTraversalError

logger = logging.getLogger(__name__)


def validate_entry_point(entry: str, plugin_dir: Path) -> Path:
    """
    Validate and resolve an entry point path securely.

    Security checks:
    - No path traversal (.. components)
    - No absolute paths
    - Must resolve within plugin directory
    - No symbolic links escaping plugin directory

    Args:
        entry: Entry point path (relative to plugin_dir)
        plugin_dir: Plugin directory (must be absolute)

    Returns:
        Resolved absolute path to entry point

    Raises:
        PathTraversalError: If path traversal is detected
    """
    # Check for obvious path traversal attempts
    if ".." in entry:
        raise PathTraversalError(entry, str(plugin_dir))

    # Check for absolute path (security: should always be relative)
    if os.path.isabs(entry):
        raise PathTraversalError(entry, str(plugin_dir))

    # Check for null bytes (security: can be used to bypass checks)
    if "\x00" in entry:
        raise PathTraversalError(entry, str(plugin_dir))

    # Ensure plugin_dir is absolute for comparison
    plugin_dir_resolved = plugin_dir.resolve()

    # Resolve the full path
    entry_path = (plugin_dir / entry).resolve()

    # Security: Verify the resolved path is within plugin directory
    # This catches symlinks that escape the directory
    try:
        entry_path.relative_to(plugin_dir_resolved)
    except ValueError:
        # Path is not relative to plugin_dir (escaped via symlink or other means)
        raise PathTraversalError(entry, str(plugin_dir))

    return entry_path


@dataclass
class LanguageConfig:
    """Configuration for a specific programming language runtime."""

    # Language identifier (e.g., "python", "node", "go")
    language: str

    # Executable name or path (None for compiled binaries)
    executable: Optional[str] = None

    # Additional arguments to pass to the executable
    args: List[str] = field(default_factory=list)

    # Default entry point filename pattern
    entry_pattern: str = "main"

    # Package manager for dependency installation
    package_manager: Optional[str] = None

    # File extensions associated with this language
    extensions: List[str] = field(default_factory=list)

    # Whether this is a compiled language (binary execution)
    is_compiled: bool = False

    # Environment variables to set
    env: Dict[str, str] = field(default_factory=dict)

    def get_executable_path(self) -> Optional[str]:
        """
        Get the full path to the executable.

        Returns:
            Path to executable, or None for compiled binaries
        """
        if self.is_compiled or not self.executable:
            return None
        return shutil.which(self.executable)

    def is_available(self) -> bool:
        """
        Check if this language runtime is available on the system.

        Returns:
            True if runtime is available
        """
        if self.is_compiled:
            return True  # Binary plugins don't need runtime
        return self.get_executable_path() is not None

    def build_command(
        self,
        entry_point: Path,
        plugin_dir: Path,
    ) -> List[str]:
        """
        Build the command to execute a plugin.

        Security: Entry point is validated to prevent path traversal attacks.

        Args:
            entry_point: Path to the entry point file/binary
            plugin_dir: Plugin directory

        Returns:
            Command list for subprocess execution

        Raises:
            PathTraversalError: If entry point escapes plugin directory
        """
        # Security: Validate and resolve entry point path
        # This prevents path traversal attacks like "../../../etc/passwd"
        if not entry_point.is_absolute():
            # entry_point is relative, validate it
            validated_path = validate_entry_point(str(entry_point), plugin_dir)
        else:
            # entry_point is already absolute, verify it's within plugin_dir
            plugin_dir_resolved = plugin_dir.resolve()
            entry_resolved = entry_point.resolve()
            try:
                entry_resolved.relative_to(plugin_dir_resolved)
                validated_path = entry_resolved
            except ValueError:
                raise PathTraversalError(str(entry_point), str(plugin_dir))

        if self.is_compiled:
            # Direct binary execution
            return [str(validated_path)]

        if not self.executable:
            raise RuntimeError(
                f"No executable configured for language: {self.language}",
                code="LANGUAGE_NO_EXECUTABLE",
            )

        cmd = [self.executable]
        cmd.extend(self.args)
        cmd.append(str(validated_path))
        return cmd


# Language configurations for supported runtimes
LANGUAGE_CONFIGS: Dict[str, LanguageConfig] = {
    "python": LanguageConfig(
        language="python",
        executable="python3",
        args=["-u"],  # Unbuffered output for real-time JSON-RPC
        entry_pattern="main.py",
        package_manager="pip",
        extensions=[".py"],
        is_compiled=False,
        env={"PYTHONUNBUFFERED": "1"},
    ),
    "node": LanguageConfig(
        language="node",
        executable="node",
        args=[],
        entry_pattern="index.js",
        package_manager="npm",
        extensions=[".js", ".mjs", ".cjs"],
        is_compiled=False,
        env={"NODE_ENV": "production"},
    ),
    "typescript": LanguageConfig(
        language="typescript",
        executable="npx",
        args=["ts-node", "--transpile-only"],
        entry_pattern="index.ts",
        package_manager="npm",
        extensions=[".ts"],
        is_compiled=False,
        env={"NODE_ENV": "production"},
    ),
    "deno": LanguageConfig(
        language="deno",
        executable="deno",
        args=["run", "--allow-net", "--allow-read", "--allow-env"],
        entry_pattern="main.ts",
        package_manager="deno",
        extensions=[".ts", ".js"],
        is_compiled=False,
    ),
    "bun": LanguageConfig(
        language="bun",
        executable="bun",
        args=["run"],
        entry_pattern="index.ts",
        package_manager="bun",
        extensions=[".ts", ".js"],
        is_compiled=False,
    ),
    "go": LanguageConfig(
        language="go",
        executable=None,  # Go plugins are compiled binaries
        args=[],
        entry_pattern="plugin",
        package_manager="go",
        extensions=[],
        is_compiled=True,
    ),
    "rust": LanguageConfig(
        language="rust",
        executable=None,  # Rust plugins are compiled binaries
        args=[],
        entry_pattern="plugin",
        package_manager="cargo",
        extensions=[],
        is_compiled=True,
    ),
    "java": LanguageConfig(
        language="java",
        executable="java",
        args=["-jar"],
        entry_pattern="plugin.jar",
        package_manager="maven",
        extensions=[".jar"],
        is_compiled=False,
    ),
    "kotlin": LanguageConfig(
        language="kotlin",
        executable="java",
        args=["-jar"],
        entry_pattern="plugin.jar",
        package_manager="gradle",
        extensions=[".jar"],
        is_compiled=False,
    ),
    "csharp": LanguageConfig(
        language="csharp",
        executable="dotnet",
        args=[],
        entry_pattern="Plugin.dll",
        package_manager="nuget",
        extensions=[".dll"],
        is_compiled=False,
    ),
    "fsharp": LanguageConfig(
        language="fsharp",
        executable="dotnet",
        args=[],
        entry_pattern="Plugin.dll",
        package_manager="nuget",
        extensions=[".dll"],
        is_compiled=False,
    ),
    "ruby": LanguageConfig(
        language="ruby",
        executable="ruby",
        args=[],
        entry_pattern="main.rb",
        package_manager="gem",
        extensions=[".rb"],
        is_compiled=False,
    ),
    "php": LanguageConfig(
        language="php",
        executable="php",
        args=[],
        entry_pattern="main.php",
        package_manager="composer",
        extensions=[".php"],
        is_compiled=False,
    ),
    "binary": LanguageConfig(
        language="binary",
        executable=None,  # Direct execution
        args=[],
        entry_pattern="plugin",
        package_manager=None,
        extensions=[],
        is_compiled=True,
    ),
}

# Aliases for common variations
LANGUAGE_ALIASES: Dict[str, str] = {
    "py": "python",
    "python3": "python",
    "js": "node",
    "javascript": "node",
    "nodejs": "node",
    "ts": "typescript",
    "golang": "go",
    "rs": "rust",
    "cs": "csharp",
    "dotnet": "csharp",
    "fs": "fsharp",
    "rb": "ruby",
    "exec": "binary",
    "bin": "binary",
}


def get_language_config(language: str) -> LanguageConfig:
    """
    Get configuration for a language.

    Args:
        language: Language identifier or alias

    Returns:
        LanguageConfig for the language

    Raises:
        RuntimeError: If language is not supported
    """
    # Resolve alias
    resolved = LANGUAGE_ALIASES.get(language.lower(), language.lower())

    if resolved not in LANGUAGE_CONFIGS:
        raise RuntimeError(
            f"Unsupported language: {language}",
            code="UNSUPPORTED_LANGUAGE",
            details={
                "language": language,
                "supported": list(LANGUAGE_CONFIGS.keys()),
            },
        )

    return LANGUAGE_CONFIGS[resolved]


def detect_language(plugin_dir: Path) -> str:
    """
    Auto-detect plugin language from directory contents.

    Args:
        plugin_dir: Plugin directory path

    Returns:
        Detected language identifier

    Detection order:
    1. plugin.yaml/plugin.manifest.json (if runtime.language is specified)
    2. Entry point file presence
    3. Package manager files
    """
    # Check for common entry points in priority order
    detection_rules = [
        # Python
        (["main.py", "plugin.py", "__main__.py"], "python"),
        # Node.js
        (["index.js", "main.js", "plugin.js"], "node"),
        # TypeScript (before generic Node.js detection)
        (["index.ts", "main.ts", "plugin.ts"], "typescript"),
        # Go (compiled binary)
        (["plugin", "main"], "go"),  # Note: also checks if executable
        # Java
        (["plugin.jar"], "java"),
        # .NET
        (["Plugin.dll", "plugin.dll"], "csharp"),
        # Ruby
        (["main.rb", "plugin.rb"], "ruby"),
        # PHP
        (["main.php", "index.php", "plugin.php"], "php"),
    ]

    for entry_files, language in detection_rules:
        for entry_file in entry_files:
            path = plugin_dir / entry_file
            if path.exists():
                # For compiled binaries, verify it's executable
                if language in ("go", "rust", "binary"):
                    if path.is_file() and _is_executable(path):
                        return language
                else:
                    return language

    # Check package manager files as fallback
    package_file_map = {
        "requirements.txt": "python",
        "setup.py": "python",
        "pyproject.toml": "python",
        "package.json": "node",
        "go.mod": "go",
        "Cargo.toml": "rust",
        "pom.xml": "java",
        "build.gradle": "kotlin",
        "*.csproj": "csharp",
        "*.fsproj": "fsharp",
        "Gemfile": "ruby",
        "composer.json": "php",
    }

    for filename, language in package_file_map.items():
        if "*" in filename:
            # Glob pattern
            import glob
            if glob.glob(str(plugin_dir / filename)):
                return language
        elif (plugin_dir / filename).exists():
            return language

    # Default to Python (most common)
    logger.warning(f"Could not detect language for {plugin_dir}, defaulting to python")
    return "python"


def _is_executable(path: Path) -> bool:
    """Check if a file is executable."""
    import os
    import stat
    try:
        mode = os.stat(path).st_mode
        return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    except OSError:
        return False


def list_available_languages() -> List[str]:
    """
    List all languages with available runtimes on this system.

    Returns:
        List of available language identifiers
    """
    available = []
    for lang_id, config in LANGUAGE_CONFIGS.items():
        if config.is_available():
            available.append(lang_id)
    return available


def get_install_instructions(language: str) -> str:
    """
    Get installation instructions for a language runtime.

    Args:
        language: Language identifier

    Returns:
        Installation instructions string
    """
    instructions = {
        "python": "Install Python 3.8+: https://www.python.org/downloads/",
        "node": "Install Node.js 18+: https://nodejs.org/",
        "typescript": "Install Node.js and run: npm install -g ts-node typescript",
        "deno": "Install Deno: https://deno.land/#installation",
        "bun": "Install Bun: https://bun.sh/",
        "go": "Install Go 1.20+: https://golang.org/dl/",
        "rust": "Install Rust: https://rustup.rs/",
        "java": "Install Java 17+: https://adoptium.net/",
        "kotlin": "Install Java 17+ and Kotlin: https://kotlinlang.org/docs/command-line.html",
        "csharp": "Install .NET 7+: https://dotnet.microsoft.com/download",
        "fsharp": "Install .NET 7+: https://dotnet.microsoft.com/download",
        "ruby": "Install Ruby 3.0+: https://www.ruby-lang.org/en/downloads/",
        "php": "Install PHP 8.1+: https://www.php.net/downloads",
        "binary": "Binary plugins don't require a runtime installation.",
    }

    resolved = LANGUAGE_ALIASES.get(language.lower(), language.lower())
    return instructions.get(resolved, f"No installation instructions for: {language}")
