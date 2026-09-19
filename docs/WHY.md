# Why flyto-core is shaped this way

## The 85-line problem

Here's what competitive pricing analysis looks like in Python:

<table>
<tr>
<td width="50%">

**Python** — 85 lines

```python
import asyncio, json, time
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://competitor.com/pricing")

        # Extract pricing
        prices = await page.evaluate("""() => {
            const cards = document.querySelectorAll(
              '[class*="price"]'
            );
            return Array.from(cards).map(
              c => c.textContent.trim()
            );
        }""")

        # Desktop screenshot
        await page.screenshot(
            path="desktop.png", full_page=True
        )

        # Mobile
        await page.set_viewport_size(
            {"width": 390, "height": 844}
        )
        await page.screenshot(
            path="mobile.png", full_page=True
        )

        # Performance
        perf = await page.evaluate("""() => {
            const nav = performance
              .getEntriesByType('navigation')[0];
            return {
              ttfb: nav.responseStart,
              loaded: nav.loadEventEnd
            };
        }""")

        # Save report
        report = {
            "prices": prices,
            "performance": perf,
        }
        with open("report.json", "w") as f:
            json.dump(report, f, indent=2)

        await browser.close()

asyncio.run(main())
```

</td>
<td width="50%">

**flyto-core** — 12 steps

```yaml
name: Competitor Intel
steps:
  - id: launch
    module: browser.launch
  - id: navigate
    module: browser.goto
    params: { url: "{{url}}" }
  - id: prices
    module: browser.evaluate
    params:
      script: |
        JSON.stringify([
          ...document.querySelectorAll(
            '[class*="price"]'
          )
        ].map(e => e.textContent.trim()))
  - id: desktop_shot
    module: browser.screenshot
    params: { path: desktop.png, full_page: true }
  - id: mobile
    module: browser.viewport
    params: { width: 390, height: 844 }
  - id: mobile_shot
    module: browser.screenshot
    params: { path: mobile.png, full_page: true }
  - id: perf
    module: browser.performance
  - id: save
    module: file.write
    params:
      path: report.json
      content: "${prices.result}"
  - id: close
    module: browser.close
```

</td>
</tr>
<tr>
<td>

No trace. No replay. No timing. If step 5 fails, re-run everything.

</td>
<td>

Full trace. Replay from any step. Per-step timing. Every run is debuggable.

</td>
</tr>
</table>

---
