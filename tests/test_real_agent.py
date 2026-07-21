#!/usr/bin/env python3
"""
Real AI Agent - 更接近真正的 AI Agent

架構：
┌─────────────────────────────────────────────────────────┐
│  1. Goal Understanding (目標理解)                        │
│     "測試登入" → 分解成具體測試案例                       │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  2. Planning (規劃)                                      │
│     生成測試計劃，預想結果                                │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  3. Execution (執行)                                     │
│     執行每個步驟，收集結果                                │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  4. Reflection (反思)                                    │
│     分析結果，決定下一步                                  │
└─────────────────────────────────────────────────────────┘
"""
import asyncio
import os
import sys
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, 'src')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import openai

import core.modules.atomic.browser.launch
import core.modules.atomic.browser.goto
import core.modules.atomic.browser.type
import core.modules.atomic.browser.click

from core.modules.registry import ModuleRegistry


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TestCase:
    """一個測試案例"""
    __test__ = False

    name: str
    description: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    expected_result: str = ""
    actual_result: str = ""
    status: TaskStatus = TaskStatus.PENDING


@dataclass
class AgentMemory:
    """Agent 的記憶"""
    site_structure: Dict[str, Any] = field(default_factory=dict)
    learned_selectors: Dict[str, str] = field(default_factory=dict)
    failed_attempts: List[Dict] = field(default_factory=list)
    successful_patterns: List[Dict] = field(default_factory=list)


# JavaScript to extract comprehensive UI structure
EXTRACT_UI_SCRIPT = """
() => {
    const result = {
        url: window.location.href,
        path: window.location.pathname,
        title: document.title,
        inputs: [],
        buttons: [],
        errors: [],
        forms: [],
        navigation: [],
        pageType: 'unknown'
    };

    // Detect page type
    const path = window.location.pathname.toLowerCase();
    if (path.includes('login') || path.includes('signin')) result.pageType = 'login';
    else if (path.includes('register') || path.includes('signup')) result.pageType = 'register';
    else if (path.includes('dashboard')) result.pageType = 'dashboard';
    else if (path === '/' || path === '') result.pageType = 'home';

    // Extract inputs with more details
    document.querySelectorAll('input, textarea, select').forEach((el, i) => {
        if (el.offsetParent !== null) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            result.inputs.push({
                index: i,
                tag: el.tagName.toLowerCase(),
                type: el.type || 'text',
                name: el.name || null,
                id: el.id || null,
                placeholder: el.placeholder || null,
                value: el.value || '',
                hasValue: !!el.value,
                required: el.required,
                disabled: el.disabled,
                autocomplete: el.autocomplete || null,
                label: label ? label.textContent.trim() : null,
                selector: el.id ? '#' + el.id :
                         el.name ? `[name="${el.name}"]` :
                         `input[type="${el.type}"]:nth-of-type(${i+1})`
            });
        }
    });

    // Extract buttons
    document.querySelectorAll('button, input[type="submit"], [role="button"]').forEach((el, i) => {
        if (el.offsetParent !== null) {
            result.buttons.push({
                index: i,
                text: el.textContent.trim().substring(0, 50),
                type: el.type || 'button',
                disabled: el.disabled,
                isSubmit: el.type === 'submit',
                selector: el.type === 'submit' ? 'button[type="submit"]' :
                         el.id ? '#' + el.id :
                         `button:nth-of-type(${i+1})`
            });
        }
    });

    // Extract errors/alerts
    document.querySelectorAll('.error, .alert, [role="alert"], .message.error, .toast').forEach(el => {
        if (el.offsetParent !== null && el.textContent.trim()) {
            result.errors.push({
                text: el.textContent.trim().substring(0, 200),
                type: el.className.includes('error') ? 'error' :
                      el.className.includes('success') ? 'success' : 'info'
            });
        }
    });

    // Extract navigation items
    document.querySelectorAll('nav a, .nav a, .sidebar a, .menu a').forEach(el => {
        if (el.href && el.textContent.trim()) {
            result.navigation.push({
                text: el.textContent.trim().substring(0, 30),
                href: el.href
            });
        }
    });

    return result;
}
"""


class RealAgent:
    """真正的 AI Agent"""

    def __init__(self, goal: str, start_url: str):
        self.goal = goal
        self.start_url = start_url
        self.context = {}
        self.memory = AgentMemory()
        self.test_cases: List[TestCase] = []
        self.current_ui: Dict[str, Any] = {}
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def run(self):
        """運行 Agent"""
        print("=" * 70)
        print(f"🤖 AI Agent Starting")
        print(f"   Goal: {self.goal}")
        print(f"   URL: {self.start_url}")
        print("=" * 70)

        # Phase 1: Launch browser and explore
        await self._launch_browser()
        await self._goto(self.start_url)
        await asyncio.sleep(2)

        # Phase 2: Understand the goal and create test plan
        print("\n📋 Phase 1: Understanding Goal & Creating Plan")
        await self._update_ui()
        await self._create_test_plan()

        # Phase 3: Execute test cases
        print("\n🚀 Phase 2: Executing Test Cases")
        await self._execute_test_cases()

        # Phase 4: Generate report
        print("\n📊 Phase 3: Generating Report")
        self._generate_report()

        # Cleanup
        print("\nKeeping browser open for 10 seconds...")
        await asyncio.sleep(10)
        if 'browser' in self.context:
            await self.context['browser'].close()

    async def _launch_browser(self):
        """啟動瀏覽器"""
        launch_cls = ModuleRegistry.get('browser.launch')
        launch_mod = launch_cls({'headless': False}, self.context)
        await launch_mod.execute()

    async def _goto(self, url: str):
        """前往網址"""
        goto_cls = ModuleRegistry.get('browser.goto')
        goto_mod = goto_cls({'url': url}, self.context)
        await goto_mod.execute()

    async def _update_ui(self):
        """更新 UI 結構"""
        browser = self.context.get('browser')
        if browser:
            self.current_ui = await browser.page.evaluate(EXTRACT_UI_SCRIPT)
            self.memory.site_structure[self.current_ui.get('path', '/')] = self.current_ui

    async def _create_test_plan(self):
        """讓 AI 理解目標並創建測試計劃"""
        prompt = f"""You are a QA AI Agent. Analyze the goal and current page to create a test plan.

## Goal
{self.goal}

## Current Page
URL: {self.current_ui.get('url')}
Page Type: {self.current_ui.get('pageType')}
Inputs: {json.dumps(self.current_ui.get('inputs', []), indent=2)}
Buttons: {json.dumps(self.current_ui.get('buttons', []), indent=2)}

## Task
Create a list of test cases to verify the goal. Each test case should have:
- name: Short name
- description: What to test
- test_type: "positive" (should work) or "negative" (should fail gracefully)
- inputs: Dict of field_type -> value to enter
- expected: What should happen

## Response Format (JSON only)
{{
    "understanding": "Your understanding of the goal",
    "test_cases": [
        {{
            "name": "Valid Login",
            "description": "Test login with correct credentials",
            "test_type": "positive",
            "inputs": {{"email": "team@flyto2.com", "password": "password123"}},
            "expected": "Should redirect to dashboard/home"
        }},
        ...
    ]
}}

Respond with JSON only."""

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith('```'):
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:]

        try:
            plan = json.loads(content)
            print(f"\n   Understanding: {plan.get('understanding', 'N/A')}")
            print(f"   Test cases: {len(plan.get('test_cases', []))}")

            for tc_data in plan.get('test_cases', []):
                tc = TestCase(
                    name=tc_data.get('name', 'Unnamed'),
                    description=tc_data.get('description', ''),
                    expected_result=tc_data.get('expected', ''),
                )
                tc.steps = [
                    {'action': 'input', 'data': tc_data.get('inputs', {})},
                    {'action': 'submit'},
                    {'action': 'verify', 'expected': tc_data.get('expected', '')}
                ]
                self.test_cases.append(tc)
                print(f"   - {tc.name}: {tc.description}")

        except json.JSONDecodeError as e:
            print(f"   ⚠️ Failed to parse plan: {e}")
            # Create a default test case
            self.test_cases.append(TestCase(
                name="Default Test",
                description="Execute the goal directly",
                expected_result="Success"
            ))

    async def _execute_test_cases(self):
        """執行所有測試案例"""
        for i, tc in enumerate(self.test_cases):
            print(f"\n   [{i+1}/{len(self.test_cases)}] {tc.name}")
            tc.status = TaskStatus.RUNNING

            try:
                # Reset to start page if needed
                await self._update_ui()
                if self.current_ui.get('pageType') != 'login':
                    await self._goto(self.start_url)
                    await asyncio.sleep(1)
                    await self._update_ui()

                # Execute steps
                for step in tc.steps:
                    if step['action'] == 'input':
                        await self._fill_form(step['data'])
                    elif step['action'] == 'submit':
                        await self._click_submit()
                        await asyncio.sleep(2)
                    elif step['action'] == 'verify':
                        await self._update_ui()
                        tc.actual_result = await self._verify_result(step['expected'])

                # Determine success
                await self._update_ui()
                if self.current_ui.get('pageType') in ('home', 'dashboard'):
                    tc.status = TaskStatus.SUCCESS
                    tc.actual_result = f"Redirected to {self.current_ui.get('path')}"
                    print(f"       ✅ PASS: {tc.actual_result}")
                elif self.current_ui.get('errors'):
                    tc.status = TaskStatus.FAILED
                    tc.actual_result = f"Error: {self.current_ui['errors'][0]['text']}"
                    print(f"       ❌ FAIL: {tc.actual_result}")
                else:
                    tc.status = TaskStatus.SUCCESS
                    tc.actual_result = f"No errors, page: {self.current_ui.get('pageType')}"
                    print(f"       ✅ PASS: {tc.actual_result}")

                # Record pattern
                if tc.status == TaskStatus.SUCCESS:
                    self.memory.successful_patterns.append({
                        'test': tc.name,
                        'selectors': self.memory.learned_selectors.copy()
                    })

            except Exception as e:
                tc.status = TaskStatus.FAILED
                tc.actual_result = str(e)
                print(f"       ❌ ERROR: {e}")
                self.memory.failed_attempts.append({
                    'test': tc.name,
                    'error': str(e)
                })

    async def _fill_form(self, data: Dict[str, str]):
        """填寫表單"""
        await self._update_ui()
        inputs = self.current_ui.get('inputs', [])

        for field_type, value in data.items():
            # Find matching input
            target = None
            for inp in inputs:
                if (inp.get('type') == field_type or
                    inp.get('autocomplete') == field_type or
                    field_type.lower() in str(inp.get('placeholder', '')).lower() or
                    field_type.lower() in str(inp.get('label', '')).lower() or
                    field_type.lower() in str(inp.get('name', '')).lower()):
                    target = inp
                    break

            if target:
                selector = target['selector']
                self.memory.learned_selectors[field_type] = selector
                print(f"       Typing {field_type} into {selector}")

                type_cls = ModuleRegistry.get('browser.type')
                type_mod = type_cls({'selector': selector, 'text': value}, self.context)
                await type_mod.execute()
            else:
                print(f"       ⚠️ Could not find input for {field_type}")

    async def _click_submit(self):
        """點擊提交按鈕"""
        await self._update_ui()
        buttons = self.current_ui.get('buttons', [])

        # Find submit button
        submit_btn = None
        for btn in buttons:
            if btn.get('isSubmit') or btn.get('type') == 'submit':
                submit_btn = btn
                break

        if submit_btn:
            selector = submit_btn['selector']
            print(f"       Clicking {selector}")
            click_cls = ModuleRegistry.get('browser.click')
            click_mod = click_cls({'selector': selector}, self.context)
            await click_mod.execute()
        else:
            print("       ⚠️ No submit button found")

    async def _verify_result(self, expected: str) -> str:
        """驗證結果"""
        await self._update_ui()
        return f"Page: {self.current_ui.get('pageType')}, URL: {self.current_ui.get('path')}"

    def _generate_report(self):
        """生成測試報告"""
        print("\n" + "=" * 70)
        print("📊 TEST REPORT")
        print("=" * 70)

        passed = sum(1 for tc in self.test_cases if tc.status == TaskStatus.SUCCESS)
        failed = sum(1 for tc in self.test_cases if tc.status == TaskStatus.FAILED)
        total = len(self.test_cases)

        print(f"\n   Summary: {passed}/{total} passed, {failed}/{total} failed")
        print(f"\n   Details:")

        for tc in self.test_cases:
            status_icon = "✅" if tc.status == TaskStatus.SUCCESS else "❌"
            print(f"   {status_icon} {tc.name}")
            print(f"      Expected: {tc.expected_result}")
            print(f"      Actual: {tc.actual_result}")

        print(f"\n   Learned Selectors:")
        for field, selector in self.memory.learned_selectors.items():
            print(f"      {field}: {selector}")

        print("=" * 70)


async def main():
    # 用自然語言描述目標，讓 AI 自己規劃
    agent = RealAgent(
        goal="Test the login functionality with email team@flyto2.com and password your_password",
        start_url="http://localhost:3000"
    )
    await agent.run()


if __name__ == '__main__':
    asyncio.run(main())
