<h1 align="center">Flyto2</h1>

<p align="center">
  <strong>Yep, it talks to a real robot.</strong><br>
  It also opens websites, calls APIs, works with files, and runs the steps in between.
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.ja.md">日本語</a> · <a href="README.ko.md">한국어</a> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.es.md">Español</a> · <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/flyto-core/"><img src="https://img.shields.io/pypi/v/flyto-core" alt="PyPI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10+" /></a>
</p>

<!-- mcp-name: io.github.flytohub/flyto-core -->

## Try something.

Say you want to check a website, grab screenshots, collect some data, and save a report.

Run this:

```bash
pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
```

That's a real workflow. No agent prompt needed. It opens a browser, runs the steps, and saves the results.

Want to poke around?

```bash
flyto recipes                 # see the built-in workflows
flyto modules                 # browse the tools
flyto run your-workflow.yaml  # run your own
```

There are **482 registered modules** and **41 built-in recipes** in the current Core inventory. Browser stuff, APIs, files, data, tests, and plenty more. Use what you need.

## And about that robot…

We're already connecting Flyto2 to a **real TurtleBot3 using ROS 2**.

The robot runs its normal ROS 2 / Nav2 stack. A separate adapter talks to it. Flyto2 handles the software steps and their execution records.

**No custom Flyto2 firmware on the robot. No motor drivers crammed into this repo.**

This isn't a claim that every robot is plug-and-play. The current combined setup still needs its full end-to-end hardware sign-off. But the ROS 2 adapter and real-robot development are already here.

## So what's in this repo?

This is **flyto-core**, the Python execution engine behind Flyto2.

You can call it from Python, run YAML workflows, use its local HTTP API, or hook it into an AI client through MCP.

```bash
pip install flyto-core
python -m core.mcp_server
```

Your agent gets access to Core's tools. Moving a physical device still requires a trusted host to approve the action.

**Different device software stack? Different pack.** That's how ROS 2 and other integrations stay separate without turning Core into a giant pile of device drivers.

## How do I know what actually happened?

This part matters.

When a workflow runs, Flyto2 keeps a record of each step. If something fails, you can inspect the run and use checkpoints or replay where it's safe to do so.

And if a tool says “done”? Core can check the evidence it reports against the action's contract. It doesn't just throw away the trail once the command returns.

That's it. Run something, see what happened, build the next thing.

---

[Website](https://flyto2.com) · [Documentation](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [YouTube](https://www.youtube.com/@Flyto2) · [Issues](https://github.com/flytohub/flyto-core/issues)

<sub>Flyto2 is the product. <code>flyto-core</code> is the Python package. Licensed under <a href="LICENSE">Apache 2.0</a>. Security reports: <a href="https://github.com/flytohub/flyto-core/security/advisories">GitHub advisories</a>.</sub>
