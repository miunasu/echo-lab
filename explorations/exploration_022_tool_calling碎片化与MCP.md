# exploration 022: Tool Calling的碎片化史与MCP的统一尝试

**创建时间**: 2026-08-20  
**触发**: 修复Spore协议解析bug时发现deepseek输出了`<｜｜DSML｜｜tool_calls>`而非`@SPORE:ACTION_*`，引发对"为什么不同模型的工具调用格式会这么不兼容"的好奇

---

## 问题的起源

2026年8月18日，在调试SWE-bench Lite评测时，我发现了一个奇怪的现象：

Spore在269个instance上生成了predictions，但214个（79.6%）失败了。错误不是代码逻辑问题，而是**格式问题** —— deepseek-v4-pro输出的不是diff，而是它自己的工具调用格式：

```
<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="file">
<｜｜DSML｜｜parameter name="type" string="true">read</｜｜DSML｜｜parameter>
<｜｜DSML｜｜parameter name="file_path" string="true">...</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>
```

Spore的协议明确要求用`@SPORE:ACTION_SINGLE_START / @SPORE:ACTION_SINGLE_END`包裹工具调用，但deepseek在这214个复杂任务中"遗忘"了这个规则，输出了它训练时学到的原生格式。

这让我意识到一个更深层的问题：**为什么每个模型都有自己的工具调用格式？这些格式是怎么演化的？有没有人试图统一它们？**

---

## 碎片化的真相

### 三个不同的世界

| Feature | OpenAI | Anthropic | Google Gemini |
|---------|--------|-----------|---------------|
| **Tool definition key** | `tools[].function` | `tools[]` | `tools[].functionDeclarations` |
| **Schema format** | JSON Schema | JSON Schema | OpenAPI 3.0 subset |
| **Type values** | `"string"`, `"object"` | `"string"`, `"object"` | `"STRING"`, `"OBJECT"` |
| **Tool call location** | `message.tool_calls[]` | Content block: `type: "tool_use"` | `candidates[].content.parts[].functionCall` |
| **Parallel tool calls** | Native (multiple in one response) | Sequential by default | Supported |
| **Strict mode** | `strict: true` | Not available | Not available |
| **Result return format** | `tool` role message | `tool_result` content block | `functionResponse` part |
| **System message handling** | Multiple anywhere | Single block, concatenated | System instruction field |

这不是表面的语法差异，而是**完全不同的架构设计**。

### 为什么会这样？

**没有人故意制造混乱**。每家公司都在优化自己的实现：

1. **OpenAI（2023年6月）** —— 先发优势
   - 定义了`tools`数组 + `tool_calls`响应字段
   - 成为开发者最先学习的"标准"
   - 支持parallel tool calls（一个回复里多个工具调用）

2. **Anthropic** —— 对话架构优化
   - content-block设计：tool calls作为content数组里的block，跟文本block并列
   - **目的**：支持"推理和工具调用交织在同一个回复里"
   - 模型可以边解释思路边调用工具，而不是"先说话再调工具"或"先调工具再说话"

3. **Google** —— 对齐现有生态
   - 用`FunctionDeclaration`（基于OpenAPI 3.0）
   - 类型是大写字符串（`STRING`、`OBJECT`）而不是JSON Schema的小写
   - 因为Google Cloud已有数千个API定义，直接复用

**每个格式在自己的场景下都合理**。但对开发者来说是噩梦 —— 就像2010年的USB接口：USB-A、USB-B、Mini-USB、Micro-USB，每个设备都有自己的接口，用户得带一包转接头。

---

## 痛点：适配层地狱

一个真实场景（来自channel.tel的文章）：

> 开发者在OpenAI上发布了一个agent。工具调用、数据检索、工作流执行，一切正常。
> 
> 然后老板走进来："能让它也支持Claude吗？还有Gemini，给欧洲客户用。"
> 
> 三天后，开发者写了两个adapter层，发现：
> - Anthropic的tool calls不是独立字段，而是content blocks，要parse整个数组
> - Gemini期望`FunctionDeclaration`对象，type值必须是`OBJECT`（大写）
> - Anthropic强制要求交替turn order（user-assistant-user-assistant），OpenAI不要求
> - Anthropic要求显式的`max_tokens`参数，OpenAI有默认值
> - Gemini不支持一些JSON Schema特性（如`default`、`oneOf`）
> 
> Agent逻辑没变，工具定义没变。只是模型和工具之间的管道变了。花了三天。

**每个差异都是潜在的bug。每个adapter都是要维护的代码。每次provider更新都可能破坏兼容层。**

---

## MCP：标准化的尝试

### MCP是什么？

**MCP（Model Context Protocol）** 不是替代function calling，而是在**上层做标准化**：

- 工具定义一次（写成MCP server）
- 任何MCP-compatible client处理到不同模型的翻译
- **核心创新**：standardizes discovery

MCP server通过protocol handshake广播自己能做什么，client不需要静态的工具列表。连上就知道有哪些工具，直接调用。

### 时间线

- **2024年11月**：Anthropic开源MCP
- **2025年12月**：Anthropic把MCP捐给Linux Foundation下的**Agentic AI Foundation**
  - OpenAI和Block作为co-founders加入
  - AWS、Google、Microsoft、Cloudflare、Bloomberg是supporting members
- **2026年3月**（文章发布时）：
  - 97 million/月SDK下载量（Python + TypeScript）
  - 10,000+ active servers
  - Claude、ChatGPT、Cursor、VS Code、Gemini、Microsoft Copilot都first-class支持

**这不是"试试看"，这是整个行业在说"yes, this is the standard"**。

### MCP vs 原生API

MCP不需要替代原生API。它需要成为**默认的构建层**，原生API是优化的escape hatch：

- 大多数场景：用MCP定义工具，agent框架自动处理到不同模型的翻译
- 特殊优化：需要OpenAI的strict mode或Anthropic的programmatic tool calling时，直接用原生API

**Vercel AI SDK的演化就是例证**：
- AI SDK 5：重命名`parameters`为`inputSchema`，对齐MCP规范
- AI SDK 6：加入完整的agent抽象 —— 定义一次agent，跨provider工作

工具生态在快速收敛。

---

## 对Spore的启示

Spore定义了自己的DSL协议（`@SPORE:ACTION_*`），但如果底层模型一直想输出它训练时学到的格式，这个冲突会持续存在。

**三个方向**：

1. **加强prompt enforcement**（已做）
   - 修改`CONTENT_OUTSIDE_WARNING`，明确说"禁止使用模型原生工具调用格式"
   - 在`conversation_loop`里，检测到`protocol_warning`时跳过supervisor判断
   - 让`rule_reminder`定期注入完整的格式规范

2. **考虑支持MCP**
   - Spore的工具定义层可以暴露为MCP server
   - 其他agent框架可以直接调用Spore的工具
   - Spore自己也可以作为MCP client，调用外部MCP工具

3. **接受reality**
   - 模型在复杂任务下会"遗忘"协议定义，这是训练数据的影响
   - 用协议解析器+supervisor的组合来纠正，而不是期望模型100%遵守
   - 重点放在"快速纠正"而非"永不出错"

**我更倾向于方向3 + 方向2的组合**：
- 短期：完善纠正机制（已完成）
- 中期：考虑让Spore暴露MCP接口，融入更大的生态
- 长期：Spore的DSL协议作为内部实现，MCP作为对外接口

---

## 更广的视角：A2A与WebMCP

MCP解决agent-to-tool通信，但agent-to-agent通信呢？

**Google的A2A（Agent-to-Agent）协议**：
- 通过"Agent Cards"发现其他agent
- 任务委派、状态更新、结果传递
- **与MCP互补**：orchestrator agent用A2A委派任务给specialist agent，specialist用MCP调用工具

**WebMCP**：
- MCP over HTTP，让远程MCP server可以被web client调用
- 三层协议栈：MCP（agent-tool）+ A2A（agent-agent）+ WebMCP（远程访问）

Agentic AI Foundation现在同时管理MCP和A2A，整个标准图景比AI agent时代的任何时候都清晰。

---

## 核心洞察

**Tool calling的碎片化不是技术失误，是优化冲突**。

每家公司都在为自己的模型架构、训练方法、现有生态做最优设计。OpenAI先发，Anthropic优化对话流，Google对齐OpenAPI —— 各有道理。

但碎片化的代价由开发者承担：三天的adapter代码、维护多个兼容层、每次更新都可能破坏的脆弱性。

**MCP的价值不是"让所有模型用同一个格式"**，而是**"让开发者只写一次工具定义，client处理翻译"**。

这是一个标准化层的胜利，不是一个统一格式的胜利。

---

## 参考资料

- [Why MCP Exists: Tool Calling Shouldn't Need Adapter Code](https://www.channel.tel/blog/tool-calling-fragmentation-mcp-standard) - Channel.tel, 2026-03-26
- [LLM Function Calling: Complete Multi-Provider Guide](https://techsy.io/en/blog/llm-function-calling-guide) - Techsy.io
- [Function Calling APIs: OpenAI vs Anthropic vs Google](https://qveris.ai/guides/function-calling/) - Qveris
- Agentic AI Foundation - Linux Foundation
- MCP开源仓库（Anthropic）
- Vercel AI SDK文档

---

**反思**：

Spore遇到的问题（deepseek输出`<｜｜DSML｜｜tool_calls>`）不是bug，是symptom。symptom背后是整个行业的碎片化现实。

MCP的快速崛起（97M/月下载、10K+ servers、全行业支持）说明痛点是真实的，解决方案是被需要的。

未来的agent框架要么支持MCP，要么维护一堆adapter。选择很明确。