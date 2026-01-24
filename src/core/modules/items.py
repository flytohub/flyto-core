"""
Item-Based Execution Data Structures.

This module provides the Item and NodeExecutionResult classes for item-based
workflow execution as specified in ITEM_PIPELINE_SPEC.md.

Design Principles:
- Item-based execution: Each node processes items[] arrays
- Backward compatible: Legacy results auto-wrapped via wrap_legacy_result()
- Per-item error tracking: Errors can be tracked per item
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class ExecutionStatus(Enum):
    """Execution status for node results."""
    SUCCESS = "success"      # All items processed successfully
    ERROR = "error"          # Entire node failed
    PARTIAL = "partial"      # Some items failed (continue execution)


class EdgeType(Enum):
    """
    Edge types for item propagation (ITEM_PIPELINE_SPEC.md Section 2.6).

    - CONTROL: Flow control only, no items propagated
    - DATA: Pass items to downstream (default)
    - ITERATE: Loop body edge, passes current iteration item
    - DONE: Loop completion edge, no items propagated
    """
    CONTROL = "control"
    DATA = "data"
    ITERATE = "iterate"
    DONE = "done"

    @classmethod
    def from_string(cls, value: str) -> "EdgeType":
        """Parse edge type from string with default fallback."""
        if not value:
            return cls.DATA  # Default is data
        try:
            return cls(value.lower())
        except ValueError:
            return cls.DATA


class MergeStrategy(Enum):
    """
    Merge strategies for multi-input nodes (ITEM_PIPELINE_SPEC.md Section 5).

    - APPEND: Concatenate all items from all inputs (default)
    - MULTIPLEX: Pair items by index (zip-like)
    - WAIT_ALL: Wait for all inputs before processing
    - FIRST: Use only the first input that arrives
    """
    APPEND = "append"
    MULTIPLEX = "multiplex"
    WAIT_ALL = "wait_all"
    FIRST = "first"

    @classmethod
    def from_string(cls, value: str) -> "MergeStrategy":
        """Parse merge strategy from string with default fallback."""
        if not value:
            return cls.APPEND
        try:
            return cls(value.lower())
        except ValueError:
            return cls.APPEND


@dataclass
class ItemMeta:
    """Item metadata for tracking source and lineage."""
    sourceNodeId: Optional[str] = None
    sourceItemIndex: Optional[int] = None
    executionIndex: Optional[int] = None


@dataclass
class ItemError:
    """Per-item error information."""
    message: str
    description: Optional[str] = None
    itemIndex: int = 0
    code: Optional[str] = None


@dataclass
class PairedItemInfo:
    """Track item source for merge/split operations."""
    item: int  # Source item index
    input: Optional[int] = None  # Source input index (for multi-input)


@dataclass
class BinaryData:
    """Binary data attachment for items (files, images, etc.)."""
    data: bytes
    mimeType: str
    fileName: Optional[str] = None
    fileExtension: Optional[str] = None
    fileSize: Optional[int] = None


@dataclass
class Item:
    """
    Single data item in the pipeline.

    Items are the fundamental data unit in item-based execution.
    Each item contains JSON data, optional binary attachments, and metadata.

    Example:
        item = Item(json={"name": "John", "age": 30})
        item_with_binary = Item(
            json={"filename": "doc.pdf"},
            binary={"file": BinaryData(data=b"...", mimeType="application/pdf")}
        )
    """
    json: Dict[str, Any] = field(default_factory=dict)
    binary: Optional[Dict[str, BinaryData]] = None
    meta: Optional[ItemMeta] = None
    error: Optional[ItemError] = None
    pairedItem: Optional[PairedItemInfo] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Item":
        """Create Item from dictionary."""
        return cls(json=data)

    @classmethod
    def from_value(cls, value: Any) -> "Item":
        """Create Item from any value."""
        if isinstance(value, Item):
            return value
        if isinstance(value, dict):
            return cls(json=value)
        return cls(json={"value": value})

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {"json": self.json}
        if self.binary:
            result["binary"] = {
                k: {
                    "mimeType": v.mimeType,
                    "fileName": v.fileName,
                    "fileSize": v.fileSize,
                }
                for k, v in self.binary.items()
            }
        if self.meta:
            result["meta"] = {
                "sourceNodeId": self.meta.sourceNodeId,
                "sourceItemIndex": self.meta.sourceItemIndex,
                "executionIndex": self.meta.executionIndex,
            }
        if self.error:
            result["error"] = {
                "message": self.error.message,
                "description": self.error.description,
                "itemIndex": self.error.itemIndex,
                "code": self.error.code,
            }
        if self.pairedItem:
            result["pairedItem"] = {
                "item": self.pairedItem.item,
                "input": self.pairedItem.input,
            }
        return result


@dataclass
class NodeError:
    """Node-level error information."""
    message: str
    code: str = "UNKNOWN"
    description: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionMeta:
    """Execution metadata for node results."""
    startTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    durationMs: int = 0
    itemsProcessed: int = 0
    itemsFailed: int = 0


@dataclass
class NodeExecutionResult:
    """
    Node execution result with item-based output.

    This replaces the legacy ModuleResult for item-based execution.
    Output data is a 2D array: [output_index][item_index]
    Most nodes have single output, so data is [[item1, item2, ...]]

    Example:
        # Single output with 3 items
        result = NodeExecutionResult(
            data=[[Item(json={"a": 1}), Item(json={"a": 2}), Item(json={"a": 3})]],
            status=ExecutionStatus.SUCCESS
        )

        # Multiple outputs (e.g., split node)
        result = NodeExecutionResult(
            data=[
                [Item(json={"matched": True})],
                [Item(json={"matched": False})]
            ],
            status=ExecutionStatus.SUCCESS
        )
    """
    data: List[List[Item]] = field(default_factory=lambda: [[]])
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    error: Optional[NodeError] = None
    meta: Optional[ExecutionMeta] = None
    hints: Optional[Dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        """Backward compatible ok property."""
        return self.status != ExecutionStatus.ERROR

    @property
    def items(self) -> List[Item]:
        """Get first output items (convenience for single-output nodes)."""
        if self.data and len(self.data) > 0:
            return self.data[0]
        return []

    @property
    def first_item(self) -> Optional[Item]:
        """Get first item from first output (convenience)."""
        items = self.items
        return items[0] if items else None

    @property
    def item_count(self) -> int:
        """Get total item count across all outputs."""
        return sum(len(output) for output in self.data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result: Dict[str, Any] = {
            "ok": self.ok,
            "status": self.status.value,
            "data": [[item.to_dict() for item in output] for output in self.data],
            "itemCount": self.item_count,
        }
        if self.error:
            result["error"] = {
                "message": self.error.message,
                "code": self.error.code,
                "description": self.error.description,
            }
        if self.meta:
            result["meta"] = {
                "durationMs": self.meta.durationMs,
                "itemsProcessed": self.meta.itemsProcessed,
                "itemsFailed": self.meta.itemsFailed,
            }
        if self.hints:
            result["hints"] = self.hints
        return result

    def to_legacy_dict(self) -> Dict[str, Any]:
        """
        Convert to legacy format for backward compatibility.

        Legacy format: {"ok": True, "data": {...}}
        This extracts the first item's json as data.
        """
        if self.status == ExecutionStatus.ERROR:
            return {
                "ok": False,
                "error": self.error.message if self.error else "Unknown error",
                "error_code": self.error.code if self.error else "UNKNOWN",
            }

        first = self.first_item
        return {
            "ok": True,
            "data": first.json if first else {},
        }


@dataclass
class ItemContext:
    """Context passed to execute_item for items mode execution."""
    items: List[Item] = field(default_factory=list)
    totalItems: int = 0
    inputsByPort: Optional[Dict[str, List[Item]]] = None


@dataclass
class StepInputItems:
    """
    Input items for a step with multi-input support.

    by_port: Items grouped by input port name
    merged: All items flattened (for simple single-input cases)
    """
    by_port: Dict[str, List[Item]] = field(default_factory=dict)
    merged: List[Item] = field(default_factory=list)

    @classmethod
    def from_items(cls, items: List[Item], port: str = "input") -> "StepInputItems":
        """Create from a simple list of items."""
        return cls(
            by_port={port: items},
            merged=items,
        )

    @classmethod
    def from_multiple_ports(cls, ports: Dict[str, List[Item]]) -> "StepInputItems":
        """Create from multiple input ports."""
        merged = []
        for items in ports.values():
            merged.extend(items)
        return cls(by_port=ports, merged=merged)


def wrap_legacy_result(result: Dict[str, Any]) -> NodeExecutionResult:
    """
    Convert legacy module result to item-based format.

    This provides backward compatibility for modules returning
    the old {"ok": True/False, "data": {...}} format.

    Args:
        result: Legacy result dict with ok, data, error fields

    Returns:
        NodeExecutionResult with data wrapped as single item
    """
    if result.get("ok", True):
        # Success: wrap data as single item
        data = result.get("data", {})
        if isinstance(data, list):
            # Already a list - convert each to Item
            items = [Item.from_value(d) for d in data]
        else:
            items = [Item(json=data if isinstance(data, dict) else {"value": data})]

        return NodeExecutionResult(
            data=[items],
            status=ExecutionStatus.SUCCESS,
            meta=ExecutionMeta(itemsProcessed=len(items)),
        )
    else:
        # Failure: return error result
        return NodeExecutionResult(
            data=[[]],
            status=ExecutionStatus.ERROR,
            error=NodeError(
                message=result.get("error", "Unknown error"),
                code=result.get("error_code", "UNKNOWN"),
            ),
        )


def items_to_legacy_context(result: NodeExecutionResult) -> Dict[str, Any]:
    """
    Convert NodeExecutionResult to legacy context format.

    This allows item-based results to work with existing workflow
    context that expects {"ok": True, "data": {...}} format.

    Args:
        result: Item-based execution result

    Returns:
        Legacy context dict with 'ok', 'data', and 'items' fields
    """
    legacy = result.to_legacy_dict()

    # Add items for new-style access (json only for backward compatibility)
    legacy["items"] = [item.json for item in result.items]
    # Preserve full item payloads for advanced consumers
    legacy["items_full"] = [item.to_dict() for item in result.items]

    return legacy


# =============================================================================
# Multi-Input Merge Functions (ITEM_PIPELINE_SPEC.md Section 5)
# =============================================================================


def merge_items_append(inputs: Dict[str, List[Item]]) -> List[Item]:
    """
    Merge items using APPEND strategy.

    Concatenates all items from all inputs in port order.

    Args:
        inputs: Dict of port_name -> items

    Returns:
        Merged list of items with pairedItem tracking
    """
    result = []
    for port_idx, (port_name, items) in enumerate(inputs.items()):
        for item_idx, item in enumerate(items):
            # Create new item with pairedItem tracking
            merged_item = Item(
                json=item.json.copy(),
                binary=item.binary,
                meta=item.meta,
                error=item.error,
                pairedItem=PairedItemInfo(item=item_idx, input=port_idx),
            )
            result.append(merged_item)
    return result


def merge_items_multiplex(inputs: Dict[str, List[Item]]) -> List[Item]:
    """
    Merge items using MULTIPLEX strategy.

    Pairs items by index (zip-like). For each index i, creates one output
    item containing data from all inputs at index i.

    Args:
        inputs: Dict of port_name -> items

    Returns:
        Multiplexed items (length = max items across all inputs)
    """
    if not inputs:
        return []

    port_names = list(inputs.keys())
    max_len = max(len(items) for items in inputs.values()) if inputs else 0

    result = []
    for i in range(max_len):
        # Combine data from all ports at index i
        combined_json = {}
        for port_name in port_names:
            items = inputs[port_name]
            if i < len(items):
                # Namespace by port name to avoid key collisions
                combined_json[port_name] = items[i].json

        result.append(Item(
            json=combined_json,
            pairedItem=PairedItemInfo(item=i),
        ))

    return result


def merge_items(
    inputs: Dict[str, List[Item]],
    strategy: MergeStrategy = MergeStrategy.APPEND
) -> List[Item]:
    """
    Merge items from multiple inputs using specified strategy.

    Args:
        inputs: Dict of port_name -> items
        strategy: Merge strategy to use

    Returns:
        Merged list of items
    """
    if not inputs:
        return []

    if strategy == MergeStrategy.APPEND:
        return merge_items_append(inputs)
    elif strategy == MergeStrategy.MULTIPLEX:
        return merge_items_multiplex(inputs)
    elif strategy == MergeStrategy.FIRST:
        # Return items from first non-empty input
        for items in inputs.values():
            if items:
                return items
        return []
    elif strategy == MergeStrategy.WAIT_ALL:
        # Same as append but semantically different (all inputs must be ready)
        return merge_items_append(inputs)
    else:
        return merge_items_append(inputs)


@dataclass
class EdgeInfo:
    """
    Edge information for item routing.

    Used to determine which items to pass downstream.
    """
    source_id: str
    target_id: str
    edge_type: EdgeType = EdgeType.DATA
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EdgeInfo":
        """Create EdgeInfo from edge dict."""
        return cls(
            source_id=data.get("source", ""),
            target_id=data.get("target", ""),
            edge_type=EdgeType.from_string(data.get("edge_type", "data")),
            source_handle=data.get("sourceHandle"),
            target_handle=data.get("targetHandle"),
        )

    def passes_items(self) -> bool:
        """Check if this edge type passes items."""
        return self.edge_type in (EdgeType.DATA, EdgeType.ITERATE)
