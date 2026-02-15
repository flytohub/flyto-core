"""
Port Configuration

Default port configurations by node type.
Each port includes handle_id and position for UI handle derivation.
"""

from typing import Any, Dict, List

from .enums import NodeType


# Default Port Configurations by NodeType
DEFAULT_PORTS_BY_NODE_TYPE: Dict[NodeType, Dict[str, List[Dict[str, Any]]]] = {
    NodeType.STANDARD: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True,
             "handle_id": "target", "position": "left"}
        ],
        "output": [
            {"id": "success", "label": "Success", "event": "success",
             "handle_id": "output", "position": "right"},
            {"id": "error", "label": "Error", "event": "error", "color": "#EF4444",
             "handle_id": "source-error", "position": "right"}
        ]
    },
    NodeType.BRANCH: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True,
             "handle_id": "target", "position": "left"}
        ],
        "output": [
            {"id": "true", "label": "True", "event": "true", "color": "#10B981",
             "handle_id": "source-true", "position": "right"},
            {"id": "false", "label": "False", "event": "false", "color": "#F59E0B",
             "handle_id": "source-false", "position": "bottom"},
            {"id": "error", "label": "Error", "event": "error", "color": "#EF4444",
             "handle_id": "source-error", "position": "right"}
        ]
    },
    NodeType.SWITCH: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True,
             "handle_id": "target", "position": "left"}
        ],
        "output": [
            {"id": "default", "label": "Default", "event": "default", "color": "#6B7280",
             "handle_id": "source-default", "position": "bottom"},
            {"id": "error", "label": "Error", "event": "error", "color": "#EF4444",
             "handle_id": "source-error", "position": "right"}
        ]
        # Note: dynamic ports are added based on 'cases' param
    },
    NodeType.LOOP: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True,
             "handle_id": "in", "position": "left"}
        ],
        "output": [
            {"id": "iterate", "label": "Iterate", "event": "iterate", "color": "#3B82F6",
             "handle_id": "body_out", "position": "right"},
            {"id": "done", "label": "Done", "event": "done", "color": "#10B981",
             "handle_id": "done_out", "position": "bottom"},
            {"id": "error", "label": "Error", "event": "error", "color": "#EF4444",
             "handle_id": "source-error", "position": "right"}
        ]
    },
    NodeType.MERGE: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": None,
             "handle_id": "target", "position": "left"}
        ],
        "output": [
            {"id": "output", "label": "Output", "event": "success",
             "handle_id": "output", "position": "right"}
        ]
    },
    NodeType.FORK: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True,
             "handle_id": "target", "position": "left"}
        ],
        "output": []  # Dynamic based on configuration
    },
    NodeType.JOIN: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": None,
             "handle_id": "target", "position": "left"}
        ],
        "output": [
            {"id": "output", "label": "Output", "event": "success",
             "handle_id": "output", "position": "right"},
            {"id": "timeout", "label": "Timeout", "event": "timeout", "color": "#F59E0B",
             "handle_id": "source-timeout", "position": "bottom"},
            {"id": "error", "label": "Error", "event": "error", "color": "#EF4444",
             "handle_id": "source-error", "position": "right"}
        ]
    },
    NodeType.CONTAINER: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1,
             "handle_id": "target", "position": "left"}
        ],
        "output": [
            {"id": "success", "label": "Success", "event": "success",
             "handle_id": "output", "position": "right"}
        ]
    },
    NodeType.TRIGGER: {
        "input": [],
        "output": [
            {"id": "trigger", "label": "Trigger", "event": "trigger",
             "handle_id": "output", "position": "right"}
        ]
    },
    NodeType.START: {
        "input": [],
        "output": [
            {"id": "start", "label": "Start", "event": "start",
             "handle_id": "output", "position": "right"}
        ]
    },
    NodeType.END: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": None,
             "handle_id": "target", "position": "left"}
        ],
        "output": []
    },
    NodeType.BREAKPOINT: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True,
             "handle_id": "target", "position": "left"}
        ],
        "output": [
            {"id": "approved", "label": "Approved", "event": "approved", "color": "#10B981",
             "handle_id": "source-approved", "position": "right"},
            {"id": "rejected", "label": "Rejected", "event": "rejected", "color": "#EF4444",
             "handle_id": "source-rejected", "position": "bottom"},
            {"id": "timeout", "label": "Timeout", "event": "timeout", "color": "#F59E0B",
             "handle_id": "source-timeout", "position": "right"}
        ]
    },
    NodeType.AI_AGENT: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True,
             "handle_id": "target", "position": "left"},
            {"id": "model", "label": "Model", "edge_type": "resource", "data_type": "ai_model",
             "handle_id": "target-model", "position": "bottom"},
            {"id": "memory", "label": "Memory", "edge_type": "resource", "data_type": "ai_memory",
             "handle_id": "target-memory", "position": "bottom"},
            {"id": "tools", "label": "Tools", "edge_type": "resource", "data_type": "ai_tool",
             "handle_id": "target-tools", "position": "bottom"},
        ],
        "output": [
            {"id": "success", "label": "Success", "event": "success",
             "handle_id": "output", "position": "right"},
            {"id": "error", "label": "Error", "event": "error", "color": "#EF4444",
             "handle_id": "source-error", "position": "right"}
        ]
    },
    NodeType.AI_SUB_NODE: {
        "input": [
            {"id": "input", "label": "Input",
             "handle_id": "target", "position": "top"}
        ],
        "output": []
    },
}


def get_default_ports(node_type: NodeType) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get default port configuration for a node type.

    Args:
        node_type: The node type

    Returns:
        Dictionary with 'input' and 'output' port lists
    """
    return DEFAULT_PORTS_BY_NODE_TYPE.get(node_type, DEFAULT_PORTS_BY_NODE_TYPE[NodeType.STANDARD])
