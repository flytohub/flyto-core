"""
Module Versioning System

Provides versioned module management:
- Multiple versions of same module
- Semver-based version resolution
- Workflow version locking
- Version migration support

This is a capability n8n does well - we adopt the pattern.

Design principles:
- Backward compatible: Unversioned calls get latest
- Flexible: Support exact, caret, tilde matching
- Safe: Version locks prevent breaking changes
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)


class VersionMatchMode(str, Enum):
    """Version matching modes"""
    EXACT = "exact"           # 1.2.3 - exact version
    CARET = "caret"           # ^1.2.3 - compatible with 1.x.x
    TILDE = "tilde"           # ~1.2.3 - compatible with 1.2.x
    GREATER = "greater"       # >1.2.3 - greater than
    GREATER_EQ = "greater_eq" # >=1.2.3 - greater or equal
    LESS = "less"             # <1.2.3 - less than
    LESS_EQ = "less_eq"       # <=1.2.3 - less or equal
    LATEST = "latest"         # * or latest - any version


@dataclass
class SemVer:
    """
    Semantic version representation.

    Attributes:
        major: Major version (breaking changes)
        minor: Minor version (new features)
        patch: Patch version (bug fixes)
        prerelease: Pre-release tag (alpha, beta, rc)
        build: Build metadata
    """
    major: int
    minor: int
    patch: int
    prerelease: Optional[str] = None
    build: Optional[str] = None

    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        if self.build:
            version += f"+{self.build}"
        return version

    def __lt__(self, other: "SemVer") -> bool:
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.patch != other.patch:
            return self.patch < other.patch
        # Pre-release versions are less than release
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        if self.prerelease and other.prerelease:
            return self.prerelease < other.prerelease
        return False

    def __le__(self, other: "SemVer") -> bool:
        return self == other or self < other

    def __gt__(self, other: "SemVer") -> bool:
        return not self <= other

    def __ge__(self, other: "SemVer") -> bool:
        return not self < other

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return False
        return (
            self.major == other.major and
            self.minor == other.minor and
            self.patch == other.patch and
            self.prerelease == other.prerelease
        )

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))

    @classmethod
    def parse(cls, version_str: str) -> "SemVer":
        """Parse version string to SemVer"""
        # Remove leading v
        version_str = version_str.lstrip('v')

        # Handle build metadata
        build = None
        if '+' in version_str:
            version_str, build = version_str.rsplit('+', 1)

        # Handle prerelease
        prerelease = None
        if '-' in version_str:
            version_str, prerelease = version_str.split('-', 1)

        # Parse version numbers
        parts = version_str.split('.')
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0

        return cls(
            major=major,
            minor=minor,
            patch=patch,
            prerelease=prerelease,
            build=build,
        )

    def is_compatible_caret(self, other: "SemVer") -> bool:
        """Check caret compatibility (^X.Y.Z)"""
        if self.major == 0:
            # 0.x.x - minor must match
            return self.major == other.major and self.minor == other.minor
        # Major must match
        return self.major == other.major

    def is_compatible_tilde(self, other: "SemVer") -> bool:
        """Check tilde compatibility (~X.Y.Z)"""
        return self.major == other.major and self.minor == other.minor


@dataclass
class VersionConstraint:
    """
    Version constraint for resolution.

    Supports:
    - "1.2.3" - exact version
    - "^1.2.3" - caret (major compatible)
    - "~1.2.3" - tilde (minor compatible)
    - ">1.2.3" - greater than
    - ">=1.2.3" - greater or equal
    - "<1.2.3" - less than
    - "<=1.2.3" - less or equal
    - "*" or "latest" - any version
    """
    mode: VersionMatchMode
    version: Optional[SemVer] = None

    @classmethod
    def parse(cls, constraint_str: str) -> "VersionConstraint":
        """Parse constraint string"""
        constraint_str = constraint_str.strip()

        if constraint_str in ('*', 'latest', ''):
            return cls(mode=VersionMatchMode.LATEST)

        if constraint_str.startswith('^'):
            return cls(
                mode=VersionMatchMode.CARET,
                version=SemVer.parse(constraint_str[1:]),
            )

        if constraint_str.startswith('~'):
            return cls(
                mode=VersionMatchMode.TILDE,
                version=SemVer.parse(constraint_str[1:]),
            )

        if constraint_str.startswith('>='):
            return cls(
                mode=VersionMatchMode.GREATER_EQ,
                version=SemVer.parse(constraint_str[2:]),
            )

        if constraint_str.startswith('<='):
            return cls(
                mode=VersionMatchMode.LESS_EQ,
                version=SemVer.parse(constraint_str[2:]),
            )

        if constraint_str.startswith('>'):
            return cls(
                mode=VersionMatchMode.GREATER,
                version=SemVer.parse(constraint_str[1:]),
            )

        if constraint_str.startswith('<'):
            return cls(
                mode=VersionMatchMode.LESS,
                version=SemVer.parse(constraint_str[1:]),
            )

        # Exact version
        return cls(
            mode=VersionMatchMode.EXACT,
            version=SemVer.parse(constraint_str),
        )

    def matches(self, version: SemVer) -> bool:
        """Check if version matches constraint"""
        if self.mode == VersionMatchMode.LATEST:
            return True

        if self.version is None:
            return True

        if self.mode == VersionMatchMode.EXACT:
            return version == self.version

        if self.mode == VersionMatchMode.CARET:
            return (
                version >= self.version and
                self.version.is_compatible_caret(version)
            )

        if self.mode == VersionMatchMode.TILDE:
            return (
                version >= self.version and
                self.version.is_compatible_tilde(version)
            )

        if self.mode == VersionMatchMode.GREATER:
            return version > self.version

        if self.mode == VersionMatchMode.GREATER_EQ:
            return version >= self.version

        if self.mode == VersionMatchMode.LESS:
            return version < self.version

        if self.mode == VersionMatchMode.LESS_EQ:
            return version <= self.version

        return False


class VersionedModuleRegistry:
    """
    Registry for versioned modules.

    Manages multiple versions of modules and provides version-aware resolution.

    Usage:
        registry = VersionedModuleRegistry()

        # Register versions
        registry.register("flow.loop", "1.0.0", LoopV1)
        registry.register("flow.loop", "2.0.0", LoopV2)

        # Get specific version
        module = registry.get("flow.loop", "2.0.0")

        # Get compatible version
        module = registry.get("flow.loop", "^1.0.0")

        # Get latest
        module = registry.get("flow.loop", "latest")
    """

    def __init__(self):
        # module_id -> version -> module_class
        self._versions: Dict[str, Dict[str, Type]] = {}
        # module_id -> version -> metadata
        self._metadata: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # module_id -> sorted version list (descending)
        self._sorted_versions: Dict[str, List[SemVer]] = {}

    def register(
        self,
        module_id: str,
        version: str,
        module_class: Type,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a versioned module.

        Args:
            module_id: Module identifier (e.g., "flow.loop")
            version: Semver version string (e.g., "2.0.0")
            module_class: Module class
            metadata: Optional metadata
        """
        if module_id not in self._versions:
            self._versions[module_id] = {}
            self._metadata[module_id] = {}
            self._sorted_versions[module_id] = []

        semver = SemVer.parse(version)
        version_key = str(semver)

        self._versions[module_id][version_key] = module_class

        if metadata:
            metadata['version'] = version_key
            self._metadata[module_id][version_key] = metadata

        # Update sorted versions
        self._sorted_versions[module_id].append(semver)
        self._sorted_versions[module_id].sort(reverse=True)

        logger.debug(f"Registered {module_id}@{version_key}")

    def unregister(
        self,
        module_id: str,
        version: Optional[str] = None,
    ) -> None:
        """
        Unregister a module version or all versions.

        Args:
            module_id: Module identifier
            version: Specific version to remove, or None for all
        """
        if module_id not in self._versions:
            return

        if version:
            semver = SemVer.parse(version)
            version_key = str(semver)

            if version_key in self._versions[module_id]:
                del self._versions[module_id][version_key]
                self._metadata[module_id].pop(version_key, None)
                self._sorted_versions[module_id] = [
                    v for v in self._sorted_versions[module_id]
                    if str(v) != version_key
                ]
        else:
            del self._versions[module_id]
            self._metadata.pop(module_id, None)
            self._sorted_versions.pop(module_id, None)

    def get(
        self,
        module_id: str,
        version_constraint: str = "latest",
    ) -> Optional[Type]:
        """
        Get module class matching version constraint.

        Args:
            module_id: Module identifier
            version_constraint: Version constraint string

        Returns:
            Module class or None if not found
        """
        if module_id not in self._versions:
            return None

        constraint = VersionConstraint.parse(version_constraint)
        sorted_versions = self._sorted_versions.get(module_id, [])

        # Find best matching version
        for semver in sorted_versions:
            if constraint.matches(semver):
                version_key = str(semver)
                return self._versions[module_id].get(version_key)

        return None

    def get_metadata(
        self,
        module_id: str,
        version_constraint: str = "latest",
    ) -> Optional[Dict[str, Any]]:
        """Get metadata for matching version"""
        if module_id not in self._metadata:
            return None

        constraint = VersionConstraint.parse(version_constraint)
        sorted_versions = self._sorted_versions.get(module_id, [])

        for semver in sorted_versions:
            if constraint.matches(semver):
                version_key = str(semver)
                return self._metadata[module_id].get(version_key)

        return None

    def list_versions(self, module_id: str) -> List[str]:
        """List all versions of a module"""
        return [
            str(v) for v in self._sorted_versions.get(module_id, [])
        ]

    def get_latest_version(self, module_id: str) -> Optional[str]:
        """Get latest version string"""
        versions = self._sorted_versions.get(module_id, [])
        if versions:
            return str(versions[0])
        return None

    def has(self, module_id: str, version: Optional[str] = None) -> bool:
        """Check if module/version exists"""
        if module_id not in self._versions:
            return False
        if version:
            return version in self._versions[module_id]
        return True

    def list_modules(self) -> List[str]:
        """List all module IDs"""
        return list(self._versions.keys())


# =============================================================================
# Module ID Parsing
# =============================================================================

def parse_module_reference(ref: str) -> Tuple[str, Optional[str]]:
    """
    Parse module reference with optional version.

    Supports:
    - "flow.loop" -> ("flow.loop", None)
    - "flow.loop@2.0.0" -> ("flow.loop", "2.0.0")
    - "flow.loop@^1.0.0" -> ("flow.loop", "^1.0.0")

    Args:
        ref: Module reference string

    Returns:
        Tuple of (module_id, version_constraint)
    """
    if '@' in ref:
        parts = ref.split('@', 1)
        return parts[0], parts[1]
    return ref, None


# =============================================================================
# Workflow Version Lock
# =============================================================================

@dataclass
class WorkflowVersionLock:
    """
    Version locks for a workflow.

    Ensures consistent module versions across executions.

    Example:
        locks = WorkflowVersionLock()
        locks.add("flow.loop", "2.0.0")
        locks.add("browser.click", "^1.0.0")

        # Resolve module
        version = locks.resolve("flow.loop")  # "2.0.0"
    """
    locks: Dict[str, str] = field(default_factory=dict)

    def add(self, module_id: str, version_constraint: str) -> None:
        """Add a version lock"""
        self.locks[module_id] = version_constraint

    def remove(self, module_id: str) -> None:
        """Remove a version lock"""
        self.locks.pop(module_id, None)

    def resolve(self, module_id: str) -> Optional[str]:
        """Get locked version for module"""
        return self.locks.get(module_id)

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary"""
        return dict(self.locks)

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "WorkflowVersionLock":
        """Create from dictionary"""
        return cls(locks=dict(data))

    @classmethod
    def from_workflow(cls, workflow: Dict[str, Any]) -> "WorkflowVersionLock":
        """Extract version locks from workflow definition"""
        locks = cls()

        # From version_locks field
        version_locks = workflow.get('version_locks', {})
        for module_id, version in version_locks.items():
            locks.add(module_id, version)

        # From step definitions (module@version)
        for step in workflow.get('steps', []):
            module_ref = step.get('module', '')
            module_id, version = parse_module_reference(module_ref)
            if version:
                locks.add(module_id, version)

        return locks


# =============================================================================
# Global Instance
# =============================================================================

_versioned_registry: Optional[VersionedModuleRegistry] = None


def get_versioned_registry() -> VersionedModuleRegistry:
    """Get global versioned registry instance"""
    global _versioned_registry
    if _versioned_registry is None:
        _versioned_registry = VersionedModuleRegistry()
    return _versioned_registry


def register_versioned_module(
    module_id: str,
    version: str,
    module_class: Type,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Register a versioned module to global registry"""
    get_versioned_registry().register(module_id, version, module_class, metadata)


def get_versioned_module(
    module_id: str,
    version_constraint: str = "latest",
) -> Optional[Type]:
    """Get versioned module from global registry"""
    return get_versioned_registry().get(module_id, version_constraint)
