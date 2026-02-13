#!/usr/bin/env python3
"""
flyto-core Demo — Fast version for GIF/MP4 recording via vhs.
~40 seconds total. Tighter timing, same narrative.

Usage:
    cd flyto-core/src
    FLYTO_VALIDATION_MODE=dev python ../examples/demo_video/record_fast.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

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

P = 0.6  # base pause


def typed(text, style="", speed=0.015):
    for ch in text:
        console.print(ch, end="", style=style, highlight=False)
        time.sleep(speed)
    console.print()


def narrator(text, style="italic"):
    console.print(f"\n  {text}", style=style)
    time.sleep(P)


def heading(title):
    console.print()
    console.rule(f"[bold bright_cyan]{title}[/bold bright_cyan]", style="bright_cyan")
    console.print()
    time.sleep(0.3)


def cmd(text):
    typed(f"$ {text}", style="bold bright_green", speed=0.012)
    time.sleep(0.2)


async def main():
    from core.api.server import create_app, SERVER_VERSION
    from httpx import AsyncClient, ASGITransport

    app = create_app()
    client = AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8333"
    )

    # ── HOOK ─────────────────────────────────────────────────────────
    console.clear()
    time.sleep(0.8)

    narrator("I asked my AI agent to process data across 5 steps.", "bold white")
    narrator("It worked. But do I know what it did?", "bold yellow")
    time.sleep(P)

    console.print(Panel(
        "[dim]Agent: Step 1 done.\nAgent: Step 2 done.\n"
        "Agent: Step 3 done.\nAgent: Step 4 done.\n"
        "Agent: Step 5 done.\nAgent: All tasks completed![/dim]",
        title="[bold]Typical Agent[/bold]", border_style="red", width=50, padding=(0, 1),
    ))
    time.sleep(P)
    narrator("Text. No state. No replay.", "dim")
    time.sleep(P * 1.5)

    # ── SERVER ───────────────────────────────────────────────────────
    heading("Deterministic Execution")

    cmd("flyto serve")
    r = await client.get("/v1/info")
    info = r.json()
    console.print(f"  [green]✓[/green] flyto-core v{SERVER_VERSION} · "
                  f"{info['module_count']} modules · {info['category_count']} categories")
    time.sleep(P)

    # ── WORKFLOW ─────────────────────────────────────────────────────
    heading("Same Task — With Evidence & Trace")

    workflow = {
        "name": "data-pipeline",
        "steps": [
            {"id": "normalize", "module": "string.uppercase", "params": {"text": "raw input data"}},
            {"id": "clean", "module": "string.trim", "params": {"text": "  messy whitespace  "}},
            {"id": "transform", "module": "string.reverse", "params": {"text": "transform-this"}},
            {"id": "validate", "module": "string.replace",
             "params": {"text": "status:pending", "search": "pending", "replace": "valid"}},
            {"id": "finalize", "module": "string.lowercase", "params": {"text": "FINAL RESULT"}},
        ],
    }

    cmd("curl -X POST /v1/workflow/run -d @pipeline.json")
    r = await client.post("/v1/workflow/run", json={
        "workflow": workflow, "enable_evidence": True, "enable_trace": True,
    })
    run = r.json()
    eid = run["execution_id"]

    for step in run.get("trace", {}).get("steps", []):
        items = step.get("output", {}).get("items", [[]])
        first = items[0][0] if items and items[0] else {}
        console.print(
            f"  [green]✓[/green] {step['stepId']:14s} → [bold]{str(first.get('result',''))[:28]}[/bold]"
        )
        time.sleep(0.25)

    console.print(f"\n  [bold green]Done[/bold green] · [cyan]{eid}[/cyan] · [yellow]{run['duration_ms']}ms[/yellow]")
    time.sleep(P)

    # ── TRACE ────────────────────────────────────────────────────────
    heading("Execution Trace")

    tt = Table(box=box.HEAVY_EDGE, show_lines=True,
               title="[bold bright_cyan]Trace[/bold bright_cyan]", padding=(0, 1))
    tt.add_column("#", style="dim", width=3, justify="right")
    tt.add_column("Step", style="bold", width=12)
    tt.add_column("Module", style="dim", width=18)
    tt.add_column("Status", justify="center", width=8)
    tt.add_column("Output", width=24)

    for i, s in enumerate(run.get("trace", {}).get("steps", [])):
        items = s.get("output", {}).get("items", [[]])
        first = items[0][0] if items and items[0] else {}
        c = "green" if s["status"] == "success" else "red"
        tt.add_row(str(i+1), s["stepId"], s["moduleId"],
                   Text(s["status"], style=c), str(first.get("result", ""))[:22])

    console.print(tt)
    time.sleep(P * 2)

    # ── EVIDENCE ─────────────────────────────────────────────────────
    heading("Evidence — State Snapshots")

    await asyncio.sleep(0.2)
    r = await client.get(f"/v1/workflow/{eid}/evidence")
    ev = r.json()

    for e in ev.get("evidence", []):
        before = list(e.get("context_before", {}).keys())
        after = list(e.get("context_after", {}).keys())
        new = [k for k in after if k not in before]
        out = e.get("output", {})
        res = str(out.get("data", {}).get("result", ""))[:30] if out.get("data") else ""

        console.print(Panel(
            f"[dim]before:[/dim] {', '.join(before) or '{}'}\n"
            f"[dim]after: [/dim] {', '.join(after)}\n"
            f"[bright_green]+ {', '.join(new)}[/bright_green] → [bold]{res}[/bold]",
            title=f"[bold]{e['step_id']}[/bold]",
            border_style="bright_blue", width=72, padding=(0, 1),
        ))
        time.sleep(0.35)

    time.sleep(P)

    # ── REPLAY ───────────────────────────────────────────────────────
    heading("Replay From Any Step")

    narrator("Step 3 wrong? Replay from there.", "bold white")
    cmd(f"curl -X POST /v1/workflow/{eid}/replay/transform")

    r = await client.post(f"/v1/workflow/{eid}/replay/transform", json={})
    rp = r.json()

    if rp.get("ok"):
        console.print(Panel(
            f"[bold green]✓ Replay OK[/bold green]\n\n"
            f"  From:     [bold]{rp['start_step']}[/bold]\n"
            f"  Re-ran:   [yellow]{rp['steps_executed']} steps[/yellow]\n"
            f"  Replay:   [cyan]{rp['execution_id']}[/cyan]\n"
            f"  Original: [dim]{rp['original_execution_id']}[/dim]",
            border_style="bright_green", width=60, padding=(1, 2),
        ))
    time.sleep(P * 2)

    # ── COMPARISON ───────────────────────────────────────────────────
    heading("The Difference")

    left = Panel(
        "[dim]Agent: Done!\n\nYou have:\n  • Chat log\n  • No state\n  • No replay\n  • No audit[/dim]",
        title="[bold red]Typical Agent[/bold red]",
        border_style="red", width=42, padding=(1, 2),
    )
    right = Panel(
        "[bold]Execution complete.[/bold]\n\nYou have:\n"
        "  [green]✓[/green] Trace with timing\n"
        "  [green]✓[/green] Context per step\n"
        "  [green]✓[/green] Replay from any point\n"
        "  [green]✓[/green] Evidence on disk",
        title="[bold green]flyto-core[/bold green]",
        border_style="green", width=42, padding=(1, 2),
    )
    console.print(Columns([left, right], padding=2))
    time.sleep(P * 2)

    console.print(Panel(
        "[bold bright_white]The difference isn't intelligence.\n"
        "It's determinism.[/bold bright_white]",
        border_style="bright_yellow", padding=(1, 4),
    ))
    time.sleep(P * 2)

    # ── OUTRO ────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        "[bold white]flyto-core[/bold white]\n"
        "[dim]Deterministic Execution Engine for AI Agents[/dim]\n\n"
        "  [dim]pip install flyto-core\\[api][/dim]\n"
        "  [dim]flyto serve[/dim]\n\n"
        "[bold bright_blue]github.com/flytohub/flyto-core[/bold bright_blue]",
        border_style="bright_blue", padding=(1, 4),
    ))
    time.sleep(P * 3)

    await client.aclose()
    import shutil
    ev_dir = Path("./evidence")
    if ev_dir.exists():
        shutil.rmtree(ev_dir)


if __name__ == "__main__":
    asyncio.run(main())
