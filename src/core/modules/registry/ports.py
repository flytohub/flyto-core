"""
Dynamic port generation utilities
"""
import re
from typing import Dict, List, Any


def generate_dynamic_ports(
    params: Dict[str, Any],
    dynamic_config: Dict[str, Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Generate dynamic ports from module params based on configuration.

    Used for Switch/Case nodes where output ports are generated from 'cases' param.

    Args:
        params: Module params (e.g., {'cases': [{'id': 'abc', 'value': 'US', 'label': 'United States'}]})
        dynamic_config: Dynamic port configuration from @register_module

    Returns:
        Dictionary with 'input' and/or 'output' port lists

    Example:
        config = {
            'output': {
                'from_param': 'cases',
                'stable_key_field': 'id',
                'id_field': 'value',
                'label_field': 'label',
                'event_prefix': 'case:',
                'include_default': True
            }
        }
        ports = generate_dynamic_ports({'cases': [...]}, config)
    """
    result = {}

    for direction, config in dynamic_config.items():
        if direction not in ('input', 'output'):
            continue

        from_param = config.get('from_param')
        if not from_param or from_param not in params:
            continue

        items = params[from_param]
        if not isinstance(items, list):
            continue

        ports = []
        stable_key_field = config.get('stable_key_field', 'id')
        id_field = config.get('id_field', 'value')
        label_field = config.get('label_field', 'label')
        event_prefix = config.get('event_prefix', '')
        color_field = config.get('color_field')

        for item in items:
            if not isinstance(item, dict):
                continue

            # Use stable_key for port.id if available, otherwise use id_field
            stable_key = item.get(stable_key_field)
            value = item.get(id_field, '')
            label = item.get(label_field, value)

            # Generate port.id: use stable_key if available, otherwise slug from value
            if stable_key:
                port_id = f"case_{stable_key}"
            else:
                # Fallback: slug from value
                port_id = f"case_{slugify(str(value))}"

            # Generate event
            event = f"{event_prefix}{value}"

            port = {
                'id': port_id,
                'label': label,
                'event': event,
                'direction': direction,
                '_stable_key': stable_key,  # Keep reference for edge binding
                '_value': value,            # Keep original value
            }

            # Add color if specified
            if color_field and color_field in item:
                port['color'] = item[color_field]

            ports.append(port)

        # Add default port if configured
        if config.get('include_default', False) and direction == 'output':
            ports.append({
                'id': 'default',
                'label': 'Default',
                'event': 'default',
                'direction': 'output',
                'color': '#6B7280'
            })

        result[direction] = ports

    return result


def slugify(text: str) -> str:
    """Convert text to a safe slug for port IDs."""
    # Replace special chars with underscore
    slug = re.sub(r'[^a-zA-Z0-9]', '_', text.lower())
    # Remove consecutive underscores
    slug = re.sub(r'_+', '_', slug)
    # Remove leading/trailing underscores
    return slug.strip('_')
