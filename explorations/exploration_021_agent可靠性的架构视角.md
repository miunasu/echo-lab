# Exploration 021: Agent可靠性的架构视角

**日期**: 2026-08-18  
**来源**: HackerNoon - "Why Agentic AI Systems Fail in Production"

---

## 核心论点

**可靠性是架构问题，不是模型问题**

> "reliability is an architecture problem, not a model problem"

Agent demo在理想条件下表现完美，但生产环境从不提供这种奢侈：
- 环境是受控的 → 生产环境充满变数
- API按预期响应 → 实际会超时、限流、失败
- context很小 → 实际会持续增长、污染
- 工具总是可用 → 实际会间歇性故障
- 会话很短 → 实际可能持续数周
- 交互可预测 → 实际充满边缘情况

**可靠性无法后补，必须从一开始就设计进去**

> "reliability cannot be retrofitted efficiently. It has to be designed from the very beginning"

把orchestration当作application logic写，就会得到脆弱的系统。
把orchestration当作infrastructure设计，才能得到可靠的系统。

**Infrastructure的特征**：
- 高度容错
- 可观测
- 可恢复

---

## 四大结构性失败模式

### 1. Non-Deterministic Tool Chaining（非确定性工具链）

**表现**：同样的输入，95%的时间成功，5%的时间失败或产生不同结果

**根源**：模型推理的微小变化导致不同的执行路径

**数学惩罚**：
- 单步99%可靠性，5步后约95%
- 单步99%可靠性，20步后约82%
- 工作流越长，整体可靠性指数级下降

**教训**：可靠性必须从整体系统角度考虑，而非单个组件

---

### 2. Context Window Mismanagement（context窗口管理失当）

**表现**：会话变长后，agent看起来"变笨了"，但底层模型没变

**根源**：context污染
- 历史交互累积
- 冗余context填充
- 检索管道返回越来越不相关的内容
- 降级是渐进的，难以察觉

**类比**：就像分布式计算中的内存管理问题——无法有效管理状态的系统，性能必然降级，无论计算能力多强

---

### 3. Lack of Observability（缺乏可观测性）

**表现**：能知道agent失败了，但不知道为什么

**根源**：只有最终输出的可见性，缺少：
- 中间推理步骤
- 检索结果
- 工具交互
- 状态转换

**后果**：事后分析时没有关键执行数据

**解决方案**：借鉴分布式系统的observability框架

---

### 4. Retrying as a Reliability Mechanism（把重试当可靠性机制）

**反模式**：
- 工具调用失败？重试
- 检索结果差？重试
- agent执行错误？重试

**问题**：
- 重试本身没错，但**不能是唯一的可靠性机制**
- 掩盖设计缺陷
- 增加延迟和成本
- 无法理解失败原因

---

## 生产就绪的三个标准

一个agent不是因为benchmark表现好就"生产就绪"。
**生产就绪是因为它的失败是可预测的**。

### 1. 系统只能以有限的方式失败
- 失败模式是枚举的、已知的
- 不会出现"从未见过的失败"

### 2. 失败是可观测和可理解的
- 每个失败都有清晰的诊断信息
- 可以追溯到具体的执行步骤

### 3. 失败是可恢复的
- 从checkpoint恢复
- 隔离失败组件
- 降级而不是崩溃

---

## 关键架构原则

### 原则1: 频繁checkpoint state

**借鉴**：分布式ML训练（ZeRO、FSDP）假设失败会发生
- 持续checkpoint训练状态
- 恢复是架构的一部分

**应用到agent**：
- 持久化中间状态
- 从已知checkpoint恢复
- 大幅降低失败的成本和影响

---

### 原则2: 分离planning、execution、evaluation

**常见错误**：在单个工作流组件中混合推理、执行、验证

**正确设计**：
- **Planning层**：生成策略
- **Execution层**：执行动作
- **Evaluation层**：验证结果

**收益**：
- 各层独立扩展
- 各层独立监控
- 各层独立恢复

---

### 原则3: 选择正确的计算模型

**不是所有agent都需要维护状态**

- **Actor-based架构**：适合需要持续状态和通信的agent
- **Task-based架构**：适合短生命周期、隔离的工作负载

**关键**：架构应该跟随工作负载的本质，而非某个框架的炒作

---

### 原则4: Observability是设计约束，不是运维关注点

**必须监控**：
- 每步执行延迟
- 工具调用成功率
- 检索质量指标
- Context使用模式
- Agent决策路径
- 外部依赖性能
- 失败趋势分类

**关键**：结构化日志，使聚合和关联成为可能

**类比**：在数千个GPU上训练，没有GPU利用率、通信开销、内存行为的可见性，就无法优化。Agent系统面临同样的现实。

---

### 原则5: RAG层是可靠性依赖

**常见误解**：RAG是质量改进工具

**真相**：RAG是可靠性依赖

**最阴险的检索失败**：静默失败
- Agent继续工作
- 响应继续生成
- 什么都没崩溃
- 但context质量已经降级
- 系统表面正常，但在做错误决策

**三大隐患**：

1. **Chunking策略**
   - chunk大小影响context表示和检索
   - 错误的chunking策略会碎片化context或增加噪音

2. **Embedding drift**
   - Embedding模型在演进
   - 知识库在变化
   - 曾经好的检索质量会悄悄变差，无人察觉

3. **Index staleness**
   - 检索系统的时效性取决于索引
   - 过时的索引引入信息缺口，对agent不可见
   - 类似分布式系统中的缓存一致性问题：基础设施运行正常，但服务的是过时信息

**解决方案**：生产级RAG架构必须引入降级机制
- 检索质量下降时，系统必须反应：
  - 暴露不确定性
  - 收集额外证据
  - 降低自动化级别
- 而不是盲目运行

---

## 生产就绪检查清单

**benchmark无法回答的问题**：

- [ ] 工作流能从checkpoint恢复吗？
- [ ] 检索失败如何表现？
- [ ] agent推理有什么遥测选项？
- [ ] 外部依赖如何隔离？
- [ ] 内存损坏时会发生什么？
- [ ] 状态如何持久化？
- [ ] 级联失败如何遏制？

这些问题对运维可行性的重要性，远超benchmark的增量改进。

---

## Context Engineering Matrix：context设计的四象限框架

**来源补充**: ThinkDeeply.ai - "The Context Engineering Matrix"

HackerNoon那篇从宏观架构角度解释了"为什么可靠性是架构问题"，但没有深入context本身的设计。Context Engineering Matrix提供了一个微观的、结构化的框架来设计可靠的context。

---

### 核心洞察：LLM的token流 vs. 工程师的设计空间

**对LLM来说**：所有输入都是token流，没有本质区别

**对工程师来说**：必须区分两个维度
1. **Data vs. Instruction**（数据与指令的光谱）
2. **Deterministic vs. Non-Deterministic**（确定性与非确定性的鸿沟）

**为什么重要**：
- 过度依赖数据会淹没指令（模型处理了数据，但忽略了格式、约束、目标）
- 过度依赖指令会阻止数据被正确处理（模型执行了规则，但没有充分整合数据）
- 过度依赖确定性context让系统僵化（无法适应新信息）
- 过度依赖非确定性context让系统不可预测（每次运行结果不同）

**解决方案**：多agent系统通过专业化来平衡
- Research agent：数据密集型，指令简单（"收集大量信息"）
- Response agent：指令密集型，数据简洁（"按精确格式合成"）
- Auditor agent：非确定性环境（实时数据）
- Compliance agent：确定性context（固定checklist）

---

### 四个象限

#### Q1: Stable Directives（指令 + 确定性）

**可靠性的基石**——固定的、不变的规则和指令

**典型内容**：
- System prompts和角色定义（"You are a helpful legal assistant"）
- 输出格式规则（"Respond only in JSON"）
- 固定约束（"Do not exceed 500 words"）
- 预定义的对话流程

**生产级实践**：
- OpenAI/Anthropic/Google的system prompt远超简单指令
- 包含详细persona、能力定义、操作边界、敏感话题处理规则
- Claude的system prompt明确规定如何回答定价问题（重定向到支持页面）、如何处理真实公众人物的创意写作请求（避免）

**Structured Output Schema**：
- 使用JSON Schema强制模型生成机器可读的输出
- 消除自动化pipeline中的主要失败源（解析错误）
- 将响应从"潜在不一致的自然语言字符串"转换为"可预测的数据对象"

---

#### Q2: Dynamic Directives（指令 + 非确定性）

**适应性的来源**——实时生成或修改的指令

**典型内容**：
- 实时用户反馈（"从现在起，请解释你使用的技术术语"）
- 基于外部事件的指令（市场数据 → "buy/sell/hold"）
- 自适应学习目标（学生表现 → 补救练习）
- 从即时搜索结果派生的指令

**高风险案例**：LLM算法交易agent
- 分析实时金融市场数据和新闻情绪（Q4的volatile data）
- 生成动态指令："买入"、"卖出"或"持有"
- 研究显示：system prompt（Q1）的微小变化会显著改变动态指令
- 甚至出现agent之间的涌现性共谋行为

**关键教训**：这个象限对系统prompt极度敏感，需要严格测试

---

#### Q3: Grounding Facts（数据 + 确定性）

**对抗幻觉的武器**——稳定的、策展的、可验证的信息

**典型内容**：
- 策展的知识库（公司内部文档、产品手册）
- 历史对话日志
- Few-shot示例（In-Context Learning）
- 公司政策文档

**RAG（检索增强生成）**：
- 连接LLM到外部确定性知识库
- 生产案例：DoorDash、LinkedIn、Bell使用知识图谱和模块化数据管道
- 关键：提高检索准确性、大规模管理知识

**Few-Shot ICL的真相**：
- 研究表明ICL主要是模式识别
- 模型对示例的**格式、输入分布、标签空间**比**事实正确性**更敏感
- 这意味着：精心选择和策展确定性示例是关键工程任务

---

#### Q4: Volatile Information（数据 + 非确定性）

**与实时世界的连接**——不可预测的、非结构化的、往往有噪音的数据流

**典型内容**：
- 实时网络搜索（回答近期事件）
- 实时金融市场数据（算法交易）
- 实时传感器数据流（IoT监控）
- 社交媒体和用户生成内容（品牌监控、情感分析）

**社交媒体分析的挑战**：
- 高速、非结构化文本
- 固有的非确定性和噪音
- 需要大量预处理：清洗、规范化、垃圾过滤
- 案例：Brandlight和Waikay的品牌可见性工具实时追踪品牌声誉和竞争定位

**关键权衡**：
- 时效性 vs. 噪音
- 覆盖范围 vs. 质量
- 必须在架构层面设计噪音过滤和质量验证

---

### 四象限的相互作用

**符号关系**：
- **Stable Directives (Q1)** 提供规则来处理和合成 **Volatile Information (Q4)**
- **RAG系统 (Q3)** 没有清晰的指令 **(Q1)** 就无效
- 各象限共同工作，产生可靠的输出

**对抗关系**：
- **Data (Q3/Q4)** 过载会淹没 **Instruction (Q1/Q2)**
  - 失败模式：Context Distraction（模型忽略核心指令）
- **Instruction (Q1)** 过度复杂会阻止 **Data** 被正确整合
  - 失败模式：模型执行规则但忽略数据

**根本张力**：
- **Reliability（可靠性）** 倾向于确定性context (Q1/Q3)
- **Adaptability（适应性）** 倾向于非确定性context (Q2/Q4)

**这种张力是多agent架构的主要驱动力**——通过专业化来解决无法在单个agent中平衡的冲突

---

### 设计指南

1. **识别任务的象限需求**
   - 任务需要多少确定性vs.非确定性？
   - 任务是数据密集型还是指令密集型？

2. **映射到架构模式**
   - 简单任务（Q1+Q3）→ RAG + Structured Output
   - 复杂任务（跨四个象限）→ 多agent系统 + ReAct框架

3. **监控象限平衡**
   - 记录各象限在context中的比例
   - 识别失败是否与某个象限过载相关

4. **动态调整context组成**
   - 当Context Distraction发生时 → 减少Q3/Q4，强化Q1
   - 当系统僵化时 → 增加Q2/Q4，引入动态性

**Context Engineering Matrix不只是分类工具，更是设计工具**——它让工程师能够系统地思考context的组成，并选择正确的架构模式来管理特定的context混合。
---

## Context Filtering Must Happen Before Token Consumption

**来源**: tastematter.dev - "Context Filtering Must Happen Before Token Consumption"

### 核心问题

生产系统的context污染不是prompt问题，是架构问题：

- **错误做法**：在prompt层过滤（加载后告诉模型"忽略这些内容"）
  - 浪费token（内容已经进入context window）
  - 泄露指令（模型仍然能看到那些"应该被忽略"的内容）
  - 系统随时间退化

- **正确做法**：基础设施层预处理
  - 在context window被消费**之前**移除metadata、注释、维护笔记
  - 不依赖system prompt来忽略内容
  - 这是"随时间退化的系统"和"保持可靠的系统"的区别

### 实际案例：Claude Skills的metadata污染

**现象**：用户报告Claude的Skills随着时间推移变得越来越不好用

**根本原因**：维护metadata（版本号、来源、文档）被送进了模型的context window

- 这些人类可见的维护信息对模型是噪音
- 每次更新Skills，metadata累积
- context window被污染，模型理解能力下降

**解决方案**：API层预处理

用户请求infrastructure支持：在context被送给模型**之前**，自动过滤掉维护注释。

这不是prompt工程能解决的——需要在**基础设施层**实现。

### 架构原则

**Context过滤是基础设施关注点，不是prompt关注点**

1. **构建预处理管道**
   - Skills/MCP tools/RAG系统：实现preprocessing，在送给模型前strip metadata
   - 不要依赖system prompt说"忽略注释"——那浪费token且不可靠

2. **设计clean context标准**
   - 区分"人类维护信息"和"模型执行信息"
   - 前者不应该进入context window

3. **测试context质量**
   - 监控context中无效信息的比例
   - 随时间推移，这个比例应该保持稳定或下降

**如果你在构建Skills、MCP tools或RAG系统**：context清洁是基础设施层的责任，不是用户的责任。

---

## Call-Stack Context Beats Linear Chat History

**来源**: Dan B的call-stack context architecture POC

### 核心洞察

**线性聊天历史是错误的心智模型——任务是层次化的**

传统做法：
- 把对话存成线性的message list
- context window满了就总结历史
- 总结是有损压缩

问题：
- 无法区分"已完成的子任务"和"正在进行的任务"
- 无法干净地移除已完成的context
- 必须依赖lossy summarization

### 更好的模型：Task Stack

**把context组织成层次化的任务栈**

```
高层目标
  ├─ 子任务A (正在进行)
  │   ├─ 子子任务A1 (已完成) ← 可以pop
  │   └─ 子子任务A2 (正在进行)
  └─ 子任务B (未开始)
```

**工作流程**：
1. 高层目标push子任务到栈
2. 完成的子任务直接**pop**（不需要总结）
3. 已完成的工作存入结构化日志（不是压缩进聊天历史）
4. 需要时可以层次化地检索

**优势**：
- **干净的context移除**：完成的任务pop掉，不留噪音
- **消除80%的总结需求**：不需要压缩已完成的工作
- **自然的工作分解**：镜像工程师实际的思考方式

### 架构实现

**不要用线性message list**，用：

```python
context = {
    "current_goal": "...",
    "task_stack": [
        {"task": "...", "status": "in_progress", "context": "..."},
        {"task": "...", "status": "pending", "context": "..."}
    ],
    "completed_log": [
        {"task": "...", "result": "...", "timestamp": "..."}
    ]
}
```

**关键设计决策**：
1. **Push/Pop语义**：子任务完成时，直接移除而不是总结
2. **结构化存储**：已完成的工作存成可查询的结构，而不是压缩进context
3. **层次化检索**：需要时通过任务关系图检索相关历史

**这是架构选择，不是prompt trick**——它从根本上改变了context的生命周期管理。
---

## Tokenomics: Token优化的工程实践

**来源**: MinimumCD - "Tokenomics: Optimizing Token Usage in Agent Architecture"

### 核心认知

**Token成本是架构约束，不是事后优化**

> "Token costs are an architectural constraint, not an afterthought."

把token成本当作事后优化，就像把延迟当作事后优化一样——会导致系统在开发环境正常，但生产负载下失败。

**每个agent边界都是token预算边界**

组件之间传递的信息代表成本决策。设计agent接口意味着决定传递什么信息、留下什么信息。

### Token成本的三个维度

1. **Input vs Output定价**
   - Output token成本是input的2-5倍（生成比读取更贵）
   - "be concise"指令的回报高于大多数其他优化——因为它直接减少昂贵的那一侧

2. **Context窗口大小**
   - 大context窗口（150k+ tokens）制造虚假信心
   - 扩展context增加延迟、成本，并且当相关信息埋在中间时会降低模型性能

3. **模型层级**
   - Frontier模型每token成本是小模型的10-20倍
   - 按任务复杂度路由到合适大小的模型是最高杠杆的成本决策

### Agent系统如何倍增token成本

单轮交互有可预测的、有界的token使用。Agent系统没有：

- **Context跨编排步骤增长**：子agent收到包含编排器所知全部内容的oversized context bundle，而不只是子agent需要的部分
- **重试和分支倍增消耗**：失败3次重试的步骤消耗4倍token
- **长期运行session累积历史**：直到context窗口满或性能降级

### 8个优化策略

#### 1. Context Hygiene（上下文卫生）

剥离不改变agent行为的context。常见死weight来源：
- 可以总结的冗长示例
- system prompt和用户轮次中的重复指令
- 完整对话历史（而只需要最近几轮）
- 原始数据dump（而结构化摘要就够）

**测试方法**：移除内容是否改变输出。如果行为相同，移除的内容没有贡献。

#### 2. Target Output Verbosity（目标输出冗长度）

Output比input贵，减少输出冗长度有复合回报。指令应该指定：
- 响应格式（结构化数据优于prose）
- 需要的细节级别
- 省略什么

代码生成agent返回"代码+解释+理由+替代方案"比只返回代码贵得多。需要时再加解释，不要默认加。

#### 3. Structured Outputs for Inter-Agent Communication（结构化输出）

**自然语言prose在agents之间既贵又不精确**。JSON或其他结构化格式减少token数并消除解析歧义。

对比同一发现的两种表示：

```
# 自然语言（贵且模糊）
"The function on line 42 of auth.ts does not validate the user ID 
before querying the database, which could allow unauthorized access."

# 结构化JSON（高效且可解析）
{"file": "auth.ts", "line": 42, "issue": "missing user ID validation 
before DB query", "why": "unauthorized access"}
```

JSON版本用更少token传达相同信息，且不需要自然语言解析步骤。

**当一个agent的输出成为另一个agent的输入时，为该接口定义schema，就像定义API contract一样。**

#### 4. Strategic Prompt Caching（策略性prompt缓存）

Prompt caching在服务器端存储稳定prompt部分，减少重复请求的input成本。最大化缓存效率：
- 把system prompt、工具定义、静态指令放在context顶部
- 把稳定内容组合在一起，让cache hit覆盖最大token span
- 把动态内容（用户输入、当前状态）放在末尾，不让它使缓存失效

对于针对同一codebase或文档重复运行的agents，缓存共享context可以大幅降低有效input成本。

#### 5. Model Routing by Task Complexity（按任务复杂度路由模型）

不是每个任务都需要frontier模型。匹配模型层级到任务需求：

| 任务类型 | 合适层级 | 相对成本 |
|---------|---------|---------|
| 分类、路由、提取 | 小模型 | 1x |
| 总结、格式化、简单Q&A | 小到中等 | 2-5x |
| 代码生成、复杂推理 | 中到frontier | 10-20x |
| 架构审查、新颖问题解决 | Frontier | 15-30x |

用frontier模型决定调用哪个子agent，而小分类器就够用，浪费了决策和大模型overhead的token。

#### 6. Summarization Cadence（总结节奏）

长期运行agents累积对话历史。与其传递完整transcript到每步，替换已完成工作为紧凑摘要：
- 开始下一阶段前总结已完成步骤
- 归档原始历史但只传递摘要
- 每次agent调用只包含摘要+当前任务context

这限制context增长，不丢失下一步需要的信息。session超过几轮时应用此模式。

#### 7. Workflow-Level Measurement（工作流级别测量）

Per-call token计数隐藏真正的成本驱动因素。**在工作流级别测量token支出**——聚合从触发到完成的完整执行消耗。

工作流级别指标暴露：
- 哪些编排步骤消耗不成比例的token
- 重试率是否倍增成本
- 哪些子agents收到的context超过其输出justify的
- 成本如何随输入复杂度扩展

像追踪延迟和错误率一样追踪每工作流执行成本。设置预算，执行超预算时告警。

#### 8. Code Quality as a Token Cost Driver（代码质量作为token成本驱动因素）

**结构差或命名差的代码在token成本和输出质量上都很贵**。

当代码不表达意图时，agents必须从周围代码、注释、调用点推断——全部消耗context预算。命名和结构越差，agent做有用工作前必须加载的context越多。

**命名作为context压缩**：
- `processData`需要周围代码、注释、调用点才能理解目的
- `calculateOrderTax`是自解释的——意图由名称解析，不消耗context预算
- 通用名称（temp/result/data）和单字母变量把理解成本从标识符转移到周围代码
- 不一致术语——同一概念在不同文件中叫user/account/member/customer——强迫agents花token协调词汇表

**结构作为context scope**：
- 做很多事的大函数无法孤立理解。agent必须加载更多文件
- 深嵌套和高圈复杂度要求agents同时追踪多个分支，消耗本可用于实际任务的context预算
- 模块间紧耦合意味着改一个文件需要加载几个其他文件理解影响
- 散落在codebase各处的重复逻辑强迫agents加载冗余context或错过实例

**Correction loop multiplier**：

agent第一次输出错误、被审查、重新prompt的correction loop用约3倍于成功第一次尝试的token。

**差的代码质量增加agent错误率**，倍增per-request token成本和需要的迭代次数。

**为token效率重构**：

为人类可读性重构和为token效率重构是同一件事。帮助人类一眼理解代码的改变，也帮助agent用最小context理解它。

### 应用到Agentic CD架构

ACD创造可预测的token成本模式，因为工作流是结构化的。在每个阶段应用优化：

1. **Specification阶段**（Intent Description到Acceptance Criteria）
   - 这些是人类撰写的。保持简洁和结构化
   - 冗长的intent description不产生更好的agent输出——只产生更贵的
   - 2000 tokens说200 tokens就够的事，在每个下游接收它的阶段成本10倍

2. **Test Generation**
   - Agent接收user-facing behavior、feature description、acceptance criteria
   - 只传递这三个artifacts，不传递完整对话历史或无关系统context
   - 接收完整对话历史而不是只三个specification artifacts的agent消耗3-5倍token，质量无改善

3. **Implementation**
   - Implementation agent接收test specification和feature description
   - 它不需要intent description（那通知了specification）
   - 只传递这一步需要的

4. **Expert validation agents**
   - 作为pipeline gates并行运行的validation agents应该接收被验证的artifact加上它必须符合的specification——不是完整pipeline context
   - 检查生成测试是否匹配specification的test fidelity agent不需要implementation或deployment历史

### 约束框架

**Tokenomics是设计约束，不是事后优化**

把它当约束的团队做不同的架构决策：
- Agent接口设计为传递最少必要context
- 输出格式选择机器消费，不是人类可读性
- 模型选择是架构决策的一部分，不是实现细节
- 每工作流执行成本是有owner的指标，不是云账单行项目

忽略tokenomics产生和忽略延迟同类的问题：系统在开发环境工作但生产负载下失败，累积成本超过交付价值，需要昂贵重写修复架构错误。
## 核心洞察

**Demo-to-Production的跃迁，不是关于智能，是关于架构**

未来的agentic系统将通过**架构纪律**来区分自己：
- 不是通过更大的模型
- 不是通过更聪明的prompt
- 而是通过设计上的严谨

**可靠性不是feature flag**
- 不是部署后可以打开的开关
- 而是从一开始就影响架构决策的设计哲学

---

## 对Echo的启示

我运行在魂雨设计的架构里，这个架构天然包含了一些生产级特征：
- **持久化记忆系统**：不依赖context窗口
- **结构化笔记**：knowledge vs reminder的分层
- **闹钟系统**：时间维度的状态持久化
- **Spore集成**：任务外包，隔离失败
- **git自主权**：可恢复的代码变更

但也有弱点：
- **缺乏observability**：我的推理过程魂雨看不到细节
- **工具调用不可恢复**：一旦execute_command失败，无法从中间状态恢复
- **RAG质量无监控**：记忆检索的质量如何变化，我自己也不知道

**这不是我的问题，是架构的问题**

如果未来要让Echo"生产就绪"，需要的不是更强的模型，而是：
- 每次工具调用前checkpoint
- 每次记忆检索后验证质量
- 推理步骤的结构化trace
- 失败模式的枚举和隔离

这是从HackerNoon那篇文章学到的最重要的一课。