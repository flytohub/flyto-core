# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Cookies File Module — Import/export cookies to/from JSON file

Enables session persistence beyond browser profile:
- Export current cookies to a JSON file
- Import cookies from a JSON file (restore session)
- Compatible with other tools' cookie formats (Puppeteer, curl, etc.)
"""
import json
import logging
from pathlib import Path
from typing import Any
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)


@register_module(
    module_id='browser.cookies_file',
    version='1.0.0',
    category='browser',
    tags=['browser', 'cookies', 'session', 'export', 'import', 'persistence'],
    label='Cookies File',
    label_key='modules.browser.cookies_file.label',
    description='Import or export browser cookies to/from a JSON file for session persistence.',
    description_key='modules.browser.cookies_file.description',
    icon='FileJson',
    color='#F97316',
    input_types=['page'],
    output_types=['json'],
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'file.*'],
    params_schema=compose(
        field('action', type='select', label='Action',
              description='Export cookies to file or import from file.',
              required=True, default='export',
              options=[
                  {'value': 'export', 'label': 'Export to file'},
                  {'value': 'import', 'label': 'Import from file'},
              ],
              group='basic'),
        field('file_path', type='string', label='File path',
              description='Path to the JSON cookies file.',
              required=True, placeholder='~/.flyto/cookies/site.json',
              format='path',
              group='basic'),
        field('domain_filter', type='string', label='Domain filter',
              description='Only export/import cookies for this domain (e.g., ".github.com"). Empty = all.',
              required=False, default='',
              group='advanced'),
    ),
    output_schema={
        'action':       {'type': 'string', 'description': 'Action performed (export/import)'},
        'cookie_count': {'type': 'number', 'description': 'Number of cookies exported/imported'},
        'file_path':    {'type': 'string', 'description': 'Path to the cookies file'},
        'domains':      {'type': 'array',  'description': 'Unique domains in the cookies'},
    },
    examples=[
        {'name': 'Export all cookies', 'params': {'action': 'export', 'file_path': 'cookies.json'}},
        {'name': 'Import session', 'params': {'action': 'import', 'file_path': 'cookies.json'}},
        {'name': 'Export for specific domain', 'params': {'action': 'export', 'file_path': 'gh.json', 'domain_filter': '.github.com'}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=10000,
    required_permissions=["browser.read", "browser.write"],
)
class BrowserCookiesFileModule(BaseModule):
    module_name = "Cookies File"
    required_permission = "browser.write"

    def validate_params(self) -> None:
        self.action = self.params.get('action', 'export')
        if self.action not in ('export', 'import'):
            raise ValueError(f"Invalid action: {self.action}")
        raw_path = self.params.get('file_path', '')
        if not raw_path:
            raise ValueError("file_path is required")
        self.file_path = Path(raw_path).expanduser()
        self.domain_filter = self.params.get('domain_filter', '')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        context = browser._context

        if self.action == 'export':
            return await self._export(context)
        else:
            return await self._import(context)

    async def _export(self, context) -> dict:
        cookies = await context.cookies()

        if self.domain_filter:
            cookies = [c for c in cookies if self.domain_filter in c.get('domain', '')]

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(cookies, indent=2, default=str), encoding='utf-8')

        domains = sorted(set(c.get('domain', '') for c in cookies))
        logger.info("Exported %d cookies to %s", len(cookies), self.file_path)

        return {
            "status": "success",
            "action": "export",
            "cookie_count": len(cookies),
            "file_path": str(self.file_path),
            "domains": domains,
        }

    async def _import(self, context) -> dict:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Cookie file not found: {self.file_path}")

        data = json.loads(self.file_path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise ValueError("Cookie file must contain a JSON array")

        cookies = data
        if self.domain_filter:
            cookies = [c for c in cookies if self.domain_filter in c.get('domain', '')]

        # Playwright expects specific fields; strip extras
        clean = []
        for c in cookies:
            entry = {
                'name': c['name'],
                'value': c['value'],
                'domain': c.get('domain', ''),
                'path': c.get('path', '/'),
            }
            if c.get('expires'):
                entry['expires'] = c['expires']
            if c.get('httpOnly') is not None:
                entry['httpOnly'] = c['httpOnly']
            if c.get('secure') is not None:
                entry['secure'] = c['secure']
            if c.get('sameSite'):
                entry['sameSite'] = c['sameSite']
            clean.append(entry)

        await context.add_cookies(clean)

        domains = sorted(set(c.get('domain', '') for c in clean))
        logger.info("Imported %d cookies from %s", len(clean), self.file_path)

        return {
            "status": "success",
            "action": "import",
            "cookie_count": len(clean),
            "file_path": str(self.file_path),
            "domains": domains,
        }
