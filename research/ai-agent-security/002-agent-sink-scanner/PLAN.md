# 002 | agent-sink-scanner：Agent 框架危险执行路径静态分析工具

**类型：** 工具开发  
**状态：** 已完成  
**背景：** [001-semantic-kernel-rce.md](../001-semantic-kernel-rce.md)

---

## 动机

Semantic Kernel 的 RCE 漏洞说明了一件事：开发者知道 eval() 危险，所以加了黑名单——但黑名单漏了几个属性名，整个防御就失效了。

这类问题在 Agent 框架里会反复出现，因为框架开发者需要动态执行逻辑（filter、sandbox、plugin loader），而 AI 模型的输出会流进这些执行路径。

现有静态分析工具（bandit、semgrep）能检测直接的 eval() 调用，但检测不到：
- 通过 Python 类型系统遍历到达 eval/exec 的间接路径
- 字符串格式化后传给 eval 的数据流污染
- 被标注为 `@KernelFunction` 的危险方法（框架特定）

agent-sink-scanner 专门针对 Agent 框架代码的这类问题。

---

## 检测目标

### 类别 1：直接危险 sink
```
eval() / exec() / compile()
os.system() / os.popen() / subprocess.*
__import__() / importlib.import_module()
open() 写模式（任意文件写）
```

### 类别 2：类型系统遍历属性
Python 允许通过类继承链绕过沙箱，核心属性：
```
__class__ / __bases__ / __subclasses__() / __mro__
__globals__ / __builtins__ / __dict__
load_module / BuiltinImporter
```
这些属性出现在 eval 上下文附近，且来自外部输入时，是高风险信号。

### 类别 3：格式化字符串 + eval 组合
```python
# 这个模式是 CVE-2026-26030 的根因
template = f"lambda x: x.field == '{user_input}'"
eval(template)  # user_input 未净化
```
检测：字符串格式化（f-string / .format() / % 拼接）的结果直接或间接传入 eval/exec。

### 类别 4：框架特定标注审计
针对 Semantic Kernel：检测被标注 `[KernelFunction]` / `@kernel_function` 的方法，
报告其参数是否直接流入危险操作（CVE-2026-25592 的根因就是误标注）。

### 类别 5：AST blocklist 脆弱性检测
如果代码里存在"构建 AST 然后用 blocklist 判断后执行"的模式，
标记为"blocklist 防御，建议改为 allowlist"——因为 Python 的灵活性使 blocklist 天然脆弱。

---

## 设计

### 输入
- Python 源码文件或目录
- 可选：指定框架（semantic-kernel / langchain / custom）
- 可选：入口点标注（哪些函数接收外部输入）

### 核心模块

```
agent-sink-scanner/
├── scanner.py          # 主入口，遍历文件
├── ast_analyzer.py     # AST 遍历，检测 sink 和危险属性
├── dataflow.py         # 简单数据流：追踪外部输入 → sink 的路径
├── patterns/
│   ├── direct_sink.py      # 类别 1
│   ├── type_traversal.py   # 类别 2
│   ├── format_eval.py      # 类别 3
│   └── framework_audit.py  # 类别 4、5
└── report.py           # 输出格式（终端 / JSON / Markdown）
```

### 输出示例
```
[HIGH] eval() with unvalidated input
  File: semantic_kernel/memory/in_memory_store.py, line 47
  Pattern: format-string → eval
  Input source: kwargs[param.name] (tool call parameter)
  Suggestion: Replace eval() with AST allowlist + safe interpreter

[MEDIUM] Type traversal attributes in eval context
  File: plugins/code_runner.py, line 23
  Pattern: __class__.__subclasses__ accessible via string input
  Suggestion: Audit eval context, consider sandboxed execution

[INFO] @kernel_function annotation detected on file operation
  File: plugins/session_plugin.py, line 89
  Method: DownloadFileAsync
  Note: Verify this method should be AI-callable
```

---

## 局限性（诚实说明）

这是静态分析，不是动态污点追踪：
- 会有误报：危险调用不一定能被外部输入到达
- 会有漏报：复杂的间接路径（多层函数调用、反射）可能追不到
- 不支持跨文件数据流（第一版）

定位是"快速扫出明显风险点，给人工审计提供线索"，不是"完整覆盖所有路径"。

---

## 下一步

- [ ] 实现 ast_analyzer.py（类别 1、2）
- [ ] 实现 format_eval.py（类别 3）
- [ ] 用 Semantic Kernel 源码验证：能否检出 CVE-2026-26030 对应的代码位置
- [ ] 补充 Spore Skill 扫描：审计现有 Skill 里的危险路径