"""
UI Evaluate Module
Comprehensive UI quality evaluation with scoring across multiple dimensions
"""

import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module


logger = logging.getLogger(__name__)


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
    timeout=90,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    handles_sensitive_data=False,
    required_permissions=['ai.vision'],

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
            'sensitive': True
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
                'description_key': 'modules.ui.evaluate.output.summary.description'}
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
    # Import vision.analyze to reuse the image handling
    from .._import_helper import get_vision_analyze

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
            'error_code': 'MISSING_API_KEY'
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
            'error_code': 'ANALYSIS_ERROR'
        }

    if not result.get('ok'):
        return result

    # Parse the analysis into structured evaluation
    analysis = result.get('analysis', '')
    structured = result.get('structured', {})

    # Try to extract scores and issues
    evaluation = _parse_evaluation(analysis, structured, criteria)

    overall_score = evaluation.get('overall_score', 0)
    passed = overall_score >= min_score

    logger.info(f"UI evaluation: score={overall_score}, passed={passed}")

    return {
        'ok': True,
        'passed': passed,
        'overall_score': overall_score,
        'scores': evaluation.get('scores', {}),
        'strengths': evaluation.get('strengths', []),
        'issues': evaluation.get('issues', []),
        'recommendations': evaluation.get('recommendations', []),
        'summary': evaluation.get('summary', analysis[:500]),
        'raw_analysis': analysis
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
