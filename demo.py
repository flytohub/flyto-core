"""30-second demo: Give your AI 412 tools with one command."""
import asyncio
import sys
import logging

logging.disable(logging.CRITICAL)

from core.modules.registry import ModuleRegistry

G = "\033[32m"
C = "\033[36m"
Y = "\033[33m"
B = "\033[1m"
D = "\033[2m"
R = "\033[0m"


async def main():
    print(f"\n{B}flyto-core demo — 412 tools for AI agents{R}\n")

    ctx = {}

    # Step 1: Launch browser
    print(f"{D}━━━ Step 1: browser.launch ━━━{R}")
    await ModuleRegistry.execute("browser.launch", params={"headless": True}, context=ctx)
    print(f"{G}✓{R} Browser launched (headless)\n")

    # Step 2: Navigate
    print(f"{D}━━━ Step 2: browser.goto ━━━{R}")
    await ModuleRegistry.execute("browser.goto",
        params={"url": "https://news.ycombinator.com"}, context=ctx)
    print(f"{G}✓{R} Navigated to Hacker News\n")

    # Step 3: Extract data
    print(f"{D}━━━ Step 3: browser.extract ━━━{R}")
    r = await ModuleRegistry.execute("browser.extract",
        params={
            "selector": ".titleline",
            "limit": 5,
            "fields": {
                "title": {"selector": "a", "type": "text"},
                "url": {"selector": "a", "type": "attribute", "attribute": "href"},
            },
        },
        context=ctx)
    elements = r.get("data", [])
    print(f"{G}✓{R} Extracted top 5 stories:\n")
    for i, el in enumerate(elements, 1):
        title = (el.get("title", "") if isinstance(el, dict) else str(el))[:65]
        print(f"  {C}{i}.{R} {title}")

    # Step 4: String transform
    print(f"\n{D}━━━ Step 4: string.uppercase ━━━{R}")
    r = await ModuleRegistry.execute("string.uppercase",
        params={"text": "flyto-core: 412 tools, zero config"}, context={})
    result = r.get("result", r.get("data", {}).get("result", ""))
    print(f"{G}✓{R} {Y}{result}{R}\n")

    # Step 5: Close
    print(f"{D}━━━ Step 5: browser.close ━━━{R}")
    await ModuleRegistry.execute("browser.close", params={}, context=ctx)
    print(f"{G}✓{R} Browser closed\n")

    print(f"{B}Done!{R} 5 tools executed. No LLM calls. Deterministic.\n")


asyncio.run(main())
