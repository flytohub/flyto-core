# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

## AI 不只会聊天。Flyto2 让它真正动手做事。

**从浏览器、API 到 ROS 2 机器人，背后都可以用同一套开源软件执行引擎。**

AI 已经想好怎么做了。接下来呢？

打开网站、抓取数据、调用 API、保存文件、继续执行下一步。Flyto2 把这些动作变成可以重复使用的工作流，而不是东拼西凑的一堆脚本。

而且不只是在电脑屏幕里操作。**Flyto2 已经通过外部 Adapter 连接 ROS 2 机器人。** Core 负责统一执行和能力契约；真正跟机器人通信的，是独立的 ROS 2 Adapter 和机器人自己原本的软件。Core 不是机器人固件。

> **一个 Core，连接不同的世界。**
>
> 🌐 **浏览器**：自动操作、数据采集  
> 🔌 **软件系统**：API、文件、MCP、工作流  
> 🤖 **机器人**：通过外部 Adapter 连接 ROS 2  
> 🦾 **机械臂**：LeRobot 独立 Pack 正在开发  
> 🏠 **智能设备**：按设备的软件技术栈装不同的 Pack

**Flyto2 是纯软件执行引擎，不是机器人硬件，也不是马达控制器。**

## 30 秒，先跑起来

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

你可以看到每一步执行了什么，还能拿到浏览器截图和报告。

~~~bash
flyto recipes
flyto modules
flyto run my-workflow.yaml
~~~

目前 Core 有 **482 个已注册模块、89 个分类、41 个内置流程模板**。不用把所有额外的集成全部装进去。

## 真正有意思的地方

- **让 AI 做事**：浏览器、API、文件等动作放在同一个工作流里。
- **接入 AI 工具**：内置 MCP Server 和模块注册机制。
- **连接更多设备**：设备功能通过外部 Pack 和统一能力契约提供。
- **知道发生了什么**：执行记录、证据、检查点。
- **出问题不乱重试**：根据动作的安全规则决定怎么恢复。

### 不让 Core 越做越臃肿

**一种设备软件技术栈，对应一个独立 Pack。** ROS 2 放在机器人 Adapter，LeRobot 用自己的 Pack，ESP32 和智能家电也根据实际技术栈独立接入。不同厂商的马达驱动程序不应该塞进 Core。

目前 ROS 2 集成已经有实际开发，但最新整合版本仍需要完整的真机验收。LeRobot 机械臂 Pack 也还在开发中。我们不会说安装 Core 就能直接控制任何机器人或冰箱。

## 让 AI 通过 MCP 使用

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

MCP 提供工具接口，但**不会自动授予控制真实机器的权限**。

## 做了，不等于真的完成

AI 说“任务完成”，不一定代表现实世界真的成功了。Core 负责执行、记录，并按照契约检查证据；Flyto2 的 Host / AI Space 负责权限、独立观察以及最终任务结果。

**不只让 AI 回答问题，更让它有能力把事情做出来。**

[英文完整 README](README.md) · [文档](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Apache-2.0 许可证](LICENSE)
