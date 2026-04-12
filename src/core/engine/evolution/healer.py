# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Step Healer — Auto-fix failed workflow steps using AI.

When a browser step fails (selector not found, timeout, element not visible),
the healer:
1. Captures the error + current page DOM
2. Asks an LLM to suggest a fix (new selector, longer wait, etc.)
3. Patches the step params and retries
4. If successful, stores the patch in EvolutionMemory for future runs

No external dependencies beyond an LLM (uses flyto-core's own ChatModel).
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .memory import EvolutionMemory

logger = logging.getLogger(__name__)

# Error patterns that the healer can fix
HEALABLE_PATTERNS = [
    # Selector not found
    r"(?i)(selector|element|locator).*not\s*found",
    r"(?i)no\s*element\s*match",
    r"(?i)waiting\s*for\s*(selector|locator).*timeout",
    # Timeout
    r"(?i)timeout.*\d+ms\s*(exceeded|expired)",
    r"(?i)navigation\s*timeout",
    # Element not interactable
    r"(?i)element.*not.*(visible|clickable|interactable)",
    r"(?i)element\s*is\s*detached",
    # Page changed
    r"(?i)target\s*closed",
    r"(?i)page\s*(closed|crashed|navigated)",
]

# Browser modules that can be healed
HEALABLE_MODULES = {
    "browser.click", "browser.type", "browser.select", "browser.extract",
    "browser.find", "browser.wait", "browser.scroll", "browser.evaluate",
    "browser.screenshot", "browser.snapshot", "browser.detect",
    "browser.goto", "browser.form", "browser.login", "browser.upload",
}


def is_healable(module_id: str, error: Exception) -> bool:
    """Check if a step failure can potentially be healed."""
    if module_id not in HEALABLE_MODULES:
        return False
    error_str = str(error)
    return any(re.search(pat, error_str) for pat in HEALABLE_PATTERNS)


class StepHealer:
    """Auto-heal failed workflow steps using AI analysis.

    Usage:
        healer = StepHealer(memory=evolution_memory, chat_model=model)
        patch = await healer.heal(step_config, error, page_context)
        if patch:
            # Apply patch and retry
    """

    def __init__(
        self,
        memory: Optional[EvolutionMemory] = None,
        chat_model=None,  # ChatModel protocol
    ):
        self._memory = memory or EvolutionMemory()
        self._chat_model = chat_model

    def apply_known_patches(
        self,
        recipe_id: str,
        step_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply previously learned patches to a step before execution.

        Returns the patched step config (or original if no patches apply).
        """
        step_id = step_config.get("id", "")
        patches = self._memory.get_patches(recipe_id, step_id=step_id)

        if not patches:
            return step_config

        patched = dict(step_config)
        params = dict(patched.get("params", {}))

        for i, patch in enumerate(patches):
            fix_type = patch.get("fix_type")
            param_key = patch.get("param_key")
            new_value = patch.get("new_value")

            if fix_type == "replace_param" and param_key and new_value is not None:
                old_value = params.get(param_key)
                if old_value == patch.get("old_value"):
                    params[param_key] = new_value
                    self._memory.mark_patch_applied(recipe_id, i)
                    logger.info(
                        f"Evolution: auto-applied patch for {step_id}.{param_key}: "
                        f"{old_value!r} → {new_value!r}"
                    )

            elif fix_type == "add_param" and param_key and new_value is not None:
                if param_key not in params:
                    params[param_key] = new_value
                    self._memory.mark_patch_applied(recipe_id, i)
                    logger.info(f"Evolution: auto-added {param_key}={new_value!r} to {step_id}")

        patched["params"] = params
        return patched

    async def heal(
        self,
        step_config: Dict[str, Any],
        error: Exception,
        page_context: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Attempt to heal a failed step.

        Args:
            step_config: The failed step's configuration
            error: The exception that was raised
            page_context: Current page DOM/snapshot (if available)

        Returns:
            A patch dict if healing succeeded, None otherwise.
            Patch format: {
                "step_id": str,
                "fix_type": "replace_param" | "add_param",
                "param_key": str,
                "old_value": any,
                "new_value": any,
                "reason": str,
            }
        """
        if not self._chat_model:
            return None

        module_id = step_config.get("module", "")
        if not is_healable(module_id, error):
            return None

        step_id = step_config.get("id", "unknown")
        logger.info(f"Evolution: attempting to heal {step_id} ({module_id})")

        try:
            patch = await self._ask_llm_for_fix(step_config, error, page_context)
            if patch:
                patch["step_id"] = step_id
                logger.info(f"Evolution: healed {step_id} — {patch.get('reason', 'fixed')}")
            return patch
        except Exception as e:
            logger.warning(f"Evolution: healing failed for {step_id}: {e}")
            return None

    async def _ask_llm_for_fix(
        self,
        step_config: Dict[str, Any],
        error: Exception,
        page_context: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Ask the LLM to analyze the error and suggest a fix."""
        module_id = step_config.get("module", "")
        params = step_config.get("params", {})
        error_str = str(error)[:1000]  # Truncate long errors

        prompt = f"""A browser automation step failed. Analyze the error and suggest a fix.

Module: {module_id}
Current params: {json.dumps(params, indent=2, ensure_ascii=False)}
Error: {error_str}
"""

        if page_context:
            # Truncate page context to avoid token overflow
            ctx = page_context[:3000]
            prompt += f"\nCurrent page DOM (truncated):\n{ctx}\n"

        prompt += """
Respond with ONLY a JSON object (no markdown, no explanation):
{
  "fix_type": "replace_param",
  "param_key": "the param to change",
  "old_value": "current value",
  "new_value": "suggested new value",
  "reason": "brief explanation"
}

If the fix is to add a new param (e.g. adding a wait_ms):
{
  "fix_type": "add_param",
  "param_key": "param to add",
  "old_value": null,
  "new_value": "value",
  "reason": "brief explanation"
}

If you cannot determine a fix, respond with: {"fix_type": "none"}
"""

        from .._interfaces_compat import get_simple_chat

        chat_fn = get_simple_chat(self._chat_model)
        response = await chat_fn([
            {"role": "system", "content": "You are a browser automation debugger. Respond only with JSON."},
            {"role": "user", "content": prompt},
        ])

        return self._parse_fix_response(response)

    def _parse_fix_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse the LLM's fix suggestion."""
        # Strip markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            fix = json.loads(cleaned)
            if fix.get("fix_type") == "none":
                return None
            if fix.get("fix_type") in ("replace_param", "add_param") and fix.get("param_key"):
                return fix
            return None
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Evolution: could not parse LLM fix response")
            return None
