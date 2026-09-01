# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Vision Analyze Module
Analyze images/screenshots using OpenAI Vision API (GPT-4V)

HOW FAR THIS MODULE FOLLOWS REALITY

The ceiling here is ACCEPTED, and no path in this file can move it. A vision
model returning prose about a screenshot is the provider describing its own
work; nothing in this module measures anything about the world the screenshot
came from. Five return paths, four answers:

  a completion came back                        ACCEPTED
      `analysis` is text OpenAI generated. That the call happened is the only
      fact in it. Whether the model actually looked at the image, described the
      image we sent rather than a plausible one, or is right about any of it --
      none of that is evaluated here, and `analysis_type='bug_detection'`
      returning "no bugs found" is a sentence, not a clean test run.

  no API key, or the image could not be read    FAILED
      Both return above the request. Nothing was sent, nothing was billed, and
      that is known rather than inferred.

  OpenAI answered with an error object          FAILED
      The provider gave a definite negative. No completion was produced. This
      is not INDETERMINATE: the uncertainty a timeout has is exactly the thing
      an error body removes.

  the request raised                            FAILED or INDETERMINATE
      Split by `_outcomes.classify_request_failure`, which claims FAILED only
      when the connection is known never to have come up, and INDETERMINATE for
      everything else -- a read timeout may well have been received, processed
      and billed. See that module for why the default leans that way.

WHY `tokens_used` DOES NOT EARN OBSERVED. It is the provider's own accounting
of the provider's own work, which is the definition of taking the peer's word.
It is also, on the path where `usage` is missing from the response, a literal
`0` written in this file -- the same shape as `file.write`'s `bytes_written`,
where a number that reads identically whether the effect happened or not was
mistaken for evidence of it. The envelope says which of the two it is on every
success, instead of putting one integer where two facts belong.
"""

import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import validate_path_with_env_config
from ...registry import register_module
from ...schema import compose, presets
from ._outcomes import classify_request_failure

logger = logging.getLogger(__name__)


# ── Outcome ────────────────────────────────────────────────────────────────
#
# The envelopes below ride on `ok: False` returns as well as the success one.
# `wrap_legacy_result` turns `ok: False` into an ERROR result and `to_legacy_dict`
# then keeps only the message and the code, so today those envelopes are dropped
# on the way out of the step -- the same trade `dns.lookup` and
# `http.request._error_result` describe. They are attached anyway: the fact is
# true whether or not a consumer exists yet, and writing them only once one does
# means the consumer is built against error results that carry nothing.


def _never_sent(reason: str, detail: str) -> Dict[str, Any]:
    """FAILED: a guard returned above the request, so no call was made."""
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'vision_request_not_sent',
            'reason': reason,
            'measured_by': 'a guard that returned before the HTTP request',
            'detail': detail,
        }],
    )


def _provider_refused(message: str) -> Dict[str, Any]:
    """FAILED: OpenAI answered, and the answer was an error object."""
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'vision_provider_error',
            'provider': 'openai',
            'provider_message': message,
            'measured_by': "the 'error' object in the provider's own response body",
            'detail': (
                'The provider answered and declined. No completion was '
                'produced. Definite, not uncertain -- which is why this is '
                'failed and a timeout is not.'
            ),
        }],
    )


def _request_raised(error: BaseException) -> Dict[str, Any]:
    """FAILED or INDETERMINATE, decided by how far the request got."""
    rung, why = classify_request_failure(error)
    return envelope(
        rung,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'vision_request_raised',
            'provider': 'openai',
            'error_type': type(error).__name__,
            'measured_by': None,
            'detail': why,
        }],
    )


def _completion_returned(
    *,
    model: str,
    analysis_chars: int,
    reported_tokens: Optional[int],
) -> Dict[str, Any]:
    """ACCEPTED: text came back. Text coming back is not evidence about the image.

    `reported_tokens` is None when the response carried no `usage` block. The
    module still puts a 0 in `tokens_used` for compatibility, so the envelope is
    the only place the difference between "the provider billed zero" and "the
    provider said nothing about billing" survives.
    """
    effects: list = [{
        'kind': 'vision_completion_returned',
        'provider': 'openai',
        'model': model,
        'analysis_chars': analysis_chars,
        'measured_by': "len() of the text in the provider's response body",
        'detail': (
            'A completion came back, which is the provider reporting on its own '
            'work. Nothing here evaluates whether the description matches the '
            'image, or whether the model looked at the image at all. A '
            'bug_detection run reporting no bugs is prose, not a passing test.'
        ),
    }]
    if reported_tokens is None:
        effects.append({
            'kind': 'vision_tokens_not_reported',
            'measured_by': None,
            'detail': (
                "The response carried no 'usage' block, so the tokens_used of 0 "
                'in the payload is a literal written in this module and not a '
                'number the provider sent. It reads identically whether nothing '
                'was billed or nothing was said.'
            ),
        })
    else:
        effects.append({
            'kind': 'vision_tokens_billed_by_provider',
            'total_tokens': reported_tokens,
            'measured_by': "usage.total_tokens in the provider's response body",
            'detail': (
                "The provider's own accounting of its own work. Real, and still "
                'the peer describing itself rather than us observing anything.'
            ),
        })
    return envelope(Outcome.ACCEPTED, claim_by=ClaimBy.NONE, effects=effects)


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
            'description': (
                'Total tokens the provider reported for this call, or 0 when the '
                "response carried no 'usage' block -- see outcome.effects for "
                'which of the two a given 0 is'
            )
        ,
                'description_key': 'modules.vision.analyze.output.tokens_used.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this analysis was followed into reality: never higher '
                'than "accepted", because a completion is the provider describing '
                'its own work and nothing here evaluates the image. "failed" when '
                'a guard returned before the request or the provider refused, '
                '"indeterminate" when the call raised after it was on the wire'
            )
        ,
                'description_key': 'modules.vision.analyze.output.outcome.description'}
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
        from ....utils import guarded_httpx_client
    except ImportError:
        try:
            import aiohttp
            use_aiohttp = True
        except ImportError:
            raise ImportError(
                "httpx or aiohttp is required for vision.analyze. "
                "Install with: pip install httpx"
            ) from None
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
            'error_code': 'MISSING_API_KEY',
            'outcome': _never_sent(
                'MISSING_API_KEY',
                'No credential was available, so no request was built.',
            ),
        }

    # Prepare image data
    image_content = await _prepare_image(image_input, detail)
    if image_content.get('error'):
        return {
            'ok': False,
            'error': image_content['error'],
            'error_code': 'IMAGE_ERROR',
            'outcome': _never_sent(
                'IMAGE_ERROR',
                'The image could not be read or encoded, so no request was built.',
            ),
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
            async with aiohttp.ClientSession() as session, session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                result = await response.json()
        else:
            async with guarded_httpx_client(timeout=60) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                result = response.json()

        if 'error' in result:
            provider_message = result['error'].get('message', 'Unknown OpenAI error')
            return {
                'ok': False,
                'error': provider_message,
                'error_code': 'OPENAI_ERROR',
                'outcome': _provider_refused(provider_message),
            }

        analysis_text = result['choices'][0]['message']['content']
        # Read before defaulting, so the envelope can tell "the provider billed
        # zero" from "the provider said nothing about billing". `tokens_used`
        # below keeps the 0 the output schema has always promised.
        reported_tokens = result.get('usage', {}).get('total_tokens')
        tokens_used = reported_tokens if reported_tokens is not None else 0

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
            'tokens_used': tokens_used,
            'outcome': _completion_returned(
                model=model,
                analysis_chars=len(analysis_text or ''),
                reported_tokens=reported_tokens,
            ),
        }

    except Exception as e:
        logger.error(f"Vision analysis failed: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'API_ERROR',
            'outcome': _request_raised(e),
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
    file_path = Path(validate_path_with_env_config(image_input))
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
