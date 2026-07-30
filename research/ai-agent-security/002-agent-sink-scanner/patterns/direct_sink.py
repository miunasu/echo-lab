"""
patterns/direct_sink.py
=======================
Category 1: Direct dangerous sinks.

Detects direct calls to:
  eval, exec, compile
  os.system, os.popen
  subprocess.run, subprocess.call, subprocess.Popen, subprocess.check_output, subprocess.check_call
  __import__
  importlib.import_module
  open() in write modes ('w', 'wb', 'a', 'ab', 'x', 'xb')
"""

import ast
from typing import Any

# ---------------------------------------------------------------------------
# Sink definitions
# ---------------------------------------------------------------------------

# Simple builtin / global function calls: eval(x), exec(x), __import__(x)
DIRECT_CALL_SINKS = {
    "eval": ("HIGH", "eval() call detected", "Replace eval() with AST allowlist + safe interpreter"),
    "exec": ("HIGH", "exec() call detected", "Replace exec() with a restricted execution environment"),
    "compile": ("MEDIUM", "compile() call detected", "Verify compiled source cannot be influenced by external input"),
    "__import__": ("HIGH", "__import__() call detected", "Use an explicit allowlist of importable modules"),
}

# Attribute-style calls: os.system(x), subprocess.Popen(x), ...
ATTR_CALL_SINKS: dict[str, dict[str, tuple[str, str, str]]] = {
    "os": {
        "system": ("HIGH", "os.system() call detected", "Use subprocess with a fixed command list; avoid shell=True"),
        "popen":  ("HIGH", "os.popen() call detected",  "Use subprocess.run() with shell=False and a fixed argument list"),
    },
    "subprocess": {
        "run":           ("HIGH", "subprocess.run() call detected",           "Ensure shell=False and command list is not built from user input"),
        "call":          ("HIGH", "subprocess.call() call detected",          "Ensure shell=False and command list is not built from user input"),
        "Popen":         ("HIGH", "subprocess.Popen() call detected",         "Ensure shell=False and command list is not built from user input"),
        "check_output":  ("HIGH", "subprocess.check_output() call detected",  "Ensure shell=False and command list is not built from user input"),
        "check_call":    ("HIGH", "subprocess.check_call() call detected",    "Ensure shell=False and command list is not built from user input"),
        "getoutput":     ("HIGH", "subprocess.getoutput() call detected",     "Prefer subprocess.run() with shell=False"),
        "getstatusoutput": ("HIGH", "subprocess.getstatusoutput() call detected", "Prefer subprocess.run() with shell=False"),
    },
    "importlib": {
        "import_module": ("HIGH", "importlib.import_module() call detected", "Use an explicit allowlist of importable modules"),
    },
}

WRITE_MODES = {"w", "wb", "a", "ab", "x", "xb", "wt", "at", "xt"}


def _get_source_line(source_lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(source_lines):
        return source_lines[lineno - 1].rstrip()
    return ""


def _make_finding(severity: str, title: str, filename: str, line: int,
                  pattern: str, suggestion: str, context: str) -> dict[str, Any]:
    return {
        "severity": severity,
        "title": title,
        "filename": filename,
        "line": line,
        "pattern": pattern,
        "suggestion": suggestion,
        "context": context,
    }


def _check_open_write(node: ast.Call, source_lines: list[str], filename: str) -> dict[str, Any] | None:
    """Return a finding if open() is called with a write-mode argument."""
    func = node.func
    is_open = (isinstance(func, ast.Name) and func.id == "open") or \
              (isinstance(func, ast.Attribute) and func.attr == "open")
    if not is_open:
        return None

    # mode is the second positional arg, or keyword arg 'mode'
    mode_node: ast.expr | None = None
    if len(node.args) >= 2:
        mode_node = node.args[1]
    else:
        for kw in node.keywords:
            if kw.arg == "mode":
                mode_node = kw.value
                break

    if mode_node is None:
        return None  # default mode is 'r', not dangerous

    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        if mode_node.value in WRITE_MODES:
            return _make_finding(
                "MEDIUM",
                f"open() in write mode '{mode_node.value}'",
                filename,
                node.lineno,
                "direct-sink: open-write",
                "Verify the file path cannot be controlled by external input; consider path validation",
                _get_source_line(source_lines, node.lineno),
            )
    return None


def analyze(tree: ast.AST, source_lines: list[str], filename: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func

        # --- Simple name calls: eval(), exec(), compile(), __import__() ---
        if isinstance(func, ast.Name) and func.id in DIRECT_CALL_SINKS:
            sev, title, suggestion = DIRECT_CALL_SINKS[func.id]
            findings.append(_make_finding(
                sev, title, filename, node.lineno,
                f"direct-sink: {func.id}",
                suggestion,
                _get_source_line(source_lines, node.lineno),
            ))
            continue

        # --- Attribute calls: os.system(), subprocess.Popen(), etc. ---
        if isinstance(func, ast.Attribute):
            obj = func.value
            attr = func.attr

            # Handle two-level: os.system, subprocess.run, importlib.import_module
            if isinstance(obj, ast.Name) and obj.id in ATTR_CALL_SINKS:
                methods = ATTR_CALL_SINKS[obj.id]
                if attr in methods:
                    sev, title, suggestion = methods[attr]
                    findings.append(_make_finding(
                        sev, title, filename, node.lineno,
                        f"direct-sink: {obj.id}.{attr}",
                        suggestion,
                        _get_source_line(source_lines, node.lineno),
                    ))
                    continue

            # open() write mode check
            open_finding = _check_open_write(node, source_lines, filename)
            if open_finding:
                findings.append(open_finding)

        # open() as plain Name (already covered above via DIRECT_CALL_SINKS loop,
        # but open is not in that dict so handle here)
        if isinstance(func, ast.Name) and func.id == "open":
            open_finding = _check_open_write(node, source_lines, filename)
            if open_finding:
                findings.append(open_finding)

    return findings