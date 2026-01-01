"""
meta.modules.update_docs - Generate or update MODULES.md documentation from registry
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import ModuleRegistry, register_module
import json


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


    can_receive_from=['*'],
    can_connect_to=['*'],    # Phase 2: Execution settings
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
