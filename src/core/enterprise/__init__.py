"""
Enterprise Features - Flyto Enterprise RPA & AI Capabilities

This module provides enterprise-grade automation capabilities:
- RPA: Desktop automation, vision, OCR
- IDP: Intelligent Document Processing
- Mining: Process Mining and discovery
- Orchestrator: Enterprise-grade scheduling and robot management
- Queue: Work queues and transaction support
- State Machine: Long-running workflow support
- AI-Native: LLM integration, AI agents, workflow evolution

Reference: ITEM_PIPELINE_SPEC.md Sections 13-21
"""

from .rpa import (
    SelectorStrategy,
    DesktopAction,
    DesktopElement,
    DesktopAutomationCapabilities,
)
from .idp import (
    DocumentType,
    ExtractionField,
    ExtractionSchema,
    ExtractionResult,
    ValidationTask,
)
from .mining import (
    ProcessEvent,
    EventLog,
    ProcessMetrics,
    ProcessDiscovery,
)
from .orchestrator import (
    Robot,
    RobotType,
    RobotStatus,
    RobotManager,
    ScheduledJob,
    Scheduler,
)
from .queue import (
    QueueItem,
    QueueItemStatus,
    WorkQueue,
    QueueStats,
    Transaction,
    TransactionStatus,
    TransactionManager,
)
from .state_machine import (
    StateType,
    StateDefinition,
    Transition,
    TransitionTrigger,
    StateMachine,
    StateMachineInstance,
    InstanceStatus,
    StateMachineEngine,
)
from .ai_native import (
    # LLM
    LLMProvider,
    MessageRole,
    ChatMessage,
    ToolDefinition,
    ToolCall,
    LLMConfig,
    LLMResponse,
    LLMClient,
    # Agent
    AgentStrategy,
    MemoryType,
    AgentStep,
    AgentResult,
    AgentConfig,
    AIAgent,
    # Evolution
    EvolutionType,
    WorkflowChange,
    EvolutionSuggestion,
    EvaluationResult,
    WorkflowEvolutionEngine,
    # NL to Workflow
    WorkflowGenerationResult,
    GenerationContext,
    WorkflowGenerator,
)

__all__ = [
    # RPA
    'SelectorStrategy',
    'DesktopAction',
    'DesktopElement',
    'DesktopAutomationCapabilities',
    # IDP
    'DocumentType',
    'ExtractionField',
    'ExtractionSchema',
    'ExtractionResult',
    'ValidationTask',
    # Mining
    'ProcessEvent',
    'EventLog',
    'ProcessMetrics',
    'ProcessDiscovery',
    # Orchestrator
    'Robot',
    'RobotType',
    'RobotStatus',
    'RobotManager',
    'ScheduledJob',
    'Scheduler',
    # Queue
    'QueueItem',
    'QueueItemStatus',
    'WorkQueue',
    'QueueStats',
    'Transaction',
    'TransactionStatus',
    'TransactionManager',
    # State Machine
    'StateType',
    'StateDefinition',
    'Transition',
    'TransitionTrigger',
    'StateMachine',
    'StateMachineInstance',
    'InstanceStatus',
    'StateMachineEngine',
    # AI-Native: LLM
    'LLMProvider',
    'MessageRole',
    'ChatMessage',
    'ToolDefinition',
    'ToolCall',
    'LLMConfig',
    'LLMResponse',
    'LLMClient',
    # AI-Native: Agent
    'AgentStrategy',
    'MemoryType',
    'AgentStep',
    'AgentResult',
    'AgentConfig',
    'AIAgent',
    # AI-Native: Evolution
    'EvolutionType',
    'WorkflowChange',
    'EvolutionSuggestion',
    'EvaluationResult',
    'WorkflowEvolutionEngine',
    # AI-Native: NL to Workflow
    'WorkflowGenerationResult',
    'GenerationContext',
    'WorkflowGenerator',
]
