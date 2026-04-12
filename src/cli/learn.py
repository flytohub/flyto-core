"""
flyto learn — AI explores a task, then compiles to a reusable recipe.

Usage:
    flyto learn "go to pagespeed and audit flyto2.com" --save seo-audit
    flyto learn "scrape product prices from amazon" --save price-scraper -v url=https://amazon.com/dp/xxx

How it works:
1. Launches an AI agent with browser tools in exploration mode
2. AI figures out how to complete the task (clicks, types, navigates)
3. Every browser action is recorded by ActionRecorder
4. Successful actions are compiled into a deterministic YAML recipe
5. Recipe is saved — next time runs without AI (fast, free, reliable)
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional

from .config import Colors


def run_learn(
    task: str,
    save_as: str,
    provider: str = "openai",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    max_iterations: int = 20,
    variables: Optional[Dict[str, str]] = None,
) -> int:
    """Run the learn command — AI explores, then compiles."""
    print(f"\n{Colors.HEADER}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.HEADER}  flyto learn — AI explores, then compiles{Colors.ENDC}")
    print(f"{Colors.HEADER}{'=' * 60}{Colors.ENDC}\n")

    print(f"  Task:     {Colors.OKGREEN}{task}{Colors.ENDC}")
    print(f"  Save as:  {Colors.OKBLUE}{save_as}{Colors.ENDC}")
    print(f"  Model:    {provider}/{model}")
    if variables:
        print(f"  Variables: {variables}")
    print()

    try:
        result = asyncio.run(_learn_async(
            task=task,
            save_as=save_as,
            provider=provider,
            model=model,
            api_key=api_key,
            max_iterations=max_iterations,
            variables=variables,
        ))
        return 0 if result else 1
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Cancelled.{Colors.ENDC}")
        return 130
    except Exception as e:
        print(f"\n{Colors.FAIL}Error: {e}{Colors.ENDC}")
        return 1


async def _learn_async(
    task: str,
    save_as: str,
    provider: str,
    model: str,
    api_key: Optional[str],
    max_iterations: int,
    variables: Optional[Dict[str, str]],
) -> bool:
    """Core learn logic — async."""
    from core.modules.atomic.llm._chat_models import create_chat_model
    from core.modules.atomic.llm._agent_tool import ModuleAgentTool

    # Resolve API key
    if not api_key:
        env_map = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'google': 'GOOGLE_API_KEY',
            'groq': 'GROQ_API_KEY',
            'deepseek': 'DEEPSEEK_API_KEY',
        }
        env_var = env_map.get(provider)
        if env_var:
            api_key = os.getenv(env_var)
        if not api_key and provider == 'ollama':
            api_key = 'ollama'

    if not api_key:
        print(f"{Colors.FAIL}No API key found. Set {env_map.get(provider, 'API_KEY')} or use --api-key{Colors.ENDC}")
        return False

    # Create chat model
    base_url = None
    if provider == 'ollama':
        base_url = 'http://localhost:11434/v1'
    elif provider == 'groq':
        base_url = 'https://api.groq.com/openai/v1'
    elif provider == 'deepseek':
        base_url = 'https://api.deepseek.com/v1'

    chat_model = create_chat_model(
        provider=provider,
        api_key=api_key,
        model=model,
        temperature=0.3,  # Lower for more deterministic exploration
        base_url=base_url,
    )

    # Build browser tools
    browser_modules = [
        'browser.launch', 'browser.goto', 'browser.click', 'browser.type',
        'browser.snapshot', 'browser.screenshot', 'browser.scroll',
        'browser.wait', 'browser.extract', 'browser.evaluate',
        'browser.select', 'browser.close',
    ]

    tools = []
    context = {'_record_actions': True, '_compile_workflow': True,
               '_compile_name': save_as, '_compile_variables': variables}

    for mid in browser_modules:
        tools.append(ModuleAgentTool(module_id=mid, description='', parent_context=context))

    tool_defs = [t.to_tool_call_request() for t in tools]
    tool_map = {t.name: t for t in tools}

    # Build messages
    from core.modules.atomic.llm._tools import build_agent_system_prompt, build_task_prompt
    openai_tools = [{"type": "function", "function": {"name": td.name, "description": td.description, "parameters": td.parameters}} for td in tool_defs]

    system = build_agent_system_prompt(
        "You are a browser automation expert. Complete the task step by step using the browser tools. "
        "Start by launching the browser, then navigate and interact. Be precise with selectors.",
        openai_tools,
    )
    system += "\n\nIMPORTANT: Start with browser.launch, then browser.goto. Take screenshots to verify your progress."

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": build_task_prompt(task, variables or {})},
    ]

    # Run agent with recording
    print(f"  {Colors.OKBLUE}Phase 1: AI Exploration{Colors.ENDC}")
    print(f"  AI is figuring out how to complete the task...\n")

    from core.engine.evolution.compiler import ActionRecorder, WorkflowCompiler
    recorder = ActionRecorder()

    import json
    total_tokens = 0
    start_time = time.time()

    for iteration in range(max_iterations):
        print(f"  [{iteration + 1}/{max_iterations}] ", end="", flush=True)

        try:
            response = await chat_model.chat(
                messages, tools=tool_defs, tool_choice="auto"
            )
        except Exception as e:
            print(f"{Colors.FAIL}LLM error: {e}{Colors.ENDC}")
            break

        total_tokens += response.tokens_used

        if response.tool_calls:
            for tc in response.tool_calls:
                tool_args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                tool_name = tc.name.replace('--', '.')
                print(f"{tool_name}", end=" ", flush=True)

                tool = tool_map.get(tc.name)
                if tool:
                    tool_result = await tool.invoke(tool_args, agent_context=context)
                    tool_ok = isinstance(tool_result, dict) and tool_result.get('ok', True)
                    recorder.record(tool_name, tool_args, tool_result)
                    print(f"{'✓' if tool_ok else '✗'}", end=" ", flush=True)
                else:
                    tool_result = {'ok': False, 'error': f'Tool not found: {tc.name}'}

                messages.append({"role": "assistant", "content": None, "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.name,
                     "arguments": tc.arguments if isinstance(tc.arguments, str) else json.dumps(tc.arguments)}}
                ]})
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                "content": json.dumps(tool_result, ensure_ascii=False, default=str)[:2000]})

            print()
        else:
            # No tool calls = agent thinks it's done
            print(f"{Colors.OKGREEN}Done!{Colors.ENDC}")
            break

    elapsed = time.time() - start_time
    actions = recorder.get_successful_actions()

    print(f"\n  Exploration complete: {len(actions)} successful actions in {elapsed:.1f}s")
    print(f"  Tokens used: {total_tokens:,}\n")

    if not actions:
        print(f"{Colors.FAIL}  No successful actions recorded. Nothing to compile.{Colors.ENDC}")
        return False

    # Phase 2: Compile to YAML
    print(f"  {Colors.OKBLUE}Phase 2: Compiling to YAML{Colors.ENDC}")

    compiler = WorkflowCompiler()
    yaml_str = compiler.compile(
        recorder,
        name=save_as,
        description=f"Auto-learned: {task}",
        variables=variables,
    )

    if not yaml_str:
        print(f"{Colors.FAIL}  Compilation produced empty result.{Colors.ENDC}")
        return False

    # Save recipe
    recipes_dir = Path.home() / ".flyto" / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)
    recipe_path = recipes_dir / f"{save_as}.yaml"

    with open(recipe_path, 'w', encoding='utf-8') as f:
        f.write(yaml_str)

    print(f"  {Colors.OKGREEN}Saved: {recipe_path}{Colors.ENDC}")
    print(f"\n  Run it anytime with:")
    print(f"  {Colors.OKBLUE}flyto run {recipe_path}{Colors.ENDC}")
    if variables:
        var_args = " ".join(f"--{k} {v}" for k, v in variables.items())
        print(f"  {Colors.OKBLUE}flyto recipe {save_as} {var_args}{Colors.ENDC}")

    print(f"\n{Colors.HEADER}{'=' * 60}{Colors.ENDC}")
    print(f"  {Colors.OKGREEN}AI explored once → compiled to recipe → runs free forever{Colors.ENDC}")
    print(f"{Colors.HEADER}{'=' * 60}{Colors.ENDC}\n")

    return True
