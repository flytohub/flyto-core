<h1 align="center">Flyto2</h1>

<p align="center">
  <strong>AI can talk. Flyto2 lets it do things.</strong><br />
  One open-source software engine for real actions — from browser tabs and APIs to ROS 2 robots through external adapters.
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/flyto-core/"><img src="https://img.shields.io/pypi/v/flyto-core" alt="PyPI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10+" /></a>
</p>

<!-- mcp-name: io.github.flytohub/flyto-core -->

## An AI agent needs more than a chat box

Your AI has a plan. Now what?

**Open a website. Grab some data. Call an API. Save a file. Run the next step.**
Flyto2 makes these actions into reusable workflows instead of a pile of one-off scripts.

And it doesn't stop at software screens. **Flyto2 already connects to ROS 2 robots using external adapters.** Core supplies the common execution and capability-contract layer; the robotics package talks to the robot's own ROS 2 stack. The robot is not running Flyto2 firmware.

> **One core. Different worlds.**
>
> 🌐 **Web** — browser automation and data extraction  
> 🔌 **Software** — APIs, files, MCP tools and workflows  
> 🤖 **Robotics** — ROS 2 through separate, host-approved adapters  
> 🦾 **Manipulation** — LeRobot arm integration is being built as a separate pack  
> 🏠 **IoT** — device-specific packs can connect smart equipment without bloating Core

This is a **software project**, not a robot model, a motor controller, or an all-in-one hardware SDK.

## See it move

<p align="center">
  <img src="demo/flyto-core-demo.gif" alt="Flyto2 running a browser and API workflow with visible steps" width="760" />
</p>

*The recording above demonstrates a software workflow, not a physical-robot run.*

## Run something in 30 seconds

Install the browser extra and try a real workflow:

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

You'll get a step-by-step execution trace, browser captures and a report. Want to see what's built in?

~~~bash
flyto recipes
flyto modules
~~~

Or run your own YAML workflow:

~~~bash
flyto run my-workflow.yaml
~~~

**482 registry-backed modules, 89 catalog categories and 41 packaged recipes** in the current Core inventory. You don't have to install every optional integration to use the engine.

## The stuff that makes it powerful

| You want to… | Flyto2 gives you… |
| --- | --- |
| Turn an idea into actual software actions | A workflow engine with typed, reusable steps |
| Let an agent use existing tools | An MCP server and a module registry |
| Connect another tool or device stack | Installable packs and host-bound capability contracts |
| Understand what ran | Structured traces and execution evidence |
| Continue after a failure | Checkpoints and replay controls, subject to each action's safety rules |
| Keep physical actions under control | Declared limits, explicit host authority and safe-stop contracts |

**Important:** a command returning “OK” isn't automatically proof that the real-world task succeeded. Core records execution and can judge declared evidence; a Flyto2 host / AI Space coordinates permissions, independent observations and the final mission verdict.

## One engine, not one giant dependency tree

~~~text
User or AI agent
      |
      v
Flyto2 host / AI Space   <-- goal, choice of tools, approvals
      |
      v
Flyto2              <-- workflow, contracts, execution, trace
      |
      +--> Browser / APIs / files / MCP
      |
      +--> Approved device pack
               |
               +--> ROS 2 adapter  --> ROS 2 robot
               +--> LeRobot pack   --> robot arm (integration in progress)
               +--> IoT adapter    --> smart device
~~~

**Here's the rule:** one device software stack, one separate pack.

ROS 2 stays in the robotics adapter stack. LeRobot gets its own pack. An ESP32 integration or another smart appliance gets the pack appropriate to its actual software stack. **No vendor-specific motor code goes into Flyto2.**

An adapter declares what a machine can do and what it needs. The trusted execution host decides whether that action is allowed. **Discovery never equals permission.** A model's confidence isn't a safety guarantee, and a failed or unknown physical action isn't blindly retried.

### What is ready — and what still needs proof

- **Core software:** workflows, browser/API/file modules, MCP interface, capability contracts, execution traces, recovery tools and adapter-pack mechanisms are implemented.
- **ROS 2 connection:** Flyto2 uses an external ROS 2 robotics stack with real TurtleBot3 development work. This is **not** a built-in ROS 2 implementation inside Core, and end-to-end physical acceptance of the current integration is still pending.
- **Robot arms:** a portable pick-and-place contract example exists; the AM-ARM200 / LeRobot adapter is a separate work in progress. Don't treat the example as a tested arm driver.
- **Smart devices:** optional adapters and integrations live outside Core. Compatibility and safety have to be tested per actual device.

We would rather show the boundary clearly than pretend every robot or refrigerator works out of the box.

## Plug it into your tools

### MCP — give your coding agent a workflow toolbox

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

You can configure that command as an MCP server in a compatible client. MCP exposes software capabilities; it does **not** grant physical-motion permission by itself.

### Python — call a module

~~~python
import asyncio
from core.modules.registry import ModuleRegistry

async def main():
    result = await ModuleRegistry.execute(
        "string.reverse",
        params={"text": "Hello, world!"},
        context={},
    )
    print(result)

asyncio.run(main())
~~~

### HTTP — run an execution service

~~~bash
python -m pip install "flyto-core[api]"
flyto serve
~~~

The local execution API runs on 127.0.0.1:8333 by default. Protect the service and configure authentication before exposing it beyond a trusted environment.

## Why build on this?

Most demos stop at “the AI said it did it.”

We care about the next step: **what actually ran, what changed, and what you can safely do next.** That's why trace, replay, bounded capabilities and evidence exist. They're not the headline; they're how we make the headline real.

Flyto2 stays useful on its own. [Flyto2](https://flyto2.com) adds goal planning, AI Spaces and cross-device coordination around that execution layer.

**Build agents that do things. Then make those things real.**

[Website](https://flyto2.com) · [Documentation](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Issues](https://github.com/flytohub/flyto-core/issues) · [YouTube](https://www.youtube.com/@Flyto2)

## Security and licensing

Physical actions must be authorized by a trusted host and backed by the actual device's local safety controls. A ROS 2 adapter, external provider or workflow is not a substitute for emergency-stop hardware or site safety validation. No blanket certification or universal device compatibility is claimed.

To report a vulnerability, use [GitHub Security Advisories](https://github.com/flytohub/flyto-core/security/advisories).

[Apache License 2.0](LICENSE) — free to use, modify and build on.
