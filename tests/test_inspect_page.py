#!/usr/bin/env python3
"""檢查頁面結構"""
import asyncio
import os
import sys

os.environ["FLYTO_VSCODE_LOCAL_MODE"] = "true"
sys.path.insert(0, 'src')

import core.modules.atomic.browser.launch
import core.modules.atomic.browser.goto

from core.modules.registry import ModuleRegistry


async def inspect_page():
    context = {}

    # Launch browser
    print("Launching browser...")
    launch_cls = ModuleRegistry.get('browser.launch')
    launch_mod = launch_cls({'headless': False}, context)
    await launch_mod.execute()

    # Go to URL
    print("Going to localhost:3000...")
    goto_cls = ModuleRegistry.get('browser.goto')
    goto_mod = goto_cls({'url': 'http://localhost:3000'}, context)
    await goto_mod.execute()

    await asyncio.sleep(3)

    page = context.get('page')
    if page:
        # 列出所有 input 元素
        print("\n=== INPUT ELEMENTS ===")
        inputs = await page.query_selector_all('input')
        for i, inp in enumerate(inputs):
            tag = await inp.evaluate('el => el.outerHTML')
            print(f"{i+1}. {tag[:200]}")

        # 列出所有 button 元素
        print("\n=== BUTTON ELEMENTS ===")
        buttons = await page.query_selector_all('button')
        for i, btn in enumerate(buttons):
            text = await btn.text_content()
            tag = await btn.evaluate('el => el.outerHTML')
            print(f"{i+1}. text='{text}' | {tag[:200]}")

        # 列出 form 元素
        print("\n=== FORM ELEMENTS ===")
        forms = await page.query_selector_all('form')
        for i, form in enumerate(forms):
            tag = await form.evaluate('el => el.outerHTML')
            print(f"{i+1}. {tag[:500]}")

        print("\n=== Current URL ===")
        print(page.url)

    await asyncio.sleep(30)

    if 'browser' in context:
        await context['browser'].close()


if __name__ == '__main__':
    asyncio.run(inspect_page())
