"""
Meta-Operations Modules

Modules for introspection and meta-operations on the workflow system itself.
"""
from typing import Any, Dict, List, Optional
from ..base import BaseModule
from ..registry import ModuleRegistry, register_module
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

    # Phase 2: Execution settings
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


@register_module(
    module_id='meta.modules.update_docs',
    version='1.0.0',
    category='meta',
    subcategory='documentation',
    tags=['meta', 'modules', 'documentation', 'generator'],
    label='Update Module Documentation',
    label_key='modules.meta.modules.update_docs.label',
    description='Generate or update MODULES.md documentation from registry',
    description_key='modules.meta.modules.update_docs.description',
    icon='FileText',
    color='#6B7280',

    # Connection types
    input_types=['none'],
    output_types=['file'],

    # Phase 2: Execution settings
    timeout=10,
    retryable=True,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.write'],

    params_schema={
        'output_path': {
            'type': 'string',
            'label': 'Output Path',
            'label_key': 'modules.meta.modules.update_docs.params.output_path.label',
            'description': 'Path to write MODULES.md file',
            'description_key': 'modules.meta.modules.update_docs.params.output_path.description',
            'default': 'docs/MODULES.md',
            'required': False
        },
        'include_examples': {
            'type': 'boolean',
            'label': 'Include Examples',
            'label_key': 'modules.meta.modules.update_docs.params.include_examples.label',
            'description': 'Include usage examples in documentation',
            'description_key': 'modules.meta.modules.update_docs.params.include_examples.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'file_path': {'type': 'string'},
        'modules_count': {'type': 'number'},
        'categories': {'type': 'array'}
    },
    examples=[
        {
            'title': 'Update module documentation',
            'params': {
                'output_path': 'docs/MODULES.md'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class UpdateModuleDocsModule(BaseModule):
    """Generate MODULES.md from current module registry"""

    def validate_params(self):
        self.output_path = self.params.get('output_path', 'docs/MODULES.md')
        self.include_examples = self.params.get('include_examples', True)

    async def execute(self) -> Any:
        # Get all modules
        all_metadata = ModuleRegistry.get_all_metadata()

        # Group by category
        by_category = {}
        for module_id, metadata in all_metadata.items():
            cat = metadata.get('category', 'other')
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((module_id, metadata))

        # Generate markdown
        content = self._generate_markdown(by_category)

        # Write to file
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return {
            'file_path': self.output_path,
            'modules_count': len(all_metadata),
            'categories': list(by_category.keys())
        }

    def _generate_markdown(self, by_category: Dict) -> str:
        """Generate complete MODULES.md content"""
        from datetime import datetime

        lines = [
            '# Flyto2 Module Registry\n\n',
            'Complete reference of all available modules.\n\n',
            f'**Last Updated:** {datetime.now().strftime("%Y-%m-%d")}\n',
            f'**Total Modules:** {sum(len(mods) for mods in by_category.values())}\n\n',
            '---\n\n'
        ]

        # Table of contents
        lines.append('## Categories\n\n')
        for category in sorted(by_category.keys()):
            count = len(by_category[category])
            lines.append(f'- [{category.title()}](#{category}) ({count} modules)\n')
        lines.append('\n---\n\n')

        # Modules by category
        for category in sorted(by_category.keys()):
            lines.append(f'## {category.title()}\n\n')

            for module_id, metadata in sorted(by_category[category]):
                lines.append(f'### {module_id}\n\n')
                lines.append(f'**Description:** {metadata.get("description", "")}\n\n')
                lines.append(f'**Category:** {metadata.get("category", "")}\n\n')

                # Parameters
                if 'params_schema' in metadata:
                    lines.append('**Parameters:**\n\n')
                    lines.append('| Parameter | Type | Required | Default | Description |\n')
                    lines.append('|-----------|------|----------|---------|-------------|\n')

                    for param_name, param_def in metadata['params_schema'].items():
                        ptype = param_def.get('type', 'any')
                        required = 'Yes' if param_def.get('required') else 'No'
                        default = str(param_def.get('default', '-'))
                        desc = param_def.get('description', '')
                        lines.append(f'| `{param_name}` | {ptype} | {required} | `{default}` | {desc} |\n')
                    lines.append('\n')

                # Output
                if 'output_schema' in metadata:
                    lines.append('**Output:**\n\n')
                    lines.append('| Field | Type | Description |\n')
                    lines.append('|-------|------|-------------|\n')

                    for out_name, out_def in metadata['output_schema'].items():
                        otype = out_def.get('type', 'any')
                        desc = out_def.get('description', '')
                        lines.append(f'| `{out_name}` | {otype} | {desc} |\n')
                    lines.append('\n')

                # Examples
                if self.include_examples and 'examples' in metadata:
                    lines.append('**Examples:**\n\n')
                    for i, example in enumerate(metadata['examples'], 1):
                        title = example.get('title', f'Example {i}')
                        lines.append(f'*{title}:*\n```yaml\n')
                        lines.append(f'- id: {module_id.replace(".", "_")}\n')
                        lines.append(f'  module: {module_id}\n')
                        lines.append('  params:\n')
                        for key, val in example.get('params', {}).items():
                            lines.append(f'    {key}: {json.dumps(val)}\n')
                        lines.append('```\n\n')

                lines.append('---\n\n')

        return ''.join(lines)
