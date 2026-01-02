"""
Unified Error Codes for Validation

All validation errors use consistent error codes.
Cloud/Pro only need to display, not define rules.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass


class ErrorCode:
    """Validation error codes"""

    # Connection errors
    TYPE_MISMATCH = 'TYPE_MISMATCH'
    PORT_NOT_FOUND = 'PORT_NOT_FOUND'
    MAX_CONNECTIONS = 'MAX_CONNECTIONS'
    SELF_CONNECTION = 'SELF_CONNECTION'
    INCOMPATIBLE_MODULES = 'INCOMPATIBLE_MODULES'

    # Start node errors
    INVALID_START_NODE = 'INVALID_START_NODE'
    MISSING_START_PARAMS = 'MISSING_START_PARAMS'
    NO_START_NODE = 'NO_START_NODE'
    MULTIPLE_START_NODES = 'MULTIPLE_START_NODES'

    # Workflow structure errors
    ORPHAN_NODE = 'ORPHAN_NODE'
    CYCLE_DETECTED = 'CYCLE_DETECTED'
    DISCONNECTED_GRAPH = 'DISCONNECTED_GRAPH'

    # Parameter errors
    MISSING_REQUIRED_PARAM = 'MISSING_REQUIRED_PARAM'
    INVALID_PARAM_VALUE = 'INVALID_PARAM_VALUE'
    INVALID_PARAM_TYPE = 'INVALID_PARAM_TYPE'
    UNKNOWN_PARAM = 'UNKNOWN_PARAM'

    # Module errors
    MODULE_NOT_FOUND = 'MODULE_NOT_FOUND'
    MODULE_DISABLED = 'MODULE_DISABLED'


# Error message templates (support i18n key replacement)
ERROR_MESSAGES = {
    # Connection
    ErrorCode.TYPE_MISMATCH: {
        'en': '{to_module} requires {expected}, but received {received}',
        'zh-TW': '{to_module} 需要 {expected}，但收到 {received}',
    },
    ErrorCode.INCOMPATIBLE_MODULES: {
        'en': '{from_module} cannot connect to {to_module}',
        'zh-TW': '{from_module} 無法連接到 {to_module}',
    },
    ErrorCode.SELF_CONNECTION: {
        'en': 'A node cannot connect to itself',
        'zh-TW': '節點不能連接到自己',
    },
    ErrorCode.MAX_CONNECTIONS: {
        'en': 'Port {port} already has maximum connections ({max})',
        'zh-TW': '端口 {port} 已達最大連接數 ({max})',
    },

    # Start node
    ErrorCode.INVALID_START_NODE: {
        'en': '{module_id} cannot be used as a start node',
        'zh-TW': '{module_id} 不能作為起點節點',
    },
    ErrorCode.MISSING_START_PARAMS: {
        'en': 'Start node {module_id} requires parameters: {params}',
        'zh-TW': '起點節點 {module_id} 需要設定參數: {params}',
    },
    ErrorCode.NO_START_NODE: {
        'en': 'Workflow has no start node',
        'zh-TW': '工作流程沒有起點節點',
    },
    ErrorCode.MULTIPLE_START_NODES: {
        'en': 'Workflow has multiple start nodes: {nodes}',
        'zh-TW': '工作流程有多個起點節點: {nodes}',
    },

    # Workflow structure
    ErrorCode.ORPHAN_NODE: {
        'en': 'Node {node_id} is not connected to any other nodes',
        'zh-TW': '節點 {node_id} 沒有連接到任何其他節點',
    },
    ErrorCode.CYCLE_DETECTED: {
        'en': 'Cycle detected in workflow: {path}',
        'zh-TW': '工作流程中偵測到循環: {path}',
    },
    ErrorCode.DISCONNECTED_GRAPH: {
        'en': 'Workflow has disconnected components',
        'zh-TW': '工作流程包含未連接的部分',
    },

    # Parameters
    ErrorCode.MISSING_REQUIRED_PARAM: {
        'en': 'Missing required parameter: {param} in {node_id}',
        'zh-TW': '缺少必填參數: {node_id} 中的 {param}',
    },
    ErrorCode.INVALID_PARAM_VALUE: {
        'en': 'Invalid value for {param}: {value}',
        'zh-TW': '{param} 的值無效: {value}',
    },
    ErrorCode.UNKNOWN_PARAM: {
        'en': 'Unknown parameter "{param}" in {node_id}. Valid params: {valid_params}',
        'zh-TW': '{node_id} 中的參數 "{param}" 不存在。有效參數: {valid_params}',
    },

    # Module
    ErrorCode.MODULE_NOT_FOUND: {
        'en': 'Module not found: {module_id}',
        'zh-TW': '找不到模組: {module_id}',
    },
}


def explain_error(
    code: str,
    meta: Optional[Dict[str, Any]] = None,
    locale: str = 'en'
) -> Dict[str, Any]:
    """
    Convert error code to human-readable message.

    Args:
        code: Error code (e.g., 'TYPE_MISMATCH')
        meta: Error context for message formatting
        locale: Language code ('en', 'zh-TW')

    Returns:
        {
            'code': 'TYPE_MISMATCH',
            'title': 'Type Mismatch',
            'message': 'browser.click requires browser_page, but received string',
            'suggestion': 'Add a browser.launch node before browser.click'
        }
    """
    meta = meta or {}
    templates = ERROR_MESSAGES.get(code, {})
    template = templates.get(locale, templates.get('en', 'Unknown error'))

    # Format message with meta
    try:
        message = template.format(**meta)
    except KeyError:
        message = template

    # Generate title from code
    title = code.replace('_', ' ').title()

    return {
        'code': code,
        'title': title,
        'message': message,
        'meta': meta,
    }
