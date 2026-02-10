#!/usr/bin/env python3
"""直接用 Playwright 調試頁面"""
import asyncio
from playwright.async_api import async_playwright


async def debug_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print("Going to localhost:3000...")
        await page.goto('http://localhost:3000')

        print("Waiting for page to settle...")
        await asyncio.sleep(3)

        print(f"\nCurrent URL: {page.url}")
        print(f"Title: {await page.title()}")

        # 列出所有 input
        print("\n=== ALL INPUTS ===")
        inputs = await page.query_selector_all('input')
        for i, inp in enumerate(inputs):
            html = await inp.evaluate('el => el.outerHTML')
            visible = await inp.is_visible()
            print(f"{i+1}. visible={visible} | {html[:150]}")

        # 列出所有 button
        print("\n=== ALL BUTTONS ===")
        buttons = await page.query_selector_all('button')
        for i, btn in enumerate(buttons):
            text = await btn.text_content()
            visible = await btn.is_visible()
            html = await btn.evaluate('el => el.outerHTML')
            print(f"{i+1}. visible={visible} text='{text.strip()}' | {html[:100]}")

        # 截圖
        await page.screenshot(path='/tmp/debug_page.png')
        print("\n📸 Screenshot saved to /tmp/debug_page.png")

        print("\nKeeping browser open for 30 seconds...")
        await asyncio.sleep(30)

        await browser.close()


if __name__ == '__main__':
    asyncio.run(debug_page())
