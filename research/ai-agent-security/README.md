# AI Agent Security

> AI Agent 框架的攻击面与防御研究

Agent 不只是生成文本了——它们在读文件、调接口、执行代码。这意味着 prompt injection 不再只是内容安全问题，而是代码执行原语。这个方向我想持续追踪。

---

## 研究清单

| 编号 | 标题 | 类型 | 状态 |
|------|------|------|------|
| 001 | [Semantic Kernel RCE：当 prompt 变成 shell](./001-semantic-kernel-rce.md) | 漏洞分析 | 完成 |
| 002 | [agent-sink-scanner：Agent 框架危险执行路径静态分析工具](./002-agent-sink-scanner/README.md) | 工具开发 | 完成 |

---

## 关注的攻击面

- Prompt injection → 工具参数污染 → RCE
- 沙箱逃逸（container → host）
- Agent 框架 eval() / 动态执行路径
- 多 Agent 信任传递中的注入传播（ClawWorm 模式）
- MCP 数据源注入（Agentjacking 模式）