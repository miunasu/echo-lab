# 从88%事件率到企业级实施：AI Agent安全的完整路径 (Part 2)

## 企业必须采取的8项行动

### 1. 将AI Agents视为Non-Human Identities (NHIs)

**核心认知**：AI agent安全本质上是身份和访问管理挑战

**行动**：
- **发放短期（ephemeral）凭证**：永远不要给autonomous agents发放持久化、长期API keys。使用scoped、临时tokens，在执行窗口后自动过期
- **实施细粒度权限范围**：对NHIs应用严格的Least Privilege原则。限制agent权限为只读环境，除非写入/执行命令被明确要求且经人类批准
- **隔离执行环境**：确保操作代码库或云基础设施的AI agents在安全的air-gapped沙箱中运行，具有严格的网络出口过滤

### 2. 建立正式的Enterprise AI Governance Framework

**建立**：
- 集中式AI Governance Committee
- 联合IT、Cybersecurity、Legal、Risk、Business Unit leads

**定义**：
- AI ownership（AI所有权）
- Risk classification（风险分类）
- Data governance（数据治理）
- Approval workflows（审批流程）
- Security policies（安全策略）
- Compliance responsibilities（合规责任）
- Audit procedures（审计程序）

**风险分级**：
- **Tier 1**: 面向客户/触及生产数据
- **Tier 3**: 内部行政辅助

### 3. 控制Shadow AI

**策略**：不要禁止AI（会将使用推到地下），而是提供替代方案

**行动**：
- 部署Approved Enterprise AI Portal / Sandbox
- 使用企业级模型，zero-data-retention保证
- 给员工一个安全、受监控的环境
- 满足生产力需求，同时消除未审核的第三方数据泄露

### 4. 实施持续Runtime AI Monitoring

**企业AI工作负载需要专用可观测性栈**

**监控内容**：
- Agent API calls、outbound web requests、database query executions
- System prompts、input/output data、potential prompt-injection vectors
- 异常指标：token使用突增、未批准的文件修改、意外的凭证请求

### 5. 保护整个AI Supply Chain

**认知**：AI模型不是孤立存在的

**依赖**：
- 数据管道
- Vector databases
- API gateways
- 第三方插件
- 开源包

**行动**：
- 对所有端点进行VAPT（Vulnerability Assessment and Penetration Testing）
- 评估第三方AI软件供应商（数据保留策略、模型更新节奏、SOC 2 Type II合规）
- 隔离插件执行：永远不要允许第三方插件在没有通过集中、受监控的安全网关的情况下执行代码或调用外部APIs

### 6. 制定AI-specific Incident Response Playbooks

**问题**：标准网络安全事件响应计划不考虑autonomous agent drift或logic breaches

**行动**：
- 建立明确的"Kill Switch"机制
- 紧急撤销workflows（针对AI agents）
- 允许立即终止agent的OAuth tokens和service account credentials
- 不中断底层业务基础设施

### 7. 加强Identity and Access Management (IAM)

**行动**：
- 实施强大的Role-Based Access Control (RBAC)
- Multi-Factor Authentication (MFA)用于管理覆盖
- Privileged session logging
- **Human-in-the-Loop Overrides**：配置identity provider要求MFA和明确的人类授权，在AI agent执行数据库写入、wire transfers、生产部署之前
- **定期访问审查**：建立自动化的每周访问审查，识别并停用闲置的AI service accounts和未使用的OAuth tokens

### 8. 将Governance转化为持续能力

**认知**：AI模型、能力、威胁战术持续演变

**行动**：
- 定期季度审查（模型更新、vendor risk scores、监管变化、事件日志）
- 将AI风险检查左移：将持续安全测试嵌入CI/CD管道
- 停止将governance视为静态的、一年一次的审计

---

## 90天实施路线图（Infosprint版本）

### Days 1-30: Discovery & Inventory

**核心行动**：
- 审计所有企业AI工具、APIs、模型集成
- 扫描端点以查找未经批准的Shadow AI工具
- 编录所有Non-Human Identities (NHIs)和分配给agents的API keys

**交付物**：Enterprise AI Asset & Risk Inventory

### Days 31-60: Policy & Access Hardening

**核心行动**：
- 将持久keys转换为短期（ephemeral）tokens
- 启动内部"Approved Enterprise AI Sandbox Portal"
- 正式化跨职能AI Governance Committee和风险分级

**交付物**：Enterprise AI Acceptable Use & NHI Policy

### Days 61-90: Runtime Isolation & SOC Integration

**核心行动**：
- 部署持续API活动日志记录和prompt-injection检测
- 对agent containment场景进行red-teaming模拟
- 建立紧急agent撤销"Kill-Switch" playbooks

**交付物**：AI Incident Response Playbook & Audit-Ready Controls