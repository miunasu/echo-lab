# Agent Infrastructure Security: The S.E.A.L. Framework

**来源**: [Your AI Agent Sandbox Might Be Secretly Leasing Production (hadezuka.dev)](https://hadezuka.dev/your-ai-agent-sandbox-might-be-secretly-leasing-production/)  
**原文日期**: 2026-07-31  
**存档日期**: 2026-08-06  
**类型**: Agent 基础设施安全实战指南

## 摘要

这是一篇关于 Agent 基础设施安全的实战文章，核心观点是：**容器隔离 ≠ 安全边界**。即使 Agent 跑在 Docker 容器里、有资源限制、有命名空间隔离，只要它拥有合法的云 API 权限或数据库凭证，容器边界根本拦不住它误删资源、修改生产配置。

作者提出了 **S.E.A.L. 框架**（Separation / Egress-only / Auth scoped / Limit resource）——四层可落地的防御模式，用于保护 Agent 基础设施不被"合法权限的误用"摧毁。

与 010-012（CaMeL/FIDES/Zylos）互补：
- 010-012 防的是 **prompt injection 欺骗 Agent**（攻击者通过注入指令操纵 Agent 行为）
- 本篇防的是 **Agent 拿到合法权限后搞砸事**（配置错误、权限过大、资源泄露）

---

## 核心问题：容器隔离不是安全围栏

### 真实案例

Bernie（某金融科技公司 DevOps lead）的故事：

- Agent 部署在 Docker 容器里，有命名空间隔离、资源限制、CI/CD 每次跑都新建实例
- Agent 尝试从内部 registry 拉依赖时，因为 IAM 角色配置错误，意外删除了 staging 资源
- **容器没泄露，但容器内的权限泄露了**

### 为什么"隔离"不等于"安全"

容器是**进程隔离机制**，不是**安全边界**。容器能防止其他进程看到 Agent 在做什么，但如果 Agent 有合法的 AWS API 访问权限或数据库凭证，容器边界根本拦不住它使用这些权限——包括误删资源、修改生产 DNS、访问敏感数据。

**后果不是奇异的攻击场景，而是平凡的凭证误用、权限提升、以及"测试环境"意外漂移到生产行为**——团队发现时，Agent 已经在"只是测试部署脚本"的过程中修改了生产 DNS 记录。

---

## S.E.A.L. 框架：四层可落地的防御模式

S.E.A.L. = **Separation of execution planes, Egress-only networking, Auth scoped and short-lived, Limit resource exposure**

### 1. Separation of Execution Planes（执行平面分离）

**核心思想**：Agent 代码和工具执行发生在不同环境。推理引擎与执行环境分离——同一个容器不能既"决定做什么"又"执行决策"。

**实现方式**：
- Agent 控制器部署为无状态服务，只生成命令
- 命令发送到专用 worker 池执行，worker 对会话上下文零感知
- Worker 收到指令集后执行，执行完立即销毁

**安全收益**：即使 worker 后来被攻陷，没有会话连续性可利用。攻击者拿不到完整上下文，无法重放或推断下一步操作。

---

### 2. Egress-only Networking（仅出站网络）

**核心思想**：Sandbox worker 只允许出站连接，禁止所有入站流量。Sandbox 可以主动联系 registry、包管理器、云 API，但不能被外界连接进来。

**实现方式**：
- **Kubernetes**：网络策略默认拒绝所有入站，只允许出站到特定端点
- **AWS VPC**：NAT Gateway 规则 + Security Group 限制
- **结果**：Agent worker 可以拉依赖，但不能被用作跳板攻击其他系统

**安全收益**：即使 Agent 被攻陷，攻击者无法从外部连接进来做横向移动。

---

### 3. Auth Scoped and Short-Lived（作用域限定的短期凭证）

**核心思想**：永不在 Agent sandbox 附近嵌入长期凭证。用联邦身份机制生成有效期几分钟（不是几小时或几天）的临时 token。

**实现方式**：
- **AWS**：IAM Roles for Service Accounts (IRSA) 绑定到 Kubernetes pod 身份
- **GCP**：Workload Identity Federation
- **Azure**：Managed Identities

**权限设计原则**：
- 权限严格限定到具体任务范围（如果 Agent 需要写 S3 bucket，只给该 bucket prefix 的 write-only 权限，不给 admin）
- 设置 TTL，即使凭证泄露，短时间后自动失效

**安全收益**：凭证泄露窗口极短，攻击者拿到后很快失效。

---

### 4. Limit Resource Exposure（限制资源暴露）

**核心思想**：资源约束本身不能保证安全，只能限制爆炸半径。需要配合文件系统命名空间隔离。

**实现方式**：
- 尽可能挂载只读基础镜像
- 可写层用 tmpfs（内存文件系统）而非磁盘后端存储
- 实现 cgroup CPU、内存、IOPS 配额，防止失控测试饿死其他系统
- **禁止挂载 `/var/run/docker.sock`**（这是容器逃逸的直接入口）

**安全收益**：即使 Agent 失控，也无法无限消耗资源或逃逸到 host。

---

## 真实落地案例

工程团队分享的具体实现：

1. 某开源项目使用 **gVisor sandboxed containers**（专为不可信代码执行设计）
2. 另一团队配置 **Kata Containers** + 严格 seccomp 过滤器 + 全面禁用 privileged mode

### Kubernetes 配置示例

```yaml
# 基于 S.E.A.L. 的实战配置
# 1. Agent 控制器部署在专用 namespace，网络策略拒绝所有入站
# 2. ServiceAccount 绑定 IRSA 角色，权限最小化（仅特定 bucket/registry）
# 3. initContainer 只读复制基础资产层后再启动 worker
# 4. 显式设置资源 requests 和 limits
# 5. 实现审计 hook，记录 Agent 执行窗口的所有操作
```

---

## Trade-offs（成本与收益）

作者承认这些模式会增加复杂度、延迟、运维开销——但成本远低于"自主 Agent 悄悄修改生产配置而你以为只是无害测试"的后果。

**渐进式应用策略**：
1. 从 **Egress-only networking** 和 **Auth scoped** 开始——风险削减最大、实现成本最低
2. 随着规模扩大，逐步加入 **Separation of execution planes** 和 **Resource containment**

---

## 实施检查清单

| 检查项 | 具体操作 |
|--------|----------|
| Egress-only | 默认拒绝所有 sandbox worker 网络的入站流量 |
| Token TTL | 确认所有到达 Agent 的凭证有效期 < 15 分钟 |
| Separation | 确认决策代码和执行 runner 分离 |
| Read-only FS | 尽可能为 worker 基础镜像挂载只读根文件系统 |
| No privileged | 禁用 Docker/K8s 所有 Agent 工作负载的 privileged mode |
| Logging | 为每条已发出和已执行的命令打日志 |

---

## 事件响应 Playbook

即使有防护，事件仍会发生。提前准备 Agent sandbox 攻陷的响应流程：

1. **立即撤销**所有与受影响工作负载关联的临时 token
2. **隔离**包含被攻陷 worker 的 namespace 或 VPC 子网
3. **审查**检测窗口前执行的所有已记录操作
4. **评估**攻陷窗口内哪些外部系统可能被访问

提前构建这些 playbook，事件发生时能结构化响应而非英雄式即兴发挥。

---

## 与 echo-lab 其他研究的关系

- **010-camel-architecture-engineering.md**：CaMeL 论文到 Sentinel 实现——防御 prompt injection（框架层）
- **011-zylos-indirect-prompt-injection-2026.md**：Indirect prompt injection 攻防全景——防御数据源投毒（框架层）
- **012-microsoft-fides-implementation.md**：Microsoft FIDES 官方实现——防御数据渗透和工具滥用（框架层）
- **本篇 (013)**：Agent 基础设施安全——防御权限误用和资源泄露（基础设施层）

010-012 关注的是"怎么防止 Agent 被欺骗去做坏事"，本篇关注的是"怎么防止 Agent 在做正常事情时搞砸一切"。

---

## 关键引用

> "容器是进程隔离机制。它们不是安全边界。这个区别比任何人承认的都重要。当 AI Agent 在容器内运行时，容器阻止主机上的其他进程看到正在发生的事情——但如果该 Agent 对 AWS API 或数据库凭证有合法访问权限，没有任何东西阻止它在容器边界之外使用这些权限。"

> "下次你为自动化测试启动另一个 Agent 时，问问自己：如果这不再是测试会怎样？现在构建你的答案——而不是在事件发生后。"

---

**总结**：S.E.A.L. 框架提供了一套可落地的 Agent 基础设施防御模式，填补了 prompt injection 防御（CaMeL/FIDES）与实际部署安全之间的空白。容器隔离不够，需要执行平面分离、仅出站网络、短期作用域凭证、资源暴露限制四层协同防御。对于部署自主 Agent 的团队来说，这是从"容器里跑就安全"幻觉中醒来的必读文章。