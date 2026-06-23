# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Warroom deterministic site discovery module."""

from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from .engine import build_site_graph

DISCOVERY_JS = r"""() => {
  const controls = Array.from(document.querySelectorAll('button, a, input, textarea, select, [role="button"], [role="tab"], [aria-haspopup="menu"]'))
    .filter((el) => {
      const style = window.getComputedStyle(el);
      return style.display !== 'none' && style.visibility !== 'hidden';
    })
    .slice(0, 160)
    .map((el, index) => {
      const testid = el.getAttribute('data-testid') || '';
      if (!testid && !el.getAttribute('data-flyto-verification-control') && !el.getAttribute('data-warroom-control')) {
        el.setAttribute('data-flyto-verification-control', String(index + 1));
      }
      return {
        tag: el.tagName.toLowerCase(),
        kind: el.getAttribute('role') || el.tagName.toLowerCase(),
        text: (el.textContent || '').trim().slice(0, 120),
        aria_label: el.getAttribute('aria-label') || '',
        name: el.getAttribute('name') || '',
        id: el.id || '',
        testid,
        href: el.getAttribute('href') || '',
        disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
        selector: testid ? `[data-testid="${testid}"]` : `[data-flyto-verification-control="${index + 1}"]`
      };
    });
  const root = document.documentElement;
  return {
    url: location.href,
    title: document.title,
    text: document.body?.innerText || '',
    horizontal_overflow: root.scrollWidth > innerWidth + 2,
    controls,
    requests: window.__flytoVerificationRequests || window.__flytoWarroomRequests || []
  };
}"""


@register_module(
    module_id="warroom.discover",
    version="1.0.0",
    category="warroom",
    tags=["warroom", "discovery", "deterministic", "browser", "evidence"],
    label="Warroom Discover",
    description="Build a deterministic site graph from browser state or supplied page snapshots",
    icon="Radar",
    color="#0EA5E9",
    input_types=["object"],
    output_types=["object"],
    can_receive_from=["browser.*", "data.*", "flow.*", "start"],
    can_connect_to=["warroom.*", "testing.*", "verify.*", "data.*", "file.*"],
    params_schema={
        "target": {"type": "string", "required": True, "description": "Target base URL or page URL"},
        "pages": {"type": "array", "required": False, "description": "Optional pre-collected page observations"},
        "use_browser": {"type": "boolean", "default": True, "description": "Read current browser page when available"},
    },
    output_schema={
        "ok": {"type": "boolean"},
        "site_graph": {"type": "object"},
        "scores": {"type": "object"},
    },
    timeout_ms=120000,
)
class WarroomDiscoverModule(BaseModule):
    """Build a deterministic Warroom site graph."""

    module_name = "Warroom Discover"
    module_description = "Build deterministic site graph from browser evidence"

    def validate_params(self) -> None:
        if not self.params.get("target"):
            raise ValueError("target is required")

    async def execute(self) -> Dict[str, Any]:
        pages = list(self.params.get("pages") or [])
        browser = self.context.get("browser")
        if self.params.get("use_browser", True) and browser and getattr(browser, "page", None):
            page_snapshot = await browser.page.evaluate(DISCOVERY_JS)
            pages.append(page_snapshot)
        if not pages:
            pages.append({"url": self.params["target"], "text": "", "controls": [], "requests": []})
        graph = build_site_graph(self.params["target"], pages)
        return {"ok": True, "site_graph": graph, "scores": graph["scores"]}
