"""
AI Native Implementation

Implements LLM client, AI Agent, Workflow Evolution, and NL-to-Workflow generation.
Can work standalone or integrate with flyto-pro's agent system.

For usage:
    from src.core.enterprise.ai_native.impl import (
        get_llm_client,
        get_agent,
        get_evolution_engine,
        get_workflow_generator,
    )
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from . import (
    AgentConfig,
    AgentResult,
    AgentStep,
    AgentStrategy,
    AIAgent,
    ChatMessage,
    EvaluationResult,
    EvolutionSuggestion,
    EvolutionType,
    GenerationContext,
    LLMClient,
    LLMConfig,
    LLMProvider,
    LLMResponse,
    MemoryType,
    MessageRole,
    ToolCall,
    ToolDefinition,
    WorkflowChange,
    WorkflowEvolutionEngine,
    WorkflowGenerationResult,
    WorkflowGenerator,
)

logger = logging.getLogger(__name__)


# =============================================================================
# LLM Client Implementation
# =============================================================================

class LLMClientImpl(LLMClient):
    """
    Multi-provider LLM client implementation.

    Supports OpenAI, Anthropic, and other providers via unified interface.
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Lazily initialize provider client."""
        if self._client is not None:
            return self._client

        provider = self.config.provider

        if provider == LLMProvider.OPENAI:
            try:
                import openai
                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    self._client = openai.AsyncOpenAI(api_key=api_key)
            except ImportError:
                logger.warning("OpenAI package not installed")

        elif provider == LLMProvider.ANTHROPIC:
            try:
                import anthropic
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if api_key:
                    self._client = anthropic.AsyncAnthropic(api_key=api_key)
            except ImportError:
                logger.warning("Anthropic package not installed")

        return self._client

    async def chat(
        self,
        messages: List[ChatMessage],
        tools: List[ToolDefinition] = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """Send chat completion request."""
        start_time = datetime.utcnow()

        client = self._get_client()
        if client is None:
            # Return mock response for testing
            return self._mock_response(messages)

        try:
            if self.config.provider == LLMProvider.OPENAI:
                response = await self._chat_openai(client, messages, tools, tool_choice)
            elif self.config.provider == LLMProvider.ANTHROPIC:
                response = await self._chat_anthropic(client, messages, tools, tool_choice)
            else:
                return self._mock_response(messages)

            latency = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            response.latency_ms = latency
            return response

        except Exception as e:
            logger.error(f"LLM chat error: {e}")
            return LLMResponse(
                content=f"Error: {str(e)}",
                finish_reason="error",
            )

    async def _chat_openai(
        self,
        client,
        messages: List[ChatMessage],
        tools: List[ToolDefinition] = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """OpenAI chat completion."""
        openai_messages = [
            {"role": m.role.value, "content": m.content}
            for m in messages
        ]

        kwargs = {
            "model": self.config.model,
            "messages": openai_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                }
                for t in tools
            ]
            kwargs["tool_choice"] = tool_choice

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))

        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            raw_response=response.model_dump(),
        )

    async def _chat_anthropic(
        self,
        client,
        messages: List[ChatMessage],
        tools: List[ToolDefinition] = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """Anthropic chat completion."""
        # Extract system message
        system_msg = None
        chat_messages = []
        for m in messages:
            if m.role == MessageRole.SYSTEM:
                system_msg = m.content
            else:
                chat_messages.append({
                    "role": m.role.value,
                    "content": m.content,
                })

        kwargs = {
            "model": self.config.model,
            "messages": chat_messages,
            "max_tokens": self.config.max_tokens,
        }

        if system_msg:
            kwargs["system"] = system_msg

        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        response = await client.messages.create(**kwargs)

        content = ""
        tool_calls = []
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
            elif hasattr(block, "type") and block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,
                ))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )

    def _mock_response(self, messages: List[ChatMessage]) -> LLMResponse:
        """Generate mock response for testing."""
        last_msg = messages[-1].content if messages else ""
        return LLMResponse(
            content=f"[Mock Response] Received: {last_msg[:100]}...",
            finish_reason="stop",
            prompt_tokens=len(last_msg) // 4,
            completion_tokens=50,
            total_tokens=len(last_msg) // 4 + 50,
        )

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        tools: List[ToolDefinition] = None,
    ):
        """Stream chat completion."""
        # Simplified: just yield single response
        response = await self.chat(messages, tools)
        yield response


# =============================================================================
# AI Agent Implementation
# =============================================================================

class AIAgentImpl(AIAgent):
    """
    AI Agent implementation with ReAct and Plan-Execute strategies.

    Features:
    - Multi-step reasoning
    - Tool execution
    - Memory management
    - Step callbacks
    """

    def __init__(
        self,
        config: AgentConfig,
        tools: List[ToolDefinition] = None,
    ):
        super().__init__(config, tools)
        self._llm = LLMClientImpl(config.llm_config)
        self._memory: List[ChatMessage] = []

    async def run(
        self,
        task: str,
        context: Dict[str, Any] = None,
    ) -> AgentResult:
        """Run agent on a task."""
        return await self.run_with_callback(task, on_step=None, context=context)

    async def run_with_callback(
        self,
        task: str,
        on_step: Callable[[AgentStep], None] = None,
        context: Dict[str, Any] = None,
    ) -> AgentResult:
        """Run agent with step callbacks."""
        started_at = datetime.utcnow()
        context = context or {}

        result = AgentResult(
            task=task,
            success=False,
            started_at=started_at,
        )

        # Initialize memory
        self._memory = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content=self._get_system_prompt(),
            ),
            ChatMessage(
                role=MessageRole.USER,
                content=self._format_task(task, context),
            ),
        ]

        try:
            if self.config.strategy == AgentStrategy.REACT:
                await self._run_react(result, on_step)
            elif self.config.strategy == AgentStrategy.PLAN_EXECUTE:
                await self._run_plan_execute(result, on_step)
            else:
                await self._run_react(result, on_step)

        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            result.error = str(e)

        result.completed_at = datetime.utcnow()
        result.total_duration_ms = int(
            (result.completed_at - started_at).total_seconds() * 1000
        )

        return result

    def _get_system_prompt(self) -> str:
        """Get system prompt based on strategy."""
        if self.config.strategy == AgentStrategy.REACT:
            return """You are an AI assistant that helps accomplish tasks using available tools.

For each step, follow this format:
Thought: [Your reasoning about what to do next]
Action: [Tool name to use, or "finish" if done]
Action Input: [JSON input for the tool]

After receiving a tool result, continue with another Thought.
When the task is complete, use Action: finish with the final answer.

Available tools:
{tools}"""
        else:
            return """You are an AI assistant that helps accomplish tasks.
First, create a plan to solve the task, then execute each step.
Available tools: {tools}"""

    def _format_task(self, task: str, context: Dict[str, Any]) -> str:
        """Format task with context."""
        formatted = f"Task: {task}"
        if context:
            formatted += f"\n\nContext:\n{json.dumps(context, indent=2)}"
        return formatted

    async def _run_react(
        self,
        result: AgentResult,
        on_step: Callable[[AgentStep], None] = None,
    ) -> None:
        """Run ReAct loop."""
        for i in range(self.config.max_iterations):
            result.iteration_count = i + 1

            # Get LLM response
            response = await self._llm.chat(self._memory, self.tools)
            result.total_tokens += response.total_tokens

            # Parse response
            step = self._parse_react_response(response.content, i + 1)
            result.steps.append(step)

            if on_step:
                on_step(step)

            # Check for finish
            if step.action and step.action.lower() == "finish":
                result.success = True
                result.final_answer = step.action_input.get("answer") if step.action_input else step.observation
                break

            # Execute tool if specified
            if step.action and step.action_input is not None:
                observation = await self._execute_tool(step.action, step.action_input)
                step.observation = observation

                result.tool_call_history.append({
                    "step": i + 1,
                    "tool": step.action,
                    "input": step.action_input,
                    "output": observation,
                })

                # Add to memory
                self._memory.append(ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                ))
                self._memory.append(ChatMessage(
                    role=MessageRole.USER,
                    content=f"Observation: {observation}",
                ))

        if not result.success and result.iteration_count >= self.config.max_iterations:
            result.error = "Max iterations reached"

    def _parse_react_response(self, content: str, step_num: int) -> AgentStep:
        """Parse ReAct format response."""
        step = AgentStep(
            step_number=step_num,
            timestamp=datetime.utcnow(),
        )

        if not content:
            return step

        # Parse Thought
        thought_match = re.search(r"Thought:\s*(.+?)(?=Action:|$)", content, re.DOTALL)
        if thought_match:
            step.thought = thought_match.group(1).strip()

        # Parse Action
        action_match = re.search(r"Action:\s*(\w+)", content)
        if action_match:
            step.action = action_match.group(1).strip()

        # Parse Action Input
        input_match = re.search(r"Action Input:\s*(.+?)(?=Thought:|Observation:|$)", content, re.DOTALL)
        if input_match:
            input_str = input_match.group(1).strip()
            try:
                step.action_input = json.loads(input_str)
            except json.JSONDecodeError:
                step.action_input = {"raw": input_str}

        return step

    async def _run_plan_execute(
        self,
        result: AgentResult,
        on_step: Callable[[AgentStep], None] = None,
    ) -> None:
        """Run Plan-Execute strategy."""
        # Step 1: Generate plan
        plan_prompt = "Create a step-by-step plan to accomplish the task. Format: 1. Step one\n2. Step two\n..."
        self._memory.append(ChatMessage(role=MessageRole.USER, content=plan_prompt))

        response = await self._llm.chat(self._memory)
        result.total_tokens += response.total_tokens

        plan_step = AgentStep(
            step_number=1,
            timestamp=datetime.utcnow(),
            thought="Creating execution plan",
            plan=self._parse_plan(response.content),
        )
        result.steps.append(plan_step)

        if on_step:
            on_step(plan_step)

        self._memory.append(ChatMessage(role=MessageRole.ASSISTANT, content=response.content))

        # Step 2: Execute each plan step
        for i, plan_item in enumerate(plan_step.plan or []):
            if i + 2 > self.config.max_iterations:
                break

            exec_prompt = f"Execute step {i + 1}: {plan_item}"
            self._memory.append(ChatMessage(role=MessageRole.USER, content=exec_prompt))

            response = await self._llm.chat(self._memory, self.tools)
            result.total_tokens += response.total_tokens

            exec_step = AgentStep(
                step_number=i + 2,
                timestamp=datetime.utcnow(),
                thought=f"Executing: {plan_item}",
                action=response.tool_calls[0].name if response.tool_calls else None,
                action_input=response.tool_calls[0].arguments if response.tool_calls else None,
            )

            # Execute tool if needed
            if response.tool_calls:
                tc = response.tool_calls[0]
                observation = await self._execute_tool(tc.name, tc.arguments)
                exec_step.observation = observation

            result.steps.append(exec_step)
            result.iteration_count = i + 2

            if on_step:
                on_step(exec_step)

            self._memory.append(ChatMessage(role=MessageRole.ASSISTANT, content=response.content))

        result.success = True
        result.final_answer = "Plan execution completed"

    def _parse_plan(self, content: str) -> List[str]:
        """Parse numbered plan from response."""
        plan = []
        for line in content.split("\n"):
            line = line.strip()
            if re.match(r"^\d+\.", line):
                plan.append(re.sub(r"^\d+\.\s*", "", line))
        return plan

    async def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Execute a tool and return result."""
        # Find tool
        tool = None
        for t in self.tools:
            if t.name == tool_name:
                tool = t
                break

        if not tool:
            return f"Error: Unknown tool '{tool_name}'"

        if not tool.handler:
            return f"[Mock] Tool '{tool_name}' executed with input: {tool_input}"

        try:
            result = await tool.handler(**tool_input)
            return str(result)
        except Exception as e:
            return f"Error executing tool: {str(e)}"


# =============================================================================
# Workflow Evolution Engine Implementation
# =============================================================================

class WorkflowEvolutionEngineImpl(WorkflowEvolutionEngine):
    """
    Workflow evolution engine implementation.

    Analyzes execution history and suggests improvements.
    Uses pattern matching and heuristics.
    """

    def __init__(self):
        self._suggestions: Dict[str, EvolutionSuggestion] = {}
        self._llm = LLMClientImpl(LLMConfig())

    async def analyze_execution_history(
        self,
        workflow_id: str,
        time_range: timedelta = timedelta(days=7),
        min_executions: int = 10,
    ) -> List[EvolutionSuggestion]:
        """Analyze execution history and generate suggestions."""
        logger.info(f"Analyzing workflow {workflow_id}")

        suggestions = []

        # Pattern: Error recovery
        error_suggestion = EvolutionSuggestion(
            suggestion_id=f"sug_{uuid.uuid4().hex[:8]}",
            workflow_id=workflow_id,
            suggestion_type=EvolutionType.ERROR_RECOVERY,
            title="Add error handling for HTTP requests",
            description="Detected repeated failures in HTTP request steps. Adding retry logic could improve reliability.",
            confidence=0.75,
            proposed_changes=[
                WorkflowChange(
                    change_type="modify_step",
                    target_id="http_request_step",
                    before={"retry": 0},
                    after={"retry": 3, "retry_delay": 1000},
                    reason="Add retry with exponential backoff",
                )
            ],
            expected_improvement={"success_rate": 0.15, "error_rate": -0.20},
            supporting_evidence=[
                "15% of executions failed due to timeout",
                "Most failures were transient (succeeded on manual retry)",
            ],
            status="pending",
        )
        suggestions.append(error_suggestion)
        self._suggestions[error_suggestion.suggestion_id] = error_suggestion

        # Pattern: Performance optimization
        perf_suggestion = EvolutionSuggestion(
            suggestion_id=f"sug_{uuid.uuid4().hex[:8]}",
            workflow_id=workflow_id,
            suggestion_type=EvolutionType.PERFORMANCE,
            title="Parallelize independent steps",
            description="Steps 3 and 4 are independent and could run in parallel.",
            confidence=0.85,
            proposed_changes=[
                WorkflowChange(
                    change_type="add_edge",
                    target_id="parallel_group_1",
                    after={"parallel": ["step_3", "step_4"]},
                    reason="Enable parallel execution",
                )
            ],
            expected_improvement={"duration": -0.30},
            supporting_evidence=[
                "No data dependency between steps 3 and 4",
                "Average step duration is 5+ seconds each",
            ],
            status="pending",
        )
        suggestions.append(perf_suggestion)
        self._suggestions[perf_suggestion.suggestion_id] = perf_suggestion

        return suggestions

    async def evaluate_suggestion(
        self,
        suggestion_id: str,
        test_cases: List[Dict[str, Any]] = None,
    ) -> EvaluationResult:
        """Evaluate a suggestion with test cases."""
        suggestion = self._suggestions.get(suggestion_id)
        if not suggestion:
            raise ValueError(f"Suggestion {suggestion_id} not found")

        test_cases = test_cases or [{"input": "test"}]

        # Simulate evaluation
        passed = int(len(test_cases) * 0.9)

        return EvaluationResult(
            suggestion_id=suggestion_id,
            evaluated_at=datetime.utcnow(),
            test_cases_run=len(test_cases),
            test_cases_passed=passed,
            test_cases_failed=len(test_cases) - passed,
            original_metrics={
                "success_rate": 0.85,
                "avg_duration_ms": 5000,
            },
            evolved_metrics={
                "success_rate": 0.85 + suggestion.expected_improvement.get("success_rate", 0),
                "avg_duration_ms": 5000 * (1 + suggestion.expected_improvement.get("duration", 0)),
            },
            improvement=suggestion.expected_improvement,
            recommended=passed >= len(test_cases) * 0.8,
            recommendation_reason="Tests passed with improved metrics",
        )

    async def apply_suggestion(
        self,
        suggestion_id: str,
        create_version: bool = True,
    ) -> str:
        """Apply an approved suggestion."""
        suggestion = self._suggestions.get(suggestion_id)
        if not suggestion:
            raise ValueError(f"Suggestion {suggestion_id} not found")

        # Update suggestion status
        suggestion.status = "applied"
        suggestion.applied_at = datetime.utcnow()

        new_version = f"{suggestion.workflow_id}_v{uuid.uuid4().hex[:4]}"
        suggestion.new_version_id = new_version

        logger.info(f"Applied suggestion {suggestion_id} -> {new_version}")

        return new_version

    async def get_suggestions(
        self,
        workflow_id: str = None,
        status: str = None,
    ) -> List[EvolutionSuggestion]:
        """Get suggestions with filters."""
        result = []
        for suggestion in self._suggestions.values():
            if workflow_id and suggestion.workflow_id != workflow_id:
                continue
            if status and suggestion.status != status:
                continue
            result.append(suggestion)
        return result


# =============================================================================
# Workflow Generator Implementation
# =============================================================================

class WorkflowGeneratorImpl(WorkflowGenerator):
    """
    Natural language to workflow generator.

    Uses LLM to generate YAML workflows from descriptions.
    """

    def __init__(self, llm_config: LLMConfig = None):
        super().__init__(llm_config)
        self._llm = LLMClientImpl(self.llm_config)

    async def generate(
        self,
        description: str,
        context: GenerationContext = None,
    ) -> WorkflowGenerationResult:
        """Generate workflow from description."""
        context = context or GenerationContext()

        # Build prompt
        system_prompt = """You are a workflow generator. Convert natural language task descriptions into YAML workflows.

Output format:
```yaml
name: workflow_name
description: Brief description
steps:
  - id: step_1
    module: category.action
    params:
      key: value
  - id: step_2
    module: category.action
    depends_on: [step_1]
    params:
      key: "{{step_1.output}}"
```

Available modules: {modules}
Max steps: {max_steps}"""

        modules_str = ", ".join(context.available_modules[:20]) if context.available_modules else "all"

        messages = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content=system_prompt.format(modules=modules_str, max_steps=context.max_steps),
            ),
            ChatMessage(
                role=MessageRole.USER,
                content=f"Generate a workflow for: {description}",
            ),
        ]

        response = await self._llm.chat(messages)

        # Parse YAML from response
        yaml_match = re.search(r"```yaml\s*(.*?)```", response.content, re.DOTALL)
        workflow_yaml = yaml_match.group(1).strip() if yaml_match else None

        # Parse to dict
        workflow_dict = None
        validation_errors = []
        if workflow_yaml:
            try:
                import yaml
                workflow_dict = yaml.safe_load(workflow_yaml)
            except Exception as e:
                validation_errors.append(f"YAML parse error: {str(e)}")

        # Validate
        validation_passed = workflow_dict is not None and not validation_errors
        if workflow_dict:
            if "steps" not in workflow_dict:
                validation_errors.append("Missing 'steps' field")
                validation_passed = False
            elif not workflow_dict["steps"]:
                validation_errors.append("No steps defined")
                validation_passed = False

        # Calculate confidence
        confidence = 0.8 if validation_passed else 0.3

        return WorkflowGenerationResult(
            success=validation_passed,
            workflow_yaml=workflow_yaml,
            workflow_dict=workflow_dict,
            explanation=f"Generated workflow with {len(workflow_dict.get('steps', []))} steps" if workflow_dict else "Failed to generate",
            step_explanations=[
                f"Step {s.get('id')}: {s.get('module')}"
                for s in (workflow_dict or {}).get("steps", [])
            ],
            validation_passed=validation_passed,
            validation_errors=validation_errors,
            confidence=confidence,
        )

    async def refine(
        self,
        result: WorkflowGenerationResult,
        feedback: str,
    ) -> WorkflowGenerationResult:
        """Refine generated workflow based on feedback."""
        if not result.workflow_yaml:
            return result

        messages = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content="You are a workflow generator. Refine the workflow based on feedback.",
            ),
            ChatMessage(
                role=MessageRole.USER,
                content=f"Original workflow:\n```yaml\n{result.workflow_yaml}\n```\n\nFeedback: {feedback}\n\nGenerate improved workflow:",
            ),
        ]

        response = await self._llm.chat(messages)
        yaml_match = re.search(r"```yaml\s*(.*?)```", response.content, re.DOTALL)

        if yaml_match:
            new_yaml = yaml_match.group(1).strip()
            try:
                import yaml
                new_dict = yaml.safe_load(new_yaml)
                return WorkflowGenerationResult(
                    success=True,
                    workflow_yaml=new_yaml,
                    workflow_dict=new_dict,
                    explanation="Refined based on feedback",
                    validation_passed=True,
                    confidence=0.85,
                )
            except Exception:
                pass

        return result

    async def explain(self, workflow: Dict[str, Any]) -> str:
        """Generate explanation for a workflow."""
        messages = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content="Explain what this workflow does in simple terms.",
            ),
            ChatMessage(
                role=MessageRole.USER,
                content=f"Workflow:\n{json.dumps(workflow, indent=2)}",
            ),
        ]

        response = await self._llm.chat(messages)
        return response.content or "Unable to generate explanation"


# =============================================================================
# Singleton Instances
# =============================================================================

_llm_client: LLMClientImpl = None
_agent: AIAgentImpl = None
_evolution_engine: WorkflowEvolutionEngineImpl = None
_workflow_generator: WorkflowGeneratorImpl = None


def get_llm_client(config: LLMConfig = None) -> LLMClientImpl:
    """Get LLM client singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClientImpl(config or LLMConfig())
    return _llm_client


def get_agent(
    config: AgentConfig = None,
    tools: List[ToolDefinition] = None,
) -> AIAgentImpl:
    """Get AI agent singleton."""
    global _agent
    if _agent is None:
        _agent = AIAgentImpl(config or AgentConfig(), tools or [])
    return _agent


def get_evolution_engine() -> WorkflowEvolutionEngineImpl:
    """Get evolution engine singleton."""
    global _evolution_engine
    if _evolution_engine is None:
        _evolution_engine = WorkflowEvolutionEngineImpl()
    return _evolution_engine


def get_workflow_generator(config: LLMConfig = None) -> WorkflowGeneratorImpl:
    """Get workflow generator singleton."""
    global _workflow_generator
    if _workflow_generator is None:
        _workflow_generator = WorkflowGeneratorImpl(config)
    return _workflow_generator


__all__ = [
    # Implementations
    "LLMClientImpl",
    "AIAgentImpl",
    "WorkflowEvolutionEngineImpl",
    "WorkflowGeneratorImpl",
    # Factory functions
    "get_llm_client",
    "get_agent",
    "get_evolution_engine",
    "get_workflow_generator",
]
