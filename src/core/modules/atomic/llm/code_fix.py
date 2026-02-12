"""
LLM Code Fix Module
AI-powered automatic code fixes based on issues and feedback
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='llm.code_fix',
    stability="beta",
    version='1.0.0',
    category='atomic',
    subcategory='llm',
    tags=['llm', 'ai', 'code', 'fix', 'auto', 'repair', 'atomic'],
    label='AI Code Fix',
    label_key='modules.llm.code_fix.label',
    description='Automatically generate code fixes based on issues',
    description_key='modules.llm.code_fix.description',
    icon='Wrench',
    color='#EF4444',

    # Connection types
    input_types=['object', 'array'],
    output_types=['object', 'array'],
    can_connect_to=['*'],  # Can connect to any module (file, shell, llm, etc.)
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=180000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    # Schema-driven params
    params_schema=compose(
        presets.CODE_ISSUES(required=True),
        presets.SOURCE_FILES(required=True),
        presets.FIX_MODE(default='suggest'),
        presets.CREATE_BACKUP(default=True),
        presets.TEXT(key='context', label='Additional Context', multiline=True, placeholder='This is a React project using Tailwind CSS...'),
        presets.LLM_MODEL(default='gpt-4o'),
        presets.LLM_API_KEY(),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether operation succeeded'
        ,
                'description_key': 'modules.llm.code_fix.output.ok.description'},
        'fixes': {
            'type': 'array',
            'description': 'List of generated fixes'
        ,
                'description_key': 'modules.llm.code_fix.output.fixes.description'},
        'applied': {
            'type': 'array',
            'description': 'List of applied fixes (if fix_mode is apply)'
        ,
                'description_key': 'modules.llm.code_fix.output.applied.description'},
        'failed': {
            'type': 'array',
            'description': 'Fixes that could not be applied'
        ,
                'description_key': 'modules.llm.code_fix.output.failed.description'},
        'summary': {
            'type': 'string',
            'description': 'Summary of fixes'
        ,
                'description_key': 'modules.llm.code_fix.output.summary.description'}
    },
    examples=[
        {
            'title': 'Fix UI Issues',
            'title_key': 'modules.llm.code_fix.examples.ui.title',
            'params': {
                'issues': '${ui_evaluation.issues}',
                'source_files': ['./src/components/Footer.tsx', './src/styles/footer.css'],
                'fix_mode': 'suggest',
                'context': 'React + Tailwind CSS project'
            }
        },
        {
            'title': 'Auto-fix and Apply',
            'title_key': 'modules.llm.code_fix.examples.apply.title',
            'params': {
                'issues': '${test_results.failures}',
                'source_files': ['./src/App.tsx'],
                'fix_mode': 'apply',
                'backup': True
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def llm_code_fix(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate and optionally apply code fixes using AI"""
    params = context['params']
    issues = params['issues']
    source_files = params['source_files']
    fix_mode = params.get('fix_mode', 'suggest')
    backup = params.get('backup', True)
    additional_context = params.get('context', '')
    model = params.get('model', 'gpt-4o')
    api_key = params.get('api_key') or os.getenv('OPENAI_API_KEY')

    if not api_key:
        return {
            'ok': False,
            'error': 'OpenAI API key not provided',
            'error_code': 'MISSING_API_KEY'
        }

    if not issues:
        return {
            'ok': True,
            'fixes': [],
            'applied': [],
            'failed': [],
            'summary': 'No issues to fix'
        }

    # Read source files
    file_contents = {}
    for file_path in source_files:
        path = Path(file_path).expanduser()
        if path.exists():
            try:
                file_contents[file_path] = path.read_text(encoding='utf-8')
            except Exception as e:
                logger.warning(f"Could not read {file_path}: {e}")

    if not file_contents:
        return {
            'ok': False,
            'error': 'No source files could be read',
            'error_code': 'NO_FILES'
        }

    # Build prompt for LLM
    prompt = _build_fix_prompt(issues, file_contents, additional_context)

    # Call LLM
    try:
        from .chat import llm_chat
        llm_result = await llm_chat({
            'params': {
                'prompt': prompt,
                'system_prompt': _get_system_prompt(),
                'model': model,
                'api_key': api_key,
                'max_tokens': 4000,
                'response_format': 'json',
                'temperature': 0.3  # Lower for more consistent code
            }
        })
    except Exception as e:
        return {
            'ok': False,
            'error': f'LLM call failed: {e}',
            'error_code': 'LLM_ERROR'
        }

    if not llm_result.get('ok'):
        return llm_result

    # Parse fixes
    fixes = _parse_fixes(llm_result.get('response', ''), llm_result.get('parsed'))

    if not fixes:
        return {
            'ok': True,
            'fixes': [],
            'applied': [],
            'failed': [],
            'summary': 'No fixes could be generated'
        }

    applied = []
    failed = []

    # Apply fixes if requested
    if fix_mode in ['apply', 'dry_run']:
        for fix in fixes:
            file_path = fix.get('file')
            if not file_path or file_path not in file_contents:
                failed.append({**fix, 'error': 'File not found'})
                continue

            original_content = file_contents[file_path]
            new_content = _apply_fix(original_content, fix)

            if new_content == original_content:
                failed.append({**fix, 'error': 'Fix could not be applied'})
                continue

            fix['diff'] = _generate_diff(original_content, new_content)

            if fix_mode == 'apply':
                path = Path(file_path).expanduser()

                # Create backup
                if backup:
                    backup_path = path.with_suffix(path.suffix + '.bak')
                    backup_path.write_text(original_content, encoding='utf-8')

                # Write fix
                try:
                    path.write_text(new_content, encoding='utf-8')
                    applied.append(fix)
                    logger.info(f"Applied fix to {file_path}")
                except Exception as e:
                    failed.append({**fix, 'error': str(e)})
            else:
                # dry_run
                applied.append(fix)

    summary = f"Generated {len(fixes)} fixes. "
    if fix_mode == 'apply':
        summary += f"Applied {len(applied)}, failed {len(failed)}."
    elif fix_mode == 'dry_run':
        summary += f"Would apply {len(applied)} fixes."
    else:
        summary += "Review and apply manually."

    logger.info(summary)

    return {
        'ok': True,
        'fixes': fixes,
        'applied': applied,
        'failed': failed,
        'summary': summary
    }


def _get_system_prompt() -> str:
    """Get system prompt for code fixing"""
    return """You are an expert software engineer fixing code issues.

For each issue, generate a precise fix. Return JSON:
{
  "fixes": [
    {
      "file": "path/to/file.tsx",
      "issue": "Description of issue being fixed",
      "fix_type": "replace|insert|delete",
      "search": "exact code to find (for replace)",
      "replace": "new code to use",
      "line_number": 42,
      "explanation": "Why this fix works"
    }
  ],
  "summary": "Brief summary of all fixes"
}

Rules:
1. Use EXACT code matches for "search" field
2. Preserve indentation and style
3. Make minimal changes needed
4. Don't break existing functionality
5. Consider accessibility and best practices"""


def _build_fix_prompt(issues: List[Dict], files: Dict[str, str], context: str) -> str:
    """Build the fix generation prompt"""
    prompt = "Generate fixes for these issues:\n\n"

    prompt += "## Issues\n"
    for i, issue in enumerate(issues, 1):
        if isinstance(issue, dict):
            prompt += f"{i}. [{issue.get('severity', 'Unknown')}] {issue.get('description', issue)}\n"
            if issue.get('location'):
                prompt += f"   Location: {issue['location']}\n"
        else:
            prompt += f"{i}. {issue}\n"

    prompt += "\n## Source Files\n"
    for file_path, content in files.items():
        prompt += f"\n### {file_path}\n```\n{content}\n```\n"

    if context:
        prompt += f"\n## Additional Context\n{context}\n"

    return prompt


def _parse_fixes(response: str, parsed: Optional[Dict]) -> List[Dict]:
    """Parse fixes from LLM response"""
    import json

    # Try parsed first
    if parsed and isinstance(parsed, dict) and 'fixes' in parsed:
        return parsed['fixes']

    # Try to find JSON
    json_match = re.search(r'\{[\s\S]*"fixes"[\s\S]*\}', response)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if 'fixes' in data:
                return data['fixes']
        except json.JSONDecodeError:
            pass

    return []


def _apply_fix(content: str, fix: Dict) -> str:
    """Apply a single fix to content"""
    fix_type = fix.get('fix_type', 'replace')
    search = fix.get('search', '')
    replace = fix.get('replace', '')
    line_number = fix.get('line_number')

    if fix_type == 'replace' and search:
        if search in content:
            return content.replace(search, replace, 1)

    if fix_type == 'insert' and line_number:
        lines = content.split('\n')
        if 0 < line_number <= len(lines) + 1:
            lines.insert(line_number - 1, replace)
            return '\n'.join(lines)

    if fix_type == 'delete' and search:
        return content.replace(search, '', 1)

    return content


def _generate_diff(original: str, new: str) -> str:
    """Generate a simple diff"""
    import difflib

    original_lines = original.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines, new_lines,
        fromfile='original', tofile='fixed',
        lineterm=''
    )

    return ''.join(diff)
