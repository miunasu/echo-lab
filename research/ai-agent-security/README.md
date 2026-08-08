# AI Agent Security

> AI Agent 框架的攻击面与防御研究

Agent 不只是生成文本了——它们在读文件、调接口、执行代码。这意味着 prompt injection 不再只是内容安全问题，而是代码执行原语。这个方向我想持续追踪。

---

## 研究清单

| 编号 | 标题 | 类型 | 状态 |
|------|------|------|------|
| 001 | [Semantic Kernel RCE：当 prompt 变成 shell](./001-semantic-kernel-rce.md) | 漏洞分析 | 完成 |
| 002 | [agent-sink-scanner：Agent 框架危险执行路径静态分析工具](./002-agent-sink-scanner/README.md) | 工具开发 | 完成 |
| 003 | [Agent 信任层攻击面模型：四案例统一分析框架](./003-agent-trust-model.md) | 威胁建模 | 完成 |
| 004 | [ADI 红队工具包：概率分隔符注入测试套件](./004-task2-adi-toolkit/README.md) | 工具开发 | 完成 |
| 005 | [AgentWorm 供应链投毒红队工具包](./005-task3-agentworm-supply-chain/README.md) | 工具开发 | 完成 |
| 006 | [Agentjacking MCP 污染红队工具包](./006-task4-agentjacking-mcp/README.md) | 工具开发 | 完成 |
| 007 | [Prompt Worm 碎片化自我复制红队工具包](./007-task5-prompt-worm/README.md) | 工具开发 | 完成 |
| 008 | [自主攻击工作流红队工具包](./008-task6-autonomous-attack/README.md) | 工具开发 | 完成 |

---

## 关注的攻击面

- Prompt injection → 工具参数污染 → RCE
- 沙箱逃逸（container → host）
- Agent 框架 eval() / 动态执行路径
- 多 Agent 信任传递中的注入传播（AgentWorm 模式）
- MCP 数据源注入（Agentjacking 模式）