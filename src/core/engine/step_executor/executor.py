# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..exceptions import StepTimeoutError, StepExecutionError, is_policy_refusal
from ..outcome import (
    ENVELOPE_KEY,
    ClaimBy,
    Outcome,
    cap,
    ceiling_for,
    default_for,
    envelope_from_exception,
    envelope,
    is_on_ladder,
    read_envelope,
    rung_index,
)
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


# A module can finish its work and still be unable to confirm the effect it
# said to expect: browser.click dispatches a click on a link that declares
# target=_blank, no tab is ever created, and the click itself never failed.
# That is not an error — nothing to raise, nothing to retry — but it is not a
# clean success either, and a step record that cannot tell the two apart hands
# the caller an unobserved outcome dressed as an observed one.
#
# 'partial' is the status this ledger already carries for exactly that shape:
# the step ran, its result stands and flows downstream, and part of what it
# reported went unconfirmed. It is not a failure — ok stays true, failedSteps
# stays 0, the workflow keeps going — so nothing that succeeded before starts
# failing now; it just stops being indistinguishable from a verified success.
_UNCONFIRMED_VERIFICATION = 'unverified'

# browser.click's five string literals, mapped onto the ladder. It is the only
# module of 483 that reports an outcome, and it predates the ladder, so its
# vocabulary is translated here rather than rewritten there — one module's
# private words becoming the engine's shared ones is exactly the migration this
# table exists to make reversible.
#
#   not_requested  nothing was expected and nothing was checked
#   dispatched     'click_only': verifies nothing beyond dispatch
#   inferred       the module guessed an expectation from markup and saw it
#   unverified     the module guessed, and did not see it
#   verified       the caller asked, and _verify_current_page_outcome held
#
# `unverified` becomes INDETERMINATE, not FAILED, and that is the point of the
# second axis: the expectation was the module's own inference, so a tab that
# never opened may mean the click was fine and the guess was wrong. A caller who
# asks explicitly and does not get it never reaches here at all — click.py:587
# and :611 raise.
_LEGACY_VERIFICATION_RUNGS = {
    'not_requested': (Outcome.DISPATCHED, ClaimBy.NONE),
    'dispatched': (Outcome.DISPATCHED, ClaimBy.NONE),
    'inferred': (Outcome.OBSERVED, ClaimBy.INFERRED),
    _UNCONFIRMED_VERIFICATION: (Outcome.INDETERMINATE, ClaimBy.INFERRED),
    'verified': (Outcome.VERIFIED, ClaimBy.CALLER),
}


def _outcome_payloads(result: Any) -> List[Dict[str, Any]]:
    """Every dict in a step result that could be carrying an outcome.

    Four places, and the last two are the hole this closes. A foreach step
    returns one result per iteration, so the list form is read. A module in
    ``execution_mode`` 'items' or 'all' returns an aggregate — ``{ok, data,
    items, items_full}`` — whose ``data`` is a *list*, so the old walk's
    ``isinstance(data, dict)`` skipped it and the per-item outcomes underneath
    were never seen at all. A module could report every one of its items
    unobserved and the step recorded a clean success.
    """
    payloads: List[Dict[str, Any]] = []
    candidates = result if isinstance(result, (list, tuple)) else [result]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        payloads.append(candidate)
        data = candidate.get('data')
        if isinstance(data, dict):
            payloads.append(data)
        elif isinstance(data, (list, tuple)):
            payloads.extend(entry for entry in data if isinstance(entry, dict))
        for key in ('items', 'items_full'):
            entries = candidate.get(key)
            if not isinstance(entries, (list, tuple)):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                payloads.append(entry)
                nested = entry.get('json')
                if isinstance(nested, dict):
                    payloads.append(nested)
    return payloads


def _payload_outcome(payload: Dict[str, Any]) -> Optional[tuple]:
    """(rung, claim_by, expected) for one payload, or None if it says nothing."""
    found = read_envelope(payload)
    if found is not None:
        return (
            Outcome(found['rung']),
            found.get('claim_by') or ClaimBy.NONE.value,
            found.get('postcondition') or payload.get('expected_outcome'),
        )
    legacy = payload.get('verification_status')
    if legacy in _LEGACY_VERIFICATION_RUNGS:
        rung, claim_by = _LEGACY_VERIFICATION_RUNGS[legacy]
        return rung, claim_by.value, payload.get('expected_outcome')
    return None


def step_outcome(result: Any) -> Optional[tuple]:
    """The weakest outcome anything in this step's result reported.

    Weakest, because a step is only as confirmed as its least confirmed part:
    nine rows written and one unobserved is not a verified step. Off-ladder
    answers win outright over any rung — `failed` and `indeterminate` are not
    low rungs to be averaged away, they are the answer.

    Returns None when nothing in the result reported an outcome at all, which
    is still the overwhelming majority of steps and must stay distinguishable
    from a module that reported `dispatched`.
    """
    reported = [
        found
        for found in (_payload_outcome(payload) for payload in _outcome_payloads(result))
        if found is not None
    ]
    if not reported:
        return None

    off_ladder = [found for found in reported if not is_on_ladder(found[0])]
    if off_ladder:
        # FAILED before INDETERMINATE: a broken contract is a stronger
        # statement than "we could not tell", and a step carrying both is
        # reported as the one somebody has to act on.
        failed = [found for found in off_ladder if found[0] is Outcome.FAILED]
        return failed[0] if failed else off_ladder[0]

    return min(reported, key=lambda found: rung_index(found[0]))


def _declared_failure(payload: Any) -> Optional[Tuple[str, str]]:
    """A payload that says it failed in a shape that cannot mean anything else.

    `wrap_legacy_result` is the only path from a module's failure to a step's,
    and it is gated on an `ok` key that 158 of the 483 modules never return. So
    a module without one could say `status: "error"`, carry an `error_code` and
    an error message, and the step completed green with the error inside it.
    Six modules do exactly that with no envelope either -- element.attribute,
    element.query, element.text and the three robotics modules -- and all six
    were reproduced completing GREEN.

    Two clauses, and the third one people reach for is a bug:

    * `error_code`, a non-empty string. Measured over all 483 modules, zero
      return it on a success-shaped path.
    * `status` equal to "error" COMPARED AS A STRING. The string comparison is
      what keeps `http.request` and `auth.oauth2` out of this -- they put an
      integer HTTP status under that key -- and `port.check`, whose status is
      'open' or 'closed'.
    * NOT a bare `error` key. `reverse.sourcemap` returns
      `{'status': 'success', 'content': None, 'error': ...}` on a step that did
      its job: error-as-data. Failing that would be a new false red.

    Yields to an envelope, so a module that said what it meant keeps saying it:
    `_raise_for_declared_failure` is the authority wherever one exists, and it
    is the reason a Slack 5xx stays INDETERMINATE instead of being sniffed into
    a failure here.
    """
    if not isinstance(payload, dict) or 'ok' in payload:
        return None                      # wrap_legacy_result owns this one
    if read_envelope(payload) is not None:
        return None                      # the module said what it meant

    code = payload.get('error_code')
    status = payload.get('status')
    message = payload.get('error') or payload.get('message')
    if isinstance(code, str) and code:
        return code, str(message or code)
    if isinstance(status, str) and status.lower() == 'error':
        return 'MODULE_ERROR', str(message or "module reported status='error'")
    return None


def _apply_outcome_contract(module_instance: Any, result: Any) -> Any:
    """Stamp the default rung, and lower a claim the declaration cannot support.

    The one place where the module's declaration, the module's own claim and the
    surviving ``data`` dict are all in scope. It runs before
    ``wrap_legacy_result``, because ``to_legacy_dict`` keeps only ``data`` and an
    envelope written anywhere else is discarded on the way out of the step.

    Two things happen here and only here:

    * A side-effecting module that reported nothing is stamped ``dispatched``.
      That is the truth about it — the instruction left us and nobody confirmed
      anything — and it is what makes the gap visible instead of absent. The
      other 334 modules are stamped with nothing at all: putting an envelope on
      every string concatenation would teach every consumer to ignore the field,
      and what makes an undeclared module visible is the ratchet counting it.

    * A claim of ``verified`` from a module that declared no postcondition is
      lowered to ``observed``. Not a policy: ``verified`` *means* a postcondition
      was evaluated and held, so with none declared there is no predicate the
      claim could be about. ``cap`` leaves ``failed`` and ``indeterminate``
      alone — a module that failed did fail, and no ceiling makes that an
      ``accepted``.

    Never upward. Nothing here can raise a rung a module claimed, because every
    reason to do so would be an inference by the engine about an effect only the
    module can see.
    """
    if not isinstance(result, dict):
        return result

    module_id = getattr(module_instance, 'module_id', '') or ''
    if not module_id:
        return result

    from ...modules.registry import ModuleRegistry

    metadata = ModuleRegistry.get_metadata(module_id) or {}
    declared = metadata.get('postcondition')

    # Where the envelope has to live, and where a module would have put it.
    #
    # Three shapes, and the middle one used to be silently wrong. A dict `data`
    # takes the stamp directly. A FLAT result with no `data` key is fine too:
    # `wrap_legacy_result` sweeps its non-meta fields into the item json, which
    # becomes `data` on the way out, so a top-level stamp arrives inside it.
    #
    # A result whose `data` is a LIST or a scalar is neither. This function used
    # to fall back to the outer dict for those, which is exactly the place its
    # own docstring says gets discarded — `to_legacy_dict` keeps `data` and
    # nothing else — so the stamp vanished and the step reported no rung at all.
    # Not a false green (nothing is worse than absent), but a hole the first
    # module to return a list-shaped `data` would fall into silently.
    data = result.get('data')
    if isinstance(data, dict):
        body = data
    elif 'data' in result:
        # A list or a scalar. There is nowhere inside it for a mapping to live,
        # so say nothing rather than write somewhere that gets thrown away.
        return result
    else:
        body = result

    existing = read_envelope(body)
    if existing is not None:
        capped = cap(existing['rung'], ceiling_for(declared))
        if capped.value != existing['rung']:
            body[ENVELOPE_KEY] = dict(
                existing,
                rung=capped.value,
                postcondition=declared,
            )
        elif (
            declared
            and not existing.get('postcondition')
            and existing['rung'] == Outcome.VERIFIED.value
        ):
            # Only onto a VERIFIED claim, because that is the only rung the
            # field means anything on: `postcondition` names the predicate that
            # was evaluated AND HELD, and below VERIFIED nothing held.
            #
            # Without the rung check this stamped the declared sentence onto
            # every envelope of a declaring module that had not named one --
            # including the ones that deliberately name none. Measured on
            # `http.response_assert` with no assertions supplied, which returns
            # ACCEPTED and `postcondition: None` precisely because there was
            # nothing to evaluate:
            #
            #   module wrote  postcondition: None
            #   engine wrote  "every assertion supplied by the caller was
            #                  evaluated against the response object supplied
            #                  by the caller, and all of them held"
            #
            # Zero assertions were supplied and none were evaluated. That
            # sentence is manufactured by the engine, about a predicate the
            # module went out of its way not to claim, and it is the exact
            # shape of overreach this contract exists to stop -- with the
            # engine, rather than a module, as the author of the lie.
            body[ENVELOPE_KEY] = dict(existing, postcondition=declared)
        return result

    # "Reported nothing" has to mean the same thing here as it does to the
    # reader, or the default silently overwrites a real answer. browser.click
    # reports through the legacy `verification_status` field and carries no
    # envelope, so a check that asked only `read_envelope` found none, stamped
    # `dispatched` beside it, and `_payload_outcome` — which prefers an envelope
    # — then returned the stamp instead of the module's own `indeterminate`. The
    # one module that already had a contract was the one the contract erased.
    if any(_payload_outcome(payload) is not None for payload in _outcome_payloads(result)):
        return result

    stamped = default_for(module_id, metadata)
    if stamped is None:
        return result
    body[ENVELOPE_KEY] = envelope(stamped, postcondition=declared)
    return result


def _unconfirmed_outcome(result: Any) -> Optional[str]:
    """Why this step's ledger entry must stop claiming a confirmed effect.

    Off-ladder answers only — FAILED and INDETERMINATE — which is precisely the
    set that degraded the step's status before this change, when the single
    value `unverified` meant them both at once. What is new is only how much of
    the result is read: an outcome buried in a per-item aggregate now reaches
    this function, where it used to be invisible.

    Deliberately NOT firing on DISPATCHED, ACCEPTED or OBSERVED, even though the
    contract says only `verified` may be rendered as success. Those three are
    the ordinary state of almost every step in the product today, and marking
    them `partial` here would turn nearly every run amber before a single
    consumer knows how to render the distinction — which would make `partial`
    meaningless for the second time, having just been given a second meaning by
    `TraceStatus.PARTIAL` already carrying "some items failed".

    The rung travels instead: `step_outcome` exposes it, and the consumers that
    decide what a person sees are the next piece of work, not a side effect of
    this one. Making an unobserved step *look* unobserved is the point of the
    contract; doing it before anything can say what it means is how a good
    signal gets switched off.
    """
    found = step_outcome(result)
    if found is None:
        return None
    rung, claim_by, expected = found
    if is_on_ladder(rung):
        return None
    subject = repr(expected) if expected else 'the expected effect'
    # "never observed X" is kept verbatim from the sentence this replaced. It
    # is what a person actually reads, seven tests pin it, and it is true --
    # the rung and the claimant are additions to it, not a replacement for it.
    # FAILED gets its own verb because "never observed" would understate it: a
    # postcondition the caller asked for was evaluated and did not hold.
    said = (
        f"{subject} did not hold"
        if rung is Outcome.FAILED
        else f"never observed {subject}"
    )
    return (
        f"Step reported success but {said} "
        f"(outcome={rung.value!r}, claimed by {claim_by})"
    )


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
        evolution: Optional["StepHealer"] = None,
        recipe_id: Optional[str] = None,
    ):
        """
        Initialize step executor.

        Args:
            hooks: Optional executor hooks for lifecycle events
            workflow_id: ID of the parent workflow (for logging/hooks)
            workflow_name: Name of the parent workflow (for hooks)
            total_steps: Total number of steps in workflow (for hooks)
            evolution: Optional StepHealer for self-healing workflows
            recipe_id: Recipe ID for evolution memory tracking
        """
        from ..hooks import NullHooks
        self._hooks = hooks or NullHooks()
        self._workflow_id = workflow_id
        self._workflow_name = workflow_name
        self._total_steps = total_steps
        self._evolution = evolution
        self._recipe_id = recipe_id

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

        # Evolution: apply known patches before execution
        if self._evolution and self._recipe_id:
            step_config = self._evolution.apply_known_patches(self._recipe_id, step_config)

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
                self._record_unconfirmed_outcome(step_trace, result)

        except Exception as e:
            # Evolution: attempt self-heal on browser step failures
            healed = await self._try_heal(step_config, e, context)
            if healed:
                # Retry with patched config
                try:
                    result = await self._execute_single_step(
                        healed, resolver, context, timeout, step_index, step_trace
                    )
                    context[step_id] = result
                    output_var = step_config.get('output')
                    if output_var:
                        context[output_var] = result
                    logger.info(f"Step '{step_id}' healed and completed successfully")
                    if step_trace and step_trace.status in ("running", "pending", "failed"):
                        step_trace.complete()
                    if step_trace:
                        self._record_unconfirmed_outcome(step_trace, result)
                    return result
                except Exception:
                    pass  # Heal retry also failed, fall through to original error

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

    @staticmethod
    def _record_unconfirmed_outcome(
        step_trace: "StepTrace",
        result: Any,
    ) -> None:
        """Record an unconfirmed outcome on an otherwise-successful step.

        The step keeps its result and the workflow keeps running; only the
        ledger entry stops claiming a verified success, so every consumer of
        the trace (CLI run output, the MCP run_recipe response, the REST
        execute response) can see which steps were actually observed.
        """
        reason = _unconfirmed_outcome(result)
        if not reason:
            return

        from ..trace import TraceError, TraceStatus

        step_trace.status = TraceStatus.PARTIAL.value
        step_trace.error = TraceError(message=reason, code='UNVERIFIED_OUTCOME')

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
        resolved_params = self._substitute_local_vars(resolved_params)
        from ..variable_resolver import VariableResolver
        resolved_params = VariableResolver.resolve_tvars(resolved_params)
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

        async def execute_fn():
            result = await self._execute_module_with_timeout(
                step_id,
                module_id,
                resolved_params,
                context,
                timeout,
                input_items,
                step_trace,
            )
            result = self._raise_for_error_event(step_id, result)
            return self._raise_for_declared_failure(step_id, result)

        try:
            if retry_config:
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
                return await execute_fn()

        except StepTimeoutError as e:
            return self._handle_step_error(step_id, e, on_error)
        except StepExecutionError as e:
            return self._handle_step_error(step_id, e, on_error)

    @staticmethod
    def _raise_for_declared_failure(step_id: str, result: Any) -> Any:
        """Honour a module that said, in its own envelope, that it failed.

        Sixteen modules write `rung: "failed"` and the engine used to discard
        it. Nothing else could act on it either: `wrap_legacy_result` is the
        only path from a module's failure to a step's failure and it is gated
        on an `ok` key that 158 of the 483 modules never return, so for a third
        of the registry a declared failure had no way of failing anything.
        Measured end to end on the shipped recipe `scrape-to-slack.yaml` with a
        revoked webhook: Slack answered 404, `notification.slack` correctly
        reported `rung: failed`, and the step completed GREEN.

        This adds nothing to the module's claim. `read_envelope` validates the
        rung against the enum, and `engine/outcome.py` DEFINES failed as "a
        postcondition was evaluated and did not hold, or the execution itself
        raised". The engine simply stops throwing the answer away.

        INDETERMINATE deliberately does not raise, and the asymmetry is the
        whole point. `notification.slack` is the worked example: a 4xx is
        FAILED because Slack rejected the message, while a 5xx is INDETERMINATE
        because the POST was already in Slack's hands and we cannot say whether
        it landed. Raising there would let `on_error: retry` post the message a
        second time. Retrying a failure is safe; retrying an indeterminate
        write may do it twice.
        """
        found = step_outcome(result)
        if found is None or found[0] is not Outcome.FAILED:
            return result

        _rung, claim_by, expected = found
        subject = repr(expected) if expected else 'the expected effect'
        raise StepExecutionError(
            step_id,
            f"Module reported outcome 'failed': {subject} did not hold "
            f"(claimed by {claim_by})",
        )

    @staticmethod
    def _raise_for_error_event(step_id: str, result: Any) -> Any:
        """Turn an emitted error event into the engine's step-failure contract."""
        if not isinstance(result, dict) or result.get('__event__') != 'error':
            return result

        error = result.get('__error__')
        error = error if isinstance(error, dict) else {}
        output_error = result.get('outputs', {}).get('error', {})
        output_error = output_error if isinstance(output_error, dict) else {}
        code = error.get('code') or result.get('error_code') or 'MODULE_ERROR'
        message = (
            error.get('message')
            or output_error.get('message')
            or result.get('error')
            or 'Module emitted an error event'
        )
        raise StepExecutionError(
            step_id,
            f"Module returned error event [{code}]: {message}",
        )

    async def _try_heal(
        self,
        step_config: Dict[str, Any],
        error: Exception,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Attempt to self-heal a failed step using Evolution Engine.

        Returns patched step_config if healing succeeded, None otherwise.
        """
        if not self._evolution or not self._recipe_id:
            return None

        module_id = step_config.get("module", "")
        from ..evolution.healer import is_healable
        if not is_healable(module_id, error):
            return None

        # Get page context for AI analysis (if browser is available)
        page_context = None
        page = context.get("page")
        if page:
            try:
                page_context = await page.content()
                if len(page_context) > 3000:
                    page_context = page_context[:3000]
            except Exception:
                pass

        patch = await self._evolution.heal(step_config, error, page_context)
        if not patch:
            return None

        # Apply patch to step config
        patched = dict(step_config)
        params = dict(patched.get("params", {}))
        if patch["fix_type"] == "replace_param":
            params[patch["param_key"]] = patch["new_value"]
        elif patch["fix_type"] == "add_param":
            params[patch["param_key"]] = patch["new_value"]
        patched["params"] = params

        # Save patch to memory for future runs
        self._evolution._memory.add_patch(self._recipe_id, patch)

        logger.info(f"Evolution: healed step '{step_config.get('id')}' — {patch.get('reason', 'auto-fixed')}")
        return patched

    def _handle_step_error(
        self,
        step_id: str,
        error: Exception,
        on_error: str
    ) -> Any:
        """Handle step execution error based on on_error strategy."""
        if on_error != 'continue':
            raise error
        if is_policy_refusal(error):
            logger.error(
                f"Step '{step_id}' was refused by the capability policy; "
                "on_error='continue' does not apply to a refusal"
            )
            raise error
        logger.warning(f"Step '{step_id}' failed but continuing: {str(error)}")
        # The absorbed error needs a rung, or absorbing it erases it. Measured
        # before this line existed: a step that RAISED, under
        # `on_error: continue`, reached the cloud as
        # `status='success', rung=None, proved=True` -- a step that crashed,
        # drawn as a proved success. `on_error: continue` is a licence to carry
        # on past something that went wrong, not a licence to forget that it did.
        #
        # The asymmetry with the raise path is deliberate: absorbing a PLAIN
        # exception yields FAILED, not indeterminate. The step raised and nobody
        # said otherwise. A module that opted in with `OutcomeError` keeps the
        # rung it chose -- that is the only way `indeterminate` gets in here.
        #
        # Top level, not under a `data` key: `_outcome_payloads` reads the outer
        # dict, so `step_outcome` finds it through the ordinary result path.
        carried = envelope_from_exception(error)
        return {
            'ok': False,
            'error': str(error),
            ENVELOPE_KEY: carried if carried is not None else envelope(
                Outcome.FAILED,
                claim_by=ClaimBy.NONE,
                effects=[{
                    'kind': 'step_raised',
                    'error': str(error)[:300],
                    'error_type': type(error).__name__,
                    'measured_by': 'the exception that reached on_error=continue',
                    'detail': (
                        'The step raised and the workflow was told to carry on. '
                        'Carrying on is not evidence that anything worked.'
                    ),
                }],
            ),
        }

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

        # SECURITY: gate before the mode branch, not inside it.
        #
        # Only the 'single' branch below reaches `run()`, and `run()` is where
        # the capability gate lives — it calls itself "the single execution
        # chokepoint", and `enforce_module_policy` documents that "EVERY module
        # ... is executed through this gate". The 'items' and 'all' branches
        # call `execute_item` / `execute_all` directly, so both sentences were
        # false: a module opted out of the security backstop by setting one
        # class attribute, and `BaseModule.execute_item` defaults to calling
        # `self.execute()` straight through.
        #
        # Nothing shipped in that state — the only non-test assignment of the
        # attribute is the default in base.py — which is what makes it cheap to
        # close before somebody uses the feature and inherits the hole.
        #
        # Gating here as well as in `run()` rather than instead of it: `run()`
        # has eleven other callers (direct invoke, the REST and MCP surfaces,
        # nested runners, composite sub-nodes), and taking the gate out of it to
        # avoid a second call would open a far larger hole than this one.
        # The check is a pure raise-or-return, so asking twice costs nothing.
        enforce = getattr(module_instance, 'enforce_policy', None)
        if callable(enforce):
            enforce()

        execution_mode = getattr(module_instance, 'execution_mode', 'single')

        try:
            if execution_mode == 'items':
                return await self._execute_items_mode(
                    step_id, module_instance, params, input_items, step_trace
                )
            elif execution_mode == 'all':
                return await self._execute_all_mode(
                    step_id, module_instance, input_items
                )
            else:
                if execution_mode != 'single':
                    logger.warning(f"Unknown execution_mode '{execution_mode}', using single")
                return await self._execute_single_mode(
                    step_id, module_instance
                )

        except Exception as e:
            raise StepExecutionError(step_id, f"Step failed: {str(e)}", e)

    async def _execute_single_mode(
        self,
        step_id: str,
        module_instance: Any,
    ) -> Any:
        """Traditional single execution mode: ignore input_items, use params."""
        from ...modules.items import (
            ExecutionStatus,
            items_to_legacy_context,
            wrap_legacy_result,
        )

        result = await module_instance.run()
        result = _apply_outcome_contract(module_instance, result)
        # Wrap legacy result for consistent handling
        if isinstance(result, dict) and 'ok' in result:
            node_result = wrap_legacy_result(result)
            if node_result.status == ExecutionStatus.ERROR:
                node_error = node_result.error
                message = node_error.message if node_error else "Unknown module error"
                code = node_error.code if node_error else "UNKNOWN"
                raise StepExecutionError(
                    step_id,
                    f"Module returned failure [{code}]: {message}",
                )
            # Return legacy format for backward compatibility
            return items_to_legacy_context(node_result)

        found = _declared_failure(result)
        if found is not None:
            code, message = found
            raise StepExecutionError(
                step_id,
                f"Module returned failure [{code}]: {message}",
            )
        return result

    async def _execute_items_mode(
        self,
        step_id: str,
        module_instance: Any,
        params: Dict[str, Any],
        input_items: Optional[List["Item"]],
        step_trace: Optional["StepTrace"],
    ) -> Any:
        """Process each input item independently."""
        from ...modules.items import (
            Item, ItemContext, NodeExecutionResult, ExecutionStatus,
            ItemError, ExecutionMeta, items_to_legacy_context
        )

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
                if on_error == 'continue' and not is_policy_refusal(e):
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

    async def _execute_all_mode(
        self,
        step_id: str,
        module_instance: Any,
        input_items: Optional[List["Item"]],
    ) -> Any:
        """Process all items at once."""
        from ...modules.items import (
            ItemContext, NodeExecutionResult, ExecutionStatus,
            ExecutionMeta, items_to_legacy_context
        )

        items = input_items or []
        item_ctx = ItemContext(items=items, totalItems=len(items))
        output_items = await module_instance.execute_all(items, item_ctx)

        node_result = NodeExecutionResult(
            data=[output_items],
            status=ExecutionStatus.SUCCESS,
            meta=ExecutionMeta(itemsProcessed=len(items))
        )
        return items_to_legacy_context(node_result)

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

    @staticmethod
    def _substitute_local_vars(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Substitute template variables ({{var}} / ${var}) with values from __vars__.

        The frontend stores user-provided values in params.__vars__.
        This pops __vars__ and replaces placeholders in all string values.
        """
        local_vars = params.pop('__vars__', None)
        if not local_vars:
            return params

        def _replace(value: Any) -> Any:
            if isinstance(value, str):
                for var_name, var_value in local_vars.items():
                    value = value.replace('{{' + var_name + '}}', str(var_value))
                    value = value.replace('${' + var_name + '}', str(var_value))
                return value
            if isinstance(value, dict):
                return {k: _replace(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_replace(item) for item in value]
            return value

        return _replace(params)

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
