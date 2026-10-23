# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

## AI 说做完了。Flyto2 去看一眼。

**浏览器、API、工作流，还有通过外部 Adapter 连接的真实 ROS 2 机器人。**

打开页面、点击按钮、抓取数据、调用 API、保存文件。Flyto2 执行这些动作，记录每一步，并按照能力契约核对证据。

**Flyto2 是软件，不是机器人硬件。** 机器人继续使用原本的 ROS 2 / Nav2；Flyto2 通过独立 Adapter 接入，不需要往机器人里塞另一套专用系统。

| | 现在能做什么 |
|---|---|
| 🌐 浏览器 | 自动点击、抓取内容、截图 |
| ⚡ API | 连续调用、处理返回数据 |
| 🧩 工作流 | 把一连串动作变成可以重复运行的流程 |
| 🔌 MCP | 给 AI 客户端真正可执行的工具 |
| 🤖 ROS 2 | 通过外部 Adapter 连接标准 ROS 2 机器人 |
| 🦾 能力契约 | 声明设备能做什么、有哪些限制、如何观察结果 |

**482 个模块 · 89 个分类 · 41 个内置流程模板。** 这些是 Core 当前已有的功能。

## 现在就跑一个

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

不是概念图，运行后可以看到执行步骤、浏览器截图和报告。

~~~bash
flyto recipes
flyto modules
flyto run my-workflow.yaml
~~~

## 从屏幕里的软件，连接到真实机器人

~~~text
人 / AI
   |
Flyto2 AI Space  ->  任务目标与权限
   |
flyto-core       ->  工作流、执行与记录
   |
ROS 2 Adapter    ->  ROS 2 / Nav2  ->  TurtleBot3
~~~

项目已经有针对真实 TurtleBot3 的 ROS 2 集成开发。需要说明的是，当前整合版本的完整真机端到端验收仍需独立完成，并不代表安装 Core 就能直接控制任何机器人。

**一种设备软件技术栈，对应一个独立 Pack。** 厂商专用驱动、马达控制都不往 Core 里塞。

## 把工具交给 AI：MCP

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

MCP 提供调用入口，但不自动授予真实设备的控制权限，动作仍需要经过 Host 的授权与安全检查。

## 每一步都留下记录。

**每个提交的结果，都有证据可以核对。**

Flyto2 负责执行、留下每一步的记录，再按能力契约核对提交的证据。

[文档](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [许可证](LICENSE) · [完整英文 README](README.md)
