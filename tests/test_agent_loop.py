#!/usr/bin/env python3
"""
真正的 AI Agent Loop

每一步：
1. 截圖當前頁面
2. 發給 AI 看
3. AI 決定下一個動作
4. 執行動作
5. 重複直到完成
"""
import asyncio
import base64
import os
import sys
import json
from pathlib import Path

os.environ["FLYTO_VSCODE_LOCAL_MODE"] = "true"
sys.path.insert(0, 'src')

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import openai

# Import browser modules
import core.modules.atomic.browser.launch
import core.modules.atomic.browser.goto
import core.modules.atomic.browser.type
import core.modules.atomic.browser.click
import core.modules.atomic.browser.screenshot
import core.modules.atomic.browser.extract

from core.modules.registry import ModuleRegistry


def get_agent_prompt(task: str) -> str:
    return f"""You are a browser automation agent. You can see screenshots of a webpage and decide what action to take next.

Available actions (respond with JSON):
- {{"action": "click", "selector": "CSS selector"}}
- {{"action": "type", "selector": "CSS selector", "text": "text to type"}}
- {{"action": "wait", "seconds": 2}}
- {{"action": "done", "result": "description of what was accomplished"}}
- {{"action": "fail", "reason": "why it failed"}}

Rules:
1. Look at the screenshot carefully before deciding
2. Use specific CSS selectors based on what you see
3. If a button says "Sign In", use selector like 'button:has-text("Sign In")' or the actual class/id
4. If you see an error message, report it
5. After successful login, you should see a different page - then respond with "done"
6. Only do ONE action at a time

Current task: {task}
"""


async def take_screenshot(context: dict) -> str:
    """Take screenshot and return base64."""
    screenshot_cls = ModuleRegistry.get('browser.screenshot')
    mod = screenshot_cls({'path': '/tmp/agent_screenshot.png', 'full_page': False}, context)
    await mod.execute()

    with open('/tmp/agent_screenshot.png', 'rb') as f:
        return base64.standard_b64encode(f.read()).decode()


async def execute_action(action: dict, context: dict) -> dict:
    """Execute a single action."""
    action_type = action.get('action')

    if action_type == 'click':
        cls = ModuleRegistry.get('browser.click')
        mod = cls({'selector': action['selector']}, context)
        return await mod.execute()

    elif action_type == 'type':
        cls = ModuleRegistry.get('browser.type')
        mod = cls({'selector': action['selector'], 'text': action['text']}, context)
        return await mod.execute()

    elif action_type == 'wait':
        await asyncio.sleep(action.get('seconds', 2))
        return {'ok': True}

    elif action_type in ('done', 'fail'):
        return {'ok': True, 'finished': True, 'result': action}

    return {'ok': False, 'error': f'Unknown action: {action_type}'}


async def ask_ai_for_next_action(screenshot_b64: str, task: str, history: list) -> dict:
    """Send screenshot to AI and get next action."""
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    messages = [
        {"role": "system", "content": get_agent_prompt(task)}
    ]

    # Add history
    for h in history[-6:]:  # Last 6 actions
        messages.append({"role": "assistant", "content": json.dumps(h['action'])})
        messages.append({"role": "user", "content": f"Result: {h['result']}"})

    # Add current screenshot
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": "Here is the current screenshot. What should I do next? Respond with JSON only."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
        ]
    })

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=500,
    )

    content = response.choices[0].message.content.strip()

    # Parse JSON from response
    if content.startswith('```'):
        content = content.split('```')[1]
        if content.startswith('json'):
            content = content[4:]

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"action": "fail", "reason": f"Could not parse AI response: {content}"}


async def run_agent(task: str, start_url: str, max_steps: int = 15):
    """Run the agent loop."""
    context = {}
    history = []

    # 1. Launch browser
    print("Launching browser...")
    launch_cls = ModuleRegistry.get('browser.launch')
    launch_mod = launch_cls({'headless': False}, context)
    await launch_mod.execute()

    # 2. Go to URL
    print(f"Going to {start_url}...")
    goto_cls = ModuleRegistry.get('browser.goto')
    goto_mod = goto_cls({'url': start_url}, context)
    await goto_mod.execute()

    await asyncio.sleep(2)  # Wait for page load

    # 3. Agent loop
    for step in range(max_steps):
        print(f"\n--- Step {step + 1} ---")

        # Take screenshot
        print("Taking screenshot...")
        screenshot_b64 = await take_screenshot(context)

        # Ask AI
        print("Asking AI for next action...")
        action = await ask_ai_for_next_action(screenshot_b64, task, history)
        print(f"AI says: {json.dumps(action, ensure_ascii=False)}")

        # Check if done
        if action.get('action') in ('done', 'fail'):
            print(f"\n{'='*50}")
            print(f"Agent finished: {action}")
            break

        # Execute action
        print(f"Executing: {action['action']}...")
        result = await execute_action(action, context)
        print(f"Result: {result}")

        # Record history
        history.append({'action': action, 'result': str(result)})

        # Wait a bit
        await asyncio.sleep(1)

    print("\nKeeping browser open for 10 seconds...")
    await asyncio.sleep(10)

    # Close
    if 'browser' in context:
        await context['browser'].close()


if __name__ == '__main__':
    task = "Login with email user@example.com and password your_password"
    asyncio.run(run_agent(task, "http://localhost:3000", max_steps=10))
