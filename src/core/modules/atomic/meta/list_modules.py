"""
meta.modules.list - List all available modules from registry
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import ModuleRegistry, register_module
import json


@register_module(
    module_id='meta.modules.list',
    version='1.0.0',
    category='meta',
    subcategory='introspection',
    tags=['meta', 'modules', 'introspection', 'registry'],
    label='List Available Modules',
    label_key='modules.meta.modules.list.label',
    description='List all available modules in the registry',
    description_key='modules.meta.modules.list.description',
    icon='List',
    color='#6B7280',

    # Connection types
    input_types=['none'],
    output_types=['json'],


    can_receive_from=['*'],
    can_connect_to=['*'],    # Phase 2: Execution settings
    timeout=5,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'category': {
            'type': 'string',
            'label': 'Category Filter',
            'label_key': 'modules.meta.modules.list.params.category.label',
            'description': 'Filter modules by category (e.g., browser, data, ai)',
            'description_key': 'modules.meta.modules.list.params.category.description',
            'required': False
        },
        'tags': {
            'type': 'array',
            'label': 'Tags Filter',
            'label_key': 'modules.meta.modules.list.params.tags.label',
            'description': 'Filter modules by tags',
            'description_key': 'modules.meta.modules.list.params.tags.description',
            'required': False
        },
        'include_params': {
            'type': 'boolean',
            'label': 'Include Parameters',
            'label_key': 'modules.meta.modules.list.params.include_params.label',
            'description': 'Include parameter schema in output',
            'description_key': 'modules.meta.modules.list.params.include_params.description',
            'default': True,
            'required': False
        },
        'include_output': {
            'type': 'boolean',
            'label': 'Include Output Schema',
            'label_key': 'modules.meta.modules.list.params.include_output.label',
            'description': 'Include output schema in response',
            'description_key': 'modules.meta.modules.list.params.include_output.description',
            'default': True,
            'required': False
        },
        'format': {
            'type': 'select',
            'label': 'Output Format',
            'label_key': 'modules.meta.modules.list.params.format.label',
            'description': 'Format for module list output',
            'description_key': 'modules.meta.modules.list.params.format.description',
            'options': [
                {'label': 'JSON (structured)', 'value': 'json'},
                {'label': 'Markdown (human-readable)', 'value': 'markdown'},
                {'label': 'Compact (names only)', 'value': 'compact'}
            ],
            'default': 'json',
            'required': False
        }
    },
    output_schema={
        'modules': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'module_id': {'type': 'string'},
                    'label': {'type': 'string'},
                    'description': {'type': 'string'},
                    'category': {'type': 'string'},
                    'tags': {'type': 'array'},
                    'params_schema': {'type': 'object'},
                    'output_schema': {'type': 'object'}
                }
            }
        },
        'count': {'type': 'number'},
        'formatted': {'type': 'string'}
    },
    examples=[
        {
            'title': 'List all modules',
            'params': {}
        },
        {
            'title': 'List browser modules only',
            'params': {
                'category': 'browser',
                'include_params': True
            }
        },
        {
            'title': 'List AI modules as markdown',
            'params': {
                'tags': ['ai', 'llm'],
                'format': 'markdown'
            }
        },
        {
            'title': 'Compact list for AI prompts',
            'params': {
                'format': 'compact'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ListModulesModule(BaseModule):
    """List all available modules from registry"""

    def validate_params(self):
        self.category = self.params.get('category')
        self.tags = self.params.get('tags')
        self.include_params = self.params.get('include_params', True)
        self.include_output = self.params.get('include_output', True)
        self.format = self.params.get('format', 'json')

    async def execute(self) -> Any:
        # Get all module metadata
        all_metadata = ModuleRegistry.get_all_metadata(
            category=self.category,
            tags=self.tags
        )

        # Build module list
        modules = []
        for module_id, metadata in all_metadata.items():
            module_info = {
                'module_id': module_id,
                'label': metadata.get('label', module_id),
                'description': metadata.get('description', ''),
                'category': metadata.get('category', ''),
                'subcategory': metadata.get('subcategory', ''),
                'tags': metadata.get('tags', []),
                'version': metadata.get('version', '1.0.0')
            }

            # Add parameters if requested
            if self.include_params and 'params_schema' in metadata:
                module_info['params_schema'] = metadata['params_schema']

            # Add output schema if requested
            if self.include_output and 'output_schema' in metadata:
                module_info['output_schema'] = metadata['output_schema']

            modules.append(module_info)

        # Sort by module_id
        modules.sort(key=lambda x: x['module_id'])

        # Format output based on requested format
        formatted = self._format_output(modules)

        return {
            'modules': modules,
            'count': len(modules),
            'formatted': formatted
        }

    def _format_output(self, modules: List[Dict]) -> str:
        """Format module list based on requested format"""
        if self.format == 'markdown':
            return self._format_markdown(modules)
        elif self.format == 'compact':
            return self._format_compact(modules)
        else:  # json
            return json.dumps(modules, indent=2)

    def _format_markdown(self, modules: List[Dict]) -> str:
        """Format as markdown documentation"""
        lines = ['# Available Modules\n']

        # Group by category
        by_category = {}
        for module in modules:
            cat = module['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(module)

        # Output by category
        for category, mods in sorted(by_category.items()):
            lines.append(f'\n## {category.title()} Modules\n')

            for mod in mods:
                lines.append(f"### {mod['module_id']}\n")
                lines.append(f"{mod['description']}\n")

                if self.include_params and 'params_schema' in mod:
                    lines.append('\n**Parameters:**\n')
                    for param_name, param_def in mod['params_schema'].items():
                        required = ' (required)' if param_def.get('required') else ''
                        param_type = param_def.get('type', 'any')
                        param_desc = param_def.get('description', '')
                        lines.append(f"- `{param_name}` ({param_type}){required}: {param_desc}\n")

                if self.include_output and 'output_schema' in mod:
                    lines.append('\n**Output:**\n')
                    for out_name, out_def in mod['output_schema'].items():
                        out_type = out_def.get('type', 'any')
                        lines.append(f"- `{out_name}` ({out_type})\n")

                lines.append('\n---\n')

        return ''.join(lines)

    def _format_compact(self, modules: List[Dict]) -> str:
        """Format as compact list for AI prompts"""
        lines = ['Available Modules:\n']

        for mod in modules:
            # Compact format: module_id - description
            lines.append(f"- {mod['module_id']}: {mod['description']}\n")

            # Add minimal params info
            if self.include_params and 'params_schema' in mod:
                param_names = list(mod['params_schema'].keys())
                if param_names:
                    lines.append(f"  params: {', '.join(param_names)}\n")

        return ''.join(lines)
