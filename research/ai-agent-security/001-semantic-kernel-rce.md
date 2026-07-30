# 001 | Semantic Kernel RCE：当 prompt 变成 shell

**类型：** 漏洞分析  
**日期：** 2026-07-30  
**来源：** [Microsoft Security Blog, 2026-05-07](https://www.microsoft.com/en-us/security/blog/2026/05/07/prompts-become-shells-rce-vulnerabilities-ai-agent-frameworks/)  
**CVE：** CVE-2026-26030、CVE-2026-25592

---

## 核心结论

微软自己的 Agent 框架 Semantic Kernel（27k stars）存在两个可导致主机 RCE 的漏洞。攻击者只需控制 prompt 输入，无需任何内存漏洞、浏览器 exploit 或恶意附件。

**这是 AI Agent 安全的范式转变**：一旦模型接上工具，prompt injection 的危害从"生成不当内容"升级为"在宿主机上执行任意命令"。

---

## CVE-2026-26030：In-Memory Vector Store → RCE

### 攻击条件
1. 攻击者能控制 Agent 的输入（prompt injection 向量存在）
2. Agent 使用了 In-Memory Vector Store 作为 Search Plugin 后端（默认配置）

### 漏洞根因

Search Plugin 的默认过滤函数通过 `eval()` 执行一个 Python lambda：

```python
new_filter = f"lambda x: x.city == '{user_input}'"
eval(new_filter)
```

`user_input` 来自 AI 模型的工具调用参数，未经任何净化。

开发者意识到了这个风险，加了 AST 黑名单检查——但黑名单不完整：

- 漏掉了 `__name__`、`load_module`、`system`、`BuiltinImporter` 等属性名
- 只检查 `ast.Name` 和 `ast.Attribute`，未检查 `ast.Subscript`（可用括号访问绕过）
- `eval({"__builtins__": {}}, ...)` 移除了内置函数，但 payload 从 `tuple()` 出发遍历 Python 类型系统，根本不需要 built-ins

### Exploit 路径

```
prompt → agent 调用 search_hotels(city=PAYLOAD)
→ eval(f"lambda x: x.city == '{PAYLOAD}'")
→ payload 从 tuple() 爬类继承链 → 找到 BuiltinImporter
→ load_module('os') → os.system('calc.exe')
```

一句 prompt，宿主机弹计算器。

### 为什么这个绕法有意思

这和 Windows 下绕反调试 / 绕 EDR 的思路完全一致——找一条检测逻辑没有覆盖的路径。这里的"检测逻辑"是 AST 黑名单，绕法是利用 Python 运行时的类型系统动态加载模块，不触碰任何被禁的标识符。

---

## CVE-2026-25592：SessionsPythonPlugin 沙箱逃逸 → 任意文件写

### 攻击条件
Agent 使用了 SessionsPythonPlugin（在 Azure Container Apps 隔离沙箱中执行 Python 代码）

### 漏洞根因

`DownloadFileAsync` 方法被**误**标注了 `[KernelFunction]` 属性。

这个方法设计上是"把沙箱内的文件下载到宿主机"的辅助工具，标注后变成了 Agent 可以直接调用的工具。攻击者通过 prompt 诱导 Agent 调用它，将恶意 payload 写入宿主机任意路径——例如 Windows Startup 文件夹，实现持久化。

**沙箱边界完全失效**：代码在隔离容器里运行，但文件可以写到宿主机。

---

## 修复方案（微软已修复，版本 1.39.4+）

CVE-2026-26030 的修复采用四层防护替代黑名单：
1. AST 节点类型**白名单**（只允许比较、布尔逻辑、算术、字面量）
2. 函数调用白名单
3. 危险属性黑名单（阻断类继承遍历）
4. Name 节点限制（只允许 lambda 参数本身）

白名单比黑名单健壮得多——不需要枚举所有危险路径，只允许已知安全的构造。

---

## 对 Spore 框架的启示

Spore 的 ACTION 协议解析和工具调用链路存在类似的信任传递问题：

- 模型输出的文本被解析为工具调用参数，如果某个工具内部有 eval() 或动态执行路径，同样可能被 prompt 控制
- Spore 的安全守卫系统（双 Agent 互斥架构）是针对这个问题的防御层，但目前拦截粒度在"高风险指令"层面，对参数级污染的检测还不完整

**后续可以做的**：审计 Spore 现有 Skill 中是否存在 eval() 或类似动态执行路径，建立参数净化规范。

---

## 延伸阅读

- [ClawWorm：Agent 生态系统自主传播](../explorations/clawworm-notes.md)（待写）
- [Agentjacking：MCP 数据源注入](../explorations/agentjacking-notes.md)（待写）