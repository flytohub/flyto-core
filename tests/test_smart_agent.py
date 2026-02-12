#!/usr/bin/env python3
"""
Smart Agent: UI 結構分析 + LLM 決策

設計理念：
1. 第一步：用 JS 提取頁面結構（input, button, form, error messages）
2. 丟給 LLM 分析，LLM 直接回傳要執行的動作 + 精確選擇器
3. 執行動作，再次分析結構，直到完成

優點：
- LLM 看到的是結構化資料，不是圖片
- 選擇器是精確的，不需要猜測
- 成本更低（不用 vision API）
- 更可靠
"""
import asyncio
import os
import sys
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

os.environ["FLYTO_VSCODE_LOCAL_MODE"] = "true"
sys.path.insert(0, 'src')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import openai

# Import browser modules
import core.modules.atomic.browser.launch
import core.modules.atomic.browser.goto
import core.modules.atomic.browser.type
import core.modules.atomic.browser.click

from core.modules.registry import ModuleRegistry


# JavaScript to extract UI structure
EXTRACT_UI_SCRIPT = """
() => {
    const result = {
        url: window.location.href,
        title: document.title,
        inputs: [],
        buttons: [],
        links: [],
        errors: [],
        forms: []
    };

    // Extract all visible inputs
    document.querySelectorAll('input').forEach((el, i) => {
        if (el.offsetParent !== null) {  // visible check
            const info = {
                index: i,
                type: el.type,
                name: el.name || null,
                id: el.id || null,
                placeholder: el.placeholder || null,
                value: el.value || null,
                autocomplete: el.autocomplete || null,
                required: el.required,
                selector: null
            };
            // Build best selector
            if (el.id) info.selector = '#' + el.id;
            else if (el.name) info.selector = `input[name="${el.name}"]`;
            else if (el.type) info.selector = `input[type="${el.type}"]:nth-of-type(${i+1})`;
            else info.selector = `input:nth-of-type(${i+1})`;

            result.inputs.push(info);
        }
    });

    // Extract all visible buttons
    document.querySelectorAll('button, input[type="submit"], a[role="button"]').forEach((el, i) => {
        if (el.offsetParent !== null) {
            const text = el.textContent.trim().replace(/\\s+/g, ' ').substring(0, 50);
            const info = {
                index: i,
                text: text,
                type: el.type || el.tagName.toLowerCase(),
                id: el.id || null,
                class: el.className || null,
                disabled: el.disabled || false,
                selector: null
            };
            // Build best selector
            if (el.id) info.selector = '#' + el.id;
            else if (el.type === 'submit') info.selector = 'button[type="submit"]';
            else if (el.className && el.className.includes('submit')) info.selector = 'button.submit-btn';
            else info.selector = `button:nth-of-type(${i+1})`;

            result.buttons.push(info);
        }
    });

    // Extract error messages
    document.querySelectorAll('.error, .alert, [role="alert"], .message.error, .input-error').forEach(el => {
        if (el.offsetParent !== null && el.textContent.trim()) {
            result.errors.push({
                text: el.textContent.trim().substring(0, 200),
                selector: el.className ? '.' + el.className.split(' ')[0] : '[role="alert"]'
            });
        }
    });

    // Extract forms
    document.querySelectorAll('form').forEach((form, i) => {
        result.forms.push({
            index: i,
            action: form.action || null,
            method: form.method || 'get',
            id: form.id || null
        });
    });

    return result;
}
"""


def get_system_prompt(task: str) -> str:
    return f"""You are a browser automation agent. You receive structured UI information (not screenshots) and decide what action to take.

## Task
{task}

## Available Actions (respond with JSON only)
- {{"action": "type", "selector": "CSS selector", "text": "text to type"}}
- {{"action": "click", "selector": "CSS selector"}}
- {{"action": "wait", "seconds": 2}}
- {{"action": "done", "result": "description of what was accomplished"}}
- {{"action": "fail", "reason": "why it failed"}}

## Rules
1. Look at the UI structure carefully - you have exact selectors
2. Use the selector field from the UI elements directly
3. For login: first type email, then password, then click submit
4. If you see error messages, report them
5. If URL changed to dashboard/home, you're done
6. Only do ONE action at a time
7. If an input already has value, don't retype

## Response Format
Respond with ONLY a JSON object, no explanation."""


async def extract_ui(context: dict) -> Dict[str, Any]:
    """Extract UI structure from current page"""
    browser = context.get('browser')
    if not browser:
        return {}

    page = browser.page
    try:
        result = await page.evaluate(EXTRACT_UI_SCRIPT)
        return result
    except Exception as e:
        return {"error": str(e)}


async def execute_action(action: dict, context: dict) -> Dict[str, Any]:
    """Execute a single action"""
    action_type = action.get('action')

    if action_type == 'click':
        cls = ModuleRegistry.get('browser.click')
        mod = cls({'selector': action['selector']}, context)
        try:
            await mod.execute()
            return {'ok': True, 'action': 'click', 'selector': action['selector']}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    elif action_type == 'type':
        cls = ModuleRegistry.get('browser.type')
        mod = cls({'selector': action['selector'], 'text': action['text']}, context)
        try:
            await mod.execute()
            return {'ok': True, 'action': 'type', 'selector': action['selector']}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    elif action_type == 'wait':
        await asyncio.sleep(action.get('seconds', 2))
        return {'ok': True, 'action': 'wait'}

    elif action_type in ('done', 'fail'):
        return {'ok': True, 'finished': True, 'result': action}

    return {'ok': False, 'error': f'Unknown action: {action_type}'}


async def ask_ai(ui_structure: dict, task: str, history: list) -> dict:
    """Ask AI for next action based on UI structure"""
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    messages = [
        {"role": "system", "content": get_system_prompt(task)}
    ]

    # Add history
    for h in history[-6:]:
        messages.append({"role": "assistant", "content": json.dumps(h['action'])})
        messages.append({"role": "user", "content": f"Result: {h['result']}"})

    # Add current UI structure
    ui_summary = f"""Current page UI structure:

URL: {ui_structure.get('url', 'unknown')}
Title: {ui_structure.get('title', 'unknown')}

Inputs ({len(ui_structure.get('inputs', []))}):
{json.dumps(ui_structure.get('inputs', []), indent=2, ensure_ascii=False)}

Buttons ({len(ui_structure.get('buttons', []))}):
{json.dumps(ui_structure.get('buttons', []), indent=2, ensure_ascii=False)}

Errors:
{json.dumps(ui_structure.get('errors', []), indent=2, ensure_ascii=False)}

What action should I take next? Respond with JSON only."""

    messages.append({"role": "user", "content": ui_summary})

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # 用 mini 就夠了，因為資料是結構化的
        messages=messages,
        max_tokens=300,
    )

    content = response.choices[0].message.content.strip()

    # Parse JSON
    if content.startswith('```'):
        content = content.split('```')[1]
        if content.startswith('json'):
            content = content[4:]

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"action": "fail", "reason": f"Could not parse AI response: {content}"}


async def run_smart_agent(task: str, start_url: str, max_steps: int = 10):
    """Run the smart agent loop"""
    context = {}
    history = []

    print("=" * 60)
    print(f"Task: {task}")
    print(f"URL: {start_url}")
    print("=" * 60)

    # 1. Launch browser
    print("\n[1] Launching browser...")
    launch_cls = ModuleRegistry.get('browser.launch')
    launch_mod = launch_cls({'headless': False}, context)
    await launch_mod.execute()

    # 2. Go to URL
    print(f"[2] Going to {start_url}...")
    goto_cls = ModuleRegistry.get('browser.goto')
    goto_mod = goto_cls({'url': start_url}, context)
    await goto_mod.execute()

    await asyncio.sleep(2)

    # 3. Agent loop
    for step in range(max_steps):
        print(f"\n--- Step {step + 1} ---")

        # Extract UI structure
        print("Extracting UI structure...")
        ui_structure = await extract_ui(context)
        print(f"  URL: {ui_structure.get('url')}")
        print(f"  Inputs: {len(ui_structure.get('inputs', []))}")
        print(f"  Buttons: {len(ui_structure.get('buttons', []))}")
        print(f"  Errors: {len(ui_structure.get('errors', []))}")

        # Ask AI
        print("Asking AI for next action...")
        action = await ask_ai(ui_structure, task, history)
        print(f"AI says: {json.dumps(action, ensure_ascii=False)}")

        # Check if done
        if action.get('action') in ('done', 'fail'):
            print(f"\n{'=' * 60}")
            print(f"Agent finished: {action}")
            break

        # Execute action
        print(f"Executing: {action.get('action')}...")
        result = await execute_action(action, context)
        print(f"Result: {result}")

        # Record history
        history.append({'action': action, 'result': str(result)})

        # Wait a bit for page to update
        await asyncio.sleep(1)

    print("\nKeeping browser open for 10 seconds...")
    await asyncio.sleep(10)

    # Close
    if 'browser' in context:
        await context['browser'].close()


if __name__ == '__main__':
    task = "Login with email user@example.com and password your_password"
    asyncio.run(run_smart_agent(task, "http://localhost:3000", max_steps=8))
