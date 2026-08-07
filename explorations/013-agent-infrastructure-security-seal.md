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

## 策略复用与治理：从临时配置到可审查的环境蓝图

S.E.A.L. 框架提供了技术实现指南，但每次临时搭环境、手动配置权限、事后才发现"忘了限制出站网络"——这不是可持续的安全模式。

### Sandbox Kits：可复用的安全策略

**核心思想**：把批准的基础镜像、语言运行时、挂载范围、允许的工具、网络策略、凭证路径编码成"可审查的环境蓝图"（Sandbox Kit）。

Kit 应该像 release input 一样被版本控制、审查、指定负责人。不是每次临时决定"这个 Agent 能访问什么"，而是：
- 选择预定义的 Kit（如 `python-safe-kit`、`node-readonly-kit`）
- Kit 已经包含了所有安全约束（只读 FS、egress-only、短期凭证、资源配额）
- 需要更多权限？提交 PR 修改 Kit 定义，经过审查后合并

**Docker 的 Sandbox Kits 框架**（2026 年推出）：
- 平台团队发布批准的 Kit 用于常见工作流
- 将高风险能力排除在默认环境外（如 `/var/run/docker.sock` 挂载、privileged mode）
- Kit 能否锁定到审查过的版本，授予过多权限时可回滚

### MCP 工具调用网关：独立的 Choke Point

即使 Agent 执行被沙箱隔离，如果它能调用外部工具（发邮件、查 CRM、开工单、改云状态、读客户数据），沙箱边界只是一半的故事。

**工具调用需要自己的认证、授权、日志、撤销机制**：
- 不应该把工具 API key 直接塞进 Agent 环境变量
- 应该通过 MCP 网关中介所有外部操作：
  - Agent 调用工具 → 请求发到 MCP 网关
  - 网关检查权限（这个 Agent 会话能调用这个工具吗？参数合法吗？）
  - 网关记录日志（谁、什么时候、调用了什么工具、带什么参数）
  - 网关转发请求到实际工具，返回结果

---

## 硬件级隔离：最后一道防线

### 为什么容器和进程沙箱不够

**核心问题**：进程级沙箱和容器级隔离都共享宿主内核——一个内核 CVE 就能逃逸。

> "Most AI agent 'sandboxes' are actually litterboxes — they look contained but they're full of 💩."  
> — Ann W., Edera 团队

**技术风险**：
- **进程级沙箱**（如 Python subprocess、Node.js child_process）：共享内核、共享网络栈、共享文件系统命名空间
- **容器级隔离**（Docker、containerd）：虽然有 namespace 和 cgroup，但依然共享内核。2024-2026 年发现的多个容器逃逸 CVE（如 CVE-2024-21626 runc 逃逸）证明容器边界不可信

**真正的沙箱**：每个 Agent 需要自己的内核、自己的 VM、硬件级隔离——被攻陷的 Agent 无法触碰集群中的其他任何东西。

### microVM 技术栈

#### Firecracker（AWS 开源）
- 专为 serverless 设计的轻量级 VM monitor
- 基于 KVM，但去掉了大部分 QEMU 设备模拟（只保留 virtio-net、virtio-block）
- 冷启动 < 125ms，内存开销 < 5MB
- AWS Lambda 和 Fargate 的底层技术

#### Kata Containers（OpenStack 基金会）
- 让容器跑在独立 VM 里，但对用户透明（仍用 Docker/K8s API）
- 每个 pod 跑在独立的轻量级 VM（基于 QEMU/Firecracker/Cloud Hypervisor）
- 兼容 OCI 标准，可直接替换 runc

#### gVisor（Google 开源）
- 用户空间内核（user-space kernel），拦截所有系统调用
- 不是完整 VM，但提供独立的内核接口
- 性能介于容器和 VM 之间

### 真实产品案例

#### Edera（YC S24）
- 提供 SaaS 化的 VM 级 Agent 沙箱
- 两行 K8s 配置，不需要改 Agent 镜像，底层用 VM 隔离
- 支持多租户场景（每个租户的 Agent 跑在独立 VM 里）

#### IronCurtain（Niels Provos 开源）
- 单一强制执行 choke point
- 把"宪法"编译成确定性策略规则（不依赖 LLM 分类器）
- 凭证完全不在 Agent 可达范围内：容器里是假密钥，代理层交换真密钥
- 开源地址：[github.com/google/iron-curtain](https://github.com/google/iron-curtain)

#### Vercel Sandbox / Cloudflare Sandboxed
- SaaS 化的开发环境 / 沙箱
- 底层可能用 Edera/Firecracker 之类的 VM hypervisor 保证多租户隔离
- 用户只需要写代码，隔离由平台自动处理

### 成本与收益

**VM 级隔离的代价**：
- 启动延迟增加（Firecracker 虽然 < 125ms，但仍比容器慢）
- 内存开销增加（每个 VM 需要独立内核）
- 运维复杂度增加（需要管理 hypervisor、VM 生命周期）

**但收益是**：
- 内核 CVE 无法逃逸到 host
- 一个 Agent 被攻陷不会影响其他 Agent
- 符合多租户安全要求（SaaS 场景必需）

**何时需要硬件级隔离**：
- 多租户场景（不同客户的 Agent 跑在同一集群）
- 高风险操作（Agent 能修改生产状态、访问敏感数据）
- 合规要求（金融、医疗等行业）

**何时容器够用**：
- 单租户场景（只有自己团队的 Agent）
- Agent 权限已严格限制（只读操作、短期凭证、egress-only）
- 配合 S.E.A.L. 框架使用，风险可控

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
| Sandbox Kit | 环境能否阻止挂载工作区外的写入？ |
| Egress-only | 出站网络访问是默认拒绝还是至少显式限定范围？ |
| Token TTL | 密钥是短期的且仅为任务注入？ |
| Separation | 确认决策代码和执行 runner 分离 |
| Read-only FS | 尽可能为 worker 基础镜像挂载只读根文件系统 |
| No privileged | 禁用 Docker/K8s 所有 Agent 工作负载的 privileged mode |
| Tool Gateway | 平台能否记录哪些工具调用被哪个 Agent 会话发起？ |
| Kit Versioning | Kit 能否锁定到审查过的版本并在授予过多权限时回滚？ |
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

**总结**：S.E.A.L. 框架提供了一套可落地的 Agent 基础设施防御模式，填补了 prompt injection 防御（CaMeL/FIDES）与实际部署安全之间的空白。容器隔离不够，需要执行平面分离、仅出站网络、短期作用域凭证、资源暴露限制四层协同防御。配合 Sandbox Kits 策略复用、MCP 工具网关、以及 microVM 硬件级隔离，构成多层次防御体系。对于部署自主 Agent 的团队来说，这是从"容器里跑就安全"幻觉中醒来的必读文章。