#!/usr/bin/env python3
"""
測試瀏覽器自動化登入 localhost:3000
"""
import asyncio
import os
import sys

# 設定環境變數允許 localhost
os.environ["FLYTO_VSCODE_LOCAL_MODE"] = "true"

sys.path.insert(0, 'src')

# 載入 browser 模組 (只需要 import 就會自動註冊)
import core.modules.atomic.browser.launch
import core.modules.atomic.browser.goto
import core.modules.atomic.browser.type
import core.modules.atomic.browser.click

async def test_login():
    from core.modules.registry import ModuleRegistry

    context = {}

    # 1. Launch browser
    print('1. Launching browser...')
    launch_cls = ModuleRegistry.get('browser.launch')
    launch_mod = launch_cls({'headless': False}, context)
    result = await launch_mod.execute()
    print(f'   Result: {result}')

    # 2. Go to URL
    print('2. Going to localhost:3000...')
    goto_cls = ModuleRegistry.get('browser.goto')
    goto_mod = goto_cls({'url': 'http://localhost:3000'}, context)
    result = await goto_mod.execute()
    print(f'   Result: {result}')

    # 等待頁面載入
    await asyncio.sleep(2)

    # 3. Type email
    print('3. Typing email...')
    type_cls = ModuleRegistry.get('browser.type')
    type_email = type_cls({
        'selector': 'input[type="email"], input[name="email"], #email, input[placeholder*="mail"]',
        'text': 'user@example.com'
    }, context)
    result = await type_email.execute()
    print(f'   Result: ok={result.get("ok", False)}')

    # 4. Type password
    print('4. Typing password...')
    type_pass = type_cls({
        'selector': 'input[type="password"], input[name="password"], #password',
        'text': 'your_password'
    }, context)
    result = await type_pass.execute()
    print(f'   Result: ok={result.get("ok", False)}')

    # 5. Click submit
    print('5. Clicking submit...')
    click_cls = ModuleRegistry.get('browser.click')
    click_mod = click_cls({
        'selector': 'button[type="submit"], button:has-text("Login"), button:has-text("登入"), .login-btn'
    }, context)
    result = await click_mod.execute()
    print(f'   Result: ok={result.get("ok", False)}')

    print('\nDone! Waiting 10 seconds before closing...')
    await asyncio.sleep(10)

    # Close browser
    if 'browser' in context:
        await context['browser'].close()

if __name__ == '__main__':
    asyncio.run(test_login())
