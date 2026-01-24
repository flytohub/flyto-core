"""
Smoke tests for enterprise module interfaces.
"""

from datetime import datetime, timedelta

from core.enterprise import (
    SelectorStrategy,
    DesktopAction,
    DesktopElement,
    DesktopAutomationCapabilities,
    DocumentType,
    ExtractionField,
    ExtractionSchema,
    ExtractionResult,
    ValidationTask,
    ProcessEvent,
    EventLog,
    ProcessMetrics,
    ProcessDiscovery,
    Robot,
    RobotType,
    RobotStatus,
    RobotManager,
    ScheduledJob,
    Scheduler,
    QueueItem,
    QueueItemStatus,
    WorkQueue,
    QueueStats,
    Transaction,
    TransactionStatus,
    TransactionManager,
    StateType,
    StateDefinition,
    Transition,
    TransitionTrigger,
    StateMachine,
    StateMachineInstance,
    InstanceStatus,
    StateMachineEngine,
    LLMProvider,
    MessageRole,
    ChatMessage,
    ToolDefinition,
    ToolCall,
    LLMConfig,
    LLMResponse,
    LLMClient,
    AgentStrategy,
    MemoryType,
    AgentStep,
    AgentResult,
    AgentConfig,
    AIAgent,
    EvolutionType,
    WorkflowChange,
    EvolutionSuggestion,
    EvaluationResult,
    WorkflowEvolutionEngine,
    WorkflowGenerationResult,
    GenerationContext,
    WorkflowGenerator,
)
from core.enterprise.orchestrator import RobotCapabilities, ScheduleType


def test_enterprise_rpa_dataclasses():
    element = DesktopElement(selector="name=ok", selector_type=SelectorStrategy.ACCESSIBILITY)
    capabilities = DesktopAutomationCapabilities(
        selectors=[SelectorStrategy.ACCESSIBILITY],
        actions=[DesktopAction.CLICK],
    )
    assert element.selector == "name=ok"
    assert SelectorStrategy.ACCESSIBILITY in capabilities.selectors


def test_enterprise_idp_dataclasses():
    schema = ExtractionSchema(
        document_type=DocumentType.INVOICE,
        name="schema",
        fields=[ExtractionField(name="id", label="ID")],
        tables=[],
        validation_rules=[],
    )
    result = ExtractionResult(
        document_id="doc1",
        document_type=DocumentType.INVOICE,
        schema_version="1.0",
        classification_confidence=0.9,
        fields={},
        tables={},
    )
    task = ValidationTask(
        task_id="t1",
        document_id="d1",
        extraction_result=result,
        confidence_scores={"id": 0.9},
        fields_to_review=["id"],
    )
    assert schema.document_type == DocumentType.INVOICE
    assert result.document_id == "doc1"
    assert task.status.value == "pending"


def test_enterprise_mining_dataclasses():
    event = ProcessEvent(
        case_id="c1",
        activity="start",
        timestamp=datetime.now(),
    )
    log = EventLog(log_id="l1", name="log", events=[event])
    metrics = ProcessMetrics(
        log_id="l1",
        analysis_timestamp=datetime.now(),
        avg_case_duration=timedelta(seconds=1),
        median_case_duration=timedelta(seconds=1),
        min_case_duration=timedelta(seconds=1),
        max_case_duration=timedelta(seconds=1),
        throughput_per_day=1.0,
        rework_rate=0.0,
        automation_rate=1.0,
        first_time_right_rate=1.0,
        bottleneck_activities=[],
        waiting_time_breakdown={},
        variant_count=1,
        top_variants=[],
    )
    assert log.events[0].activity == "start"
    assert metrics.automation_rate == 1.0


def test_enterprise_orchestrator_queue_dataclasses():
    robot = Robot(
        robot_id="r1",
        name="robot",
        machine_name="host",
        robot_type=RobotType.ATTENDED,
        status=RobotStatus.AVAILABLE,
        last_heartbeat=datetime.now(),
        current_job_id=None,
        capabilities=RobotCapabilities(browser=True),
        environments=["dev"],
    )
    job = ScheduledJob(
        job_id="j1",
        workflow_id="wf1",
        name="job",
        schedule_type=ScheduleType.ONCE,
        run_at=datetime.now(),
    )
    queue_item = QueueItem(
        item_id="i1",
        queue_name="q1",
        reference="ref",
        data={"a": 1},
        status=QueueItemStatus.NEW,
        created_at=datetime.now(),
    )
    stats = QueueStats(
        queue_name="q1",
        timestamp=datetime.now(),
        total_items=1,
        new_items=1,
        in_progress=0,
        completed_today=0,
        failed_today=0,
        avg_processing_time_ms=0,
        throughput_per_hour=0.0,
    )
    transaction = Transaction(
        transaction_id="t1",
        queue_item_id="i1",
        workflow_id="wf1",
        status=TransactionStatus.STARTED,
        started_at=datetime.now(),
    )
    assert robot.robot_id == "r1"
    assert job.schedule_type == ScheduleType.ONCE
    assert queue_item.status == QueueItemStatus.NEW
    assert stats.queue_name == "q1"
    assert transaction.status == TransactionStatus.STARTED


def test_enterprise_state_machine_dataclasses():
    transition = Transition(
        name="go",
        from_state="s1",
        to_state="s2",
        trigger=TransitionTrigger(trigger_type="event", event_name="go"),
    )
    machine = StateMachine(
        machine_id="m1",
        name="machine",
        initial_state="s1",
        states={
            "s1": StateDefinition(state_id="s1", state_type=StateType.INITIAL, name="S1"),
            "s2": StateDefinition(state_id="s2", state_type=StateType.FINAL, name="S2"),
        },
        transitions=[transition],
        persistence=None,
    )
    instance = StateMachineInstance(
        instance_id="i1",
        machine_id="m1",
        machine_version="1.0",
        correlation_id="c1",
        current_state="s1",
        state_data={},
        created_at=datetime.now(),
        last_transition_at=datetime.now(),
        status=InstanceStatus.RUNNING,
    )
    assert machine.initial_state == "s1"
    assert instance.status == InstanceStatus.RUNNING


def test_enterprise_ai_native_dataclasses():
    message = ChatMessage(role=MessageRole.USER, content="hello")
    tool_def = ToolDefinition(name="t1", description="tool", parameters={})
    tool_call = ToolCall(id="c1", name="t1", arguments={"a": 1})
    config = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4")
    response = LLMResponse(content="ok", total_tokens=1)
    agent_step = AgentStep(
        timestamp=datetime.now(),
        step_number=0,
        thought="think",
        observation="obs",
    )
    agent_result = AgentResult(
        task="task",
        success=True,
        final_answer="done",
        iteration_count=1,
    )
    agent_config = AgentConfig(
        strategy=AgentStrategy.REACT,
        memory_type=MemoryType.BUFFER,
        max_iterations=1,
    )
    suggestion = EvolutionSuggestion(
        suggestion_id="s1",
        workflow_id="wf1",
        suggestion_type=EvolutionType.ERROR_RECOVERY,
        title="fix",
        description="desc",
        confidence=0.5,
        proposed_changes=[],
        expected_improvement={},
        status="pending",
    )
    eval_result = EvaluationResult(
        suggestion_id="s1",
        evaluated_at=datetime.now(),
        test_cases_run=1,
        test_cases_passed=1,
        test_cases_failed=0,
        recommended=True,
    )
    generation = WorkflowGenerationResult(
        success=True,
        workflow_yaml="wf",
        explanation="exp",
    )
    context = GenerationContext()

    assert message.role == MessageRole.USER
    assert tool_call.arguments["a"] == 1
    assert config.model == "gpt-4"
    assert response.content == "ok"
    assert agent_step.thought == "think"
    assert agent_result.iteration_count == 1
    assert agent_config.max_iterations == 1
    assert suggestion.status == "pending"
    assert eval_result.recommended is True
    assert generation.workflow_yaml == "wf"
    assert isinstance(context.available_modules, list)
