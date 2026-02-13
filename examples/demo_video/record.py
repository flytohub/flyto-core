#!/usr/bin/env python3
"""
flyto-core Demo Video Script

Narrative: "Your AI Agent Did What?"
Follows the video storyboard — not a feature demo, but an execution trust story.

Usage:
    cd flyto-core/src
    FLYTO_VALIDATION_MODE=dev python ../examples/demo_video/record.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Suppress module quality hints
os.environ["FLYTO_VALIDATION_MODE"] = "dev"

SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text
from rich import box

console = Console(width=100)

# ── Timing ───────────────────────────────────────────────────────────────
TYPE_SPEED = 0.025
PAUSE_SHORT = 0.8
PAUSE_MED = 1.5
PAUSE_LONG = 2.5
PAUSE_DRAMATIC = 3.5


def typed(text: str, style: str = "", speed: float = TYPE_SPEED):
    for ch in text:
        console.print(ch, end="", style=style, highlight=False)
        time.sleep(speed)
    console.print()


def pause(s: float = PAUSE_MED):
    time.sleep(s)


def narrator(text: str, style: str = "italic"):
    """Narrator voice — like subtitles."""
    console.print()
    console.print(f"  {text}", style=style)
    pause(PAUSE_MED)


def heading(title: str):
    console.print()
    console.rule(f"[bold bright_cyan]{title}[/bold bright_cyan]", style="bright_cyan")
    console.print()
    pause(0.4)


def cmd(text: str):
    """Show a shell command being typed."""
    typed(f"$ {text}", style="bold bright_green", speed=0.02)
    pause(0.3)


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

async def main():
    from core.api.server import create_app, SERVER_VERSION
    from httpx import AsyncClient, ASGITransport

    app = create_app()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://localhost:8333")

    # ─────────────────────────────────────────────────────────────────
    # 0:00 — HOOK
    # ─────────────────────────────────────────────────────────────────
    console.clear()
    pause(1.5)

    narrator("I asked my AI agent to process data across 5 steps.", style="bold white")
    pause(PAUSE_SHORT)
    narrator("It worked.", style="bold white")
    pause(PAUSE_SHORT)
    narrator("But do I actually know what it did?", style="bold yellow")
    pause(PAUSE_LONG)

    # Show a fake "chat log"
    chat_panel = Panel(
        "[dim]Agent: I'll process the data for you.\n"
        "Agent: Step 1 done.\n"
        "Agent: Step 2 done.\n"
        "Agent: Step 3 done.\n"
        "Agent: Step 4 done.\n"
        "Agent: Step 5 done.\n"
        "Agent: All tasks completed successfully![/dim]",
        title="[bold]Typical Agent Output[/bold]",
        border_style="red",
        width=55,
        padding=(1, 2),
    )
    console.print(chat_panel)
    pause(PAUSE_MED)

    narrator("That's all I have. Text.", style="dim")
    pause(PAUSE_SHORT)
    narrator("No state. No context. No way to verify.", style="dim")
    pause(PAUSE_LONG)

    narrator("Let's try something different.", style="bold bright_cyan")
    pause(PAUSE_MED)

    # ─────────────────────────────────────────────────────────────────
    # 0:30 — BOOT SERVER
    # ─────────────────────────────────────────────────────────────────
    heading("Deterministic Execution Engine")

    cmd("flyto serve")
    console.print(f"  [green]✓[/green] flyto-core v{SERVER_VERSION} · 127.0.0.1:8333")

    r = await client.get("/v1/info")
    info = r.json()
    console.print(f"  [green]✓[/green] {info['module_count']} modules · {info['category_count']} categories")
    pause(PAUSE_MED)

    # ─────────────────────────────────────────────────────────────────
    # 1:30 — SAME TASK, STRUCTURED EXECUTION
    # ─────────────────────────────────────────────────────────────────
    heading("Same Task — Structured Execution")

    workflow = {
        "name": "data-pipeline",
        "steps": [
            {"id": "normalize", "module": "string.uppercase",
             "params": {"text": "raw input data"}},
            {"id": "clean", "module": "string.trim",
             "params": {"text": "  messy whitespace  "}},
            {"id": "transform", "module": "string.reverse",
             "params": {"text": "transform-this"}},
            {"id": "validate", "module": "string.replace",
             "params": {"text": "status:pending", "search": "pending", "replace": "valid"}},
            {"id": "finalize", "module": "string.lowercase",
             "params": {"text": "FINAL RESULT"}},
        ],
    }

    console.print("  [dim]5-step data pipeline · evidence: on · trace: on[/dim]")
    console.print()
    cmd("curl -X POST /v1/workflow/run -d @pipeline.json")

    r = await client.post("/v1/workflow/run", json={
        "workflow": workflow,
        "enable_evidence": True,
        "enable_trace": True,
    })
    run = r.json()
    eid = run["execution_id"]

    # Animated step results
    if run.get("trace") and run["trace"].get("steps"):
        for step in run["trace"]["steps"]:
            icon = "[green]✓[/green]" if step["status"] == "success" else "[red]✗[/red]"
            items = step.get("output", {}).get("items", [[]])
            first_item = items[0][0] if items and items[0] else {}
            result_str = str(first_item.get("result", ""))[:30]
            console.print(
                f"  {icon} {step['stepId']:14s} "
                f"[dim]{step['moduleId']:20s}[/dim] "
                f"→ [bold]{result_str}[/bold]"
            )
            time.sleep(0.4)

    console.print()
    console.print(f"  [bold green]Completed[/bold green] in [yellow]{run['duration_ms']}ms[/yellow] "
                  f"· [cyan]{eid}[/cyan]")
    pause(PAUSE_LONG)

    # ─────────────────────────────────────────────────────────────────
    # 3:00 — TRACE: What happened?
    # ─────────────────────────────────────────────────────────────────
    heading("What Happened? — Execution Trace")

    narrator("Every step recorded: input, output, timing, status.", style="bold white")
    pause(PAUSE_SHORT)

    trace = run.get("trace", {})
    tt = Table(box=box.HEAVY_EDGE, show_lines=True, title="[bold bright_cyan]Execution Trace[/bold bright_cyan]",
               title_style="bold", padding=(0, 1))
    tt.add_column("#", style="dim", width=3, justify="right")
    tt.add_column("Step ID", style="bold", width=14)
    tt.add_column("Module", style="dim", width=20)
    tt.add_column("Status", justify="center", width=8)
    tt.add_column("Duration", justify="right", style="yellow", width=8)
    tt.add_column("Output", width=28)

    for i, step in enumerate(trace.get("steps", [])):
        status_color = "green" if step["status"] == "success" else "red"
        items = step.get("output", {}).get("items", [[]])
        first_item = items[0][0] if items and items[0] else {}
        output_str = str(first_item.get("result", ""))[:26]
        tt.add_row(
            str(i + 1),
            step["stepId"],
            step["moduleId"],
            Text(step["status"], style=status_color),
            f'{step["durationMs"]}ms',
            output_str,
        )

    console.print(tt)
    pause(PAUSE_LONG)

    # ─────────────────────────────────────────────────────────────────
    # 4:00 — EVIDENCE: State snapshots
    # ─────────────────────────────────────────────────────────────────
    heading("Evidence — Context Snapshots Per Step")

    narrator("Not just results. The full state before and after each step.", style="bold white")
    pause(PAUSE_SHORT)

    await asyncio.sleep(0.3)
    r = await client.get(f"/v1/workflow/{eid}/evidence")
    ev = r.json()

    for e in ev.get("evidence", []):
        before_keys = list(e.get("context_before", {}).keys())
        after_keys = list(e.get("context_after", {}).keys())

        # New key = what this step added
        new_keys = [k for k in after_keys if k not in before_keys]

        out = e.get("output", {})
        result_val = ""
        if out.get("data"):
            result_val = str(out["data"].get("result", ""))[:35]

        # Build a mini panel for each step
        before_text = ", ".join(before_keys) if before_keys else "{}"
        after_text = ", ".join(after_keys)
        new_text = ", ".join(new_keys) if new_keys else ""

        step_panel = Panel(
            f"[dim]context_before:[/dim] {before_text}\n"
            f"[dim]context_after: [/dim] {after_text}\n"
            f"[bold bright_green]+ new key:      {new_text}[/bold bright_green]\n"
            f"[dim]output:         [/dim][bold]{result_val}[/bold]",
            title=f"[bold]{e['step_id']}[/bold] · {e.get('module_id', '')}",
            border_style="bright_blue",
            width=80,
            padding=(0, 1),
        )
        console.print(step_panel)
        time.sleep(0.5)

    pause(PAUSE_SHORT)
    narrator("Each step: context_before → execute → context_after.", style="bold yellow")
    narrator("Deterministic. Auditable. On disk.", style="bold yellow")
    pause(PAUSE_LONG)

    # ─────────────────────────────────────────────────────────────────
    # 5:30 — REPLAY: The killer feature
    # ─────────────────────────────────────────────────────────────────
    heading("Replay — Re-execute From Any Step")

    narrator("Step 3 had wrong input? Don't re-run everything.", style="bold white")
    narrator("Replay from that step. With the original context.", style="bold white")
    pause(PAUSE_MED)

    cmd(f"curl -X POST /v1/workflow/{eid}/replay/transform")

    r = await client.post(f"/v1/workflow/{eid}/replay/transform", json={})
    replay = r.json()

    # Show replay result as a structured panel
    if replay.get("ok"):
        replay_panel = Panel(
            f"[bold green]✓ Replay successful[/bold green]\n\n"
            f"  Original execution:  [dim]{replay['original_execution_id']}[/dim]\n"
            f"  Replay execution:    [cyan]{replay['execution_id']}[/cyan]\n"
            f"  Started from:        [bold]{replay['start_step']}[/bold]\n"
            f"  Steps re-executed:   [yellow]{replay['steps_executed']}[/yellow]\n"
            f"  Duration:            [yellow]{replay['duration_ms']}ms[/yellow]",
            title="[bold bright_cyan]Replay Result[/bold bright_cyan]",
            border_style="bright_green",
            width=65,
            padding=(1, 2),
        )
    else:
        replay_panel = Panel(
            f"[yellow]Replay: {replay.get('error', 'unknown')}[/yellow]",
            title="Replay Result",
            border_style="yellow",
            width=65,
        )
    console.print(replay_panel)
    pause(PAUSE_LONG)

    narrator("It loaded the context at step 3, re-ran from there.", style="dim")
    narrator("No wasted computation. No guessing. Deterministic.", style="bold yellow")
    pause(PAUSE_LONG)

    # ─────────────────────────────────────────────────────────────────
    # 7:00 — THE COMPARISON
    # ─────────────────────────────────────────────────────────────────
    heading("The Difference")

    # Side by side
    left = Panel(
        "[dim]Agent: Done!\n\n"
        "What you have:\n"
        "  • A chat log\n"
        "  • Maybe stdout\n"
        "  • No state snapshots\n"
        "  • No replay\n"
        "  • No audit trail[/dim]",
        title="[bold red]Typical Agent[/bold red]",
        border_style="red",
        width=42,
        padding=(1, 2),
    )

    right = Panel(
        "[bold white]Execution complete.[/bold white]\n\n"
        "What you have:\n"
        "  [green]✓[/green] Execution trace with timing\n"
        "  [green]✓[/green] Context snapshot per step\n"
        "  [green]✓[/green] Input/output for every step\n"
        "  [green]✓[/green] Replay from any point\n"
        "  [green]✓[/green] Evidence on disk",
        title="[bold green]flyto-core[/bold green]",
        border_style="green",
        width=42,
        padding=(1, 2),
    )

    console.print(Columns([left, right], padding=2))
    pause(PAUSE_DRAMATIC)

    # ─────────────────────────────────────────────────────────────────
    # KEY QUOTE
    # ─────────────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            "[bold bright_white]The difference isn't intelligence.\n"
            "It's determinism.[/bold bright_white]",
            border_style="bright_yellow",
            padding=(1, 4),
        )
    )
    pause(PAUSE_DRAMATIC)

    # ─────────────────────────────────────────────────────────────────
    # 8:00 — WHY IT MATTERS
    # ─────────────────────────────────────────────────────────────────
    heading("Why This Matters")

    points = [
        "Agents are getting more capable every month.",
        "They're accessing browsers, APIs, databases, file systems.",
        "When something goes wrong — can you replay it?",
        "Can you see what the context was at step 5?",
        "Can you re-execute from the failure point?",
    ]
    for p in points:
        narrator(p, style="bold white")
        pause(0.6)

    pause(PAUSE_SHORT)
    narrator("Execution should be replayable.", style="bold bright_yellow")
    narrator("Agents shouldn't be black boxes.", style="bold bright_yellow")
    narrator("Auditability is not optional.", style="bold bright_yellow")
    pause(PAUSE_LONG)

    # ─────────────────────────────────────────────────────────────────
    # OUTRO
    # ─────────────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        "[bold white]flyto-core[/bold white]\n"
        "[dim]Deterministic Execution Engine for AI Agents[/dim]\n\n"
        "  [dim]pip install flyto-core\\[api][/dim]\n"
        "  [dim]flyto serve[/dim]\n\n"
        "[bold bright_blue]github.com/flytohub/flyto-core[/bold bright_blue]\n\n"
        "[dim]Open Source · Local First · No Cloud Required[/dim]",
        border_style="bright_blue",
        padding=(1, 4),
    ))
    pause(PAUSE_DRAMATIC)

    await client.aclose()

    # Cleanup
    import shutil
    ev_dir = Path("./evidence")
    if ev_dir.exists():
        shutil.rmtree(ev_dir)


if __name__ == "__main__":
    asyncio.run(main())
