"""
HTTP API Request/Response Models
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class ExecuteModuleRequest(BaseModel):
    module_id: str = Field(..., description="Module ID, e.g. 'browser.goto'")
    params: Dict[str, Any] = Field(default_factory=dict, description="Module parameters")
    context: Optional[Dict[str, Any]] = Field(None, description="Execution context (browser_session etc.)")


class RunWorkflowRequest(BaseModel):
    workflow: Dict[str, Any] = Field(..., description="Full workflow dict (parsed YAML)")
    params: Optional[Dict[str, Any]] = Field(None, description="Workflow input parameters")
    enable_evidence: bool = Field(True, description="Collect step evidence")
    enable_trace: bool = Field(True, description="Collect execution trace")


class ReplayRequest(BaseModel):
    modified_context: Optional[Dict[str, Any]] = Field(None, description="Context modifications")
    dry_run: bool = Field(False, description="Validate only, don't execute")


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class ExecuteModuleResponse(BaseModel):
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    browser_session: Optional[str] = None
    duration_ms: int = 0


class WorkflowRunResponse(BaseModel):
    ok: bool
    execution_id: str
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    trace: Optional[Dict[str, Any]] = None
    evidence_path: Optional[str] = None
    duration_ms: int = 0
    error: Optional[str] = None


class ReplayResponse(BaseModel):
    ok: bool
    execution_id: str
    original_execution_id: str
    start_step: str
    steps_executed: int = 0
    duration_ms: int = 0
    error: Optional[str] = None


class StepEvidenceResponse(BaseModel):
    step_id: str
    module_id: Optional[str] = None
    status: str = "success"
    duration_ms: int = 0
    context_before: Dict[str, Any] = {}
    context_after: Dict[str, Any] = {}
    output: Dict[str, Any] = {}
    error_message: Optional[str] = None


class ModuleInfo(BaseModel):
    module_id: str
    label: str = ""
    description: str = ""


class CategoryInfo(BaseModel):
    category: str
    label: str = ""
    description: str = ""
    count: int = 0
    use_cases: List[str] = []


class ServerInfo(BaseModel):
    name: str = "flyto-core"
    version: str
    module_count: int = 0
    category_count: int = 0
    capabilities: List[str] = []
