# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Verify Visual Diff Module - End-to-end visual comparison pipeline

Pipeline:
1. Screenshot reference_url and dev_url via Playwright
2. Deterministically compare PNG pixels in the detachable TypeScript worker
3. Preserve content-addressed diff evidence
4. Generate a sanitized HTML report

Model interpretation belongs to flyto-ai and can consume this evidence as an
advisory step; it is never allowed to override the deterministic pass/fail.
"""
import html
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from ....utils import SSRFError, enforce_outbound_url
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose
from ...schema import field as schema_field
from ..testing.visual import compare_visual_files

logger = logging.getLogger(__name__)


async def _screenshot_url(url: str, output_path: str, viewport_width: int = 1280, viewport_height: int = 800) -> str:
    """Take a full-page screenshot of a URL using Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise ImportError(
            "playwright is required. Install with: pip install playwright && playwright install chromium"
        ) from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={'width': viewport_width, 'height': viewport_height})
            await page.emulate_media(reduced_motion='reduce')
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await page.evaluate("document.fonts && document.fonts.ready")
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=output_path, full_page=True, animations='disabled')
        finally:
            await browser.close()

    return output_path


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
    summary = html.escape(str(report_data.get('summary', '')))
    passed = report_data.get('passed') is True
    difference_percentage = report_data.get('difference_percentage', 'N/A')
    threshold_percentage = report_data.get('threshold_percentage', 'N/A')
    algorithm = html.escape(str(report_data.get('algorithm', 'unknown')))
    run_id = html.escape(str(report_data.get('run_id', '')))
    created_at = datetime.now().isoformat()

    ann_rows = ''
    for a in annotations:
        severity = html.escape(str(a.get('severity', 'Minor')))
        sev_class = {'Critical': 'error', 'Major': 'error', 'Minor': 'warning', 'Cosmetic': 'info'}.get(severity, 'info')
        ann_rows += f'''
        <tr class="{sev_class}">
            <td><strong>{html.escape(str(a.get('label', '?')))}</strong></td>
            <td>{severity}</td>
            <td>{html.escape(str(a.get('description', '')))}</td>
            <td>({a.get('x', 0)}, {a.get('y', 0)}) {a.get('width', 0)}x{a.get('height', 0)}</td>
        </tr>'''

    # Use relative paths for images
    ref_rel = html.escape(os.path.basename(ref_screenshot), quote=True) if ref_screenshot else ''
    dev_rel = html.escape(os.path.basename(dev_screenshot), quote=True) if dev_screenshot else ''
    ann_rel = html.escape(os.path.basename(annotated_screenshot), quote=True) if annotated_screenshot else ''

    report_html = f'''<!DOCTYPE html>
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
        .status {{ display:inline-block; padding:.25rem .65rem; border-radius:999px; color:white; background:{'#16a34a' if passed else '#dc2626'}; font-weight:700; }}
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
        <div class="status">{'PASSED' if passed else 'FAILED'}</div>
        <div>Similarity: <span class="score">{similarity}%</span></div>
        <div>Difference: {difference_percentage}% / budget {threshold_percentage}%</div>
        <div>Algorithm: {algorithm}</div>
        <div>Run ID: <code>{run_id}</code></div>
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
    Path(output_path).write_text(report_html, encoding='utf-8')
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
    version='2.0.0',
    category='verify',
    tags=['verify', 'visual', 'diff', 'compare', 'screenshot', 'design', 'figma'],
    label='Visual Diff',
    label_key='modules.verify.visual_diff.label',
    description='Deterministically compare a reference design with a dev site and preserve diff evidence',
    description_key='modules.verify.visual_diff.description',
    icon='ScanSearch',
    color='#8B5CF6',

    input_types=['object'],
    output_types=['object', 'image', 'file'],

    can_receive_from=['verify.*', 'browser.*', 'vision.*'],
    can_connect_to=['verify.*', 'file.*', 'notify.*'],

    timeout_ms=120000,
    retryable=True,
    max_retries=1,
    concurrent_safe=True,

    requires_credentials=False,
    credential_keys=[],
    handles_sensitive_data=False,
    required_permissions=['browser.automation', 'file.write'],

    params_schema=compose(
        schema_field('reference_url', type='string', required=True, description='URL or local image path of reference design',
                     placeholder='https://example.com'),
        schema_field('dev_url', type='string', required=True, description='URL of development site to compare',
                     placeholder='https://example.com'),
        schema_field('output_dir', type='string', required=False, default='./verify-reports/visual-diff', description='Output directory for reports',
                     placeholder='/path/to/output'),
        schema_field('viewport_width', type='number', required=False, default=1280, description='Browser viewport width'),
        schema_field('viewport_height', type='number', required=False, default=800, description='Browser viewport height'),
        schema_field('threshold', type='number', required=False, default=0.001, description='Maximum changed-pixel ratio (0-1)'),
        schema_field('color_threshold', type='number', required=False, default=0.1, description='Per-pixel color sensitivity (0-1)'),
    ),
    output_schema={
        'similarity_score': {'type': 'number', 'description': 'Similarity percentage (0-100)'},
        'passed': {'type': 'boolean', 'description': 'Whether deterministic visual budget passed'},
        'difference_percentage': {'type': 'number', 'description': 'Changed-pixel percentage (0-100)'},
        'annotations': {'type': 'array', 'description': 'List of annotated differences'},
        'annotated_image': {'type': 'string', 'description': 'Path to annotated screenshot'},
        'report_path': {'type': 'string', 'description': 'Path to HTML report'},
        'summary': {'type': 'string', 'description': 'Summary of differences'},
    },
)
class VerifyVisualDiffModule(BaseModule):
    """End-to-end deterministic visual comparison and evidence report."""

    module_name = "Visual Diff"
    module_description = "Compare reference with dev site and annotate differences"

    def validate_params(self) -> None:
        self.reference_url = self.params.get('reference_url')
        self.dev_url = self.params.get('dev_url')
        self.output_dir = Path(self.params.get('output_dir', './verify-reports/visual-diff'))
        self.viewport_width = int(self.params.get('viewport_width', 1280))
        self.viewport_height = int(self.params.get('viewport_height', 800))
        self.threshold = float(self.params.get('threshold', 0.001))
        self.color_threshold = float(self.params.get('color_threshold', 0.1))

        if not self.reference_url:
            raise ValueError("reference_url is required")
        if not self.dev_url:
            raise ValueError("dev_url is required")
        if not 320 <= self.viewport_width <= 7680:
            raise ValueError("viewport_width must be between 320 and 7680")
        if not 320 <= self.viewport_height <= 4320:
            raise ValueError("viewport_height must be between 320 and 4320")
        if not 0 <= self.threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        if not 0 <= self.color_threshold <= 1:
            raise ValueError("color_threshold must be between 0 and 1")

    async def execute(self) -> Dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Step 1: Screenshot both URLs (or use local image for reference)
        ref_screenshot = str(self.output_dir / f'ref_{timestamp}.png')
        dev_screenshot = str(self.output_dir / f'dev_{timestamp}.png')

        ref_is_url = self.reference_url.startswith(('http://', 'https://'))
        ref_is_image = not ref_is_url and Path(self.reference_url).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')

        # SECURITY: gate the client-controlled URLs through the SSRF guard before
        # the headless browser navigates to them (GHSA-pgwh-4jj4-qm8v).
        try:
            if ref_is_url:
                enforce_outbound_url(self.reference_url)
            enforce_outbound_url(self.dev_url)
        except SSRFError as e:
            return {'ok': False, 'error': f'SSRF protection blocked request: {e}', 'error_code': 'SSRF_BLOCKED'}

        if ref_is_url:
            await _screenshot_url(self.reference_url, ref_screenshot, self.viewport_width, self.viewport_height)
        elif ref_is_image:
            try:
                from PIL import Image
            except ImportError as exc:
                raise ImportError("Pillow is required for local reference images") from exc
            with Image.open(self.reference_url) as source_image:
                source_image.convert('RGBA').save(ref_screenshot, format='PNG')
        else:
            return {'ok': False, 'error': f'reference_url must be a URL or image path: {self.reference_url}'}

        await _screenshot_url(self.dev_url, dev_screenshot, self.viewport_width, self.viewport_height)

        # Step 2: deterministic comparison. This is the sole pass/fail authority;
        # flyto-ai may later interpret the evidence, but cannot override it.
        diff_image = str(self.output_dir / f'diff_{timestamp}.png')
        comparison = await compare_visual_files(
            ref_screenshot,
            dev_screenshot,
            threshold=self.threshold,
            color_threshold=self.color_threshold,
            output_diff=True,
            diff_path=diff_image,
        )

        if not comparison.get('ok', False):
            return comparison

        difference_ratio = comparison['difference']
        difference_percentage = comparison['diff_percentage']
        similarity_score = max(0.0, (1 - difference_ratio) * 100)
        passed = comparison['match']
        annotations: List[Dict[str, Any]] = []
        annotated_image = comparison['diff_image']
        summary = (
            f"Deterministic visual budget {'passed' if passed else 'failed'}: "
            f"{difference_percentage:.4f}% changed pixels with a {self.threshold * 100:.4f}% budget."
        )

        # Step 4: Generate HTML report
        report_path = str(self.output_dir / f'visual_diff_{timestamp}.html')
        report_data = {
            'similarity_score': similarity_score,
            'passed': passed,
            'difference_percentage': difference_percentage,
            'threshold_percentage': self.threshold * 100,
            'algorithm': comparison['algorithm'],
            'run_id': comparison['run_id'],
            'annotations': annotations,
            'summary': summary,
        }
        _generate_visual_diff_html(report_data, ref_screenshot, dev_screenshot, annotated_image, report_path)

        return {
            'ok': True,
            'data': {
                'similarity_score': similarity_score,
                'passed': passed,
                'match': passed,
                'difference_ratio': difference_ratio,
                'difference_percentage': difference_percentage,
                'threshold': self.threshold,
                'annotations': annotations,
                'annotated_image': annotated_image,
                'diff_image': comparison['diff_image'],
                'report_path': report_path,
                'reference_screenshot': ref_screenshot,
                'dev_screenshot': dev_screenshot,
                'summary': summary,
                'difference_count': len(annotations),
                'algorithm': comparison['algorithm'],
                'run_id': comparison['run_id'],
                'evidence': comparison['evidence'],
                'dimensions': comparison['dimensions'],
                'advisory': {
                    'status': 'not_requested',
                    'owner': 'flyto-ai',
                    'can_override_gate': False,
                },
            },
        }
