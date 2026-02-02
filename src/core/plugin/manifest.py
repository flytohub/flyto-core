"""
Plugin Manifest Schema

Defines the structure for Flyto plugin packages.
Third-party developers can create plugins following this manifest format.

Usage:
    1. Create a Python package with flyto-plugin-* prefix
    2. Add plugin.manifest.json to package root
    3. Publish to PyPI
    4. Users can install via Plugin Marketplace

Manifest Format:
    {
        "name": "flyto-plugin-slack",
        "version": "1.0.0",
        "flyto_version": ">=2.0.0",
        "description": "Slack integration for Flyto",
        "author": "Your Name",
        "modules": [
            {
                "module_id": "slack.send_message",
                "entry_point": "flyto_plugin_slack.modules:SlackSendMessage"
            }
        ],
        "credentials": [
            {
                "type": "slack_oauth",
                "label": "Slack OAuth",
                "fields": ["client_id", "client_secret", "redirect_uri"]
            }
        ],
        "permissions": ["network"],
        "homepage": "https://github.com/...",
        "repository": "https://github.com/...",
        "license": "MIT",
        "keywords": ["slack", "messaging", "notification"]
    }
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class PluginStatus(str, Enum):
    """Plugin installation status."""
    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    UPDATE_AVAILABLE = "update_available"
    INSTALLING = "installing"
    FAILED = "failed"
    DISABLED = "disabled"


class PluginPermission(str, Enum):
    """Plugin permission types."""
    NETWORK = "network"           # Can make HTTP requests
    FILESYSTEM = "filesystem"     # Can read/write files
    SUBPROCESS = "subprocess"     # Can spawn subprocesses
    BROWSER = "browser"           # Can control browser
    CREDENTIALS = "credentials"   # Can access credentials
    DATABASE = "database"         # Can access database
    SYSTEM = "system"             # System-level operations


@dataclass
class PluginModule:
    """Module definition in a plugin."""
    module_id: str
    entry_point: str
    label: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "entry_point": self.entry_point,
            "label": self.label,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginModule":
        return cls(
            module_id=data.get("module_id", ""),
            entry_point=data.get("entry_point", ""),
            label=data.get("label"),
            description=data.get("description"),
            category=data.get("category"),
            icon=data.get("icon"),
        )


@dataclass
class PluginCredentialType:
    """Credential type definition for a plugin."""
    type: str
    label: str
    fields: List[str] = field(default_factory=list)
    description: Optional[str] = None
    oauth_config: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "label": self.label,
            "fields": self.fields,
            "description": self.description,
            "oauth_config": self.oauth_config,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginCredentialType":
        return cls(
            type=data.get("type", ""),
            label=data.get("label", ""),
            fields=data.get("fields", []),
            description=data.get("description"),
            oauth_config=data.get("oauth_config"),
        )


@dataclass
class PluginManifest:
    """
    Plugin manifest defining package structure and metadata.

    Plugins must include a plugin.manifest.json file with this structure.
    """
    # Required fields
    name: str                          # Package name (flyto-plugin-*)
    version: str                       # SemVer version
    description: str                   # Short description

    # Version compatibility
    flyto_version: str = ">=2.0.0"     # Required Flyto version

    # Author info
    author: str = ""
    author_email: Optional[str] = None

    # Modules provided by this plugin
    modules: List[PluginModule] = field(default_factory=list)

    # Credential types defined by this plugin
    credentials: List[PluginCredentialType] = field(default_factory=list)

    # Required permissions
    permissions: List[str] = field(default_factory=list)

    # Links
    homepage: Optional[str] = None
    repository: Optional[str] = None
    documentation: Optional[str] = None

    # Categorization
    license: str = "MIT"
    keywords: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)

    # Runtime requirements
    python_version: str = ">=3.9"
    dependencies: List[str] = field(default_factory=list)

    # Marketplace metadata
    icon: Optional[str] = None         # URL to icon image
    banner: Optional[str] = None       # URL to banner image
    screenshots: List[str] = field(default_factory=list)

    # Statistics (populated by marketplace)
    downloads: int = 0
    rating: float = 0.0
    rating_count: int = 0

    # Status
    status: PluginStatus = PluginStatus.NOT_INSTALLED
    installed_version: Optional[str] = None
    installed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "flyto_version": self.flyto_version,
            "author": self.author,
            "author_email": self.author_email,
            "modules": [m.to_dict() for m in self.modules],
            "credentials": [c.to_dict() for c in self.credentials],
            "permissions": self.permissions,
            "homepage": self.homepage,
            "repository": self.repository,
            "documentation": self.documentation,
            "license": self.license,
            "keywords": self.keywords,
            "categories": self.categories,
            "python_version": self.python_version,
            "dependencies": self.dependencies,
            "icon": self.icon,
            "banner": self.banner,
            "screenshots": self.screenshots,
            "downloads": self.downloads,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "status": self.status.value,
            "installed_version": self.installed_version,
            "installed_at": self.installed_at.isoformat() if self.installed_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        """Create from dictionary."""
        modules = [PluginModule.from_dict(m) for m in data.get("modules", [])]
        credentials = [PluginCredentialType.from_dict(c) for c in data.get("credentials", [])]

        installed_at = None
        if data.get("installed_at"):
            try:
                installed_at = datetime.fromisoformat(data["installed_at"])
            except (ValueError, TypeError):
                pass

        status = PluginStatus.NOT_INSTALLED
        if data.get("status"):
            try:
                status = PluginStatus(data["status"])
            except ValueError:
                pass

        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            flyto_version=data.get("flyto_version", ">=2.0.0"),
            author=data.get("author", ""),
            author_email=data.get("author_email"),
            modules=modules,
            credentials=credentials,
            permissions=data.get("permissions", []),
            homepage=data.get("homepage"),
            repository=data.get("repository"),
            documentation=data.get("documentation"),
            license=data.get("license", "MIT"),
            keywords=data.get("keywords", []),
            categories=data.get("categories", []),
            python_version=data.get("python_version", ">=3.9"),
            dependencies=data.get("dependencies", []),
            icon=data.get("icon"),
            banner=data.get("banner"),
            screenshots=data.get("screenshots", []),
            downloads=data.get("downloads", 0),
            rating=data.get("rating", 0.0),
            rating_count=data.get("rating_count", 0),
            status=status,
            installed_version=data.get("installed_version"),
            installed_at=installed_at,
        )

    def validate(self) -> List[str]:
        """
        Validate manifest format.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Required fields
        if not self.name:
            errors.append("Missing required field: name")
        elif not self.name.startswith("flyto-plugin-"):
            errors.append("Plugin name must start with 'flyto-plugin-'")

        if not self.version:
            errors.append("Missing required field: version")

        if not self.description:
            errors.append("Missing required field: description")

        # Module validation
        for i, module in enumerate(self.modules):
            if not module.module_id:
                errors.append(f"Module {i}: missing module_id")
            if not module.entry_point:
                errors.append(f"Module {i}: missing entry_point")

        # Permission validation
        valid_permissions = [p.value for p in PluginPermission]
        for perm in self.permissions:
            if perm not in valid_permissions:
                errors.append(f"Invalid permission: {perm}")

        return errors

    @property
    def module_count(self) -> int:
        """Get number of modules in this plugin."""
        return len(self.modules)

    @property
    def has_credentials(self) -> bool:
        """Check if plugin defines credential types."""
        return len(self.credentials) > 0

    @property
    def is_installed(self) -> bool:
        """Check if plugin is installed."""
        return self.status in (PluginStatus.INSTALLED, PluginStatus.UPDATE_AVAILABLE)

    @property
    def needs_update(self) -> bool:
        """Check if plugin has available update."""
        return self.status == PluginStatus.UPDATE_AVAILABLE


def load_manifest_from_file(path: str) -> PluginManifest:
    """
    Load plugin manifest from JSON file.

    Args:
        path: Path to plugin.manifest.json

    Returns:
        PluginManifest instance

    Raises:
        ValueError: If manifest is invalid
    """
    import json

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    manifest = PluginManifest.from_dict(data)
    errors = manifest.validate()

    if errors:
        raise ValueError(f"Invalid manifest: {'; '.join(errors)}")

    return manifest


def create_manifest_template(
    name: str,
    description: str,
    author: str,
) -> PluginManifest:
    """
    Create a template manifest for new plugin development.

    Args:
        name: Plugin name (will be prefixed with flyto-plugin- if needed)
        description: Plugin description
        author: Author name

    Returns:
        PluginManifest template
    """
    if not name.startswith("flyto-plugin-"):
        name = f"flyto-plugin-{name}"

    return PluginManifest(
        name=name,
        version="0.1.0",
        description=description,
        author=author,
        modules=[],
        credentials=[],
        permissions=[],
        keywords=[],
        categories=[],
    )
