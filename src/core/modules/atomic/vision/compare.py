"""
Vision Compare Module
Compare two images/screenshots for visual differences
"""

import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='vision.compare',
    stability="beta",
    version='1.0.0',
    category='atomic',
    subcategory='vision',
    tags=['vision', 'compare', 'diff', 'screenshot', 'regression', 'atomic'],
    label='Compare Images',
    label_key='modules.vision.compare.label',
    description='Compare two images and identify visual differences',
    description_key='modules.vision.compare.description',
    icon='GitCompare',
    color='#F59E0B',

    # Connection types
    input_types=['object', 'array'],
    output_types=['object'],
    can_connect_to=['test.*', 'file.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    handles_sensitive_data=False,
    required_permissions=['ai.vision'],

    params_schema=compose(
        presets.VISION_IMAGE_BEFORE(),
        presets.VISION_IMAGE_AFTER(),
        presets.VISION_COMPARISON_TYPE(),
        presets.VISION_THRESHOLD(),
        presets.VISION_FOCUS_AREAS(),
        presets.VISION_IGNORE_AREAS(),
        presets.LLM_MODEL(key='model', default='gpt-4o'),
        presets.API_KEY(key='api_key', label='OpenAI API Key'),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether comparison succeeded'
        ,
                'description_key': 'modules.vision.compare.output.ok.description'},
        'has_differences': {
            'type': 'boolean',
            'description': 'Whether significant differences were found'
        ,
                'description_key': 'modules.vision.compare.output.has_differences.description'},
        'similarity_score': {
            'type': 'number',
            'description': 'Similarity percentage (0-100)'
        ,
                'description_key': 'modules.vision.compare.output.similarity_score.description'},
        'differences': {
            'type': 'array',
            'description': 'List of identified differences'
        ,
                'description_key': 'modules.vision.compare.output.differences.description'},
        'summary': {
            'type': 'string',
            'description': 'Summary of comparison results'
        ,
                'description_key': 'modules.vision.compare.output.summary.description'},
        'recommendation': {
            'type': 'string',
            'description': 'Pass/Fail recommendation based on threshold'
        ,
                'description_key': 'modules.vision.compare.output.recommendation.description'}
    },
    examples=[
        {
            'title': 'Visual Regression Test',
            'title_key': 'modules.vision.compare.examples.regression.title',
            'params': {
                'image_before': './screenshots/baseline/home.png',
                'image_after': './screenshots/current/home.png',
                'comparison_type': 'visual_regression',
                'threshold': 5
            }
        },
        {
            'title': 'Layout Comparison',
            'title_key': 'modules.vision.compare.examples.layout.title',
            'params': {
                'image_before': './design/mockup.png',
                'image_after': './screenshots/implementation.png',
                'comparison_type': 'layout_diff',
                'focus_areas': ['header', 'main content']
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def vision_compare(context: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two images using AI vision"""
    try:
        import httpx
        use_httpx = True
    except ImportError:
        try:
            import aiohttp
            use_httpx = False
        except ImportError:
            raise ImportError("httpx or aiohttp required. Install with: pip install httpx")

    params = context['params']
    image_before = params['image_before']
    image_after = params['image_after']
    comparison_type = params.get('comparison_type', 'visual_regression')
    threshold = params.get('threshold', 5)
    focus_areas = params.get('focus_areas', [])
    ignore_areas = params.get('ignore_areas', [])
    model = params.get('model', 'gpt-4o')
    api_key = params.get('api_key') or os.getenv('OPENAI_API_KEY')

    if not api_key:
        return {
            'ok': False,
            'error': 'OpenAI API key not provided',
            'error_code': 'MISSING_API_KEY'
        }

    # Load images
    before_content = await _load_image(image_before)
    if before_content.get('error'):
        return {'ok': False, 'error': f"Before image: {before_content['error']}", 'error_code': 'IMAGE_ERROR'}

    after_content = await _load_image(image_after)
    if after_content.get('error'):
        return {'ok': False, 'error': f"After image: {after_content['error']}", 'error_code': 'IMAGE_ERROR'}

    # Build comparison prompt
    prompt = _build_comparison_prompt(comparison_type, focus_areas, ignore_areas, threshold)

    messages = [
        {
            "role": "system",
            "content": """You are an expert visual QA analyst comparing two screenshots.
Analyze the images carefully and provide:
1. A similarity score (0-100%)
2. List of specific differences found
3. Severity of each difference (Critical/Major/Minor/Cosmetic)
4. Pass/Fail recommendation based on the threshold

Return your analysis in this JSON format:
{
  "similarity_score": 95,
  "has_differences": true,
  "differences": [
    {"location": "header", "description": "Logo changed", "severity": "Minor"},
    {"location": "button", "description": "Color changed from blue to green", "severity": "Major"}
  ],
  "summary": "Brief summary of changes",
  "recommendation": "PASS" or "FAIL"
}"""
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"BEFORE image (baseline):\n{prompt}"},
                before_content['content'],
                {"type": "text", "text": "AFTER image (current):"},
                after_content['content']
            ]
        }
    ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 1500
    }

    try:
        if use_httpx:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                result = response.json()
        else:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    result = await response.json()

        if 'error' in result:
            return {
                'ok': False,
                'error': result['error'].get('message', 'Unknown error'),
                'error_code': 'OPENAI_ERROR'
            }

        analysis_text = result['choices'][0]['message']['content']

        # Parse JSON response
        import json
        import re

        json_match = re.search(r'\{[\s\S]*\}', analysis_text)
        if json_match:
            try:
                analysis = json.loads(json_match.group())
                similarity = analysis.get('similarity_score', 0)
                has_diff = analysis.get('has_differences', True)
                recommendation = 'PASS' if similarity >= (100 - threshold) else 'FAIL'

                return {
                    'ok': True,
                    'has_differences': has_diff,
                    'similarity_score': similarity,
                    'differences': analysis.get('differences', []),
                    'summary': analysis.get('summary', ''),
                    'recommendation': recommendation,
                    'raw_analysis': analysis_text
                }
            except json.JSONDecodeError:
                pass

        # Fallback: return raw analysis
        return {
            'ok': True,
            'has_differences': True,
            'similarity_score': None,
            'differences': [],
            'summary': analysis_text,
            'recommendation': 'REVIEW_NEEDED'
        }

    except Exception as e:
        logger.error(f"Vision compare failed: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'API_ERROR'
        }


async def _load_image(image_path: str) -> Dict[str, Any]:
    """Load image and prepare for API"""
    if image_path.startswith('http://') or image_path.startswith('https://'):
        return {
            'content': {
                "type": "image_url",
                "image_url": {"url": image_path, "detail": "high"}
            }
        }

    path = Path(image_path).expanduser()
    if not path.exists():
        return {'error': f'File not found: {image_path}'}

    try:
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('utf-8')

        suffix = path.suffix.lower()
        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}
        mime = mime_map.get(suffix, 'image/png')

        return {
            'content': {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{data}",
                    "detail": "high"
                }
            }
        }
    except Exception as e:
        return {'error': str(e)}


def _build_comparison_prompt(comp_type: str, focus: list, ignore: list, threshold: int) -> str:
    """Build comparison prompt"""
    prompt = f"Compare these two screenshots. Acceptable difference threshold: {threshold}%\n"

    type_instructions = {
        'visual_regression': "Focus on visual regressions - unexpected changes that might be bugs.",
        'layout_diff': "Focus on layout and structural differences - spacing, alignment, positioning.",
        'content_diff': "Focus on content changes - text, images, data displayed.",
        'full_analysis': "Perform a comprehensive comparison of all visual aspects."
    }

    prompt += type_instructions.get(comp_type, type_instructions['visual_regression'])

    if focus:
        prompt += f"\n\nFocus specifically on these areas: {', '.join(focus)}"

    if ignore:
        prompt += f"\n\nIgnore these areas (dynamic content): {', '.join(ignore)}"

    return prompt
