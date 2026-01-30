"""
Runtime Configuration

Loads and manages runtime configuration from files and environment.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default configuration file path
DEFAULT_CONFIG_PATH = "/etc/flyto/runtime.yaml"


@dataclass
class ProcessConfig:
    """Process lifecycle configuration."""
    start_policy: str = "lazy"  # lazy, eager
    idle_timeout_seconds: int = 300
    min_processes: int = 0
    max_processes: int = 2


@dataclass
class ConcurrencyConfig:
    """Concurrency configuration."""
    mode: str = "queue_then_scale"
    max_queue_length: int = 50
    scale_up_queue_threshold: int = 10
    per_process_max_concurrent_invokes: int = 1


@dataclass
class RestartPolicyConfig:
    """Restart policy configuration."""
    max_restarts: int = 3
    restart_window_seconds: int = 60
    backoff_seconds: List[int] = field(default_factory=lambda: [1, 2, 4])
    after_max_restarts: str = "mark_unhealthy"
    unhealthy_cooldown_seconds: int = 300


@dataclass
class HealthCheckConfig:
    """Health check configuration."""
    enabled: bool = True
    interval_seconds: int = 30
    timeout_seconds: int = 5
    method: str = "ping"


@dataclass
class SecretsConfig:
    """Secrets handling configuration."""
    mode: str = "proxy"  # proxy, direct (NOT RECOMMENDED)
    allow_direct_for_verified: bool = False
    ref_ttl_seconds: int = 60
    max_resolutions_per_ref: int = 1


@dataclass
class MeteringConfig:
    """Metering and billing configuration."""
    bill_on: str = "success_only"  # success_only, all_except_validation
    retry_attempts_billed: bool = False
    batch_mode: str = "per_item"  # per_item, per_invoke
    cost_class_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "free": 0.0,
        "standard": 1.0,
        "premium": 3.0,
        "enterprise": 10.0,
    })


@dataclass
class RoutingConfig:
    """Module routing configuration."""
    default_prefer: str = "plugin"  # plugin, legacy
    default_fallback: str = "legacy"  # legacy, error
    force_plugin_default: bool = False
    overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class ProtocolConfig:
    """Protocol configuration."""
    version: str = "0.1.0"
    transport: str = "stdio"
    encoding: str = "utf-8"
    frame_delimiter: str = "newline"
    handshake_timeout_ms: int = 5000
    default_invoke_timeout_ms: int = 30000
    shutdown_grace_ms: int = 5000


@dataclass
class PathsConfig:
    """File path configuration."""
    plugin_dir: str = "/plugins"
    manifest_filename: str = "plugin.manifest.json"
    log_dir: str = "/var/log/flyto/plugins"


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "info"
    capture_stderr: bool = True
    max_log_size_bytes: int = 10485760  # 10MB
    rotate_count: int = 5


@dataclass
class MultiTenantConfig:
    """Multi-tenant configuration."""
    default_tier: str = "shared_pool"
    dedicated_tiers: List[str] = field(default_factory=lambda: ["team", "enterprise"])
    max_dedicated_pools: int = 100


@dataclass
class RuntimeConfig:
    """Complete runtime configuration."""
    process: ProcessConfig = field(default_factory=ProcessConfig)
    concurrency: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)
    restart_policy: RestartPolicyConfig = field(default_factory=RestartPolicyConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig)
    metering: MeteringConfig = field(default_factory=MeteringConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    multi_tenant: MultiTenantConfig = field(default_factory=MultiTenantConfig)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "RuntimeConfig":
        """
        Load configuration from file and environment.

        Args:
            config_path: Path to config file (default: /etc/flyto/runtime.yaml)

        Returns:
            RuntimeConfig with merged values
        """
        path = config_path or DEFAULT_CONFIG_PATH

        # Start with defaults
        data: Dict[str, Any] = {}

        # Load from file if exists
        if os.path.exists(path):
            try:
                import yaml
                with open(path) as f:
                    file_data = yaml.safe_load(f) or {}
                data = file_data
                logger.info(f"Loaded config from {path}")
            except ImportError:
                logger.warning("PyYAML not installed, using defaults")
            except Exception as e:
                logger.error(f"Failed to load config from {path}: {e}")

        # Apply environment variable overrides
        data = cls._apply_env_overrides(data)

        # Build config object
        return cls._from_dict(data)

    @classmethod
    def _apply_env_overrides(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply FLYTO_RUNTIME_* environment variables."""
        prefix = "FLYTO_RUNTIME_"

        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue

            # Parse path from key
            # e.g., FLYTO_RUNTIME_PROCESS_START_POLICY -> process.start_policy
            path_parts = key[len(prefix):].lower().split("_")

            # Convert to nested dict path
            cls._set_nested(data, path_parts, cls._parse_env_value(value))

        return data

    @staticmethod
    def _set_nested(data: Dict, path: List[str], value: Any):
        """Set a nested dictionary value."""
        for part in path[:-1]:
            if part not in data:
                data[part] = {}
            data = data[part]
        if path:
            data[path[-1]] = value

    @staticmethod
    def _parse_env_value(value: str) -> Any:
        """Parse environment variable value to appropriate type."""
        # Boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # Integer
        try:
            return int(value)
        except ValueError:
            pass

        # Float
        try:
            return float(value)
        except ValueError:
            pass

        # List (comma-separated)
        if "," in value:
            return [v.strip() for v in value.split(",")]

        # String
        return value

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "RuntimeConfig":
        """Create RuntimeConfig from dictionary."""
        return cls(
            process=cls._build_process_config(data.get("process", {})),
            concurrency=cls._build_concurrency_config(data.get("concurrency", {})),
            restart_policy=cls._build_restart_policy_config(data.get("restart_policy", data.get("restartPolicy", {}))),
            health_check=cls._build_health_check_config(data.get("health_check", data.get("healthCheck", {}))),
            secrets=cls._build_secrets_config(data.get("secrets", {})),
            metering=cls._build_metering_config(data.get("metering", {})),
            routing=cls._build_routing_config(data.get("routing", {})),
            protocol=cls._build_protocol_config(data.get("protocol", {})),
            paths=cls._build_paths_config(data.get("paths", {})),
            logging=cls._build_logging_config(data.get("logging", {})),
            multi_tenant=cls._build_multi_tenant_config(data.get("multi_tenant", data.get("multiTenant", {}))),
        )

    @staticmethod
    def _build_process_config(data: Dict) -> ProcessConfig:
        return ProcessConfig(
            start_policy=data.get("start_policy", data.get("startPolicy", "lazy")),
            idle_timeout_seconds=data.get("idle_timeout_seconds", data.get("idleTimeoutSeconds", 300)),
            min_processes=data.get("min_processes", data.get("minProcesses", 0)),
            max_processes=data.get("max_processes", data.get("maxProcesses", 2)),
        )

    @staticmethod
    def _build_concurrency_config(data: Dict) -> ConcurrencyConfig:
        return ConcurrencyConfig(
            mode=data.get("mode", "queue_then_scale"),
            max_queue_length=data.get("max_queue_length", data.get("maxQueueLength", 50)),
            scale_up_queue_threshold=data.get("scale_up_queue_threshold", data.get("scaleUpQueueThreshold", 10)),
            per_process_max_concurrent_invokes=data.get("per_process_max_concurrent_invokes", data.get("perProcessMaxConcurrentInvokes", 1)),
        )

    @staticmethod
    def _build_restart_policy_config(data: Dict) -> RestartPolicyConfig:
        return RestartPolicyConfig(
            max_restarts=data.get("max_restarts", data.get("maxRestarts", 3)),
            restart_window_seconds=data.get("restart_window_seconds", data.get("restartWindowSeconds", 60)),
            backoff_seconds=data.get("backoff_seconds", data.get("backoffSeconds", [1, 2, 4])),
            after_max_restarts=data.get("after_max_restarts", data.get("afterMaxRestarts", "mark_unhealthy")),
            unhealthy_cooldown_seconds=data.get("unhealthy_cooldown_seconds", data.get("unhealthyCooldownSeconds", 300)),
        )

    @staticmethod
    def _build_health_check_config(data: Dict) -> HealthCheckConfig:
        return HealthCheckConfig(
            enabled=data.get("enabled", True),
            interval_seconds=data.get("interval_seconds", data.get("intervalSeconds", 30)),
            timeout_seconds=data.get("timeout_seconds", data.get("timeoutSeconds", 5)),
            method=data.get("method", "ping"),
        )

    @staticmethod
    def _build_secrets_config(data: Dict) -> SecretsConfig:
        return SecretsConfig(
            mode=data.get("mode", "proxy"),
            allow_direct_for_verified=data.get("allow_direct_for_verified", data.get("allowDirectForVerified", False)),
            ref_ttl_seconds=data.get("ref_ttl_seconds", data.get("refTtlSeconds", 60)),
            max_resolutions_per_ref=data.get("max_resolutions_per_ref", data.get("maxResolutionsPerRef", 1)),
        )

    @staticmethod
    def _build_metering_config(data: Dict) -> MeteringConfig:
        return MeteringConfig(
            bill_on=data.get("bill_on", data.get("billOn", "success_only")),
            retry_attempts_billed=data.get("retry_attempts_billed", data.get("retryAttemptsBilled", False)),
            batch_mode=data.get("batch_mode", data.get("batchMode", "per_item")),
            cost_class_multipliers=data.get("cost_class_multipliers", data.get("costClassMultipliers", {
                "free": 0.0, "standard": 1.0, "premium": 3.0, "enterprise": 10.0
            })),
        )

    @staticmethod
    def _build_routing_config(data: Dict) -> RoutingConfig:
        return RoutingConfig(
            default_prefer=data.get("default_prefer", data.get("defaultPrefer", "plugin")),
            default_fallback=data.get("default_fallback", data.get("defaultFallback", "legacy")),
            force_plugin_default=data.get("force_plugin_default", data.get("forcePluginDefault", False)),
            overrides=data.get("overrides", {}),
        )

    @staticmethod
    def _build_protocol_config(data: Dict) -> ProtocolConfig:
        timeouts = data.get("timeouts", {})
        return ProtocolConfig(
            version=data.get("version", "0.1.0"),
            transport=data.get("transport", "stdio"),
            encoding=data.get("encoding", "utf-8"),
            frame_delimiter=data.get("frame_delimiter", data.get("frameDelimiter", "newline")),
            handshake_timeout_ms=timeouts.get("handshake_ms", timeouts.get("handshakeMs", 5000)),
            default_invoke_timeout_ms=timeouts.get("default_invoke_ms", timeouts.get("defaultInvokeMs", 30000)),
            shutdown_grace_ms=timeouts.get("shutdown_grace_ms", timeouts.get("shutdownGraceMs", 5000)),
        )

    @staticmethod
    def _build_paths_config(data: Dict) -> PathsConfig:
        return PathsConfig(
            plugin_dir=data.get("plugin_dir", data.get("pluginDir", "/plugins")),
            manifest_filename=data.get("manifest_filename", data.get("manifestFilename", "plugin.manifest.json")),
            log_dir=data.get("log_dir", data.get("logDir", "/var/log/flyto/plugins")),
        )

    @staticmethod
    def _build_logging_config(data: Dict) -> LoggingConfig:
        return LoggingConfig(
            level=data.get("level", "info"),
            capture_stderr=data.get("capture_stderr", data.get("captureStderr", True)),
            max_log_size_bytes=data.get("max_log_size_bytes", data.get("maxLogSizeBytes", 10485760)),
            rotate_count=data.get("rotate_count", data.get("rotateCount", 5)),
        )

    @staticmethod
    def _build_multi_tenant_config(data: Dict) -> MultiTenantConfig:
        return MultiTenantConfig(
            default_tier=data.get("default_tier", data.get("defaultTier", "shared_pool")),
            dedicated_tiers=data.get("dedicated_tiers", data.get("dedicatedTiers", ["team", "enterprise"])),
            max_dedicated_pools=data.get("max_dedicated_pools", data.get("maxDedicatedPools", 100)),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "process": {
                "startPolicy": self.process.start_policy,
                "idleTimeoutSeconds": self.process.idle_timeout_seconds,
                "minProcesses": self.process.min_processes,
                "maxProcesses": self.process.max_processes,
            },
            "restartPolicy": {
                "maxRestarts": self.restart_policy.max_restarts,
                "restartWindowSeconds": self.restart_policy.restart_window_seconds,
                "backoffSeconds": self.restart_policy.backoff_seconds,
                "afterMaxRestarts": self.restart_policy.after_max_restarts,
                "unhealthyCooldownSeconds": self.restart_policy.unhealthy_cooldown_seconds,
            },
            "healthCheck": {
                "enabled": self.health_check.enabled,
                "intervalSeconds": self.health_check.interval_seconds,
                "timeoutSeconds": self.health_check.timeout_seconds,
                "method": self.health_check.method,
            },
            "secrets": {
                "mode": self.secrets.mode,
                "allowDirectForVerified": self.secrets.allow_direct_for_verified,
            },
            "metering": {
                "billOn": self.metering.bill_on,
                "retryAttemptsBilled": self.metering.retry_attempts_billed,
                "batchMode": self.metering.batch_mode,
            },
            "routing": {
                "defaultPrefer": self.routing.default_prefer,
                "defaultFallback": self.routing.default_fallback,
                "forcePluginDefault": self.routing.force_plugin_default,
            },
        }


# Global singleton
_config: Optional[RuntimeConfig] = None


def get_config() -> RuntimeConfig:
    """Get global runtime configuration."""
    global _config
    if _config is None:
        _config = RuntimeConfig.load()
    return _config


def reload_config(config_path: Optional[str] = None) -> RuntimeConfig:
    """Reload configuration from file."""
    global _config
    _config = RuntimeConfig.load(config_path)
    return _config
