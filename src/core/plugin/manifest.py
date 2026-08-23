# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Plugin Manifest Schema

Defines the structure for Flyto2 plugin packages.
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
        "description": "Slack integration for Flyto2",
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

import contextlib
import hashlib
import ipaddress
import json
import os
import re
import stat
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit


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
    flyto_version: str = ">=2.0.0"     # Required Flyto2 version

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
    python_version: str = ">=3.10"
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
            with contextlib.suppress(ValueError, TypeError):
                installed_at = datetime.fromisoformat(data["installed_at"])

        status = PluginStatus.NOT_INSTALLED
        if data.get("status"):
            with contextlib.suppress(ValueError):
                status = PluginStatus(data["status"])

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
            python_version=data.get("python_version", ">=3.10"),
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


# Language-neutral supply-chain manifest.  This deliberately does not feed the
# legacy loader above: adoption is validation and verification, never install.
PLUGIN_SCHEMA = "flyto.plugin.v1"
MAX_MANIFEST_BYTES = 262_144
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_JSON_DEPTH = 12
MAX_JSON_NODES = 4096
MAX_TEXT = 2048
MAX_MODULES = 128
MAX_CAPABILITIES = 256
MAX_EVIDENCE = 256
MAX_ALLOWED_HOSTS = 32
MAX_HOST_AUTHORITY_BYTES = 255
MAX_EXISTING_PLUGIN_IDS = 256
DANGEROUS_PERMISSIONS = frozenset(
    {"shell.execute", "subprocess.execute", "payment.process", "browser.debug", "code.execute"}
)
DENIED_NAMESPACES = frozenset(
    {
        "agent", "ai", "analysis", "api", "archive", "array", "auth", "aws", "browser", "cache", "check", "cloud",
        "communication", "compare", "convert", "core", "crypto", "data", "database", "datetime", "db", "decode", "dns",
        "docker", "element", "encode", "env", "error", "excel", "file", "flow", "format", "git", "google", "graphql",
        "hash", "http", "image", "k8s", "llm", "logic", "markdown", "math", "mcp", "meta", "monitor", "network",
        "notification", "notify", "object", "output", "path", "payment", "pdf", "port", "process", "productivity",
        "queue", "random", "regex", "sandbox", "scheduler", "set", "shell", "ssh", "stats", "storage", "string",
        "template", "test", "testing", "text", "utility", "validate", "verification", "verify", "warroom", "word",
    }
)
FORBIDDEN_PARAMETERS = frozenset(
    {"url", "host", "endpoint", "address", "gateway", "command", "argv", "token", "secret", "password", "credential"}
)
_IDENT = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_NAMESPACE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_PLUGIN_ID = re.compile(r"^(?:[a-z][a-z0-9-]*\.){2,}[a-z][a-z0-9-]*$")
_SEMVER = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")
_DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
_ENV_COMPONENT = re.compile(r"^[A-Z][A-Z0-9_]{0,62}$")

_TOP_KEYS = frozenset({"schema", "plugin", "artifact", "serve", "capabilities", "evidence", "modules"})
_PLUGIN_KEYS = frozenset({"id", "namespace", "version", "title", "summary", "license", "support_url", "publisher_key_id", "min_host"})
_ARTIFACT_KEYS = frozenset({"kind", "name", "version", "digest", "attestation"})
_SERVE_KEYS = frozenset({"binding", "locality", "request_timeout_ms", "max_response_bytes"})
_CAPABILITY_KEYS = frozenset({"id"})
_EVIDENCE_KEYS = frozenset({"kind", "produced_by"})
_MODULE_KEYS = frozenset({"module_id", "provides_capability", "label", "label_key", "description", "category", "icon", "actuates", "idempotent", "retryable", "timeout_ms", "required_permissions", "params_schema"})
_SCHEMA_KEYS = frozenset({"type", "additionalProperties", "properties", "required", "description", "title", "default", "enum", "const", "items", "minLength", "maxLength", "minimum", "maximum", "pattern", "format"})


class PluginManifestError(ValueError):
    """A secret-free, stable failure from v1 validation or adoption."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class AdoptedPluginManifest:
    """Detached immutable output of inert manifest adoption."""

    manifest: Mapping[str, Any]
    endpoint_env: str
    token_env: str
    artifact_sha256: Optional[str] = None


def _fail(code: str, message: str) -> None:
    raise PluginManifestError(code, message)


def _validated_text(value: Any, code: str, message: str, *, allow_empty: bool = True) -> str:
    """Return bounded UTF-8 text without unsafe Unicode scalar values."""
    if type(value) is not str or (not allow_empty and not value):
        _fail(code, message)
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(code, message)
    if len(encoded) > MAX_TEXT or any(
        unicodedata.category(ch) in {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}
        for ch in value
    ):
        _fail(code, message)
    return value


def _plain(value: Any, depth: int = 0, counter: Optional[List[int]] = None) -> Any:
    """Copy hostile Mapping/Sequence input into bounded JSON-compatible data."""
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_JSON_NODES:
        _fail("MANIFEST_TOO_COMPLEX", "manifest exceeds the node limit")
    if depth > MAX_JSON_DEPTH:
        _fail("MANIFEST_TOO_DEEP", "manifest exceeds the depth limit")
    if value is None or type(value) in (bool, int, float):
        if type(value) is float and (value != value or abs(value) == float("inf")):
            _fail("INVALID_VALUE", "manifest contains a non-finite number")
        return value
    if type(value) is str:
        return _validated_text(value, "INVALID_TEXT", "manifest text is invalid or too long")
    if isinstance(value, Mapping):
        try:
            items = iter(value.items())
        except Exception:
            _fail("INVALID_MAPPING", "manifest mapping could not be read")
        result = {}
        try:
            for key, item in items:
                if len(result) >= MAX_JSON_NODES:
                    _fail("MANIFEST_TOO_COMPLEX", "manifest exceeds the node limit")
                _validated_text(key, "INVALID_KEY", "manifest key is invalid or too long")
                if key in result:
                    _fail("DUPLICATE_KEY", "manifest contains a duplicate key")
                result[key] = _plain(item, depth + 1, counter)
        except PluginManifestError:
            raise
        except Exception:
            _fail("INVALID_MAPPING", "manifest mapping could not be read")
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        try:
            return [_plain(item, depth + 1, counter) for item in value]
        except PluginManifestError:
            raise
        except Exception:
            _fail("INVALID_SEQUENCE", "manifest sequence could not be read")
    _fail("INVALID_TYPE", "manifest contains a non-JSON value")


def _object(value: Any, where: str, keys: frozenset[str]) -> Dict[str, Any]:
    if type(value) is not dict:
        _fail("INVALID_OBJECT", f"{where} must be an object")
    unknown = sorted(set(value) - keys)
    if unknown:
        _fail("UNKNOWN_KEY", f"{where} contains an unknown key")
    return value


def _required(obj: Dict[str, Any], names: Sequence[str], where: str) -> None:
    missing = next((name for name in names if name not in obj), None)
    if missing:
        _fail("MISSING_FIELD", f"{where} is missing required field: {missing}")


def _text(obj: Dict[str, Any], name: str, where: str) -> str:
    return _validated_text(
        obj.get(name), "INVALID_FIELD", f"{where}.{name} must be non-empty text", allow_empty=False
    )


def _closed_schema(value: Any, where: str) -> Dict[str, Any]:
    obj = _object(value, where, _SCHEMA_KEYS)
    if obj.get("type") != "object" or obj.get("additionalProperties") is not False:
        _fail("OPEN_PARAMS_SCHEMA", f"{where} must be a closed object schema")
    properties = obj.get("properties")
    if type(properties) is not dict:
        _fail("INVALID_PARAMS_SCHEMA", f"{where}.properties must be an object")
    for name, definition in properties.items():
        if not _IDENT.fullmatch(name) or name.lower() in FORBIDDEN_PARAMETERS:
            _fail("FORBIDDEN_PARAMETER", f"{where} contains a forbidden parameter name")
        _schema_node(definition, f"{where}.properties.{name}")
    required = obj.get("required", [])
    if (
        type(required) is not list
        or any(type(name) is not str or name not in properties for name in required)
        or len(required) != len(set(required))
    ):
        _fail("INVALID_PARAMS_SCHEMA", f"{where}.required must name declared properties")
    return obj


def _schema_value_matches(value: Any, schema_type: str) -> bool:
    if schema_type == "null":
        return value is None
    if schema_type == "boolean":
        return type(value) is bool
    if schema_type == "integer":
        return type(value) is int
    if schema_type == "number":
        return type(value) in (int, float)
    if schema_type == "string":
        return type(value) is str
    if schema_type == "array":
        return type(value) is list
    return type(value) is dict


def _schema_node(value: Any, where: str) -> None:
    obj = _object(value, where, _SCHEMA_KEYS)
    schema_type = obj.get("type")
    if type(schema_type) is not str or schema_type not in {"object", "array", "string", "integer", "number", "boolean", "null"}:
        _fail("INVALID_PARAMS_SCHEMA", f"{where}.type is invalid")
    for name in ("description", "title"):
        if name in obj and type(obj[name]) is not str:
            _fail("INVALID_PARAMS_SCHEMA", f"{where}.{name} must be text")
    for name in ("pattern", "format"):
        if name in obj and (type(obj[name]) is not str or schema_type != "string"):
            _fail("INVALID_PARAMS_SCHEMA", f"{where}.{name} is invalid")
    for name in ("minLength", "maxLength"):
        if name in obj and (type(obj[name]) is not int or obj[name] < 0 or schema_type != "string"):
            _fail("INVALID_PARAMS_SCHEMA", f"{where}.{name} is invalid")
    for name in ("minimum", "maximum"):
        if name in obj and (type(obj[name]) not in (int, float) or schema_type not in {"integer", "number"}):
            _fail("INVALID_PARAMS_SCHEMA", f"{where}.{name} is invalid")
    if "minimum" in obj and "maximum" in obj and obj["minimum"] > obj["maximum"]:
        _fail("INVALID_PARAMS_SCHEMA", f"{where} numeric bounds are inconsistent")
    if "minLength" in obj and "maxLength" in obj and obj["minLength"] > obj["maxLength"]:
        _fail("INVALID_PARAMS_SCHEMA", f"{where} string bounds are inconsistent")
    if "additionalProperties" in obj and (
        schema_type != "object" or obj["additionalProperties"] is not False
    ):
        _fail("OPEN_PARAMS_SCHEMA", f"{where}.additionalProperties is invalid")
    if "properties" in obj and schema_type != "object":
        _fail("INVALID_PARAMS_SCHEMA", f"{where}.properties requires an object schema")
    if "required" in obj and "properties" not in obj:
        _fail("INVALID_PARAMS_SCHEMA", f"{where}.required requires an object schema")
    if "properties" in obj:
        properties = obj["properties"]
        if type(properties) is not dict or obj.get("type") != "object" or obj.get("additionalProperties") is not False:
            _fail("OPEN_PARAMS_SCHEMA", f"{where} nested object schema must be closed")
        for name, definition in properties.items():
            if not _IDENT.fullmatch(name) or name.lower() in FORBIDDEN_PARAMETERS:
                _fail("FORBIDDEN_PARAMETER", f"{where} contains a forbidden parameter name")
            _schema_node(definition, f"{where}.properties.{name}")
        required = obj.get("required", [])
        if (
            type(required) is not list
            or any(type(name) is not str or name not in properties for name in required)
            or len(required) != len(set(required))
        ):
            _fail("INVALID_PARAMS_SCHEMA", f"{where}.required must uniquely name declared properties")
    elif schema_type == "object":
        _fail("INVALID_PARAMS_SCHEMA", f"{where}.properties is required for an object schema")
    if "items" in obj:
        if obj.get("type") != "array":
            _fail("INVALID_PARAMS_SCHEMA", f"{where}.items requires an array schema")
        _schema_node(obj["items"], f"{where}.items")
    if schema_type == "array" and "items" not in obj:
        _fail("INVALID_PARAMS_SCHEMA", f"{where}.items is required for an array schema")
    if "enum" in obj:
        enum = obj["enum"]
        if type(enum) is not list or not enum or any(not _schema_value_matches(item, schema_type) for item in enum):
            _fail("INVALID_PARAMS_SCHEMA", f"{where}.enum is invalid")
        encoded = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in enum]
        if len(encoded) != len(set(encoded)):
            _fail("INVALID_PARAMS_SCHEMA", f"{where}.enum values must be unique")
    for name in ("default", "const"):
        if name in obj and not _schema_value_matches(obj[name], schema_type):
            _fail("INVALID_PARAMS_SCHEMA", f"{where}.{name} does not match its type")


def _canonical(value: Any) -> Any:
    if type(value) is dict:
        return {key: _canonical(value[key]) for key in sorted(value)}
    if type(value) is list:
        return [_canonical(item) for item in value]
    return value


def validate_plugin_manifest(data: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a detached canonical v1 manifest, or fail closed with a stable error."""
    plain = _plain(data)
    try:
        encoded = json.dumps(plain, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    except (TypeError, ValueError, UnicodeError):
        _fail("INVALID_JSON", "manifest is not canonical JSON data")
    if len(encoded) > MAX_MANIFEST_BYTES:
        _fail("MANIFEST_TOO_LARGE", "manifest exceeds the byte limit")
    # Schema has defined precedence over every field-level or unknown-key error.
    if type(plain) is not dict or plain.get("schema") != PLUGIN_SCHEMA:
        _fail("UNSUPPORTED_SCHEMA", "schema must be flyto.plugin.v1")
    top = _object(plain, "manifest", _TOP_KEYS)
    _required(top, ("plugin", "artifact", "serve", "capabilities", "evidence", "modules"), "manifest")
    plugin = _object(top["plugin"], "plugin", _PLUGIN_KEYS)
    _required(plugin, sorted(_PLUGIN_KEYS), "plugin")
    plugin_id = _text(plugin, "id", "plugin")
    namespace = _text(plugin, "namespace", "plugin")
    if not _PLUGIN_ID.fullmatch(plugin_id):
        _fail("INVALID_PLUGIN_ID", "plugin.id must be lowercase reverse-DNS")
    if not _NAMESPACE.fullmatch(namespace) or namespace in DENIED_NAMESPACES:
        _fail("INVALID_NAMESPACE", "plugin.namespace is invalid or reserved")
    for name in ("version", "min_host"):
        if not _SEMVER.fullmatch(_text(plugin, name, "plugin")):
            _fail("INVALID_SEMVER", f"plugin.{name} must be semver")
    support_url = _text(plugin, "support_url", "plugin")
    try:
        support = urlsplit(support_url)
        support_host = support.hostname
        support_port = support.port
    except ValueError:
        _fail("INVALID_URL", "plugin.support_url must be an absolute HTTPS URL")
    if support.scheme != "https" or not support_host or support.username or support.password or support.fragment:
        _fail("INVALID_URL", "plugin.support_url must be an absolute HTTPS URL")
    try:
        support_host.encode("ascii")
    except UnicodeEncodeError:
        _fail("INVALID_URL", "plugin.support_url host must be ASCII")
    if support_port is not None and not 1 <= support_port <= 65535:
        _fail("INVALID_URL", "plugin.support_url port is invalid")

    artifact = _object(top["artifact"], "artifact", _ARTIFACT_KEYS)
    _required(artifact, sorted(_ARTIFACT_KEYS), "artifact")
    if _text(artifact, "kind", "artifact") not in {"pypi", "oci", "archive", "inprocess-python"}:
        _fail("INVALID_ARTIFACT", "artifact.kind is not supported")
    if not _IDENT.fullmatch(_text(artifact, "name", "artifact")):
        _fail("INVALID_ARTIFACT", "artifact.name is invalid")
    if not _SEMVER.fullmatch(_text(artifact, "version", "artifact")):
        _fail("INVALID_SEMVER", "artifact.version must be semver")
    if not _DIGEST.fullmatch(_text(artifact, "digest", "artifact")):
        _fail("INVALID_DIGEST", "artifact.digest must be lowercase sha256")
    if _text(artifact, "attestation", "artifact") not in {"pypi-trusted-publishing", "sigstore", "none"}:
        _fail("INVALID_ATTESTATION", "artifact.attestation is not supported")

    serve = _object(top["serve"], "serve", _SERVE_KEYS)
    _required(serve, sorted(_SERVE_KEYS), "serve")
    if serve["binding"] not in {"inprocess-python", "http"} or serve["locality"] not in {"same_host", "same_network"}:
        _fail("INVALID_SERVE", "serve binding or locality is invalid")
    for name, maximum in (("request_timeout_ms", 120_000), ("max_response_bytes", 16_777_216)):
        if type(serve[name]) is not int or not 1 <= serve[name] <= maximum:
            _fail("INVALID_BOUND", f"serve.{name} is outside its bound")

    capabilities = top["capabilities"]
    evidence = top["evidence"]
    modules = top["modules"]
    if type(capabilities) is not list or not 1 <= len(capabilities) <= MAX_CAPABILITIES:
        _fail("INVALID_COUNT", "capabilities count is outside its bound")
    if type(evidence) is not list or len(evidence) > MAX_EVIDENCE:
        _fail("INVALID_COUNT", "evidence count is outside its bound")
    if type(modules) is not list or not 1 <= len(modules) <= MAX_MODULES:
        _fail("INVALID_COUNT", "modules count is outside its bound")
    capability_ids = []
    for index, value in enumerate(capabilities):
        item = _object(value, f"capabilities[{index}]", _CAPABILITY_KEYS)
        _required(item, ("id",), f"capabilities[{index}]")
        ident = _text(item, "id", f"capabilities[{index}]")
        if not _IDENT.fullmatch(ident) or ident == "human.approval":
            _fail("INVALID_CAPABILITY", "capability id is invalid or unschedulable")
        capability_ids.append(ident)
    if len(set(capability_ids)) != len(capability_ids):
        _fail("DUPLICATE_ID", "capability ids must be unique")

    module_ids = []
    produced = []
    for index, value in enumerate(modules):
        where = f"modules[{index}]"
        item = _object(value, where, _MODULE_KEYS)
        _required(item, sorted(_MODULE_KEYS), where)
        module_id = _text(item, "module_id", where)
        capability = _text(item, "provides_capability", where)
        if not _IDENT.fullmatch(module_id) or not module_id.startswith(namespace + "."):
            _fail("MODULE_NAMESPACE_MISMATCH", "module id is outside the plugin namespace")
        if capability not in capability_ids:
            _fail("CAPABILITY_MISMATCH", "module capability is not declared")
        for name in ("actuates", "idempotent", "retryable"):
            if type(item[name]) is not bool:
                _fail("INVALID_BOOLEAN", f"{where}.{name} must be a boolean")
        if type(item["timeout_ms"]) is not int or not 1 <= item["timeout_ms"] <= 3_600_000:
            _fail("INVALID_BOUND", f"{where}.timeout_ms is outside its bound")
        permissions = item["required_permissions"]
        if type(permissions) is not list or len(permissions) > len(DANGEROUS_PERMISSIONS) or any(type(p) is not str or p not in DANGEROUS_PERMISSIONS for p in permissions) or len(set(permissions)) != len(permissions):
            _fail("INVALID_PERMISSION", "required_permissions contains an unsupported value")
        _closed_schema(item["params_schema"], f"{where}.params_schema")
        module_ids.append(module_id)
        produced.append(capability)
    if len(set(module_ids)) != len(module_ids):
        _fail("DUPLICATE_ID", "module ids must be unique")
    if set(produced) != set(capability_ids):
        _fail("CAPABILITY_MISMATCH", "every capability must have a module producer")

    evidence_pairs = set()
    for index, value in enumerate(evidence):
        where = f"evidence[{index}]"
        item = _object(value, where, _EVIDENCE_KEYS)
        _required(item, ("kind", "produced_by"), where)
        kind = _text(item, "kind", where)
        producer = _text(item, "produced_by", where)
        if not _IDENT.fullmatch(kind) or producer not in produced or producer == "human.approval":
            _fail("EVIDENCE_MISMATCH", "evidence producer is not a declared module capability")
        if (kind, producer) in evidence_pairs:
            _fail("DUPLICATE_ID", "evidence declarations must be unique")
        evidence_pairs.add((kind, producer))
    return _canonical(plain)


def verify_plugin_artifact(path: os.PathLike[str] | str, digest: str, max_bytes: int = MAX_ARTIFACT_BYTES) -> str:
    """Hash one already-local regular file without following its final symlink."""
    match = _DIGEST.fullmatch(digest) if type(digest) is str else None
    if not match:
        _fail("INVALID_DIGEST", "artifact.digest must be lowercase sha256")
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_ARTIFACT_BYTES:
        _fail("INVALID_BOUND", "artifact byte limit is outside the hard cap")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | nofollow
    try:
        artifact_path = os.fspath(path)
    except (TypeError, ValueError):
        _fail("ARTIFACT_UNREADABLE", "artifact must be a readable local regular file")
    expected = None
    if not nofollow:
        try:
            expected = os.lstat(artifact_path)
        except (OSError, TypeError, ValueError):
            _fail("ARTIFACT_UNREADABLE", "artifact must be a readable local regular file")
        if not stat.S_ISREG(expected.st_mode):
            _fail("ARTIFACT_UNREADABLE", "artifact must be a readable local regular file")
    try:
        fd = os.open(artifact_path, flags)
    except (OSError, TypeError, ValueError):
        _fail("ARTIFACT_UNREADABLE", "artifact must be a readable local regular file")
    try:
        before = os.fstat(fd)
        if expected is not None and (expected.st_dev, expected.st_ino) != (before.st_dev, before.st_ino):
            _fail("ARTIFACT_CHANGED", "artifact changed during verification")
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            _fail("ARTIFACT_INVALID", "artifact must be a bounded regular file")
        hasher = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, min(1024 * 1024, max_bytes + 1 - total))
            if not block:
                break
            total += len(block)
            if total > max_bytes:
                _fail("ARTIFACT_TOO_LARGE", "artifact exceeds the byte limit")
            hasher.update(block)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            _fail("ARTIFACT_CHANGED", "artifact changed during verification")
    except OSError:
        _fail("ARTIFACT_UNREADABLE", "artifact could not be read")
    finally:
        os.close(fd)
    actual = hasher.hexdigest()
    if actual != match.group(1):
        _fail("DIGEST_MISMATCH", "artifact digest does not match")
    return actual


def plugin_environment_names(namespace: str) -> tuple[str, str]:
    """Derive, never accept, the endpoint and token environment names."""
    if not _NAMESPACE.fullmatch(namespace) or namespace in DENIED_NAMESPACES:
        _fail("INVALID_NAMESPACE", "plugin.namespace is invalid or reserved")
    component = namespace.upper()
    if not _ENV_COMPONENT.fullmatch(component):
        _fail("INVALID_NAMESPACE", "plugin.namespace cannot form an environment name")
    return f"FLYTO_PLUGIN_ENDPOINT__{component}", f"FLYTO_PLUGIN_TOKEN__{component}"


def _host_authority(value: Any) -> str:
    """Return one bounded canonical ASCII host authority without resolving it."""
    authority = _validated_text(
        value, "INVALID_ENDPOINT", "endpoint allowlist entry is invalid", allow_empty=False
    )
    try:
        encoded = authority.encode("ascii")
    except UnicodeEncodeError:
        _fail("INVALID_ENDPOINT", "endpoint allowlist entry must be ASCII")
    if len(encoded) > MAX_HOST_AUTHORITY_BYTES:
        _fail("INVALID_ENDPOINT", "endpoint allowlist entry is too long")
    try:
        parsed = urlsplit("//" + authority)
        parsed_host = parsed.hostname
        parsed_port = parsed.port
    except ValueError:
        _fail("INVALID_ENDPOINT", "endpoint allowlist entry must be a host authority")
    if (
        not parsed_host
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        _fail("INVALID_ENDPOINT", "endpoint allowlist entry must be a host authority")
    host = parsed_host.lower().rstrip(".")
    if not host or any(ch.isspace() for ch in host):
        _fail("INVALID_ENDPOINT", "endpoint allowlist entry must be a host authority")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if any(not (label and len(label) <= 63 and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)) for label in host.split(".")):
            _fail("INVALID_ENDPOINT", "endpoint allowlist entry must be a host authority")
        canonical_host = host
    else:
        canonical_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    if parsed_port is not None and not 1 <= parsed_port <= 65535:
        _fail("INVALID_ENDPOINT", "endpoint allowlist port is invalid")
    return canonical_host + (f":{parsed_port}" if parsed_port is not None else "")


def validate_plugin_endpoint(endpoint: str, locality: str, allowed_hosts: Sequence[str] = ()) -> str:
    """Validate a configured HTTP endpoint without DNS resolution."""
    endpoint = _validated_text(endpoint, "INVALID_ENDPOINT", "plugin endpoint is invalid", allow_empty=False)
    try:
        parsed = urlsplit(endpoint)
        parsed_host = parsed.hostname
        parsed_port = parsed.port
    except ValueError:
        _fail("INVALID_ENDPOINT", "plugin endpoint must be an absolute HTTP URL")
    if parsed.scheme not in {"http", "https"} or not parsed_host or parsed.username or parsed.password or parsed.fragment:
        _fail("INVALID_ENDPOINT", "plugin endpoint must be an absolute HTTP URL")
    if parsed_port is not None and not 1 <= parsed_port <= 65535:
        _fail("INVALID_ENDPOINT", "plugin endpoint port is invalid")
    host = parsed_host.lower().rstrip(".")
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        _fail("INVALID_ENDPOINT", "plugin endpoint host must be ASCII")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if locality == "same_host":
        if address is None or not address.is_loopback:
            _fail("LOCALITY_DENIED", "same_host endpoint must be loopback")
    elif locality == "same_network":
        if (
            type(allowed_hosts) not in (list, tuple)
            or not allowed_hosts
            or len(allowed_hosts) > MAX_ALLOWED_HOSTS
        ):
            _fail("LOCALITY_DENIED", "same_network requires an explicit host allowlist")
        canonical = []
        for item in allowed_hosts:
            authority = _host_authority(item)
            if authority in canonical:
                _fail("INVALID_ENDPOINT", "endpoint allowlist entries must be unique")
            canonical.append(authority)
        endpoint_host = f"[{address.compressed}]" if address is not None and address.version == 6 else host
        endpoint_authority = endpoint_host + (f":{parsed_port}" if parsed_port is not None else "")
        if endpoint_authority not in canonical:
            _fail("LOCALITY_DENIED", "endpoint host is not explicitly allowed")
    else:
        _fail("INVALID_SERVE", "serve.locality is invalid")
    return endpoint


def _freeze(value: Any) -> Any:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _validated_existing_plugin_ids(value: Any) -> frozenset[str]:
    """Copy only a small exact built-in collection of valid plugin IDs."""
    message = "existing_plugin_ids must be a bounded unique list or tuple of plugin ids"
    if type(value) not in (list, tuple) or len(value) > MAX_EXISTING_PLUGIN_IDS:
        _fail("INVALID_EXISTING_PLUGIN_IDS", message)
    validated = set()
    for plugin_id in value:
        if type(plugin_id) is not str:
            _fail("INVALID_EXISTING_PLUGIN_IDS", message)
        try:
            encoded = plugin_id.encode("ascii")
        except UnicodeEncodeError:
            _fail("INVALID_EXISTING_PLUGIN_IDS", message)
        if (
            not encoded
            or len(encoded) > MAX_TEXT
            or any(byte < 32 or byte == 127 for byte in encoded)
            or not _PLUGIN_ID.fullmatch(plugin_id)
            or plugin_id in validated
        ):
            _fail("INVALID_EXISTING_PLUGIN_IDS", message)
        validated.add(plugin_id)
    return frozenset(validated)


def adopt_plugin_manifest(data: Mapping[str, Any], *, artifact_path: Optional[os.PathLike[str] | str] = None, endpoint: Optional[str] = None, allowed_hosts: Sequence[str] = (), existing_plugin_ids: Sequence[str] = ()) -> AdoptedPluginManifest:
    """Validate and optionally verify local inputs; start, install, and load nothing."""
    manifest = validate_plugin_manifest(data)
    existing_ids = _validated_existing_plugin_ids(existing_plugin_ids)
    if manifest["plugin"]["id"] in existing_ids:
        _fail("DUPLICATE_PLUGIN_ID", "plugin.id is already adopted")
    namespace = manifest["plugin"]["namespace"]
    endpoint_env, token_env = plugin_environment_names(namespace)
    actual = None
    if endpoint is not None:
        validate_plugin_endpoint(endpoint, manifest["serve"]["locality"], allowed_hosts)
    if artifact_path is not None:
        actual = verify_plugin_artifact(artifact_path, manifest["artifact"]["digest"])
    return AdoptedPluginManifest(_freeze(manifest), endpoint_env, token_env, actual)
