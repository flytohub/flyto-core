"""
Step Executor

Handles execution of individual workflow steps with item-based execution support.

SECURITY: Includes redaction of sensitive data from module outputs.

Item-Based Execution:
- Supports execution_mode: "single", "items", "all"
- Wraps legacy results via wrap_legacy_result()
- Stores items in context for downstream access
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..exceptions import StepTimeoutError, StepExecutionError
from ..hooks import ExecutorHooks, HookAction
from .context_builder import create_step_context
from .foreach import execute_foreach_step
from .retry import execute_with_retry

# Phase 0: Runtime invoker for future plugin support
# This import will be used when we transition to subprocess plugins
try:
    from ...runtime.invoke import get_invoker, parse_module_id
    _RUNTIME_INVOKER_AVAILABLE = True
except ImportError:
    _RUNTIME_INVOKER_AVAILABLE = False

if TYPE_CHECKING:
    from ..variable_resolver import VariableResolver
    from ...modules.items import Item, NodeExecutionResult, StepInputItems
    from ..trace import StepTrace, TraceCollector

logger = logging.getLogger(__name__)

# SECURITY: Patterns for sensitive keys that should be redacted from results
_SENSITIVE_KEY_PATTERN = re.compile(
    r'(?i)(api[_-]?key|secret|password|token|credential|auth|private[_-]?key|bearer|jwt)',
)


def _redact_sensitive_output(data: Any, depth: int = 0) -> Any:
    """
    Redact sensitive data from module output.

    SECURITY: Prevents secrets in module outputs from leaking to hooks or storage.
    Only redacts up to 10 levels deep to prevent infinite recursion.
    """
    if depth > 10:
        return data

    if data is None:
        return data

    if isinstance(data, str):
        # Don't redact regular strings - only check dict keys
        return data

    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            # Check if key name suggests sensitive data
            if _SENSITIVE_KEY_PATTERN.search(str(key)):
                redacted[key] = '[REDACTED]'
            else:
                redacted[key] = _redact_sensitive_output(value, depth + 1)
        return redacted

    if isinstance(data, (list, tuple)):
        return [_redact_sensitive_output(item, depth + 1) for item in data]

    return data


class StepExecutor:
    """
    Handles execution of individual workflow steps.

    Responsibilities:
    - Execute single steps with timeout
    - Handle foreach iteration
    - Implement retry logic with backoff
    - Integrate with executor hooks
    - Track execution results
    """

    def __init__(
        self,
        hooks: Optional[ExecutorHooks] = None,
        workflow_id: str = "unknown",
        workflow_name: str = "Unnamed Workflow",
        total_steps: int = 0,
    ):
        """
        Initialize step executor.

        Args:
            hooks: Optional executor hooks for lifecycle events
            workflow_id: ID of the parent workflow (for logging/hooks)
            workflow_name: Name of the parent workflow (for hooks)
            total_steps: Total number of steps in workflow (for hooks)
        """
        from ..hooks import NullHooks
        self._hooks = hooks or NullHooks()
        self._workflow_id = workflow_id
        self._workflow_name = workflow_name
        self._total_steps = total_steps

    def _create_step_context(
        self,
        step_config: Dict[str, Any],
        step_index: int,
        context: Dict[str, Any],
        result: Any = None,
        error: Optional[Exception] = None,
        attempt: int = 1,
        max_attempts: int = 1,
        step_start_time: Optional[float] = None,
    ):
        """Create hook context for step-level events."""
        return create_step_context(
            workflow_id=self._workflow_id,
            workflow_name=self._workflow_name,
            total_steps=self._total_steps,
            step_config=step_config,
            step_index=step_index,
            context=context,
            result=result,
            error=error,
            attempt=attempt,
            max_attempts=max_attempts,
            step_start_time=step_start_time,
        )

    async def execute_step(
        self,
        step_config: Dict[str, Any],
        step_index: int,
        context: Dict[str, Any],
        resolver: "VariableResolver",
        should_execute: bool = True,
        trace_collector: Optional["TraceCollector"] = None,
    ) -> Optional[Any]:
        """
        Execute a single step with timeout and foreach support.

        Args:
            step_config: Step configuration from workflow
            step_index: Index of the step
            context: Current workflow context (will be modified)
            resolver: Variable resolver instance
            should_execute: Whether the step should execute (from 'when' condition)
            trace_collector: Optional trace collector for execution tracing

        Returns:
            Step execution result, or None if skipped

        Raises:
            StepExecutionError: If step execution fails and on_error is 'stop'
        """
        step_id = step_config.get('id', f'step_{id(step_config)}')
        module_id = step_config.get('module')
        description = step_config.get('description', '')
        timeout = step_config.get('timeout', 0)
        foreach_array = step_config.get('foreach')
        foreach_var = step_config.get('as', 'item')

        # Data Pinning: Check for pinned output - skip execution if present
        pinned_output = step_config.get('pinned_output')
        if pinned_output is not None:
            logger.info(f"Step '{step_id}': Using pinned output (skipping execution)")

            # Record pinned output as a completed step trace
            if trace_collector and module_id:
                step_trace = trace_collector.start_step(step_id, step_index, module_id)
                params_raw = step_config.get('params', {})
                resolved_params = resolver.resolve(params_raw)
                step_trace.set_input(params=resolved_params, params_raw=params_raw)
                items_output = []
                if isinstance(pinned_output, dict):
                    items = pinned_output.get('items', [])
                    if items:
                        items_output = [items]
                    elif pinned_output.get('data'):
                        items_output = [[pinned_output.get('data')]]
                step_trace.set_output(items=items_output)
                step_trace.complete()

            # Store pinned result in context (same as normal execution)
            context[step_id] = pinned_output

            # Also store in output variable if specified
            output_var = step_config.get('output')
            if output_var:
                context[output_var] = pinned_output

            # Return pinned result (will be treated as successful completion)
            return pinned_output

        if not module_id:
            raise StepExecutionError(step_id, "Step missing 'module' field")

        if not should_execute:
            logger.info(f"Skipping step '{step_id}' (condition not met)")
            # Record skipped step in trace
            if trace_collector:
                trace_collector.skip_step(step_id, step_index, module_id or "unknown", "condition not met")
            return None

        # Start step trace if collector provided
        step_trace = None
        if trace_collector and module_id:
            step_trace = trace_collector.start_step(step_id, step_index, module_id)

        step_start_time = time.time()

        # Call pre-execute hook
        pre_context = self._create_step_context(
            step_config, step_index, context, step_start_time=step_start_time
        )
        pre_result = self._hooks.on_pre_execute(pre_context)

        if pre_result.action == HookAction.SKIP:
            logger.info(f"Skipping step '{step_id}' (hook requested skip)")
            return None
        if pre_result.action == HookAction.ABORT:
            raise StepExecutionError(
                step_id, f"Step aborted by hook: {pre_result.abort_reason}"
            )

        log_message = f"Executing step '{step_id}': {module_id}"
        if description:
            log_message += f" - {description}"
        logger.info(log_message)

        result = None
        error = None

        try:
            if foreach_array:
                result = await execute_foreach_step(
                    step_config, resolver, context, foreach_array, foreach_var,
                    self._execute_single_step, step_index, step_trace
                )
            else:
                result = await self._execute_single_step(
                    step_config, resolver, context, timeout, step_index, step_trace
                )

            # Store result in context
            context[step_id] = result

            output_var = step_config.get('output')
            if output_var:
                context[output_var] = result

            logger.info(f"Step '{step_id}' completed successfully")

            # Record successful step trace
            if step_trace:
                from ..trace import StepOutput
                items_output = []
                if isinstance(result, dict):
                    items = result.get('items', [])
                    if items:
                        items_output = [items]
                    elif result.get('data'):
                        items_output = [[result.get('data')]]
                step_trace.set_output(items=items_output)
                if step_trace.status in ("running", "pending"):
                    step_trace.complete()

        except Exception as e:
            error = e
            # Record failed step trace
            if step_trace:
                step_trace.fail(e)
            raise

        finally:
            # Call post-execute hook
            # SECURITY: Redact sensitive data before passing to hooks
            redacted_result = _redact_sensitive_output(result) if result else result
            post_context = self._create_step_context(
                step_config,
                step_index,
                context,
                result=redacted_result,
                error=error,
                step_start_time=step_start_time,
            )
            self._hooks.on_post_execute(post_context)

        return result

    async def _execute_single_step(
        self,
        step_config: Dict[str, Any],
        resolver: "VariableResolver",
        context: Dict[str, Any],
        timeout: int,
        step_index: int = 0,
        step_trace: Optional["StepTrace"] = None,
    ) -> Any:
        """Execute a single step with optional timeout."""
        step_id = step_config.get('id', f'step_{id(step_config)}')
        module_id = step_config.get('module')
        step_params = step_config.get('params', {})
        resolved_params = resolver.resolve(step_params)
        on_error = step_config.get('on_error', 'stop')

        retry_config = step_config.get('retry', {})

        # on_error: retry — auto-create default retry config if not explicitly set
        if on_error == 'retry' and not retry_config:
            retry_config = {'count': 3, 'delay_ms': 1000, 'backoff': 'linear'}

        # Get input items from upstream steps (item-based execution)
        # Support both flat list and by-port structure for multi-input
        upstream_by_port = step_config.get('$upstream_by_port')
        upstream_step_ids = step_config.get('$upstream_steps') or step_config.get('inputs')

        if upstream_by_port:
            # Multi-input: get items grouped by port, then merge
            input_items = self._get_input_items_by_port(context, upstream_by_port, resolved_params)
        else:
            # Single input: flat list
            input_items = self._get_input_items_from_context(context, upstream_step_ids)

        # Propagate workflow on_error to item-based execution
        resolved_params.setdefault('$on_error', on_error)

        if step_trace:
            trace_items = None
            if input_items is not None:
                trace_items = [item.json for item in input_items]
            step_trace.set_input(
                params=resolved_params,
                params_raw=step_params,
                items=trace_items,
            )

        try:
            if retry_config:
                async def execute_fn():
                    return await self._execute_module_with_timeout(
                        step_id, module_id, resolved_params, context, timeout, input_items, step_trace
                    )

                return await execute_with_retry(
                    step_id=step_id,
                    execute_fn=execute_fn,
                    retry_config=retry_config,
                    hooks=self._hooks,
                    step_config=step_config,
                    step_index=step_index,
                    context=context,
                    workflow_id=self._workflow_id,
                    workflow_name=self._workflow_name,
                    total_steps=self._total_steps,
                )
            else:
                return await self._execute_module_with_timeout(
                    step_id, module_id, resolved_params, context, timeout, input_items, step_trace
                )

        except StepTimeoutError as e:
            return self._handle_step_error(step_id, e, on_error)
        except StepExecutionError as e:
            return self._handle_step_error(step_id, e, on_error)

    def _handle_step_error(
        self,
        step_id: str,
        error: Exception,
        on_error: str
    ) -> Any:
        """Handle step execution error based on on_error strategy."""
        if on_error == 'continue':
            logger.warning(f"Step '{step_id}' failed but continuing: {str(error)}")
            return {'ok': False, 'error': str(error)}
        else:
            raise error

    async def _execute_module_with_timeout(
        self,
        step_id: str,
        module_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        timeout: int,
        input_items: Optional[List["Item"]] = None,
        step_trace: Optional["StepTrace"] = None,
    ) -> Any:
        """Execute a module with optional timeout."""
        if timeout <= 0:
            return await self._execute_module(step_id, module_id, params, context, input_items, step_trace)

        try:
            return await asyncio.wait_for(
                self._execute_module(step_id, module_id, params, context, input_items, step_trace),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise StepTimeoutError(step_id, timeout)

    async def _execute_module(
        self,
        step_id: str,
        module_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        input_items: Optional[List["Item"]] = None,
        step_trace: Optional["StepTrace"] = None,
    ) -> Any:
        """
        Execute a module and return result.

        Supports item-based execution based on module's execution_mode:
        - "single": Traditional execution, ignores input_items
        - "items": Process each input item independently
        - "all": Process all items at once
        """
        from ...modules.registry import ModuleRegistry
        from ...modules.items import (
            Item, ItemContext, NodeExecutionResult, ExecutionStatus,
            ItemError, ExecutionMeta, wrap_legacy_result, items_to_legacy_context
        )

        # Handle template.invoke:xxx format - strip suffix for registry lookup
        # but preserve full ID for the module to know which template to invoke
        lookup_id = module_id
        if module_id.startswith('template.invoke:'):
            lookup_id = 'template.invoke'
            # Ensure template_id is in params
            template_id = module_id.replace('template.invoke:', '')
            if 'template_id' not in params:
                params['template_id'] = template_id
            if 'library_id' not in params:
                params['library_id'] = template_id

        module_class = ModuleRegistry.get(lookup_id)

        if not module_class:
            raise StepExecutionError(step_id, f"Module not found: {module_id}")

        module_instance = module_class(params, context)
        execution_mode = getattr(module_instance, 'execution_mode', 'single')

        try:
            if execution_mode == 'single':
                # Traditional mode: ignore input_items, use params
                result = await module_instance.run()
                # Wrap legacy result for consistent handling
                if isinstance(result, dict) and 'ok' in result:
                    node_result = wrap_legacy_result(result)
                    # Return legacy format for backward compatibility
                    return items_to_legacy_context(node_result)
                return result

            elif execution_mode == 'items':
                # Process each item independently
                items = input_items if input_items is not None else [Item(json={})]
                output_items = []
                errors = []
                on_error = params.get('$on_error', 'stop')

                for i, item in enumerate(items):
                    item_trace = None
                    if step_trace:
                        from ..trace import ItemTrace
                        item_trace = ItemTrace(index=i, input=item.json).start()
                    try:
                        item_ctx = ItemContext(items=items, totalItems=len(items))
                        result_item = await module_instance.execute_item(item, i, item_ctx)
                        if isinstance(result_item, list):
                            output_items.extend(result_item)
                            if item_trace:
                                item_trace.complete({
                                    "items": [
                                        (ri.json if isinstance(ri, Item) else Item.from_value(ri).json)
                                        for ri in result_item
                                    ]
                                })
                        else:
                            output_items.append(result_item)
                            if item_trace:
                                if isinstance(result_item, Item):
                                    item_trace.complete(result_item.json)
                                elif isinstance(result_item, dict):
                                    item_trace.complete(result_item)
                                else:
                                    item_trace.complete({"value": result_item})
                    except Exception as e:
                        if on_error == 'continue':
                            error_item = Item(
                                json={},
                                error=ItemError(message=str(e), itemIndex=i)
                            )
                            output_items.append(error_item)
                            errors.append(e)
                            if item_trace:
                                item_trace.fail(str(e))
                        else:
                            raise
                    finally:
                        if item_trace and step_trace:
                            step_trace.add_item_trace(item_trace)

                status = ExecutionStatus.PARTIAL if errors else ExecutionStatus.SUCCESS
                node_result = NodeExecutionResult(
                    data=[output_items],
                    status=status,
                    meta=ExecutionMeta(
                        itemsProcessed=len(items),
                        itemsFailed=len(errors)
                    )
                )
                return items_to_legacy_context(node_result)

            elif execution_mode == 'all':
                # Process all items at once
                items = input_items or []
                item_ctx = ItemContext(items=items, totalItems=len(items))
                output_items = await module_instance.execute_all(items, item_ctx)

                node_result = NodeExecutionResult(
                    data=[output_items],
                    status=ExecutionStatus.SUCCESS,
                    meta=ExecutionMeta(itemsProcessed=len(items))
                )
                return items_to_legacy_context(node_result)

            else:
                # Unknown mode, fall back to single
                logger.warning(f"Unknown execution_mode '{execution_mode}', using single")
                return await module_instance.run()

        except Exception as e:
            raise StepExecutionError(step_id, f"Step failed: {str(e)}", e)

    def _get_input_items_from_context(
        self,
        context: Dict[str, Any],
        upstream_step_ids: Optional[List[str]] = None
    ) -> Optional[List["Item"]]:
        """
        Extract input items from context based on upstream steps.

        Args:
            context: Workflow context
            upstream_step_ids: List of upstream step IDs to get items from

        Returns:
            List of input items merged from all upstream steps,
            or None if no upstream info is provided.
        """
        from ...modules.items import Item

        if upstream_step_ids is None:
            return None
        if not upstream_step_ids:
            return []

        items = []
        for step_id in upstream_step_ids:
            step_result = context.get(step_id, {})
            if isinstance(step_result, dict):
                # Check for items array
                step_items = step_result.get('items', [])
                if step_items:
                    for item_data in step_items:
                        items.append(Item.from_value(item_data))
                elif step_result.get('data'):
                    # Legacy format: wrap data as single item
                    items.append(Item(json=step_result.get('data', {})))

        return items

    def _get_input_items_by_port(
        self,
        context: Dict[str, Any],
        upstream_by_port: Dict[str, List[str]],
        params: Dict[str, Any],
    ) -> Optional[List["Item"]]:
        """
        Extract input items from context grouped by port, then merge.

        Supports multi-input with merge strategies as per ITEM_PIPELINE_SPEC.md.

        Args:
            context: Workflow context
            upstream_by_port: Dict mapping port name to list of upstream step IDs
            params: Resolved params (may contain $merge_strategy)

        Returns:
            Merged list of input items
        """
        from ...modules.items import Item, MergeStrategy, merge_items

        if not upstream_by_port:
            return None

        # Collect items by port
        items_by_port: Dict[str, List[Item]] = {}

        for port_name, step_ids in upstream_by_port.items():
            port_items: List[Item] = []
            for step_id in step_ids:
                step_result = context.get(step_id, {})
                if isinstance(step_result, dict):
                    step_items = step_result.get('items', [])
                    if step_items:
                        for item_data in step_items:
                            port_items.append(Item.from_value(item_data))
                    elif step_result.get('data'):
                        port_items.append(Item(json=step_result.get('data', {})))
            if port_items:
                items_by_port[port_name] = port_items

        if not items_by_port:
            return []

        # Inject items_by_port into params for modules that need it
        params['$input_items_by_port'] = {
            port: [item.json for item in items]
            for port, items in items_by_port.items()
        }

        # Get merge strategy from params or use default
        strategy_str = params.get('$merge_strategy', 'append')
        strategy = MergeStrategy.from_string(strategy_str)

        # Merge items using strategy
        return merge_items(items_by_port, strategy)

    # =========================================================================
    # Phase 0: Runtime Invoker Integration
    # =========================================================================
    # The following methods prepare for future plugin system integration.
    # Currently, they delegate to the existing in-process module execution.
    # In Phase 1+, these will route to subprocess plugins when available.

    def _parse_module_id(self, module_id: str) -> tuple:
        """
        Parse legacy module_id into plugin_id and step_id.

        Examples:
            "database.query" -> ("flyto-official/database", "query")
            "llm.chat" -> ("flyto-official/llm", "chat")

        This method is used to convert between the legacy module format
        and the new plugin/step format for future plugin routing.
        """
        if _RUNTIME_INVOKER_AVAILABLE:
            return parse_module_id(module_id)

        # Fallback implementation
        parts = module_id.split(".")
        if len(parts) >= 2:
            category = parts[0]
            action = ".".join(parts[1:])
            return (f"flyto-official/{category}", action)
        else:
            return (f"flyto-official/{module_id}", "execute")

    async def _invoke_via_runtime(
        self,
        module_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Any:
        """
        Invoke a module via the RuntimeInvoker.

        This method provides a clean interface for future plugin routing.
        Currently delegates to the in-process module registry.

        Phase 0: Direct in-process execution (current)
        Phase 1+: Will route to subprocess plugins when available

        Args:
            module_id: Legacy module ID (e.g., "database.query")
            params: Resolved parameters
            context: Execution context

        Returns:
            Module execution result
        """
        if not _RUNTIME_INVOKER_AVAILABLE:
            # Fallback: use direct registry access
            from ...modules.registry import ModuleRegistry

            # Handle template.invoke:xxx format
            lookup_id = module_id
            if module_id.startswith('template.invoke:'):
                lookup_id = 'template.invoke'
                template_id = module_id.replace('template.invoke:', '')
                if 'template_id' not in params:
                    params['template_id'] = template_id
                if 'library_id' not in params:
                    params['library_id'] = template_id

            module_class = ModuleRegistry.get(lookup_id)
            if not module_class:
                raise StepExecutionError("unknown", f"Module not found: {lookup_id}")
            module_instance = module_class(params, context)
            return await module_instance.run()

        # Use RuntimeInvoker
        plugin_id, step_id = self._parse_module_id(module_id)
        invoker = get_invoker()

        result = await invoker.invoke(
            module_id=plugin_id,
            step_id=step_id,
            input_data=params,
            config={},
            context=context,
        )

        return result
