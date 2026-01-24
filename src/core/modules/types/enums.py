"""
Module Type Enums

Core enumerations for the module system.
"""

from enum import Enum


class ExecutionEnvironment(str, Enum):
    """
    Execution environment - determines where modules can safely run.

    LOCAL: Only safe to run on user's local machine
           (browser automation, file system access, etc.)
    CLOUD: Safe to run in cloud environment
           (API calls, data processing, pure functions)
    ALL: Can run in both environments (default for most modules)
    """
    LOCAL = "local"
    CLOUD = "cloud"
    ALL = "all"


class ModuleLevel(str, Enum):
    """
    Module level - determines priority and trust level.

    ATOMIC: Level 2 - Core atomic modules (building blocks, expert mode)
    COMPOSITE: Level 3 - Composite modules (normal user visible)
    TEMPLATE: Level 1 - Workflow templates (one-click solutions)
    PATTERN: Level 4 - Advanced patterns (system internal)
    THIRD_PARTY: Third-party API integrations
    AI_TOOL: AI tools for analysis
    EXTERNAL: External services (MCP, remote agents)
    """
    ATOMIC = "atomic"
    COMPOSITE = "composite"
    TEMPLATE = "template"
    PATTERN = "pattern"
    THIRD_PARTY = "third_party"
    AI_TOOL = "ai_tool"
    EXTERNAL = "external"


class UIVisibility(str, Enum):
    """
    UI visibility level for modules.

    DEFAULT: Show in normal mode (templates, composites)
    EXPERT: Show only in expert collapsed section (atomic modules)
    HIDDEN: Never show in UI (internal system modules)
    """
    DEFAULT = "default"
    EXPERT = "expert"
    HIDDEN = "hidden"


class ContextType(str, Enum):
    """
    Context types that modules can require or provide.

    Used for connection validation between modules.
    """
    BROWSER = "browser"
    PAGE = "page"
    FILE = "file"
    DATA = "data"
    API_RESPONSE = "api_response"
    DATABASE = "database"
    SESSION = "session"


class NodeType(str, Enum):
    """
    Node types for workflow canvas.

    Determines node behavior, port configuration, and execution semantics.
    Reference: FLYTO2_WORKFLOW_SPEC_V1.md
    """
    STANDARD = "standard"
    BRANCH = "branch"
    SWITCH = "switch"
    LOOP = "loop"
    MERGE = "merge"
    FORK = "fork"
    JOIN = "join"
    CONTAINER = "container"
    SUBFLOW = "subflow"
    TRIGGER = "trigger"
    START = "start"
    END = "end"
    BREAKPOINT = "breakpoint"
    # AI-specific node types (n8n-style cluster nodes)
    AI_AGENT = "ai_agent"
    AI_SUB_NODE = "ai_sub_node"


class EdgeType(str, Enum):
    """
    Edge types for workflow connections.

    CONTROL: Determines execution flow (which node runs next)
    RESOURCE: Injects data/tools without affecting flow order
    """
    CONTROL = "control"
    RESOURCE = "resource"


class DataType(str, Enum):
    """
    Data types for port type checking.

    Used for connection validation between ports.
    """
    ANY = "any"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    BINARY = "binary"
    TABLE = "table"
    BROWSER = "browser"
    PAGE = "page"
    ELEMENT = "element"
    FILE = "file"
    IMAGE = "image"
    JSON = "json"
    XML = "xml"
    HTML = "html"
    CREDENTIAL = "credential"
    # AI-specific types (for n8n-style multi-port connections)
    AI_MODEL = "ai_model"
    AI_MEMORY = "ai_memory"
    AI_TOOL = "ai_tool"
    AI_OUTPUT_PARSER = "ai_output_parser"


class PortImportance(str, Enum):
    """
    Port UI importance level.

    Controls where ports are displayed on the node.
    """
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ADVANCED = "advanced"


class StabilityLevel(str, Enum):
    """
    Module stability level - determines which environment sees the module.

    STABLE: Production ready, shown in all environments
    BETA: Testing phase, shown in development/staging only
    ALPHA: Early development, shown only in local dev mode
    DEPRECATED: Scheduled for removal, hidden but still functional
    """
    STABLE = "stable"
    BETA = "beta"
    ALPHA = "alpha"
    DEPRECATED = "deprecated"


class ModuleTier(str, Enum):
    """
    Module tier - determines UI display grouping and visibility.

    Controls how modules are organized in the node picker dialog.
    Frontend reads this value and displays accordingly.

    FEATURED: Prominent display, recommended for most users
    STANDARD: Normal display in category sections
    TOOLKIT: Collapsed "Toolkit" section for advanced/atomic modules
    INTERNAL: Hidden from UI, system use only
    """
    FEATURED = "featured"    # ⭐ Recommended/Popular
    STANDARD = "standard"    # 📦 Standard modules
    TOOLKIT = "toolkit"      # 🔧 Developer toolkit (atomic/advanced)
    INTERNAL = "internal"    # 🔒 System internal


# Display order for tiers (lower = higher in list)
TIER_DISPLAY_ORDER = {
    ModuleTier.FEATURED: 1,
    ModuleTier.STANDARD: 2,
    ModuleTier.TOOLKIT: 3,
    ModuleTier.INTERNAL: 99,
}


# Priority order for module selection (lower = higher priority)
LEVEL_PRIORITY = {
    ModuleLevel.ATOMIC: 1,
    ModuleLevel.COMPOSITE: 2,
    ModuleLevel.TEMPLATE: 3,
    ModuleLevel.PATTERN: 4,
    ModuleLevel.THIRD_PARTY: 5,
    ModuleLevel.AI_TOOL: 6,
    ModuleLevel.EXTERNAL: 7,
}
