# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Workflow Compiler — AI explores, then compiles to deterministic YAML.

The "Self-Grow" layer:
1. User describes a task in natural language
2. AI agent explores the website using browser tools, recording every action
3. Successful actions are compiled into a deterministic flyto YAML workflow
4. Next time, the workflow runs without AI (fast, free, reliable)

This is flyto's answer to browser-use's exploration model:
- browser-use: AI every time → slow, expensive
- flyto: AI once → compile → fast, free forever
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Browser actions that can be compiled to workflow steps
ACTION_TO_MODULE = {
    "goto": "browser.goto",
    "click": "browser.click",
    "type": "browser.type",
    "select": "browser.select",
    "scroll": "browser.scroll",
    "wait": "browser.wait",
    "screenshot": "browser.screenshot",
    "snapshot": "browser.snapshot",
    "extract": "browser.extract",
    "evaluate": "browser.evaluate",
    "upload": "browser.upload",
    "navigate_back": "browser.goto",
    "navigate_forward": "browser.goto",
}


class ActionRecorder:
    """Records browser actions during AI exploration.

    Attached to agent context, captures every tool call and result.
    """

    def __init__(self):
        self.actions: List[Dict[str, Any]] = []
        self.start_time = time.time()

    def record(self, tool_name: str, arguments: Dict[str, Any], result: Any):
        """Record a browser action."""
        self.actions.append({
            "tool": tool_name,
            "arguments": arguments,
            "result_ok": isinstance(result, dict) and result.get("ok", True),
            "timestamp": time.time() - self.start_time,
        })

    def get_successful_actions(self) -> List[Dict]:
        """Get only actions that succeeded."""
        return [a for a in self.actions if a.get("result_ok", False)]


class WorkflowCompiler:
    """Compile recorded browser actions into a deterministic YAML workflow.

    Usage:
        compiler = WorkflowCompiler()

        # Option 1: Compile from recorded actions
        recorder = ActionRecorder()
        # ... AI explores, recorder captures actions ...
        yaml_str = compiler.compile(recorder, name="my-recipe", description="...")

        # Option 2: Compile from AI agent steps
        yaml_str = compiler.compile_from_steps(agent_steps, name="my-recipe")
    """

    def compile(
        self,
        recorder: ActionRecorder,
        name: str = "generated-recipe",
        description: str = "",
        variables: Optional[Dict[str, str]] = None,
    ) -> str:
        """Compile recorded actions into a YAML workflow.

        Args:
            recorder: ActionRecorder with captured actions
            name: Recipe name
            description: Recipe description
            variables: Template variables (e.g. {"url": "https://example.com"})

        Returns:
            YAML string of the compiled workflow
        """
        actions = recorder.get_successful_actions()
        if not actions:
            return ""

        actions = self._deduplicate(actions)
        actions = self._optimize(actions)

        steps = self._actions_to_steps(actions, variables)
        return self._build_yaml(name, description, steps, variables)

    def compile_from_steps(
        self,
        agent_steps: List[Dict[str, Any]],
        name: str = "generated-recipe",
        description: str = "",
        variables: Optional[Dict[str, str]] = None,
    ) -> str:
        """Compile from llm.agent step output.

        agent_steps is the 'steps' array from agent execution result:
        [{"type": "tool_call", "tool": "browser--goto", "arguments": {...}}, ...]
        """
        actions = []
        for step in agent_steps:
            if step.get("type") != "tool_call":
                continue
            tool = step.get("tool", "").replace("--", ".")
            if not tool.startswith("browser."):
                continue
            actions.append({
                "tool": tool,
                "arguments": step.get("arguments", {}),
                "result_ok": True,
            })

        if not actions:
            return ""

        actions = self._optimize(actions)
        steps = self._actions_to_steps(actions, variables)
        return self._build_yaml(name, description, steps, variables)

    def _deduplicate(self, actions: List[Dict]) -> List[Dict]:
        """Remove consecutive duplicate actions (e.g. double-clicks)."""
        if not actions:
            return actions

        deduped = [actions[0]]
        for action in actions[1:]:
            prev = deduped[-1]
            if (action["tool"] == prev["tool"] and
                    action["arguments"] == prev["arguments"]):
                continue  # Skip duplicate
            deduped.append(action)
        return deduped

    def _optimize(self, actions: List[Dict]) -> List[Dict]:
        """Optimize action sequence.

        - Remove redundant screenshots between meaningful actions
        - Merge consecutive waits
        - Add implicit waits after navigation
        """
        optimized = []

        for i, action in enumerate(actions):
            tool = action["tool"]

            # Skip screenshot if followed by another screenshot
            if tool == "browser.screenshot":
                if i + 1 < len(actions) and actions[i + 1]["tool"] == "browser.screenshot":
                    continue

            # Merge consecutive waits
            if tool == "browser.wait" and optimized:
                prev = optimized[-1]
                if prev["tool"] == "browser.wait":
                    # Merge: keep the longer wait
                    prev_ms = prev["arguments"].get("duration_ms", 1000)
                    curr_ms = action["arguments"].get("duration_ms", 1000)
                    prev["arguments"]["duration_ms"] = max(prev_ms, curr_ms)
                    continue

            optimized.append(action)

        return optimized

    def _actions_to_steps(
        self,
        actions: List[Dict],
        variables: Optional[Dict[str, str]] = None,
    ) -> List[Dict]:
        """Convert actions to workflow step configs."""
        steps = []

        # Always start with browser.launch
        steps.append({
            "id": "launch",
            "module": "browser.launch",
            "label": "Launch Browser",
            "params": {"headless": True},
        })

        for i, action in enumerate(actions):
            tool = action["tool"]
            args = dict(action.get("arguments", {}))

            # Templatize variables (replace literal values with {{var}})
            if variables:
                args = self._templatize(args, variables)

            step_id = f"step_{i + 1}"
            module = tool  # Already in module format

            step = {
                "id": step_id,
                "module": module,
                "params": args,
            }

            steps.append(step)

        # End with browser.close
        steps.append({
            "id": "close",
            "module": "browser.close",
            "label": "Close Browser",
        })

        return steps

    def _templatize(self, args: Dict, variables: Dict[str, str]) -> Dict:
        """Replace literal values with template variables.

        If variables = {"url": "https://example.com"} and args has
        "url": "https://example.com", replace with "url": "[[url]]"
        """
        result = {}
        for key, value in args.items():
            if isinstance(value, str):
                for var_name, var_value in variables.items():
                    if var_value and var_value in value:
                        value = value.replace(var_value, f"[[{var_name}]]")
            result[key] = value
        return result

    def _build_yaml(
        self,
        name: str,
        description: str,
        steps: List[Dict],
        variables: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build the final YAML workflow."""
        workflow = {
            "name": name,
            "description": description or f"Auto-generated workflow ({len(steps)} steps)",
            "version": "1.0.0",
            "auto_generated": True,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        if variables:
            workflow["variables"] = variables

        workflow["steps"] = steps

        return yaml.dump(
            workflow,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
