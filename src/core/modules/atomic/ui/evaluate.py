# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
UI Evaluate Module
Comprehensive UI quality evaluation with scoring across multiple dimensions

HOW FAR THIS MODULE FOLLOWS REALITY

This module makes no network call of its own. It builds a prompt, hands it to
`vision.analyze`, and parses what comes back. Every rung below is therefore a
statement about a *delegation boundary*, and the ceiling is set by that and not
by the OpenAI API:

  the nested call returned ok=True             ACCEPTED
      The other side acknowledged taking it. That is the definition of the rung
      and it is the exact shape of what happened: `vision.analyze` reported
      success on its own work, and this module read a `tokens_used` count the
      provider put in its reply. Reaching OBSERVED would mean this module
      measured something about the world, and the only thing it measures is
      another module's return dict.

      `overall_score` and `passed` are emphatically NOT evidence and cannot
      raise this. `_parse_evaluation` falls back to `result['overall_score'] = 0`
      when it can find no number in the text, so `passed=False` is produced
      identically by a model that scored the screenshot badly and by a reply
      this module could not parse at all. That is the `file.write`
      `bytes_written` shape -- a value unchanged by whether the effect happened
      -- and it is why the rung rests on the reply having arrived, not on what
      the reply said.

  no API key                                   FAILED, and nothing was sent
      Returned before `vision.analyze` is even imported. Without an envelope
      the engine stamps `dispatched` here, which would claim an instruction
      left this machine when none did.

  the nested call raised                       INDETERMINATE
      `vision_analyze(...)` is called inside a bare `except Exception`. That
      handler spans the HTTP POST as well as everything around it, so a request
      may have been sent, billed and answered before something downstream of it
      raised. "We do not know" is the honest answer and the expensive one to
      get wrong: a retry buys a second completion.

  the nested call returned ok=False            it depends, and it is asked
      This module returns that dict through unchanged, so the rung is derived
      from the `error_code` the nested module set: a missing key or an
      unreadable image means nothing was sent (FAILED); an error named by
      OpenAI in its reply means the provider refused (FAILED); anything else,
      including the nested module's own catch-all, means we cannot say
      (INDETERMINATE). If `vision.analyze` ever grows an envelope of its own,
      that envelope is passed through untouched instead -- it is the module
      that made the call and its answer outranks an inference made out here.

VERIFIED is unreachable and no postcondition is declared. The thing worth
verifying about a UI evaluation is whether the score reflects the screenshot,
and no predicate in this file, or any file it calls, evaluates that.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope, read_envelope
from ...registry import register_module


logger = logging.getLogger(__name__)


#: What `vision.analyze` sets `error_code` to, and how far each one got.
#: Read rather than guessed: `atomic/vision/analyze.py` returns MISSING_API_KEY
#: and IMAGE_ERROR before it builds a request, OPENAI_ERROR after reading an
#: `error` member out of a reply it received, and API_ERROR from a bare
#: `except Exception` wrapped around the POST itself.
_NESTED_ERROR_RUNGS = {
    'MISSING_API_KEY': (Outcome.FAILED, 'no request was built: the nested call had no API key'),
    'IMAGE_ERROR': (Outcome.FAILED, 'no request was built: the screenshot could not be read'),
    'OPENAI_ERROR': (Outcome.FAILED, 'the provider answered and named an error in its reply'),
}


def _evaluation_accepted(*, usage_units: Any, analysis_chars: int) -> Dict[str, Any]:
    """ACCEPTED -- the nested vision call reported success and returned a reply.

    Both numbers here are recorded and neither decides the rung. The usage count
    is the provider's own accounting of work it says it did; `analysis_chars` is
    the length of the text that reached us. A zero in either is a real state of
    this path -- `vision.analyze` returns ok=True with whatever
    `result['choices'][0]['message']['content']` held -- so they are reported as
    facts about the reply, not as evidence of an evaluation.

    The field is `provider_usage_units` and not `tokens_used`, which is what
    `vision.analyze` calls the same number, because
    `_redact_sensitive_output` (`step_executor/executor.py:44`) blanks any key
    containing `token` before results reach a hook. Under the nested module's
    name the evidence for this rung would arrive as '[REDACTED]'.
    """
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'vision_call_acknowledged',
            'provider_usage_units': usage_units,
            'analysis_chars': analysis_chars,
            'measured_by': "vision.analyze returned ok=True; usage count from the provider's usage block",
            'detail': (
                'The nested vision call reported success and handed back text. '
                'This module made no request of its own and read nothing back, '
                'so nothing above accepted is available to it.'
            ),
        }],
    )


def _evaluation_not_sent(reason: str) -> Dict[str, Any]:
    """FAILED -- returned before anything was called, let alone sent."""
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'request_not_sent',
            'reason': reason,
            'measured_by': 'returned before vision.analyze was invoked',
            'detail': 'No vision call was made. No provider was contacted.',
        }],
    )


def _evaluation_uncertain(*, reason: str, detail: str) -> Dict[str, Any]:
    """INDETERMINATE -- the call may have been made, billed and answered."""
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'vision_call_unconfirmed',
            'reason': reason,
            'measured_by': None,
            'detail': detail,
        }],
    )


def _nested_failure_outcome(result: Dict[str, Any]) -> Dict[str, Any]:
    """The rung for a failure this module did not produce and cannot see into.

    Preference order, and the order is the point: the envelope the nested
    module built beats anything inferred out here, because it was the code that
    made the call. Only when there is none does the documented `error_code`
    decide, and only when that is unrecognised does this fall to
    INDETERMINATE -- which is what an unknown failure of a paid API call is.
    """
    existing = read_envelope(result)
    if existing is not None:
        return existing

    code = result.get('error_code')
    known = _NESTED_ERROR_RUNGS.get(code)
    if known is not None:
        rung, detail = known
        return envelope(
            rung,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'vision_call_failed',
                'error_code': code,
                'measured_by': "error_code returned by vision.analyze",
                'detail': detail,
            }],
        )

    return _evaluation_uncertain(
        reason=f'vision.analyze failed with error_code={code!r}',
        detail=(
            'The nested call reported a failure this module cannot place. Its '
            'catch-all handler wraps the POST itself, so the request may have '
            'been sent, billed and answered before something raised.'
        ),
    )


@register_module(
    module_id='ui.evaluate',
    stability="beta",
    version='1.0.0',
    category='atomic',
    subcategory='ui',
    tags=['ui', 'ux', 'evaluate', 'score', 'quality', 'design', 'atomic'],
    label='Evaluate UI Quality',
    label_key='modules.ui.evaluate.label',
    description='Comprehensive UI quality evaluation with multi-dimensional scoring',
    description_key='modules.ui.evaluate.description',
    icon='Award',
    color='#8B5CF6',

    # Connection types
    input_types=['string', 'image'],
    output_types=['object'],
    can_connect_to=['test.*', 'file.*', 'webhook.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=90000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'screenshot': {
            'type': 'string',
            'label': 'Screenshot',
            'label_key': 'modules.ui.evaluate.params.screenshot.label',
            'description': 'Screenshot path or URL to evaluate',
            'description_key': 'modules.ui.evaluate.params.screenshot.description',
            'required': True,
            'placeholder': './screenshots/page.png'
        },
        'app_type': {
            'type': 'string',
            'label': 'Application Type',
            'label_key': 'modules.ui.evaluate.params.app_type.label',
            'description': 'Type of application for context-aware evaluation',
            'description_key': 'modules.ui.evaluate.params.app_type.description',
            'required': False,
            'default': 'web_app',
            'enum': [
                'web_app', 'mobile_app', 'dashboard', 'e_commerce',
                'landing_page', 'form', 'admin_panel', 'documentation'
            ]
        },
        'page_type': {
            'type': 'string',
            'label': 'Page Type',
            'label_key': 'modules.ui.evaluate.params.page_type.label',
            'description': 'Type of page being evaluated',
            'description_key': 'modules.ui.evaluate.params.page_type.description',
            'required': False,
            'placeholder': 'login, dashboard, settings, etc.'
        },
        'evaluation_criteria': {
            'type': 'array',
            'label': 'Evaluation Criteria',
            'label_key': 'modules.ui.evaluate.params.evaluation_criteria.label',
            'description': 'Specific criteria to evaluate (defaults to all)',
            'description_key': 'modules.ui.evaluate.params.evaluation_criteria.description',
            'required': False,
            'default': ['visual_design', 'usability', 'accessibility', 'consistency', 'responsiveness'],
            'options': [
                {'value': 'visual_design', 'label': 'Visual Design'},
                {'value': 'usability', 'label': 'Usability'},
                {'value': 'accessibility', 'label': 'Accessibility'},
                {'value': 'consistency', 'label': 'Consistency'},
                {'value': 'responsiveness', 'label': 'Responsiveness'},
                {'value': 'typography', 'label': 'Typography'},
                {'value': 'color_scheme', 'label': 'Color Scheme'},
                {'value': 'navigation', 'label': 'Navigation'},
                {'value': 'cta_effectiveness', 'label': 'CTA Effectiveness'},
                {'value': 'information_hierarchy', 'label': 'Information Hierarchy'}
            ]
        },
        'target_audience': {
            'type': 'string',
            'label': 'Target Audience',
            'label_key': 'modules.ui.evaluate.params.target_audience.label',
            'description': 'Description of target users',
            'description_key': 'modules.ui.evaluate.params.target_audience.description',
            'required': False,
            'placeholder': 'developers, enterprise users, general consumers, etc.'
        },
        'brand_guidelines': {
            'type': 'string',
            'label': 'Brand Guidelines',
            'label_key': 'modules.ui.evaluate.params.brand_guidelines.label',
            'description': 'Brief brand guidelines to check against',
            'description_key': 'modules.ui.evaluate.params.brand_guidelines.description',
            'required': False,
            'multiline': True,
            'placeholder': 'Primary color: #3B82F6, Font: Inter, Style: Modern minimalist'
        },
        'min_score': {
            'type': 'number',
            'label': 'Minimum Pass Score',
            'label_key': 'modules.ui.evaluate.params.min_score.label',
            'description': 'Minimum overall score to pass (0-100)',
            'description_key': 'modules.ui.evaluate.params.min_score.description',
            'required': False,
            'default': 70,
            'validation': {
                'min': 0,
                'max': 100
            }
        },
        'api_key': {
            'type': 'string',
            'label': 'OpenAI API Key',
            'label_key': 'modules.ui.evaluate.params.api_key.label',
            'description': 'OpenAI API key (defaults to OPENAI_API_KEY env var)',
            'description_key': 'modules.ui.evaluate.params.api_key.description',
            'required': False,
            'sensitive': True,
            'placeholder': 'sk-...',
}
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether evaluation succeeded'
        ,
                'description_key': 'modules.ui.evaluate.output.ok.description'},
        'passed': {
            'type': 'boolean',
            'description': 'Whether UI meets minimum score threshold'
        ,
                'description_key': 'modules.ui.evaluate.output.passed.description'},
        'overall_score': {
            'type': 'number',
            'description': 'Overall UI quality score (0-100)'
        ,
                'description_key': 'modules.ui.evaluate.output.overall_score.description'},
        'scores': {
            'type': 'object',
            'description': 'Scores by evaluation criteria'
        ,
                'description_key': 'modules.ui.evaluate.output.scores.description'},
        'strengths': {
            'type': 'array',
            'description': 'List of UI strengths'
        ,
                'description_key': 'modules.ui.evaluate.output.strengths.description'},
        'issues': {
            'type': 'array',
            'description': 'List of issues found with severity'
        ,
                'description_key': 'modules.ui.evaluate.output.issues.description'},
        'recommendations': {
            'type': 'array',
            'description': 'Specific improvement recommendations'
        ,
                'description_key': 'modules.ui.evaluate.output.recommendations.description'},
        'summary': {
            'type': 'string',
            'description': 'Executive summary of evaluation'
        ,
                'description_key': 'modules.ui.evaluate.output.summary.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the evaluation was followed: "accepted" when the nested '
                'vision call reported success, "failed" when nothing was sent or '
                'the provider named a refusal, "indeterminate" when the call may '
                'have been made and billed without an answer reaching us. Never '
                'higher: passed and overall_score are this module output, not '
                'evidence about it'
            )
        ,
                'description_key': 'modules.ui.evaluate.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Evaluate Dashboard',
            'title_key': 'modules.ui.evaluate.examples.dashboard.title',
            'params': {
                'screenshot': './screenshots/dashboard.png',
                'app_type': 'dashboard',
                'page_type': 'analytics dashboard',
                'target_audience': 'business analysts',
                'min_score': 75
            }
        },
        {
            'title': 'E-commerce Page Review',
            'title_key': 'modules.ui.evaluate.examples.ecommerce.title',
            'params': {
                'screenshot': './screenshots/product.png',
                'app_type': 'e_commerce',
                'page_type': 'product detail',
                'evaluation_criteria': ['usability', 'cta_effectiveness', 'visual_design']
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def ui_evaluate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Comprehensive UI quality evaluation"""
    # REMOVED: `from .._import_helper import get_vision_analyze`.
    #
    # `core.modules.atomic._import_helper` does not exist -- not in this
    # package, not anywhere in src/ -- so this line raised ModuleNotFoundError
    # on the first statement of the function body, on every call, and this
    # module could never run at all. The symbol was never used either: the real
    # import is `from ..vision.analyze import vision_analyze` further down,
    # inside the try. Deleting a dead import that made the module unreachable
    # is the whole fix.
    #
    # Found by writing the outcome tests below: every path this file can take
    # was unreachable, so no rung it claimed could ever have been observed.
    params = context['params']
    screenshot = params['screenshot']
    app_type = params.get('app_type', 'web_app')
    page_type = params.get('page_type', '')
    criteria = params.get('evaluation_criteria', [
        'visual_design', 'usability', 'accessibility', 'consistency', 'responsiveness'
    ])
    target_audience = params.get('target_audience', '')
    brand_guidelines = params.get('brand_guidelines', '')
    min_score = params.get('min_score', 70)
    api_key = params.get('api_key') or os.getenv('OPENAI_API_KEY')

    if not api_key:
        return {
            'ok': False,
            'error': 'OpenAI API key not provided',
            'error_code': 'MISSING_API_KEY',
            'outcome': _evaluation_not_sent('no OpenAI API key was configured'),
        }

    # Build comprehensive evaluation prompt
    prompt = _build_evaluation_prompt(
        app_type, page_type, criteria, target_audience, brand_guidelines
    )

    # Use vision.analyze internally
    vision_context = {
        'params': {
            'image': screenshot,
            'prompt': prompt,
            'analysis_type': 'ui_review',
            'output_format': 'json',
            'api_key': api_key,
            'max_tokens': 2000
        }
    }

    # Import and call vision_analyze
    try:
        from ..vision.analyze import vision_analyze
        result = await vision_analyze(vision_context)
    except Exception as e:
        return {
            'ok': False,
            'error': f'Failed to run vision analysis: {e}',
            'error_code': 'ANALYSIS_ERROR',
            # This handler covers the import AND the call. An ImportError never
            # sent anything; anything raised out of vision_analyze may have been
            # raised after the POST completed. One rung has to cover both, and
            # the honest one is the weaker.
            'outcome': _evaluation_uncertain(
                reason=f'{type(e).__name__} raised around the vision call',
                detail=(
                    'The nested call raised. This handler spans importing the module '
                    'and running it, so whether a request was sent, billed and '
                    'answered before the raise is not knowable from here.'
                ),
            ),
        }

    if not result.get('ok'):
        # Returned through unchanged apart from the rung -- this module is the
        # only place the failure is visible to a consumer, and a failure that
        # says nothing about how far it got is the gap this contract exists to
        # close. Mutating the nested dict is safe: it is this call's own return
        # value and nothing else holds a reference to it.
        # Assigned rather than setdefault-ed: `_nested_failure_outcome` returns
        # the nested envelope untouched when there is a well-formed one, so the
        # only thing this overwrites is a key that is not an envelope -- which
        # `read_envelope` would refuse to read anyway.
        result['outcome'] = _nested_failure_outcome(result)
        return result

    # Parse the analysis into structured evaluation
    analysis = result.get('analysis', '')
    structured = result.get('structured', {})

    # Try to extract scores and issues
    evaluation = _parse_evaluation(analysis, structured, criteria)

    overall_score = evaluation.get('overall_score', 0)
    passed = overall_score >= min_score

    logger.info("UI evaluation completed: passed=%s", passed)

    return {
        'ok': True,
        'passed': passed,
        'overall_score': overall_score,
        'scores': evaluation.get('scores', {}),
        'strengths': evaluation.get('strengths', []),
        'issues': evaluation.get('issues', []),
        'recommendations': evaluation.get('recommendations', []),
        'summary': evaluation.get('summary', analysis[:500]),
        'raw_analysis': analysis,
        'outcome': _evaluation_accepted(
            usage_units=result.get('tokens_used'),
            analysis_chars=len(analysis),
        ),
    }


def _build_evaluation_prompt(
    app_type: str,
    page_type: str,
    criteria: List[str],
    target_audience: str,
    brand_guidelines: str
) -> str:
    """Build comprehensive evaluation prompt"""

    criteria_descriptions = {
        'visual_design': "Visual Design: Layout balance, whitespace, visual appeal, modern aesthetics",
        'usability': "Usability: Ease of use, intuitive navigation, clear affordances, learnability",
        'accessibility': "Accessibility: Color contrast, text readability, touch targets, WCAG compliance indicators",
        'consistency': "Consistency: Visual consistency, pattern reuse, element alignment, spacing uniformity",
        'responsiveness': "Responsiveness: Adaptation to viewport, flexible layouts, no horizontal scroll",
        'typography': "Typography: Font choices, hierarchy, readability, line height, letter spacing",
        'color_scheme': "Color Scheme: Palette harmony, contrast, brand alignment, emotional impact",
        'navigation': "Navigation: Clear structure, findability, breadcrumbs, menu organization",
        'cta_effectiveness': "CTA Effectiveness: Button visibility, action clarity, conversion optimization",
        'information_hierarchy': "Information Hierarchy: Content prioritization, visual flow, F-pattern compliance"
    }

    prompt = f"""Perform a comprehensive UI quality evaluation of this {app_type} screenshot.

"""

    if page_type:
        prompt += f"Page type: {page_type}\n"

    if target_audience:
        prompt += f"Target audience: {target_audience}\n"

    if brand_guidelines:
        prompt += f"Brand guidelines: {brand_guidelines}\n"

    prompt += "\n## Evaluation Criteria\n"
    for criterion in criteria:
        if criterion in criteria_descriptions:
            prompt += f"- {criteria_descriptions[criterion]}\n"

    prompt += """
## Required Output Format (JSON)
Return your evaluation as valid JSON:
{
  "overall_score": 75,
  "scores": {
    "visual_design": 80,
    "usability": 70,
    "accessibility": 65,
    ...
  },
  "strengths": [
    "Clean, modern visual design",
    "Clear call-to-action buttons",
    ...
  ],
  "issues": [
    {"area": "accessibility", "severity": "Major", "description": "Low contrast text in footer", "location": "footer"},
    {"area": "usability", "severity": "Minor", "description": "Small click targets on mobile", "location": "navigation"},
    ...
  ],
  "recommendations": [
    {"priority": "High", "action": "Increase footer text contrast to meet WCAG AA"},
    {"priority": "Medium", "action": "Enlarge navigation touch targets to 44x44px minimum"},
    ...
  ],
  "summary": "Brief executive summary of the UI quality..."
}

Score each criterion from 0-100. The overall_score should be a weighted average.
Be specific and actionable in your feedback."""

    return prompt


def _parse_evaluation(analysis: str, structured: Optional[Dict], criteria: List[str]) -> Dict[str, Any]:
    """Parse evaluation results"""
    import json
    import re

    result = {
        'overall_score': 0,
        'scores': {},
        'strengths': [],
        'issues': [],
        'recommendations': [],
        'summary': ''
    }

    # Try structured data first
    if structured and isinstance(structured, dict):
        if 'overall_score' in structured:
            return structured

    # Try to find JSON in analysis
    json_match = re.search(r'\{[\s\S]*\}', analysis)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if 'overall_score' in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    # Fallback: extract what we can
    # Look for score patterns like "Score: 75" or "75/100"
    score_match = re.search(r'(?:overall|total|score)[:\s]*(\d+)', analysis, re.IGNORECASE)
    if score_match:
        result['overall_score'] = int(score_match.group(1))

    # Extract individual criterion scores
    for criterion in criteria:
        pattern = rf'{criterion}[:\s]*(\d+)'
        match = re.search(pattern, analysis, re.IGNORECASE)
        if match:
            result['scores'][criterion] = int(match.group(1))

    # Calculate overall if we have individual scores
    if result['scores'] and not result['overall_score']:
        result['overall_score'] = sum(result['scores'].values()) // len(result['scores'])

    result['summary'] = analysis[:500] if len(analysis) > 500 else analysis

    return result
