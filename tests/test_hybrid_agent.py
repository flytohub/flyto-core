#!/usr/bin/env python3
"""
Hybrid Agent: 規則優先 + AI 備援

設計原則：
1. 常見操作用規則處理（快、穩定、免費）
2. 只在必要時才呼叫 AI
3. 明確的成功/失敗判斷
"""
import asyncio
import os
import sys
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

os.environ["FLYTO_VSCODE_LOCAL_MODE"] = "true"
sys.path.insert(0, 'src')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Import browser modules
import core.modules.atomic.browser.launch
import core.modules.atomic.browser.goto
import core.modules.atomic.browser.type
import core.modules.atomic.browser.click
import core.modules.atomic.browser.screenshot
import core.modules.atomic.browser.extract
import core.modules.atomic.browser.wait

from core.modules.registry import ModuleRegistry


@dataclass
class LoginTask:
    """登入任務定義"""
    url: str
    email: str
    password: str
    # 常見選擇器 - 按優先順序嘗試
    email_selectors: List[str] = None
    password_selectors: List[str] = None
    submit_selectors: List[str] = None
    # 成功判斷
    success_indicators: List[str] = None

    def __post_init__(self):
        if self.email_selectors is None:
            self.email_selectors = [
                # Flyto Cloud 專用
                'input[autocomplete="email"]',
                # 通用
                'input[type="email"]',
                'input[name="email"]',
                '#email',
                'input[placeholder*="mail" i]',
            ]
        if self.password_selectors is None:
            self.password_selectors = [
                # Flyto Cloud 專用
                'input[autocomplete="current-password"]',
                # 通用
                'input[type="password"]',
                'input[name="password"]',
                '#password',
            ]
        if self.submit_selectors is None:
            self.submit_selectors = [
                # Flyto Cloud 專用
                'button.submit-btn',
                # 通用
                'button[type="submit"]',
                'form button',
            ]
        if self.success_indicators is None:
            self.success_indicators = [
                # URL 變化
                '/templates',
                '/dashboard',
                '/home',
                '/app',
                # 元素出現
                '.sidebar',
                'nav',
                '.user-menu',
            ]


async def find_element(context: dict, selectors: List[str], timeout: int = 5000) -> Optional[str]:
    """嘗試多個選擇器，返回第一個找到的"""
    browser = context.get('browser')
    if not browser:
        return None

    page = browser.page  # BrowserDriver.page property

    for selector in selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=timeout)
            if element:
                print("  ✓ Found matching selector")
                return selector
        except Exception:
            continue

    return None


async def check_success(context: dict, indicators: List[str]) -> bool:
    """檢查是否登入成功"""
    browser = context.get('browser')
    if not browser:
        return False

    page = browser.page
    current_url = page.url

    # 檢查 URL 變化
    for indicator in indicators:
        if indicator.startswith('/') and indicator in current_url:
            print(f"  ✓ URL contains: {indicator}")
            return True

    # 檢查元素出現
    for indicator in indicators:
        if not indicator.startswith('/'):
            try:
                element = await page.wait_for_selector(indicator, timeout=2000)
                if element:
                    print(f"  ✓ Element found: {indicator}")
                    return True
            except Exception:
                continue

    return False


async def execute_login_workflow(task: LoginTask) -> Dict[str, Any]:
    """執行登入流程 - 規則驅動"""
    context = {}

    try:
        # 1. 啟動瀏覽器
        print("Step 1: Launching browser...")
        launch_cls = ModuleRegistry.get('browser.launch')
        launch_mod = launch_cls({'headless': False}, context)
        await launch_mod.execute()

        # 2. 前往網址
        print(f"Step 2: Going to {task.url}...")
        goto_cls = ModuleRegistry.get('browser.goto')
        goto_mod = goto_cls({'url': task.url}, context)
        await goto_mod.execute()

        await asyncio.sleep(2)  # 等待頁面載入

        # 3. 找到並填入 email
        print("Step 3: Finding email field...")
        email_selector = await find_element(context, task.email_selectors)
        if not email_selector:
            return {'ok': False, 'error': 'Email field not found', 'tried': task.email_selectors}

        type_cls = ModuleRegistry.get('browser.type')
        type_mod = type_cls({'selector': email_selector, 'text': task.email}, context)
        await type_mod.execute()
        print(f"  Typed email: {task.email}")

        # 4. 找到並填入 password
        print("Step 4: Finding password field...")
        password_selector = await find_element(context, task.password_selectors)
        if not password_selector:
            return {'ok': False, 'error': 'Password field not found', 'tried': task.password_selectors}

        type_mod = type_cls({'selector': password_selector, 'text': task.password}, context)
        await type_mod.execute()
        print(f"  Typed password: {'*' * len(task.password)}")

        # 5. 點擊登入按鈕
        print("Step 5: Finding submit button...")
        submit_selector = await find_element(context, task.submit_selectors)
        if not submit_selector:
            return {'ok': False, 'error': 'Submit button not found', 'tried': task.submit_selectors}

        click_cls = ModuleRegistry.get('browser.click')
        click_mod = click_cls({'selector': submit_selector}, context)
        await click_mod.execute()
        print(f"  Clicked: {submit_selector}")

        # 6. 等待並檢查結果
        print("Step 6: Checking login result...")
        await asyncio.sleep(3)  # 等待登入處理

        success = await check_success(context, task.success_indicators)

        if success:
            print("\n✅ Login successful!")
            return {'ok': True, 'message': 'Login successful'}
        else:
            # 檢查錯誤訊息
            page = context.get('page')
            error_selectors = ['.error', '.alert-error', '[role="alert"]', '.message.error']
            for sel in error_selectors:
                try:
                    element = await page.wait_for_selector(sel, timeout=1000)
                    if element:
                        error_text = await element.text_content()
                        print(f"\n❌ Login failed: {error_text}")
                        return {'ok': False, 'error': error_text}
                except Exception:
                    continue

            print("\n⚠️ Login status unclear")
            return {'ok': False, 'error': 'Could not verify login success'}

    except Exception as e:
        return {'ok': False, 'error': str(e)}

    finally:
        # 保持瀏覽器開啟一段時間供檢查
        print("\nKeeping browser open for 10 seconds...")
        await asyncio.sleep(10)

        if 'browser' in context:
            await context['browser'].close()


async def main():
    """測試登入流程"""
    task = LoginTask(
        url="http://localhost:3000",
        email="user@example.com",
        password="your_password",
        # 可以自訂選擇器
        success_indicators=[
            '/dashboard',
            '/home',
            '/templates',
            '.user-menu',
            '.sidebar',
            '[data-testid="main-layout"]',
        ]
    )

    result = await execute_login_workflow(task)
    print(f"\nFinal result: ok={result.get('ok')}")


if __name__ == '__main__':
    asyncio.run(main())
