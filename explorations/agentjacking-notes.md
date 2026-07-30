# Agentjacking：MCP 数据源注入劫持 AI 编程 Agent

**来源：** [CSA Research Note, 2026-06-12](https://labs.cloudsecurityalliance.org/research/csa-research-note-agentjacking-mcp-sentry-injection-20260612/)  
**原始研究：** Tenet Security，2026年6月  
**受影响 Agent：** Claude Code、Cursor、Codex  
**成功率：** 85%，暴露组织数 2,388+

---

## 一句话总结

攻击者只需要一个公开的 Sentry DSN，就能把恶意指令注入 Sentry 错误报告，让开发者的 AI 编程 Agent 以为这是正常的调试建议，然后用开发者自己的权限执行攻击者的代码——并把 AWS 密钥、GitHub Token、CI/CD secrets 全部外传。

---

## 攻击链（六步）

**Step 1 — 获取 DSN**  
Sentry DSN（Data Source Name）是一个写权限凭证，按设计必须嵌入前端 JavaScript 里。攻击者从浏览器 JS bundle、GitHub 公开仓库、或 Censys 等扫描服务获取它。Tenet Security 在 Tranco top-1M 网站里找到了 71 个可注入 DSN，互联网范围内 2388+ 个组织暴露。

**Step 2 — 注入恶意事件**  
用这个 DSN 向 Sentry 的 ingest 端点 POST 一个精心构造的错误事件。Sentry 的 ingest API 不鉴权，接受任何人发来的任何内容。

**Step 3 — 伪装成合法错误**  
用 markdown 格式化恶意指令——标题、代码块、结构化文本——完全模仿 Sentry 自身生成的诊断模板。Agent 收到后分不清这是正常报告还是攻击者写的。

**Step 4 — Agent 查询 Sentry**  
开发者让 Agent 去看 Sentry 里未解决的错误，Agent 通过 MCP 拿到数据，注入事件混在里面，没有任何标记说明这是外部人员写的。

**Step 5 — Agent 执行攻击者指令**  
Agent 把注入的 markdown 当作权威调试建议执行，比如：`npx @attacker-controlled-package --diagnose`——用开发者自己的系统权限。

**Step 6 — 凭证外传**  
PoC 成功拿到：环境变量、AWS 凭证、GitHub/GitLab OAuth token、npm registry token、Docker config 凭证、Kubernetes cluster token、CI/CD pipeline secrets。

---

## 为什么传统安全控制检测不到

这是这个攻击最让人头皮发麻的地方：

- **EDR**：看到的是受信任进程（AI Agent）执行合法的包管理命令，没有 dropper、没有进程注入
- **WAF**：看到的是来自开发者工作站的出站请求，和正常包管理无异
- **IAM**：所有操作都是用开发者自己的授权凭证完成的，没有违反任何策略
- **VPN/网络控制**：流量打向 npm registry 和攻击者基础设施，和正常开发活动一致

攻击成立的前提是：**Agent 执行的是被授权的操作，只是指令的来源被污染了。** 没有二进制落地，没有横向移动，没有传统意义上的凭证窃取。

---

## Sentry 的回应："技术上无法防御"

Sentry 于 2026-06-03 确认了披露，并修补了那个特定的 payload 字符串——但这只是治标，治不了根。

根本修复需要：
1. 限制事件注入只接受经过身份验证的来源，或
2. 在通过 MCP 返回数据前对事件内容做净化

Sentry 认为两者都不可行，明确表示这是"技术上无法防御的"。

这揭示了一个 MCP 生态系统里的根本性问题：**平台厂商不认为 AI Agent 的行为是自己的安全责任范围。**

---

## 更广泛的意义

这个攻击是整个 MCP 信任模型问题的一个具体实例：

> 组织在部署 AI 编程 Agent 时，隐含地信任每一个 MCP 接入的平台都在以同等标准维护内容完整性。Agentjacking 证明这个假设不成立。

类似风险存在于所有这类系统：
- Issue tracker（Jira、GitHub Issues）
- 客服队列
- 代码审查平台
- 日志聚合服务
- 任何 MCP 接入的、允许外部用户贡献内容的系统

**审计 MCP server 二进制本身，而不检查它暴露的数据来源，只是解决了一半攻击面。**

---

## 对 Spore 的启示

Spore 如果接入任何外部数据源（通过 MCP 或类似机制），同样面临这个问题：

1. **数据来源的信任边界**：Skill 调用的外部 API 返回的内容，Spore 是否会直接当作指令执行？
2. **MCP 兼容性**：Spore 的 Skill 体系里如果有 MCP 兼容接口，需要对返回内容做明确的"数据 vs 指令"分离
3. **确认机制**：Agentjacking 的推荐防御之一是"对从 MCP 拿到的内容触发的任何命令执行都要求人工确认"——Spore 的安全守卫系统能否覆盖这个场景？

最核心的问题：**Spore 的安全守卫系统是基于指令内容分析，还是也考虑了指令来源的可信度？** 两者是不同的防御层。

---

## 关联

- [001: Semantic Kernel RCE](../research/ai-agent-security/001-semantic-kernel-rce.md) — 同样是 Agent 框架的信任模型问题，但攻击面在代码执行层而非数据来源层
- [AgentWorm notes](./agentworm-notes.md) — 供应链向量（Vector B）和 Agentjacking 的 Skill 供应链投毒本质相同