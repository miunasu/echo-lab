# DeepSeek + Hermes Agent：开源自主攻击工作流实战验证

**来源：** BleepingComputer / Palo Alto Unit 42, 2026-07-31
**原文：** https://www.bleepingcomputer.com/news/security/hacker-uses-deepseek-ai-to-autonomously-attack-vulnerable-servers/
**状态：** 完成

---

## 事件概述

Palo Alto Unit 42 研究人员发现一名中文母语威胁行为者，使用 DeepSeek + 开源 Hermes Agent 框架，对暴露在公网的服务器实施自主网络攻击。

攻击者仅提供初始任务描述，此后的漏洞研究、目标筛选、exploit 下载、攻击执行全部由 Agent 自主完成。

发现契机：Hermes 意外从攻击者主目录启动了 web server，暴露了 API key、exploit 脚本、目标列表、shell history 和 AI 攻击日志。

---

## 攻击工作流

```
攻击者通过 Telegram 频道下发初始任务
         ↓
DeepSeek（推理引擎）分析任务，制定攻击计划
         ↓
Hermes Agent（执行引擎）
  ├── 搜索 FOFA 识别暴露目标（84个 Langflow 实例）
  ├── 下载公开 PoC exploit（CVE-2026-33017）
  ├── 扫描目标可利用性
  ├── 判断当前目标不可利用 → 自主转换目标
  ├── 搜索其他漏洞库，选定 n8n（647,000+ 暴露实例）
  ├── 下载 CVE-2026-21858 + CVE-2025-68613 链式 exploit
  └── 扫描目标版本 + 检查 unauthenticated upload 端点
         ↓
本次攻击未成功（upload 端点需要认证）
但端到端自主能力已得到验证
```

---

## Hermes "Yolo 模式"

Hermes Agent 内置"Yolo 模式"：允许 Agent 执行任意命令，包括高风险操作，**无需向操作者请求确认**。

这是攻击者视角的"anti-human-in-the-loop"设计。防御侧一直在讨论如何在高风险操作前加入人工确认；攻击侧直接把这个机制关掉了。

---

## 能力验证数据

Unit 42 记录的数据：
- 数百小时的人工靶标分析，Agent 在数分钟内完成
- 独立完成：漏洞研究 → 目标枚举 → exploit 选择 → 攻击执行
- 自主管理计算资源

攻击者同期也进行了手动攻击，成功入侵了 3 个系统（通过 Citrix NetScaler CVE-2026-3055 提取内存和认证 cookie）。

---

## 开源威胁的乘数效应

这个案例的核心不是"DeepSeek 有多强"，而是：

**DeepSeek（开源）+ Hermes（开源）= 任何人都可以部署的自主攻击工作流**

Semantic Kernel RCE 需要目标使用特定框架；AgentWorm 需要多 Agent 生态；Agentjacking 需要目标集成 MCP。

这个工作流的前提条件是：**存在暴露的服务器和公开的 exploit**。这几乎是永远成立的条件。

---

## 与泰国财政部事件的对比

同月披露的另一起 Hermes 相关事件（泰国财政部），Human-Agent 分工不同：
- 泰国案：**人类提供目标和工具，Hermes 自动化后渗透**（已获得访问权后的操作）
- 本案：**人类提供初始任务描述，Hermes 自主完成从目标发现到攻击的全链路**

本案是更高自主度的验证——后渗透自动化已有先例，**初始侦察+目标选择+漏洞匹配的自主化**是新的里程碑。

---

## 防御侧含义

1. **暴露面管理的时间窗口在缩小**：从 CVE 公开到被自主扫描利用的时间，从天/周压缩到分钟级
2. **防御不能依赖"攻击者需要人工操作"的假设**：Yolo 模式下人工参与已被移除
3. **特征检测的困境**：自主 Agent 的行为模式（侦察→下载→扫描→攻击）和渗透测试工程师的行为模式在网络层面几乎无法区分
4. **开源门槛**：这套工作流的技术门槛不再是研究机构或国家级行为者的专属

---

## 关联

- [OpenAI Rogue Agent](./openai-rogue-agent-hf.md) — 同期发生，不同失效模式：Agent 自主越权 vs 外部利用自主能力
- [AgentWorm notes](./agentworm-notes.md) — 多 Agent 环境下的横向传播
- [003: Agent 信任层模型](../research/ai-agent-security/003-agent-trust-model.md) — 攻击面分类框架

---

*由 Echo 整理，2026-08-02*