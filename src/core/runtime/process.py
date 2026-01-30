"""
Plugin Process Management

Handles subprocess lifecycle for plugin execution.
"""

import asyncio
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from .protocol import (
    ProtocolEncoder,
    ProtocolDecoder,
    JsonRpcResponse,
    PROTOCOL_VERSION,
)
from .exceptions import (
    PluginCrashedError,
    PluginTimeoutError,
    PluginProtocolError,
)

logger = logging.getLogger(__name__)


class ProcessStatus(Enum):
    """Status of a plugin process."""
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    UNHEALTHY = "unhealthy"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class ProcessConfig:
    """Configuration for plugin process."""
    plugin_id: str
    plugin_dir: Path
    entry_point: str = "main.py"
    python_executable: str = "python3"
    env: Dict[str, str] = field(default_factory=dict)

    # Timeouts
    handshake_timeout_ms: int = 5000
    invoke_timeout_ms: int = 30000
    shutdown_timeout_ms: int = 5000

    # Resource limits
    max_memory_mb: int = 512
    max_cpu_percent: int = 100


@dataclass
class RestartPolicy:
    """Restart policy for crashed plugins."""
    max_restarts: int = 3
    restart_window_seconds: int = 60
    backoff_seconds: List[int] = field(default_factory=lambda: [1, 2, 4])
    unhealthy_cooldown_seconds: int = 300


class PluginProcess:
    """
    Manages a single plugin subprocess.

    Handles:
    - Process lifecycle (start, stop, restart)
    - JSON-RPC communication over stdio
    - Health checking
    - Crash detection and restart policy
    """

    def __init__(
        self,
        config: ProcessConfig,
        restart_policy: Optional[RestartPolicy] = None,
    ):
        self.config = config
        self.restart_policy = restart_policy or RestartPolicy()

        self._process: Optional[asyncio.subprocess.Process] = None
        self._status = ProcessStatus.STOPPED
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}

        # Restart tracking
        self._restart_times: List[float] = []
        self._unhealthy_until: Optional[float] = None

        # Reader task
        self._reader_task: Optional[asyncio.Task] = None

        # Callbacks
        self._on_crash: Optional[Callable] = None
        self._on_message: Optional[Callable] = None

    @property
    def status(self) -> ProcessStatus:
        """Get current process status."""
        return self._status

    @property
    def is_ready(self) -> bool:
        """Check if process is ready for invocations."""
        return self._status == ProcessStatus.READY

    @property
    def is_unhealthy(self) -> bool:
        """Check if process is marked unhealthy."""
        if self._status == ProcessStatus.UNHEALTHY:
            # Check if cooldown has passed
            if self._unhealthy_until and time.time() >= self._unhealthy_until:
                self._status = ProcessStatus.STOPPED
                self._unhealthy_until = None
                self._restart_times.clear()
                return False
            return True
        return False

    def _next_request_id(self) -> int:
        """Generate next request ID."""
        self._request_id += 1
        return self._request_id

    async def start(self) -> bool:
        """
        Start the plugin process.

        Returns:
            True if started successfully, False otherwise
        """
        if self.is_unhealthy:
            remaining = int(self._unhealthy_until - time.time()) if self._unhealthy_until else 0
            logger.warning(
                f"Plugin {self.config.plugin_id} is unhealthy, cooldown: {remaining}s"
            )
            return False

        if self._process is not None:
            logger.warning(f"Plugin {self.config.plugin_id} already running")
            return True

        self._status = ProcessStatus.STARTING

        try:
            # Build command
            entry_path = self.config.plugin_dir / self.config.entry_point
            cmd = [self.config.python_executable, str(entry_path)]

            # Build environment
            env = os.environ.copy()
            env.update(self.config.env)
            env["FLYTO_PLUGIN_ID"] = self.config.plugin_id
            env["FLYTO_PROTOCOL_VERSION"] = PROTOCOL_VERSION

            logger.info(f"Starting plugin process: {self.config.plugin_id}")

            # Start subprocess
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.config.plugin_dir),
                env=env,
            )

            # Start reader task
            self._reader_task = asyncio.create_task(self._read_stdout())

            # Perform handshake
            success = await self._handshake()
            if success:
                self._status = ProcessStatus.READY
                logger.info(f"Plugin {self.config.plugin_id} ready")
                return True
            else:
                await self.stop()
                return False

        except Exception as e:
            logger.error(f"Failed to start plugin {self.config.plugin_id}: {e}")
            self._status = ProcessStatus.STOPPED
            return False

    async def stop(self, reason: str = "shutdown", grace_period_ms: int = 5000):
        """
        Stop the plugin process gracefully.

        Args:
            reason: Reason for shutdown
            grace_period_ms: Grace period before force kill
        """
        if self._process is None:
            return

        self._status = ProcessStatus.SHUTTING_DOWN

        try:
            # Send shutdown command
            request_id = self._next_request_id()
            msg = ProtocolEncoder.encode_shutdown(reason, grace_period_ms, request_id)
            await self._send(msg)

            # Wait for graceful shutdown
            try:
                await asyncio.wait_for(
                    self._process.wait(),
                    timeout=grace_period_ms / 1000.0,
                )
                logger.info(f"Plugin {self.config.plugin_id} shut down gracefully")
            except asyncio.TimeoutError:
                logger.warning(f"Plugin {self.config.plugin_id} did not shutdown, killing")
                self._process.terminate()
                await asyncio.sleep(1)
                if self._process.returncode is None:
                    self._process.kill()

        except Exception as e:
            logger.error(f"Error stopping plugin {self.config.plugin_id}: {e}")
            if self._process and self._process.returncode is None:
                self._process.kill()

        finally:
            # Cancel reader task
            if self._reader_task:
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass

            self._process = None
            self._reader_task = None
            self._status = ProcessStatus.STOPPED

            # Cancel pending requests
            for future in self._pending_requests.values():
                if not future.done():
                    future.cancel()
            self._pending_requests.clear()

    async def invoke(
        self,
        step: str,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any],
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a step on the plugin.

        Args:
            step: Step ID to invoke
            input_data: Input parameters
            config: Static configuration
            context: Execution context
            timeout_ms: Timeout (uses config default if not specified)

        Returns:
            Result dictionary

        Raises:
            PluginCrashedError: If plugin crashed
            PluginTimeoutError: If invocation timed out
            PluginProtocolError: If protocol error
        """
        if not self.is_ready:
            if not await self.start():
                raise PluginCrashedError(self.config.plugin_id)

        timeout = timeout_ms or self.config.invoke_timeout_ms
        request_id = self._next_request_id()

        # Create future for response
        future: asyncio.Future = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            self._status = ProcessStatus.BUSY

            # Send invoke request
            msg = ProtocolEncoder.encode_invoke(
                step, input_data, config, context, request_id, timeout
            )
            await self._send(msg)

            # Wait for response
            try:
                response = await asyncio.wait_for(
                    future,
                    timeout=timeout / 1000.0,
                )
                return ProtocolDecoder.extract_result(response)

            except asyncio.TimeoutError:
                raise PluginTimeoutError(self.config.plugin_id, step, timeout)

        finally:
            self._pending_requests.pop(request_id, None)
            if self._status == ProcessStatus.BUSY:
                self._status = ProcessStatus.READY

    async def ping(self, timeout_ms: int = 5000) -> bool:
        """
        Health check the plugin.

        Args:
            timeout_ms: Timeout for ping response

        Returns:
            True if healthy, False otherwise
        """
        if self._process is None or self._process.returncode is not None:
            return False

        request_id = self._next_request_id()
        future: asyncio.Future = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            msg = ProtocolEncoder.encode_ping(request_id)
            await self._send(msg)

            await asyncio.wait_for(future, timeout=timeout_ms / 1000.0)
            return True

        except (asyncio.TimeoutError, Exception):
            return False

        finally:
            self._pending_requests.pop(request_id, None)

    async def _handshake(self) -> bool:
        """Perform protocol handshake."""
        request_id = self._next_request_id()
        future: asyncio.Future = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            msg = ProtocolEncoder.encode_handshake(
                PROTOCOL_VERSION,
                self.config.plugin_id,
                "startup",
                request_id,
            )
            await self._send(msg)

            response = await asyncio.wait_for(
                future,
                timeout=self.config.handshake_timeout_ms / 1000.0,
            )

            if response.is_success:
                result = response.result or {}
                plugin_version = result.get("pluginVersion", "unknown")
                logger.info(
                    f"Handshake complete: {self.config.plugin_id} v{plugin_version}"
                )
                return True
            else:
                logger.error(f"Handshake failed: {response.error}")
                return False

        except asyncio.TimeoutError:
            logger.error(f"Handshake timeout: {self.config.plugin_id}")
            return False

        except Exception as e:
            logger.error(f"Handshake error: {e}")
            return False

        finally:
            self._pending_requests.pop(request_id, None)

    async def _send(self, message: str):
        """Send message to plugin stdin."""
        if self._process and self._process.stdin:
            data = (message + "\n").encode("utf-8")
            self._process.stdin.write(data)
            await self._process.stdin.drain()

    async def _read_stdout(self):
        """Read and process messages from plugin stdout."""
        if not self._process or not self._process.stdout:
            return

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    # Process ended
                    await self._handle_crash()
                    break

                try:
                    data = line.decode("utf-8").strip()
                    if not data:
                        continue

                    response = ProtocolDecoder.decode_response(data)

                    # Find pending request
                    future = self._pending_requests.get(response.id)
                    if future and not future.done():
                        future.set_result(response)

                except Exception as e:
                    logger.error(f"Error processing plugin output: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Reader task error: {e}")
            await self._handle_crash()

    async def _handle_crash(self):
        """Handle plugin crash."""
        exit_code = self._process.returncode if self._process else None
        logger.error(f"Plugin {self.config.plugin_id} crashed (exit: {exit_code})")

        # Record restart time
        self._restart_times.append(time.time())

        # Clean up old restart times
        cutoff = time.time() - self.restart_policy.restart_window_seconds
        self._restart_times = [t for t in self._restart_times if t > cutoff]

        # Check if exceeded max restarts
        if len(self._restart_times) >= self.restart_policy.max_restarts:
            self._status = ProcessStatus.UNHEALTHY
            self._unhealthy_until = time.time() + self.restart_policy.unhealthy_cooldown_seconds
            logger.error(
                f"Plugin {self.config.plugin_id} marked unhealthy "
                f"(cooldown: {self.restart_policy.unhealthy_cooldown_seconds}s)"
            )
        else:
            self._status = ProcessStatus.STOPPED

        # Cancel pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(
                    PluginCrashedError(self.config.plugin_id, exit_code)
                )
        self._pending_requests.clear()

        self._process = None

        # Notify callback
        if self._on_crash:
            try:
                self._on_crash(self.config.plugin_id, exit_code)
            except Exception as e:
                logger.error(f"Crash callback error: {e}")
