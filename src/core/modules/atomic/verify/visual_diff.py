"""
Verify Visual Diff Module - End-to-end visual comparison pipeline

Pipeline:
1. Screenshot reference_url and dev_url via Playwright
2. AI vision comparison via vision.compare (GPT-4o)
3. Annotate dev screenshot with labeled difference regions
4. Generate HTML report with side-by-side comparison

Returns annotated image, annotations list, similarity score, and report path.
"""
import base64
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field as schema_field

logger = logging.getLogger(__name__)


async def _screenshot_url(url: str, output_path: str, viewport_width: int = 1280, viewport_height: int = 800) -> str:
    """Take a full-page screenshot of a URL using Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ImportError("playwright is required. Install with: pip install playwright && playwright install chromium")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': viewport_width, 'height': viewport_height})
        await page.goto(url, wait_until='networkidle', timeout=30000)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=output_path, full_page=False)
        await browser.close()

    return output_path


async def _vision_compare_images(
    reference_path: str,
    dev_path: str,
    focus_areas: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    model: str = 'gpt-4o',
) -> Dict[str, Any]:
    """
    Use OpenAI Vision API to compare two screenshots and identify differences.
    Returns structured difference data with bounding box estimates.
    """
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx is required. Install with: pip install httpx")

    api_key = api_key or os.getenv('OPENAI_API_KEY')
    if not api_key:
        return {'ok': False, 'error': 'OpenAI API key not configured (OPENAI_API_KEY)'}

    def load_image_b64(img_path: str) -> Dict:
        if img_path.startswith(('http://', 'https://')):
            return {"type": "image_url", "image_url": {"url": img_path, "detail": "high"}}
        data = base64.b64encode(Path(img_path).read_bytes()).decode('utf-8')
        suffix = Path(img_path).suffix.lower()
        mime = {'png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}.get(suffix, 'image/png')
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}", "detail": "high"}}

    ref_content = load_image_b64(reference_path)
    dev_content = load_image_b64(dev_path)

    focus_hint = ""
    if focus_areas:
        focus_hint = f"\nFocus specifically on these areas: {', '.join(focus_areas)}"

    messages = [
        {
            "role": "system",
            "content": """You are an expert visual QA analyst comparing a reference design with a development implementation.

Analyze both images and identify visual differences. For EACH difference, estimate the bounding box location as percentage of image dimensions (0-100).

Return your analysis as JSON:
{
  "similarity_score": 85,
  "differences": [
    {
      "label": "A",
      "description": "Button color differs - expected blue, got green",
      "severity": "Major",
      "x_pct": 10, "y_pct": 20, "w_pct": 15, "h_pct": 5
    }
  ],
  "summary": "Brief overall summary"
}

Labels should be A, B, C, etc. Coordinates are percentages of image dimensions.
Severity: Critical, Major, Minor, or Cosmetic.
Return ONLY the JSON, no other text."""
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"REFERENCE (design/target):{focus_hint}"},
                ref_content,
                {"type": "text", "text": "DEVELOPMENT (current implementation):"},
                dev_content,
            ],
        },
    ]

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": 2000},
        )
        result = response.json()

    if 'error' in result:
        return {'ok': False, 'error': result['error'].get('message', 'OpenAI API error')}

    analysis_text = result['choices'][0]['message']['content']

    # Parse JSON from response
    json_match = re.search(r'\{[\s\S]*\}', analysis_text)
    if json_match:
        try:
            analysis = json.loads(json_match.group())
            return {'ok': True, **analysis}
        except json.JSONDecodeError:
            pass

    return {'ok': True, 'similarity_score': None, 'differences': [], 'summary': analysis_text}


def _pct_to_px(differences: List[Dict], img_width: int, img_height: int) -> List[Dict]:
    """Convert percentage-based coordinates to pixel coordinates."""
    annotations = []
    for d in differences:
        annotations.append({
            'label': d.get('label', '?'),
            'x': int(d.get('x_pct', 0) * img_width / 100),
            'y': int(d.get('y_pct', 0) * img_height / 100),
            'width': int(d.get('w_pct', 10) * img_width / 100),
            'height': int(d.get('h_pct', 5) * img_height / 100),
            'description': d.get('description', ''),
            'severity': d.get('severity', 'Minor'),
        })
    return annotations


def _generate_visual_diff_html(
    report_data: Dict,
    ref_screenshot: str,
    dev_screenshot: str,
    annotated_screenshot: str,
    output_path: str,
) -> str:
    """Generate an HTML report with side-by-side comparison and annotations."""
    annotations = report_data.get('annotations', [])
    similarity = report_data.get('similarity_score', 'N/A')
    summary = report_data.get('summary', '')
    created_at = datetime.now().isoformat()

    ann_rows = ''
    for a in annotations:
        severity = a.get('severity', 'Minor')
        sev_class = {'Critical': 'error', 'Major': 'error', 'Minor': 'warning', 'Cosmetic': 'info'}.get(severity, 'info')
        ann_rows += f'''
        <tr class="{sev_class}">
            <td><strong>{a.get('label', '?')}</strong></td>
            <td>{severity}</td>
            <td>{a.get('description', '')}</td>
            <td>({a.get('x', 0)}, {a.get('y', 0)}) {a.get('width', 0)}x{a.get('height', 0)}</td>
        </tr>'''

    # Use relative paths for images
    ref_rel = os.path.basename(ref_screenshot) if ref_screenshot else ''
    dev_rel = os.path.basename(dev_screenshot) if dev_screenshot else ''
    ann_rel = os.path.basename(annotated_screenshot) if annotated_screenshot else ''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visual Diff Report</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: system-ui, sans-serif; max-width: 1400px; margin: 0 auto; padding: 2rem; background: #f5f5f5; }}
        .header {{ background: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .header h1 {{ margin: 0 0 0.5rem 0; }}
        .score {{ font-size: 2rem; font-weight: bold; color: {_score_color(similarity)}; }}
        .comparison {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }}
        .panel {{ background: white; padding: 1rem; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .panel h3 {{ margin: 0 0 0.5rem 0; font-size: 0.9rem; color: #666; }}
        .panel img {{ width: 100%; border: 1px solid #e5e7eb; border-radius: 4px; }}
        .annotated {{ background: white; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .annotated img {{ max-width: 100%; border: 1px solid #e5e7eb; border-radius: 4px; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid #e5e7eb; }}
        th {{ background: #f9fafb; font-weight: 600; }}
        tr.error {{ background: #fef2f2; }}
        tr.warning {{ background: #fffbeb; }}
        tr.info {{ background: #eff6ff; }}
        .summary {{ background: white; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Visual Diff Report</h1>
        <div>Similarity: <span class="score">{similarity}%</span></div>
        <div style="color:#999;font-size:0.85rem;">Generated at {created_at}</div>
    </div>

    <div class="summary">
        <h3>Summary</h3>
        <p>{summary}</p>
    </div>

    <div class="comparison">
        <div class="panel">
            <h3>Reference (Design/Target)</h3>
            <img src="{ref_rel}" alt="Reference">
        </div>
        <div class="panel">
            <h3>Development (Current)</h3>
            <img src="{dev_rel}" alt="Development">
        </div>
    </div>

    <div class="annotated">
        <h3>Annotated Differences</h3>
        <img src="{ann_rel}" alt="Annotated">
    </div>

    <h3>Difference Details ({len(annotations)} found)</h3>
    <table>
        <thead>
            <tr><th>Label</th><th>Severity</th><th>Description</th><th>Location</th></tr>
        </thead>
        <tbody>
            {ann_rows if ann_rows else '<tr><td colspan="4" style="text-align:center;color:#22c55e;">No differences found</td></tr>'}
        </tbody>
    </table>
</body>
</html>'''

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding='utf-8')
    return output_path


def _score_color(score) -> str:
    if score is None or score == 'N/A':
        return '#666'
    if isinstance(score, (int, float)):
        if score >= 90:
            return '#22c55e'
        if score >= 70:
            return '#f59e0b'
        return '#ef4444'
    return '#666'


@register_module(
    module_id='verify.visual_diff',
    version='1.0.0',
    category='verify',
    tags=['verify', 'visual', 'diff', 'compare', 'screenshot', 'design', 'figma'],
    label='Visual Diff',
    label_key='modules.verify.visual_diff.label',
    description='Compare reference design with dev site visually, annotate differences',
    description_key='modules.verify.visual_diff.description',
    icon='ScanSearch',
    color='#8B5CF6',

    input_types=['object'],
    output_types=['object', 'image', 'file'],

    can_receive_from=['verify.*', 'browser.*', 'vision.*'],
    can_connect_to=['verify.*', 'file.*', 'notification.*'],

    timeout_ms=120000,
    retryable=True,
    max_retries=1,
    concurrent_safe=True,

    requires_credentials=True,
    credential_keys=['OPENAI_API_KEY'],
    handles_sensitive_data=False,
    required_permissions=['browser.automation', 'file.write'],

    params_schema=compose(
        schema_field('reference_url', type='string', required=True, description='URL or local image path of reference design'),
        schema_field('dev_url', type='string', required=True, description='URL of development site to compare'),
        schema_field('output_dir', type='string', required=False, default='./verify-reports/visual-diff', description='Output directory for reports'),
        schema_field('focus_areas', type='array', required=False, description='Areas to focus on (e.g. ["header", "login form"])'),
        schema_field('viewport_width', type='integer', required=False, default=1280, description='Browser viewport width'),
        schema_field('viewport_height', type='integer', required=False, default=800, description='Browser viewport height'),
        schema_field('model', type='string', required=False, default='gpt-4o', description='Vision model to use'),
        schema_field('api_key', type='string', required=False, description='OpenAI API key (or use OPENAI_API_KEY env)'),
    ),
    output_schema={
        'similarity_score': {'type': 'number', 'description': 'Similarity percentage (0-100)'},
        'annotations': {'type': 'array', 'description': 'List of annotated differences'},
        'annotated_image': {'type': 'string', 'description': 'Path to annotated screenshot'},
        'report_path': {'type': 'string', 'description': 'Path to HTML report'},
        'summary': {'type': 'string', 'description': 'Summary of differences'},
    },
)
class VerifyVisualDiffModule(BaseModule):
    """End-to-end visual comparison: screenshot, AI diff, annotate, report."""

    module_name = "Visual Diff"
    module_description = "Compare reference with dev site and annotate differences"

    def validate_params(self) -> None:
        self.reference_url = self.params.get('reference_url')
        self.dev_url = self.params.get('dev_url')
        self.output_dir = Path(self.params.get('output_dir', './verify-reports/visual-diff'))
        self.focus_areas = self.params.get('focus_areas', [])
        self.viewport_width = self.params.get('viewport_width', 1280)
        self.viewport_height = self.params.get('viewport_height', 800)
        self.model = self.params.get('model', 'gpt-4o')
        self.api_key = self.params.get('api_key')

        if not self.reference_url:
            raise ValueError("reference_url is required")
        if not self.dev_url:
            raise ValueError("dev_url is required")

    async def execute(self) -> Dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Step 1: Screenshot both URLs (or use local image for reference)
        ref_screenshot = str(self.output_dir / f'ref_{timestamp}.png')
        dev_screenshot = str(self.output_dir / f'dev_{timestamp}.png')

        ref_is_url = self.reference_url.startswith(('http://', 'https://'))
        ref_is_image = not ref_is_url and Path(self.reference_url).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')

        if ref_is_url:
            await _screenshot_url(self.reference_url, ref_screenshot, self.viewport_width, self.viewport_height)
        elif ref_is_image:
            # Use existing image as reference
            import shutil
            shutil.copy2(self.reference_url, ref_screenshot)
        else:
            return {'ok': False, 'error': f'reference_url must be a URL or image path: {self.reference_url}'}

        await _screenshot_url(self.dev_url, dev_screenshot, self.viewport_width, self.viewport_height)

        # Step 2: AI vision comparison
        vision_result = await _vision_compare_images(
            ref_screenshot,
            dev_screenshot,
            focus_areas=self.focus_areas,
            api_key=self.api_key,
            model=self.model,
        )

        if not vision_result.get('ok', False):
            return {'ok': False, 'error': vision_result.get('error', 'Vision comparison failed')}

        similarity_score = vision_result.get('similarity_score')
        differences = vision_result.get('differences', [])
        summary = vision_result.get('summary', '')

        # Step 3: Convert percentage coordinates to pixel coordinates and annotate
        try:
            from PIL import Image
            dev_img = Image.open(dev_screenshot)
            img_width, img_height = dev_img.size
            dev_img.close()
        except ImportError:
            img_width, img_height = self.viewport_width, self.viewport_height

        annotations = _pct_to_px(differences, img_width, img_height)

        annotated_image = str(self.output_dir / f'annotated_{timestamp}.png')
        if annotations:
            from .annotate import draw_annotations
            draw_annotations(dev_screenshot, annotations, annotated_image)
        else:
            # No differences: copy dev screenshot as-is
            import shutil
            shutil.copy2(dev_screenshot, annotated_image)

        # Step 4: Generate HTML report
        report_path = str(self.output_dir / f'visual_diff_{timestamp}.html')
        report_data = {
            'similarity_score': similarity_score,
            'annotations': annotations,
            'summary': summary,
        }
        _generate_visual_diff_html(report_data, ref_screenshot, dev_screenshot, annotated_image, report_path)

        return {
            'ok': True,
            'data': {
                'similarity_score': similarity_score,
                'annotations': annotations,
                'annotated_image': annotated_image,
                'report_path': report_path,
                'reference_screenshot': ref_screenshot,
                'dev_screenshot': dev_screenshot,
                'summary': summary,
                'difference_count': len(annotations),
            },
        }
