"""
Container Module - Embedded Subflow Execution

Workflow Spec v1.1:
- NodeType.CONTAINER for embedded workflows
- Executes subflow definition stored in params
- Returns __event__ for engine routing
- Supports variable scope inheritance
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ...types import NodeType, EdgeType, DataType


# Maximum nesting depth for containers
MAX_CONTAINER_DEPTH = 5


@register_module(
    module_id='flow.container',
    version='1.0.0',
    category='flow',
    tags=['flow', 'container', 'sandbox', 'subflow', 'nested'],
    label='Container',
    label_key='modules.flow.container.label',
    description='Embedded subflow container for organizing complex workflows',
    description_key='modules.flow.container.description',
    icon='Box',
    color='#8B5CF6',


    can_receive_from=['data.*', 'api.*', 'http.*', 'string.*', 'array.*', 'object.*', 'math.*', 'file.*', 'database.*', 'ai.*', 'flow.*', 'element.*'],
    can_connect_to=['*'],    # Workflow Spec v1.1
    node_type=NodeType.CONTAINER,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.container.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': False
        }
    ],

    output_ports=[
        {
            'id': 'success',
            'label': 'Success',
            'label_key': 'modules.flow.container.ports.success',
            'event': 'success',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'error',
            'label': 'Error',
            'label_key': 'common.ports.error',
            'event': 'error',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=True,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.SUBFLOW_DEFINITION(),
        presets.INHERIT_CONTEXT(default=True),
        presets.DATA_ARRAY(key='isolated_variables', label='Isolated Variables'),
        presets.DATA_ARRAY(key='export_variables', label='Export Variables'),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (success/error)'
        ,
                'description_key': 'modules.flow.container.output.__event__.description'},
        'outputs': {
            'type': 'object',
            'description': 'Output values by port',
                'description_key': 'modules.flow.container.output.outputs.description',
            'properties': {
                'success': {'type': 'object', 'description': 'Whether the operation completed successfully',
                'description_key': 'modules.flow.container.output.outputs.properties.success.description'},
                'error': {'type': 'object', 'description': 'Error message if operation failed',
                'description_key': 'modules.flow.container.output.outputs.properties.error.description'}
            }
        },
        'subflow_result': {
            'type': 'object',
            'description': 'Result from subflow execution'
        ,
                'description_key': 'modules.flow.container.output.subflow_result.description'},
        'exported_variables': {
            'type': 'object',
            'description': 'Variables exported from subflow'
        ,
                'description_key': 'modules.flow.container.output.exported_variables.description'},
        'node_count': {
            'type': 'integer',
            'description': 'Number of nodes in subflow'
        ,
                'description_key': 'modules.flow.container.output.node_count.description'},
        'execution_time_ms': {
            'type': 'number',
            'description': 'Total subflow execution time in milliseconds'
        ,
                'description_key': 'modules.flow.container.output.execution_time_ms.description'}
    },

    examples=[
        {
            'name': 'Simple container',
            'description': 'Container with inherited context',
            'params': {
                'subflow': {
                    'nodes': [],
                    'edges': []
                },
                'inherit_context': True
            },
            'note': 'Double-click to edit subflow content'
        },
        {
            'name': 'Isolated container',
            'description': 'Container with isolated variable scope',
            'params': {
                'subflow': {
                    'nodes': [],
                    'edges': []
                },
                'inherit_context': False
            },
            'note': 'Variables from parent are not accessible inside'
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=5000,
)
class ContainerModule(BaseModule):
    """
    Container Module - Embedded Subflow Execution

    Provides a way to group workflow nodes into a reusable,
    isolated container with optional variable scope inheritance.

    Features:
    - Embedded subflow definition
    - Configurable variable scope (inherit or isolate)
    - Variable export from subflow to parent
    - Max 5 levels of nesting

    Returns __event__ for workflow engine routing.
    """

    module_name = "Container"
    module_description = "Embedded subflow container"
    def validate_params(self) -> None:
        """Validate container parameters."""
        # Get subflow definition
        self.subflow = self.params.get('subflow', {'nodes': [], 'edges': []})
        if not isinstance(self.subflow, dict):
            self.subflow = {'nodes': [], 'edges': []}

        # Ensure nodes and edges are lists
        if 'nodes' not in self.subflow:
            self.subflow['nodes'] = []
        if 'edges' not in self.subflow:
            self.subflow['edges'] = []

        # Get context inheritance setting
        self.inherit_context = self.params.get('inherit_context', True)

        # Get isolated variables (not inherited from parent)
        self.isolated_variables = self.params.get('isolated_variables', [])
        if not isinstance(self.isolated_variables, list):
            self.isolated_variables = []

        # Get export variables (to export back to parent)
        self.export_variables = self.params.get('export_variables', [])
        if not isinstance(self.export_variables, list):
            self.export_variables = []

        # Validate nesting depth
        current_depth = self._get_current_depth()
        if current_depth >= MAX_CONTAINER_DEPTH:
            raise ValueError(
                f"Maximum container nesting depth ({MAX_CONTAINER_DEPTH}) exceeded. "
                f"Current depth: {current_depth}"
            )

    def _get_current_depth(self) -> int:
        """Get current nesting depth from context."""
        return self.context.get('__container_depth__', 0)

    def _prepare_subflow_context(self) -> Dict[str, Any]:
        """Prepare context for subflow execution."""
        subflow_context = {
            '__container_depth__': self._get_current_depth() + 1,
            '__parent_container_id__': self.context.get('__node_id__'),
        }

        if self.inherit_context:
            # Copy parent context, excluding internal keys
            for key, value in self.context.items():
                if not key.startswith('__') and key not in self.isolated_variables:
                    subflow_context[key] = value

        return subflow_context

    def _extract_exports(self, subflow_result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract variables to export from subflow result."""
        exports = {}

        if not self.export_variables:
            return exports

        # Extract specified variables from result
        result_data = subflow_result.get('outputs', {})
        for var_name in self.export_variables:
            if var_name in result_data:
                exports[var_name] = result_data[var_name]

        return exports

    async def execute(self) -> Dict[str, Any]:
        """
        Execute the container's embedded subflow.

        Returns:
            Dict with __event__ (success/error) for engine routing
        """
        import time
        start_time = time.time()

        try:
            nodes = self.subflow.get('nodes', [])
            edges = self.subflow.get('edges', [])
            node_count = len(nodes)

            # Empty subflow - just pass through
            if node_count == 0:
                return {
                    '__event__': 'success',
                    'outputs': {
                        'success': {
                            'message': 'Empty container - passed through',
                            'node_count': 0
                        }
                    },
                    'subflow_result': None,
                    'exported_variables': {},
                    'node_count': 0,
                    'execution_time_ms': (time.time() - start_time) * 1000
                }

            # Prepare subflow context
            subflow_context = self._prepare_subflow_context()

            # Execute subflow
            # Note: Actual execution is delegated to the workflow engine
            # This module prepares the context and returns the subflow definition
            # The engine will handle actual step execution
            subflow_result = await self._execute_subflow(
                nodes=nodes,
                edges=edges,
                context=subflow_context
            )

            # Extract exports
            exported_variables = self._extract_exports(subflow_result)

            execution_time = (time.time() - start_time) * 1000

            return {
                '__event__': 'success',
                'outputs': {
                    'success': {
                        'subflow_result': subflow_result,
                        'exported_variables': exported_variables,
                        'node_count': node_count
                    }
                },
                'subflow_result': subflow_result,
                'exported_variables': exported_variables,
                'node_count': node_count,
                'execution_time_ms': execution_time
            }

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {
                        'message': str(e),
                        'type': type(e).__name__
                    }
                },
                '__error__': {
                    'code': 'CONTAINER_EXECUTION_ERROR',
                    'message': str(e)
                },
                'subflow_result': None,
                'exported_variables': {},
                'node_count': len(self.subflow.get('nodes', [])),
                'execution_time_ms': execution_time
            }

    async def _execute_subflow(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute the embedded subflow.

        This method delegates to the workflow engine for actual execution.
        In a real implementation, this would:
        1. Create a sub-execution context
        2. Run the subflow nodes in order
        3. Collect and return results

        For now, we return the subflow definition for the engine to execute.
        """
        # Build execution request for engine
        execution_request = {
            'type': 'subflow',
            'nodes': nodes,
            'edges': edges,
            'context': context,
            'inherit_context': self.inherit_context,
            'parent_depth': self._get_current_depth()
        }

        # Check if we have an engine reference in context
        engine = self.context.get('__workflow_engine__')
        if engine and hasattr(engine, 'execute_subflow'):
            # Delegate to engine
            result = await engine.execute_subflow(execution_request)
            return result

        # Fallback: Return the subflow info
        # The engine will handle this during post-processing
        return {
            '__subflow_request__': execution_request,
            'pending': True,
            'node_count': len(nodes),
            'edge_count': len(edges)
        }
