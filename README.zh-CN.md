# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

**对，Flyto2 真的能连接机器人。**

当然，也能操作网站、调用 API、处理文件，把中间那些步骤串起来执行。

## 先跑一个看看

比如你想检查一个网页，抓点数据、截几张图，顺便生成报告：

```bash
pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
```

这是可以直接运行的工作流，不用先给 AI 写提示词。浏览器会打开，任务会一步步跑，结果会保存下来。

想看还有什么？

```bash
flyto recipes                 # 看内置流程
flyto modules                 # 看有哪些工具
flyto run your-workflow.yaml  # 跑自己的流程
```

当前 Core 有 **482 个已注册模块**和 **41 个内置流程**。浏览器、API、文件、数据处理、测试都能用。

## 机器人这部分呢？

我们已经通过外部 ROS 2 Adapter，把 Flyto2 接到了**真实的 TurtleBot3** 上。

机器人照常运行 ROS 2 / Nav2；Adapter 负责跟它通信，Flyto2 负责执行软件步骤、记录执行过程。

**机器人不用安装 Flyto2 专用固件，Core 也不用塞马达驱动。**

当前整合版本的完整真机验收还没结束。这不代表所有机器人安装后就能用，但 ROS 2 连接和真机开发已经在做，而且有实际代码。

## 这个仓库到底是什么？

这里是 **flyto-core**，Flyto2 的 Python 执行引擎。

你可以写 YAML 工作流、从 Python 调用、使用本地 HTTP API，或者通过 MCP 把工具交给 AI 客户端：

```bash
pip install flyto-core
python -m core.mcp_server
```

MCP 接上了不等于机器人就能随便动。真实设备的操作权限，还是由可信任的执行主机检查。

不同的软件技术栈，各自放一个 Pack。ROS 2 和其他设备驱动都留在 Core 外面。

## 跑完之后呢？

每一步做了什么，Flyto2 都会留下记录。出了问题，可以检查执行过程，在安全的情况下从检查点恢复。

如果工具回报「完成」，Core 还可以按能力契约检查它提交的证据。不用只看一句成功就猜结果。

---

[网站](https://flyto2.com) · [文档](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [GitHub Issues](https://github.com/flytohub/flyto-core/issues) · [Apache-2.0 许可证](LICENSE)
