"""
Workflow Output Collection

Collects and formats workflow execution output.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..variable_resolver import VariableResolver


class OutputCollector:
    """
    Collects and formats workflow output.
    """

    def __init__(
        self,
        workflow_id: str,
        workflow_name: str,
        workflow_version: str,
    ):
        self.workflow_id = workflow_id
        self.workflow_name = workflow_name
        self.workflow_version = workflow_version

    def collect(
        self,
        output_template: Dict[str, Any],
        context: Dict[str, Any],
        params: Dict[str, Any],
        workflow_metadata: Dict[str, Any],
        status: str,
        start_time: Optional[float],
        end_time: Optional[float],
        execution_log: List[Dict[str, Any]],
        resolver: VariableResolver,
    ) -> Dict[str, Any]:
        """
        Collect workflow output based on template or default structure.

        Args:
            output_template: Workflow output template
            context: Execution context
            params: Workflow parameters
            workflow_metadata: Workflow metadata dict
            status: Workflow status
            start_time: Execution start time
            end_time: Execution end time
            execution_log: List of executed steps
            resolver: Variable resolver for template resolution

        Returns:
            Formatted output dictionary
        """
        execution_time_ms = None
        if end_time and start_time:
            execution_time_ms = int((end_time - start_time) * 1000)

        metadata = {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'workflow_version': self.workflow_version,
            'status': status,
            'execution_time_ms': execution_time_ms,
            'steps_executed': len(execution_log),
            'timestamp': datetime.now().isoformat()
        }

        if not output_template:
            return {
                'status': status,
                'steps': context,
                'execution_time_ms': execution_time_ms,
                '__metadata__': metadata
            }

        resolved_output = resolver.resolve(output_template)

        if isinstance(resolved_output, dict):
            resolved_output['__metadata__'] = metadata
        else:
            resolved_output = {
                'result': resolved_output,
                '__metadata__': metadata
            }

        return resolved_output

    def get_execution_summary(
        self,
        workflow_description: str,
        status: str,
        start_time: Optional[float],
        end_time: Optional[float],
        execution_log: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Get execution summary with all workflow metadata.

        Returns:
            Summary dictionary
        """
        execution_time_ms = None
        if end_time and start_time:
            execution_time_ms = int((end_time - start_time) * 1000)

        return {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'workflow_version': self.workflow_version,
            'workflow_description': workflow_description,
            'status': status,
            'start_time': datetime.fromtimestamp(start_time).isoformat() if start_time else None,
            'end_time': datetime.fromtimestamp(end_time).isoformat() if end_time else None,
            'execution_time_ms': execution_time_ms,
            'steps_executed': len(execution_log),
            'execution_log': execution_log
        }
