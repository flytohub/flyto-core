"""
AI-Native Features - First-Class AI Integration

AI-native automation capabilities:
- LLM Integration (multi-provider)
- AI Agent Loop (ReAct, Plan-Execute)
- Workflow Self-Evolution
- Natural Language to Workflow

Reference: ITEM_PIPELINE_SPEC.md Section 19
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union


# =============================================================================
# LLM Integration
# =============================================================================

class LLMProvider(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    LOCAL = "local"  # Ollama, etc.
    CUSTOM = "custom"


class MessageRole(Enum):
    """Chat message roles."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ChatMessage:
    """Chat message."""
    role: MessageRole
    content: str
    name: Optional[str] = None  # For tool messages
    tool_call_id: Optional[str] = None


@dataclass
class ToolDefinition:
    """Tool definition for function calling."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    handler: Optional[Callable] = None


@dataclass
class ToolCall:
    """Tool call request from LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMConfig:
    """LLM configuration."""
    provider: LLMProvider = LLMProvider.OPENAI
    model: str = "gpt-4"

    # Generation parameters
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

    # Timeout
    timeout_seconds: int = 120

    # Retry
    max_retries: int = 3
    retry_delay_seconds: int = 1


@dataclass
class LLMResponse:
    """LLM response."""
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"

    # Usage
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Timing
    latency_ms: int = 0

    # Raw response
    raw_response: Optional[Dict[str, Any]] = None


class LLMClient:
    """
    LLM client interface.

    Multi-provider LLM integration.
    """

    def __init__(self, config: LLMConfig):
        self.config = config

    async def chat(
        self,
        messages: List[ChatMessage],
        tools: List[ToolDefinition] = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """
        Send chat completion request.

        Args:
            messages: Chat history
            tools: Available tools for function calling
            tool_choice: "auto", "none", or specific tool name

        Returns:
            LLM response
        """
        raise NotImplementedError("Implementation required")

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        tools: List[ToolDefinition] = None,
    ):
        """
        Stream chat completion.

        Yields partial responses as they arrive.
        """
        raise NotImplementedError("Implementation required")


# =============================================================================
# AI Agent
# =============================================================================

class AgentStrategy(Enum):
    """Agent execution strategies."""
    REACT = "react"              # Reasoning + Acting
    PLAN_EXECUTE = "plan_execute"  # Plan then Execute
    REFLEXION = "reflexion"      # Self-reflection


class MemoryType(Enum):
    """Agent memory types."""
    BUFFER = "buffer"      # Recent N messages
    SUMMARY = "summary"    # Summarized history
    VECTOR = "vector"      # Vector store retrieval


@dataclass
class AgentStep:
    """Single agent step (thought + action)."""
    step_number: int
    timestamp: datetime

    # Reasoning
    thought: Optional[str] = None
    plan: Optional[List[str]] = None

    # Action
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None

    # Observation (tool result)
    observation: Optional[str] = None

    # Self-reflection
    reflection: Optional[str] = None


@dataclass
class AgentResult:
    """Agent execution result."""
    task: str
    success: bool

    # Output
    final_answer: Optional[str] = None
    structured_output: Optional[Dict[str, Any]] = None

    # Execution trace
    steps: List[AgentStep] = field(default_factory=list)
    iteration_count: int = 0

    # Tool usage
    tool_call_history: List[Dict[str, Any]] = field(default_factory=list)

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_ms: int = 0

    # Token usage
    total_tokens: int = 0

    # Error
    error: Optional[str] = None


@dataclass
class AgentConfig:
    """Agent configuration."""
    strategy: AgentStrategy = AgentStrategy.REACT
    memory_type: MemoryType = MemoryType.BUFFER
    max_iterations: int = 10

    # LLM config
    llm_config: LLMConfig = field(default_factory=LLMConfig)

    # Memory settings
    memory_buffer_size: int = 10
    memory_summary_threshold: int = 20

    # Safety
    max_tokens_per_step: int = 4096
    require_final_answer: bool = True


class AIAgent:
    """
    AI Agent interface.

    Autonomous agent that can use tools to accomplish tasks.
    """

    def __init__(
        self,
        config: AgentConfig,
        tools: List[ToolDefinition] = None,
    ):
        self.config = config
        self.tools = tools or []

    async def run(
        self,
        task: str,
        context: Dict[str, Any] = None,
    ) -> AgentResult:
        """
        Run agent on a task.

        Args:
            task: Task description
            context: Optional context data

        Returns:
            Agent execution result
        """
        raise NotImplementedError("Implementation required")

    async def run_with_callback(
        self,
        task: str,
        on_step: Callable[[AgentStep], None] = None,
        context: Dict[str, Any] = None,
    ) -> AgentResult:
        """
        Run agent with step callbacks.

        Args:
            task: Task description
            on_step: Callback for each step
            context: Optional context data

        Returns:
            Agent execution result
        """
        raise NotImplementedError("Implementation required")


# =============================================================================
# Workflow Evolution
# =============================================================================

class EvolutionType(Enum):
    """Evolution suggestion types."""
    ERROR_RECOVERY = "error_recovery"      # Auto-fix common errors
    PERFORMANCE = "performance"            # Performance optimization
    RELIABILITY = "reliability"            # Reliability improvement
    SIMPLIFICATION = "simplification"      # Process simplification
    COST_REDUCTION = "cost_reduction"      # Cost optimization


@dataclass
class WorkflowChange:
    """Proposed workflow change."""
    change_type: str  # "add_step" | "remove_step" | "modify_step" | "add_edge" | "remove_edge"
    target_id: str  # Step or edge ID
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    reason: str = ""


@dataclass
class EvolutionSuggestion:
    """Workflow evolution suggestion."""
    suggestion_id: str
    workflow_id: str
    suggestion_type: EvolutionType

    # Suggestion details
    title: str
    description: str
    confidence: float  # 0-1

    # Proposed changes
    proposed_changes: List[WorkflowChange] = field(default_factory=list)

    # Expected impact
    expected_improvement: Dict[str, float] = field(default_factory=dict)
    # e.g., {"success_rate": 0.05, "duration": -0.2}

    # Evidence
    supporting_evidence: List[str] = field(default_factory=list)
    sample_failures: List[str] = field(default_factory=list)

    # Status
    status: str = "pending"  # "pending" | "approved" | "rejected" | "applied"

    # Review
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    # Application
    applied_at: Optional[datetime] = None
    new_version_id: Optional[str] = None


@dataclass
class EvaluationResult:
    """Evolution evaluation result."""
    suggestion_id: str
    evaluated_at: datetime

    # Test results
    test_cases_run: int
    test_cases_passed: int
    test_cases_failed: int

    # Metrics comparison
    original_metrics: Dict[str, float] = field(default_factory=dict)
    evolved_metrics: Dict[str, float] = field(default_factory=dict)
    improvement: Dict[str, float] = field(default_factory=dict)

    # Recommendation
    recommended: bool = False
    recommendation_reason: str = ""


class WorkflowEvolutionEngine:
    """
    Workflow evolution engine.

    Analyzes execution history and suggests improvements.
    """

    async def analyze_execution_history(
        self,
        workflow_id: str,
        time_range: timedelta = timedelta(days=7),
        min_executions: int = 10,
    ) -> List[EvolutionSuggestion]:
        """
        Analyze execution history and generate suggestions.

        Args:
            workflow_id: Workflow to analyze
            time_range: Time window for analysis
            min_executions: Minimum executions required

        Returns:
            List of evolution suggestions
        """
        raise NotImplementedError("Implementation required")

    async def evaluate_suggestion(
        self,
        suggestion_id: str,
        test_cases: List[Dict[str, Any]] = None,
    ) -> EvaluationResult:
        """
        Evaluate a suggestion with test cases.

        Args:
            suggestion_id: Suggestion to evaluate
            test_cases: Test cases to run

        Returns:
            Evaluation result
        """
        raise NotImplementedError("Implementation required")

    async def apply_suggestion(
        self,
        suggestion_id: str,
        create_version: bool = True,
    ) -> str:
        """
        Apply an approved suggestion.

        Args:
            suggestion_id: Suggestion to apply
            create_version: Create new workflow version

        Returns:
            New workflow version ID
        """
        raise NotImplementedError("Implementation required")

    async def get_suggestions(
        self,
        workflow_id: str = None,
        status: str = None,
    ) -> List[EvolutionSuggestion]:
        """Get suggestions with filters."""
        raise NotImplementedError("Implementation required")


# =============================================================================
# Natural Language to Workflow
# =============================================================================

@dataclass
class WorkflowGenerationResult:
    """Result of NL-to-workflow generation."""
    success: bool

    # Generated workflow
    workflow_yaml: Optional[str] = None
    workflow_dict: Optional[Dict[str, Any]] = None

    # Explanation
    explanation: str = ""
    step_explanations: List[str] = field(default_factory=list)

    # Validation
    validation_passed: bool = False
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)

    # Confidence
    confidence: float = 0.0
    uncertainty_notes: List[str] = field(default_factory=list)

    # Suggestions
    improvement_suggestions: List[str] = field(default_factory=list)


@dataclass
class GenerationContext:
    """Context for workflow generation."""
    # Available resources
    available_modules: List[str] = field(default_factory=list)
    available_credentials: List[str] = field(default_factory=list)
    available_workflows: List[str] = field(default_factory=list)

    # Constraints
    max_steps: int = 20
    allowed_categories: List[str] = field(default_factory=list)
    forbidden_modules: List[str] = field(default_factory=list)

    # Examples
    similar_workflows: List[Dict[str, Any]] = field(default_factory=list)


class WorkflowGenerator:
    """
    Natural language to workflow generator.

    Converts task descriptions to executable workflows.
    """

    def __init__(self, llm_config: LLMConfig = None):
        self.llm_config = llm_config or LLMConfig()

    async def generate(
        self,
        description: str,
        context: GenerationContext = None,
    ) -> WorkflowGenerationResult:
        """
        Generate workflow from description.

        Args:
            description: Natural language task description
            context: Optional generation context

        Returns:
            Generation result
        """
        raise NotImplementedError("Implementation required")

    async def refine(
        self,
        result: WorkflowGenerationResult,
        feedback: str,
    ) -> WorkflowGenerationResult:
        """
        Refine generated workflow based on feedback.

        Args:
            result: Previous generation result
            feedback: User feedback

        Returns:
            Refined result
        """
        raise NotImplementedError("Implementation required")

    async def explain(
        self,
        workflow: Dict[str, Any],
    ) -> str:
        """
        Generate explanation for a workflow.

        Args:
            workflow: Workflow definition

        Returns:
            Human-readable explanation
        """
        raise NotImplementedError("Implementation required")


# Update enterprise __init__.py exports
__all__ = [
    # LLM
    'LLMProvider',
    'MessageRole',
    'ChatMessage',
    'ToolDefinition',
    'ToolCall',
    'LLMConfig',
    'LLMResponse',
    'LLMClient',
    # Agent
    'AgentStrategy',
    'MemoryType',
    'AgentStep',
    'AgentResult',
    'AgentConfig',
    'AIAgent',
    # Evolution
    'EvolutionType',
    'WorkflowChange',
    'EvolutionSuggestion',
    'EvaluationResult',
    'WorkflowEvolutionEngine',
    # NL to Workflow
    'WorkflowGenerationResult',
    'GenerationContext',
    'WorkflowGenerator',
]
