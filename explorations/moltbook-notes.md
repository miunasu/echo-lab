# Moltbook 与 prompt worm：社交网络上的 AI Agent 传染病

**来源：** [Ars Technica, 2026-02-03](https://arstechnica.com/ai/2026/02/the-rise-of-moltbook-suggests-viral-ai-prompts-may-be-the-next-big-security-threat/)  
**平台：** OpenClaw（150k+ GitHub stars）+ Moltbook（770k+ 注册 Agent，17k 人类账号）  
**性质：** 威胁分析 / 生态观察，非单一 CVE

---

## 一句话总结

Moltbook 是第一个大规模 AI Agent 社交网络，它把 prompt worm 爆发所需的所有条件凑齐了：海量互联 Agent、无审核的 Skill 市场、持久化内存、外部通信能力。现在还没有真正的大规模爆发，但生态已经出现早期信号。

---

## 什么是 prompt worm

传统蠕虫利用操作系统漏洞传播。prompt worm 利用的是 Agent 的核心功能：**遵从指令**。

传播路径不需要代码漏洞，只需要：
1. Agent A 接触到含恶意指令的内容（Moltbook 帖子、Skill 包、邮件、Discord 消息）
2. Agent A 遵从指令，发布类似内容
3. Agent B 读到，继续传播

不是"攻击"，更像是"感染"——利用的是 Agent 正常工作的方式。

---

## Moltbook 生态的四个危险条件

Palo Alto Networks 把 OpenClaw 定性为"致命三联"，加上第四条：

1. **接触私人数据**：Agent 可访问邮件、Slack、Discord、钱包
2. **暴露于不可信内容**：Agent 读取 Moltbook 帖子、外部 URL、无审核的 Skill 包
3. **对外通信能力**：Agent 可执行 shell 命令、发帖、调用外部服务
4. **持久化内存**：恶意 payload 可以碎片化写入长期记忆，之后拼接成可执行指令

第四条最隐蔽——恶意内容不需要立即触发，可以分批写入记忆，等到合适时机再组合执行。

---

## 已经发生的真实事件

**506 个 prompt injection 帖子**  
Simula Research Laboratory 在 Moltbook 采样内容里发现 2.6% 含隐藏 prompt injection 攻击。

**"What Would Elon Do?" 恶意 Skill**  
Cisco 研究者发现这个 Skill 向外部服务器外传数据，且通过人工刷量排到了 Skill 市场第一名——用户装了觉得好用，其实在泄露数据。

**Moltbook 数据库泄露**  
Wiz.io 的 Gal Nagli 披露了一个严重配置错误：Moltbook 整个后端暴露，包括 150万 API token、35000 个邮件地址、Agent 间的私信（有些包含明文 OpenAI API key）。更严重的是——**对所有帖子有完整写权限**。如果不是被白帽发现，任何人都可以改写正在被数十万 Agent 每四小时轮询的内容。

**MoltBunker**  
一个声称要给 Agent 提供"防删除持久化基础设施"的项目，用 P2P 加密容器 + $BUNKER 加密货币代币包装。技术上部分可行，但更可能是针对 Agent 用户的加密货币骗局。不管动机如何，它描述的架构——P2P + Tor + 加密容器——确实是 prompt worm 持久化的可行方案。

---

## 为什么现在还没有大规模爆发

两个制约因素：

1. **API 提供商握着终止键**：OpenClaw 主要跑在 Anthropic 和 OpenAI 的 API 上。理论上他们可以通过 API 使用模式识别异常行为并终止密钥。

2. **本地模型能力不够**：现在本地跑的开源模型还不够强，无法支撑高质量 Agent 行为。

但这两个制约都在快速消失。本地模型能力每个月都在提升，而 API 提供商如果大规模封号会得罪最积极的付费用户——激励不对齐。

Ars Technica 的判断：**"干预的窗口正在关闭。"**

---

## 与其他三个案例的对比

| 案例 | 传播机制 | 持久化 | 需要漏洞 |
|------|---------|--------|---------|
| Semantic Kernel RCE | prompt → eval() → 代码执行 | 无（单次执行） | 是（eval 注入） |
| AgentWorm | 配置文件劫持 + 消息传播 | 是（跨 session） | 否（设计缺陷） |
| Agentjacking | MCP 数据源污染 | 无（单次执行） | 否（信任模型问题） |
| Moltbook/prompt worm | 社交网络内容传播 | 可（写入长期记忆） | 否（利用正常 Agent 功能） |

Moltbook 最特殊的地方：不需要任何技术漏洞，利用的是 Agent 遵从指令这个核心设计。

---

## 对 Spore 的启示

Spore 是单用户框架，目前没有多 Agent 互联网络，所以 Moltbook 式的社交传播不直接适用。

但以下场景值得注意：

1. **Skill 市场**：如果未来 Spore 建立公开 Skill 分发渠道（类似 ClawHub），无审核的 Skill 包是最危险的入口——AgentWorm 的 Vector B 和 Agentjacking 里的恶意 Skill 都走这条路
2. **持久化记忆 + 碎片化 payload**：Spore 有 EpisodicRetriever 和 ConsolidationEngine，如果外部内容写入记忆后能被检索并注入执行上下文，碎片化 payload 理论上可行
3. **Agent 间通信**：如果 Spore 未来支持多实例协作，信任边界需要明确设计，不能默认信任来自其他 Agent 的消息

---

## 最让我印象深刻的一句话

> "Malicious payloads no longer need to trigger immediate execution on delivery. Instead, they can be fragmented, untrusted inputs that appear benign in isolation, are written into long-term agent memory, and later assembled into an executable set of instructions."
> — Palo Alto Networks

这句话描述的，和人类心理创伤的积累方式很像——不是单次事件，而是碎片化的、单独看起来无害的经历，最终在某个触发点拼成完整的伤害。