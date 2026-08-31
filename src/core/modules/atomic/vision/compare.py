# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Vision Compare Module
Compare two images/screenshots for visual differences

HOW FAR THIS MODULE FOLLOWS REALITY

The ceiling is ACCEPTED, and this is the module in the group where that matters
most, because of one field: `recommendation`. It reads `PASS` or `FAIL`, the
label says "Pass/Fail recommendation based on threshold", and the documented use
is a visual regression gate. Nothing in this file compares two images.

What actually produces that verdict:

    similarity = analysis.get('similarity_score', 0)          # the model's guess
    recommendation = 'PASS' if similarity >= (100 - threshold) else 'FAIL'

`similarity_score` is a number a language model wrote into a JSON block after
being asked to estimate one. No pixels are diffed, no perceptual hash is
computed, no bounding box is measured. The arithmetic on the second line is
exact and the input to it is an opinion, which is precisely how a guess acquires
the appearance of a measurement. Apply the test this contract is built on --
would this value be the same if the effect had not happened? A model asked to
compare two images it did not really look at returns a plausible 97 just as
readily as a model that did. It is not evidence, so no rung rests on it, and the
`regression_verdict_is_model_opinion` effect says so inside every success
envelope rather than leaving a dashboard to infer otherwise.

The four answers:

  the provider returned a parseable verdict     ACCEPTED
      A completion came back. The verdict inside it is the model's opinion.

  the provider returned unparseable text        ACCEPTED
      `recommendation` becomes 'REVIEW_NEEDED' and `similarity_score` becomes
      None. Same rung: the peer answered either way, and a shape we could not
      read is not a lower claim about the call, only a worse payload.

  a guard returned, or the provider refused     FAILED
      No key, either image unreadable, or an `error` object in the response.
      Nothing was produced, and it is known rather than inferred.

  the request raised                            FAILED or INDETERMINATE
      Split by `_outcomes.classify_request_failure`; INDETERMINATE unless the
      connection is known never to have come up.

VERIFIED is unreachable and is not merely undeclared. A postcondition on this
module would have to be a predicate about the two images, and there is no line
here that could evaluate one -- adding the declaration without a real diff would
move the same guess one rung higher and call it proof.
"""

import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import validate_path_with_env_config
from ...registry import register_module
from ...schema import compose, presets
from ._outcomes import classify_request_failure

logger = logging.getLogger(__name__)


# ── Outcome ────────────────────────────────────────────────────────────────
#
# As in `analyze.py`, the `ok: False` envelopes are attached knowing that
# `wrap_legacy_result` discards `data` for an ERROR result today. The fact is
# true before a consumer exists to read it.


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
    """FAILED: the provider answered, and the answer was an error object."""
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'vision_provider_error',
            'provider': 'openai',
            'provider_message': message,
            'measured_by': "the 'error' object in the provider's own response body",
            'detail': (
                'The provider answered and declined. No comparison was produced.'
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


#: Carried on every success. The single most important sentence this module can
#: hand a consumer, because the payload beside it looks like a test result.
_VERDICT_IS_OPINION = {
    'kind': 'regression_verdict_is_model_opinion',
    'measured_by': (
        "similarity_score as written by the language model, then compared "
        "against the caller's threshold"
    ),
    'detail': (
        'No pixels were compared. similarity_score is a number the model '
        'estimated in prose and recommendation is exact arithmetic over that '
        'estimate, which is how a guess comes to look like a measurement. A '
        "PASS here is a model's opinion that two screenshots look alike; it is "
        'not a visual regression check having run.'
    ),
}


def _comparison_returned(
    *,
    model: str,
    similarity_score: Any,
    recommendation: str,
    differences: int,
    score_reported: bool,
) -> Dict[str, Any]:
    """ACCEPTED: the provider answered with a verdict it invented.

    `score_reported` is False when the model's JSON carried no
    `similarity_score`. The module then defaults it to 0, which drives
    `recommendation` to FAIL for every threshold below 100 -- a verdict produced
    by a missing field rather than by a comparison, and worth naming.
    """
    effects: list = [
        {
            'kind': 'vision_comparison_returned',
            'provider': 'openai',
            'model': model,
            'similarity_score': similarity_score,
            'recommendation': recommendation,
            'differences_listed': differences,
            'measured_by': "the JSON block in the provider's response body",
            'detail': (
                'A completion came back and parsed. That the provider answered '
                'is the whole of what this rung claims.'
            ),
        },
        _VERDICT_IS_OPINION,
    ]
    if not score_reported:
        effects.append({
            'kind': 'similarity_score_defaulted',
            'measured_by': None,
            'detail': (
                'The model returned JSON with no similarity_score, so the 0 the '
                'verdict was computed from is a literal written in this module. '
                'The resulting FAIL was produced by a missing field, not by a '
                'difference anyone found.'
            ),
        })
    return envelope(Outcome.ACCEPTED, claim_by=ClaimBy.NONE, effects=effects)


def _comparison_unparseable(*, model: str, analysis_chars: int) -> Dict[str, Any]:
    """ACCEPTED: the provider answered, in a shape this module could not read."""
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            {
                'kind': 'vision_comparison_unparseable',
                'provider': 'openai',
                'model': model,
                'analysis_chars': analysis_chars,
                'measured_by': "len() of the text in the provider's response body",
                'detail': (
                    'No JSON object could be read out of the response, so '
                    'similarity_score is null and recommendation is '
                    'REVIEW_NEEDED. The call still happened and was still '
                    'billed, which is what accepted says and all it says.'
                ),
            },
            _VERDICT_IS_OPINION,
        ],
    )


@register_module(
    module_id='vision.compare',
    stability="beta",
    version='1.0.0',
    category='atomic',
    subcategory='vision',
    tags=[
        'vision', 'compare', 'diff', 'screenshot', 'regression', 'atomic',
        'path_restricted',
    ],
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
    timeout_ms=60000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=False,
    required_permissions=[],

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
            'description': (
                "PASS/FAIL computed from the model's estimated similarity_score "
                'against the threshold, or REVIEW_NEEDED when the response could '
                'not be parsed. An opinion put through arithmetic, not a pixel '
                'comparison -- see outcome.effects'
            )
        ,
                'description_key': 'modules.vision.compare.output.recommendation.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this comparison was followed into reality: never higher '
                'than "accepted", because no pixels are compared anywhere in this '
                "module and the verdict is the model's own estimate. \"failed\" "
                'when a guard returned before the request or the provider '
                'refused, "indeterminate" when the call raised on the wire'
            )
        ,
                'description_key': 'modules.vision.compare.output.outcome.description'}
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
        from ....utils import guarded_httpx_client
        use_httpx = True
    except ImportError:
        try:
            import aiohttp
            use_httpx = False
        except ImportError:
            raise ImportError(
                "httpx or aiohttp required. Install with: pip install httpx"
            ) from None

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
            'error_code': 'MISSING_API_KEY',
            'outcome': _never_sent(
                'MISSING_API_KEY',
                'No credential was available, so no request was built.',
            ),
        }

    # Load images
    before_content = await _load_image(image_before)
    if before_content.get('error'):
        return {
            'ok': False,
            'error': f"Before image: {before_content['error']}",
            'error_code': 'IMAGE_ERROR',
            'outcome': _never_sent(
                'IMAGE_ERROR',
                'The baseline image could not be read, so no request was built.',
            ),
        }

    after_content = await _load_image(image_after)
    if after_content.get('error'):
        return {
            'ok': False,
            'error': f"After image: {after_content['error']}",
            'error_code': 'IMAGE_ERROR',
            'outcome': _never_sent(
                'IMAGE_ERROR',
                'The current image could not be read, so no request was built.',
            ),
        }

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
            async with guarded_httpx_client(timeout=60) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                result = response.json()
        else:
            async with aiohttp.ClientSession() as session, session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                result = await response.json()

        if 'error' in result:
            provider_message = result['error'].get('message', 'Unknown error')
            return {
                'ok': False,
                'error': provider_message,
                'error_code': 'OPENAI_ERROR',
                'outcome': _provider_refused(provider_message),
            }

        analysis_text = result['choices'][0]['message']['content']

        # Parse JSON response
        import json
        import re

        json_match = re.search(r'\{[\s\S]*\}', analysis_text)
        if json_match:
            try:
                analysis = json.loads(json_match.group())
                # A model that returned "95" instead of 95 used to take the
                # whole call down: the comparison below raised TypeError, the
                # bare `except Exception` caught it and the step reported
                # API_ERROR -- an unreachable-provider code for a provider that
                # answered perfectly well. Anything that is not a real number is
                # now treated as the absent field it effectively is, which is
                # also the distinction the envelope needs.
                raw_similarity = analysis.get('similarity_score')
                score_reported = isinstance(raw_similarity, (int, float)) and not isinstance(
                    raw_similarity, bool
                )
                similarity = raw_similarity if score_reported else 0
                has_diff = analysis.get('has_differences', True)
                recommendation = 'PASS' if similarity >= (100 - threshold) else 'FAIL'
                differences = analysis.get('differences', [])

                return {
                    'ok': True,
                    'has_differences': has_diff,
                    'similarity_score': similarity,
                    'differences': differences,
                    'summary': analysis.get('summary', ''),
                    'recommendation': recommendation,
                    'raw_analysis': analysis_text,
                    'outcome': _comparison_returned(
                        model=model,
                        similarity_score=similarity,
                        recommendation=recommendation,
                        differences=len(differences) if isinstance(differences, list) else 0,
                        score_reported=score_reported,
                    ),
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
            'recommendation': 'REVIEW_NEEDED',
            'outcome': _comparison_unparseable(
                model=model,
                analysis_chars=len(analysis_text or ''),
            ),
        }

    except Exception as e:
        logger.error(f"Vision compare failed: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'API_ERROR',
            'outcome': _request_raised(e),
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

    path = Path(validate_path_with_env_config(image_path))
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
