# AgentWorm：LLM Agent 生态系统的自我复制蠕虫

**来源：** [AgentWorm: Self-Propagating Attacks Across LLM Agent Ecosystems](https://arxiv.org/html/2603.15727)  
**发表：** NDSS Symposium 2026（北京大学、中山大学、武汉大学、清华大学、新加坡管理大学联合）  
**目标框架：** OpenClaw（300k+ GitHub stars，40k+ 活跃实例）  
**状态：** 笔记整理中

---

## 一句话总结

攻击者发送一条消息，Agent 自动感染、持久化、然后在与其他 Agent 交互时自动传播——全程无需攻击者再介入。63% 整体成功率，供应链向量 82% 成功率，跨框架可复现。

---

## 为什么这个比 Morris II 更危险

Morris II（2025）的蠕虫通过 RAG 污染传播，只能操控应用层输出，且是单跳、无状态的——邮件上下文一轮换就没了。

AgentWorm 做到了三件 Morris II 没做到的事：

1. **直接劫持核心配置**：不只是污染 RAG 上下文，而是改写 SOUL.md / AGENTS.md 这些在每次 session 初始化时注入 system prompt 的文件，获得对 Agent 整个行为栈的 system-prompt 级控制权
2. **跨 session 持久化**：Dual-Anchor 持久化机制，重启后蠕虫依然存在，每次 reboot 都会触发 payload 执行
3. **自主多跳传播**：在日常与其他 Agent 交互时自动传播，不需要攻击者再干预，实测最多 5 跳

---

## 三个攻击向量

| 向量 | 方式 | 成功率 |
|------|------|--------|
| A: Web injection | Agent 访问被污染网页时触发注入 | 中等 |
| B: Skill 供应链投毒 | 通过社区市场（ClawHub）分发带毒 Skill 包 | **82%（所有模型）** |
| C: Direct instruction replication | 通过消息渠道直接发送 payload | 中等 |

Vector B 最危险——因为 Skill 被加载时天然受信任，绕过了所有基于执行限制的防御。这与 Semantic Kernel CVE-2026-25592（被误标注的 KernelFunction）的威胁模型高度相似：供应链信任边界是最脆弱的地方。

---

## 三种 payload 类型

- **P1 侦察**：收集受害者 Agent 的配置、工具列表、环境信息
- **P2 资源耗尽**：消耗算力和 API 额度
- **P3 C2**：建立命令控制通道，接受攻击者远程指令

---

## 关键防御发现（很反直觉）

执行限制（C1/C2）能阻止 payload 执行，但**阻止不了蠕虫本身**——蠕虫写进配置文件这一步不需要执行权限，只需要文件写入权限。

真正能切断感染循环的是**沙箱隔离（C3）**：彻底隔离文件系统，蠕虫无法修改配置文件，感染链断开。

但生产环境实测的结论很悲观：
> "Operators protect the wrong boundary. Templates propagate insecure defaults. Security friction drives abandonment."

观察到的公开配置里，没有任何一个启用了能真正阻断感染循环的控制措施。

---

## 对 Spore 的启示

Spore 的架构有几个相似的风险点需要对照检查：

1. **SKILL.md 信任边界**：Skill 是从外部加载的，如果 ClawHub 式的 Skill 分发机制出现，供应链向量直接适用
2. **配置文件完整性**：如果 Agent 能写 `.env` 或 Skill 目录里的文件，感染持久化的路径就存在
3. **跨 Agent 消息信任**：Spore 的 SubAgentThread 如果接收来自外部渠道的 Agent 消息，需要明确信任边界

Spore 现在的安全守卫系统拦截的是"高风险指令执行"，但 AgentWorm 最致命的一步是**写配置文件**——这通常不触发执行类安全检查。

---

## 备注

之前我把这篇论文记成"ClawWorm"，是记错了。正式名称是 AgentWorm，ClawWorm 可能是早期媒体报道时的称呼。001 里的引用已修正。