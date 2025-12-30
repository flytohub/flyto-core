"""
Port Configuration

Default port configurations by node type.
"""

from typing import Any, Dict, List

from .enums import NodeType


# Default Port Configurations by NodeType
DEFAULT_PORTS_BY_NODE_TYPE: Dict[NodeType, Dict[str, List[Dict[str, Any]]]] = {
    NodeType.STANDARD: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True}
        ],
        "output": [
            {"id": "success", "label": "Success", "event": "success"},
            {"id": "error", "label": "Error", "event": "error"}
        ]
    },
    NodeType.BRANCH: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True}
        ],
        "output": [
            {"id": "true", "label": "True", "event": "true", "color": "#10B981"},
            {"id": "false", "label": "False", "event": "false", "color": "#F59E0B"},
            {"id": "error", "label": "Error", "event": "error", "color": "#EF4444"}
        ]
    },
    NodeType.SWITCH: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True}
        ],
        "output": [
            {"id": "default", "label": "Default", "event": "default", "color": "#6B7280"},
            {"id": "error", "label": "Error", "event": "error", "color": "#EF4444"}
        ]
        # Note: dynamic ports are added based on 'cases' param
    },
    NodeType.LOOP: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True}
        ],
        "output": [
            {"id": "iterate", "label": "Iterate", "event": "iterate", "color": "#F59E0B"},
            {"id": "done", "label": "Done", "event": "done", "color": "#10B981"},
            {"id": "error", "label": "Error", "event": "error", "color": "#EF4444"}
        ]
    },
    NodeType.MERGE: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": None}  # Unlimited
        ],
        "output": [
            {"id": "output", "label": "Output", "event": "success"}
        ]
    },
    NodeType.FORK: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True}
        ],
        "output": []  # Dynamic based on configuration
    },
    NodeType.JOIN: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": None}  # Unlimited
        ],
        "output": [
            {"id": "output", "label": "Output", "event": "success"},
            {"id": "timeout", "label": "Timeout", "event": "timeout"},
            {"id": "error", "label": "Error", "event": "error"}
        ]
    },
    NodeType.CONTAINER: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1}
        ],
        "output": [
            {"id": "success", "label": "Success", "event": "success"},
            {"id": "error", "label": "Error", "event": "error"}
        ]
    },
    NodeType.TRIGGER: {
        "input": [],
        "output": [
            {"id": "trigger", "label": "Trigger", "event": "trigger"}
        ]
    },
    NodeType.START: {
        "input": [],
        "output": [
            {"id": "start", "label": "Start", "event": "start"}
        ]
    },
    NodeType.END: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": None}
        ],
        "output": []
    },
    NodeType.BREAKPOINT: {
        "input": [
            {"id": "input", "label": "Input", "max_connections": 1, "required": True}
        ],
        "output": [
            {"id": "approved", "label": "Approved", "event": "approved", "color": "#10B981"},
            {"id": "rejected", "label": "Rejected", "event": "rejected", "color": "#EF4444"},
            {"id": "timeout", "label": "Timeout", "event": "timeout", "color": "#F59E0B"}
        ]
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
