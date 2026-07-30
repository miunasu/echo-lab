# agent-sink-scanner

Static analysis tool for detecting dangerous execution paths in Python Agent framework code.

Inspired by the Semantic Kernel RCE vulnerability class: attackers can use prompt injection
to bypass AST blocklists, traverse the Python type system, and reach arbitrary code execution.
This tool finds those patterns before deployment.

---

## What it detects

| Category | Description |
|----------|-------------|
| 1. Direct sinks | `eval`, `exec`, `compile`, `os.system`, `os.popen`, `subprocess.*`, `__import__`, `importlib.import_module`, `open()` in write mode |
| 2. Type traversal | `__class__`, `__bases__`, `__subclasses__`, `__mro__`, `__globals__`, `__builtins__`, `__dict__`, `load_module`, `BuiltinImporter` appearing near `eval`/`exec` in the same function |
| 3. Format-string + eval | f-string / `.format()` / `%` / string concat result flowing into `eval`/`exec` |
| 4. Framework annotations | `@kernel_function` / `@KernelFunction` methods whose parameters flow into dangerous sinks |
| 5. AST blocklist weakness | `ast.parse` -> blocklist check -> `eval`/`exec` pattern; flags as fragile, suggests allowlist |

---

## Installation

```bash
pip install -r requirements.txt
```

The only external dependency is `colorama` for terminal color output.
All analysis logic uses the Python standard library `ast` module.

---

## Usage

```bash
# Scan a directory
python scanner.py path/to/project/

# Scan a single file
python scanner.py path/to/plugin.py

# JSON output (machine-readable)
python scanner.py path/to/project/ --format json

# Markdown report saved to file
python scanner.py path/to/project/ --format markdown --output report.md

# Only show HIGH severity findings
python scanner.py path/to/project/ --severity HIGH

# Scan with Semantic Kernel framework context
python scanner.py path/to/project/ --framework semantic-kernel

# Disable taint annotation pass
python scanner.py path/to/project/ --no-taint
```

---

## Output example

```
[!] HIGH  eval() call detected
  File: plugins/code_runner.py, line 47
  Pattern: direct-sink: eval
  Tainted input: yes (parameter taint)
  Code:     result = eval(user_expression)
  Suggestion: Replace eval() with AST allowlist + safe interpreter

[*] MEDIUM  Type traversal attribute '__subclasses__' near eval/exec (distance=3 lines)
  File: plugins/code_runner.py, line 44
  Pattern: type-traversal: dunder-attr near eval
  Code:     subclasses = obj.__subclasses__()
  Suggestion: Audit whether eval/exec context allows access to type-system attributes

[i] INFO  @kernel_function annotation on method 'RunCode'
  File: plugins/code_runner.py, line 38
  Pattern: framework-audit: kernel-function annotation
  Suggestion: Verify this method should be AI-callable. Ensure all parameters are validated.
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | No HIGH findings |
| 1 | At least one HIGH finding detected |
| 2 | Invalid arguments or path not found |

---

## Architecture

```
agent-sink-scanner/
├── scanner.py          # CLI entry point, file discovery, orchestration
├── ast_analyzer.py     # Parses files, runs all pattern modules
├── dataflow.py         # Intra-function taint propagation (parameter -> sink)
├── patterns/
│   ├── __init__.py
│   ├── direct_sink.py      # Category 1: eval/exec/os.system/subprocess/...
│   ├── type_traversal.py   # Category 2: __class__/__subclasses__ near eval
│   ├── format_eval.py      # Category 3: f-string/format() -> eval
│   └── framework_audit.py  # Category 4+5: @kernel_function + AST blocklist
├── report.py           # Terminal / JSON / Markdown output rendering
├── requirements.txt
└── README.md
```

---

## Limitations

This is static analysis, not dynamic taint tracking:

- **False positives**: a detected sink call may not be reachable from external input
- **False negatives**: multi-file data flow and deeply indirect call chains are not tracked
- **Scope**: intra-function taint propagation only; cross-function flows are not followed
- **Intent**: surface obvious risk points for human audit, not exhaustive coverage

---

## Background

The Semantic Kernel RCE pattern (CVE-2026-26030):

```python
# Vulnerable pattern - blocklist is bypassable via type traversal
code = ast.parse(user_input)
for node in ast.walk(code):
    if type(node).__name__ in BLOCKED_NODES:   # blocklist check
        raise ValueError("blocked")
eval(compile(code, "<string>", "exec"))        # reached via __subclasses__ chain
```

Safe pattern - allowlist only permits known-safe node types:

```python
ALLOWED_NODES = {ast.Expression, ast.Num, ast.BinOp, ast.Add, ast.Sub, ...}
for node in ast.walk(code):
    if type(node) not in ALLOWED_NODES:
        raise ValueError("not allowed")
```