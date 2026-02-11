"""
Vision Analyze Module
Analyze images/screenshots using OpenAI Vision API (GPT-4V)
"""

import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='vision.analyze',
    stability="beta",
    version='1.0.0',
    category='atomic',
    subcategory='vision',
    tags=['vision', 'ai', 'image', 'screenshot', 'analysis', 'openai', 'gpt4v', 'atomic', 'ssrf_protected', 'path_restricted'],
    label='Analyze Image with AI',
    label_key='modules.vision.analyze.label',
    description='Analyze images using OpenAI Vision API (GPT-4V)',
    description_key='modules.vision.analyze.description',
    icon='Eye',
    color='#10A37F',

    # Connection types
    input_types=['string', 'image', 'object'],
    output_types=['object', 'string'],
    can_connect_to=['test.*', 'ui.*', 'file.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=60000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        presets.VISION_IMAGE(),
        presets.VISION_PROMPT(),
        presets.VISION_ANALYSIS_TYPE(),
        presets.VISION_CONTEXT(),
        presets.VISION_OUTPUT_FORMAT(),
        presets.LLM_MODEL(key='model', default='gpt-4o'),
        presets.MAX_TOKENS(key='max_tokens', default=1000),
        presets.API_KEY(key='api_key', label='OpenAI API Key'),
        presets.VISION_DETAIL(),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether analysis succeeded'
        ,
                'description_key': 'modules.vision.analyze.output.ok.description'},
        'analysis': {
            'type': 'string',
            'description': 'The AI analysis result'
        ,
                'description_key': 'modules.vision.analyze.output.analysis.description'},
        'structured': {
            'type': 'object',
            'description': 'Structured analysis data (if output_format is structured/json)'
        ,
                'description_key': 'modules.vision.analyze.output.structured.description'},
        'model': {
            'type': 'string',
            'description': 'Model used for analysis'
        ,
                'description_key': 'modules.vision.analyze.output.model.description',
            'placeholder': 'gpt-4o',
},
        'tokens_used': {
            'type': 'number',
            'description': 'Total tokens used'
        ,
                'description_key': 'modules.vision.analyze.output.tokens_used.description'}
    },
    examples=[
        {
            'title': 'UI Review',
            'title_key': 'modules.vision.analyze.examples.ui_review.title',
            'params': {
                'image': './screenshots/dashboard.png',
                'prompt': 'Review this dashboard UI. Evaluate: 1) Visual hierarchy 2) Color contrast 3) Button visibility 4) Overall usability. Suggest specific improvements.',
                'analysis_type': 'ui_review',
                'output_format': 'structured'
            }
        },
        {
            'title': 'Bug Detection',
            'title_key': 'modules.vision.analyze.examples.bug.title',
            'params': {
                'image': './screenshots/form.png',
                'prompt': 'Find any visual bugs, layout issues, or broken elements in this form',
                'analysis_type': 'bug_detection'
            }
        },
        {
            'title': 'Accessibility Check',
            'title_key': 'modules.vision.analyze.examples.a11y.title',
            'params': {
                'image': './screenshots/page.png',
                'prompt': 'Evaluate accessibility: color contrast, text readability, button sizes, clear labels',
                'analysis_type': 'accessibility'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def vision_analyze(context: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze image using OpenAI Vision API"""
    try:
        import httpx
    except ImportError:
        try:
            import aiohttp
            use_aiohttp = True
        except ImportError:
            raise ImportError(
                "httpx or aiohttp is required for vision.analyze. "
                "Install with: pip install httpx"
            )
    else:
        use_aiohttp = False

    params = context['params']
    image_input = params['image']
    prompt = params['prompt']
    analysis_type = params.get('analysis_type', 'general')
    additional_context = params.get('context', '')
    output_format = params.get('output_format', 'structured')
    model = params.get('model', 'gpt-4o')
    max_tokens = params.get('max_tokens', 1000)
    api_key = params.get('api_key') or os.getenv('OPENAI_API_KEY')
    detail = params.get('detail', 'high')

    if not api_key:
        return {
            'ok': False,
            'error': 'OpenAI API key not provided. Set OPENAI_API_KEY env var or pass api_key param',
            'error_code': 'MISSING_API_KEY'
        }

    # Prepare image data
    image_content = await _prepare_image(image_input, detail)
    if image_content.get('error'):
        return {
            'ok': False,
            'error': image_content['error'],
            'error_code': 'IMAGE_ERROR'
        }

    # Build system prompt based on analysis type
    system_prompt = _build_system_prompt(analysis_type, output_format, additional_context)

    # Build messages
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                image_content['content']
            ]
        }
    ]

    # Call OpenAI API
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens
    }

    try:
        if use_aiohttp:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    result = await response.json()
        else:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                result = response.json()

        if 'error' in result:
            return {
                'ok': False,
                'error': result['error'].get('message', 'Unknown OpenAI error'),
                'error_code': 'OPENAI_ERROR'
            }

        analysis_text = result['choices'][0]['message']['content']
        tokens_used = result.get('usage', {}).get('total_tokens', 0)

        # Parse structured output if requested
        structured_data = None
        if output_format in ['structured', 'json']:
            structured_data = _parse_structured_output(analysis_text)

        logger.info(f"Vision analysis completed: {len(analysis_text)} chars, {tokens_used} tokens")

        return {
            'ok': True,
            'analysis': analysis_text,
            'structured': structured_data,
            'model': model,
            'tokens_used': tokens_used
        }

    except Exception as e:
        logger.error(f"Vision analysis failed: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'API_ERROR'
        }


async def _prepare_image(image_input: str, detail: str) -> Dict[str, Any]:
    """Prepare image content for OpenAI API"""
    # Check if it's a URL
    if image_input.startswith('http://') or image_input.startswith('https://'):
        return {
            'content': {
                "type": "image_url",
                "image_url": {
                    "url": image_input,
                    "detail": detail
                }
            }
        }

    # Check if it's base64
    if image_input.startswith('data:image/'):
        return {
            'content': {
                "type": "image_url",
                "image_url": {
                    "url": image_input,
                    "detail": detail
                }
            }
        }

    # Assume it's a file path
    file_path = Path(image_input).expanduser()
    if not file_path.exists():
        return {'error': f'Image file not found: {image_input}'}

    # Read and encode file
    try:
        with open(file_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')

        # Determine MIME type
        suffix = file_path.suffix.lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        mime_type = mime_types.get(suffix, 'image/png')

        return {
            'content': {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_data}",
                    "detail": detail
                }
            }
        }
    except Exception as e:
        return {'error': f'Failed to read image: {e}'}


def _build_system_prompt(analysis_type: str, output_format: str, context: str) -> str:
    """Build system prompt based on analysis type"""
    base_prompts = {
        'general': "You are an AI assistant that analyzes images and provides detailed descriptions and insights.",
        'ui_review': """You are a senior UX/UI designer reviewing screenshots. Analyze:
- Visual hierarchy and layout
- Color scheme and contrast
- Typography and readability
- Button/CTA visibility and placement
- Consistency and alignment
- Mobile responsiveness indicators
- Overall user experience
Provide specific, actionable feedback.""",
        'accessibility': """You are an accessibility expert (WCAG specialist). Evaluate:
- Color contrast ratios
- Text size and readability
- Interactive element sizes (min 44x44px)
- Clear labels and instructions
- Focus indicators visibility
- Potential screen reader issues
Rate issues by severity: Critical, Major, Minor.""",
        'bug_detection': """You are a QA engineer looking for visual bugs. Find:
- Layout issues (overlapping, misalignment)
- Broken images or missing assets
- Text overflow or truncation
- Inconsistent spacing
- Z-index issues
- Responsive design problems
List each issue with location and severity.""",
        'comparison': "You are comparing two UI states. Identify all differences, changes, and potential regressions.",
        'data_extraction': "You are extracting structured data from the image. Return the data in a clean, organized format."
    }

    format_instructions = {
        'text': "Provide your analysis as clear, readable text.",
        'structured': """Structure your response with clear sections:
## Summary
[Brief overview]

## Findings
[Detailed findings with bullet points]

## Score
[If applicable, provide scores or ratings]

## Recommendations
[Specific, actionable recommendations]""",
        'json': "Return your analysis as valid JSON with keys: summary, findings (array), score (object), recommendations (array)",
        'checklist': "Format as a checklist with [PASS], [FAIL], or [WARN] for each item checked."
    }

    prompt = base_prompts.get(analysis_type, base_prompts['general'])
    prompt += "\n\n" + format_instructions.get(output_format, format_instructions['text'])

    if context:
        prompt += f"\n\nAdditional context: {context}"

    return prompt


def _parse_structured_output(text: str) -> Optional[Dict[str, Any]]:
    """Try to parse structured data from the response"""
    import json
    import re

    # Try to find JSON block
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to parse as JSON directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract sections from markdown
    sections = {}
    current_section = 'content'
    current_content = []

    for line in text.split('\n'):
        if line.startswith('## '):
            if current_content:
                sections[current_section] = '\n'.join(current_content).strip()
            current_section = line[3:].lower().replace(' ', '_')
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        sections[current_section] = '\n'.join(current_content).strip()

    return sections if sections else None
