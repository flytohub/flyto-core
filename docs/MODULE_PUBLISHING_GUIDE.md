# Module Publishing Guide

> 10 minutes to publish. Beautiful UI is auto-generated.

## Minimum Requirements (Must Have)

```python
@register_module(
    module_id='category.action',      # e.g., 'image.resize'
    category='image',                 # Category for auto-classification
    params_schema={...},              # Input parameters (see below)
    output_schema={...},              # Output structure (see below)
)
```

That's it. UI is auto-generated from your schema.

---

## params_schema: Type Determines UI

| Type | UI Component | Example |
|------|-------------|---------|
| `string` | Text input | `{'type': 'string'}` |
| `string` + `format: 'multiline'` | Textarea | `{'type': 'string', 'format': 'multiline'}` |
| `string` + `format: 'path'` | Path selector | `{'type': 'string', 'format': 'path'}` |
| `string` + `enum` | Dropdown | `{'type': 'string', 'enum': ['png', 'jpg']}` |
| `number` | Number input | `{'type': 'number'}` |
| `number` + `min/max/step` | Slider | `{'type': 'number', 'min': 0, 'max': 100, 'step': 1}` |
| `boolean` | Toggle switch | `{'type': 'boolean'}` |
| `file` | Upload (drag & drop) | `{'type': 'file'}` |
| `file` + `accept: 'image/*'` | Image upload with preview | `{'type': 'file', 'accept': 'image/*'}` |
| `file` + `accept: 'audio/*'` | Audio upload with player | `{'type': 'file', 'accept': 'audio/*'}` |

### Full Param Example

```python
params_schema={
    'input_image': {
        'type': 'file',
        'accept': 'image/*',
        'label': 'Input Image',
        'description': 'Image to process',
        'required': True
    },
    'quality': {
        'type': 'number',
        'min': 1,
        'max': 100,
        'step': 1,
        'default': 85,
        'label': 'Quality',
        'description': 'Output quality (1-100)'
    },
    'format': {
        'type': 'string',
        'enum': ['png', 'jpg', 'webp'],
        'default': 'png',
        'label': 'Output Format'
    }
}
```

---

## output_schema: Type Determines Result Display

| Output Type | Result Widget | Example |
|-------------|--------------|---------|
| `string` | Text block | `{'type': 'string'}` |
| `string` + `format: 'image'` | Image preview | `{'type': 'string', 'format': 'image'}` |
| `string` + `format: 'url'` | Clickable link | `{'type': 'string', 'format': 'url'}` |
| `file` | Download button | `{'type': 'file'}` |
| `array` | Table view | `{'type': 'array'}` |
| `object` | JSON viewer | `{'type': 'object'}` |

### Full Output Example

```python
output_schema={
    'result_image': {
        'type': 'string',
        'format': 'image',
        'description': 'Processed image (base64 or URL)'
    },
    'original_size': {
        'type': 'array',
        'description': '[width, height] in pixels'
    },
    'file_size': {
        'type': 'number',
        'description': 'Output file size in bytes'
    }
}
```

---

## Complete Module Example

```python
@register_module(
    module_id='image.compress',
    category='image',
    label='Compress Image',
    description='Compress image with quality control',
    icon='FileImage',

    params_schema={
        'input': {
            'type': 'file',
            'accept': 'image/*',
            'label': 'Input Image',
            'required': True
        },
        'quality': {
            'type': 'number',
            'min': 1,
            'max': 100,
            'default': 80,
            'label': 'Quality'
        },
        'max_width': {
            'type': 'number',
            'min': 100,
            'max': 4096,
            'label': 'Max Width',
            'required': False
        }
    },

    output_schema={
        'output': {
            'type': 'string',
            'format': 'image',
            'description': 'Compressed image'
        },
        'original_size': {'type': 'number'},
        'compressed_size': {'type': 'number'},
        'reduction': {'type': 'string'}
    },

    examples=[{
        'title': 'Compress to 60% quality',
        'params': {'quality': 60}
    }]
)
class ImageCompressModule(BaseModule):
    ...
```

---

## Value-Add Options (Optional - For Premium Modules)

| Field | Purpose | Example |
|-------|---------|---------|
| `icon` | Module icon (Lucide) | `'FileImage'` |
| `color` | Brand color | `'#3B82F6'` |
| `ui_group` | UI grouping | `'Image Tools'` |
| `presets` | One-click configs | `[{'name': 'Web', 'params': {...}}]` |
| `demo_assets` | Test files | `['sample.jpg']` |
| `docs_url` | Documentation link | `'https://...'` |

---

## UI Visibility Rules

Modules are auto-classified based on `category`:

| Category | Default Visibility | Target User |
|----------|-------------------|-------------|
| `ai`, `image`, `api`, `notification` | DEFAULT | Everyone |
| `string`, `array`, `math`, `utility` | EXPERT | Engineers |
| `flow`, `meta`, `test` | HIDDEN | Internal |

Override with: `ui_visibility=UIVisibility.DEFAULT`

---

## Checklist

- [ ] `module_id` follows `category.action` format
- [ ] `params_schema` has type for each param
- [ ] `output_schema` describes return structure
- [ ] `label` and `description` are user-friendly
- [ ] At least 1 example in `examples`
- [ ] Works locally before publishing
